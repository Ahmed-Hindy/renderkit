"""Integration tests using real EXR sequence files."""

import tempfile
from pathlib import Path

import pytest

from renderkit.api.processor import RenderKit
from renderkit.core.config import ConversionConfigBuilder
from renderkit.core.sequence import SequenceDetector
from renderkit.processing.color_space import ColorSpacePreset


class TestRealEXRSequence:
    """Integration tests with real EXR sequence files."""

    # Real file path pattern
    REAL_SEQUENCE_PATTERN = (
        r"G:/Projects/AYON_PROJECTS/Canyon_Run/sq001/sh001/publish/render/renderCompositingMain/v001"
        r"/CanRun_sh001_renderCompositingMain_v001.%04d.exr"
    )

    def test_sequence_detection_real_files(self) -> None:
        """Test sequence detection with real EXR files."""
        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        # Verify sequence was detected
        assert sequence is not None
        assert len(sequence) > 0
        assert len(sequence.frame_numbers) > 0

        # Verify first frame exists
        first_frame = sequence.get_file_path(sequence.frame_numbers[0])
        assert first_frame.exists(), f"First frame should exist: {first_frame}"

        # Verify padding
        assert sequence.padding == 4

    def test_sequence_frame_numbers(self) -> None:
        """Test that frame numbers are correctly detected."""
        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        # Verify frame numbers are sorted
        assert sequence.frame_numbers == sorted(sequence.frame_numbers)

        # Verify frame numbers are positive
        assert all(f > 0 for f in sequence.frame_numbers)

    def test_get_file_paths(self) -> None:
        """Test getting file paths for specific frames."""
        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        # Test getting path for first frame
        first_frame_num = sequence.frame_numbers[0]
        first_path = sequence.get_file_path(first_frame_num)
        assert first_path.exists(), f"Frame {first_frame_num} should exist: {first_path}"

        # Test getting path for middle frame (if available)
        if len(sequence.frame_numbers) > 2:
            middle_frame_num = sequence.frame_numbers[len(sequence.frame_numbers) // 2]
            middle_path = sequence.get_file_path(middle_frame_num)
            assert middle_path.exists(), f"Frame {middle_frame_num} should exist: {middle_path}"

    def test_image_reader_real_files(self) -> None:
        """Test reading real EXR files."""
        from renderkit.io.image_reader import ImageReaderFactory

        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)
        first_frame_path = sequence.get_file_path(sequence.frame_numbers[0])

        # Create reader and read image
        reader = ImageReaderFactory.create_reader(first_frame_path)
        image = reader.read(first_frame_path)

        # Verify image properties
        assert image is not None
        assert len(image.shape) == 3  # Should be H, W, C
        assert image.shape[2] in [3, 4]  # RGB or RGBA
        assert image.dtype in [float, "float32", "float64"]

        # Verify resolution
        width, height = reader.get_resolution(first_frame_path)
        assert width > 0
        assert height > 0
        assert image.shape[0] == height
        assert image.shape[1] == width

    def test_color_space_conversion_real_files(self) -> None:
        """Test color space conversion with real EXR files."""
        from renderkit.io.image_reader import ImageReaderFactory
        from renderkit.processing.color_space import ColorSpaceConverter

        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)
        first_frame_path = sequence.get_file_path(sequence.frame_numbers[0])

        # Read image
        reader = ImageReaderFactory.create_reader(first_frame_path)
        image = reader.read(first_frame_path)

        # Convert color space
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)
        converted = converter.convert(image)

        # Verify conversion
        assert converted is not None
        assert converted.shape == image.shape
        assert converted.dtype == image.dtype
        # Values should be in [0, 1] range after conversion
        assert converted.min() >= 0.0
        assert converted.max() <= 1.0

    def test_full_conversion_small_range(self) -> None:
        """Test full conversion with a small frame range."""
        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        # Use only first 3 frames for quick test
        if len(sequence.frame_numbers) < 3:
            pytest.skip("Not enough frames in sequence")

        start_frame = sequence.frame_numbers[0]
        end_frame = sequence.frame_numbers[min(2, len(sequence.frame_numbers) - 1)]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_output.mp4"

            # Build configuration
            config = (
                ConversionConfigBuilder()
                .with_input_pattern(self.REAL_SEQUENCE_PATTERN)
                .with_output_path(str(output_path))
                .with_fps(24.0)
                .with_frame_range(start_frame, end_frame)
                .with_color_space_preset(ColorSpacePreset.LINEAR_TO_SRGB)
                .build()
            )

            # Convert
            processor = RenderKit()
            processor.convert_with_config(config)

            # Verify output file was created
            assert output_path.exists(), "Output video file should be created"
            assert output_path.stat().st_size > 0, "Output file should not be empty"

    def test_full_conversion_all_frames(self) -> None:
        """Test full conversion with all frames (may take longer)."""
        SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_output_all_frames.mp4"

            # Build configuration
            config = (
                ConversionConfigBuilder()
                .with_input_pattern(self.REAL_SEQUENCE_PATTERN)
                .with_output_path(str(output_path))
                .with_fps(24.0)
                .with_color_space_preset(ColorSpacePreset.LINEAR_TO_SRGB)
                .build()
            )

            # Convert
            processor = RenderKit()
            processor.convert_with_config(config)

            # Verify output file was created
            assert output_path.exists(), "Output video file should be created"
            assert output_path.stat().st_size > 0, "Output file should not be empty"

    def test_conversion_with_different_color_spaces(self) -> None:
        """Test conversion with different color space presets."""
        sequence = SequenceDetector.detect_sequence(self.REAL_SEQUENCE_PATTERN)

        # Use only first frame for quick test
        start_frame = sequence.frame_numbers[0]
        end_frame = start_frame

        color_spaces = [
            ColorSpacePreset.LINEAR_TO_SRGB,
            ColorSpacePreset.LINEAR_TO_REC709,
            ColorSpacePreset.NO_CONVERSION,
        ]

        for color_space in color_spaces:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = Path(tmpdir) / f"test_output_{color_space.name}.mp4"

                config = (
                    ConversionConfigBuilder()
                    .with_input_pattern(self.REAL_SEQUENCE_PATTERN)
                    .with_output_path(str(output_path))
                    .with_fps(24.0)
                    .with_frame_range(start_frame, end_frame)
                    .with_color_space_preset(color_space)
                    .build()
                )

                processor = RenderKit()
                processor.convert_with_config(config)

                assert output_path.exists(), f"Output should be created for {color_space.name}"
                assert output_path.stat().st_size > 0
