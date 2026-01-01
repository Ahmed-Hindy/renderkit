"""Tests for sequence detection and parsing."""

from pathlib import Path

import pytest

from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import SequenceDetectionError


class TestSequenceDetector:
    """Tests for SequenceDetector."""

    def test_detect_percent_pattern(self, tmp_path: Path) -> None:
        """Test detection of %04d pattern."""
        # Create test files
        for i in range(1, 6):
            (tmp_path / f"render.{i:04d}.exr").touch()

        pattern = str(tmp_path / "render.%04d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 5
        assert sequence.frame_numbers == [1, 2, 3, 4, 5]
        assert sequence.padding == 4

    def test_detect_dollar_f_pattern(self, tmp_path: Path) -> None:
        """Test detection of $F4 pattern."""
        # Create test files
        for i in range(10, 15):
            (tmp_path / f"render.{i:04d}.exr").touch()

        pattern = str(tmp_path / "render.$F4.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 5
        assert sequence.frame_numbers == [10, 11, 12, 13, 14]

    def test_detect_hash_pattern(self, tmp_path: Path) -> None:
        """Test detection of #### pattern."""
        # Create test files
        for i in range(100, 105):
            (tmp_path / f"render.{i:04d}.exr").touch()

        pattern = str(tmp_path / "render.####.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 5
        assert sequence.frame_numbers == [100, 101, 102, 103, 104]

    def test_detect_numeric_pattern(self, tmp_path: Path) -> None:
        """Test detection of numeric pattern."""
        # Create test files
        for i in range(1, 6):
            (tmp_path / f"render.{i:04d}.exr").touch()

        pattern = str(tmp_path / "render.0001.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 5
        assert sequence.frame_numbers == [1, 2, 3, 4, 5]

    def test_detect_sequence_not_found(self, tmp_path: Path) -> None:
        """Test error when sequence cannot be detected."""
        pattern = str(tmp_path / "nonexistent.%04d.exr")

        with pytest.raises(SequenceDetectionError):
            SequenceDetector.detect_sequence(pattern)

    def test_get_file_path(self, tmp_path: Path) -> None:
        """Test getting file path for a frame number."""
        # Create test files
        for i in range(1, 6):
            (tmp_path / f"render.{i:04d}.exr").touch()

        pattern = str(tmp_path / "render.%04d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        file_path = sequence.get_file_path(3)
        assert file_path == tmp_path / "render.0003.exr"
        assert file_path.exists()


class TestFrameSequence:
    """Tests for FrameSequence."""

    def test_frame_sequence_creation(self, tmp_path: Path) -> None:
        """Test FrameSequence creation."""
        base_path = tmp_path
        pattern = "render.%04d.exr"
        frame_numbers = [1, 2, 3, 4, 5]
        padding = 4

        sequence = FrameSequence(base_path, pattern, frame_numbers, padding)

        assert sequence.base_path == base_path
        assert sequence.pattern == pattern
        assert sequence.frame_numbers == [1, 2, 3, 4, 5]
        assert sequence.padding == 4
        assert len(sequence) == 5

    def test_frame_sequence_repr(self, tmp_path: Path) -> None:
        """Test FrameSequence string representation."""
        sequence = FrameSequence(tmp_path, "render.%04d.exr", [1, 2, 3], 4)
        repr_str = repr(sequence)

        assert "FrameSequence" in repr_str
        assert "render.%04d.exr" in repr_str
        assert "frames=3" in repr_str
