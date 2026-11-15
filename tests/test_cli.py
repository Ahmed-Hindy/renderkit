"""Tests for the RenderKit command line interface."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from renderkit.cli import batch as cli_batch
from renderkit.cli import main as cli_main
from renderkit.core.config import SlateConfig, WatermarkConfig
from renderkit.core.presets import load_preset
from renderkit.core.sequence import SequenceDetector
from renderkit.processing.color_space import ColorSpacePreset


def test_help_lists_ui_command(monkeypatch) -> None:
    """Verify the public launcher appears in CLI help."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(cli_main.main, ["--help"])

    assert result.exit_code == 0
    assert "ui" in result.output
    assert "batch-replace" in result.output
    assert "replace-sequence-with-mp4" in result.output
    assert "Launch the RenderKit desktop UI." in result.output
    assert "gui" not in result.output


def test_contact_sheet_help_describes_layer_labels(monkeypatch) -> None:
    """Contact sheet labels identify EXR layers, not source filenames."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(cli_main.main, ["contact-sheet", "--help"])

    assert result.exit_code == 0
    assert "Disable layer labels below thumbnails" in result.output
    assert "filename labels" not in result.output


def test_ui_command_launches_gui(monkeypatch) -> None:
    """Verify the ui command dispatches to the Qt launcher."""
    launched = False

    def fake_launch_ui() -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "_launch_ui", fake_launch_ui)

    result = CliRunner().invoke(cli_main.main, ["ui"])

    assert result.exit_code == 0
    assert launched


def test_convert_exr_sequence_accepts_three_digit_printf_pattern(
    monkeypatch, tmp_path: Path
) -> None:
    """Verify CLI conversion can resolve a %03d input pattern."""
    for frame in range(1, 4):
        (tmp_path / f"shot.{frame:03d}.exr").touch()

    output_path = tmp_path / "output.mp4"
    resolved_paths: list[Path] = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            sequence = SequenceDetector.detect_sequence(config.input_pattern)
            resolved_paths.extend(sequence.get_file_path(frame) for frame in sequence.frame_numbers)
            output_path.touch()

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            str(tmp_path / "shot.%03d.exr"),
            str(output_path),
            "--fps",
            "24",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Successfully converted" in result.output
    assert resolved_paths == [
        tmp_path / "shot.001.exr",
        tmp_path / "shot.002.exr",
        tmp_path / "shot.003.exr",
    ]
    assert all(path.exists() for path in resolved_paths)


def test_gui_alias_launches_gui(monkeypatch) -> None:
    """Verify the gui alias dispatches to the Qt launcher."""
    launched = False

    def fake_launch_ui() -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "_launch_ui", fake_launch_ui)

    result = CliRunner().invoke(cli_main.main, ["gui"])

    assert result.exit_code == 0
    assert launched


def test_convert_no_progress_disables_progress(monkeypatch, tmp_path) -> None:
    """Verify --no-progress requests plain automation-friendly output."""
    calls = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            calls.append((config, show_progress))

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "output.mp4"),
            "--fps",
            "24",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    _, show_progress = calls.pop()
    assert show_progress is False
    assert "Successfully converted" in result.output


def test_convert_defaults_to_auto_progress_detection(monkeypatch, tmp_path) -> None:
    """Verify default CLI behavior lets the converter decide from the terminal."""
    calls = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            calls.append((config, show_progress))

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "output.mp4"),
            "--fps",
            "24",
        ],
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    _, show_progress = calls.pop()
    assert show_progress is None


@pytest.mark.parametrize(
    ("option", "value", "missing_option"),
    [
        ("--width", "1920", "--height"),
        ("--height", "1080", "--width"),
    ],
)
def test_convert_rejects_one_sided_resolution(
    monkeypatch, tmp_path: Path, option: str, value: str, missing_option: str
) -> None:
    """Lone resize dimensions should fail instead of being silently ignored."""
    calls = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            calls.append(config)

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "output.mp4"),
            "--fps",
            "24",
            option,
            value,
        ],
    )

    assert result.exit_code == 2
    assert "--width and --height must be used together" in result.output
    assert missing_option in result.output
    assert calls == []


def test_convert_resolution_validation_runs_before_output_exists_check(
    monkeypatch, tmp_path: Path
) -> None:
    """Invalid resize options should report usage before runtime output checks."""
    output_path = tmp_path / "output.mp4"
    output_path.touch()

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(output_path),
            "--fps",
            "24",
            "--width",
            "1920",
        ],
    )

    assert result.exit_code == 2
    assert "--width and --height must be used together" in result.output
    assert "Use --overwrite" not in result.output


@pytest.mark.parametrize(
    ("option", "value", "expected_range"),
    [
        ("--start-frame", "1001", (1001, None)),
        ("--end-frame", "1008", (None, 1008)),
    ],
)
def test_convert_preserves_one_sided_frame_range(
    monkeypatch,
    tmp_path: Path,
    option: str,
    value: str,
    expected_range: tuple[int | None, int | None],
) -> None:
    """A single range bound should stay open-ended for sequence filtering."""
    captured_ranges = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            captured_ranges.append((config.start_frame, config.end_frame))

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "output.mp4"),
            "--fps",
            "24",
            option,
            value,
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured_ranges == [expected_range]


def test_contact_sheet_command_uses_still_writer(monkeypatch, tmp_path: Path) -> None:
    """Verify the still contact sheet command wires CLI options into the writer."""
    calls = []
    output_path = tmp_path / "contact_sheet.jpg"

    def fake_write_sequence_contact_sheet(
        input_pattern,
        output_path,
        config,
        layer,
        start_frame,
        end_frame,
    ) -> None:
        calls.append((input_pattern, output_path, config, layer, start_frame, end_frame))
        output_path.touch()

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(
        cli_main, "_write_sequence_contact_sheet", fake_write_sequence_contact_sheet
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "contact-sheet",
            "render.%04d.exr",
            str(output_path),
            "--columns",
            "3",
            "--thumb-width",
            "256",
            "--padding",
            "8",
            "--no-labels",
            "--font-size",
            "12",
            "--layer",
            "diffuse",
            "--start-frame",
            "1001",
            "--end-frame",
            "1008",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    input_pattern, called_output_path, config, layer, start_frame, end_frame = calls[0]
    assert input_pattern == "render.%04d.exr"
    assert called_output_path == output_path
    assert config.columns == 3
    assert config.thumbnail_width == 256
    assert config.padding == 8
    assert config.show_labels is False
    assert config.font_size == 12
    assert layer == "diffuse"
    assert start_frame == 1001
    assert end_frame == 1008
    assert "Successfully created contact sheet" in result.output


def test_contact_sheet_invalid_input_returns_clean_cli_error(monkeypatch, tmp_path: Path) -> None:
    """Invalid contact sheet inputs should not expose implementation tracebacks."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "contact-sheet",
            str(tmp_path / "missing.%04d.exr"),
            str(tmp_path / "contact_sheet.jpg"),
            "--overwrite",
        ],
    )

    assert result.exit_code == 1
    assert "Error: Could not detect frame sequence." in result.output
    assert "Traceback" not in result.output
    assert "AttributeError" not in result.output


