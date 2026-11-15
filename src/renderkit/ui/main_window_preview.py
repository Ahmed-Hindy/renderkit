"""Preview request assembly for the RenderKit main window."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import BurnInConfig, BurnInElement, ContactSheetConfig
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.ui.main_window_ocio import (
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


def build_burnin_config(ui: Any, *, include_layer: bool) -> Optional[BurnInConfig]:
    """Build burn-in settings from the current main-window UI state."""
    if not ui.burnin_enable_check.isChecked():
        return None

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
    if not scrubbing:
        burnin_config = build_burnin_config(
            ui,
            include_layer=not ui.cs_enable_check.isChecked(),
        )
        if burnin_config is not None:
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
    )
    return request
