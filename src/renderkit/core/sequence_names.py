"""Helpers for parsing numbered frame sequence names."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def split_numbered_frame_name(
    path_or_name: Path | str,
    *,
    required_extension: Optional[str] = None,
) -> Optional[tuple[str, str, str]]:
    """Split a numbered frame name into prefix, frame text, and suffix.

    Args:
        path_or_name: Path or filename with trailing frame digits before the extension.
        required_extension: Optional extension filter, with or without a leading dot.

    Returns:
        Tuple of ``(prefix, frame_text, suffix)`` when a frame number is present,
        otherwise ``None``.
    """
    path = Path(path_or_name)
    suffix = path.suffix
    if required_extension is not None and suffix.lower() != _normalize_extension(
        required_extension
    ):
        return None

    stem = path.stem
    frame_start = len(stem)
    while frame_start > 0 and stem[frame_start - 1].isdigit():
        frame_start -= 1

    if frame_start == len(stem):
        return None

    return stem[:frame_start], stem[frame_start:], suffix


def _normalize_extension(extension: str) -> str:
    normalized = extension.strip().lower()
    if not normalized:
        raise ValueError("Extension cannot be empty")
    return normalized if normalized.startswith(".") else f".{normalized}"
