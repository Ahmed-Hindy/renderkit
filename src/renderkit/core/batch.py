"""Batch sequence discovery and manifest helpers."""

from __future__ import annotations

import csv
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import ConversionConfig
from renderkit.core.sequence_names import split_numbered_frame_name
from renderkit.exceptions import RenderKitError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BatchSequence:
    """A frame sequence discovered from a directory scan."""

    directory: Path
    prefix: str
    suffix: str
    padding: int
    frame_numbers: list[int]

    @property
    def pattern(self) -> str:
        return f"{self.prefix}%0{self.padding}d{self.suffix}"

    @property
    def input_pattern(self) -> Path:
        return self.directory / self.pattern

    @property
    def frame_count(self) -> int:
        return len(self.frame_numbers)

    @property
    def frame_range(self) -> str:
        return f"{self.frame_numbers[0]}-{self.frame_numbers[-1]}"

    @property
    def pattern_path(self) -> Path:
        """Return the full pattern path for this sequence."""
        return self.input_pattern

    @property
    def files(self) -> list[Path]:
        """Return concrete frame paths ordered by frame number."""
        return [
            self.directory / f"{self.prefix}{frame_num:0{self.padding}d}{self.suffix}"
            for frame_num in self.frame_numbers
        ]


@dataclass
class BatchManifestRecord:
    """A manifest row for a batch conversion attempt."""

    input_pattern: str
    output_path: str
    frame_count: int
    frame_range: str
    size_bytes: Optional[int]
    status: str
    error: str = ""

    def as_dict(self) -> dict[str, str | int]:
        return {
            "input_pattern": self.input_pattern,
            "output_path": self.output_path,
            "frame_count": self.frame_count,
            "frame_range": self.frame_range,
            "size_bytes": "" if self.size_bytes is None else self.size_bytes,
            "status": self.status,
            "error": self.error,
        }


def discover_frame_sequences(
    root: Path,
    extension: str = "exr",
    *,
    recursive: bool = True,
    min_sequence_length: int = 1,
) -> list[BatchSequence]:
    """Discover frame sequences with a numeric frame component under root.

    Args:
        root: Directory to search.
        extension: Image file extension (with or without leading dot).
        recursive: Whether to scan subdirectories recursively.
        min_sequence_length: Minimum number of frames required to include a sequence.

    Returns:
        Sorted list of discovered :class:`BatchSequence` objects.
    """
    if min_sequence_length < 1:
        raise ValueError("min_sequence_length must be >= 1")

    normalized_ext = _normalize_extension(extension)
    groups: dict[tuple[Path, str, str, int], set[int]] = {}
    candidates = sorted(root.rglob("*")) if recursive else sorted(root.iterdir())

    for frame_path in candidates:
        if not frame_path.is_file() or frame_path.suffix.lower() != normalized_ext:
            continue

        parsed_name = split_numbered_frame_name(frame_path)
        if parsed_name is None:
            continue

        prefix, frame_text, suffix = parsed_name
        key = (
            frame_path.parent,
            prefix,
            suffix,
            len(frame_text),
        )
        groups.setdefault(key, set()).add(int(frame_text))

    sequences = [
        BatchSequence(
            directory=directory,
            prefix=prefix,
            suffix=suffix,
            padding=padding,
            frame_numbers=sorted(frame_numbers),
        )
        for (directory, prefix, suffix, padding), frame_numbers in groups.items()
        if len(frame_numbers) >= min_sequence_length
    ]
    return sorted(sequences, key=lambda seq: (seq.directory.as_posix(), seq.pattern))


def build_safe_output_path(
    root: Path,
    output_dir: Path,
    sequence: BatchSequence,
    container_ext: str = ".mp4",
) -> Path:
    """Build a stable collision-resistant video path for a discovered sequence.

    Args:
        root: Batch root directory.
        output_dir: Target output directory.
        sequence: Discovered frame sequence.
        container_ext: Output container extension (e.g., ``'.mp4'`` or ``'.mov'``).

    Returns:
        Collision-resistant output file path.
    """
    normalized_ext = _normalize_container_extension(container_ext)
    relative_dir = sequence.directory.resolve().relative_to(root.resolve())
    name_parts = [part for part in relative_dir.parts if part not in ("", ".")]
    stem = sequence.prefix.rstrip("._- ") or "sequence"
    name_parts.append(stem)
    safe_name = "_".join(_safe_filename_part(part) for part in name_parts)
    return output_dir / f"{safe_name}{normalized_ext}"


def is_sequence_settled(
    sequence: BatchSequence,
    settle_seconds: float = 2.0,
    now: Optional[float] = None,
) -> bool:
    """Return True when all frames in a sequence exist and have stopped updating.

    Args:
        sequence: Frame sequence to check.
        settle_seconds: Minimum elapsed seconds since the newest frame mtime.
        now: Optional epoch timestamp override for deterministic testing.

    Returns:
        ``True`` if the sequence is non-empty, all files are stat-able, and the
        newest file is at least ``settle_seconds`` old.
    """
    files = _sequence_files(sequence)
    if not files:
        return False

    max_mtime: Optional[float] = None
    for file_path in files:
        try:
            mtime = file_path.stat().st_mtime
        except OSError:
            return False
        if max_mtime is None or mtime > max_mtime:
            max_mtime = mtime

    if max_mtime is None:
        return False
    current_time = time.time() if now is None else now
    return (current_time - max_mtime) >= settle_seconds


