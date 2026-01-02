"""Video encoding using imageio/FFmpeg."""

import logging
from pathlib import Path
from typing import Optional

import imageio
import numpy as np

from renderkit.exceptions import VideoEncodingError
from renderkit.processing.scaler import ImageScaler

logger = logging.getLogger(__name__)


class VideoEncoder:
    """Video encoder for creating MP4 files using imageio (FFmpeg)."""

    def __init__(
        self,
        output_path: Path,
        fps: float,
        codec: str = "libx264",
        bitrate: Optional[int] = None,
        quality: Optional[int] = 10,
    ) -> None:
        """Initialize video encoder.

        Args:
            output_path: Path to output video file
            fps: Frame rate
            codec: Video codec (FFmpeg name like 'libx264', 'libx265')
            bitrate: Video bitrate in kbps (optional)
            quality: Video quality (0-10), 10 is best (optional, used if bitrate is None)
        """
        self.output_path = output_path.absolute()
        self.fps = fps
        self.codec = codec
        self.bitrate = bitrate
        self.quality = quality
        self._writer = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._adjusted_width: Optional[int] = None
        self._adjusted_height: Optional[int] = None

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
        # This prevents imageio-ffmpeg from auto-resizing only the first frame
        self._adjusted_width = self._make_divisible(width, 16)
        self._adjusted_height = self._make_divisible(height, 16)

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

        # Prepare writer options
        writer_kwargs = {
            "fps": self.fps,
            "codec": ffmpeg_codec,
            "macro_block_size": 16,
            "pixelformat": "yuv420p",
        }

        # Set default FFmpeg parameters for broad compatibility and web optimization
        # -movflags +faststart enables progressive loading for web playback
        ffmpeg_params = ["-movflags", "+faststart"]

        # Codec-specific tuning and quality mapping
        if ffmpeg_codec in ["libx264", "libx265"]:
            # Map quality (0-10) to CRF (35-18)
            # 10 -> 18 (Excellent), 0 -> 35 (Low quality)
            # Default to 23 if not specified
            crf = 18 + (10 - self.quality) * 1.7 if self.quality is not None else 23
            ffmpeg_params.extend(["-crf", f"{int(crf)}"])
            logger.info(f"{ffmpeg_codec} tuning: crf={int(crf)}")

        elif ffmpeg_codec == "libaom-av1":
            # AV1 is extremely slow by default. Use -cpu-used 6 for better speed.
            # Map 0-10 quality to CRF 50-20 (lower is better)
            crf = 20 + (10 - self.quality) * 3 if self.quality is not None else 32
            ffmpeg_params.extend(["-crf", f"{int(crf)}", "-cpu-used", "6"])
            # libaom-av1 needs bitrate=0 to enable CRF mode in imageio-ffmpeg
            writer_kwargs["bitrate"] = 0
            logger.info(f"AV1 tuning: crf={int(crf)}, cpu-used=6")

        elif ffmpeg_codec == "mpeg4":
            # Map quality (0-10) to -q:v (31-2)
            # Higher -q:v is lower quality.
            qv = 2 + (10 - self.quality) * 2.9 if self.quality is not None else 4
            ffmpeg_params.extend(["-q:v", f"{int(qv)}"])
            logger.info(f"MPEG-4 tuning: q:v={int(qv)}")

        elif self.bitrate:
            writer_kwargs["bitrate"] = f"{self.bitrate}k"

        # Apply final FFmpeg parameters
        writer_kwargs["ffmpeg_params"] = ffmpeg_params

        try:
            # Using str() on an absolute path is safest across platforms
            output_str = str(self.output_path)

            self._writer = imageio.get_writer(
                output_str,
                format="FFMPEG",
                mode="I",
                **writer_kwargs,
            )
            logger.info(
                f"Initialized imageio-ffmpeg writer: {width}x{height} @ {self.fps}fps, "
                f"codec={ffmpeg_codec}, quality={self.quality}, params={ffmpeg_params}"
            )
        except (ImportError, RuntimeError) as e:
            # Catch common issues with missing ffmpeg backend
            msg = str(e)
            if "ffmpeg" in msg.lower():
                raise VideoEncodingError(
                    "FFmpeg backend not found. Please install imageio-ffmpeg: 'pip install imageio-ffmpeg'"
                ) from e
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e
        except Exception as e:
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

        # Ensure frame is uint8 [0, 255] for imageio
        if frame.dtype != np.uint8:
            frame = np.clip(frame * 255.0, 0, 255).astype(np.uint8)

        # imageio expects RGB (standard)
        # If RGBA, drop alpha channel
        if len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]
        # If Grayscale, ensure 3D
        elif len(frame.shape) == 2:
            frame = np.stack([frame] * 3, axis=-1)

        try:
            self._writer.append_data(frame)
        except Exception as e:
            raise VideoEncodingError(f"Failed to write frame to video: {e}") from e

    def close(self) -> None:
        """Close the video writer."""
        if self._writer is not None:
            try:
                self._writer.close()
                logger.info(f"Video encoding completed: {self.output_path}")
            except Exception as e:
                logger.error(f"Error closing video writer: {e}")
            finally:
                self._writer = None

    def is_initialized(self) -> bool:
        """Check if encoder is initialized."""
        return self._writer is not None
