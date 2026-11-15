"""Tests for safe sequence replacement cleanup."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from renderkit.core import sequence_replacement
from renderkit.core.sequence_replacement import (
    find_exr_sequences,
    find_replacement_mp4,
    replace_sequence_with_mp4,
    verify_mp4_readable,
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


def test_find_replacement_mp4_matches_nested_batch_convert_name(tmp_path: Path) -> None:
    """Nested sequence replacement names should match batch-convert output names."""
    _write_sequence(tmp_path / "shot_a", name="render", count=1)
    patterns = find_exr_sequences(tmp_path)

    replacement_path = find_replacement_mp4(
        patterns[0],
        tmp_path / "_review_mp4s",
        root=tmp_path,
    )

    assert replacement_path == tmp_path / "_review_mp4s" / "shot_a_render.mp4"


def test_verify_mp4_readable_matches_expected_nb_read_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """verify_mp4_readable passes when ffprobe nb_read_frames matches expected_frames."""
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"mp4")
    captured_cmd: list[str] = []

    def fake_run(cmd, **kwargs):
        captured_cmd.extend(cmd)
        payload = {"streams": [{"nb_read_frames": "3"}], "format": {"duration": "0.125"}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sequence_replacement, "get_ffprobe_exe", lambda: "ffprobe")
    monkeypatch.setattr(sequence_replacement.subprocess, "run", fake_run)

    verify_mp4_readable(mp4_path, expected_frames=3)

    assert "-count_frames" in captured_cmd
    assert "stream=nb_read_frames,nb_frames:format=duration" in captured_cmd


def test_verify_mp4_readable_rejects_mismatched_nb_read_frames(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """verify_mp4_readable raises SequenceReplacementError on frame count mismatch."""
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"mp4")

    def fake_run(cmd, **kwargs):
        payload = {"streams": [{"nb_read_frames": "2"}], "format": {"duration": "0.083"}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sequence_replacement, "get_ffprobe_exe", lambda: "ffprobe")
    monkeypatch.setattr(sequence_replacement.subprocess, "run", fake_run)

    with pytest.raises(SequenceReplacementError, match="expected 3, got 2"):
        verify_mp4_readable(mp4_path, expected_frames=3)


def test_verify_mp4_readable_rejects_missing_or_non_integer_frame_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """verify_mp4_readable rejects missing or non-integer stream frame counts."""
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"mp4")

    def fake_run_missing(cmd, **kwargs):
        payload = {"streams": [{}]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sequence_replacement, "get_ffprobe_exe", lambda: "ffprobe")
    monkeypatch.setattr(sequence_replacement.subprocess, "run", fake_run_missing)

    with pytest.raises(SequenceReplacementError, match="missing or invalid"):
        verify_mp4_readable(mp4_path, expected_frames=3)

    def fake_run_bad_int(cmd, **kwargs):
        payload = {"streams": [{"nb_read_frames": "N/A"}]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sequence_replacement.subprocess, "run", fake_run_bad_int)

    with pytest.raises(SequenceReplacementError, match="not an integer"):
        verify_mp4_readable(mp4_path, expected_frames=3)


def test_replace_sequence_default_verifier_checks_source_frame_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """replace_sequence_with_mp4 passes source frame count to default verify_mp4_readable."""
    frames = _write_sequence(tmp_path, count=4)
    mp4_path = tmp_path / "render.mp4"
    mp4_path.write_bytes(b"mp4")

    def fake_run(cmd, **kwargs):
        payload = {"streams": [{"nb_read_frames": "3"}]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(sequence_replacement, "get_ffprobe_exe", lambda: "ffprobe")
    monkeypatch.setattr(sequence_replacement.subprocess, "run", fake_run)

    with pytest.raises(SequenceReplacementError, match="expected 4, got 3"):
        replace_sequence_with_mp4(
            str(tmp_path / "render.%04d.exr"),
            mp4_path,
            delete_source=True,
        )

    assert all(path.exists() for path in frames)
