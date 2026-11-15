"""Editorial video transcode and proxy generation utilities."""

from __future__ import annotations

import getpass
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import BurnInConfig, WatermarkConfig
from renderkit.exceptions import (
    ConfigurationError,
    ConversionCancelledError,
    VideoEncodingError,
)
from renderkit.io.video_reader import FFmpegVideoReader, VideoReadError
from renderkit.processing.burnin import BurnInProcessor
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.processing.scaler import ImageScaler
from renderkit.processing.video_encoder import VideoEncoder, get_codec_profile
from renderkit.processing.watermark import WatermarkProcessor

logger = logging.getLogger(__name__)

_EVEN_DIM_CODECS = frozenset(
    {
        "libx264",
        "h264",
        "avc1",
        "h264_nvenc",
        "libx265",
        "hevc",
        "hevc_10bit",
        "libx265_10bit",
        "hevc_nvenc",
        "libaom-av1",
        "av1",
        "av1_nvenc",
        "mpeg4",
        "mp4v",
        "xvid",
    }
)


@dataclass(frozen=True)
class VideoTranscodeConfig:
    """Configuration for transcoding a video file."""

    input_path: Path
    output_path: Path
    codec: str = "libx264"
    fps: Optional[float] = None
    quality: int = 10
    scale_width: Optional[int] = None
    scale_height: Optional[int] = None
    input_space: str = "sRGB"
    output_space: str = "sRGB"
    ocio_config_path: Optional[str] = None
    ocio_display: Optional[str] = None
    ocio_view: Optional[str] = None
    exposure: float = 0.0
    gamma: float = 1.0
    burnin_config: Optional[BurnInConfig] = None
    watermark_config: Optional[WatermarkConfig] = None

    def __post_init__(self) -> None:
        """Validate transcode configuration fields."""
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_path", Path(self.output_path))

        if self.fps is not None and self.fps <= 0:
            raise ConfigurationError("FPS must be greater than 0.")
        if not 0 <= self.quality <= 10:
            raise ConfigurationError("Quality must be between 0 and 10.")
        if self.scale_width is not None and self.scale_width <= 0:
            raise ConfigurationError("scale_width must be greater than 0.")
        if self.scale_height is not None and self.scale_height <= 0:
            raise ConfigurationError("scale_height must be greater than 0.")
        if self.gamma <= 0:
            raise ConfigurationError("Gamma must be greater than 0.")


def _make_even(dimension: int) -> int:
    """Ensure ``dimension`` is an even integer >= 2."""
    clamped = max(2, int(dimension))
    return clamped if clamped % 2 == 0 else clamped + 1


def _resolve_target_dimensions(
    source_width: int,
    source_height: int,
    scale_width: Optional[int],
    scale_height: Optional[int],
    codec: str,
) -> tuple[int, int]:
    """Compute target dimensions while preserving aspect ratio for one-sided overrides."""
    if scale_width is not None and scale_height is not None:
        target_w = scale_width
        target_h = scale_height
    elif scale_width is not None:
        target_w = scale_width
        target_h = _make_even(round(source_height * (scale_width / float(source_width))))
    elif scale_height is not None:
        target_h = scale_height
        target_w = _make_even(round(source_width * (scale_height / float(source_height))))
    else:
        target_w = source_width
        target_h = source_height

    if codec.lower() in _EVEN_DIM_CODECS:
        target_w = _make_even(target_w)
        target_h = _make_even(target_h)

    return target_w, target_h


