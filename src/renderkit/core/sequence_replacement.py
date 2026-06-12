"""Safe replacement of frame sequences with verified MP4 files."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from renderkit.core.batch import BatchSequence, build_safe_output_path
from renderkit.core.ffmpeg_utils import get_ffprobe_exe, popen_kwargs
from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import SequenceReplacementError

Mp4Verifier = Callable[[Path], None]


@dataclass(frozen=True)
class SequenceReplacementResult:
    """Result of a sequence replacement operation."""

    source_pattern: str
    source_frames: list[Path]
    replacement_mp4: Path
    copied_mp4: Path
    audit_report: Path
    deleted_frames: list[Path]
    deleted_count: int
    reclaimed_bytes: int
    dry_run: bool
    verified: bool
    copied: bool

    def to_audit_record(self) -> dict[str, object]:
        """Return a JSON-serializable audit record."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "source_pattern": self.source_pattern,
            "source_frames": [str(path) for path in self.source_frames],
            "source_count": len(self.source_frames),
            "replacement_mp4": str(self.replacement_mp4),
            "copied_mp4": str(self.copied_mp4),
            "deleted_frames": [str(path) for path in self.deleted_frames],
            "deleted_count": self.deleted_count,
            "reclaimed_bytes": self.reclaimed_bytes,
            "dry_run": self.dry_run,
            "verified": self.verified,
            "copied": self.copied,
        }


def verify_mp4_readable(mp4_path: Path) -> None:
    """Verify that an MP4 exists and can be read by FFprobe.

    Args:
        mp4_path: MP4 file to verify.

    Raises:
        SequenceReplacementError: If the MP4 does not exist or FFprobe cannot read it.
    """
    if not mp4_path.is_file():
        raise SequenceReplacementError(f"Replacement MP4 does not exist: {mp4_path}")

    ffprobe_exe = get_ffprobe_exe()
    command = [
        ffprobe_exe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(mp4_path),
    ]
    try:
        # FFprobe receives fixed arguments and the MP4 path as a single argv item.
        result = subprocess.run(  # NOSONAR
            command,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            **popen_kwargs(),
        )
    except OSError as exc:
        raise SequenceReplacementError(f"Could not run ffprobe: {exc}") from exc

    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "ffprobe returned an error"
        raise SequenceReplacementError(f"Replacement MP4 is not readable: {mp4_path} ({details})")


def replace_sequence_with_mp4(
    input_pattern: str,
    output_mp4: Path,
    *,
    delete_source: bool = False,
    verify: bool = False,
    dry_run: bool = False,
    audit_report: Optional[Path] = None,
    verifier: Mp4Verifier = verify_mp4_readable,
) -> SequenceReplacementResult:
    """Replace one detected frame sequence with an MP4 and write an audit record.

    Args:
        input_pattern: Sequence pattern such as ``render.%04d.exr``.
        output_mp4: MP4 file to copy into the source sequence directory.
        delete_source: Whether to delete the source frame files after replacement.
        verify: Whether to verify the MP4 with FFprobe before proceeding.
        dry_run: Whether to only report planned actions.
        audit_report: Optional JSONL audit path.
        verifier: Verification callback used by tests.

    Returns:
        Result describing the replacement.

    Raises:
        SequenceReplacementError: If verification, copy, or deletion cannot proceed safely.
    """
    sequence = SequenceDetector.detect_sequence(input_pattern)
    source_frames = _existing_sequence_frames(sequence)
    if not source_frames:
        raise SequenceReplacementError(f"No source frames found for pattern: {input_pattern}")

    source_mp4 = output_mp4.resolve()
    destination_mp4 = sequence.base_path / output_mp4.name
    report_path = audit_report or (sequence.base_path / "renderkit-replacement-audit.jsonl")
    _prepare_audit_report(report_path)
    verified = _verify_source_mp4_if_needed(
        source_mp4,
        delete_source=delete_source,
        verify=verify,
        dry_run=dry_run,
        verifier=verifier,
    )
    copied, destination_verified = _copy_replacement_mp4(
        source_mp4,
        destination_mp4,
        delete_source=delete_source,
        dry_run=dry_run,
        verifier=verifier,
    )
    verified = verified or destination_verified
    deleted_frames, reclaimed_bytes = _delete_or_plan_frames(
        source_frames,
        delete_source=delete_source,
        dry_run=dry_run,
    )

    result = SequenceReplacementResult(
        source_pattern=input_pattern,
        source_frames=source_frames,
        replacement_mp4=source_mp4,
        copied_mp4=destination_mp4,
        audit_report=report_path,
        deleted_frames=deleted_frames,
        deleted_count=len(deleted_frames) if delete_source else 0,
        reclaimed_bytes=reclaimed_bytes if delete_source else 0,
        dry_run=dry_run,
        verified=verified,
        copied=copied,
    )
    _append_audit_record(report_path, result.to_audit_record())
    return result


def _verify_source_mp4_if_needed(
    source_mp4: Path,
    *,
    delete_source: bool,
    verify: bool,
    dry_run: bool,
    verifier: Mp4Verifier,
) -> bool:
    should_verify = verify or (delete_source and not dry_run)
    if not should_verify:
        return False

    verifier(source_mp4)
    return True


