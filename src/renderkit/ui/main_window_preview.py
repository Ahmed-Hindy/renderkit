"""Preview request assembly for the RenderKit main window."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import BurnInConfig, BurnInElement, ContactSheetConfig
from renderkit.processing.color_space import ColorSpacePreset
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
        background_color=(0.1, 0.1, 0.1, 1.0),
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

    return PreviewRequest(
        sample_path=sample_path,
        preset=preset,
        input_space=input_space,
        layer=layer,
        cs_config=cs_config,
        burnin_config=burnin_config,
        burnin_metadata=burnin_metadata,
        preview_scale=ui.preview_scale_spin.value() / 100.0,
    )
