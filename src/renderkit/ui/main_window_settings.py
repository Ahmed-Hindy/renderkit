"""Settings persistence helpers for the RenderKit main window."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingSpec:
    """Describe how one main-window setting is read, written, and restored."""

    key: str
    default: Any
    value_type: type[Any]
    getter: Callable[[Any], Any]
    setter: Callable[[Any, Any], None]
    is_available: Callable[[Any], bool] = lambda _: True
    resetter: Callable[[Any], None] | None = None

    def reset(self, ui: Any) -> None:
        """Restore this setting to its default UI state."""
        if self.resetter is not None:
            self.resetter(ui)
            return
        self.setter(ui, self.default)


SETTINGS_SCHEMA: tuple[SettingSpec, ...] = (
    SettingSpec(
        "fps",
        24,
        int,
        lambda ui: ui.fps_spin.value(),
        lambda ui, value: ui.fps_spin.setValue(value),
    ),
    SettingSpec(
        "keep_source_fps",
        True,
        bool,
        lambda ui: ui.keep_source_fps_check.isChecked(),
        lambda ui, value: ui.keep_source_fps_check.setChecked(value),
    ),
    SettingSpec(
        "keep_source_frame_range",
        True,
        bool,
        lambda ui: ui.keep_source_frame_range_check.isChecked(),
        lambda ui, value: ui.keep_source_frame_range_check.setChecked(value),
    ),
    SettingSpec(
        "width",
        1920,
        int,
        lambda ui: ui.width_spin.value(),
        lambda ui, value: ui.width_spin.setValue(value),
    ),
    SettingSpec(
        "height",
        1080,
        int,
        lambda ui: ui.height_spin.value(),
        lambda ui, value: ui.height_spin.setValue(value),
    ),
    SettingSpec(
        "codec_text",
        "",
        str,
        lambda ui: ui.codec_combo.currentText(),
        lambda ui, value: ui.codec_combo.setCurrentText(value),
        resetter=lambda ui: ui.codec_combo.setCurrentIndex(0),
    ),
    SettingSpec(
        "keep_resolution",
        True,
        bool,
        lambda ui: ui.keep_resolution_check.isChecked(),
        lambda ui, value: ui.keep_resolution_check.setChecked(value),
    ),
    SettingSpec(
        "aspect_linked",
        True,
        bool,
        lambda ui: ui.aspect_link_btn.isChecked(),
        lambda ui, value: ui.aspect_link_btn.setChecked(value),
        lambda ui: hasattr(ui, "aspect_link_btn"),
    ),
    SettingSpec(
        "quality",
        10,
        int,
        lambda ui: ui.quality_slider.value(),
        lambda ui, value: ui.quality_slider.setValue(value),
    ),
    SettingSpec(
        "prefetch_workers",
        2,
        int,
        lambda ui: ui.prefetch_workers_spin.value(),
        lambda ui, value: ui.prefetch_workers_spin.setValue(value),
        lambda ui: hasattr(ui, "prefetch_workers_spin"),
    ),
    SettingSpec(
        "burnin_enable",
        True,
        bool,
        lambda ui: ui.burnin_enable_check.isChecked(),
        lambda ui, value: ui.burnin_enable_check.setChecked(value),
    ),
    SettingSpec(
        "burnin_frame",
        True,
        bool,
        lambda ui: ui.burnin_frame_check.isChecked(),
        lambda ui, value: ui.burnin_frame_check.setChecked(value),
    ),
    SettingSpec(
        "burnin_layer",
        True,
        bool,
        lambda ui: ui.burnin_layer_check.isChecked(),
        lambda ui, value: ui.burnin_layer_check.setChecked(value),
    ),
    SettingSpec(
        "burnin_fps",
        True,
        bool,
        lambda ui: ui.burnin_fps_check.isChecked(),
        lambda ui, value: ui.burnin_fps_check.setChecked(value),
    ),
    SettingSpec(
        "burnin_font_size",
        20,
        int,
        lambda ui: ui.burnin_font_size_spin.value(),
        lambda ui, value: ui.burnin_font_size_spin.setValue(value),
    ),
    SettingSpec(
        "burnin_opacity",
        30,
        int,
        lambda ui: ui.burnin_opacity_spin.value(),
        lambda ui, value: ui.burnin_opacity_spin.setValue(value),
    ),
    SettingSpec(
        "cs_enable",
        False,
        bool,
        lambda ui: ui.cs_enable_check.isChecked(),
        lambda ui, value: ui.cs_enable_check.setChecked(value),
    ),
    SettingSpec(
        "cs_columns",
        4,
        int,
        lambda ui: ui.cs_columns_spin.value(),
        lambda ui, value: ui.cs_columns_spin.setValue(value),
    ),
    SettingSpec(
        "cs_padding",
        4,
        int,
        lambda ui: ui.cs_padding_spin.value(),
        lambda ui, value: ui.cs_padding_spin.setValue(value),
    ),
    SettingSpec(
        "preview_scale",
        75,
        int,
        lambda ui: ui.preview_scale_spin.value(),
        lambda ui, value: ui.preview_scale_spin.setValue(value),
    ),
)


def save_settings(ui: Any) -> None:
    """Persist all available main-window settings."""
    for spec in SETTINGS_SCHEMA:
        if spec.is_available(ui):
            ui.settings.setValue(spec.key, spec.getter(ui))


def load_settings(ui: Any) -> None:
    """Restore all available main-window settings."""
    for spec in SETTINGS_SCHEMA:
        if not spec.is_available(ui):
            continue
        value = ui.settings.value(spec.key, spec.default, type=spec.value_type)
        spec.setter(ui, value)


def reset_settings(ui: Any) -> None:
    """Reset all available main-window settings to their defaults."""
    for spec in SETTINGS_SCHEMA:
        if spec.is_available(ui):
            spec.reset(ui)
