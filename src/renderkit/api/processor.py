"""Public Python API for the Render Kit."""

import logging
from typing import Optional

from renderkit.core.config import ContactSheetConfig, ConversionConfig, ConversionConfigBuilder
from renderkit.core.converter import SequenceConverter
from renderkit.core.ffmpeg_utils import ensure_ffmpeg_env
from renderkit.logging_utils import setup_logging
from renderkit.processing.color_space import ColorSpacePreset

logger = logging.getLogger("renderkit.api.processor")


class RenderKit:
    """Main public API for image and video processing."""

    def __init__(self) -> None:
        """Initialize RenderKit."""
        ensure_ffmpeg_env()
        setup_logging()

    def convert_exr_sequence_to_mp4(
        self,
        input_pattern: str,
        output_path: str,
        prefetch_workers: int = 1,
        fps: Optional[float] = None,
        color_space_preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB,
        width: Optional[int] = None,
        height: Optional[int] = None,
        codec: str = "libx264",
        quality: int = 10,
        layer: Optional[str] = None,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None,
        contact_sheet: bool = False,
        contact_sheet_config: Optional[ContactSheetConfig] = None,
    ) -> None:
        """Convert an EXR sequence to MP4 video.

        Args:
            input_pattern: Input file pattern (e.g., "render.%04d.exr")
            output_path: Output video file path
            prefetch_workers: Number of concurrent frame reads (1 disables prefetch)
            fps: Frame rate (optional, will try to auto-detect if not provided)
            color_space_preset: Color space conversion preset
            width: Output width (optional, uses source width if not provided)
            height: Output height (optional, uses source height if not provided)
            codec: Video codec (default: "libx264")
            quality: Video quality (0-10), 10 is best (default: 10)
            layer: Optional EXR layer to extract (default: None)
            start_frame: Start frame number (optional)
            end_frame: End frame number (optional)

        Example:
            >>> processor = RenderKit()
            >>> processor.convert_exr_sequence_to_mp4(
            ...     "render.%04d.exr",
            ...     "output.mp4",
            ...     fps=24.0,
            ...     quality=10,
            ...     layer="diffuse"
            ... )
        """
        config = (
            ConversionConfigBuilder()
            .with_input_pattern(input_pattern)
            .with_output_path(output_path)
            .with_prefetch_workers(prefetch_workers)
            .with_fps(fps)
            .with_color_space_preset(color_space_preset)
            .with_codec(codec)
            .with_quality(quality)
            .with_layer(layer)
        )

        if width is not None and height is not None:
            config.with_resolution(width, height)

        if start_frame is not None and end_frame is not None:
            config.with_frame_range(start_frame, end_frame)
        elif start_frame is not None:
            config.with_frame_range(start_frame, start_frame)
        elif end_frame is not None:
            config.with_frame_range(0, end_frame)

        if contact_sheet:
            config.with_contact_sheet(True, contact_sheet_config)

        conversion_config = config.build()
        converter = SequenceConverter(conversion_config)
        converter.convert()

    def convert_with_config(self, config: ConversionConfig) -> None:
        """Convert using a ConversionConfig object.

        Args:
            config: Conversion configuration object

        Example:
            >>> from renderkit.core.config import ConversionConfigBuilder
            >>> config = ConversionConfigBuilder()\\
            ...     .with_input_pattern("render.%04d.exr")\\
            ...     .with_output_path("output.mp4")\\
            ...     .with_fps(24.0)\\
            ...     .build()
            >>> processor = RenderKit()
            >>> processor.convert_with_config(config)
        """
        converter = SequenceConverter(config)
        converter.convert()
