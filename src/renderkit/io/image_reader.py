"""Image reading with OpenImageIO (OIIO)."""

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import numpy as np

from renderkit import constants
from renderkit.exceptions import ImageReadError
from renderkit.io.file_info import FileInfo
from renderkit.io.file_utils import FileUtils

logger = logging.getLogger(__name__)


class ImageReader(ABC):
    """Abstract base class for image readers."""

    @abstractmethod
    def read(self, path: Path, layer: Optional[str] = None) -> np.ndarray:
        """Read an image file and return as numpy array.

        Args:
            path: Path to image file
            layer: Optional layer name to extract (for multi-layer EXRs)
        """
        pass

    @abstractmethod
    def get_file_info(self, path: Path) -> FileInfo:
        """Get consolidated file information in a single read operation."""
        pass

    @abstractmethod
    def get_layers(self, path: Path) -> list[str]:
        """Get available layers from the image file."""
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
    """Reader for all image formats supported by OpenImageIO.

    Includes caching to minimize redundant I/O operations, especially
    important for heavy EXR files accessed over network paths.
    """

    def __init__(self) -> None:
        """Initialize the reader with caching."""
        super().__init__()
        # Cache: (path, mtime) -> FileInfo
        self._file_info_cache: dict[tuple[str, float], FileInfo] = {}

    def _get_cache_key(self, path: Path) -> tuple[str, float]:
        """Generate cache key based on path and modification time."""
        try:
            mtime = os.path.getmtime(path)
            return (str(path), mtime)
        except OSError:
            # If we can't get mtime (network error, etc.), use path only
            return (str(path), 0.0)

    def get_file_info(self, path: Path) -> FileInfo:
        """Get consolidated file information in a single read operation.

        This method opens the file once and extracts all metadata,
        significantly reducing I/O operations for network files.
        Results are cached based on file path and modification time.

        Args:
            path: Path to image file

        Returns:
            FileInfo with all metadata
        """
        # Check cache first
        cache_key = self._get_cache_key(path)
        if cache_key in self._file_info_cache:
            logger.debug(f"Using cached file info for {path}")
            return self._file_info_cache[cache_key]

        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise ImageReadError("OpenImageIO library not available.") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            # Open file once and extract everything
            buf = oiio.ImageBuf(str(path))
            if buf.has_error:
                raise ImageReadError(f"OIIO failed to read {path}: {buf.geterror()}")

            spec = buf.spec()
            width = spec.width
            height = spec.height
            channels = spec.nchannels
            subimages = buf.nsubimages

            # Extract FPS metadata
            fps = None
            for key in constants.FPS_METADATA_KEYS:
                val = spec.getattribute(key)
                if val is not None:
                    try:
                        if isinstance(val, bytes):
                            val = val.decode("utf-8")
                        if isinstance(val, (list, tuple)) and len(val) == 2:
                            fps = float(val[0]) / float(val[1])
                        elif isinstance(val, str) and "/" in val:
                            parts = val.split("/")
                            if len(parts) == 2:
                                fps = float(parts[0]) / float(parts[1])
                        else:
                            fps = float(val)
                        break
                    except (ValueError, TypeError, ZeroDivisionError):
                        continue

            # Extract color space metadata
            color_space = None
            for key in constants.COLOR_SPACE_METADATA_KEYS:
                val = spec.getattribute(key)
                if val is not None:
                    if isinstance(val, bytes):
                        val = val.decode("utf-8")
                    color_space = str(val).strip()
                    break

            # Extract layers from all subimages
            layers = set()
            for i in range(subimages):
                sub_buf = oiio.ImageBuf(str(path), i, 0)
                sub_spec = sub_buf.spec()

                # Check subimage name
                part_name = sub_spec.getattribute("name")
                if part_name:
                    if isinstance(part_name, bytes):
                        part_name = part_name.decode("utf-8")
                    if part_name.lower() not in ("rgba", "beauty", "default"):
                        layers.add(part_name)
                    else:
                        layers.add("RGBA")

                # Check channel prefixes
                for channel_name in sub_spec.channelnames:
                    if "." in channel_name:
                        layers.add(channel_name.rsplit(".", 1)[0])
                    else:
                        if not part_name or part_name.lower() in ("rgba", "beauty", "default"):
                            layers.add("RGBA")

            # Sort layers with RGBA first
            layers_list = sorted(layers)
            if "RGBA" in layers_list:
                layers_list.remove("RGBA")
                layers_list.insert(0, "RGBA")

            # Create FileInfo and cache it
            file_info = FileInfo(
                width=width,
                height=height,
                channels=channels,
                layers=layers_list,
                fps=fps,
                color_space=color_space,
                subimages=subimages,
            )

            self._file_info_cache[cache_key] = file_info
            logger.debug(f"Cached file info for {path}")
            return file_info

        except Exception as e:
            raise ImageReadError(f"Failed to read file info with OIIO: {path} - {e}") from e

    def read(self, path: Path, layer: Optional[str] = None) -> np.ndarray:
        """Read an image using OIIO ImageBuf.

        Args:
            path: Path to image file
            layer: Optional layer name to extract (e.g., "diffuse")

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
            # First, find which subimage (part) contains the requested layer
            subimage_index = 0
            if layer and layer != "RGBA":
                # Quick scan to find the part
                temp_buf = oiio.ImageBuf(str(path))
                for i in range(temp_buf.nsubimages):
                    sub_buf = oiio.ImageBuf(str(path), i, 0)
                    spec = sub_buf.spec()
                    part_name = spec.getattribute("name")
                    if part_name:
                        if isinstance(part_name, bytes):
                            part_name = part_name.decode("utf-8")
                        if part_name == layer:
                            subimage_index = i
                            break

                    # Also check channel prefixes in this part
                    if any(c.startswith(f"{layer}.") for c in spec.channelnames):
                        subimage_index = i
                        break

            # Load the correct subimage
            buf = oiio.ImageBuf(str(path), subimage_index, 0)
            if buf.has_error:
                raise ImageReadError(
                    f"OIIO failed to read {path} (part {subimage_index}): {buf.geterror()}"
                )

            # Handle layer selection for multi-layer EXRs within the part
            spec = buf.spec()
            if layer and layer != "RGBA":
                channel_names = spec.channelnames
                # Check if we need to filter channels (if it's a grouped layer in this part)
                indices = []
                new_names = []
                found_exact_match = False

                # If the part name IS the layer, we usually want all channels of this part
                part_name = spec.getattribute("name")
                if part_name and isinstance(part_name, bytes):
                    part_name = part_name.decode("utf-8")

                if part_name == layer:
                    # Keep all channels but clean up prefixes if they exist
                    for i, name in enumerate(channel_names):
                        indices.append(i)
                        new_names.append(name.split(".", 1)[1] if "." in name else name)
                    found_exact_match = True
                else:
                    # Look for prefixed channels
                    for i, name in enumerate(channel_names):
                        if name.startswith(f"{layer}."):
                            indices.append(i)
                            new_names.append(name.split(".", 1)[1])
                            found_exact_match = True

                if found_exact_match and indices:
                    buf = oiio.ImageBufAlgo.channels(buf, tuple(indices), tuple(new_names))
                    if buf.has_error:
                        raise ImageReadError(f"Failed to extract layer {layer}: {buf.geterror()}")
                elif subimage_index == 0 and not found_exact_match:
                    logger.warning(
                        f"Layer {layer} not found in any part of {path}, falling back to beauty."
                    )

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

    def get_layers(self, path: Path) -> list[str]:
        """Get available layers from the image file, including multi-part AOVs.

        Uses cached file info to avoid redundant I/O.
        """
        try:
            file_info = self.get_file_info(path)
            return file_info.layers
        except ImageReadError:
            return ["RGBA"]

    def get_channels(self, path: Path) -> int:
        """Get channel count using OIIO.

        Uses cached file info to avoid redundant I/O.
        """
        try:
            file_info = self.get_file_info(path)
            return file_info.channels
        except ImageReadError:
            return 3

    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get resolution using OIIO.

        Uses cached file info to avoid redundant I/O.
        """
        try:
            file_info = self.get_file_info(path)
            return (file_info.width, file_info.height)
        except ImageReadError:
            return (0, 0)

    def get_metadata_fps(self, path: Path) -> Optional[float]:
        """Get FPS from OIIO metadata.

        Uses cached file info to avoid redundant I/O.
        """
        try:
            file_info = self.get_file_info(path)
            return file_info.fps
        except ImageReadError:
            return None

    def get_metadata_color_space(self, path: Path) -> Optional[str]:
        """Get color space from OIIO metadata.

        Uses cached file info to avoid redundant I/O.
        """
        try:
            file_info = self.get_file_info(path)
            return file_info.color_space
        except ImageReadError:
            return None


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
