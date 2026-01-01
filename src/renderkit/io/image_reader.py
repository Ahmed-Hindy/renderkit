"""Image reading with OpenImageIO (OIIO)."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from renderkit import constants
from renderkit.exceptions import ImageReadError
from renderkit.io.file_utils import FileUtils

logger = logging.getLogger(__name__)


class ImageReader(ABC):
    """Abstract base class for image readers."""

    @abstractmethod
    def read(self, path: Path) -> np.ndarray:
        """Read an image file and return as numpy array."""
        pass

    @abstractmethod
    def get_channels(self, path: Path) -> int:
        """Get the number of channels."""
        pass

    @abstractmethod
    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get the resolution (width, height)."""
        pass

    @abstractmethod
    def get_metadata_fps(self, path: Path) -> Optional[float]:
        """Get FPS from metadata."""
        pass

    @abstractmethod
    def get_metadata_color_space(self, path: Path) -> Optional[str]:
        """Get color space from metadata."""
        pass


class OIIOReader(ImageReader):
    """Reader for all image formats supported by OpenImageIO."""

    def read(self, path: Path) -> np.ndarray:
        """Read an image using OIIO ImageBuf.

        Returns:
            Image as numpy array (H, W, C) in float32 format.
        """
        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise ImageReadError("OpenImageIO library not available.") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            buf = oiio.ImageBuf(str(path))
            if buf.has_error:
                raise ImageReadError(f"OIIO failed to read {path}: {buf.geterror()}")

            # Read image as float32
            data = buf.get_pixels(oiio.FLOAT)

            if data is None or data.size == 0:
                raise ImageReadError(f"OIIO failed to extract pixel data: {path}")

            spec = buf.spec()
            width = spec.width
            height = spec.height
            channels = spec.nchannels

            # OIIO's get_pixels often returns the correctly shaped array already,
            # but let's be explicit and ensure (H, W, C)
            if data.ndim == 1:
                image = data.reshape((height, width, channels))
            else:
                image = data

            return image

        except Exception as e:
            raise ImageReadError(f"Failed to read image with OIIO: {path} - {e}") from e

    def get_channels(self, path: Path) -> int:
        """Get channel count using OIIO."""
        try:
            import OpenImageIO as oiio
        except ImportError:
            return 3

        buf = oiio.ImageBuf(str(path))
        if buf.has_error:
            return 3

        spec = buf.spec()
        return spec.nchannels

    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get resolution using OIIO."""
        try:
            import OpenImageIO as oiio
        except ImportError:
            return (0, 0)

        buf = oiio.ImageBuf(str(path))
        if buf.has_error:
            return (0, 0)

        spec = buf.spec()
        return (spec.width, spec.height)

    def get_metadata_fps(self, path: Path) -> Optional[float]:
        """Get FPS from OIIO metadata."""
        try:
            import OpenImageIO as oiio
        except ImportError:
            return None

        buf = oiio.ImageBuf(str(path))
        if buf.has_error:
            return None

        spec = buf.spec()
        fps = None

        # Check standard and custom keys in constants
        for key in constants.FPS_METADATA_KEYS:
            val = spec.getattribute(key)
            if val is not None:
                try:
                    # OIIO attributes can be tuples for rationals
                    if isinstance(val, (list, tuple)) and len(val) == 2:
                        fps = float(val[0]) / float(val[1])
                    else:
                        fps = float(val)
                    break
                except (ValueError, TypeError, ZeroDivisionError):
                    continue

        return fps

    def get_metadata_color_space(self, path: Path) -> Optional[str]:
        """Get color space from OIIO metadata."""
        try:
            import OpenImageIO as oiio
        except ImportError:
            return None

        buf = oiio.ImageBuf(str(path))
        if buf.has_error:
            return None

        spec = buf.spec()
        color_space = None

        # Check standard and custom keys in constants
        for key in constants.COLOR_SPACE_METADATA_KEYS:
            val = spec.getattribute(key)
            if val is not None:
                if isinstance(val, bytes):
                    val = val.decode("utf-8")
                color_space = str(val).strip()
                break

        return color_space


class ImageReaderFactory:
    """Factory for creating appropriate image readers (Now standardized to OIIO)."""

    _readers: dict[str, type[ImageReader]] = {
        "exr": OIIOReader,
        "png": OIIOReader,
        "jpg": OIIOReader,
        "jpeg": OIIOReader,
        "tiff": OIIOReader,
        "tif": OIIOReader,
        "dpx": OIIOReader,
    }

    @classmethod
    def create_reader(cls, path: Path) -> ImageReader:
        """Create an OIIO reader for the given file."""
        extension = FileUtils.get_file_extension(path)
        reader_class = cls._readers.get(extension, OIIOReader)
        return reader_class()

    @classmethod
    def register_reader(cls, extension: str, reader_class: type[ImageReader]) -> None:
        """Register a custom image reader."""
        cls._readers[extension.lower()] = reader_class
