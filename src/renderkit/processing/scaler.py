"""Image scaling utilities using OpenImageIO (OIIO)."""

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ImageScaler:
    """Utility class for image scaling using OpenImageIO."""

    @staticmethod
    def scale_image(
        image: np.ndarray,
        width: Optional[int] = None,
        height: Optional[int] = None,
        filter_name: str = "lanczos3",
    ) -> np.ndarray:
        """Scale an image to the specified dimensions using OIIO.

        Args:
            image: Input image array (H, W, C)
            width: Target width
            height: Target height
            filter_name: OIIO filter name (e.g., 'lanczos3', 'mitchell', 'catmull-rom')

        Returns:
            Scaled image array
        """
        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise RuntimeError("OpenImageIO library not available.") from e

        if width is None and height is None:
            raise ValueError("At least one of width or height must be specified")

        h, w = image.shape[:2]
        channels = image.shape[2] if len(image.shape) == 3 else 1

        # Calculate target dimensions
        if width is not None and height is not None:
            target_w, target_h = width, height
        elif width is not None:
            aspect_ratio = h / w
            target_w = width
            target_h = int(width * aspect_ratio)
        else:
            aspect_ratio = w / h
            target_h = height
            target_w = int(height * aspect_ratio)

        # No scaling needed if dimensions match
        if target_w == w and target_h == h:
            return image

        # Create OIIO ImageBuf from numpy array
        # Note: image might be float32 or uint8. OIIO handles both.
        src_buf = oiio.ImageBuf(oiio.ImageSpec(w, h, channels, oiio.FLOAT))
        src_buf.set_pixels(oiio.ROI(), image.astype(np.float32))

        # Create destination buffer
        dst_buf = oiio.ImageBuf(oiio.ImageSpec(target_w, target_h, channels, oiio.FLOAT))

        # Perform the resize
        if not oiio.ImageBufAlgo.resize(dst_buf, src_buf, filtername=filter_name):
            raise RuntimeError(f"OIIO resize failed: {oiio.geterror()}")

        # Convert back to numpy
        scaled = dst_buf.get_pixels(oiio.FLOAT)
        scaled = scaled.reshape((target_h, target_w, channels))

        # Cast back to original type if needed (though our pipeline mostly uses float32)
        if image.dtype == np.uint8:
            scaled = (np.clip(scaled, 0.0, 1.0) * 255.0).astype(np.uint8)

        return scaled

    @staticmethod
    def scale_to_fit(
        image: np.ndarray,
        max_width: int,
        max_height: int,
        filter_name: str = "lanczos3",
    ) -> np.ndarray:
        """Scale image to fit within maximum dimensions while maintaining aspect ratio."""
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

        return ImageScaler.scale_image(image, target_w, target_h, filter_name)