def test_convert_ocio_grade_slate_and_save_preset_flags(monkeypatch, tmp_path: Path) -> None:
    """Verify new OCIO, grade, slate, and --save-preset CLI flags wire into ConversionConfig."""
    captured = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            captured.append(config)

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    preset_file = tmp_path / "shot_preset.json"
    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "out.mp4"),
            "--fps",
            "24",
            "--color-space",
            "ocio_conversion",
            "--ocio",
            "/studio/config.ocio",
            "--input-space",
            "ACEScg",
            "--display",
            "sRGB",
            "--view",
            "ACES 1.0 - SDR Video",
            "--exposure",
            "1.5",
            "--gamma",
            "2.2",
            "--slate",
            "--slate-title",
            "Daily Review",
            "--slate-show",
            "PROJ",
            "--slate-shot",
            "sh020",
            "--slate-artist",
            "Sam",
            "--slate-notes",
            "Approved",
            "--save-preset",
            str(preset_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    config = captured[0]
    assert config.color_space_preset == ColorSpacePreset.OCIO_CONVERSION
    assert config.ocio_config_path == "/studio/config.ocio"
    assert config.explicit_input_color_space == "ACEScg"
    assert config.ocio_display == "sRGB"
    assert config.ocio_view == "ACES 1.0 - SDR Video"
    assert config.exposure == 1.5
    assert config.gamma == 2.2
    assert config.slate_config == SlateConfig(
        enabled=True,
        title="Daily Review",
        show="PROJ",
        shot="sh020",
        artist="Sam",
        notes="Approved",
    )
    assert preset_file.exists()
    loaded = load_preset(preset_file)
    assert loaded["exposure"] == 1.5
    assert loaded["gamma"] == 2.2
    assert loaded["slate_config"] == config.slate_config


def test_convert_with_preset_loads_defaults_and_allows_cli_override(
    monkeypatch, tmp_path: Path
) -> None:
    """Verify --preset seeds conversion options while explicit CLI flags override them."""
    captured = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            captured.append(config)

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    preset_file = tmp_path / "base_preset.json"
    save_res = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "first.mp4"),
            "--fps",
            "24",
            "--codec",
            "prores_hq",
            "--quality",
            "7",
            "--exposure",
            "0.75",
            "--gamma",
            "1.8",
            "--slate",
            "--slate-title",
            "Preset Title",
            "--save-preset",
            str(preset_file),
        ],
    )
    assert save_res.exit_code == 0, save_res.output
    captured.clear()

    load_res = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "shot2.%04d.exr",
            str(tmp_path / "second.mp4"),
            "--preset",
            str(preset_file),
            "--quality",
            "9",
            "--slate-title",
            "Override Title",
        ],
    )

    assert load_res.exit_code == 0, load_res.output
    assert len(captured) == 1
    config = captured[0]
    assert config.fps == 24.0
    assert config.codec == "prores_hq"
    assert config.quality == 9
    assert config.exposure == 0.75
    assert config.gamma == 1.8
    assert config.slate_config is not None
    assert config.slate_config.enabled is True
    assert config.slate_config.title == "Override Title"


