"""Tests for preview load wiring in main window logic."""

from pathlib import Path

import pytest

from renderkit.processing.color_space import ColorSpacePreset
from renderkit.processing.video_encoder import EncoderProbeResult
from renderkit.ui import main_window_logic


class _DummyValue:
    def __init__(self, value) -> None:
        self._value = value

    def value(self):
        return self._value


class _DummyCheck:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


class _DummyCombo:
    def __init__(self, text: str, index: int = 0) -> None:
        self._text = text
        self._index = index

    def currentText(self) -> str:
        return self._text

    def current_index(self) -> int:
        return self._index

    def set_current_index(self, index: int) -> None:
        self._index = index

    def __getattr__(self, name: str):
        if name == "currentIndex":
            return self.current_index
        if name == "setCurrentIndex":
            return self.set_current_index
        raise AttributeError(name)


class _DummyPreviewWidget:
    def __init__(self) -> None:
        self.calls = []

    def load_preview(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


class _DummyWindow(main_window_logic.MainWindowLogicMixin):
    def __init__(self, cs_enabled: bool, burnin_enabled: bool = False) -> None:
        self.preview_widget = _DummyPreviewWidget()
        self.preview_scale_spin = _DummyValue(100)
        self.keep_resolution_check = _DummyCheck(True)
        self.width_spin = _DummyValue(1920)
        self.height_spin = _DummyValue(1080)
        self.cs_enable_check = _DummyCheck(cs_enabled)
        self.cs_columns_spin = _DummyValue(4)
        self.cs_padding_spin = _DummyValue(4)
        self.layer_combo = _DummyCombo("RGBA")
        self.color_space_combo = _DummyCombo("Linear")
        self.fps_spin = _DummyValue(24)
        self.input_pattern_combo = _DummyCombo("render.%04d.exr")
        self.quality_slider = _DummyValue(8)
        self.start_frame_spin = _DummyValue(1001)
        self.end_frame_spin = _DummyValue(1010)
        self.prefetch_workers_spin = _DummyValue(3)
        self.codec_combo = _DummyCombo("H.264", index=0)
        self._codec_map = {0: "libx264", 1: "libx265"}
        self.burnin_enable_check = _DummyCheck(burnin_enabled)
        self.burnin_frame_check = _DummyCheck(True)
        self.burnin_layer_check = _DummyCheck(True)
        self.burnin_fps_check = _DummyCheck(True)
        self.burnin_font_size_spin = _DummyValue(20)
        self.burnin_opacity_spin = _DummyValue(30)
        self._ocio_role_display_map = {}
        self._last_preview_path = None


def test_load_preview_from_path_uses_load_preview(tmp_path: Path) -> None:
    """Ensure preview load uses preview widget API with scaled preview."""
    sample_path = tmp_path / "render.0001.exr"
    sample_path.write_text("data")

    window = _DummyWindow(cs_enabled=False, burnin_enabled=False)
    window._load_preview_from_path(sample_path)

    assert window.preview_widget.calls
    args, kwargs = window.preview_widget.calls[-1]
    assert args[0] == sample_path
    assert args[1] == ColorSpacePreset.OCIO_CONVERSION
    assert kwargs["layer"] == "RGBA"
    assert kwargs["cs_config"] is None
    assert kwargs["burnin_config"] is None
    assert kwargs["burnin_metadata"] is None
    assert kwargs["preview_scale"] == 1


def test_load_preview_from_path_builds_contact_sheet_config(tmp_path: Path) -> None:
    """Ensure contact sheet config is passed when enabled."""
    sample_path = tmp_path / "render.0001.exr"
    sample_path.write_text("data")

    window = _DummyWindow(cs_enabled=True, burnin_enabled=True)
    window._load_preview_from_path(sample_path)

    args, kwargs = window.preview_widget.calls[-1]
    assert args[0] == sample_path
    assert kwargs["layer"] is None
    cs_config = kwargs["cs_config"]
    assert cs_config is not None
    assert cs_config.columns == 4
    assert cs_config.thumbnail_width is None
    assert cs_config.padding == 4
    assert cs_config.show_labels is True
    assert cs_config.font_size == 20


def test_load_preview_from_path_builds_burnin_config(tmp_path: Path) -> None:
    """Ensure burn-in config is passed when enabled."""
    sample_path = tmp_path / "render.0100.exr"
    sample_path.write_text("data")

    window = _DummyWindow(cs_enabled=False, burnin_enabled=True)
    window._load_preview_from_path(sample_path)

    _, kwargs = window.preview_widget.calls[-1]
    burnin_config = kwargs["burnin_config"]
    assert burnin_config is not None
    assert burnin_config.background_opacity == 30
    metadata = kwargs["burnin_metadata"]
    assert metadata is not None
    assert metadata["frame"] == 100
    assert metadata["file"] == "render.0100.exr"


def test_build_conversion_config_from_ui_is_worker_free(tmp_path: Path) -> None:
    """Ensure UI config assembly can be tested without starting a worker."""
    output_path = tmp_path / "out.mp4"
    window = _DummyWindow(cs_enabled=True, burnin_enabled=True)
    window.keep_resolution_check = _DummyCheck(False)

    config = window._build_conversion_config_from_ui(output_path, "libx265")

    assert config.input_pattern == "render.%04d.exr"
    assert config.output_path == str(output_path)
    assert config.codec == "libx265"
    assert config.fps == pytest.approx(24.0)
    assert config.quality == 8
    assert config.prefetch_workers == 3
    assert config.start_frame == 1001
    assert config.end_frame == 1010
    assert config.width == 1920
    assert config.height == 1080
    assert config.explicit_input_color_space == "Linear"

    assert config.contact_sheet_mode is True
    assert config.contact_sheet_config is not None
    assert config.contact_sheet_config.columns == 4
    assert config.contact_sheet_config.layer_width == 1920
    assert config.contact_sheet_config.layer_height == 1080
    assert config.contact_sheet_config.show_labels is True

    assert config.burnin_config is not None
    templates = [element.text_template for element in config.burnin_config.elements]
    assert templates == ["Frame: {frame}", "FPS: {fps:.2f}"]


def test_resolve_encoder_for_conversion_falls_back(monkeypatch) -> None:
    """Ensure encoder fallback is handled without starting conversion."""
    warnings = []
    window = _DummyWindow(cs_enabled=False)

    monkeypatch.setattr(
        main_window_logic,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx265"})),
    )
    monkeypatch.setattr(
        main_window_logic.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    resolved_codec = window._resolve_encoder_for_conversion("libx264")

    assert resolved_codec == "libx265"
    assert window.codec_combo.currentIndex() == 1
    assert warnings


def test_resolve_encoder_for_conversion_rejects_unavailable_codec(monkeypatch) -> None:
    """Ensure confirmed encoder absence aborts before building config."""
    critical_messages = []
    window = _DummyWindow(cs_enabled=False)

    monkeypatch.setattr(
        main_window_logic,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"vp9"})),
    )
    monkeypatch.setattr(
        main_window_logic.QMessageBox,
        "critical",
        lambda *args, **kwargs: critical_messages.append(args),
    )

    resolved_codec = window._resolve_encoder_for_conversion("libx264")

    assert resolved_codec is None
    assert critical_messages


def test_resolve_encoder_for_conversion_allows_probe_failure(monkeypatch) -> None:
    """Ensure probe failures remain warning-only for conversion startup."""
    warnings = []
    window = _DummyWindow(cs_enabled=False)

    monkeypatch.setattr(
        main_window_logic,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset(), error="ffmpeg missing"),
    )
    monkeypatch.setattr(
        main_window_logic.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    resolved_codec = window._resolve_encoder_for_conversion("libx264")

    assert resolved_codec == "libx264"
    assert warnings
