"""Batch sequence discovery and manifest helpers."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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


def discover_frame_sequences(root: Path, extension: str) -> list[BatchSequence]:
    """Recursively discover frame sequences with a numeric frame component."""
    normalized_ext = _normalize_extension(extension)
    groups: dict[tuple[Path, str, str, int], set[int]] = {}

    for frame_path in sorted(root.rglob("*")):
        if not frame_path.is_file() or frame_path.suffix.lower() != normalized_ext:
            continue

        match = re.match(r"^(?P<prefix>.*?)(?P<frame>\d+)(?P<suffix>\.[^.]+)$", frame_path.name)
        if not match:
            continue

        frame_text = match.group("frame")
        key = (
            frame_path.parent,
            match.group("prefix"),
            match.group("suffix"),
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
        if frame_numbers
    ]
    return sorted(sequences, key=lambda seq: (seq.directory.as_posix(), seq.pattern))


def build_safe_output_path(root: Path, output_dir: Path, sequence: BatchSequence) -> Path:
    """Build a stable collision-resistant MP4 path for a discovered sequence."""
    relative_dir = sequence.directory.resolve().relative_to(root.resolve())
    name_parts = [part for part in relative_dir.parts if part not in ("", ".")]
    stem = sequence.prefix.rstrip("._- ") or "sequence"
    name_parts.append(stem)
    safe_name = "_".join(_safe_filename_part(part) for part in name_parts)
    return output_dir / f"{safe_name}.mp4"


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


def _safe_filename_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    safe = safe.strip("._-")
    return safe or "sequence"