def test_convert_rejects_non_positive_gamma(monkeypatch, tmp_path: Path) -> None:
    """Verify --gamma <= 0 reports a clean CLI error."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "out.mp4"),
            "--fps",
            "24",
            "--gamma",
            "0",
        ],
    )

    assert result.exit_code == 1
    assert "Gamma must be greater than 0" in result.output


def test_batch_convert_ocio_and_grade_flags(monkeypatch, tmp_path: Path) -> None:
    """Verify batch-convert accepts OCIO and grade options and wires them into configs."""
    shot_dir = tmp_path / "shot"
    shot_dir.mkdir()
    (shot_dir / "render.0001.exr").touch()

    captured = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            captured.append(config)
            Path(config.output_path).write_bytes(b"mp4")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_batch, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-convert",
            str(tmp_path),
            "--fps",
            "24",
            "--color-space",
            "ocio_conversion",
            "--ocio",
            "/studio/config.ocio",
            "--input-space",
            "ACEScg",
            "--display",
            "sRGB",
            "--view",
            "ACES 1.0 - SDR Video",
            "--exposure",
            "-0.5",
            "--gamma",
            "2.0",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    config = captured[0]
    assert config.color_space_preset == ColorSpacePreset.OCIO_CONVERSION
    assert config.ocio_config_path == "/studio/config.ocio"
    assert config.explicit_input_color_space == "ACEScg"
    assert config.ocio_display == "sRGB"
    assert config.ocio_view == "ACES 1.0 - SDR Video"
    assert config.exposure == -0.5
    assert config.gamma == 2.0


def test_help_lists_video_ingest_and_transcode_commands(monkeypatch) -> None:
    """Verify video-to-exr, transcode, and proxy appear in CLI help."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(cli_main.main, ["--help"])

    assert result.exit_code == 0
    assert "video-to-exr" in result.output
    assert "transcode" in result.output
    assert "proxy" in result.output