def _create_transcode_color_converter(
    config: VideoTranscodeConfig,
) -> Optional[ColorSpaceConverter]:
    """Build the color converter for video transcoding, or ``None`` for passthrough."""
    has_ocio = any(
        value is not None
        for value in (config.ocio_config_path, config.ocio_display, config.ocio_view)
    )
    has_grade = abs(config.exposure) > 1e-6 or abs(config.gamma - 1.0) > 1e-6

    in_space = config.input_space.strip()
    out_space = config.output_space.strip()

    if has_ocio:
        use_display_view = config.ocio_display is not None or config.ocio_view is not None
        return ColorSpaceConverter(
            ColorSpacePreset.OCIO_CONVERSION,
            ocio_config_path=config.ocio_config_path,
            ocio_display=config.ocio_display,
            ocio_view=config.ocio_view,
            ocio_output_space=None if use_display_view else out_space,
            exposure=config.exposure,
            gamma=config.gamma,
        )

    if in_space.lower() == out_space.lower():
        if not has_grade:
            return None
        return ColorSpaceConverter(
            ColorSpacePreset.NO_CONVERSION,
            exposure=config.exposure,
            gamma=config.gamma,
        )

    in_lower = in_space.lower()
    out_lower = out_space.lower()
    if in_lower == "srgb" and out_lower == "linear":
        return ColorSpaceConverter(
            ColorSpacePreset.SRGB_TO_LINEAR,
            exposure=config.exposure,
            gamma=config.gamma,
        )
    if in_lower == "linear" and out_lower == "srgb":
        return ColorSpaceConverter(
            ColorSpacePreset.LINEAR_TO_SRGB,
            exposure=config.exposure,
            gamma=config.gamma,
        )
    if in_lower == "linear" and out_lower in {"rec709", "rec.709", "bt709", "bt.709"}:
        return ColorSpaceConverter(
            ColorSpacePreset.LINEAR_TO_REC709,
            exposure=config.exposure,
            gamma=config.gamma,
        )

    return ColorSpaceConverter(
        ColorSpacePreset.OCIO_CONVERSION,
        ocio_output_space=out_space,
        exposure=config.exposure,
        gamma=config.gamma,
    )


def transcode_video(
    config: VideoTranscodeConfig,
    video_reader: Optional[FFmpegVideoReader] = None,
    encoder_factory: Optional[Callable[..., Any]] = None,
    progress_callback: Optional[Callable[[int, int], Any]] = None,
) -> Path:
    """Transcode a video file with optional scaling, color grading, burn-ins, and watermark.

    Args:
        config: Transcode configuration.
        video_reader: Optional custom video reader (primarily for testing).
        encoder_factory: Optional callable constructing a :class:`VideoEncoder`-compatible
            object (primarily for testing).
        progress_callback: Optional callback ``(current, total) -> bool | None``.
            Returning ``False`` cancels the transcode.

    Returns:
        Destination video :class:`Path`.

    Raises:
        ConversionCancelledError: If ``progress_callback`` returns ``False``.
        VideoReadError: If probing fails or no frames are decoded.
        VideoEncodingError: If encoding fails.
    """
    reader = video_reader or FFmpegVideoReader()
    factory = encoder_factory or VideoEncoder

    info = reader.probe_video(config.input_path)
    target_fps = config.fps if config.fps is not None else info.fps
    target_width, target_height = _resolve_target_dimensions(
        info.width,
        info.height,
        config.scale_width,
        config.scale_height,
        config.codec,
    )

    color_converter = _create_transcode_color_converter(config)
    burnin_processor = BurnInProcessor() if config.burnin_config is not None else None
    watermark_processor = WatermarkProcessor() if config.watermark_config is not None else None

    encoder_kwargs: dict[str, Any] = {}
    if abs(info.pixel_aspect - 1.0) > 1e-4:
        encoder_kwargs["pixel_aspect"] = info.pixel_aspect

    encoder = factory(
        Path(config.output_path),
        target_fps,
        codec=config.codec,
        quality=config.quality,
        **encoder_kwargs,
    )

    frames_written = 0
    frame_range_text = (
        f"0-{info.frame_count - 1}"
        if info.frame_count is not None and info.frame_count > 0
        else "0"
    )
    date_text = datetime.now().strftime("%Y-%m-%d")
    try:
        user_text = getpass.getuser() or "unknown"
    except Exception:
        user_text = "unknown"

    try:
        encoder.initialize(target_width, target_height)
        for frame_idx, buf in reader.iter_frames(Path(config.input_path), bit_depth=16):
            spec = buf.spec()
            if spec.width != target_width or spec.height != target_height:
                buf = ImageScaler.scale_buf(buf, target_width, target_height)

            if color_converter is not None:
                buf = color_converter.convert_buf(buf, input_space=config.input_space)

            metadata: Optional[dict[str, Any]] = None
            if config.burnin_config is not None or config.watermark_config is not None:
                metadata = {
                    "frame": frame_idx,
                    "file": config.input_path.name,
                    "filename": config.input_path.name,
                    "stem": config.input_path.stem,
                    "shot": config.input_path.stem,
                    "fps": target_fps,
                    "layer": "RGB",
                    "colorspace": config.output_space,
                    "resolution": f"{target_width}x{target_height}",
                    "date": date_text,
                    "frame_range": frame_range_text,
                    "user": user_text,
                }

            if config.burnin_config is not None and burnin_processor is not None:
                assert metadata is not None
                buf = burnin_processor.apply_burnins(buf, metadata, config.burnin_config)

            if config.watermark_config is not None and watermark_processor is not None:
                buf = watermark_processor.apply_watermark(
                    buf,
                    config.watermark_config,
                    metadata=metadata,
                )

            encoder.write_frame(buf)
            frames_written += 1

            if progress_callback is not None:
                if progress_callback(frames_written, info.frame_count or 0) is False:
                    raise ConversionCancelledError("Video transcode cancelled by user.")

        if frames_written == 0:
            raise VideoReadError(f"No frames were decoded from '{config.input_path}'.")
        encoder.close()
    except Exception:
        if hasattr(encoder, "abort"):
            try:
                encoder.abort()
            except (OSError, RuntimeError, VideoEncodingError):
                logger.exception("Video encoder abort failed during transcode cleanup.")
        raise

    return Path(config.output_path)


