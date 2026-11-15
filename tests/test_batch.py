"""Tests for batch sequence discovery and conversion orchestration."""

import csv
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from renderkit.cli import batch as cli_batch
from renderkit.cli import main as cli_main
from renderkit.core.batch import (
    BatchSequence,
    build_safe_output_path,
    discover_frame_sequences,
    is_sequence_settled,
    watch_and_convert_sequences,
)
from renderkit.core.config import ConversionConfig, ConversionConfigBuilder
from renderkit.core.presets import save_preset


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


def test_batch_convert_rejects_one_sided_resolution(monkeypatch, tmp_path: Path) -> None:
    """Batch conversion should use the same paired resize validation."""
    (tmp_path / "render.0001.exr").touch()
    calls = []

    class FakeRenderKit:
        def convert_with_config(self, config, show_progress=None) -> None:
            calls.append(config)

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
            "--width",
            "1920",
        ],
    )

    assert result.exit_code == 2
    assert "--width and --height must be used together" in result.output
    assert calls == []
    assert not (tmp_path / "_review_mp4s").exists()


def test_batch_replace_uses_nested_batch_convert_output_names(monkeypatch, tmp_path: Path) -> None:
    """Batch replacement should consume nested review MP4 names from batch conversion."""
    shot_dir = tmp_path / "shot_a"
    shot_dir.mkdir()
    (shot_dir / "render.0001.exr").touch()
    replacement = tmp_path / "_review_mp4s" / "shot_a_render.mp4"
    replacement.parent.mkdir()
    replacement.write_bytes(b"mp4")
    output_paths: list[Path] = []

    def fake_replace_sequence_with_mp4(input_pattern: str, output_mp4: Path, **_kwargs):
        output_paths.append(output_mp4)
        assert input_pattern == str(shot_dir / "render.%04d.exr")
        return object()

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(
        cli_main,
        "replace_sequence_with_mp4",
        fake_replace_sequence_with_mp4,
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-replace",
            str(tmp_path),
            "--mp4-dir",
            "_review_mp4s",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_paths == [replacement]


def test_batch_replace_deduplicates_colliding_batch_convert_output_names(
    monkeypatch, tmp_path: Path
) -> None:
    """Batch replacement should mirror batch-convert suffixes for colliding names."""
    (tmp_path / "render.001.exr").touch()
    (tmp_path / "render.0001.exr").touch()
    review_dir = tmp_path / "_review_mp4s"
    review_dir.mkdir()
    (review_dir / "render.mp4").write_bytes(b"mp4")
    (review_dir / "render_2.mp4").write_bytes(b"mp4")
    output_paths: list[Path] = []

    def fake_replace_sequence_with_mp4(_input_pattern: str, output_mp4: Path, **_kwargs):
        output_paths.append(output_mp4)
        return object()

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(
        cli_main,
        "replace_sequence_with_mp4",
        fake_replace_sequence_with_mp4,
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-replace",
            str(tmp_path),
            "--mp4-dir",
            "_review_mp4s",
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_paths == [
        review_dir / "render.mp4",
        review_dir / "render_2.mp4",
    ]


def test_build_safe_output_path_supports_custom_container_ext(tmp_path: Path) -> None:
    """build_safe_output_path normalizes container extensions and rejects invalid ones."""
    shot_dir = tmp_path / "shot_01"
    shot_dir.mkdir()
    (shot_dir / "beauty.0001.exr").touch()

    seq = discover_frame_sequences(tmp_path, "exr")[0]
    output_dir = tmp_path / "out"

    assert build_safe_output_path(tmp_path, output_dir, seq, container_ext="MOV") == (
        output_dir / "shot_01_beauty.mov"
    )
    assert build_safe_output_path(tmp_path, output_dir, seq, container_ext=".mov") == (
        output_dir / "shot_01_beauty.mov"
    )

    with pytest.raises(ValueError):
        build_safe_output_path(tmp_path, output_dir, seq, container_ext="../mov")


def test_is_sequence_settled_checks_mtime_and_missing_files(tmp_path: Path) -> None:
    """is_sequence_settled distinguishes fresh, settled, empty, and missing sequences."""
    f1 = tmp_path / "render.0001.exr"
    f2 = tmp_path / "render.0002.exr"
    f1.touch()
    f2.touch()

    os.utime(f1, (1000.0, 1000.0))
    os.utime(f2, (1005.0, 1005.0))

    seq = discover_frame_sequences(tmp_path, "exr")[0]
    assert not is_sequence_settled(seq, settle_seconds=2.0, now=1006.0)
    assert is_sequence_settled(seq, settle_seconds=2.0, now=1007.0)

    f2.unlink()
    assert not is_sequence_settled(seq, settle_seconds=2.0, now=1010.0)

    empty_seq = BatchSequence(
        directory=tmp_path,
        prefix="empty.",
        suffix=".exr",
        padding=4,
        frame_numbers=[],
    )
    assert not is_sequence_settled(empty_seq, settle_seconds=0.0, now=1010.0)


def test_watch_and_convert_sequences_waits_for_settle_and_tracks_rerenders(
    tmp_path: Path,
) -> None:
    """Watch polling ignores unsettled/unchanged sequences and reconverts updated renders."""
    seq_dir = tmp_path / "shot"
    seq_dir.mkdir()
    f1 = seq_dir / "beauty.0001.exr"
    f2 = seq_dir / "beauty.0002.exr"
    f1.touch()
    f2.touch()
    os.utime(f1, (100.0, 100.0))
    os.utime(f2, (100.0, 100.0))

    out_dir = tmp_path / "out"
    conversions: list[str] = []

    class FakeConverter:
        def __init__(self, config: ConversionConfig) -> None:
            self._config = config

        def convert(self) -> None:
            conversions.append(self._config.input_pattern)
            Path(self._config.output_path).write_bytes(b"mov")

    def build_config(seq: BatchSequence) -> ConversionConfig:
        out_path = build_safe_output_path(tmp_path, out_dir, seq, container_ext=".mov")
        return (
            ConversionConfigBuilder()
            .with_input_pattern(str(seq.input_pattern))
            .with_output_path(str(out_path))
            .with_fps(24.0)
            .with_codec("prores_422")
            .build()
        )

    poll_counter = {"count": 0}

    def on_sleep(_interval: float) -> None:
        poll_counter["count"] += 1
        if poll_counter["count"] == 1:
            # Poll 2 stays unchanged -> must NOT reconvert
            return
        if poll_counter["count"] == 2:
            # Poll 3 adds frame 3 -> re-rendered sequence MUST convert again
            f3 = seq_dir / "beauty.0003.exr"
            f3.touch()
            os.utime(f3, (105.0, 105.0))

    produced = watch_and_convert_sequences(
        tmp_path,
        build_config,
        settle_seconds=1.0,
        poll_interval=0.1,
        max_polls=3,
        sleep_fn=on_sleep,
        converter_factory=FakeConverter,
    )

    assert len(conversions) == 2
    assert produced == [out_dir / "shot_beauty.mov", out_dir / "shot_beauty.mov"]


def test_batch_convert_preset_prores_mov_and_watch_flags(monkeypatch, tmp_path: Path) -> None:
    """CLI batch-convert supports --preset (.mov output + overrides) and --watch --max-polls 1."""
    shot_dir = tmp_path / "shot"
    shot_dir.mkdir()
    for frame in (1001, 1002):
        frame_path = shot_dir / f"comp.{frame:04d}.exr"
        frame_path.touch()
        os.utime(frame_path, (100.0, 100.0))

    preset_file = tmp_path / "dailies.json"
    preset_config = (
        ConversionConfigBuilder()
        .with_input_pattern("placeholder.%04d.exr")
        .with_output_path("placeholder.mov")
        .with_fps(25.0)
        .with_codec("prores_422")
        .build()
    )
    save_preset(preset_config, preset_file)

    captured_configs: list[ConversionConfig] = []

    class FakeRenderKit:
        def convert_with_config(self, config: ConversionConfig, show_progress=None) -> None:
            captured_configs.append(config)
            Path(config.output_path).write_bytes(b"mov")

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_batch, "RenderKit", FakeRenderKit)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "batch-convert",
            str(tmp_path),
            "--preset",
            str(preset_file),
            "--fps",
            "30",
            "--watch",
            "--max-polls",
            "1",
            "--settle-seconds",
            "0",
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Watch complete: 1 sequence(s) converted." in result.output
    assert len(captured_configs) == 1
    assert captured_configs[0].codec == "prores_422"
    assert captured_configs[0].fps == 30.0
    assert captured_configs[0].output_path.endswith("shot_comp.mov")