def test_convert_watermark_and_preset_search_path(monkeypatch, tmp_path: Path) -> None:
    """Verify --watermark flags and RENDERKIT_PRESET_PATH resolution work in convert-exr-sequence."""
    captured = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            captured.append(config)

    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    preset_file = preset_dir / "studio_daily.json"
    preset_file.write_text(
        '{"schema_version": 1, "fps": 24.0, "codec": "prores_hq", "quality": 9}\n',
        encoding="utf-8",
    )

    monkeypatch.setenv("RENDERKIT_PRESET_PATH", str(preset_dir))
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "convert-exr-sequence",
            "render.%04d.exr",
            str(tmp_path / "out.mov"),
            "--preset",
            "studio_daily",
            "--watermark",
            "CONFIDENTIAL",
            "--watermark-opacity",
            "40",
            "--watermark-tiled",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    config = captured[0]
    assert config.codec == "prores_hq"
    assert config.watermark_config == WatermarkConfig(
        text="CONFIDENTIAL",
        opacity=40,
        tiled=True,
    )


def test_ui_command_forwards_open_layer_preset_and_ocio(monkeypatch, tmp_path: Path) -> None:
    """Verify ui --open/--layer/--preset/--ocio resolve preset and forward kwargs."""
    captured: list[dict[str, object]] = []
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    preset_file = preset_dir / "review.json"
    preset_file.write_text('{"schema_version": 1}\n', encoding="utf-8")

    def fake_launch_ui(
        open_path=None,
        layer=None,
        preset=None,
        ocio_path=None,
    ) -> int:
        captured.append(
            {
                "open_path": open_path,
                "layer": layer,
                "preset": preset,
                "ocio_path": ocio_path,
            }
        )
        return 0

    monkeypatch.setenv("RENDERKIT_PRESET_PATH", str(preset_dir))
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "_launch_ui", fake_launch_ui)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "ui",
            "--open",
            str(tmp_path / "shot.%04d.exr"),
            "--layer",
            "diffuse",
            "--preset",
            "review",
            "--ocio",
            "/studio/config.ocio",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == [
        {
            "open_path": str(tmp_path / "shot.%04d.exr"),
            "layer": "diffuse",
            "preset": str(preset_file),
            "ocio_path": "/studio/config.ocio",
        }
    ]


def test_launch_ui_forwards_to_run_ui(monkeypatch) -> None:
    """Verify _launch_ui calls renderkit.ui.main_window.run_ui with keyword args."""
    import renderkit.ui.main_window as main_window

    calls: list[dict[str, object]] = []

    def fake_run_ui(
        open_path=None,
        layer=None,
        preset=None,
        ocio_path=None,
    ) -> int:
        calls.append(
            {
                "open_path": open_path,
                "layer": layer,
                "preset": preset,
                "ocio_path": ocio_path,
            }
        )
        return 0

    monkeypatch.setattr(main_window, "run_ui", fake_run_ui)

    assert cli_main._launch_ui() == 0
    assert (
        cli_main._launch_ui(
            open_path="a.%04d.exr", layer="beauty", preset="p.json", ocio_path="o.ocio"
        )
        == 0
    )
    assert calls == [
        {"open_path": None, "layer": None, "preset": None, "ocio_path": None},
        {
            "open_path": "a.%04d.exr",
            "layer": "beauty",
            "preset": "p.json",
            "ocio_path": "o.ocio",
        },
    ]


