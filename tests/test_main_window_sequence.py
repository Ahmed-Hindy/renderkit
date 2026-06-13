"""Tests for main-window sequence path helpers."""

from pathlib import Path

from renderkit.ui.main_window_sequence import (
    build_pattern_from_path,
    derive_sequence_stem,
    extract_frame_number,
    pattern_has_frame_token,
)


def test_pattern_has_frame_token_recognizes_patterns_and_numbered_files() -> None:
    """Existing pattern syntax and numbered filenames should be accepted."""
    assert pattern_has_frame_token("render.%04d.exr") is True
    assert pattern_has_frame_token("render.$F4.exr") is True
    assert pattern_has_frame_token("render.####.exr") is True
    assert pattern_has_frame_token("render.1001.exr") is True
    assert pattern_has_frame_token("render.final.exr") is False


def test_extract_frame_number_uses_trailing_digits() -> None:
    """Only the terminal filename number should be treated as the frame."""
    assert extract_frame_number(Path("shot.v003.1001.exr")) == 1001
    assert extract_frame_number(Path("shot.v003.exr")) == 3
    assert extract_frame_number(Path("shot.final.exr")) is None


def test_derive_sequence_stem_removes_pattern_tokens() -> None:
    """Pattern tokens should be stripped from generated thumbnail stems."""
    assert derive_sequence_stem("C:/show/shot/render.%04d.exr") == "render"
    assert derive_sequence_stem("render.$F4.exr") == "render"
    assert derive_sequence_stem("render.####.exr") == "render"
    assert derive_sequence_stem("render.1001.exr") == "render"


def test_build_pattern_from_path_uses_last_number_group(tmp_path: Path) -> None:
    """Numbered files should become printf-style patterns using the frame padding."""
    source = tmp_path / "shot.v003.render.1001.exr"
    source.write_text("data")

    assert build_pattern_from_path(source) == str(tmp_path / "shot.v003.render.%04d.exr")


def test_build_pattern_from_path_rejects_non_numbered_or_missing_files(tmp_path: Path) -> None:
    """Files without frame numbers should not create a sequence pattern."""
    missing = tmp_path / "shot.1001.exr"
    unnumbered = tmp_path / "shot.final.exr"
    unnumbered.write_text("data")

    assert build_pattern_from_path(missing) is None
    assert build_pattern_from_path(unnumbered) is None
