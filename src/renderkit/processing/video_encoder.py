"""Video encoding using imageio/FFmpeg."""

import logging
from pathlib import Path
from typing import Optional

import imageio
import numpy as np

from renderkit.exceptions import VideoEncodingError

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
        }

        # Encoder-specific tuning
        if ffmpeg_codec == "libaom-av1":
            # AV1 is extremely slow by default. Use -cpu-used 6-8 for better speed.
            # Also needs bitrate=0 to enable CRF mode in libaom.
            writer_kwargs["bitrate"] = 0
            # Map 0-10 quality to CRF 60-15 (lower is better)
            crf = 60 - (self.quality * 4) if self.quality is not None else 32
            writer_kwargs["ffmpeg_params"] = ["-crf", str(crf), "-cpu-used", "6"]
            logger.info(f"AV1 tuning: crf={crf}, cpu-used=6")
        elif self.bitrate:
            writer_kwargs["bitrate"] = f"{self.bitrate}k"
        elif self.quality is not None:
            writer_kwargs["quality"] = self.quality

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
                f"codec={ffmpeg_codec}, bitrate={self.bitrate or 'Auto'}k, quality={self.quality}"
            )
        except Exception as e:
            raise VideoEncodingError(f"Failed to initialize video encoder: {e}") from e

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a frame to the video.

        Args:
            frame: Frame as numpy array (H, W, C) in uint8 or float32 format
        """
        if self._writer is None:
            raise VideoEncodingError("Video encoder not initialized. Call initialize() first.")

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