def test_video_to_exr_command_wires_config(monkeypatch, tmp_path: Path) -> None:
    """Verify video-to-exr CLI wires all options into VideoToExrConfig and converter."""
    captured = []

    class FakeConverter:
        def __init__(self, config) -> None:
            captured.append(config)

        def convert(self) -> list[Path]:
            return [tmp_path / "plate.1001.exr", tmp_path / "plate.1002.exr"]

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "VideoToExrConverter", FakeConverter)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "video-to-exr",
            str(tmp_path / "plate.mov"),
            str(tmp_path / "plate.%04d.exr"),
            "--start-frame",
            "101",
            "--source-start",
            "2",
            "--source-end",
            "5",
            "--compression",
            "zip",
            "--float32",
            "--input-space",
            "Output - sRGB",
            "--output-space",
            "ACES - ACEScg",
            "--ocio",
            "/studio/config.ocio",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote 2 EXR frames" in result.output
    assert len(captured) == 1
    cfg = captured[0]
    assert cfg.input_path == tmp_path / "plate.mov"
    assert cfg.output_pattern == str(tmp_path / "plate.%04d.exr")
    assert cfg.start_frame == 101
    assert cfg.source_start_frame == 2
    assert cfg.source_end_frame == 5
    assert cfg.compression == "zip"
    assert cfg.half_float is False
    assert cfg.input_space == "Output - sRGB"
    assert cfg.output_space == "ACES - ACEScg"
    assert cfg.ocio_config_path == "/studio/config.ocio"


def test_transcode_command_wires_config(monkeypatch, tmp_path: Path) -> None:
    """Verify transcode CLI wires scaling, OCIO, grade, and watermark options."""
    captured = []

    def fake_transcode_video(config) -> Path:
        captured.append(config)
        return config.output_path

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "transcode_video", fake_transcode_video)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "transcode",
            str(tmp_path / "in.mov"),
            str(tmp_path / "out.mov"),
            "--codec",
            "prores_422",
            "--fps",
            "23.976",
            "--quality",
            "8",
            "--width",
            "1280",
            "--ocio",
            "/studio/config.ocio",
            "--input-space",
            "ACES - ACEScg",
            "--output-space",
            "Output - sRGB",
            "--display",
            "sRGB",
            "--view",
            "Film",
            "--exposure",
            "0.5",
            "--gamma",
            "1.2",
            "--watermark",
            "CLIENT REVIEW",
            "--watermark-opacity",
            "35",
            "--watermark-tiled",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured) == 1
    cfg = captured[0]
    assert cfg.input_path == tmp_path / "in.mov"
    assert cfg.output_path == tmp_path / "out.mov"
    assert cfg.codec == "prores_422"
    assert cfg.fps == pytest.approx(23.976)
    assert cfg.quality == 8
    assert cfg.scale_width == 1280
    assert cfg.scale_height is None
    assert cfg.ocio_config_path == "/studio/config.ocio"
    assert cfg.input_space == "ACES - ACEScg"
    assert cfg.output_space == "Output - sRGB"
    assert cfg.ocio_display == "sRGB"
    assert cfg.ocio_view == "Film"
    assert cfg.exposure == 0.5
    assert cfg.gamma == 1.2
    assert cfg.watermark_config == WatermarkConfig(
        text="CLIENT REVIEW",
        opacity=35,
        tiled=True,
    )


def test_proxy_command_wires_arguments(monkeypatch, tmp_path: Path) -> None:
    """Verify proxy CLI delegates to generate_video_proxy with expected options."""
    captured: list[tuple[Path, Path | None, float, str, int]] = []

    def fake_generate_video_proxy(
        input_video: Path,
        output: Path | None = None,
        *,
        scale_factor: float = 0.5,
        codec: str = "libx264",
        quality: int = 10,
    ) -> Path:
        captured.append((input_video, output, scale_factor, codec, quality))
        return output or (input_video.parent / "Proxy" / f"{input_video.stem}_proxy.mp4")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "generate_video_proxy", fake_generate_video_proxy)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "proxy",
            str(tmp_path / "master.mov"),
            "--output",
            str(tmp_path / "custom_proxy.mp4"),
            "--scale",
            "0.25",
            "--codec",
            "libx265",
            "--quality",
            "6",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == [
        (
            tmp_path / "master.mov",
            tmp_path / "custom_proxy.mp4",
            0.25,
            "libx265",
            6,
        )
    ]
