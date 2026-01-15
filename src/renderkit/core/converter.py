import logging
from collections.abc import Callable
from pathlib import Path
from typing import Optional

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

        # Step 4: Read first frame to get dimensions and metadata (batched for efficiency)
        first_frame_path = self.sequence.get_file_path(frame_numbers[0])
        self.reader = ImageReaderFactory.create_reader(first_frame_path)

        # Get all file info in a single batched operation (reduces network I/O)
        file_info = self.reader.get_file_info(first_frame_path)
        width = file_info.width
        height = file_info.height
        detected_color_space = file_info.color_space

        if detected_color_space:
            logger.info(f"Detected input color space: {detected_color_space}")

        if self.config.contact_sheet_mode and self.config.contact_sheet_config:
            self.contact_sheet_generator = ContactSheetGenerator(
                self.config.contact_sheet_config,
                reader=self.reader,
                layers=file_info.layers,
            )

        # Step 5: Determine output resolution
        output_width = self.config.width or width
        output_height = self.config.height or height

        if self.config.contact_sheet_mode and self.contact_sheet_generator:
            # We need to calculate the actual composite size
            layers = file_info.layers
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

        # Step 8: Process frames with freeze-frame for missing frames
        logger.debug(f"Processing {len(frame_numbers)} frames...")

        # Determine the actual frame range to process
        start_frame = (
            self.config.start_frame if self.config.start_frame is not None else frame_numbers[0]
        )
        end_frame = (
            self.config.end_frame if self.config.end_frame is not None else frame_numbers[-1]
        )

        # Create a set of existing frames for fast lookup
        existing_frames = set(frame_numbers)

        # Generate complete frame range
        all_frames = list(range(start_frame, end_frame + 1))
        total_frames = len(all_frames)

        # Count missing frames for logging
        missing_count = total_frames - len([f for f in all_frames if f in existing_frames])
        if missing_count > 0:
            logger.warning(
                f"Detected {missing_count} missing frames in range {start_frame}-{end_frame}. "
                f"Will use freeze-frame (hold last valid frame) for missing frames."
            )

        scaler = ImageScaler()
        success_count = 0
        last_valid_image = None

        try:
            if progress_callback:
                # Use provided callback
                for i, frame_num in enumerate(all_frames):
                    # Check for cancellation via callback return value
                    if progress_callback(i, total_frames) is False:
                        logger.info("Conversion cancelled by progress callback")
                        raise ConversionCancelledError("Conversion cancelled by user")

                    if frame_num in existing_frames:
                        # Process actual frame
                        result = self._process_single_frame(
                            frame_num,
                            output_width,
                            output_height,
                            width,
                            height,
                            scaler,
                            input_space,
                            self.contact_sheet_generator
                            if self.config.contact_sheet_mode
                            else None,
                        )
                        if result is not None:
                            last_valid_image = result
                            success_count += 1
                    else:
                        # Missing frame - use freeze-frame
                        if last_valid_image is not None:
                            try:
                                self.encoder.write_frame(last_valid_image)
                                success_count += 1
                                if i == 0 or (i + 1) % 10 == 0:  # Log occasionally to avoid spam
                                    logger.debug(f"Frame {frame_num} missing, using freeze-frame")
                            except VideoEncodingError as e:
                                logger.error(f"Failed to write freeze-frame for {frame_num}: {e}")
                                raise
                        else:
                            logger.warning(
                                f"Frame {frame_num} missing and no previous frame available. Skipping."
                            )

                # Final progress update
                progress_callback(total_frames, total_frames)
            else:
                # Use tqdm for console
                from tqdm import tqdm

                for frame_num in tqdm(all_frames, desc="Converting frames"):
                    if frame_num in existing_frames:
                        # Process actual frame
                        result = self._process_single_frame(
                            frame_num,
                            output_width,
                            output_height,
                            width,
                            height,
                            scaler,
                            input_space,
                            self.contact_sheet_generator
                            if self.config.contact_sheet_mode
                            else None,
                        )
                        if result is not None:
                            last_valid_image = result
                            success_count += 1
                    else:
                        # Missing frame - use freeze-frame
                        if last_valid_image is not None:
                            try:
                                self.encoder.write_frame(last_valid_image)
                                success_count += 1
                            except VideoEncodingError as e:
                                logger.error(f"Failed to write freeze-frame for {frame_num}: {e}")
                                raise
                        else:
                            logger.warning(
                                f"Frame {frame_num} missing and no previous frame available. Skipping."
                            )

            if success_count == 0:
                raise VideoEncodingError(
                    "No frames were successfully written to the video file. "
                    "Check logs for reading or conversion errors."
                )

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
    ) -> Optional[np.ndarray]:
        """Process a single frame.

        Args:
            frame_num: Frame number to process
            output_width: Target width
            output_height: Target height
            width: Source width
            height: Source height
            scaler: Image scaler instance
            input_space: Explicit input color space
            contact_sheet_generator: Optional contact sheet generator

        Returns:
            Processed image as numpy array, or None if processing failed.
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
            return None

        # Convert color space
        try:
            image = self.color_converter.convert(image, input_space=input_space)
        except ColorSpaceError as e:
            logger.warning(f"Color space conversion failed for frame {frame_num}: {e}")
            return None

        if output_width != width or output_height != height:
            image = scaler.scale_image(image, output_width, output_height)

        # Apply burn-ins if configured
        if self.config.burnin_config:
            try:
                # Convert NumPy to ImageBuf
                h, w = image.shape[:2]
                channels = image.shape[2] if image.ndim == 3 else 1
                buf = oiio.ImageBuf(oiio.ImageSpec(w, h, channels, oiio.FLOAT))
                pixels = image if image.dtype == np.float32 else image.astype(np.float32)
                buf.set_pixels(oiio.ROI(), pixels)

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

        return image
