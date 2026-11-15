import logging
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Optional

from renderkit.core.config import ContactSheetConfig, ConversionConfig
from renderkit.core.sequence import FrameSequence, SequenceDetector
from renderkit.exceptions import (
    ConversionCancelledError,
    ImageReadError,
    SequenceDetectionError,
    VideoEncodingError,
)
from renderkit.io.file_info import FileInfo
from renderkit.io.image_reader import ImageReader, ImageReaderFactory, LayerMapEntry
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.burnin import BurnInProcessor
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.processing.contact_sheet import (
    ContactSheetGenerator,
    compute_contact_sheet_label_metrics,
)
from renderkit.processing.frame_pipeline import FramePreparationOptions, prepare_frame_buffer
from renderkit.processing.scaler import ImageScaler
from renderkit.processing.video_encoder import VideoEncoder
from renderkit.processing.watermark import WatermarkProcessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FrameProcessingPlan:
    """Resolved frame range and lookup data for conversion."""

    all_frames: tuple[int, ...]
    existing_frames: frozenset[int]
    start_frame: int
    end_frame: int
    total_frames: int


class _FramePrefetcher:
    """Manage a bounded set of in-flight frame futures."""

    def __init__(
        self,
        prefetch_fn: Callable[[int], Any],
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
        self._pending: dict[int, Future[Any]] = {}
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

    def get_future(self, frame_num: int) -> Future[Any]:
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

    def __enter__(self) -> "_FramePrefetcher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
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
        self.reader: Optional[ImageReader] = None
        self.color_converter: Optional[ColorSpaceConverter] = None
        self.encoder: Optional[VideoEncoder] = None
        self.burnin_processor = BurnInProcessor()
        self.watermark_processor: Optional[WatermarkProcessor] = (
            WatermarkProcessor() if config.watermark_config is not None else None
        )
        self.contact_sheet_generator: Optional[ContactSheetGenerator] = None
        self._layer_map: Optional[dict[str, LayerMapEntry]] = None
        self._resolved_color_preset: Optional[ColorSpacePreset] = None

    def convert(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        show_progress: Optional[bool] = None,
    ) -> None:
        """Perform the conversion from image sequence to video.

        Args:
            progress_callback: Optional callback for UI or programmatic progress updates.
            show_progress: Whether to show the CLI tqdm progress bar. When omitted, progress is
                shown only when stderr is interactive.

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
        raw_pixel_aspect = getattr(file_info, "pixel_aspect", 1.0)
        pixel_aspect = (
            float(raw_pixel_aspect)
            if isinstance(raw_pixel_aspect, (int, float)) and not isinstance(raw_pixel_aspect, bool)
            else 1.0
        )
        self._initialize_encoder(output_width, output_height, pixel_aspect=pixel_aspect)

        self._process_frames(
            frame_numbers,
            output_width,
            output_height,
            width,
            height,
            input_space,
            file_info,
            progress_callback,
            show_progress,
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
        if self.sequence is None:
            raise RuntimeError("Sequence must be detected before initializing the reader.")
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
            except ImageReadError as e:
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

        cs_config = self.config.contact_sheet_config
        if self.config.contact_sheet_mode and self.contact_sheet_generator and cs_config:
            layers = file_info.layers
            if layers:
                cols = cs_config.columns
                rows = (len(layers) + cols - 1) // cols

                thumb_w, thumb_h = cs_config.resolve_layer_size(width, height)

                padding = cs_config.padding
                _, label_h = compute_contact_sheet_label_metrics(cs_config)

                cell_w = thumb_w + (padding * 2)
                cell_h = thumb_h + (padding * 2) + label_h

                output_width = cell_w * cols
                output_height = cell_h * rows

                logger.info(f"Targeting contact sheet resolution: {output_width}x{output_height}")

        return output_width, output_height

    def _effective_color_preset(self) -> ColorSpacePreset:
        """Resolve the base color preset considering explicit OCIO overrides."""
        if (
            self.config.ocio_config_path
            or self.config.ocio_display
            or self.config.ocio_view
            or self.config.ocio_output_space
        ):
            return ColorSpacePreset.OCIO_CONVERSION
        return self.config.color_space_preset

    def _create_color_converter(self, preset: ColorSpacePreset) -> ColorSpaceConverter:
        """Construct a ColorSpaceConverter with configured OCIO and grade settings."""
        return ColorSpaceConverter(
            preset,
            ocio_config_path=self.config.ocio_config_path,
            ocio_display=self.config.ocio_display,
            ocio_view=self.config.ocio_view,
            ocio_output_space=self.config.ocio_output_space,
            exposure=self.config.exposure,
            gamma=self.config.gamma,
        )

    def _configure_color_converter(self, detected_color_space: Optional[str]) -> Optional[str]:
        """Initialize color conversion and return resolved input space."""
        preset = self._effective_color_preset()
        input_space = self.config.explicit_input_color_space

        if not input_space and detected_color_space:
            if (
                preset == ColorSpacePreset.LINEAR_TO_SRGB
                or preset == ColorSpacePreset.OCIO_CONVERSION
            ):
                if "ocio_conversion" in [p.value for p in ColorSpacePreset]:
                    preset = ColorSpacePreset.OCIO_CONVERSION
                    input_space = detected_color_space

        self._resolved_color_preset = preset
        self.color_converter = self._create_color_converter(preset)
        return input_space

    def _initialize_encoder(
        self, output_width: int, output_height: int, pixel_aspect: float = 1.0
    ) -> None:
        """Initialize the video encoder for output."""
        if self.config.fps is None:
            raise ValueError("FPS must be resolved before initializing the encoder.")
        encoder_kwargs: dict[str, Any] = {}
        if abs(pixel_aspect - 1.0) > 1e-4:
            encoder_kwargs["pixel_aspect"] = pixel_aspect
        self.encoder = VideoEncoder(
            Path(self.config.output_path),
            self.config.fps,
            self.config.codec,
            self.config.bitrate,
            self.config.quality,
            **encoder_kwargs,
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
        show_progress: Optional[bool],
    ) -> None:
        """Process all frames and write them to the encoder."""
        logger.debug(f"Processing {len(frame_numbers)} frames...")
        if self.sequence is None:
            raise RuntimeError("Sequence must be detected before processing frames.")

        plan = self._build_frame_processing_plan(frame_numbers)
        self._log_missing_frame_policy(plan)

        scaler = ImageScaler()
        success_count = 0
        contact_sheet_config = (
            self.config.contact_sheet_config if self.config.contact_sheet_mode else None
        )
        contact_sheet_enabled = contact_sheet_config is not None
        if show_progress is None:
            stderr_isatty = getattr(sys.stderr, "isatty", None)
            show_progress = bool(stderr_isatty and stderr_isatty())
        pbar: Any = None

        def _tick_progress(current_index: int) -> None:
            if progress_callback:
                if progress_callback(current_index, plan.total_frames) is False:
                    logger.info("Conversion cancelled by progress callback")
                    raise ConversionCancelledError("Conversion cancelled by user")
            elif pbar is not None:
                pbar.update(1)

        try:
            if progress_callback is None and show_progress:
                from tqdm import tqdm

                pbar = tqdm(total=plan.total_frames, desc="Converting frames")

            if self.config.slate_config is not None and self.config.slate_config.enabled:
                from renderkit.processing.slate import SlateGenerator

                slate_meta: dict[str, Any] = {
                    "frame_range": f"{plan.start_frame}-{plan.end_frame}",
                    "fps": f"{self.config.fps:.2f}" if self.config.fps is not None else "",
                    "resolution": f"{output_width}x{output_height}",
                    "colorspace": input_space or self.config.color_space_preset.value,
                    "codec": self.config.codec,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "layer": self.config.layer or "beauty",
                }
                slate_buf = SlateGenerator(self.config.slate_config).generate_slate_buf(
                    output_width, output_height, slate_meta
                )
                if self.encoder is None:
                    raise VideoEncodingError("Video encoder is not initialized.")
                self.encoder.write_frame(slate_buf)

            if self._should_prefetch_frames():
                success_count = self._process_prefetched_frame_plan(
                    plan,
                    frame_numbers,
                    output_width,
                    output_height,
                    width,
                    height,
                    scaler,
                    input_space,
                    file_info,
                    contact_sheet_config if contact_sheet_enabled else None,
                    _tick_progress,
                )
            else:
                success_count = self._process_sequential_frame_plan(
                    plan,
                    output_width,
                    output_height,
                    width,
                    height,
                    scaler,
                    input_space,
                    self.contact_sheet_generator if contact_sheet_enabled else None,
                    _tick_progress,
                    file_info=file_info,
                )

            if progress_callback:
                progress_callback(plan.total_frames, plan.total_frames)

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
                if sys.exception() is None:
                    self.encoder.close()
                elif hasattr(self.encoder, "abort"):
                    try:
                        self.encoder.abort()
                    except (OSError, RuntimeError, VideoEncodingError):
                        logger.exception("Video encoder abort failed during cleanup.")
                else:
                    try:
                        self.encoder.close()
                    except VideoEncodingError:
                        logger.exception("Video encoder finalization failed during cleanup.")

    def _build_frame_processing_plan(self, frame_numbers: list[int]) -> _FrameProcessingPlan:
        """Resolve conversion frame range metadata for processing."""
        all_frames, existing_frames, start_frame, end_frame, total_frames = self._build_frame_range(
            frame_numbers
        )
        return _FrameProcessingPlan(
            all_frames=tuple(all_frames),
            existing_frames=frozenset(existing_frames),
            start_frame=start_frame,
            end_frame=end_frame,
            total_frames=total_frames,
        )

    def _log_missing_frame_policy(self, plan: _FrameProcessingPlan) -> None:
        """Log freeze-frame policy when the resolved frame range has holes."""
        missing_count = plan.total_frames - len(plan.existing_frames)
        if missing_count <= 0:
            return

        logger.warning(
            f"Detected {missing_count} missing frames in range "
            f"{plan.start_frame}-{plan.end_frame}. "
            f"Will use freeze-frame (hold last valid frame) for missing frames."
        )

    def _should_prefetch_frames(self) -> bool:
        """Return whether frame preparation should use the threaded prefetch path."""
        return max(1, self.config.prefetch_workers) > 1

    def _process_prefetched_frame_plan(
        self,
        plan: _FrameProcessingPlan,
        frame_numbers: list[int],
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        file_info: FileInfo,
        contact_sheet_config: Optional[ContactSheetConfig],
        tick_progress: Callable[[int], None],
    ) -> int:
        """Process a frame plan using worker-thread preparation and main-thread writes."""
        frame_range = f"{plan.start_frame}-{plan.end_frame}"
        prefetch_frame = self._create_prefetch_frame_fn(
            output_width,
            output_height,
            width,
            height,
            scaler,
            input_space,
            file_info,
            contact_sheet_config,
            frame_range=frame_range,
        )

        prefetch_workers = max(1, self.config.prefetch_workers)
        with _FramePrefetcher(prefetch_frame, frame_numbers, prefetch_workers) as prefetcher:
            return self._write_prefetched_frame_plan(plan, prefetcher, tick_progress)

    def _create_prefetch_frame_fn(
        self,
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        file_info: FileInfo,
        contact_sheet_config: Optional[ContactSheetConfig],
        frame_range: Optional[str] = None,
    ) -> Callable[[int], Any]:
        """Create a worker-thread frame preparation callback."""
        if self.sequence is None:
            raise RuntimeError("Sequence must be detected before processing frames.")

        sequence = self.sequence
        thread_state = threading.local()
        layers_for_cs = file_info.layers if contact_sheet_config is not None else None

        def _prefetch_frame(frame_num: int) -> Any:
            frame_path = sequence.get_file_path(frame_num)
            resources = self._get_prefetch_thread_resources(
                thread_state,
                frame_path,
                contact_sheet_config,
                layers_for_cs,
            )
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
                watermark_processor=getattr(resources, "watermark_processor", None),
                frame_range=frame_range,
                file_info=file_info,
            )

        return _prefetch_frame

    def _get_prefetch_thread_resources(
        self,
        thread_state: Any,
        frame_path: Path,
        contact_sheet_config: Optional[ContactSheetConfig],
        layers_for_cs: Optional[list[str]],
    ) -> Any:
        """Return reusable frame-processing resources for the active prefetch thread."""
        reader = getattr(thread_state, "reader", None)
        if reader is None:
            reader = ImageReaderFactory.create_reader(
                frame_path, image_cache=get_shared_image_cache()
            )
            thread_state.reader = reader

        if not hasattr(thread_state, "color_converter"):
            preset = getattr(self, "_resolved_color_preset", None) or self._effective_color_preset()
            thread_state.color_converter = self._create_color_converter(preset)

        if self.config.burnin_config and not hasattr(thread_state, "burnin_processor"):
            thread_state.burnin_processor = BurnInProcessor()

        if self.config.watermark_config is not None and not hasattr(
            thread_state, "watermark_processor"
        ):
            thread_state.watermark_processor = WatermarkProcessor()

        if contact_sheet_config is not None and not hasattr(
            thread_state, "contact_sheet_generator"
        ):
            thread_state.contact_sheet_generator = ContactSheetGenerator(
                contact_sheet_config,
                reader=reader,
                layers=layers_for_cs,
                layer_map=self._layer_map,
            )

        return thread_state

    def _write_prefetched_frame_plan(
        self,
        plan: _FrameProcessingPlan,
        prefetcher: _FramePrefetcher,
        tick_progress: Callable[[int], None],
    ) -> int:
        """Write prefetched frames and freeze-frames in presentation order."""
        success_count = 0
        last_valid_buf: Any = None
        for index, frame_num in enumerate(plan.all_frames):
            tick_progress(index)
            if frame_num in plan.existing_frames:
                future = prefetcher.get_future(frame_num)
                result = future.result()
                last_valid_buf = result
                self._write_frame_buf(frame_num, result)
                success_count += 1
            elif self._write_freeze_frame(frame_num, last_valid_buf, index):
                success_count += 1

        return success_count

    def _process_sequential_frame_plan(
        self,
        plan: _FrameProcessingPlan,
        output_width: int,
        output_height: int,
        width: int,
        height: int,
        scaler: "ImageScaler",
        input_space: Optional[str],
        contact_sheet_generator: Optional[ContactSheetGenerator],
        tick_progress: Callable[[int], None],
        file_info: Optional[FileInfo] = None,
    ) -> int:
        """Process a frame plan in frame order on the current thread."""
        success_count = 0
        last_valid_buf: Any = None
        frame_range = f"{plan.start_frame}-{plan.end_frame}"
        for index, frame_num in enumerate(plan.all_frames):
            tick_progress(index)
            if frame_num in plan.existing_frames:
                result = self._process_single_frame_buf(
                    frame_num,
                    output_width,
                    output_height,
                    width,
                    height,
                    scaler,
                    input_space,
                    contact_sheet_generator,
                    frame_range=frame_range,
                    file_info=file_info,
                )
                last_valid_buf = result
                success_count += 1
            elif self._write_freeze_frame(frame_num, last_valid_buf, index):
                success_count += 1

        return success_count

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
        watermark_processor: Optional[WatermarkProcessor] = None,
        frame_range: Optional[str] = None,
        file_info: Optional[FileInfo] = None,
        burnin_metadata: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Prepare a single frame buffer without writing it to the encoder."""
        if self.sequence is None:
            raise RuntimeError("Sequence must be detected before preparing frames.")
        frame_path = self.sequence.get_file_path(frame_num)
        resolved_metadata: Optional[dict[str, Any]] = (
            dict(burnin_metadata) if burnin_metadata is not None else None
        )
        if frame_range is not None:
            if resolved_metadata is None:
                resolved_metadata = {"frame_range": frame_range}
            elif "frame_range" not in resolved_metadata:
                resolved_metadata["frame_range"] = frame_range

        return prepare_frame_buffer(
            FramePreparationOptions(
                frame_path=frame_path,
                frame_num=frame_num,
                output_width=output_width,
                output_height=output_height,
                source_width=width,
                source_height=height,
                scaler=scaler,
                input_space=input_space,
                reader=reader,
                color_converter=color_converter,
                burnin_processor=burnin_processor,
                burnin_config=self.config.burnin_config,
                burnin_metadata=resolved_metadata,
                contact_sheet_generator=contact_sheet_generator,
                layer=self.config.layer,
                layer_map=self._layer_map,
                fps=self.config.fps,
                file_info=file_info,
                watermark_processor=watermark_processor,
                watermark_config=self.config.watermark_config,
            )
        ).buf

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

    def _write_frame_buf(self, frame_num: int, buf: Any, label: str = "frame") -> None:
        """Write an ImageBuf to the encoder with consistent error handling."""
        if self.encoder is None:
            raise VideoEncodingError("Video encoder is not initialized.")
        try:
            self.encoder.write_frame(buf)
        except VideoEncodingError:
            raise
        except (RuntimeError, TypeError, ValueError) as e:
            logger.error(f"Failed to write {label} {frame_num}: {e}")
            raise VideoEncodingError(f"Failed to write {label} {frame_num}: {e}") from e

    def _write_freeze_frame(
        self, frame_num: int, last_valid_buf: Any, index: int, log_every: int = 10
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
        frame_range: Optional[str] = None,
        file_info: Optional[FileInfo] = None,
    ) -> Any:
        """Process a single frame using ImageBuf-first operations."""
        if self.reader is None:
            raise RuntimeError("Reader must be initialized before processing frames.")
        if self.color_converter is None:
            raise RuntimeError("Color converter must be initialized before processing frames.")
        watermark_processor: Optional[WatermarkProcessor] = None
        if self.config.watermark_config is not None:
            watermark_processor = getattr(self, "watermark_processor", None)
            if watermark_processor is None:
                watermark_processor = WatermarkProcessor()
                self.watermark_processor = watermark_processor
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
            watermark_processor=watermark_processor,
            frame_range=frame_range,
            file_info=file_info,
        )

        self._write_frame_buf(frame_num, buf)

        return buf
