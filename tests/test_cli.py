"""Tests for the RenderKit command line interface."""

import json
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


def test_batch_replace_uses_batch_convert_nested_output_names(monkeypatch, tmp_path: Path) -> None:
    """Verify batch-replace can consume nested names generated by batch-convert."""
    shot_dir = tmp_path / "shot_a"
    shot_dir.mkdir()
    frames = []
    for frame in [1, 2]:
        frame_path = shot_dir / f"render.{frame:04d}.exr"
        frame_path.write_bytes(b"frame")
        frames.append(frame_path)

    review_dir = tmp_path / "_review_mp4s"
    review_dir.mkdir()
    replacement_mp4 = review_dir / "shot_a_render.mp4"
    replacement_mp4.write_bytes(b"mp4")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-replace",
            str(tmp_path),
            "--dry-run",
            "--delete-source",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Would replace sequences: 1" in result.output
    assert all(path.exists() for path in frames)

    audit_path = tmp_path / "renderkit-batch-replace-audit.jsonl"
    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert record["replacement_mp4"] == str(replacement_mp4.resolve())
    assert record["deleted_count"] == 2


def test_batch_replace_uses_batch_convert_deduplicated_output_names(
    monkeypatch, tmp_path: Path
) -> None:
    """Verify colliding batch output names resolve in the same order as batch-convert."""
    frames = []
    for filename in ["render.001.exr", "render.0001.exr"]:
        frame_path = tmp_path / filename
        frame_path.write_bytes(b"frame")
        frames.append(frame_path)

    review_dir = tmp_path / "_review_mp4s"
    review_dir.mkdir()
    first_mp4 = review_dir / "render.mp4"
    second_mp4 = review_dir / "render_2.mp4"
    first_mp4.write_bytes(b"first")
    second_mp4.write_bytes(b"second")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-replace",
            str(tmp_path),
            "--dry-run",
            "--delete-source",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Would replace sequences: 2" in result.output
    assert all(path.exists() for path in frames)

    audit_path = tmp_path / "renderkit-batch-replace-audit.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["replacement_mp4"] for record in records] == [
        str(first_mp4.resolve()),
        str(second_mp4.resolve()),
    ]
