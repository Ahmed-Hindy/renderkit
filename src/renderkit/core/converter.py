"""Main conversion orchestrator."""

import logging
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from renderkit.core.config import ConversionConfig
from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import (
    ColorSpaceError,
    ImageReadError,
    SequenceDetectionError,
    VideoEncodingError,
)
from renderkit.io.image_reader import ImageReaderFactory
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.processing.scaler import ImageScaler
from renderkit.processing.video_encoder import VideoEncoder

logger = logging.getLogger(__name__)


class SequenceConverter:
    """Orchestrates the conversion of image sequences to video."""

    def __init__(self, config: ConversionConfig) -> None:
        """Initialize the converter.

        Args:
            config: Conversion configuration
        """
        self.config = config
        self.sequence: Optional[FrameSequence] = None
        self.reader = None
        self.color_converter: Optional[ColorSpaceConverter] = None
        self.encoder: Optional[VideoEncoder] = None

    def convert(self) -> None:
        """Perform the conversion from image sequence to video.

        Raises:
            SequenceDetectionError: If sequence cannot be detected
            ImageReadError: If images cannot be read
            VideoEncodingError: If video encoding fails
        """
        logger.info(
            f"Starting conversion: {self.config.input_pattern} -> {self.config.output_path}"
        )

        # Step 1: Detect sequence
        try:
            self.sequence = SequenceDetector.detect_sequence(self.config.input_pattern)
            logger.info(f"Detected sequence: {self.sequence}")
        except SequenceDetectionError as e:
            logger.error(f"Sequence detection failed: {e}")
            raise

        # Step 2: Auto-detect FPS if not provided
        if self.config.fps is None:
            # Use first frame as sample for metadata detection
            fps = None
            if self.sequence.frame_numbers:
                sample_path = self.sequence.get_file_path(self.sequence.frame_numbers[0])
                fps = SequenceDetector.auto_detect_fps(
                    self.sequence.frame_numbers, sample_path=sample_path
                )

            if fps is None:
                raise ValueError(
                    "FPS is required but could not be auto-detected. "
                    "Please provide --fps option or set fps in configuration."
                )
            self.config.fps = fps
            logger.info(f"Auto-detected FPS: {fps}")

        # Step 3: Filter frame range if specified
        frame_numbers = self.sequence.frame_numbers
        if self.config.start_frame is not None:
            frame_numbers = [f for f in frame_numbers if f >= self.config.start_frame]
        if self.config.end_frame is not None:
            frame_numbers = [f for f in frame_numbers if f <= self.config.end_frame]

        if not frame_numbers:
            raise ValueError("No frames found in specified range")

        # Step 4: Read first frame to get dimensions and metadata
        first_frame_path = self.sequence.get_file_path(frame_numbers[0])
        self.reader = ImageReaderFactory.create_reader(first_frame_path)
        width, height = self.reader.get_resolution(first_frame_path)

        # Detect input color space
        detected_color_space = self.reader.get_metadata_color_space(first_frame_path)
        if detected_color_space:
            logger.info(f"Detected input color space: {detected_color_space}")

        # Step 5: Determine output resolution
        output_width = self.config.width or width
        output_height = self.config.height or height

        # Step 6: Initialize color space converter
        preset = self.config.color_space_preset
        input_space = self.config.explicit_input_color_space

        # If no explicit input space set, but we detected one, use it if we are in a flexible mode or OCIO mode
        if not input_space and detected_color_space:
            # Check if we should upgrade to OCIO
            if (
                preset == ColorSpacePreset.LINEAR_TO_SRGB
                or preset == ColorSpacePreset.OCIO_CONVERSION
            ):
                # If we found metadata, prefer OCIO if available
                if "ocio_conversion" in [p.value for p in ColorSpacePreset]:
                    preset = ColorSpacePreset.OCIO_CONVERSION
                    input_space = detected_color_space

        self.color_converter = ColorSpaceConverter(preset)

        # Step 7: Initialize video encoder
        self.encoder = VideoEncoder(
            Path(self.config.output_path),
            self.config.fps,
            self.config.codec,
            self.config.bitrate,
        )
        self.encoder.initialize(output_width, output_height)

        # Step 8: Process frames
        logger.info(f"Processing {len(frame_numbers)} frames...")
        scaler = ImageScaler()
        success_count = 0

        try:
            for frame_num in tqdm(frame_numbers, desc="Converting frames"):
                frame_path = self.sequence.get_file_path(frame_num)

                # Read image
                try:
                    image = self.reader.read(frame_path)
                except ImageReadError as e:
                    logger.warning(f"Failed to read frame {frame_num}: {e}")
                    continue

                # Convert color space
                try:
                    image = self.color_converter.convert(image, input_space=input_space)
                except ColorSpaceError as e:
                    logger.warning(f"Color space conversion failed for frame {frame_num}: {e}")
                    continue

                # Scale if needed
                if output_width != width or output_height != height:
                    image = scaler.scale_image(image, output_width, output_height)

                # Write frame
                try:
                    self.encoder.write_frame(image)
                    success_count += 1
                except VideoEncodingError as e:
                    logger.error(f"Failed to write frame {frame_num}: {e}")
                    raise

            if success_count == 0:
                raise VideoEncodingError(
                    "No frames were successfully written to the video file. "
                    "Check logs for reading or conversion errors."
                )

            logger.info(f"Conversion completed successfully: {success_count} frames written")

        finally:
            # Clean up
            if self.encoder:
                self.encoder.close()
