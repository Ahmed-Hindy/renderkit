"""Tests for main-window preview request assembly."""

from pathlib import Path

import pytest

from renderkit.processing.color_space import ColorSpacePreset
from renderkit.ui.main_window_preview import build_burnin_config, build_preview_request


class _DummyValue:
    def __init__(self, value) -> None:
        self._value = value

    def value(self):
        return self._value


class _DummyCheck:
    def __init__(self, checked: bool) -> None:
        self._checked = checked
        self.isChecked = self.is_checked

    def is_checked(self) -> bool:
        return self._checked


class _DummyCombo:
    def __init__(self, text: str) -> None:
        self._text = text
        self.currentText = self.current_text

    def current_text(self) -> str:
        return self._text


class _DummyWindow:
    def __init__(self, *, contact_sheet: bool, burnin: bool, keep_resolution: bool = True) -> None:
        self.preview_scale_spin = _DummyValue(50)
        self.keep_resolution_check = _DummyCheck(keep_resolution)
        self.width_spin = _DummyValue(1920)
        self.height_spin = _DummyValue(1080)
        self.cs_enable_check = _DummyCheck(contact_sheet)
        self.cs_columns_spin = _DummyValue(4)
        self.cs_padding_spin = _DummyValue(6)
        self.layer_combo = _DummyCombo("beauty")
        self.fps_spin = _DummyValue(24)
        self.burnin_enable_check = _DummyCheck(burnin)
        self.burnin_frame_check = _DummyCheck(True)
        self.burnin_layer_check = _DummyCheck(True)
        self.burnin_fps_check = _DummyCheck(True)
        self.burnin_font_size_spin = _DummyValue(20)
        self.burnin_opacity_spin = _DummyValue(30)


def test_build_preview_request_keeps_single_layer_preview_simple(tmp_path: Path) -> None:
    """Normal previews should preserve layer, color, and scale settings."""
    sample_path = tmp_path / "render.0001.exr"
    ui = _DummyWindow(contact_sheet=False, burnin=False)

    request = build_preview_request(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space="Linear",
        scrubbing=False,
    )

    assert request.sample_path == sample_path
    assert request.preset == ColorSpacePreset.OCIO_CONVERSION
    assert request.input_space == "Linear"
    assert request.layer == "beauty"
    assert request.cs_config is None
    assert request.burnin_config is None
    assert request.burnin_metadata is None
    assert request.preview_scale == pytest.approx(0.5)


def test_build_preview_request_uses_contact_sheet_config(tmp_path: Path) -> None:
    """Contact-sheet previews should delegate layer handling to the generator."""
    sample_path = tmp_path / "render.0001.exr"
    ui = _DummyWindow(contact_sheet=True, burnin=True, keep_resolution=False)

    request = build_preview_request(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space="ACEScg",
        scrubbing=False,
    )

    assert request.layer is None
    assert request.cs_config is not None
    assert request.cs_config.columns == 4
    assert request.cs_config.padding == 6
    assert request.cs_config.show_labels is True
    assert request.cs_config.layer_width == 1920
    assert request.cs_config.layer_height == 1080
    assert request.burnin_metadata["layer"] == "RGBA"


def test_build_preview_request_builds_burnin_metadata(tmp_path: Path) -> None:
    """Burn-in previews should include frame and display metadata."""
    sample_path = tmp_path / "render.0100.exr"
    ui = _DummyWindow(contact_sheet=False, burnin=True)

    request = build_preview_request(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space=None,
        scrubbing=False,
    )

    assert request.burnin_config is not None
    assert request.burnin_config.background_opacity == 30
    templates = [element.text_template for element in request.burnin_config.elements]
    assert templates == ["Frame: {frame}", "Layer: {layer}", "FPS: {fps:.2f}"]
    assert request.burnin_metadata == {
        "frame": 100,
        "file": "render.0100.exr",
        "fps": 24.0,
        "layer": "beauty",
        "colorspace": "Unknown",
    }


def test_build_preview_request_disables_expensive_options_while_scrubbing(tmp_path: Path) -> None:
    """Timeline scrubbing should skip contact-sheet and burn-in preview work."""
    sample_path = tmp_path / "render.0100.exr"
    ui = _DummyWindow(contact_sheet=True, burnin=True)

    request = build_preview_request(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space="Linear",
        scrubbing=True,
    )

    assert request.layer == "beauty"
    assert request.cs_config is None
    assert request.burnin_config is None
    assert request.burnin_metadata is None


def test_build_burnin_config_can_exclude_layer_template() -> None:
    """Contact-sheet conversions should be able to omit the per-layer burn-in."""
    ui = _DummyWindow(contact_sheet=True, burnin=True)

    config = build_burnin_config(ui, include_layer=False)

    assert config is not None
    templates = [element.text_template for element in config.elements]
    assert templates == ["Frame: {frame}", "FPS: {fps:.2f}"]
