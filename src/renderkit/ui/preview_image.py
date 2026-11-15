"""Preview image marshaling helpers for Qt display."""

import math
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
import OpenImageIO as oiio

from renderkit.processing.pixels import float_pixels_to_uint8
from renderkit.ui.qt_compat import QImage, QPixmap, qt_enum, resolve_enum_member


@dataclass(frozen=True)
class PreviewImageData:
    """Contiguous uint8 preview pixels that can cross the worker/UI boundary."""

    pixels: np.ndarray
    width: int
    height: int
    channels: int
    pixel_aspect: float = 1.0


def _extract_pixel_aspect(spec: Any) -> float:
    """Extract a positive finite PixelAspectRatio from an OIIO ImageSpec."""
    try:
        raw_aspect = spec.get_float_attribute("PixelAspectRatio", 1.0)
        pixel_aspect = float(raw_aspect)
    except (AttributeError, TypeError, ValueError):
        return 1.0
    if not math.isfinite(pixel_aspect) or pixel_aspect <= 0.0:
        return 1.0
    return pixel_aspect


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
        image = float_pixels_to_uint8(image)

    image = np.ascontiguousarray(image)
    return PreviewImageData(
        pixels=image,
        width=width,
        height=height,
        channels=channels,
        pixel_aspect=_extract_pixel_aspect(spec),
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
    if data.pixels.ndim != 3:
        raise ValueError(
            f"Preview image pixels must be 3-dimensional (height, width, channels), "
            f"but got ndim: {data.pixels.ndim}"
        )

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
    # Pin underlying NumPy array reference to QImage to guarantee it is not
    # garbage collected before the deep copy is completed.
    cast(Any, image)._numpy_ref = pixels
    return image.copy()


def preview_image_to_pixmap(data: PreviewImageData) -> QPixmap:
    """Create a QPixmap from preview image data, applying anamorphic unsqueeze if needed."""
    pixmap = QPixmap.fromImage(preview_image_to_qimage(data))
    if data.pixel_aspect > 0.0 and abs(data.pixel_aspect - 1.0) > 1e-4:
        target_width = max(1, int(round(data.width * data.pixel_aspect)))
        pixmap = pixmap.scaled(
            target_width,
            data.height,
            qt_enum("AspectRatioMode", "IgnoreAspectRatio"),
            qt_enum("TransformationMode", "SmoothTransformation"),
        )
    return pixmap


def _qimage_format(channels: int) -> Any:
    if channels == 3:
        name = "Format_RGB888"
    elif channels == 4:
        name = "Format_RGBA8888"
    else:
        raise ValueError(f"Unsupported image channels: {channels}")

    try:
        return resolve_enum_member(QImage, "Format", name)
    except AttributeError as exc:
        raise ValueError(f"Qt image format is unavailable: {name}") from exc
