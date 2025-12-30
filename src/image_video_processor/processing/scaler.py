"""Image scaling utilities."""

import logging
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ImageScaler:
    """Utility class for image scaling."""

    @staticmethod
    def scale_image(
        image: np.ndarray,
        width: Optional[int] = None,
        height: Optional[int] = None,
        interpolation: int = cv2.INTER_LANCZOS4,
    ) -> np.ndarray:
        """Scale an image to the specified dimensions.

        Args:
            image: Input image array (H, W, C)
            width: Target width (None to maintain aspect ratio)
            height: Target height (None to maintain aspect ratio)
            interpolation: OpenCV interpolation method

        Returns:
            Scaled image array

        Raises:
            ValueError: If both width and height are None
        """
        if width is None and height is None:
            raise ValueError("At least one of width or height must be specified")

        h, w = image.shape[:2]

        # Calculate target dimensions
        if width is not None and height is not None:
            target_w, target_h = width, height
        elif width is not None:
            # Maintain aspect ratio
            aspect_ratio = h / w
            target_w = width
            target_h = int(width * aspect_ratio)
        else:
            # height is not None
            aspect_ratio = w / h
            target_h = height
            target_w = int(height * aspect_ratio)

        # No scaling needed if dimensions match
        if target_w == w and target_h == h:
            return image

        # Scale the image
        scaled = cv2.resize(image, (target_w, target_h), interpolation=interpolation)

        return scaled

    @staticmethod
    def scale_to_fit(
        image: np.ndarray,
        max_width: int,
        max_height: int,
        interpolation: int = cv2.INTER_LANCZOS4,
    ) -> np.ndarray:
        """Scale image to fit within maximum dimensions while maintaining aspect ratio.

        Args:
            image: Input image array (H, W, C)
            max_width: Maximum width
            max_height: Maximum height
            interpolation: OpenCV interpolation method

        Returns:
            Scaled image array
        """
        h, w = image.shape[:2]

        # Calculate scaling factor
        scale_w = max_width / w if w > max_width else 1.0
        scale_h = max_height / h if h > max_height else 1.0
        scale = min(scale_w, scale_h)

        # If no scaling needed
        if scale >= 1.0:
            return image

        target_w = int(w * scale)
        target_h = int(h * scale)

        return ImageScaler.scale_image(image, target_w, target_h, interpolation)

