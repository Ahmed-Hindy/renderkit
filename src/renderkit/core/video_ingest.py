"""Video-to-EXR plate ingest utilities."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit.exceptions import ConfigurationError, ConversionCancelledError, RenderKitError
from renderkit.io.oiio_utils import require_oiio
from renderkit.io.video_reader import FFmpegVideoReader, VideoReadError
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset

logger = logging.getLogger(__name__)

VALID_EXR_COMPRESSIONS: tuple[str, ...] = (
    "none",
    "rle",
    "zip",
    "zips",
    "piz",
    "pxr24",
    "b44",
    "b44a",
    "dwaa",
    "dwab",
)

_PRINTF_FRAME_RE = re.compile(r"(?<!%)%(?:0?(\d+))?d")
_HASH_FRAME_RE = re.compile(r"#+")


class VideoIngestError(RenderKitError, RuntimeError):
    """Raised when writing ingested EXR plates fails."""


@dataclass(frozen=True)
class VideoToExrConfig:
    """Configuration for ingesting a video file into an EXR frame sequence."""

    input_path: Path
    output_pattern: str
    start_frame: int = 1001
    source_start_frame: Optional[int] = None
    source_end_frame: Optional[int] = None
    compression: str = "dwaa"
    half_float: bool = True
    input_space: str = "sRGB"
    output_space: str = "Linear"
    ocio_config_path: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate video-to-EXR configuration fields."""
        object.__setattr__(self, "input_path", Path(self.input_path))
        normalized_compression = self.compression.lower()
        object.__setattr__(self, "compression", normalized_compression)

        if not self.output_pattern or not self.output_pattern.strip():
            raise ConfigurationError("Output pattern must be a non-empty string.")
        if normalized_compression not in VALID_EXR_COMPRESSIONS:
            raise ConfigurationError(
                f"Invalid EXR compression '{self.compression}'. "
                f"Must be one of {VALID_EXR_COMPRESSIONS}."
            )
        if self.source_start_frame is not None and self.source_start_frame < 0:
            raise ConfigurationError("source_start_frame must be >= 0.")
        if self.source_end_frame is not None and self.source_end_frame < 0:
            raise ConfigurationError("source_end_frame must be >= 0.")
        if (
            self.source_start_frame is not None
            and self.source_end_frame is not None
            and self.source_start_frame > self.source_end_frame
        ):
            raise ConfigurationError("source_start_frame must be <= source_end_frame.")


def format_sequence_frame_path(output_pattern: str, frame_number: int) -> Path:
    """Format a frame sequence pattern containing ``%0Nd``/``%d`` or ``#`` tokens.

    Args:
        output_pattern: Sequence path pattern (e.g. ``plate.%04d.exr`` or ``plate.####.exr``).
        frame_number: Frame number to substitute into the pattern.

    Returns:
        Resolved :class:`Path` for ``frame_number``.

    Raises:
        ValueError: If ``output_pattern`` does not contain a supported frame token.
    """
    if _PRINTF_FRAME_RE.search(output_pattern):

        def _replace_printf(match: re.Match[str]) -> str:
            width_str = match.group(1)
            if width_str:
                return f"{frame_number:0{int(width_str)}d}"
            return str(frame_number)

        formatted = _PRINTF_FRAME_RE.sub(_replace_printf, output_pattern).replace("%%", "%")
        return Path(formatted)

    pattern_path = Path(output_pattern)
    filename = pattern_path.name
    if _HASH_FRAME_RE.search(filename):

        def _replace_hashes(match: re.Match[str]) -> str:
            width = len(match.group(0))
            return f"{frame_number:0{width}d}"

        formatted_name = _HASH_FRAME_RE.sub(_replace_hashes, filename)
        return pattern_path.with_name(formatted_name)

    raise ValueError(
        f"Output pattern '{output_pattern}' does not contain a frame token (%0Nd, %d, or #)."
    )


def _build_partial_exr_path(target_path: Path) -> Path:
    """Return an atomic staging path ending in ``.partial.exr``."""
    return target_path.with_name(f".{target_path.stem}.partial{target_path.suffix}")


