"""Path and pattern helpers used by the main-window sequence workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def pattern_has_frame_token(filename: str) -> bool:
    """Return whether a filename already looks like a frame-sequence pattern."""
    if "%" in filename:
        percent_index = filename.find("%")
        i = percent_index + 1
        while i < len(filename) and filename[i].isdigit():
            i += 1
        if i < len(filename) and filename[i] == "d":
            return True

    if "$F" in filename:
        return True

    if "#" in filename:
        return True

    stem = Path(filename).stem
    if not stem:
        return False
    i = len(stem) - 1
    while i >= 0 and stem[i].isdigit():
        i -= 1
    return i < len(stem) - 1


def extract_frame_number(path: Path) -> Optional[int]:
    """Extract a trailing frame number from a filename."""
    stem = path.stem
    if not stem:
        return None

    match = re.search(r"(\d+)$", stem)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def derive_sequence_stem(pattern: str) -> str:
    """Return a clean stem for a frame-sequence pattern."""
    if not pattern:
        return ""
    name = Path(pattern).name
    stem = Path(name).stem

    stem = re.sub(r"%\d*d", "", stem)
    stem = re.sub(r"\$F\d*", "", stem)
    stem = re.sub(r"#+", "", stem)
    stem = re.sub(r"\d+$", "", stem)
    return stem.rstrip("._- ").strip()


def build_pattern_from_path(path: Path) -> Optional[str]:
    """Convert a numbered file path into a printf-style sequence pattern."""
    if not path or not path.is_file():
        return None

    name_part, ext = path.stem, path.suffix
    if not name_part or not ext:
        return None

    digit_matches = list(re.finditer(r"\d+", name_part))
    if not digit_matches:
        return None

    last_match = digit_matches[-1]
    frame_number = last_match.group(0)
    padding = len(frame_number)
    pattern_name = name_part[: last_match.start()] + f"%0{padding}d" + name_part[last_match.end() :]
    pattern_filename = pattern_name + ext
    return str(path.parent / pattern_filename)
