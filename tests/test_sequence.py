"""Tests for sequence detection and parsing."""

import logging
from pathlib import Path

import pytest

from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import ImageReadError, SequenceDetectionError


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

    def test_detect_percent_pattern_with_three_digit_padding(self, tmp_path: Path) -> None:
        """Test detection and resolution of %03d pattern."""
        (tmp_path / "shot.007.exr").touch()

        pattern = str(tmp_path / "shot.%03d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 1
        assert sequence.frame_numbers == [7]
        assert sequence.padding == 3
        assert sequence.get_file_path(7) == tmp_path / "shot.007.exr"

    def test_detect_percent_pattern_with_five_digit_padding(self, tmp_path: Path) -> None:
        """Test detection and resolution of %05d pattern."""
        for i in range(1, 4):
            (tmp_path / f"shot.{i:05d}.exr").touch()

        pattern = str(tmp_path / "shot.%05d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert len(sequence) == 3
        assert sequence.frame_numbers == [1, 2, 3]
        assert sequence.padding == 5
        assert sequence.get_file_path(2) == tmp_path / "shot.00002.exr"

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

    def test_detect_numeric_pattern_uses_varying_digits_after_version(self, tmp_path: Path) -> None:
        """Test numeric detection uses frame digits, not version digits."""
        for i in range(1, 4):
            (tmp_path / f"shot_v001.{i:04d}.exr").touch()

        pattern = str(tmp_path / "shot_v001.0001.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.pattern == "shot_v001.%04d.exr"
        assert sequence.frame_numbers == [1, 2, 3]
        assert sequence.get_file_path(3) == tmp_path / "shot_v001.0003.exr"

    def test_detect_numeric_pattern_ignores_fixed_numeric_suffix(self, tmp_path: Path) -> None:
        """Test numeric detection ignores later fixed numeric tags."""
        for i in range(1, 4):
            (tmp_path / f"render.{i:04d}.layer1.exr").touch()

        pattern = str(tmp_path / "render.0001.layer1.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.pattern == "render.%04d.layer1.exr"
        assert sequence.frame_numbers == [1, 2, 3]
        assert sequence.get_file_path(3) == tmp_path / "render.0003.layer1.exr"

    def test_detect_numeric_pattern_ignores_more_common_suffix_digits(self, tmp_path: Path) -> None:
        """Test numeric detection does not prefer non-frame suffix variants."""
        for i in range(1, 3):
            (tmp_path / f"render.{i:04d}.layer1.exr").touch()
        for i in range(2, 8):
            (tmp_path / f"render.0001.layer{i}.exr").touch()

        pattern = str(tmp_path / "render.0001.layer1.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.pattern == "render.%04d.layer1.exr"
        assert sequence.frame_numbers == [1, 2]

    def test_detect_numeric_pattern_ignores_version_variants(self, tmp_path: Path) -> None:
        """Test numeric detection does not treat version digits as frames."""
        for i in range(1, 6):
            (tmp_path / f"shot001_v{i:03d}.0001.exr").touch()

        pattern = str(tmp_path / "shot001_v001.0001.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.pattern == "shot001_v001.%04d.exr"
        assert sequence.frame_numbers == [1]

    def test_detect_numeric_pattern_requires_three_to_five_digits(self, tmp_path: Path) -> None:
        """Test direct numeric detection ignores oversized numeric runs."""
        (tmp_path / "shot.000001.exr").touch()

        pattern = str(tmp_path / "shot.000001.exr")

        with pytest.raises(SequenceDetectionError):
            SequenceDetector.detect_sequence(pattern)

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

    def test_get_file_path_resolves_multi_frame_percent_pattern(self, tmp_path: Path) -> None:
        """Test resolving each frame in a %03d sequence."""
        for i in range(1, 4):
            (tmp_path / f"render.{i:03d}.exr").touch()

        pattern = str(tmp_path / "render.%03d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        paths = [sequence.get_file_path(frame) for frame in sequence.frame_numbers]
        assert paths == [
            tmp_path / "render.001.exr",
            tmp_path / "render.002.exr",
            tmp_path / "render.003.exr",
        ]
        assert all(path.exists() for path in paths)

    def test_detect_percent_pattern_uses_exact_filename_match(self, tmp_path: Path) -> None:
        """Test sequence detection excludes partial filename matches."""
        (tmp_path / "render.0001.exr").touch()
        (tmp_path / "render.0001.exr.tmp").touch()
        (tmp_path / "renderx0002.exr").touch()

        pattern = str(tmp_path / "render.%04d.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.frame_numbers == [1]

    def test_numeric_pattern_get_file_path_uses_detected_padding(self, tmp_path: Path) -> None:
        """Test numeric sequence detection stores a reusable pattern."""
        for i in range(1, 4):
            (tmp_path / f"shot.{i:05d}.exr").touch()

        pattern = str(tmp_path / "shot.00001.exr")
        sequence = SequenceDetector.detect_sequence(pattern)

        assert sequence.pattern == "shot.%05d.exr"
        assert sequence.get_file_path(3) == tmp_path / "shot.00003.exr"

    def test_auto_detect_fps_logs_metadata_read_failures(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test FPS metadata read failures do not disappear silently."""
        sample_path = tmp_path / "render.0001.exr"
        sample_path.touch()

        class FailingReader:
            def get_metadata_fps(self, path: Path) -> float:
                raise ImageReadError("metadata read failed")

        monkeypatch.setattr("renderkit.io.oiio_cache.get_shared_image_cache", lambda: object())
        monkeypatch.setattr(
            "renderkit.io.image_reader.ImageReaderFactory.create_reader",
            lambda path, image_cache=None: FailingReader(),
        )

        with caplog.at_level(logging.WARNING, logger="renderkit.core.sequence"):
            fps = SequenceDetector.auto_detect_fps([1], default_fps=24.0, sample_path=sample_path)

        assert fps == pytest.approx(24.0)
        assert "FPS metadata detection failed" in caplog.text

    def test_auto_detect_fps_propagates_unexpected_metadata_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test unexpected reader bugs are not hidden as missing FPS metadata."""
        sample_path = tmp_path / "render.0001.exr"
        sample_path.touch()

        class BrokenReader:
            def get_metadata_fps(self, path: Path) -> float:
                raise RuntimeError("reader API drift")

        monkeypatch.setattr("renderkit.io.oiio_cache.get_shared_image_cache", lambda: object())
        monkeypatch.setattr(
            "renderkit.io.image_reader.ImageReaderFactory.create_reader",
            lambda path, image_cache=None: BrokenReader(),
        )

        with pytest.raises(RuntimeError, match="reader API drift"):
            SequenceDetector.auto_detect_fps([1], default_fps=24.0, sample_path=sample_path)


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
