import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from renderkit.core.config import ConversionConfig
from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import (
    ColorSpaceError,
    ConversionCancelledError,
    ImageReadError,
    SequenceDetectionError,
    VideoEncodingError,
)
from renderkit.io.file_info import FileInfo
from renderkit.io.image_reader import ImageReader, ImageReaderFactory
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.burnin import BurnInProcessor
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.processing.contact_sheet import ContactSheetGenerator
from renderkit.processing.scaler import ImageScaler
from renderkit.processing.video_encoder import VideoEncoder

logger = logging.getLogger(__name__)


class _FramePrefetcher:
    """Manage a bounded set of in-flight frame futures."""

    def __init__(
        self,
        prefetch_fn: Callable[[int], object],
        frames: list[int],
        max_workers: int,
        thread_name_prefix: str = "renderkit-prefetch",
    ) -> None:
        self._prefetch_fn = prefetch_fn
        self._frames = frames
        self._max_pending = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._pending: dict[int, object] = {}
        self._next_index = 0
        self._prime()

    def _submit_next(self) -> bool:
        if self._next_index >= len(self._frames):
            return False
        frame_num = self._frames[self._next_index]
        self._next_index += 1
        self._pending[frame_num] = self._executor.submit(self._prefetch_fn, frame_num)
        return True

    def _prime(self) -> None:
        while len(self._pending) < self._max_pending and self._submit_next():
            pass

    def get_future(self, frame_num: int):
        future = self._pending.pop(frame_num, None)
        if future is None:
            future = self._executor.submit(self._prefetch_fn, frame_num)
        self._prime()
        return future

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            self._executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


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
        self._layer_map = None

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

        self.sequence = self._detect_sequence()
        self._resolve_fps(self.sequence)

        frame_numbers = self._filter_frame_numbers(self.sequence.frame_numbers)
        if not frame_numbers:
            raise ValueError("No frames found in specified range")

        file_info, width, height, detected_color_space = self._initialize_reader_and_metadata(
            frame_numbers[0]
        )
        output_width, output_height = self._resolve_output_resolution(file_info, width, height)
        input_space = self._configure_color_converter(detected_color_space)
        self._initialize_encoder(output_width, output_height)

        self._process_frames(
            frame_numbers,
            output_width,
            output_height,
            width,
            height,
            input_space,
            file_info,
            progress_callback,
        )

    def _detect_sequence(self) -> FrameSequence:
        """Detect and return the frame sequence."""
        try:
            sequence = SequenceDetector.detect_sequence(self.config.input_pattern)
            logger.info(f"Detected sequence: {sequence}")
            return sequence
        except SequenceDetectionError as e:
            logger.error(f"Sequence detection failed: {e}")
            raise

    def _resolve_fps(self, sequence: FrameSequence) -> None:
        """Resolve FPS from metadata when not explicitly provided."""
        if self.config.fps is not None:
            return

        fps = None
        if sequence.frame_numbers:
            sample_path = sequence.get_file_path(sequence.frame_numbers[0])
            fps = SequenceDetector.auto_detect_fps(sequence.frame_numbers, sample_path=sample_path)

        if fps is None:
            raise ValueError(
                "FPS is required but could not be auto-detected. "
                "Please provide --fps option or set fps in configuration."
            )
        self.config.fps = fps
        logger.info(f"Auto-detected FPS: {fps}")

    def _filter_frame_numbers(self, frame_numbers: list[int]) -> list[int]:
        """Apply frame range limits to a list of frames."""
        if self.config.start_frame is not None:
            frame_numbers = [f for f in frame_numbers if f >= self.config.start_frame]
        if self.config.end_frame is not None:
            frame_numbers = [f for f in frame_numbers if f <= self.config.end_frame]
        return frame_numbers

    def _initialize_reader_and_metadata(
        self, first_frame_num: int
    ) -> tuple[FileInfo, int, int, Optional[str]]:
        """Initialize reader, metadata caches, and contact sheet generator."""
        first_frame_path = self.sequence.get_file_path(first_frame_num)
        self.reader = ImageReaderFactory.create_reader(
            first_frame_path, image_cache=get_shared_image_cache()
        )

        file_info = self.reader.get_file_info(first_frame_path)
        width = file_info.width
        height = file_info.height
        detected_color_space = file_info.color_space

        if detected_color_space:
            logger.info(f"Detected input color space: {detected_color_space}")

        if hasattr(self.reader, "get_layer_map"):
            try:
                self._layer_map = self.reader.get_layer_map(first_frame_path)
            except Exception as e:
                logger.debug(f"Failed to build layer map for {first_frame_path}: {e}")

        if self.config.contact_sheet_mode and self.config.contact_sheet_config:
            cs_config = self.config.contact_sheet_config
            if cs_config.layer_width is None and cs_config.layer_height is None:
                if self.config.width is not None or self.config.height is not None:
                    cs_config.layer_width = self.config.width
                    cs_config.layer_height = self.config.height

            self.contact_sheet_generator = ContactSheetGenerator(
                cs_config,
                reader=self.reader,
                layers=file_info.layers,
                layer_map=self._layer_map,
            )

        return file_info, width, height, detected_color_space

    def _resolve_output_resolution(
        self, file_info: FileInfo, width: int, height: int
    ) -> tuple[int, int]:
        """Resolve output dimensions including contact sheet overrides."""
        output_width = self.config.width or width
        output_height = self.config.height or height

        if self.config.contact_sheet_mode and self.contact_sheet_generator:
            layers = file_info.layers
            if layers:
                cols = self.config.contact_sheet_config.columns
                rows = (len(layers) + cols - 1) // cols

                thumb_w, thumb_h = self.config.contact_sheet_config.resolve_layer_size(
                    width, height
                )

                padding = self.config.contact_sheet_config.padding
                label_h = 0
                if self.config.contact_sheet_config.show_labels:
                    label_h = int(self.config.contact_sheet_config.font_size * 2.5)

                cell_w = thumb_w + (padding * 2)
                cell_h = thumb_h + (padding * 2) + label_h

                output_width = cell_w * cols
                output_height = cell_h * rows

                logger.info(f"Targeting contact sheet resolution: {output_width}x{output_height}")

        return output_width, output_height

    def _configure_color_converter(self, detected_color_space: Optional[str]) -> Optional[str]:
        """Initialize color conversion and return resolved input space."""
        preset = self.config.color_space_preset
        input_space = self.config.explicit_input_color_space

        if not input_space and detected_color_space:
            if (
                preset == ColorSpacePreset.LINEAR_TO_SRGB
                or preset == ColorSpacePreset.OCIO_CONVERSION
            ):
                if "ocio_conversion" in [p.value for p in ColorSpacePreset]:
                    preset = ColorSpacePreset.OCIO_CONVERSION
                    input_space = detected_color_space

        self.color_converter = ColorSpaceConverter(preset)
        return input_space

    def _initialize_encoder(self, output_width: int, output_height: int) -> None:
        """Initialize the video encoder for output."""
        self.encoder = VideoEncoder(
            Path(self.config.output_path),
            self.config.fps,
            self.config.codec,
            self.config.bitrate,
            self.config.quality,
        )
        self.encoder.initialize(output_width, output_height)

    def _process_frames(
        self,
        frame_numbers: list[int],
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        input_space: Optional[str],
        file_info: FileInfo,
        progress_callback: Optional[Callable[[int, int], None]],
    ) -> None:
        """Process all frames and write them to the encoder."""
        logger.debug(f"Processing {len(frame_numbers)} frames...")

        all_frames, existing_frames, start_frame, end_frame, total_frames = self._build_frame_range(
            frame_numbers
        )

        missing_count = total_frames - len(existing_frames)
        if missing_count > 0:
            logger.warning(
                f"Detected {missing_count} missing frames in range {start_frame}-{end_frame}. "
                f"Will use freeze-frame (hold last valid frame) for missing frames."
            )

        scaler = ImageScaler()
        success_count = 0
        last_valid_buf = None
        prefetch_workers = max(1, self.config.prefetch_workers)
        contact_sheet_enabled = (
            self.config.contact_sheet_mode and self.config.contact_sheet_config is not None
        )
        pbar = None

        def _tick_progress(current_index: int) -> None:
            if progress_callback:
                if progress_callback(current_index, total_frames) is False:
                    logger.info("Conversion cancelled by progress callback")
                    raise ConversionCancelledError("Conversion cancelled by user")
            elif pbar is not None:
                pbar.update(1)

        try:
            if progress_callback is None:
                from tqdm import tqdm

                pbar = tqdm(total=total_frames, desc="Converting frames")

            if prefetch_workers > 1:
                thread_state = threading.local()
                layers_for_cs = file_info.layers if contact_sheet_enabled else None

                def _get_thread_resources(frame_path: Path):
                    reader = getattr(thread_state, "reader", None)
                    if reader is None:
                        reader = ImageReaderFactory.create_reader(
                            frame_path, image_cache=get_shared_image_cache()
                        )
                        thread_state.reader = reader

                    if not hasattr(thread_state, "color_converter"):
                        thread_state.color_converter = ColorSpaceConverter(
                            self.config.color_space_preset
                        )

                    if self.config.burnin_config and not hasattr(thread_state, "burnin_processor"):
                        thread_state.burnin_processor = BurnInProcessor()

                    if contact_sheet_enabled and not hasattr(
                        thread_state, "contact_sheet_generator"
                    ):
                        thread_state.contact_sheet_generator = ContactSheetGenerator(
                            self.config.contact_sheet_config,
                            reader=reader,
                            layers=layers_for_cs,
                            layer_map=self._layer_map,
                        )

                    return thread_state

                def _prefetch_frame(frame_num: int):
                    frame_path = self.sequence.get_file_path(frame_num)
                    resources = _get_thread_resources(frame_path)
                    return self._prepare_frame_buf(
                        frame_num,
                        output_width,
                        output_height,
                        width,
                        height,
                        scaler,
                        input_space,
                        resources.reader,
                        resources.color_converter,
                        getattr(resources, "burnin_processor", None),
                        contact_sheet_generator=getattr(resources, "contact_sheet_generator", None),
                    )

                with _FramePrefetcher(
                    _prefetch_frame, frame_numbers, prefetch_workers
                ) as prefetcher:
                    for i, frame_num in enumerate(all_frames):
                        _tick_progress(i)
                        if frame_num in existing_frames:
                            future = prefetcher.get_future(frame_num)
                            try:
                                result = future.result()
                            except Exception as e:
                                logger.warning(f"Failed to process frame {frame_num}: {e}")
                                result = None

                            if result is not None:
                                last_valid_buf = result
                                self._write_frame_buf(frame_num, result)
                                success_count += 1
                        else:
                            if self._write_freeze_frame(frame_num, last_valid_buf, i):
                                success_count += 1
            else:
                for i, frame_num in enumerate(all_frames):
                    _tick_progress(i)
                    if frame_num in existing_frames:
                        result = self._process_single_frame_buf(
                            frame_num,
                            output_width,
                            output_height,
                            width,
                            height,
                            scaler,
                            input_space,
                            self.contact_sheet_generator if contact_sheet_enabled else None,
                        )
                        if result is not None:
                            last_valid_buf = result
                            success_count += 1
                    else:
                        if self._write_freeze_frame(frame_num, last_valid_buf, i):
                            success_count += 1

            if progress_callback:
                progress_callback(total_frames, total_frames)

            if success_count == 0:
                raise VideoEncodingError(
                    "No frames were successfully written to the video file. "
                    "Check logs for reading or conversion errors."
                )

            logger.info(f"{success_count} frames written")

        finally:
            if pbar is not None:
                pbar.close()
            if self.encoder:
                self.encoder.close()

    def _prepare_frame_buf(
        self,
        frame_num: int,
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        reader: "ImageReader",
        color_converter: ColorSpaceConverter,
        burnin_processor: Optional[BurnInProcessor],
        contact_sheet_generator: Optional[ContactSheetGenerator] = None,
    ):
        """Prepare a single frame buffer without writing it to the encoder."""
        frame_path = self.sequence.get_file_path(frame_num)

        try:
            if contact_sheet_generator:
                buf = contact_sheet_generator.composite_layers(frame_path)
                spec = buf.spec()
                width, height = spec.width, spec.height
            else:
                buf = reader.read_imagebuf(
                    frame_path,
                    layer=self.config.layer,
                    layer_map=self._layer_map,
                )
        except (ImageReadError, Exception) as e:
            logger.warning(f"Failed to process frame {frame_num}: {e}")
            return None

        try:
            buf = color_converter.convert_buf(buf, input_space=input_space)
        except ColorSpaceError as e:
            logger.warning(f"Color space conversion failed for frame {frame_num}: {e}")
            return None

        if output_width != width or output_height != height:
            buf = scaler.scale_buf(buf, output_width, output_height)

        if self.config.burnin_config and burnin_processor:
            try:
                metadata = {
                    "frame": frame_num,
                    "file": frame_path.name,
                    "fps": self.config.fps,
                    "layer": self.config.layer or "RGBA",
                    "colorspace": input_space or "Unknown",
                }
                buf = burnin_processor.apply_burnins(
                    buf,
                    metadata,
                    self.config.burnin_config,
                )
            except Exception as e:
                logger.error(f"Failed to apply burn-ins for frame {frame_num}: {e}")

        return buf

    def _build_frame_range(
        self, frame_numbers: list[int]
    ) -> tuple[list[int], set[int], int, int, int]:
        """Build the full frame range and lookup set."""
        start_frame = (
            self.config.start_frame if self.config.start_frame is not None else frame_numbers[0]
        )
        end_frame = (
            self.config.end_frame if self.config.end_frame is not None else frame_numbers[-1]
        )
        existing_frames = set(frame_numbers)
        all_frames = list(range(start_frame, end_frame + 1))
        total_frames = len(all_frames)
        return all_frames, existing_frames, start_frame, end_frame, total_frames

    def _write_frame_buf(self, frame_num: int, buf, label: str = "frame") -> None:
        """Write an ImageBuf to the encoder with consistent error handling."""
        try:
            self.encoder.write_frame(buf)
        except VideoEncodingError:
            raise
        except Exception as e:
            logger.error(f"Failed to write {label} {frame_num}: {e}")
            raise VideoEncodingError(f"Failed to write {label} {frame_num}: {e}") from e

    def _write_freeze_frame(
        self, frame_num: int, last_valid_buf, index: int, log_every: int = 10
    ) -> bool:
        """Write a freeze-frame if available, otherwise log and skip."""
        if last_valid_buf is None:
            logger.warning(f"Frame {frame_num} missing and no previous frame available. Skipping.")
            return False

        self._write_frame_buf(frame_num, last_valid_buf, label="freeze-frame")
        if index == 0 or (index + 1) % log_every == 0:
            logger.debug(f"Frame {frame_num} missing, using freeze-frame")
        return True

    def _process_single_frame_buf(
        self,
        frame_num: int,
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        contact_sheet_generator: Optional[ContactSheetGenerator] = None,
    ):
        """Process a single frame using ImageBuf-first operations."""
        buf = self._prepare_frame_buf(
            frame_num,
            output_width,
            output_height,
            width,
            height,
            scaler,
            input_space,
            self.reader,
            self.color_converter,
            self.burnin_processor,
            contact_sheet_generator=contact_sheet_generator,
        )
        if buf is None:
            return None

        self._write_frame_buf(frame_num, buf)

        return buf
