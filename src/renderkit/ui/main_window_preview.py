"""Preview request assembly for the RenderKit main window."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.ui.main_window_ocio import (
    build_slate_config_from_ui,
    build_watermark_config_from_ui,
    get_configured_ocio_path,
    get_grade_values,
    get_selected_ocio_display,
    get_selected_ocio_view,
)
from renderkit.ui.main_window_sequence import extract_frame_number


@dataclass(frozen=True)
class PreviewRequest:
    """All arguments needed to load one preview frame."""

    sample_path: Path
    preset: ColorSpacePreset
    input_space: Optional[str]
    layer: Optional[str]
    cs_config: Optional[ContactSheetConfig]
    burnin_config: Optional[BurnInConfig]
    burnin_metadata: Optional[dict[str, Any]]
    preview_scale: float
    ocio_config_path: Optional[str] = None
    ocio_display: Optional[str] = None
    ocio_view: Optional[str] = None
    exposure: float = 0.0
    gamma: float = 1.0
    watermark_config: Optional[WatermarkConfig] = None
    slate_config: Optional[SlateConfig] = None
    preview_slate: bool = False


def get_selected_burnin_zone(ui: Any) -> Optional[str]:
    """Return the selected burn-in HUD zone name, or ``None`` for automatic layout."""
    combo = getattr(ui, "burnin_zone_combo", None)
    if combo is None:
        return None
    if hasattr(combo, "currentData"):
        data = combo.currentData()
        if isinstance(data, str):
            cleaned = data.strip()
            return cleaned or None
        if data is None:
            return None
    if hasattr(combo, "currentText"):
        text = str(combo.currentText()).strip()
        if not text or text == "(Auto)":
            return None
        return text
    return None


def build_burnin_config(ui: Any, *, include_layer: bool) -> Optional[BurnInConfig]:
    """Build burn-in settings from the current main-window UI state."""
    if not ui.burnin_enable_check.isChecked():
        return None

    selected_zone = get_selected_burnin_zone(ui)
    preset_zones = getattr(ui, "_preset_burnin_zones", None)
    if not isinstance(preset_zones, dict):
        preset_zones = {}

    def _zone_for(key: str) -> Optional[str]:
        if selected_zone is not None:
            return selected_zone
        zone_val = preset_zones.get(key)
        return str(zone_val) if isinstance(zone_val, str) and zone_val else None

    burnin_elements = []
    font_size = ui.burnin_font_size_spin.value()
    if ui.burnin_frame_check.isChecked():
        burnin_elements.append(
            BurnInElement(
                text_template="Frame: {frame}",
                x=0,
                y=10,
                font_size=font_size,
                alignment="left",
                zone=_zone_for("frame"),
            )
        )
    if include_layer and ui.burnin_layer_check.isChecked():
        burnin_elements.append(
            BurnInElement(
                text_template="Layer: {layer}",
                x=0,
                y=10,
                font_size=font_size,
                alignment="center",
                zone=_zone_for("layer"),
            )
        )
    if ui.burnin_fps_check.isChecked():
        burnin_elements.append(
            BurnInElement(
                text_template="FPS: {fps:.2f}",
                x=0,
                y=10,
                font_size=font_size,
                alignment="right",
                zone=_zone_for("fps"),
            )
        )

    if not burnin_elements:
        return None
    return BurnInConfig(
        elements=burnin_elements,
        background_opacity=ui.burnin_opacity_spin.value(),
    )


def build_preview_contact_sheet_config(ui: Any, *, scrubbing: bool) -> Optional[ContactSheetConfig]:
    """Build contact-sheet settings for a preview request."""
    if not ui.cs_enable_check.isChecked() or scrubbing:
        return None

    layer_width = None
    layer_height = None
    if not ui.keep_resolution_check.isChecked():
        layer_width = ui.width_spin.value()
        layer_height = ui.height_spin.value()

    show_labels = ui.burnin_enable_check.isChecked() and ui.burnin_layer_check.isChecked()
    return ContactSheetConfig(
        columns=ui.cs_columns_spin.value(),
        thumbnail_width=None,
        padding=ui.cs_padding_spin.value(),
        show_labels=show_labels,
        font_size=ui.burnin_font_size_spin.value(),
        background_color=(0.1, 0.1, 0.1),
        layer_width=layer_width,
        layer_height=layer_height,
    )


def build_burnin_metadata(
    sample_path: Path,
    *,
    fps: float,
    layer: Optional[str],
    input_space: Optional[str],
) -> dict[str, Any]:
    """Build metadata used by preview burn-in rendering."""
    frame_number = extract_frame_number(sample_path)
    return {
        "frame": frame_number if frame_number is not None else 0,
        "file": sample_path.name,
        "fps": fps,
        "layer": layer or "RGBA",
        "colorspace": input_space or "Unknown",
    }


def build_preview_request(
    ui: Any,
    sample_path: Path,
    *,
    preset: ColorSpacePreset,
    input_space: Optional[str],
    scrubbing: bool,
) -> PreviewRequest:
    """Build the full preview widget request from the current UI state."""
    layer = ui.layer_combo.currentText()
    cs_config = build_preview_contact_sheet_config(ui, scrubbing=scrubbing)
    if cs_config is not None:
        layer = None

    burnin_config = None
    burnin_metadata = None
    watermark_config = None
    slate_config = None
    preview_slate = False
    if not scrubbing:
        burnin_config = build_burnin_config(
            ui,
            include_layer=not ui.cs_enable_check.isChecked(),
        )
        watermark_config = build_watermark_config_from_ui(ui)
        slate_config = build_slate_config_from_ui(ui)
        slate_preview_check = getattr(ui, "slate_preview_check", None)
        preview_slate = (
            bool(slate_preview_check.isChecked())
            if slate_preview_check is not None and hasattr(slate_preview_check, "isChecked")
            else False
        )
        if (
            burnin_config is not None
            or watermark_config is not None
            or (preview_slate and slate_config is not None)
        ):
            burnin_metadata = build_burnin_metadata(
                sample_path,
                fps=float(ui.fps_spin.value()),
                layer=layer,
                input_space=input_space,
            )

    exposure, gamma = get_grade_values(ui)
    return PreviewRequest(
        sample_path=sample_path,
        preset=preset,
        input_space=input_space,
        layer=layer,
        cs_config=cs_config,
        burnin_config=burnin_config,
        burnin_metadata=burnin_metadata,
        preview_scale=ui.preview_scale_spin.value() / 100.0,
        ocio_config_path=get_configured_ocio_path(ui),
        ocio_display=get_selected_ocio_display(ui),
        ocio_view=get_selected_ocio_view(ui),
        exposure=exposure,
        gamma=gamma,
        watermark_config=watermark_config,
        slate_config=slate_config,
        preview_slate=preview_slate,
    )


def load_preview_for_frame(
    ui: Any,
    sample_path: Path,
    *,
    preset: ColorSpacePreset,
    input_space: Optional[str],
    scrubbing: bool = False,
) -> PreviewRequest:
    """Build a preview request for a frame and dispatch it to ``ui.preview_widget``."""
    request = build_preview_request(
        ui,
        sample_path,
        preset=preset,
        input_space=input_space,
        scrubbing=scrubbing,
    )
    ui._last_preview_path = sample_path
    ui.preview_widget.load_preview(
        request.sample_path,
        request.preset,
        input_space=request.input_space,
        layer=request.layer,
        cs_config=request.cs_config,
        burnin_config=request.burnin_config,
        burnin_metadata=request.burnin_metadata,
        preview_scale=request.preview_scale,
        ocio_config_path=request.ocio_config_path,
        ocio_display=request.ocio_display,
        ocio_view=request.ocio_view,
        exposure=request.exposure,
        gamma=request.gamma,
        watermark_config=request.watermark_config,
        slate_config=request.slate_config,
        preview_slate=request.preview_slate,
    )
    return request
