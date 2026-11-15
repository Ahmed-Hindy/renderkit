"""Video encoding using FFmpeg."""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import TracebackType
from typing import Any, Optional

import numpy as np
import OpenImageIO as oiio

from renderkit.core.ffmpeg_utils import get_ffmpeg_exe, popen_kwargs
from renderkit.exceptions import ConfigurationError, VideoEncodingError
from renderkit.processing.pixels import float_pixels_to_uint8, float_pixels_to_uint16
from renderkit.processing.scaler import ImageScaler

_FFREPORT_ENV_VAR = "FFREPORT"
_FFMPEG_REPORT_VERBOSITY_LEVEL = 48
_FFMPEG_REPORT_MAX_TAIL_LINES = 80
_QUALITY_MAX = 10
_X26X_CRF_BEST = 18
_X26X_CRF_STEP = 1.7
_X26X_CRF_DEFAULT = 23
_AV1_CRF_BEST = 20
_AV1_CRF_STEP = 3
_AV1_CRF_DEFAULT = 32
_AV1_CPU_USED = "6"
_AV1_CRF_BITRATE = "0"
_MPEG4_QV_BEST = 2
_MPEG4_QV_STEP = 2.9
_MPEG4_QV_DEFAULT = 4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodecProfile:
    """FFmpeg encoding configuration for a codec preset or name."""

    ffmpeg_codec: str
    pix_fmt_in: str = "rgb24"
    pix_fmt_out: str = "yuv420p"
    bit_depth: int = 8
    needs_alpha: bool = False
    extra_params: tuple[str, ...] = ()
    macro_block_size: int = 16
    container_ext: str = ".mp4"