def _copy_replacement_mp4(
    source_mp4: Path,
    destination_mp4: Path,
    *,
    delete_source: bool,
    dry_run: bool,
    verifier: Mp4Verifier,
) -> tuple[bool, bool]:
    if not source_mp4.is_file():
        raise SequenceReplacementError(f"Replacement MP4 does not exist: {source_mp4}")

    if dry_run:
        return False, False

    copied = False
    if source_mp4 != destination_mp4.resolve():
        shutil.copy2(source_mp4, destination_mp4)
        copied = True

    if delete_source:
        verifier(destination_mp4)
        return copied, True

    return copied, False


def _delete_or_plan_frames(
    source_frames: list[Path],
    *,
    delete_source: bool,
    dry_run: bool,
) -> tuple[list[Path], int]:
    if not delete_source:
        return [], 0
    if dry_run:
        return source_frames, _sum_existing_sizes(source_frames)
    return _delete_frames(source_frames)


def find_exr_sequences(root: Path) -> list[str]:
    """Find EXR sequence patterns below a directory.

    Args:
        root: Directory to scan recursively.

    Returns:
        Detected sequence patterns sorted by path.
    """
    groups: dict[tuple[Path, str, str, int], list[int]] = {}
    for file_path in root.rglob("*.exr"):
        if not file_path.is_file():
            continue
        numbered_name = _split_numbered_exr_name(file_path.name)
        if numbered_name is None:
            continue
        prefix, frame, suffix = numbered_name
        key = (file_path.parent, prefix, suffix, len(frame))
        groups.setdefault(key, []).append(int(frame))

    patterns = []
    for directory, prefix, suffix, padding in groups:
        if not groups[(directory, prefix, suffix, padding)]:
            continue
        patterns.append(str(directory / f"{prefix}%0{padding}d{suffix}"))
    return sorted(patterns)


def find_replacement_mp4(sequence_pattern: str, mp4_dir: Path, root: Optional[Path] = None) -> Path:
    """Return the expected MP4 replacement path for a sequence pattern.

    Args:
        sequence_pattern: Detected sequence pattern.
        mp4_dir: Directory containing replacement MP4s.
        root: Optional scan root used to match batch-convert's nested output names.

    Returns:
        Expected MP4 path.
    """
    if root is not None:
        sequence_path = Path(sequence_pattern)
        sequence_parts = _split_sequence_pattern_name(sequence_path.name)
        if sequence_parts is not None:
            prefix, suffix, padding = sequence_parts
            sequence = BatchSequence(
                directory=sequence_path.parent,
                prefix=prefix,
                suffix=suffix,
                padding=padding,
                frame_numbers=[0],
            )
            return build_safe_output_path(root, mp4_dir, sequence)

    pattern_name = Path(sequence_pattern).name
    stem = Path(_remove_frame_token(pattern_name)).stem.strip(" ._-")
    return mp4_dir / f"{stem}.mp4"


def _existing_sequence_frames(sequence: FrameSequence) -> list[Path]:
    return [
        path
        for frame_number in sequence.frame_numbers
        if (path := sequence.get_file_path(frame_number)).is_file()
    ]


def _split_numbered_exr_name(filename: str) -> Optional[tuple[str, str, str]]:
    path = Path(filename)
    if path.suffix.lower() != ".exr":
        return None

    stem = path.stem
    frame_start = len(stem)
    while frame_start > 0 and stem[frame_start - 1].isdigit():
        frame_start -= 1

    if frame_start == len(stem):
        return None

    return stem[:frame_start], stem[frame_start:], path.suffix


def _sum_existing_sizes(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.is_file())


def _delete_frames(paths: list[Path]) -> tuple[list[Path], int]:
    deleted_frames = []
    reclaimed_bytes = 0
    for path in paths:
        if not path.is_file():
            continue
        reclaimed_bytes += path.stat().st_size
        path.unlink()
        deleted_frames.append(path)
    return deleted_frames, reclaimed_bytes


def _append_audit_record(audit_report: Path, record: dict[str, object]) -> None:
    try:
        with audit_report.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        raise SequenceReplacementError(f"Could not write audit report: {audit_report}") from exc


def _prepare_audit_report(audit_report: Path) -> None:
    try:
        audit_report.parent.mkdir(parents=True, exist_ok=True)
        with audit_report.open("a", encoding="utf-8") as stream:
            stream.flush()
    except OSError as exc:
        raise SequenceReplacementError(f"Could not write audit report: {audit_report}") from exc


def _remove_frame_token(filename: str) -> str:
    filename = re.sub(r"%\d+d", "", filename)
    filename = re.sub(r"\$F\d+", "", filename)
    filename = re.sub(r"#+", "", filename)
    return filename


def _split_sequence_pattern_name(pattern_name: str) -> Optional[tuple[str, str, int]]:
    match = re.search(r"(%0?(\d+)d|\$F(\d+)|#+)", pattern_name)
    if match is None:
        return None

    token = match.group(0)
    padding_text = match.group(2) or match.group(3)
    padding = int(padding_text) if padding_text else len(token)
    return pattern_name[: match.start()], pattern_name[match.end() :], padding
