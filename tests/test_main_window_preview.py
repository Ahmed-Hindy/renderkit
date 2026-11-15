"""Tests for main-window preview request assembly."""

from pathlib import Path

import pytest

from renderkit.core.config import ConversionConfig, SlateConfig, WatermarkConfig
from renderkit.core.presets import load_preset, save_preset
from renderkit.exceptions import ConfigurationError
from renderkit.processing.color_space import ColorSpacePreset, get_bundled_ocio_config_path
from renderkit.ui.main_window_ocio import (
    apply_preset_data_to_ui,
    build_slate_config_from_ui,
    build_watermark_config_from_ui,
    container_extension_for_codec,
)
from renderkit.ui.main_window_preview import (
    build_burnin_config,
    build_preview_request,
    load_preview_for_frame,
)


class _DummyValue:
    def __init__(self, value) -> None:
        self._value = value

    def value(self):
        return self._value


class _DummyCheck:
    def __init__(self, checked: bool) -> None:
        self._checked = checked

    def is_checked(self) -> bool:
        return self._checked

    def __getattr__(self, name: str):
        if name == "isChecked":
            return self.is_checked
        raise AttributeError(name)


class _DummyCombo:
    def __init__(self, text: str) -> None:
        self._text = text

    def current_text(self) -> str:
        return self._text

    def __getattr__(self, name: str):
        if name == "currentText":
            return self.current_text
        raise AttributeError(name)


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


class _DummyLineEdit:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _DummyPreviewTarget:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def load_preview(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))


def test_build_preview_request_and_load_forward_ocio_and_grade(tmp_path: Path) -> None:
    """PreviewRequest and load_preview_for_frame should forward OCIO and grade settings."""
    sample_path = tmp_path / "render.0001.exr"
    ui = _DummyWindow(contact_sheet=False, burnin=False)
    ui.ocio_config_edit = _DummyLineEdit("/path/to/config.ocio")
    ui.ocio_display_combo = _DummyCombo("ACES")
    ui.ocio_view_combo = _DummyCombo("sRGB")
    ui.exposure_spin = _DummyValue(1.5)
    ui.gamma_spin = _DummyValue(1.25)
    ui.preview_widget = _DummyPreviewTarget()

    request = load_preview_for_frame(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space="ACEScg",
        scrubbing=False,
    )

    assert request.ocio_config_path == "/path/to/config.ocio"
    assert request.ocio_display == "ACES"
    assert request.ocio_view == "sRGB"
    assert request.exposure == pytest.approx(1.5)
    assert request.gamma == pytest.approx(1.25)

    _, kwargs = ui.preview_widget.calls[-1]
    assert kwargs["ocio_config_path"] == "/path/to/config.ocio"
    assert kwargs["ocio_display"] == "ACES"
    assert kwargs["ocio_view"] == "sRGB"
    assert kwargs["exposure"] == pytest.approx(1.5)
    assert kwargs["gamma"] == pytest.approx(1.25)


def test_build_preview_request_treats_auto_ocio_labels_as_none(tmp_path: Path) -> None:
    """'(Auto)' OCIO display/view sentinel values should resolve to None."""
    sample_path = tmp_path / "render.0001.exr"
    ui = _DummyWindow(contact_sheet=False, burnin=False)
    ui.ocio_config_edit = _DummyLineEdit("   ")
    ui.ocio_display_combo = _DummyCombo("(Auto)")
    ui.ocio_view_combo = _DummyCombo("(Auto)")

    request = build_preview_request(
        ui,
        sample_path,
        preset=ColorSpacePreset.OCIO_CONVERSION,
        input_space="Linear",
        scrubbing=False,
    )

    assert request.ocio_config_path is None
    assert request.ocio_display is None
    assert request.ocio_view is None


