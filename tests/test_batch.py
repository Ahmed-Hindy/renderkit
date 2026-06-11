"""Tests for batch sequence discovery and conversion orchestration."""

import csv
import json
from pathlib import Path

from click.testing import CliRunner

from renderkit.cli import batch as cli_batch
from renderkit.cli import main as cli_main
from renderkit.core.batch import build_safe_output_path, discover_frame_sequences


def test_discover_frame_sequences_groups_nested_sparse_and_single_frames(
    tmp_path: Path,
) -> None:
    """Batch discovery groups by directory, prefix, suffix, and padding."""
    for frame in [1001, 1003, 1004]:
        (tmp_path / "shot_a").mkdir(exist_ok=True)
        (tmp_path / "shot_a" / f"beauty.{frame:04d}.exr").touch()

    single_dir = tmp_path / "shot_b" / "plates"
    single_dir.mkdir(parents=True)
    (single_dir / "plate.007.exr").touch()
    (single_dir / "notes.txt").touch()

    sequences = discover_frame_sequences(tmp_path, "exr")

    assert [sequence.pattern for sequence in sequences] == [
        "beauty.%04d.exr",
        "plate.%03d.exr",
    ]
    assert sequences[0].frame_numbers == [1001, 1003, 1004]
    assert sequences[0].frame_range == "1001-1004"
    assert sequences[1].frame_numbers == [7]
    assert sequences[1].frame_range == "7-7"


def test_build_safe_output_path_uses_relative_directory_for_collisions(tmp_path: Path) -> None:
    """Output names include relative folders so repeated sequence stems do not collide."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "render.0001.exr").touch()
    (tmp_path / "b" / "render.0001.exr").touch()

    sequences = discover_frame_sequences(tmp_path, "exr")
    output_dir = tmp_path / "_review_mp4s"
    output_paths = [
        build_safe_output_path(tmp_path, output_dir, sequence) for sequence in sequences
    ]

    assert output_paths == [
        output_dir / "a_render.mp4",
        output_dir / "b_render.mp4",
    ]


def test_discover_frame_sequences_matches_extension_case_insensitively(tmp_path: Path) -> None:
    """Lowercase --ext values still discover uppercase frame extensions."""
    (tmp_path / "render.0001.EXR").touch()

    sequences = discover_frame_sequences(tmp_path, "exr")

    assert len(sequences) == 1
    assert sequences[0].pattern == "render.%04d.EXR"


def test_batch_convert_continues_after_failure_and_writes_manifests(
    monkeypatch, tmp_path: Path
) -> None:
    """A failed sequence is recorded without stopping later conversions."""
    good_dir = tmp_path / "good"
    bad_dir = tmp_path / "bad"
    later_dir = tmp_path / "later"
    good_dir.mkdir()
    bad_dir.mkdir()
    later_dir.mkdir()

    for frame in [1, 2]:
        (good_dir / f"beauty.{frame:04d}.exr").touch()
    (bad_dir / "broken.0001.exr").touch()
    (later_dir / "plate.007.exr").touch()

    calls: list[str] = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            calls.append(Path(config.input_pattern).name)
            if "broken" in config.input_pattern:
                raise RuntimeError("simulated conversion failure")
            Path(config.output_path).write_bytes(b"mp4")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_batch, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-convert",
            str(tmp_path),
            "--ext",
            "exr",
            "--out",
            "_review_mp4s",
            "--fps",
            "24",
            "--no-progress",
        ],
    )

    assert result.exit_code == 1, result.output
    assert calls == ["broken.%04d.exr", "beauty.%04d.exr", "plate.%03d.exr"]
    assert "Batch complete: 2 succeeded, 1 failed, 0 skipped" in result.output

    csv_path = tmp_path / "_review_mp4s" / "renderkit_batch_manifest.csv"
    jsonl_path = tmp_path / "_review_mp4s" / "renderkit_batch_results.jsonl"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    jsonl_rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]

    assert [row["status"] for row in rows] == ["failed", "success", "success"]
    assert [row["status"] for row in jsonl_rows] == ["failed", "success", "success"]
    assert rows[0]["frame_count"] == "1"
    assert rows[1]["frame_range"] == "1-2"
    assert rows[2]["size_bytes"] == "3"


def test_batch_convert_skips_existing_outputs_without_overwrite(
    monkeypatch, tmp_path: Path
) -> None:
    """Existing outputs are manifest-recorded as skipped unless --overwrite is set."""
    shot_dir = tmp_path / "shot"
    shot_dir.mkdir()
    (shot_dir / "render.0001.exr").touch()

    output_dir = tmp_path / "_review_mp4s"
    output_dir.mkdir()
    existing_output = output_dir / "shot_render.mp4"
    existing_output.write_bytes(b"existing")

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            raise AssertionError("conversion should not run for skipped output")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_batch, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-convert",
            str(tmp_path),
            "--out",
            "_review_mp4s",
            "--fps",
            "24",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "0 succeeded, 0 failed, 1 skipped" in result.output

    csv_path = output_dir / "renderkit_batch_manifest.csv"
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["status"] == "skipped"
    assert rows[0]["size_bytes"] == str(len(b"existing"))


def test_batch_convert_deduplicates_colliding_output_names(monkeypatch, tmp_path: Path) -> None:
    """Sequences with the same output stem get distinct MP4 paths."""
    (tmp_path / "render.001.exr").touch()
    (tmp_path / "render.0001.exr").touch()
    output_paths: list[Path] = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            output_path = Path(config.output_path)
            output_paths.append(output_path)
            output_path.write_bytes(b"mp4")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_batch, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-convert",
            str(tmp_path),
            "--out",
            "_review_mp4s",
            "--fps",
            "24",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_paths == [
        tmp_path / "_review_mp4s" / "render.mp4",
        tmp_path / "_review_mp4s" / "render_2.mp4",
    ]
