"""Tests for converter (integration tests would require actual EXR files)."""

import pytest

from image_video_processor.core.config import ConversionConfig, ConversionConfigBuilder
from image_video_processor.exceptions import ConfigurationError


class TestConversionConfig:
    """Tests for ConversionConfig."""

    def test_config_creation(self) -> None:
        """Test creating a valid configuration."""
        config = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path="output.mp4",
            fps=24.0,
        )

        assert config.input_pattern == "render.%04d.exr"
        assert config.output_path == "output.mp4"
        assert config.fps == 24.0

    def test_config_validation_fps(self) -> None:
        """Test FPS validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                fps=-1.0,
            )

    def test_config_validation_frame_range(self) -> None:
        """Test frame range validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                start_frame=10,
                end_frame=5,  # Invalid: start > end
            )


class TestConversionConfigBuilder:
    """Tests for ConversionConfigBuilder."""

    def test_builder_pattern(self) -> None:
        """Test building configuration with builder pattern."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_fps(24.0)
            .build()
        )

        assert config.input_pattern == "render.%04d.exr"
        assert config.output_path == "output.mp4"
        assert config.fps == 24.0

    def test_builder_missing_required(self) -> None:
        """Test builder error when required fields are missing."""
        with pytest.raises(ConfigurationError):
            ConversionConfigBuilder().with_output_path("output.mp4").build()

        with pytest.raises(ConfigurationError):
            ConversionConfigBuilder().with_input_pattern("render.%04d.exr").build()

    def test_builder_with_resolution(self) -> None:
        """Test builder with resolution."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_resolution(1920, 1080)
            .build()
        )

        assert config.width == 1920
        assert config.height == 1080

    def test_builder_with_frame_range(self) -> None:
        """Test builder with frame range."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_frame_range(100, 200)
            .build()
        )

        assert config.start_frame == 100
        assert config.end_frame == 200

