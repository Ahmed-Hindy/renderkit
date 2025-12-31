"""Main conversion orchestrator."""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from tqdm import tqdm

from image_video_processor.core.config import ConversionConfig
from image_video_processor.core.sequence import FrameSequence, SequenceDetector
from image_video_processor.exceptions import (
    ColorSpaceError,
    ImageReadError,
    SequenceDetectionError,
    VideoEncodingError,
)
from image_video_processor.io.image_reader import ImageReaderFactory
from image_video_processor.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from image_video_processor.processing.scaler import ImageScaler
from image_video_processor.processing.video_encoder import VideoEncoder

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
            fps = SequenceDetector.auto_detect_fps(self.sequence.frame_numbers)
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

        # Step 4: Read first frame to get dimensions
        first_frame_path = self.sequence.get_file_path(frame_numbers[0])
        self.reader = ImageReaderFactory.create_reader(first_frame_path)
        width, height = self.reader.get_resolution(first_frame_path)

        # Step 5: Determine output resolution
        output_width = self.config.width or width
        output_height = self.config.height or height

        # Step 6: Initialize color space converter
        self.color_converter = ColorSpaceConverter(self.config.color_space_preset)

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
                    image = self.color_converter.convert(image)
                except ColorSpaceError as e:
                    logger.warning(f"Color space conversion failed for frame {frame_num}: {e}")
                    continue

                # Scale if needed
                if output_width != width or output_height != height:
                    image = scaler.scale_image(image, output_width, output_height)

                # Write frame
                try:
                    self.encoder.write_frame(image)
                except VideoEncodingError as e:
                    logger.error(f"Failed to write frame {frame_num}: {e}")
                    raise

            logger.info("Conversion completed successfully")

        finally:
            # Clean up
            if self.encoder:
                self.encoder.close()
