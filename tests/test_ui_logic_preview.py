"""Tests for preview load wiring in main window logic."""

from pathlib import Path

from renderkit.processing.color_space import ColorSpacePreset
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
    def __init__(self, text: str) -> None:
        self._text = text

    def currentText(self) -> str:
        return self._text


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
