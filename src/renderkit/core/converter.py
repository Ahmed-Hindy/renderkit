import logging
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import OpenImageIO as oiio

from renderkit.core.config import ConversionConfig
from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import (
    ColorSpaceError,
    ConversionCancelledError,
    ImageReadError,
    SequenceDetectionError,
    VideoEncodingError,
)
from renderkit.io.image_reader import ImageReaderFactory
from renderkit.processing.burnin import BurnInProcessor
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.processing.contact_sheet import ContactSheetGenerator
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
        self.burnin_processor = BurnInProcessor()
        self.contact_sheet_generator: Optional[ContactSheetGenerator] = None
        if self.config.contact_sheet_mode and self.config.contact_sheet_config:
            self.contact_sheet_generator = ContactSheetGenerator(self.config.contact_sheet_config)

    def convert(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
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

        if self.config.contact_sheet_mode and self.contact_sheet_generator:
            # We need to calculate the actual composite size
            layers = self.reader.get_layers(first_frame_path)
            if layers:
                cols = self.config.contact_sheet_config.columns
                rows = (len(layers) + cols - 1) // cols

                thumb_w = self.config.contact_sheet_config.thumbnail_width
                aspect = height / width
                thumb_h = int(thumb_w * aspect)

                padding = self.config.contact_sheet_config.padding
                label_h = 0
                if self.config.contact_sheet_config.show_labels:
                    label_h = int(self.config.contact_sheet_config.font_size * 2.5)

                cell_w = thumb_w + (padding * 2)
                cell_h = thumb_h + (padding * 2) + label_h

                composite_w = cell_w * cols
                composite_h = cell_h * rows

                # If explicit resolution not set, use composite size
                if not self.config.width:
                    output_width = composite_w
                if not self.config.height:
                    output_height = composite_h

                logger.info(f"Targeting contact sheet resolution: {output_width}x{output_height}")

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
            self.config.quality,
        )
        self.encoder.initialize(output_width, output_height)

        # Step 8: Process frames
        logger.debug(f"Processing {len(frame_numbers)} frames...")
        scaler = ImageScaler()
        success_count = 0

        try:
            total_frames = len(frame_numbers)
            if progress_callback:
                # Use provided callback
                for i, frame_num in enumerate(frame_numbers):
                    # Check for cancellation via callback return value
                    if progress_callback(i, total_frames) is False:
                        logger.info("Conversion cancelled by progress callback")
                        raise ConversionCancelledError("Conversion cancelled by user")

                    wrote_frame = self._process_single_frame(
                        frame_num,
                        output_width,
                        output_height,
                        width,
                        height,
                        scaler,
                        input_space,
                        self.contact_sheet_generator if self.config.contact_sheet_mode else None,
                    )
                    if wrote_frame:
                        success_count += 1
                # Final progress update
                progress_callback(total_frames, total_frames)
            else:
                # Use tqdm for console
                from tqdm import tqdm

                for frame_num in tqdm(frame_numbers, desc="Converting frames"):
                    wrote_frame = self._process_single_frame(
                        frame_num,
                        output_width,
                        output_height,
                        width,
                        height,
                        scaler,
                        input_space,
                        self.contact_sheet_generator if self.config.contact_sheet_mode else None,
                    )
                    if wrote_frame:
                        success_count += 1

            if success_count == 0:
                raise VideoEncodingError(
                    "No frames were successfully written to the video file. "
                    "Check logs for reading or conversion errors."
                )

            logger.info("Conversion completed successfully.")
            logger.info(f"{success_count} frames written")

        finally:
            # Clean up
            if self.encoder:
                self.encoder.close()

    def _process_single_frame(
        self,
        frame_num: int,
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        contact_sheet_generator: Optional[ContactSheetGenerator] = None,
    ) -> bool:
        """Process a single frame.

        Args:
            frame_num: Frame number to process
            output_width: Target width
            output_height: Target height
            width: Source width
            height: Source height
            scaler: Image scaler instance
            input_space: Explicit input color space
        Returns:
            True if a frame was written successfully.
        """
        frame_path = self.sequence.get_file_path(frame_num)

        # Read image or generate contact sheet
        try:
            if contact_sheet_generator:
                buf = contact_sheet_generator.composite_layers(frame_path)
                # Composite is already in FLOAT and has correct layers (3 or 4)
                # We need to convert it to numpy for the rest of the pipeline
                image = buf.get_pixels(oiio.FLOAT)
                # Reshape if necessary (buf.spec() gives us dimensions)
                spec = buf.spec()
                image = image.reshape((spec.height, spec.width, spec.nchannels))

                # Update current width/height for scaling logic
                width, height = spec.width, spec.height
            else:
                image = self.reader.read(frame_path, layer=self.config.layer)
        except (ImageReadError, Exception) as e:
            logger.warning(f"Failed to process frame {frame_num}: {e}")
            return False

        # Convert color space
        try:
            image = self.color_converter.convert(image, input_space=input_space)
        except ColorSpaceError as e:
            logger.warning(f"Color space conversion failed for frame {frame_num}: {e}")
            return False

        if output_width != width or output_height != height:
            image = scaler.scale_image(image, output_width, output_height)

        # Apply burn-ins if configured
        if self.config.burnin_config:
            try:
                # Convert NumPy to ImageBuf
                h, w = image.shape[:2]
                channels = image.shape[2] if image.ndim == 3 else 1
                buf = oiio.ImageBuf(oiio.ImageSpec(w, h, channels, oiio.FLOAT))
                buf.set_pixels(oiio.ROI(), image.astype(np.float32))

                # Prepare metadata for tokens
                metadata = {
                    "frame": frame_num,
                    "file": frame_path.name,
                    "fps": self.config.fps,
                    "layer": self.config.layer or "RGBA",
                    "colorspace": input_space or "Unknown",
                }

                # Apply burn-ins
                buf = self.burnin_processor.apply_burnins(buf, metadata, self.config.burnin_config)

                # Convert back to NumPy
                image = buf.get_pixels(oiio.FLOAT)
                image = image.reshape((h, w, channels))
            except Exception as e:
                logger.error(f"Failed to apply burn-ins for frame {frame_num}: {e}")

        # Write frame
        try:
            self.encoder.write_frame(image)
        except VideoEncodingError as e:
            logger.error(f"Failed to write frame {frame_num}: {e}")
            raise
        return True