def watch_and_convert_sequences(
    root_dir: Path,
    config_builder_fn: Callable[[BatchSequence], ConversionConfig],
    *,
    extension: str = "exr",
    recursive: bool = True,
    min_sequence_length: int = 2,
    settle_seconds: float = 2.0,
    poll_interval: float = 5.0,
    max_polls: Optional[int] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    converter_factory: Optional[Callable[[ConversionConfig], Any]] = None,
) -> list[Path]:
    """Poll a root directory and convert newly settled frame sequences.

    Args:
        root_dir: Directory to watch for incoming frame sequences.
        config_builder_fn: Callback returning a :class:`ConversionConfig` for a sequence.
        extension: Frame extension to watch for.
        recursive: Whether to scan subdirectories recursively.
        min_sequence_length: Minimum number of frames required before converting.
        settle_seconds: Minimum age since the last frame write before converting.
        poll_interval: Seconds to sleep between polls.
        max_polls: Optional poll iteration cap (primarily for CLI/testing).
        sleep_fn: Sleep callable between polls.
        converter_factory: Optional callable constructing a converter with ``.convert()``.

    Returns:
        List of output video paths produced during polling.
    """
    if converter_factory is None:
        from renderkit.core.converter import SequenceConverter

        factory: Callable[[ConversionConfig], Any] = SequenceConverter
    else:
        factory = converter_factory

    processed_signatures: dict[Path, tuple[int, int]] = {}
    produced_outputs: list[Path] = []
    polls = 0

    try:
        while max_polls is None or polls < max_polls:
            polls += 1
            sequences = discover_frame_sequences(
                root_dir,
                extension,
                recursive=recursive,
                min_sequence_length=min_sequence_length,
            )
            for sequence in sequences:
                files = _sequence_files(sequence)
                if not files:
                    continue
                max_mtime_ns = _max_mtime_ns(files)
                if max_mtime_ns is None:
                    continue
                if not is_sequence_settled(sequence, settle_seconds=settle_seconds):
                    continue

                pattern_key = Path(getattr(sequence, "pattern_path", sequence.input_pattern))
                signature = (len(files), max_mtime_ns)
                if processed_signatures.get(pattern_key) == signature:
                    continue

                config = config_builder_fn(sequence)
                output_path = Path(config.output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    converter = factory(config)
                    converter.convert()
                except (RenderKitError, OSError, RuntimeError, ValueError):
                    logger.exception("Watch conversion failed for %s", pattern_key)
                    continue

                processed_signatures[pattern_key] = signature
                produced_outputs.append(output_path)

            if max_polls is not None and polls >= max_polls:
                break
            sleep_fn(poll_interval)
    except KeyboardInterrupt:
        logger.info("Watch polling stopped by KeyboardInterrupt.")

    return produced_outputs


def deduplicate_output_path(output_path: Path, planned_outputs: set[Path]) -> Path:
    """Return a suffixed output path when a planned batch path already exists."""
    if output_path not in planned_outputs:
        return output_path

    index = 2
    while True:
        candidate = output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix}")
        if candidate not in planned_outputs:
            return candidate
        index += 1


def write_csv_manifest(path: Path, records: list[BatchManifestRecord]) -> None:
    """Write a CSV manifest for all attempted batch conversions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "input_pattern",
        "output_path",
        "frame_count",
        "frame_range",
        "size_bytes",
        "status",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.as_dict())


def append_jsonl_manifest(path: Path, record: BatchManifestRecord) -> None:
    """Append one JSONL manifest record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict()) + "\n")


def _normalize_extension(extension: str) -> str:
    ext = extension.strip().lower()
    if not ext:
        raise ValueError("Extension cannot be empty")
    return ext if ext.startswith(".") else f".{ext}"


def _normalize_container_extension(container_ext: str) -> str:
    ext = container_ext.strip().lower()
    if not ext:
        raise ValueError("Container extension cannot be empty")
    if not ext.startswith("."):
        ext = f".{ext}"
    body = ext[1:]
    if not body or not body.isalnum():
        raise ValueError(f"Invalid container extension: {container_ext!r}")
    return ext


def _sequence_files(sequence: Any) -> list[Path]:
    nested = getattr(sequence, "sequence", None)
    if nested is not None and hasattr(nested, "files"):
        return [Path(path) for path in nested.files]
    if hasattr(sequence, "files"):
        return [Path(path) for path in sequence.files]
    return []


def _max_mtime_ns(files: list[Path]) -> Optional[int]:
    max_mtime_ns: Optional[int] = None
    for file_path in files:
        try:
            mtime_ns = file_path.stat().st_mtime_ns
        except OSError:
            return None
        if max_mtime_ns is None or mtime_ns > max_mtime_ns:
            max_mtime_ns = mtime_ns
    return max_mtime_ns


def _safe_filename_part(value: str) -> str:
    safe = "".join(
        character if character.isascii() and (character.isalnum() or character in "._-") else "_"
        for character in value.strip()
    ).strip("._-")
    return safe or "sequence"