def generate_video_proxy(
    input_path: Path,
    output_path: Optional[Path] = None,
    *,
    scale_factor: float = 0.5,
    codec: str = "libx264",
    quality: int = 10,
    video_reader: Optional[FFmpegVideoReader] = None,
    encoder_factory: Optional[Callable[..., Any]] = None,
) -> Path:
    """Generate a scaled editorial proxy video from an input video file.

    Args:
        input_path: Source video path.
        output_path: Optional destination video path. Defaults to
            ``<input_dir>/Proxy/<stem>_proxy.mp4`` (or ``.mov`` for ProRes/DNxHR).
        scale_factor: Resolution multiplier in ``(0.0, 1.0]``.
        codec: Target video codec/profile name.
        quality: Encoding quality in ``0..10``.
        video_reader: Optional custom video reader (primarily for testing).
        encoder_factory: Optional custom encoder factory (primarily for testing).

    Returns:
        Path to the generated proxy video file.

    Raises:
        ConfigurationError: If ``scale_factor`` is outside ``(0.0, 1.0]``.
    """
    if isinstance(scale_factor, bool) or not (0.0 < scale_factor <= 1.0):
        raise ConfigurationError("scale_factor must be greater than 0.0 and <= 1.0.")

    src_path = Path(input_path)
    reader = video_reader or FFmpegVideoReader()
    info = reader.probe_video(src_path)

    scaled_w = max(2, (int(round(info.width * scale_factor)) // 2) * 2)
    scaled_h = max(2, (int(round(info.height * scale_factor)) // 2) * 2)

    if output_path is None:
        ext = get_codec_profile(codec).container_ext
        resolved_output = src_path.parent / "Proxy" / f"{src_path.stem}_proxy{ext}"
    else:
        resolved_output = Path(output_path)

    config = VideoTranscodeConfig(
        input_path=src_path,
        output_path=resolved_output,
        codec=codec,
        quality=quality,
        scale_width=scaled_w,
        scale_height=scaled_h,
    )
    return transcode_video(
        config,
        video_reader=reader,
        encoder_factory=encoder_factory,
    )
