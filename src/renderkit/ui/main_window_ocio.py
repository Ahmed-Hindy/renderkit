"""OCIO, color grading, and preset UI controller helpers for the RenderKit main window."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from renderkit.core import presets as core_presets
from renderkit.core.config import (
    BurnInConfig,
    ContactSheetConfig,
    ConversionConfig,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.exceptions import ColorSpaceError, ConfigurationError
from renderkit.processing.color_space import (
    ColorSpacePreset,
    get_ocio_colorspace_label,
    get_ocio_displays,
    get_ocio_role_display_options,
    get_ocio_views,
    resolve_ocio_config_path,
)
from renderkit.processing.video_encoder import get_codec_profile

logger = logging.getLogger("renderkit.ui.main_window")

AUTO_OCIO_LABEL = "(Auto)"
_AUTO_SENTINELS = frozenset({"", AUTO_OCIO_LABEL, "(Default)", "Auto", "Default"})


def container_extension_for_codec(codec_id: str) -> str:
    """Return the default container file extension for a codec identifier.

    Args:
        codec_id: FFmpeg or RenderKit codec profile identifier.

    Returns:
        Container extension such as ``".mov"`` or ``".mp4"``.
    """
    normalized = codec_id.strip()
    if normalized.lower().startswith("dnxhd"):
        return ".mov"
    return get_codec_profile(normalized).container_ext


def build_slate_config_from_ui(ui: Any) -> Optional[SlateConfig]:
    """Build intro slate configuration from UI controls when enabled."""
    enable_check = getattr(ui, "slate_enable_check", None)
    if enable_check is None or not enable_check.isChecked():
        return None

    def _read_text(attr: str) -> str:
        widget = getattr(ui, attr, None)
        if widget is not None and hasattr(widget, "text"):
            return str(widget.text()).strip()
        return ""

    return SlateConfig(
        enabled=True,
        title=_read_text("slate_title_edit"),
        show=_read_text("slate_show_edit"),
        shot=_read_text("slate_shot_edit"),
        artist=_read_text("slate_artist_edit"),
        notes=_read_text("slate_notes_edit"),
    )


def build_watermark_config_from_ui(ui: Any, *, strict: bool = False) -> Optional[WatermarkConfig]:
    """Build watermark configuration from UI controls when enabled and non-empty.

    Args:
        ui: Main window or UI-like object exposing watermark controls.
        strict: When ``True``, raise :class:`ConfigurationError` if watermark
            is enabled with empty text.

    Returns:
        A :class:`WatermarkConfig` instance when enabled with non-empty text,
        otherwise ``None``.

    Raises:
        ConfigurationError: If ``strict=True`` and watermark is enabled with
            empty text.
    """
    enable_check = getattr(ui, "watermark_enable_check", None)
    if enable_check is None or not enable_check.isChecked():
        return None

    text_edit = getattr(ui, "watermark_text_edit", None)
    text = (
        str(text_edit.text()).strip()
        if text_edit is not None and hasattr(text_edit, "text")
        else ""
    )
    if not text:
        if strict:
            raise ConfigurationError("Watermark text must not be empty when watermark is enabled.")
        return None

    opacity_spin = getattr(ui, "watermark_opacity_spin", None)
    opacity = (
        int(opacity_spin.value())
        if opacity_spin is not None and hasattr(opacity_spin, "value")
        else 25
    )
    tiled_check = getattr(ui, "watermark_tiled_check", None)
    tiled = (
        bool(tiled_check.isChecked())
        if tiled_check is not None and hasattr(tiled_check, "isChecked")
        else False
    )
    return WatermarkConfig(text=text, opacity=opacity, tiled=tiled)


def get_configured_ocio_path(ui: Any) -> Optional[str]:
    """Return the non-empty explicit OCIO config path configured in the UI, if any."""
    edit = getattr(ui, "ocio_config_edit", None)
    if edit is not None and hasattr(edit, "text"):
        value = str(edit.text()).strip()
        return value or None
    fallback = getattr(ui, "ocio_config_path", None)
    if isinstance(fallback, str):
        cleaned = fallback.strip()
        return cleaned or None
    return None


def _read_ocio_combo_selection(ui: Any, combo_attr: str, fallback_attr: str) -> Optional[str]:
    combo = getattr(ui, combo_attr, None)
    if combo is not None:
        if hasattr(combo, "currentData"):
            data = combo.currentData()
            if isinstance(data, str):
                cleaned = data.strip()
                return cleaned or None
        if hasattr(combo, "currentText"):
            text = str(combo.currentText()).strip()
            if text in _AUTO_SENTINELS:
                return None
            return text
    fallback = getattr(ui, fallback_attr, None)
    if isinstance(fallback, str):
        cleaned = fallback.strip()
        return None if cleaned in _AUTO_SENTINELS else cleaned
    return None


def get_selected_ocio_display(ui: Any) -> Optional[str]:
    """Return the selected OCIO display name, or ``None`` for automatic selection."""
    return _read_ocio_combo_selection(ui, "ocio_display_combo", "ocio_display")


def get_selected_ocio_view(ui: Any) -> Optional[str]:
    """Return the selected OCIO view name, or ``None`` for automatic selection."""
    return _read_ocio_combo_selection(ui, "ocio_view_combo", "ocio_view")


def get_grade_values(ui: Any) -> tuple[float, float]:
    """Return ``(exposure, gamma)`` from the UI grade spinboxes or defaults."""
    exp_spin = getattr(ui, "exposure_spin", None)
    exposure = (
        float(exp_spin.value())
        if exp_spin is not None and hasattr(exp_spin, "value")
        else float(getattr(ui, "exposure", 0.0))
    )
    gamma_spin = getattr(ui, "gamma_spin", None)
    gamma = (
        float(gamma_spin.value())
        if gamma_spin is not None and hasattr(gamma_spin, "value")
        else float(getattr(ui, "gamma", 1.0))
    )
    if gamma <= 0.0:
        gamma = 1.0
    return exposure, gamma


def set_grade_values(ui: Any, exposure: float = 0.0, gamma: float = 1.0) -> None:
    """Update the UI exposure and gamma spinboxes without emitting redundant signals."""
    exp_spin = getattr(ui, "exposure_spin", None)
    if exp_spin is not None:
        exp_spin.blockSignals(True)
        try:
            exp_spin.setValue(float(exposure))
        finally:
            exp_spin.blockSignals(False)

    gamma_spin = getattr(ui, "gamma_spin", None)
    if gamma_spin is not None:
        gamma_spin.blockSignals(True)
        try:
            gamma_spin.setValue(max(0.1, float(gamma)))
        finally:
            gamma_spin.blockSignals(False)


def populate_color_space_combo_for_config(
    combo: Any, config_path: Optional[str] = None
) -> dict[str, str]:
    """Populate the input color space combo box from the active OCIO config.

    Args:
        combo: Target combo box widget.
        config_path: Optional explicit OCIO config path; uses bundled/env default when ``None``.

    Returns:
        Mapping of display labels to OCIO role names.
    """
    combo.clear()
    if config_path is None:
        role_options = get_ocio_role_display_options()
        utility_linear = get_ocio_colorspace_label("Utility - Linear - sRGB")
        if utility_linear:
            combo.addItem(utility_linear)
        if role_options:
            combo.addItems([label for label, _ in role_options])
            return dict(role_options)
        return {}

    try:
        import PyOpenColorIO as ocio

        resolved = resolve_ocio_config_path(config_path)
        cfg = ocio.Config.CreateFromFile(str(resolved))
        roles = sorted(cfg.getRoleNames())
        role_map: dict[str, str] = {}
        options: list[tuple[str, str]] = []
        for role in roles:
            space = cfg.getRoleColorSpace(role)
            if space:
                label = f"{role} ({space})"
                role_map[label] = role
                options.append((label, role))
        spaces = list(cfg.getColorSpaceNames())
        for label, _ in options:
            combo.addItem(label)
        for space in spaces:
            if combo.findText(space) < 0:
                combo.addItem(space)
        return role_map
    except Exception as exc:
        logger.warning("Failed to populate color spaces from OCIO '%s': %s", config_path, exc)
        return {}


def _select_combo_text(combo: Any, target: Optional[str]) -> None:
    if target is None:
        combo.setCurrentIndex(0)
        return
    idx = combo.findText(target)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    else:
        combo.addItem(target, target)
        combo.setCurrentIndex(combo.count() - 1)


def populate_ocio_views(
    ui: Any,
    config_path: Optional[str] = None,
    *,
    selected_view: Optional[str] = None,
) -> list[str]:
    """Populate the OCIO view combo box for the currently selected display."""
    view_combo = getattr(ui, "ocio_view_combo", None)
    if view_combo is None:
        return []

    display = get_selected_ocio_display(ui)
    active_config = config_path if config_path is not None else get_configured_ocio_path(ui)

    view_combo.blockSignals(True)
    try:
        view_combo.clear()
        view_combo.addItem(AUTO_OCIO_LABEL, "")
        if not display:
            view_combo.setEnabled(False)
            return []

        try:
            views = get_ocio_views(display, active_config)
        except ColorSpaceError as exc:
            logger.warning("Failed to discover OCIO views for display '%s': %s", display, exc)
            view_combo.setEnabled(False)
            return []

        for view_name in views:
            view_combo.addItem(view_name, view_name)
        view_combo.setEnabled(bool(views))
        _select_combo_text(view_combo, selected_view)
        return views
    finally:
        view_combo.blockSignals(False)


def populate_ocio_displays(
    ui: Any,
    config_path: Optional[str] = None,
    *,
    selected_display: Optional[str] = None,
    selected_view: Optional[str] = None,
) -> list[str]:
    """Discover OCIO displays and populate display/view dropdowns."""
    display_combo = getattr(ui, "ocio_display_combo", None)
    if display_combo is None:
        return []

    active_config = config_path if config_path is not None else get_configured_ocio_path(ui)
    try:
        resolved = resolve_ocio_config_path(active_config)
        displays = get_ocio_displays(resolved)
    except ColorSpaceError as exc:
        logger.warning("Failed to discover OCIO displays: %s", exc)
        displays = []

    display_combo.blockSignals(True)
    try:
        display_combo.clear()
        display_combo.addItem(AUTO_OCIO_LABEL, "")
        for display_name in displays:
            display_combo.addItem(display_name, display_name)
        _select_combo_text(display_combo, selected_display)
    finally:
        display_combo.blockSignals(False)

    populate_ocio_views(ui, config_path=active_config, selected_view=selected_view)
    return displays


def apply_ocio_config_path(ui: Any, ocio_path: Optional[str]) -> Optional[Path]:
    """Validate and apply an OCIO config path to the UI and refresh OCIO dropdowns.

    Args:
        ui: Main window instance.
        ocio_path: Explicit OCIO config path, or ``None``/empty to reset to default.

    Returns:
        Resolved Path if ``ocio_path`` was non-empty, otherwise ``None``.

    Raises:
        ColorSpaceError: If ``ocio_path`` is non-empty but invalid or unreadable.
    """
    cleaned = ocio_path.strip() if isinstance(ocio_path, str) else ""
    resolved: Optional[Path] = None
    if cleaned:
        resolved = resolve_ocio_config_path(cleaned)

    edit = getattr(ui, "ocio_config_edit", None)
    if edit is not None:
        edit.blockSignals(True)
        try:
            edit.setText(str(resolved) if resolved is not None else "")
        finally:
            edit.blockSignals(False)

    cs_combo = getattr(ui, "color_space_combo", None)
    if cs_combo is not None:
        cs_combo.blockSignals(True)
        try:
            ui._ocio_role_display_map = populate_color_space_combo_for_config(
                cs_combo, str(resolved) if resolved is not None else None
            )
        finally:
            cs_combo.blockSignals(False)

    populate_ocio_displays(ui, str(resolved) if resolved is not None else None)
    return resolved


def _apply_burnin_preset(ui: Any, burnin_config: Optional[BurnInConfig]) -> None:
    if not hasattr(ui, "burnin_enable_check"):
        return
    zone_combo = getattr(ui, "burnin_zone_combo", None)
    if burnin_config is None:
        ui._preset_burnin_zones = {}
        if zone_combo is not None:
            zone_combo.blockSignals(True)
            try:
                zone_combo.setCurrentIndex(0)
            finally:
                zone_combo.blockSignals(False)
        ui.burnin_enable_check.setChecked(False)
        return

    ui.burnin_enable_check.setChecked(True)
    templates = [el.text_template for el in burnin_config.elements]
    if hasattr(ui, "burnin_frame_check"):
        ui.burnin_frame_check.setChecked(any("{frame}" in t for t in templates))
    if hasattr(ui, "burnin_layer_check"):
        ui.burnin_layer_check.setChecked(any("{layer}" in t for t in templates))
    if hasattr(ui, "burnin_fps_check"):
        ui.burnin_fps_check.setChecked(any("{fps" in t for t in templates))
    if hasattr(ui, "burnin_font_size_spin") and burnin_config.elements:
        ui.burnin_font_size_spin.setValue(int(burnin_config.elements[0].font_size))
    if hasattr(ui, "burnin_opacity_spin"):
        ui.burnin_opacity_spin.setValue(int(burnin_config.background_opacity))

    zones = {el.zone for el in burnin_config.elements}
    preset_zones: dict[str, Optional[str]] = {}
    target_zone: Optional[str] = None
    if len(zones) == 1:
        only_zone = next(iter(zones))
        if isinstance(only_zone, str) and only_zone:
            target_zone = only_zone
    elif len(zones) > 1:
        for el in burnin_config.elements:
            if "{frame}" in el.text_template:
                preset_zones["frame"] = el.zone
            if "{layer}" in el.text_template:
                preset_zones["layer"] = el.zone
            if "{fps" in el.text_template:
                preset_zones["fps"] = el.zone

    ui._preset_burnin_zones = preset_zones
    if zone_combo is not None:
        zone_combo.blockSignals(True)
        try:
            if target_zone is not None:
                idx = zone_combo.findData(target_zone)
                if idx < 0:
                    idx = zone_combo.findText(target_zone)
                zone_combo.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                zone_combo.setCurrentIndex(0)
        finally:
            zone_combo.blockSignals(False)


def _apply_contact_sheet_preset(
    ui: Any, enabled: bool, cs_config: Optional[ContactSheetConfig]
) -> None:
    if hasattr(ui, "cs_enable_check"):
        ui.cs_enable_check.setChecked(bool(enabled))
    if cs_config is not None:
        if hasattr(ui, "cs_columns_spin"):
            ui.cs_columns_spin.setValue(int(cs_config.columns))
        if hasattr(ui, "cs_padding_spin"):
            ui.cs_padding_spin.setValue(int(cs_config.padding))


def _apply_slate_preset(ui: Any, slate_config: Optional[SlateConfig]) -> None:
    if not hasattr(ui, "slate_enable_check"):
        return
    field_attrs = (
        ("slate_title_edit", "title"),
        ("slate_show_edit", "show"),
        ("slate_shot_edit", "shot"),
        ("slate_artist_edit", "artist"),
        ("slate_notes_edit", "notes"),
    )
    if slate_config is None:
        ui.slate_enable_check.setChecked(False)
        if hasattr(ui, "slate_preview_check"):
            ui.slate_preview_check.setChecked(False)
        for widget_attr, _ in field_attrs:
            widget = getattr(ui, widget_attr, None)
            if widget is not None and hasattr(widget, "setText"):
                widget.setText("")
        return

    ui.slate_enable_check.setChecked(bool(slate_config.enabled))
    for widget_attr, field_name in field_attrs:
        widget = getattr(ui, widget_attr, None)
        if widget is not None and hasattr(widget, "setText"):
            widget.setText(str(getattr(slate_config, field_name, "")))


def _apply_watermark_preset(ui: Any, watermark_config: Optional[WatermarkConfig]) -> None:
    if not hasattr(ui, "watermark_enable_check"):
        return
    if watermark_config is None:
        ui.watermark_enable_check.setChecked(False)
        if hasattr(ui, "watermark_text_edit"):
            ui.watermark_text_edit.setText("")
        if hasattr(ui, "watermark_opacity_spin"):
            ui.watermark_opacity_spin.setValue(25)
        if hasattr(ui, "watermark_tiled_check"):
            ui.watermark_tiled_check.setChecked(False)
        return

    ui.watermark_enable_check.setChecked(True)
    if hasattr(ui, "watermark_text_edit"):
        ui.watermark_text_edit.setText(str(watermark_config.text))
    if hasattr(ui, "watermark_opacity_spin"):
        ui.watermark_opacity_spin.setValue(int(watermark_config.opacity))
    if hasattr(ui, "watermark_tiled_check"):
        ui.watermark_tiled_check.setChecked(bool(watermark_config.tiled))


def apply_preset_data_to_ui(ui: Any, preset_data: dict[str, Any]) -> None:
    """Apply deserialized preset settings onto main window widgets."""
    if "codec" in preset_data and preset_data["codec"] and hasattr(ui, "codec_combo"):
        target_codec = str(preset_data["codec"])
        codec_map = getattr(ui, "_codec_map", {})
        for idx, codec_id in codec_map.items():
            if codec_id == target_codec:
                ui.codec_combo.setCurrentIndex(idx)
                break

    if (
        "quality" in preset_data
        and preset_data["quality"] is not None
        and hasattr(ui, "quality_slider")
    ):
        ui.quality_slider.setValue(int(preset_data["quality"]))

    if "prefetch_workers" in preset_data and preset_data["prefetch_workers"] is not None:
        if hasattr(ui, "prefetch_workers_spin"):
            ui.prefetch_workers_spin.setValue(int(preset_data["prefetch_workers"]))

    if "fps" in preset_data:
        fps_val = preset_data["fps"]
        if fps_val is None:
            if hasattr(ui, "keep_source_fps_check"):
                ui.keep_source_fps_check.setChecked(True)
        else:
            if hasattr(ui, "keep_source_fps_check"):
                ui.keep_source_fps_check.setChecked(False)
            if hasattr(ui, "fps_spin"):
                ui.fps_spin.setValue(float(fps_val))

    width_val = preset_data.get("width")
    height_val = preset_data.get("height")
    if width_val is not None and height_val is not None:
        if hasattr(ui, "keep_resolution_check"):
            ui.keep_resolution_check.setChecked(False)
        if hasattr(ui, "width_spin"):
            ui.width_spin.setValue(int(width_val))
        if hasattr(ui, "height_spin"):
            ui.height_spin.setValue(int(height_val))
    elif "width" in preset_data or "height" in preset_data:
        if hasattr(ui, "keep_resolution_check"):
            ui.keep_resolution_check.setChecked(True)

    start_val = preset_data.get("start_frame")
    end_val = preset_data.get("end_frame")
    if start_val is not None and end_val is not None:
        if hasattr(ui, "keep_source_frame_range_check"):
            ui.keep_source_frame_range_check.setChecked(False)
        if hasattr(ui, "start_frame_spin"):
            ui.start_frame_spin.setValue(int(start_val))
        if hasattr(ui, "end_frame_spin"):
            ui.end_frame_spin.setValue(int(end_val))

    if "layer" in preset_data and preset_data["layer"]:
        layer_name = str(preset_data["layer"])
        ui._pending_layer = layer_name
        if hasattr(ui, "layer_combo"):
            idx = ui.layer_combo.findText(layer_name)
            if idx >= 0:
                ui.layer_combo.setCurrentIndex(idx)

    ocio_path = preset_data.get("ocio_config_path")
    if "ocio_config_path" in preset_data:
        try:
            apply_ocio_config_path(ui, ocio_path)
        except ColorSpaceError as exc:
            logger.warning("Preset OCIO config '%s' could not be loaded: %s", ocio_path, exc)

    if "ocio_display" in preset_data or "ocio_view" in preset_data:
        populate_ocio_displays(
            ui,
            get_configured_ocio_path(ui),
            selected_display=preset_data.get("ocio_display"),
            selected_view=preset_data.get("ocio_view"),
        )

    input_space = preset_data.get("explicit_input_color_space")
    if input_space and hasattr(ui, "color_space_combo"):
        idx = ui.color_space_combo.findText(str(input_space))
        if idx < 0:
            ui.color_space_combo.addItem(str(input_space))
            idx = ui.color_space_combo.count() - 1
        ui.color_space_combo.setCurrentIndex(idx)

    exposure = preset_data.get("exposure", 0.0)
    gamma = preset_data.get("gamma", 1.0)
    set_grade_values(
        ui,
        exposure=float(exposure) if exposure is not None else 0.0,
        gamma=float(gamma) if gamma is not None else 1.0,
    )

    if "contact_sheet_mode" in preset_data or "contact_sheet_config" in preset_data:
        _apply_contact_sheet_preset(
            ui,
            bool(preset_data.get("contact_sheet_mode", False)),
            preset_data.get("contact_sheet_config"),
        )

    if "burnin_config" in preset_data:
        _apply_burnin_preset(ui, preset_data.get("burnin_config"))

    if "slate_config" in preset_data:
        _apply_slate_preset(ui, preset_data.get("slate_config"))

    if "watermark_config" in preset_data:
        _apply_watermark_preset(ui, preset_data.get("watermark_config"))


def load_preset_into_ui(ui: Any, preset_path: str | Path) -> dict[str, Any]:
    """Resolve, load, and apply a JSON preset file to the UI.

    Args:
        ui: Main window instance.
        preset_path: Preset path or name resolved via ``resolve_preset_path`` if available.

    Returns:
        The deserialized preset dictionary.
    """
    resolver = getattr(core_presets, "resolve_preset_path", None)
    resolved = resolver(preset_path) if resolver is not None else Path(preset_path)
    preset_data = core_presets.load_preset(resolved)
    apply_preset_data_to_ui(ui, preset_data)
    return preset_data


def save_preset_from_ui(ui: Any, preset_path: str | Path) -> Path:
    """Serialize current UI conversion settings to a JSON preset file.

    Args:
        ui: Main window instance.
        preset_path: Destination JSON file path.

    Returns:
        Destination ``Path`` written to disk.
    """
    target_path = Path(preset_path)
    resolved_codec = ui._selected_codec_id() if hasattr(ui, "_selected_codec_id") else "libx264"
    ext = container_extension_for_codec(resolved_codec)
    dummy_out = Path(f"preset_output{ext}")

    if hasattr(ui, "_build_conversion_config_from_ui"):
        pattern_combo = getattr(ui, "input_pattern_combo", None)
        current_pattern = pattern_combo.currentText().strip() if pattern_combo is not None else ""
        config: ConversionConfig = ui._build_conversion_config_from_ui(dummy_out, resolved_codec)
        if not current_pattern:
            config.input_pattern = "render.%04d.exr"
    else:
        exposure, gamma = get_grade_values(ui)
        config = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path=str(dummy_out),
            codec=resolved_codec,
            color_space_preset=ColorSpacePreset.OCIO_CONVERSION,
            ocio_config_path=get_configured_ocio_path(ui),
            ocio_display=get_selected_ocio_display(ui),
            ocio_view=get_selected_ocio_view(ui),
            exposure=exposure,
            gamma=gamma,
            slate_config=build_slate_config_from_ui(ui),
            watermark_config=build_watermark_config_from_ui(ui, strict=True),
        )

    core_presets.save_preset(config, target_path)
    return target_path
