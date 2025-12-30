"""Video encoding using OpenCV/FFmpeg."""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from image_video_processor.exceptions import VideoEncodingError

logger = logging.getLogger(__name__)


class VideoEncoder:
    """Video encoder for creating MP4 files from image sequences."""

    def __init__(
        self,
        output_path: Path,
        fps: float,
        codec: str = "mp4v",
        bitrate: Optional[int] = None,
    ) -> None:
        """Initialize video encoder.

        Args:
            output_path: Path to output video file
            fps: Frame rate
            codec: Video codec (default: 'mp4v', use 'avc1' for H.264)
            bitrate: Video bitrate in bits per second (optional)
        """
        self.output_path = output_path
        self.fps = fps
        self.codec = codec
        self.bitrate = bitrate
        self._writer: Optional[cv2.VideoWriter] = None
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

        # Get fourcc codec
        fourcc = cv2.VideoWriter_fourcc(*self.codec)

        # Create video writer
        self._writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (width, height),
        )

        if not self._writer.isOpened():
            # Try alternative codec for better compatibility
            if self.codec == "mp4v":
                logger.warning("mp4v codec failed, trying avc1 (H.264)")
                fourcc = cv2.VideoWriter_fourcc(*"avc1")
                self._writer = cv2.VideoWriter(
                    str(self.output_path),
                    fourcc,
                    self.fps,
                    (width, height),
                )

            if not self._writer.isOpened():
                raise VideoEncodingError(
                    f"Failed to initialize video encoder for: {self.output_path}"
                )

        logger.info(
            f"Initialized video encoder: {width}x{height} @ {self.fps}fps, "
            f"codec={self.codec}"
        )

    def write_frame(self, frame: np.ndarray) -> None:
        """Write a frame to the video.

        Args:
            frame: Frame as numpy array (H, W, C) in uint8 format [0, 255]

        Raises:
            VideoEncodingError: If frame cannot be written
        """
        if self._writer is None:
            raise VideoEncodingError("Video encoder not initialized. Call initialize() first.")

        # Ensure frame is uint8
        if frame.dtype != np.uint8:
            # Clamp and convert
            frame = np.clip(frame * 255.0, 0, 255).astype(np.uint8)

        # Resize frame if dimensions don't match encoder dimensions
        h, w = frame.shape[:2]
        if w != self._width or h != self._height:
            logger.warning(
                f"Frame dimensions ({w}x{h}) do not match encoder dimensions "
                f"({self._width}x{self._height}). Resizing frame to match."
            )
            frame = cv2.resize(frame, (self._width, self._height), interpolation=cv2.INTER_LANCZOS4)

        # Convert BGR to RGB if needed (OpenCV uses BGR)
        if frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        elif frame.shape[2] == 4:
            # RGBA to BGRA
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)

        self._writer.write(frame)

    def close(self) -> None:
        """Close the video writer."""
        if self._writer is not None:
            self._writer.release()
            self._writer = None
            logger.info(f"Video encoding completed: {self.output_path}")

    def is_initialized(self) -> bool:
        """Check if encoder is initialized.

        Returns:
            True if encoder is initialized
        """
        return self._writer is not None and self._writer.isOpened()

