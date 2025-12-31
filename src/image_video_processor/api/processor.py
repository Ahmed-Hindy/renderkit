"""Public Python API for the image video processor."""

import logging
from typing import Optional

from image_video_processor.core.config import ConversionConfig, ConversionConfigBuilder
from image_video_processor.core.converter import SequenceConverter
from image_video_processor.processing.color_space import ColorSpacePreset

logger = logging.getLogger(__name__)


class ImageVideoProcessor:
    """Main public API for image and video processing."""

    def __init__(self) -> None:
        """Initialize the processor."""
        pass

    def convert_exr_sequence_to_mp4(
        self,
        input_pattern: str,
        output_path: str,
        fps: Optional[float] = None,
        color_space_preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB,
        width: Optional[int] = None,
        height: Optional[int] = None,
        codec: str = "mp4v",
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None,
    ) -> None:
        """Convert an EXR sequence to MP4 video.

        Args:
            input_pattern: Input file pattern (e.g., "render.%04d.exr")
            output_path: Output video file path
            fps: Frame rate (optional, will try to auto-detect if not provided)
            color_space_preset: Color space conversion preset
            width: Output width (optional, uses source width if not provided)
            height: Output height (optional, uses source height if not provided)
            codec: Video codec (default: "mp4v")
            start_frame: Start frame number (optional)
            end_frame: End frame number (optional)

        Example:
            >>> processor = ImageVideoProcessor()
            >>> processor.convert_exr_sequence_to_mp4(
            ...     "render.%04d.exr",
            ...     "output.mp4",
            ...     fps=24.0
            ... )
        """
        config = (
            ConversionConfigBuilder()
            .with_input_pattern(input_pattern)
            .with_output_path(output_path)
            .with_fps(fps)
            .with_color_space_preset(color_space_preset)
            .with_codec(codec)
        )

        if width is not None and height is not None:
            config.with_resolution(width, height)

        if start_frame is not None and end_frame is not None:
            config.with_frame_range(start_frame, end_frame)
        elif start_frame is not None:
            config.with_frame_range(start_frame, start_frame)
        elif end_frame is not None:
            config.with_frame_range(0, end_frame)

        conversion_config = config.build()
        converter = SequenceConverter(conversion_config)
        converter.convert()

    def convert_with_config(self, config: ConversionConfig) -> None:
        """Convert using a ConversionConfig object.

        Args:
            config: Conversion configuration object

        Example:
            >>> from image_video_processor.core.config import ConversionConfigBuilder
            >>> config = ConversionConfigBuilder()\\
            ...     .with_input_pattern("render.%04d.exr")\\
            ...     .with_output_path("output.mp4")\\
            ...     .with_fps(24.0)\\
            ...     .build()
            >>> processor = ImageVideoProcessor()
            >>> processor.convert_with_config(config)
        """
        converter = SequenceConverter(config)
        converter.convert()
