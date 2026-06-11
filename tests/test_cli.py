"""Tests for the RenderKit command line interface."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from renderkit.cli import main as cli_main
from renderkit.core.sequence import SequenceDetector


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