def test_codec_change_switches_auto_output_extension_and_respects_user_edits(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    """Auto-generated output paths should switch .mp4/.mov with codec unless user-edited."""
    from renderkit.ui.main_window import ModernMainWindow

    for i in range(1, 3):
        (tmp_path / f"shot.{i:04d}.exr").touch()

    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    libx264_idx = next(idx for idx, cid in window._codec_map.items() if cid == "libx264")
    prores_idx = next(idx for idx, cid in window._codec_map.items() if cid == "prores_hq")
    window.codec_combo.setCurrentIndex(libx264_idx)

    pattern = str(tmp_path / "shot.%04d.exr")
    window.input_pattern_combo.lineEdit().setText(pattern)
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    expected_mp4 = str(tmp_path / "shot.mp4")
    qtbot.waitUntil(lambda: window.output_path_edit.text() == expected_mp4, timeout=2000)

    # Switching to ProRes should auto-switch extension to .mov
    window.codec_combo.setCurrentIndex(prores_idx)
    assert window.output_path_edit.text() == str(tmp_path / "shot.mov")

    # Switching back to H.264 should auto-switch extension back to .mp4
    window.codec_combo.setCurrentIndex(libx264_idx)
    assert window.output_path_edit.text() == expected_mp4

    # User-edited output path must not be overwritten when codec changes
    custom_path = str(tmp_path / "custom_dailies.mp4")
    window.output_path_edit.setText(custom_path)
    window.codec_combo.setCurrentIndex(prores_idx)
    assert window.output_path_edit.text() == custom_path


def test_run_ui_prepopulates_startup_options(qtbot, qapp, tmp_path: Path, monkeypatch) -> None:
    """run_ui should accept --open, --layer, --preset, and --ocio startup arguments."""
    from renderkit.ui import main_window

    for i in range(1, 3):
        (tmp_path / f"comp.{i:04d}.exr").touch()

    preset_file = tmp_path / "dailies.json"
    preset_cfg = ConversionConfig(
        input_pattern="x.%04d.exr",
        output_path="x.mov",
        codec="prores_422",
        exposure=1.5,
        gamma=1.15,
    )
    save_preset(preset_cfg, preset_file)
    bundled_ocio = str(get_bundled_ocio_config_path())

    class _DummySplash:
        def show(self) -> None:
            pass

        def finish(self, _win) -> None:
            pass

        def close(self) -> None:
            pass

    created_windows = []
    original_init = main_window.ModernMainWindow.__init__

    def spy_init(self) -> None:
        original_init(self)
        created_windows.append(self)

    monkeypatch.setattr(main_window.ModernMainWindow, "__init__", spy_init)
    monkeypatch.setattr(main_window, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(main_window, "create_splash_screen", lambda _v: _DummySplash())
    monkeypatch.setattr(main_window, "wait_for_minimum_splash_duration", lambda **_kw: None)
    monkeypatch.setattr(main_window.FileInfoWorker, "start", lambda self: None)
    monkeypatch.setattr(main_window.ModernMainWindow, "show", lambda self: None)
    monkeypatch.setattr(qapp, "exec", lambda: 0)

    exit_code = main_window.run_ui(
        open_path=str(tmp_path / "comp.0001.exr"),
        layer="diffuse",
        preset=str(preset_file),
        ocio_path=bundled_ocio,
    )

    assert exit_code == 0
    assert created_windows
    win = created_windows[0]
    qtbot.addWidget(win)
    assert "comp.%04d.exr" in win.input_pattern_combo.currentText()
    assert win._pending_layer == "diffuse"
    assert win.ocio_config_edit.text() == bundled_ocio
    assert win.exposure_spin.value() == pytest.approx(1.5)
    assert win.gamma_spin.value() == pytest.approx(1.15)
    assert win._selected_codec_id() == "prores_422"


@pytest.mark.parametrize(
    ("codec_id", "expected_ext"),
    [
        ("libx264", ".mp4"),
        ("libx265", ".mp4"),
        ("hevc_10bit", ".mp4"),
        ("libaom-av1", ".mp4"),
        ("mpeg4", ".mp4"),
        ("prores_422", ".mov"),
        ("prores_hq", ".mov"),
        ("prores_4444", ".mov"),
        ("dnxhr_hq", ".mov"),
        ("dnxhr_hqx", ".mov"),
        ("dnxhd", ".mov"),
    ],
)
def test_container_extension_for_codec_uses_codec_profiles(
    codec_id: str, expected_ext: str
) -> None:
    """Codec container extensions should match video_encoder profiles and dnxhd alias."""
    assert container_extension_for_codec(codec_id) == expected_ext


def test_build_slate_and_watermark_configs_from_ui(qtbot) -> None:
    """Slate and watermark UI builders should respect enable flags and strict mode."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    assert window.slate_enable_check.isChecked() is False
    assert window.watermark_enable_check.isChecked() is False
    assert build_slate_config_from_ui(window) is None
    assert build_watermark_config_from_ui(window) is None

    window.slate_enable_check.setChecked(True)
    window.slate_title_edit.setText("  Comp Review  ")
    window.slate_show_edit.setText("SHOW_A")
    window.slate_shot_edit.setText("SH010")
    window.slate_artist_edit.setText("Alex")
    window.slate_notes_edit.setText("Final grade check")

    slate_cfg = build_slate_config_from_ui(window)
    assert slate_cfg == SlateConfig(
        enabled=True,
        title="Comp Review",
        show="SHOW_A",
        shot="SH010",
        artist="Alex",
        notes="Final grade check",
    )

    window.watermark_enable_check.setChecked(True)
    window.watermark_text_edit.setText("   ")
    assert build_watermark_config_from_ui(window) is None
    with pytest.raises(ConfigurationError, match="Watermark text must not be empty"):
        build_watermark_config_from_ui(window, strict=True)

    window.watermark_text_edit.setText("INTERNAL REVIEW")
    window.watermark_opacity_spin.setValue(40)
    window.watermark_tiled_check.setChecked(True)

    watermark_cfg = build_watermark_config_from_ui(window, strict=True)
    assert watermark_cfg == WatermarkConfig(
        text="INTERNAL REVIEW",
        opacity=40,
        tiled=True,
    )


def test_slate_and_watermark_preset_round_trip_in_ui(qtbot, tmp_path: Path) -> None:
    """Presets should round-trip slate_config and watermark_config through UI widgets."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    preset_file = tmp_path / "slate_watermark_preset.json"
    slate_cfg = SlateConfig(
        enabled=True,
        title="Lighting Dailies",
        show="PROJ",
        shot="SQ02_SH04",
        artist="Sam",
        notes="Check rim light",
    )
    watermark_cfg = WatermarkConfig(text="CONFIDENTIAL", opacity=35, tiled=True)
    cfg = ConversionConfig(
        input_pattern="render.%04d.exr",
        output_path="out.mp4",
        slate_config=slate_cfg,
        watermark_config=watermark_cfg,
    )
    save_preset(cfg, preset_file)

    loaded = load_preset(preset_file)
    apply_preset_data_to_ui(window, loaded)

    assert window.slate_enable_check.isChecked() is True
    assert window.slate_title_edit.text() == "Lighting Dailies"
    assert window.slate_show_edit.text() == "PROJ"
    assert window.slate_shot_edit.text() == "SQ02_SH04"
    assert window.slate_artist_edit.text() == "Sam"
    assert window.slate_notes_edit.text() == "Check rim light"

    assert window.watermark_enable_check.isChecked() is True
    assert window.watermark_text_edit.text() == "CONFIDENTIAL"
    assert window.watermark_opacity_spin.value() == 35
    assert window.watermark_tiled_check.isChecked() is True

    built = window._build_conversion_config_from_ui(tmp_path / "out.mp4", "libx264")
    assert built.slate_config == slate_cfg
    assert built.watermark_config == watermark_cfg

    # Applying None should uncheck and clear controls
    apply_preset_data_to_ui(window, {"slate_config": None, "watermark_config": None})
    assert window.slate_enable_check.isChecked() is False
    assert window.slate_title_edit.text() == ""
    assert window.slate_notes_edit.text() == ""
    assert window.watermark_enable_check.isChecked() is False
    assert window.watermark_text_edit.text() == ""
    assert window.watermark_opacity_spin.value() == 25
    assert window.watermark_tiled_check.isChecked() is False
