"""Preview image marshaling helpers for Qt display."""

from dataclasses import dataclass
from typing import Any

import numpy as np
import OpenImageIO as oiio

from renderkit.ui.qt_compat import QImage, QPixmap


@dataclass(frozen=True)
class PreviewImageData:
    """Contiguous uint8 preview pixels that can cross the worker/UI boundary."""

    pixels: np.ndarray
    width: int
    height: int
    channels: int


def imagebuf_to_preview_image(buf: oiio.ImageBuf) -> PreviewImageData:
    """Convert an ImageBuf into contiguous uint8 RGB/RGBA preview data."""
    image = buf.get_pixels(oiio.FLOAT)
    if image is None or image.size == 0:
        raise ValueError("Failed to extract preview pixels.")

    spec = buf.spec()
    if image.ndim == 1:
        image = image.reshape((spec.height, spec.width, spec.nchannels))

    if image.ndim != 3:
        raise ValueError(f"Unsupported preview image dimensions: {image.ndim}")

    height, width, channels = image.shape
    if channels not in (3, 4):
        raise ValueError(f"Unsupported image channels: {channels}")

    if image.dtype != np.uint8:
        image_f32 = image.astype(np.float32, copy=False)
        image = np.clip(image_f32, 0.0, 1.0)
        image = (image * np.float32(255.0)).astype(np.uint8)

    image = np.ascontiguousarray(image)
    return PreviewImageData(
        pixels=image,
        width=width,
        height=height,
        channels=channels,
    )


def preview_image_to_qimage(data: PreviewImageData) -> QImage:
    """Create a QImage from preview image data.

    This function performs safety checks and returns a deep copy of the image.
    Crucially, it checks that the array is C-contiguous (copying if necessary to
    avoid garbled textures or segfaults) and that the dtype is uint8 (preventing
    memory footprint/row stride mismatch corruption).

    Finally, it returns a deep copy of the QImage to prevent a use-after-free bug
    when the Python PreviewImageData goes out of scope and gets garbage collected.
    """
    if data.pixels.dtype != np.uint8:
        raise ValueError(f"Preview image pixels must be uint8, but got dtype: {data.pixels.dtype}")

    pixels = data.pixels
    if not pixels.flags.c_contiguous:
        pixels = np.ascontiguousarray(pixels)

    q_format = _qimage_format(data.channels)
    bytes_per_line = data.width * data.channels
    image = QImage(
        pixels.data,
        data.width,
        data.height,
        bytes_per_line,
        q_format,
    )
    return image.copy()


def preview_image_to_pixmap(data: PreviewImageData) -> QPixmap:
    """Create a QPixmap from preview image data."""
    return QPixmap.fromImage(preview_image_to_qimage(data))


def _qimage_format(channels: int) -> Any:
    if channels == 3:
        name = "Format_RGB888"
    elif channels == 4:
        name = "Format_RGBA8888"
    else:
        raise ValueError(f"Unsupported image channels: {channels}")

    enum = getattr(QImage, "Format", None)
    if enum is not None:
        value = getattr(enum, name, None)
        if value is not None:
            return value

    value = getattr(QImage, name, None)
    if value is None:
        raise ValueError(f"Qt image format is unavailable: {name}")
    return value
