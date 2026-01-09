"""Video encoding using FFmpeg."""

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
import numpy as np
from imageio_ffmpeg._utils import _popen_kwargs

from renderkit.exceptions import VideoEncodingError
from renderkit.processing.scaler import ImageScaler

logger = logging.getLogger(__name__)


def _escape_ffreport_path(path: Path) -> str:
    if os.name == "nt":
        return path.as_posix().replace(":", r"\:")
    return str(path)


def get_available_encoders() -> set[str]:
    try:
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-encoders"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **_popen_kwargs(prevent_sigint=True),
        )
        text = (result.stdout or "") + "\n" + (result.stderr or "")
    except Exception as exc:
        logger.warning("Unable to query FFmpeg encoders: %s", exc)
        return set()

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
    return encoders


def select_available_encoder(requested: str, available: set[str]) -> tuple[str, Optional[str]]:
    if not available or requested in available:
        return requested, None

    fallback_map = {
        "libx264": ["libx265", "libaom-av1", "mpeg4"],
        "libx265": ["libaom-av1", "mpeg4"],
        "libaom-av1": ["libx265", "mpeg4"],
        "mpeg4": ["libx265", "libaom-av1"],
    }
    for candidate in fallback_map.get(requested, ["libx265", "libaom-av1", "mpeg4"]):
        if candidate in available:
            return candidate, (
                f"Requested encoder '{requested}' is unavailable; falling back to '{candidate}'."
            )

    return requested, None


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
    ) -> None:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
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
        try:
            self._process = subprocess.Popen(
                self._cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                **_popen_kwargs(prevent_sigint=True),
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to start FFmpeg: {exc}") from exc
        if self._process.stdin is None:
            raise RuntimeError("FFmpeg stdin is not available for writing.")

    def append_data(self, frame: np.ndarray) -> None:
        if self._process.poll() is not None:
            raise RuntimeError(f"FFmpeg exited early with code {self._process.returncode}.")
        try:
            self._process.stdin.write(frame.tobytes())
        except Exception as exc:
            raise RuntimeError(f"{exc}\n\nFFMPEG COMMAND:\n{self._cmd_str}") from exc

    def close(self) -> None:
        if self._process.poll() is None:
            try:
                self._process.stdin.close()
            except Exception as exc:
                logger.warning("Error closing FFmpeg stdin: %s", exc)
            self._process.wait()
        try:
            self._process.stdout.close()
        except Exception:
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
        macro_block_size: int = 16,
    ) -> None:
        """Initialize video encoder.

        Args:
            output_path: Path to output video file
            fps: Frame rate
            codec: Video codec (FFmpeg name like 'libx264', 'libx265', 'libaom-av1')
            bitrate: Video bitrate in kbps (optional)
            quality: Video quality (0-10), 10 is best (optional, used if bitrate is None)
            macro_block_size: Macro block size for codec compatibility (default: 16)
                             Frame dimensions will be rounded up to multiples of this value
        """
        self.output_path = output_path.absolute()
        self.fps = fps
        self.codec = codec
        self.bitrate = bitrate
        self.quality = quality
        self.macro_block_size = macro_block_size
        self._writer = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._adjusted_width: Optional[int] = None
        self._adjusted_height: Optional[int] = None
        self._ffmpeg_report_path: Optional[Path] = None
        self._ffreport_prev: Optional[str] = None
        self._ffreport_set: bool = False

    def _configure_ffmpeg_report(self) -> Optional[Path]:
        """Enable ffmpeg report logging (on by default)."""
        value = os.environ.get("RENDERKIT_FFMPEG_LOG", "1")
        if value.lower() in {"0", "false", "no", "off"}:
            return None
        if value.lower() in {"1", "true", "yes", "on"}:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = Path(tempfile.gettempdir()) / f"renderkit-ffmpeg-{stamp}.log"
        else:
            path = Path(value).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        if "FFREPORT" in os.environ:
            self._ffreport_prev = os.environ["FFREPORT"]
        else:
            self._ffreport_prev = None
        escaped_path = _escape_ffreport_path(path)
        os.environ["FFREPORT"] = f"file={escaped_path}:level=48"
        self._ffreport_set = True
        return path

    def _restore_ffmpeg_report_env(self) -> None:
        if not self._ffreport_set:
            return
        if self._ffreport_prev is None:
            os.environ.pop("FFREPORT", None)
        else:
            os.environ["FFREPORT"] = self._ffreport_prev
        self._ffreport_set = False

    def _read_ffmpeg_report_tail(self, max_lines: int = 80) -> Optional[str]:
        if self._ffmpeg_report_path is None:
            return None
        if not self._ffmpeg_report_path.exists():
            return None
        try:
            content = self._ffmpeg_report_path.read_text(errors="ignore")
        except Exception:
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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close video writer."""
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

        # Map UI/OpenCV-style codecs to FFmpeg codecs
        codec_map = {
            "avc1": "libx264",
            "hevc": "libx265",
            "mp4v": "mpeg4",
            "XVID": "mpeg4",
        }
        ffmpeg_codec = codec_map.get(self.codec, self.codec)
        available_encoders = get_available_encoders()
        ffmpeg_codec, fallback_warning = select_available_encoder(ffmpeg_codec, available_encoders)
        if fallback_warning:
            logger.warning(fallback_warning)
        if available_encoders and ffmpeg_codec not in available_encoders:
            available = ", ".join(sorted(available_encoders))
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

        bitrate: Optional[str] = None

        # Codec-specific tuning and quality mapping
        if ffmpeg_codec in ["libx264", "libx265"]:
            # Map quality (0-10) to CRF (35-18)
            # 10 -> 18 (Excellent), 0 -> 35 (Low quality)
            # Default to 23 if not specified
            crf = 18 + (10 - self.quality) * 1.7 if self.quality is not None else 23
            ffmpeg_params.extend(["-crf", f"{int(crf)}"])
            logger.debug(f"{ffmpeg_codec} tuning: crf={int(crf)}")

        elif ffmpeg_codec == "libaom-av1":
            # AV1 is extremely slow by default. Use -cpu-used 6 for better speed.
            # Map 0-10 quality to CRF 50-20 (lower is better)
            crf = 20 + (10 - self.quality) * 3 if self.quality is not None else 32
            ffmpeg_params.extend(["-crf", f"{int(crf)}", "-cpu-used", "6"])
            # libaom-av1 needs bitrate=0 to enable CRF mode in FFmpeg
            bitrate = "0"
            logger.debug(f"AV1 tuning: crf={int(crf)}, cpu-used=6")

        elif ffmpeg_codec == "mpeg4":
            # Map quality (0-10) to -q:v (31-2)
            # Higher -q:v is lower quality.
            qv = 2 + (10 - self.quality) * 2.9 if self.quality is not None else 4
            ffmpeg_params.extend(["-q:v", f"{int(qv)}"])
            logger.debug(f"MPEG-4 tuning: q:v={int(qv)}")

        elif self.bitrate:
            bitrate = f"{self.bitrate}k"

        # Apply final FFmpeg parameters
        if self._ffmpeg_report_path is not None:
            ffmpeg_params.extend(["-report", "-loglevel", "info"])
        try:
            self._writer = _RawFfmpegPipeWriter(
                self.output_path,
                self._adjusted_width,
                self._adjusted_height,
                self.fps,
                ffmpeg_codec,
                "rgb24",
                "yuv420p",
                ffmpeg_params,
                ffmpeg_log_level,
                bitrate,
            )
            logger.debug(
                f"Initialized FFmpeg pipe writer: {width}x{height} @ {self.fps}fps, "
                f"codec={ffmpeg_codec}, quality={self.quality}, params={ffmpeg_params}"
            )
        except RuntimeError as e:
            msg = str(e)
            self._restore_ffmpeg_report_env()
            if "ffmpeg" in msg.lower():
                raise VideoEncodingError(
                    "FFmpeg backend not found. Please install imageio-ffmpeg: 'pip install imageio-ffmpeg'"
                ) from e
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e
        except Exception as e:
            self._restore_ffmpeg_report_env()
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a frame to the video.

        Args:
            frame: Frame as numpy array (H, W, C) in uint8 or float32 format
        """
        if self._writer is None:
            raise VideoEncodingError("Video encoder not initialized. Call initialize() first.")

        # Resize frame if needed to match adjusted dimensions
        # This ensures all frames have consistent size for video encoding
        if frame.shape[1] != self._adjusted_width or frame.shape[0] != self._adjusted_height:
            frame = ImageScaler.scale_image(
                frame,
                width=self._adjusted_width,
                height=self._adjusted_height,
                filter_name="lanczos3",
            )

        # Ensure frame is uint8 [0, 255] for FFmpeg rawvideo
        if frame.dtype != np.uint8:
            frame = np.clip(frame * 255.0, 0, 255).astype(np.uint8)

        # FFmpeg rawvideo expects RGB (standard)
        # If RGBA, drop alpha channel
        if len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]
        # If Grayscale, ensure 3D
        elif len(frame.shape) == 2:
            frame = np.stack([frame] * 3, axis=-1)

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
        """Close the video writer."""
        if self._writer is not None:
            try:
                self._writer.close()
                logger.info("Video encoding completed.")
            except Exception as e:
                logger.error(f"Error closing video writer: {e}")
            finally:
                self._writer = None
        self._restore_ffmpeg_report_env()

    def is_initialized(self) -> bool:
        """Check if encoder is initialized."""
        return self._writer is not None
