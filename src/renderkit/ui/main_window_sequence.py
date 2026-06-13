"""Path and pattern helpers used by the main-window sequence workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def _trailing_digit_span(text: str) -> Optional[tuple[int, int]]:
    end = len(text)
    start = end
    while start > 0 and text[start - 1].isdigit():
        start -= 1
    if start == end:
        return None
    return start, end


def _last_digit_run_span(text: str) -> Optional[tuple[int, int]]:
    end = len(text)
    while end > 0 and not text[end - 1].isdigit():
        end -= 1
    if end == 0:
        return None

    start = end
    while start > 0 and text[start - 1].isdigit():
        start -= 1
    return start, end


def _remove_percent_frame_tokens(text: str) -> str:
    result = []
    index = 0
    while index < len(text):
        if text[index] != "%":
            result.append(text[index])
            index += 1
            continue

        token_end = index + 1
        while token_end < len(text) and text[token_end].isdigit():
            token_end += 1
        if token_end < len(text) and text[token_end] == "d":
            index = token_end + 1
            continue

        result.append(text[index])
        index += 1
    return "".join(result)


def _remove_houdini_frame_tokens(text: str) -> str:
    result = []
    index = 0
    while index < len(text):
        if text.startswith("$F", index):
            index += 2
            while index < len(text) and text[index].isdigit():
                index += 1
            continue

        result.append(text[index])
        index += 1
    return "".join(result)


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

    span = _trailing_digit_span(stem)
    if span is None:
        return None
    try:
        return int(stem[span[0] : span[1]])
    except ValueError:
        return None


def derive_sequence_stem(pattern: str) -> str:
    """Return a clean stem for a frame-sequence pattern."""
    if not pattern:
        return ""
    name = Path(pattern).name
    stem = Path(name).stem

    stem = _remove_percent_frame_tokens(stem)
    stem = _remove_houdini_frame_tokens(stem)
    stem = stem.replace("#", "")
    span = _trailing_digit_span(stem)
    if span is not None:
        stem = stem[: span[0]]
    return stem.rstrip("._- ").strip()


def build_pattern_from_path(path: Path) -> Optional[str]:
    """Convert a numbered file path into a printf-style sequence pattern."""
    if not path or not path.is_file():
        return None

    name_part, ext = path.stem, path.suffix
    if not name_part or not ext:
        return None

    span = _last_digit_run_span(name_part)
    if span is None:
        return None

    frame_number = name_part[span[0] : span[1]]
    padding = len(frame_number)
    pattern_name = name_part[: span[0]] + f"%0{padding}d" + name_part[span[1] :]
    pattern_filename = pattern_name + ext
    return str(path.parent / pattern_filename)
