"""Tests for safe sequence replacement cleanup."""

import json
from pathlib import Path

import pytest

from renderkit.core.batch import build_safe_output_path, discover_frame_sequences
from renderkit.core.sequence_replacement import (
    find_exr_sequences,
    find_replacement_mp4,
    replace_sequence_with_mp4,
)
from renderkit.exceptions import SequenceReplacementError


def _write_sequence(tmp_path: Path, name: str = "render", count: int = 3) -> list[Path]:
    paths = []
    tmp_path.mkdir(parents=True, exist_ok=True)
    for frame in range(1, count + 1):
        path = tmp_path / f"{name}.{frame:04d}.exr"
        path.write_bytes(b"frame")
        paths.append(path)
    return paths


def test_replace_sequence_dry_run_writes_audit_without_deleting(tmp_path: Path) -> None:
    """Verify dry-run records planned source deletion without unlinking files."""
    frames = _write_sequence(tmp_path)
    mp4_path = tmp_path / "_review_mp4s" / "render.mp4"
    mp4_path.parent.mkdir()
    mp4_path.write_bytes(b"mp4")
    audit_path = tmp_path / "audit.jsonl"

    result = replace_sequence_with_mp4(
        str(tmp_path / "render.%04d.exr"),
        mp4_path,
        delete_source=True,
        dry_run=True,
        audit_report=audit_path,
    )

    assert result.dry_run is True
    assert result.deleted_count == 3
    assert all(path.exists() for path in frames)
    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert record["dry_run"] is True
    assert record["deleted_count"] == 3


def test_replace_sequence_dry_run_requires_replacement_mp4(tmp_path: Path) -> None:
    """Verify dry-run fails when the planned replacement MP4 is missing."""
    frames = _write_sequence(tmp_path)
    missing_mp4 = tmp_path / "_review_mp4s" / "render.mp4"

    with pytest.raises(SequenceReplacementError, match="Replacement MP4 does not exist"):
        replace_sequence_with_mp4(
            str(tmp_path / "render.%04d.exr"),
            missing_mp4,
            delete_source=True,
            dry_run=True,
        )

    assert all(path.exists() for path in frames)


def test_replace_sequence_refuses_delete_when_verification_fails(tmp_path: Path) -> None:
    """Verify source frames survive when MP4 verification fails."""
    frames = _write_sequence(tmp_path)
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"not a real video")

    def fail_verifier(path: Path) -> None:
        raise SequenceReplacementError(f"unreadable: {path}")

    with pytest.raises(SequenceReplacementError, match="unreadable"):
        replace_sequence_with_mp4(
            str(tmp_path / "render.%04d.exr"),
            mp4_path,
            delete_source=True,
            verifier=fail_verifier,
        )

    assert all(path.exists() for path in frames)


def test_replace_sequence_refuses_delete_when_audit_report_is_unwritable(
    tmp_path: Path,
) -> None:
    """Verify source frames survive when the audit report cannot be opened."""
    frames = _write_sequence(tmp_path)
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"mp4")
    audit_parent = tmp_path / "audit-parent"
    audit_parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SequenceReplacementError, match="Could not write audit report"):
        replace_sequence_with_mp4(
            str(tmp_path / "render.%04d.exr"),
            mp4_path,
            delete_source=True,
            audit_report=audit_parent / "audit.jsonl",
            verifier=lambda _path: None,
        )

    assert all(path.exists() for path in frames)


def test_replace_sequence_copies_verified_mp4_then_deletes_frames(tmp_path: Path) -> None:
    """Verify a successful replacement copies the MP4 and deletes exact source frames."""
    frames = _write_sequence(tmp_path)
    stray = tmp_path / "render.0001.exr.tmp"
    stray.write_bytes(b"keep")
    mp4_path = tmp_path / "_review_mp4s" / "render.mp4"
    mp4_path.parent.mkdir()
    mp4_path.write_bytes(b"mp4")
    verified_paths = []

    def verifier(path: Path) -> None:
        verified_paths.append(path)

    result = replace_sequence_with_mp4(
        str(tmp_path / "render.%04d.exr"),
        mp4_path,
        delete_source=True,
        verifier=verifier,
    )

    assert result.deleted_count == 3
    assert result.reclaimed_bytes == 15
    assert not any(path.exists() for path in frames)
    assert stray.exists()
    assert (tmp_path / "render.mp4").exists()
    assert verified_paths == [mp4_path.resolve(), tmp_path / "render.mp4"]


def test_find_exr_sequences_and_matching_mp4(tmp_path: Path) -> None:
    """Verify batch helpers derive sequence patterns and MP4 names."""
    _write_sequence(tmp_path, name="beauty")
    _write_sequence(tmp_path / "nested", name="depth", count=2)

    patterns = find_exr_sequences(tmp_path)

    assert patterns == [
        str(tmp_path / "beauty.%04d.exr"),
        str(tmp_path / "nested" / "depth.%04d.exr"),
    ]
    assert find_replacement_mp4(patterns[0], tmp_path / "_review_mp4s") == (
        tmp_path / "_review_mp4s" / "beauty.mp4"
    )


def test_find_replacement_mp4_matches_batch_convert_nested_output(tmp_path: Path) -> None:
    """Verify nested batch-convert outputs are found by batch-replace lookup."""
    _write_sequence(tmp_path / "shot_a", name="render", count=2)
    output_dir = tmp_path / "_review_mp4s"

    batch_sequence = discover_frame_sequences(tmp_path, "exr")[0]
    batch_output = build_safe_output_path(tmp_path, output_dir, batch_sequence)
    replacement_pattern = find_exr_sequences(tmp_path)[0]

    assert batch_output == output_dir / "shot_a_render.mp4"
    assert find_replacement_mp4(replacement_pattern, output_dir, tmp_path) == batch_output


def test_find_replacement_mp4_matches_batch_convert_empty_prefix_output(
    tmp_path: Path,
) -> None:
    """Verify frame-only sequence names still resolve to sequence.mp4."""
    for frame in [1, 2]:
        (tmp_path / f"{frame:04d}.exr").write_bytes(b"frame")
    output_dir = tmp_path / "_review_mp4s"

    batch_sequence = discover_frame_sequences(tmp_path, "exr")[0]
    batch_output = build_safe_output_path(tmp_path, output_dir, batch_sequence)
    replacement_pattern = find_exr_sequences(tmp_path)[0]

    assert batch_output == output_dir / "sequence.mp4"
    assert find_replacement_mp4(replacement_pattern, output_dir, tmp_path) == batch_output