CODEC_PROFILES: dict[str, CodecProfile] = {
    "libx264": CodecProfile(
        ffmpeg_codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "h264": CodecProfile(
        ffmpeg_codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "libx265": CodecProfile(
        ffmpeg_codec="libx265",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "hevc": CodecProfile(
        ffmpeg_codec="libx265",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "hevc_10bit": CodecProfile(
        ffmpeg_codec="libx265",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv420p10le",
        bit_depth=10,
        extra_params=("-tag:v", "hvc1"),
        macro_block_size=16,
    ),
    "libx265_10bit": CodecProfile(
        ffmpeg_codec="libx265",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv420p10le",
        bit_depth=10,
        extra_params=("-tag:v", "hvc1"),
        macro_block_size=16,
    ),
    "libaom-av1": CodecProfile(
        ffmpeg_codec="libaom-av1",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "av1": CodecProfile(
        ffmpeg_codec="libaom-av1",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "mpeg4": CodecProfile(
        ffmpeg_codec="mpeg4",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
    ),
    "prores_proxy": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "0", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores_lt": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "1", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores_422": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "2", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores_hq": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "3", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "3", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores_4444": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgba64le",
        pix_fmt_out="yuva444p12le",
        bit_depth=12,
        needs_alpha=True,
        extra_params=("-profile:v", "4", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "prores_xq": CodecProfile(
        ffmpeg_codec="prores_ks",
        pix_fmt_in="rgba64le",
        pix_fmt_out="yuva444p12le",
        bit_depth=12,
        needs_alpha=True,
        extra_params=("-profile:v", "5", "-vendor", "apl0"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "dnxhr_hq": CodecProfile(
        ffmpeg_codec="dnxhd",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv422p",
        bit_depth=8,
        extra_params=("-profile:v", "dnxhr_hq"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "dnxhr_hqx": CodecProfile(
        ffmpeg_codec="dnxhd",
        pix_fmt_in="rgb48le",
        pix_fmt_out="yuv422p10le",
        bit_depth=10,
        extra_params=("-profile:v", "dnxhr_hqx"),
        macro_block_size=2,
        container_ext=".mov",
    ),
    "h264_nvenc": CodecProfile(
        ffmpeg_codec="h264_nvenc",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        extra_params=("-preset", "p4"),
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "hevc_nvenc": CodecProfile(
        ffmpeg_codec="hevc_nvenc",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        extra_params=("-preset", "p4"),
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "h264_qsv": CodecProfile(
        ffmpeg_codec="h264_qsv",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        extra_params=("-preset", "medium"),
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "hevc_qsv": CodecProfile(
        ffmpeg_codec="hevc_qsv",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        extra_params=("-preset", "medium"),
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "h264_videotoolbox": CodecProfile(
        ffmpeg_codec="h264_videotoolbox",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "hevc_videotoolbox": CodecProfile(
        ffmpeg_codec="hevc_videotoolbox",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
        container_ext=".mp4",
    ),
    "h264_vaapi": CodecProfile(
        ffmpeg_codec="h264_vaapi",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        bit_depth=8,
        macro_block_size=16,
        container_ext=".mp4",
    ),
}

_LEGACY_CODEC_ALIASES: dict[str, str] = {
    "avc1": "libx264",
    "mp4v": "mpeg4",
    "XVID": "mpeg4",
}

_FALLBACK_ELIGIBLE_CODECS = {
    "libx264",
    "h264",
    "avc1",
    "libx265",
    "hevc",
    "libaom-av1",
    "av1",
    "mpeg4",
    "mp4v",
    "XVID",
    "h264_nvenc",
    "hevc_nvenc",
    "h264_qsv",
    "hevc_qsv",
    "h264_videotoolbox",
    "hevc_videotoolbox",
    "h264_vaapi",
}


def get_codec_profile(codec: str) -> CodecProfile:
    """Resolve a RenderKit codec name or legacy alias to a CodecProfile.

    Args:
        codec: Codec identifier or alias (e.g., ``'libx264'``, ``'prores_422'``, ``'h264_nvenc'``).

    Returns:
        Matching :class:`CodecProfile` or a default profile wrapping ``codec``.
    """
    mapped = _LEGACY_CODEC_ALIASES.get(codec, codec)
    if mapped in CODEC_PROFILES:
        return CODEC_PROFILES[mapped]
    lowered = mapped.lower()
    if lowered in CODEC_PROFILES:
        return CODEC_PROFILES[lowered]
    return CodecProfile(ffmpeg_codec=mapped)


def _resolve_codec_profile(codec: str) -> CodecProfile:
    return get_codec_profile(codec)


@dataclass(frozen=True)
class EncoderProbeResult:
    """Structured result for FFmpeg encoder capability probing."""

    encoders: frozenset[str]
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None

    @property
    def failed(self) -> bool:
        return self.error is not None


def _escape_ffreport_path(path: Path) -> str:
    if os.name == "nt":
        return path.as_posix().replace(":", r"\:")
    return str(path)


def _probe_failure_result(error: str) -> EncoderProbeResult:
    logger.warning("Unable to query FFmpeg encoders: %s", error)
    return EncoderProbeResult(frozenset(), error=error)


def _last_nonempty_line(text: str) -> Optional[str]:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            return line
    return None


def _probe_available_encoders() -> EncoderProbeResult:
    try:
        cmd = [get_ffmpeg_exe(), "-hide_banner", "-encoders"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **popen_kwargs(prevent_sigint=True),
        )
        text = (result.stdout or "") + "\n" + (result.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return _probe_failure_result(str(exc))

    if result.returncode != 0:
        error = f"ffmpeg -encoders exited with code {result.returncode}"
        output_tail = _last_nonempty_line(text)
        if output_tail:
            error = f"{error}: {output_tail}"
        return _probe_failure_result(error)

    encoders: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Encoders:") or line.startswith("-"):
            continue
        if not line[0].isalpha() or len(line) < 2:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if parts[0].startswith("V"):
            encoders.add(parts[1])
    return EncoderProbeResult(frozenset(encoders))


@lru_cache(maxsize=1)
def _cached_encoder_probe_result() -> EncoderProbeResult:
    return _probe_available_encoders()


def get_encoder_probe_result() -> EncoderProbeResult:
    return _cached_encoder_probe_result()


def get_available_encoders() -> set[str]:
    return set(get_encoder_probe_result().encoders)


def select_available_encoder(
    requested: str,
    available: set[str],
    logger: Any = None,
) -> tuple[str, Optional[str]]:
    """Select the requested encoder if available or a compatible software fallback.

    Args:
        requested: Requested FFmpeg encoder name.
        available: Set of encoder names reported by FFmpeg.
        logger: Optional logger instance to emit a warning when falling back.

    Returns:
        Tuple of ``(selected_encoder, warning_message_or_none)``.
    """
    if not available or requested in available:
        return requested, None

    fallback_map = {
        "libx264": ["libx265", "libaom-av1", "mpeg4"],
        "libx265": ["libaom-av1", "mpeg4"],
        "libaom-av1": ["libx265", "mpeg4"],
        "mpeg4": ["libx265", "libaom-av1"],
        "hevc_nvenc": ["libx265", "libaom-av1", "mpeg4"],
        "hevc_qsv": ["libx265", "libaom-av1", "mpeg4"],
        "hevc_videotoolbox": ["libx265", "libaom-av1", "mpeg4"],
        "h264_nvenc": ["libx264", "libx265", "libaom-av1", "mpeg4"],
        "h264_qsv": ["libx264", "libx265", "libaom-av1", "mpeg4"],
        "h264_videotoolbox": ["libx264", "libx265", "libaom-av1", "mpeg4"],
        "h264_vaapi": ["libx264", "libx265", "libaom-av1", "mpeg4"],
    }
    if requested in fallback_map:
        candidates = fallback_map[requested]
    elif requested.startswith("hevc_"):
        candidates = ["libx265", "libaom-av1", "mpeg4"]
    elif requested.startswith("h264_"):
        candidates = ["libx264", "libx265", "libaom-av1", "mpeg4"]
    else:
        candidates = ["libx265", "libaom-av1", "mpeg4"]

    for candidate in candidates:
        if candidate in available:
            warning_msg = (
                f"Requested encoder '{requested}' is unavailable; falling back to '{candidate}'."
            )
            if logger is not None:
                logger.warning(warning_msg)
            return candidate, warning_msg

    return requested, None


def _build_partial_output_path(output_path: Path) -> Path:
    """Return a hidden partial output path in the target directory."""
    return output_path.with_name(f".{output_path.stem}.partial{output_path.suffix}")


class _RawFfmpegPipeWriter:
    def __init__(
        self,
        output_path: Path,
        width: int,
        height: int,
        fps: float,
        codec: str,
        pix_fmt_in: str,
        pix_fmt_out: str,
        ffmpeg_params: list[str],
        ffmpeg_log_level: str,
        bitrate: Optional[str],
        env: Optional[dict[str, str]] = None,
    ) -> None:
        ffmpeg_exe = get_ffmpeg_exe()
        size_str = f"{width}x{height}"
        self._cmd = [
            ffmpeg_exe,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            size_str,
            "-pix_fmt",
            pix_fmt_in,
            "-r",
            f"{fps:.02f}",
            "-i",
            "pipe:0",
            "-an",
            "-vcodec",
            codec,
            "-pix_fmt",
            pix_fmt_out,
        ]
        if bitrate is not None:
            self._cmd += ["-b:v", bitrate]
        self._cmd += ["-v", ffmpeg_log_level]
        self._cmd += ffmpeg_params
        self._cmd.append(str(output_path))
        self._cmd_str = " ".join(self._cmd)
        self._env = env
        popen_extra: dict[str, Any] = popen_kwargs(prevent_sigint=True)
        if self._env is not None:
            popen_extra["env"] = self._env
        try:
            self._process = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=None,
                **popen_extra,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to start FFmpeg: {exc}") from exc
        if self._process.stdin is None:
            raise RuntimeError("FFmpeg stdin is not available for writing.")

    def append_data(self, frame: np.ndarray) -> None:
        if self._process.poll() is not None:
            raise RuntimeError(f"FFmpeg exited early with code {self._process.returncode}.")
        if self._process.stdin is None:
            raise RuntimeError("FFmpeg stdin is not available for writing.")
        try:
            self._process.stdin.write(frame.tobytes())
        except Exception as exc:
            raise RuntimeError(f"{exc}\n\nFFMPEG COMMAND:\n{self._cmd_str}") from exc

    def close(self) -> None:
        if self._process.poll() is None:
            if self._process.stdin is not None:
                try:
                    self._process.stdin.close()
                except Exception as exc:
                    logger.warning("Error closing FFmpeg stdin: %s", exc)
            self._process.wait()
        if self._process.returncode:
            raise RuntimeError(
                f"FFmpeg exited with code {self._process.returncode} while finalizing video."
                f"\n\nFFMPEG COMMAND:\n{self._cmd_str}"
            )

    def abort(self) -> None:
        """Terminate an active FFmpeg process without waiting for finalization."""
        if self._process.poll() is not None:
            return
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except (OSError, ValueError):
                pass
        try:
            self._process.terminate()
        except OSError:
            return
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
                self._process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass


class VideoEncoder:
    """Video encoder for creating MP4 files using FFmpeg."""

    def __init__(
        self,
        output_path: Path,
        fps: float,
        codec: str = "libx264",
        bitrate: Optional[int] = None,
        quality: Optional[int] = 10,
        macro_block_size: Optional[int] = None,
        pixel_aspect: float = 1.0,
    ) -> None:
        """Initialize video encoder.

        Args:
            output_path: Path to output video file.
            fps: Frame rate.
            codec: Video codec or profile name (e.g. 'libx264', 'hevc_10bit', 'prores_hq').
            bitrate: Video bitrate in kbps (optional).
            quality: Video quality (0-10), 10 is best (optional, used only if bitrate is None).
            macro_block_size: Macro block size for codec compatibility (defaults to codec profile).
                Frame dimensions will be rounded up to multiples of this value.
            pixel_aspect: Sample/pixel aspect ratio (must be > 0).
        """
        if quality is not None and not 0 <= quality <= _QUALITY_MAX:
            raise ConfigurationError("Quality must be between 0 and 10")
        if isinstance(pixel_aspect, bool) or pixel_aspect <= 0:
            raise ConfigurationError("Pixel aspect ratio must be positive")

        self.output_path = output_path.absolute()
        self._partial_output_path = _build_partial_output_path(self.output_path)
        self.fps = fps
        self.codec = codec
        self._profile = _resolve_codec_profile(codec)
        self.bitrate = bitrate
        self.quality = quality
        self.macro_block_size = (
            self._profile.macro_block_size if macro_block_size is None else macro_block_size
        )
        self.pixel_aspect = float(pixel_aspect)
        self._writer: Optional[_RawFfmpegPipeWriter] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._adjusted_width: Optional[int] = None
        self._adjusted_height: Optional[int] = None
        self._ffmpeg_report_path: Optional[Path] = None
        self._ffmpeg_env: Optional[dict[str, str]] = None

    def _configure_ffmpeg_report(self) -> Optional[Path]:
        """Enable ffmpeg report logging (on by default)."""
        self._ffmpeg_env = None
        value = os.environ.get("RENDERKIT_FFMPEG_LOG", "1")
        if value.lower() in {"0", "false", "no", "off"}:
            return None
        if value.lower() in {"1", "true", "yes", "on"}:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = Path(tempfile.gettempdir()) / f"renderkit-ffmpeg-{stamp}.log"
        else:
            path = Path(value).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        escaped_path = _escape_ffreport_path(path)
        env = os.environ.copy()
        env[_FFREPORT_ENV_VAR] = f"file={escaped_path}:level={_FFMPEG_REPORT_VERBOSITY_LEVEL}"
        self._ffmpeg_env = env
        return path

    def _restore_ffmpeg_report_env(self) -> None:
        self._ffmpeg_env = None

    def _read_ffmpeg_report_tail(
        self, max_lines: int = _FFMPEG_REPORT_MAX_TAIL_LINES
    ) -> Optional[str]:
        """Best-effort FFmpeg report tail for error messages."""
        if self._ffmpeg_report_path is None:
            return None
        if not self._ffmpeg_report_path.exists():
            return None
        try:
            content = self._ffmpeg_report_path.read_text(errors="ignore")
        except OSError as exc:
            logger.debug(
                "Unable to read FFmpeg report tail from %s: %s", self._ffmpeg_report_path, exc
            )
            return None
        lines = [line for line in content.splitlines() if line.strip()]
        if not lines:
            return None
        tail = "\n".join(lines[-max_lines:])
        return f"FFMPEG REPORT (tail) [{self._ffmpeg_report_path}]:\n{tail}"

    @staticmethod
    def _make_divisible(dimension: int, divisor: int = 16) -> int:
        """Round up dimension to be divisible by divisor for codec compatibility.

        Args:
            dimension: Original dimension
            divisor: Divisor (typically 16 for macro block size)

        Returns:
            Dimension rounded up to nearest multiple of divisor
        """
        return ((dimension + divisor - 1) // divisor) * divisor

    def __enter__(self) -> "VideoEncoder":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit - abort on error, otherwise close video writer."""
        if exc_type is not None:
            self.abort()
            return
        self.close()

    def initialize(self, width: int, height: int) -> None:
        """Initialize the video writer with frame dimensions.

        Args:
            width: Frame width
            height: Frame height

        Raises:
            VideoEncodingError: If encoder cannot be initialized
        """
        self._width = width
        self._height = height

        # Adjust dimensions to be divisible by macro_block_size for codec compatibility
        # This prevents ffmpeg from needing to auto-resize frames.
        self._adjusted_width = self._make_divisible(width, self.macro_block_size)
        self._adjusted_height = self._make_divisible(height, self.macro_block_size)

        if self._adjusted_width != width or self._adjusted_height != height:
            logger.warning(
                f"Frame dimensions adjusted from {width}x{height} to "
                f"{self._adjusted_width}x{self._adjusted_height} for codec compatibility"
            )

        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        # Resolve codec profile and verify FFmpeg encoder availability
        profile = self._profile
        ffmpeg_codec = profile.ffmpeg_codec
        encoder_probe = get_encoder_probe_result()
        available_encoders = set(encoder_probe.encoders)
        if self.codec in _FALLBACK_ELIGIBLE_CODECS or (
            profile.ffmpeg_codec in _FALLBACK_ELIGIBLE_CODECS
            and profile.bit_depth == 8
            and not profile.extra_params
        ):
            ffmpeg_codec, fallback_warning = select_available_encoder(
                ffmpeg_codec, available_encoders
            )
            if fallback_warning:
                logger.warning(fallback_warning)
                profile = _resolve_codec_profile(ffmpeg_codec)
                self._profile = profile
        if encoder_probe.failed:
            logger.warning(
                "Skipping FFmpeg encoder availability validation because probing failed: %s. "
                "Attempting '%s'.",
                encoder_probe.error,
                ffmpeg_codec,
            )
        elif ffmpeg_codec not in encoder_probe.encoders:
            available = ", ".join(sorted(encoder_probe.encoders))
            if not available:
                available = "none"
            raise VideoEncodingError(
                f"Requested FFmpeg encoder '{ffmpeg_codec}' is not available. "
                f"Available encoders: {available}"
            )

        ffmpeg_log_level = "warning"
        self._ffmpeg_report_path = self._configure_ffmpeg_report()
        if self._ffmpeg_report_path is not None:
            ffmpeg_log_level = "info"
            logger.info("Logging to file: %s", self._ffmpeg_report_path)

        # Set default FFmpeg parameters for broad compatibility and web optimization
        # -movflags +faststart enables progressive loading for web playback
        # Add explicit SDR color tags for predictable playback across platforms
        ffmpeg_params = [
            "-movflags",
            "+faststart",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-colorspace",
            "bt709",
        ]
        if profile.extra_params:
            ffmpeg_params.extend(profile.extra_params)
        if abs(self.pixel_aspect - 1.0) > 1e-4:
            ffmpeg_params.extend(["-vf", f"setsar={self.pixel_aspect:.6f}"])

        bitrate: Optional[str] = None

        # Bitrate takes precedence over quality tuning when provided.
        if self.bitrate is not None:
            bitrate = f"{self.bitrate}k"
            if ffmpeg_codec == "libaom-av1":
                ffmpeg_params.extend(["-cpu-used", _AV1_CPU_USED])
            logger.debug("%s tuning: bitrate=%s", ffmpeg_codec, bitrate)
        # Codec-specific tuning and quality mapping (used only when bitrate is not provided).
        elif ffmpeg_codec in ["libx264", "libx265"]:
            # Map quality (0-10) to CRF (35-18)
            # 10 -> 18 (Excellent), 0 -> 35 (Low quality)
            # Default to 23 if not specified
            crf = (
                _X26X_CRF_BEST + (_QUALITY_MAX - self.quality) * _X26X_CRF_STEP
                if self.quality is not None
                else _X26X_CRF_DEFAULT
            )
            ffmpeg_params.extend(["-crf", f"{int(crf)}"])
            logger.debug(f"{ffmpeg_codec} tuning: crf={int(crf)}")

        elif ffmpeg_codec == "libaom-av1":
            # AV1 is extremely slow by default. Use -cpu-used 6 for better speed.
            # Map 0-10 quality to CRF 50-20 (lower is better)
            crf = (
                _AV1_CRF_BEST + (_QUALITY_MAX - self.quality) * _AV1_CRF_STEP
                if self.quality is not None
                else _AV1_CRF_DEFAULT
            )
            ffmpeg_params.extend(["-crf", f"{int(crf)}", "-cpu-used", _AV1_CPU_USED])
            # libaom-av1 needs bitrate=0 to enable CRF mode in FFmpeg
            bitrate = _AV1_CRF_BITRATE
            logger.debug(f"AV1 tuning: crf={int(crf)}, cpu-used=6")

        elif ffmpeg_codec == "mpeg4":
            # Map quality (0-10) to -q:v (31-2)
            # Higher -q:v is lower quality.
            qv = (
                _MPEG4_QV_BEST + (_QUALITY_MAX - self.quality) * _MPEG4_QV_STEP
                if self.quality is not None
                else _MPEG4_QV_DEFAULT
            )
            ffmpeg_params.extend(["-q:v", f"{int(qv)}"])
            logger.debug(f"MPEG-4 tuning: q:v={int(qv)}")

        elif ffmpeg_codec in ("h264_nvenc", "hevc_nvenc"):
            cq = (
                _X26X_CRF_BEST + (_QUALITY_MAX - self.quality) * _X26X_CRF_STEP
                if self.quality is not None
                else _X26X_CRF_DEFAULT
            )
            ffmpeg_params.extend(["-cq", f"{int(cq)}"])
            logger.debug("%s tuning: cq=%s", ffmpeg_codec, int(cq))

        elif ffmpeg_codec in ("h264_qsv", "hevc_qsv"):
            gq = (
                _X26X_CRF_BEST + (_QUALITY_MAX - self.quality) * _X26X_CRF_STEP
                if self.quality is not None
                else _X26X_CRF_DEFAULT
            )
            ffmpeg_params.extend(["-global_quality", f"{int(gq)}"])
            logger.debug("%s tuning: global_quality=%s", ffmpeg_codec, int(gq))

        elif ffmpeg_codec in ("h264_videotoolbox", "hevc_videotoolbox"):
            qv_vt = 30 + (self.quality if self.quality is not None else 7) * 5
            ffmpeg_params.extend(["-q:v", f"{int(qv_vt)}"])
            logger.debug("%s tuning: q:v=%s", ffmpeg_codec, int(qv_vt))

        elif ffmpeg_codec == "h264_vaapi":
            qp = (
                _X26X_CRF_BEST + (_QUALITY_MAX - self.quality) * _X26X_CRF_STEP
                if self.quality is not None
                else _X26X_CRF_DEFAULT
            )
            ffmpeg_params.extend(["-qp", f"{int(qp)}"])
            logger.debug("%s tuning: qp=%s", ffmpeg_codec, int(qp))

        # Apply final FFmpeg parameters
        if self._ffmpeg_report_path is not None:
            ffmpeg_params.extend(["-report", "-loglevel", "info"])
        self._partial_output_path.unlink(missing_ok=True)
        try:
            writer_kwargs: dict[str, Any] = {}
            if self._ffmpeg_env is not None:
                writer_kwargs["env"] = self._ffmpeg_env
            self._writer = _RawFfmpegPipeWriter(
                self._partial_output_path,
                self._adjusted_width,
                self._adjusted_height,
                self.fps,
                ffmpeg_codec,
                profile.pix_fmt_in,
                profile.pix_fmt_out,
                ffmpeg_params,
                ffmpeg_log_level,
                bitrate,
                **writer_kwargs,
            )
            logger.debug(
                f"Initialized FFmpeg pipe writer: {width}x{height} @ {self.fps}fps, "
                f"codec={ffmpeg_codec}, quality={self.quality}, bitrate={bitrate}, "
                f"params={ffmpeg_params}"
            )
        except RuntimeError as e:
            msg = str(e)
            self._partial_output_path.unlink(missing_ok=True)
            self._restore_ffmpeg_report_env()
            if "ffmpeg" in msg.lower():
                raise VideoEncodingError(
                    "FFmpeg backend not found. Ensure a bundled FFmpeg is available or ffmpeg is on PATH."
                ) from e
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e
        except Exception as e:
            self._partial_output_path.unlink(missing_ok=True)
            self._restore_ffmpeg_report_env()
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e

    def write_frame(self, buf: oiio.ImageBuf) -> None:
        """Write an ImageBuf frame to the video."""
        if self._writer is None or self._adjusted_width is None or self._adjusted_height is None:
            raise VideoEncodingError("Video encoder not initialized. Call initialize() first.")

        spec = buf.spec()
        if spec.width != self._adjusted_width or spec.height != self._adjusted_height:
            buf = ImageScaler.scale_buf(
                buf,
                width=self._adjusted_width,
                height=self._adjusted_height,
                filter_name="lanczos3",
            )
            spec = buf.spec()

        pixels = buf.get_pixels(oiio.FLOAT)
        if pixels is None or pixels.size == 0:
            raise VideoEncodingError("Failed to extract pixel data from ImageBuf.")
        if pixels.ndim == 1:
            frame = pixels.reshape((spec.height, spec.width, spec.nchannels))
        else:
            frame = pixels

        if self._profile.bit_depth > 8:
            frame = float_pixels_to_uint16(frame)
            opaque_alpha = 65535
        else:
            frame = float_pixels_to_uint8(frame)
            opaque_alpha = 255

        if self._profile.needs_alpha:
            if frame.ndim == 2:
                alpha = np.full(frame.shape, opaque_alpha, dtype=frame.dtype)
                frame = np.stack([frame, frame, frame, alpha], axis=-1)
            elif frame.ndim == 3 and frame.shape[2] == 1:
                rgb = np.repeat(frame, 3, axis=2)
                alpha = np.full(
                    (frame.shape[0], frame.shape[1], 1), opaque_alpha, dtype=frame.dtype
                )
                frame = np.concatenate([rgb, alpha], axis=2)
            elif frame.ndim == 3 and frame.shape[2] == 3:
                alpha = np.full(
                    (frame.shape[0], frame.shape[1], 1), opaque_alpha, dtype=frame.dtype
                )
                frame = np.concatenate([frame, alpha], axis=2)
            elif frame.ndim == 3 and frame.shape[2] > 4:
                frame = frame[:, :, :4]
        else:
            # FFmpeg rawvideo expects RGB (standard)
            # If RGBA, drop alpha channel
            if frame.ndim == 3 and frame.shape[2] >= 4:
                frame = frame[:, :, :3]
            elif frame.ndim == 3 and frame.shape[2] == 1:
                frame = np.repeat(frame, 3, axis=2)
            # If Grayscale, ensure 3D
            elif frame.ndim == 2:
                frame = np.stack([frame] * 3, axis=-1)

        frame = np.ascontiguousarray(frame)

        try:
            self._writer.append_data(frame)
        except Exception as e:
            report_tail = self._read_ffmpeg_report_tail()
            if report_tail:
                raise VideoEncodingError(
                    f"Failed to write frame to video: {e}\n\n{report_tail}"
                ) from e
            raise VideoEncodingError(f"Failed to write frame to video: {e}") from e

    def close(self) -> None:
        """Close the video writer and promote the partial file on success."""
        try:
            if self._writer is not None:
                try:
                    self._writer.close()
                    if self._partial_output_path.exists():
                        self._partial_output_path.replace(self.output_path)
                    logger.info("Video encoding completed.")
                except Exception as e:
                    logger.error(f"Error closing video writer: {e}")
                    self._partial_output_path.unlink(missing_ok=True)
                    report_tail = self._read_ffmpeg_report_tail()
                    if report_tail:
                        raise VideoEncodingError(
                            f"Failed to finalize video encoding: {e}\n\n{report_tail}"
                        ) from e
                    raise VideoEncodingError(f"Failed to finalize video encoding: {e}") from e
                finally:
                    self._writer = None
        finally:
            self._restore_ffmpeg_report_env()

    def abort(self) -> None:
        """Abort active encoding and discard any partial output file."""
        try:
            if self._writer is not None:
                try:
                    if hasattr(self._writer, "abort"):
                        self._writer.abort()
                    else:
                        self._writer.close()
                except Exception as e:
                    logger.warning("Error aborting video writer: %s", e)
                finally:
                    self._writer = None
            self._partial_output_path.unlink(missing_ok=True)
        finally:
            self._restore_ffmpeg_report_env()

    def is_initialized(self) -> bool:
        """Check if encoder is initialized."""
        return self._writer is not None