class VideoToExrConverter:
    """Convert a video file into an OpenEXR plate sequence."""

    def __init__(
        self,
        config: VideoToExrConfig,
        video_reader: Optional[FFmpegVideoReader] = None,
    ) -> None:
        """Initialize the converter.

        Args:
            config: Video-to-EXR conversion settings.
            video_reader: Optional custom video reader (primarily for testing).
        """
        self.config = config
        self.video_reader = video_reader or FFmpegVideoReader()

    def _create_color_converter(self) -> Optional[ColorSpaceConverter]:
        """Construct the appropriate color converter, or ``None`` for passthrough."""
        in_space = self.config.input_space.strip()
        out_space = self.config.output_space.strip()
        if self.config.ocio_config_path:
            if in_space == out_space:
                return None
            return ColorSpaceConverter(
                ColorSpacePreset.OCIO_CONVERSION,
                ocio_config_path=self.config.ocio_config_path,
                ocio_output_space=out_space,
            )

        if in_space.lower() == out_space.lower():
            return None

        in_lower = in_space.lower()
        out_lower = out_space.lower()
        if in_lower == "srgb" and out_lower == "linear":
            return ColorSpaceConverter(ColorSpacePreset.SRGB_TO_LINEAR)
        if in_lower == "linear" and out_lower == "srgb":
            return ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)
        if in_lower == "linear" and out_lower in {"rec709", "rec.709", "bt709", "bt.709"}:
            return ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_REC709)

        return ColorSpaceConverter(
            ColorSpacePreset.OCIO_CONVERSION,
            ocio_output_space=out_space,
        )

    def _estimate_total_frames(self) -> int:
        """Estimate total frames to be written for progress reporting."""
        if not hasattr(self.video_reader, "probe_video"):
            return 0
        try:
            info = self.video_reader.probe_video(self.config.input_path)
        except Exception:
            return 0
        if info.frame_count is None:
            return 0
        start = self.config.source_start_frame or 0
        end = (
            min(info.frame_count - 1, self.config.source_end_frame)
            if self.config.source_end_frame is not None
            else info.frame_count - 1
        )
        return max(0, end - start + 1)

    def convert(
        self,
        progress_callback: Optional[Callable[[int, int], Any]] = None,
    ) -> list[Path]:
        """Decode frames from the input video and write atomic EXR plates.

        Args:
            progress_callback: Optional callback ``(current, total) -> bool | None``.
                Returning ``False`` cancels the conversion.

        Returns:
            List of written EXR file paths in frame order.

        Raises:
            ConversionCancelledError: If ``progress_callback`` returns ``False``.
            VideoReadError: If no frames can be decoded from the input video.
            VideoIngestError: If writing an EXR frame fails.
        """
        oiio = require_oiio(VideoIngestError, "OpenImageIO is required for EXR writing.")
        first_target = format_sequence_frame_path(
            self.config.output_pattern, self.config.start_frame
        )
        first_target.parent.mkdir(parents=True, exist_ok=True)

        color_converter = self._create_color_converter()
        total_frames = self._estimate_total_frames()
        written_paths: list[Path] = []
        write_format = oiio.HALF if self.config.half_float else oiio.FLOAT

        for idx, (_source_idx, buf) in enumerate(
            self.video_reader.iter_frames(
                self.config.input_path,
                start_frame=self.config.source_start_frame,
                end_frame=self.config.source_end_frame,
                bit_depth=16,
            )
        ):
            target_frame = self.config.start_frame + idx
            target_path = format_sequence_frame_path(self.config.output_pattern, target_frame)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            pixel_aspect = 1.0
            try:
                raw_par = buf.spec().get_float_attribute("PixelAspectRatio", 1.0)
                if isinstance(raw_par, (int, float)) and raw_par > 0:
                    pixel_aspect = float(raw_par)
            except Exception:
                pixel_aspect = 1.0

            if color_converter is not None:
                buf = color_converter.convert_buf(buf, input_space=self.config.input_space)

            spec_mod = buf.specmod()
            spec_mod.attribute("compression", self.config.compression)
            if abs(pixel_aspect - 1.0) > 1e-4:
                spec_mod.attribute("PixelAspectRatio", pixel_aspect)
            buf.set_write_format(write_format)

            partial_path = _build_partial_exr_path(target_path)
            partial_path.unlink(missing_ok=True)
            try:
                if not buf.write(str(partial_path)):
                    err = buf.geterror() or oiio.geterror() or "unknown OIIO write error"
                    raise VideoIngestError(
                        f"Failed to write EXR frame {target_frame} to '{partial_path}': {err}"
                    )
                os.replace(partial_path, target_path)
            except Exception:
                partial_path.unlink(missing_ok=True)
                raise

            written_paths.append(target_path)

            if progress_callback is not None:
                if progress_callback(idx + 1, total_frames) is False:
                    raise ConversionCancelledError("Video-to-EXR conversion cancelled by user.")

        if not written_paths:
            raise VideoReadError(f"No frames were decoded from '{self.config.input_path}'.")

        return written_paths
