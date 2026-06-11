"""Tests for the RenderKit command line interface."""

from pathlib import Path

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
