"""Image reading with OpenImageIO (OIIO)."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from renderkit import constants
from renderkit.exceptions import ImageReadError
from renderkit.io.file_info import FileInfo
from renderkit.io.file_utils import FileUtils
from renderkit.io.oiio_cache import get_shared_image_cache

logger = logging.getLogger(__name__)


class ImageReader(ABC):
    """Abstract base class for image readers."""

    @abstractmethod
    def read_imagebuf(
        self,
        path: Path,
        layer: Optional[str] = None,
        layer_map: Optional[dict[str, "LayerMapEntry"]] = None,
    ) -> Any:
        """Read an image file and return as an OIIO ImageBuf."""
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


@dataclass(frozen=True)
class LayerMapEntry:
    """Mapping metadata for extracting a layer from a subimage."""

    subimage_index: int
    channel_indices: Optional[tuple[int, ...]] = None


class OIIOReader(ImageReader):
    """Reader for all image formats supported by OpenImageIO.

    Includes caching to minimize redundant I/O operations, especially
    important for heavy EXR files accessed over network paths.
    """

    def __init__(self, image_cache: Optional[Any] = None) -> None:
        """Initialize the reader with caching."""
        super().__init__()
        # Cache: (path, mtime) -> FileInfo
        self._file_info_cache: dict[tuple[str, float], FileInfo] = {}
        # Cache: (path, mtime) -> layer map
        self._layer_map_cache: dict[tuple[str, float], dict[str, LayerMapEntry]] = {}
        self._image_cache = image_cache

    def _get_image_cache(self):
        if self._image_cache is None:
            self._image_cache = get_shared_image_cache()
        return self._image_cache

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
            cache = self._get_image_cache()
            spec = None
            if cache is not None:
                spec = cache.get_imagespec(str(path), 0)
                if cache.has_error or spec is None or spec.width == 0 or spec.height == 0:
                    spec = None

            if spec is None:
                # Open file once and extract everything
                buf = oiio.ImageBuf(str(path))
                if buf.has_error:
                    raise ImageReadError(f"OIIO failed to read {path}: {buf.geterror()}")

                spec = buf.spec()
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                subimages = buf.nsubimages
            else:
                width = spec.width
                height = spec.height
                channels = spec.nchannels
                subimages = spec.getattribute("oiio:subimages") or 1
                subimages = int(subimages)

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
                if i == 0:
                    sub_spec = spec
                else:
                    sub_spec = None
                    if cache is not None:
                        sub_spec = cache.get_imagespec(str(path), i)
                        if cache.has_error or sub_spec is None:
                            sub_spec = None
                    if sub_spec is None:
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

    def get_layer_map(self, path: Path) -> dict[str, LayerMapEntry]:
        """Precompute a mapping of layer names to subimage indices for fast lookup."""
        cache_key = self._get_cache_key(path)
        cached = self._layer_map_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise ImageReadError("OpenImageIO library not available.") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            cache = self._get_image_cache()
            spec0 = None
            if cache is not None:
                spec0 = cache.get_imagespec(str(path), 0)
                if cache.has_error or spec0 is None or spec0.width == 0 or spec0.height == 0:
                    spec0 = None

            if spec0 is None:
                temp_buf = oiio.ImageBuf(str(path))
                if temp_buf.has_error:
                    raise ImageReadError(f"OIIO failed to read {path}: {temp_buf.geterror()}")
                subimages = temp_buf.nsubimages
            else:
                subimages = spec0.getattribute("oiio:subimages") or 1
                subimages = int(subimages)
            layer_map: dict[str, LayerMapEntry] = {}
            default_entry: Optional[LayerMapEntry] = None

            for i in range(subimages):
                if spec0 is not None and i == 0:
                    sub_spec = spec0
                else:
                    sub_spec = None
                    if cache is not None:
                        sub_spec = cache.get_imagespec(str(path), i)
                        if cache.has_error or sub_spec is None:
                            sub_spec = None
                    if sub_spec is None:
                        sub_buf = oiio.ImageBuf(str(path), i, 0)
                        sub_spec = sub_buf.spec()
                part_name = sub_spec.getattribute("name")
                if isinstance(part_name, bytes):
                    part_name = part_name.decode("utf-8")

                if part_name and part_name.lower() not in ("rgba", "beauty", "default"):
                    if part_name not in layer_map:
                        layer_map[part_name] = LayerMapEntry(i, None)
                elif default_entry is None:
                    default_entry = LayerMapEntry(i, None)

                prefix_indices: dict[str, list[int]] = {}
                for idx, channel_name in enumerate(sub_spec.channelnames):
                    if "." in channel_name:
                        prefix, _ = channel_name.split(".", 1)
                        prefix_indices.setdefault(prefix, []).append(idx)

                for prefix, indices in prefix_indices.items():
                    if prefix not in layer_map:
                        layer_map[prefix] = LayerMapEntry(i, tuple(indices))

            if "RGBA" not in layer_map and default_entry is not None:
                layer_map["RGBA"] = default_entry

            self._layer_map_cache[cache_key] = layer_map
            return layer_map

        except Exception as e:
            raise ImageReadError(f"Failed to build layer map with OIIO: {path} - {e}") from e

    def read_imagebuf(
        self,
        path: Path,
        layer: Optional[str] = None,
        layer_map: Optional[dict[str, LayerMapEntry]] = None,
    ):
        """Read an image using OIIO ImageBuf and return the ImageBuf."""
        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise ImageReadError("OpenImageIO library not available.") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            # First, find which subimage (part) contains the requested layer
            subimage_index = 0
            channel_indices: Optional[tuple[int, ...]] = None
            use_layer_map = False

            if layer_map is not None:
                lookup = layer if layer else "RGBA"
                entry = layer_map.get(lookup)
                if entry is not None:
                    subimage_index = entry.subimage_index
                    channel_indices = entry.channel_indices
                    use_layer_map = True

            if not use_layer_map and layer and layer != "RGBA":
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
            if not use_layer_map and layer and layer != "RGBA":
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

            if use_layer_map and channel_indices:
                buf = oiio.ImageBufAlgo.channels(buf, channel_indices)
                if buf.has_error:
                    raise ImageReadError(f"Failed to extract layer {layer}: {buf.geterror()}")

            # Ensure float32 for downstream processing
            spec = buf.spec()
            if spec.format != oiio.FLOAT:
                float_spec = oiio.ImageSpec(
                    spec.width,
                    spec.height,
                    spec.nchannels,
                    oiio.FLOAT,
                )
                float_buf = oiio.ImageBuf(float_spec)
                if not oiio.ImageBufAlgo.copy(float_buf, buf):
                    raise ImageReadError(f"Failed to convert {path} to float32: {buf.geterror()}")
                buf = float_buf

            return buf

        except Exception as e:
            raise ImageReadError(f"Failed to read image with OIIO: {path} - {e}") from e

    def read_subimagebuf(self, path: Path, subimage_index: int):
        """Read a specific subimage as an OIIO ImageBuf."""
        try:
            import OpenImageIO as oiio
        except ImportError as e:
            raise ImageReadError("OpenImageIO library not available.") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            cache = self._get_image_cache()
            if cache is not None:
                spec = cache.get_imagespec(str(path), subimage_index)
                if not cache.has_error and spec is not None and spec.width and spec.height:
                    roi = oiio.ROI(
                        0,
                        spec.width,
                        0,
                        spec.height,
                        0,
                        1,
                        0,
                        spec.nchannels,
                    )
                    pixels = cache.get_pixels(str(path), subimage_index, 0, roi, oiio.FLOAT)
                    if pixels is not None:
                        float_spec = oiio.ImageSpec(
                            spec.width,
                            spec.height,
                            spec.nchannels,
                            oiio.FLOAT,
                        )
                        buf = oiio.ImageBuf(float_spec)
                        if buf.set_pixels(roi, pixels):
                            return buf

            buf = oiio.ImageBuf(str(path), subimage_index, 0)
            if buf.has_error:
                raise ImageReadError(
                    f"OIIO failed to read {path} (part {subimage_index}): {buf.geterror()}"
                )

            spec = buf.spec()
            if spec.format != oiio.FLOAT:
                float_spec = oiio.ImageSpec(
                    spec.width,
                    spec.height,
                    spec.nchannels,
                    oiio.FLOAT,
                )
                float_buf = oiio.ImageBuf(float_spec)
                if not oiio.ImageBufAlgo.copy(float_buf, buf):
                    raise ImageReadError(f"Failed to convert {path} to float32: {buf.geterror()}")
                buf = float_buf

            return buf

        except Exception as e:
            raise ImageReadError(
                f"Failed to read subimage {subimage_index} with OIIO: {path} - {e}"
            ) from e

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
    def create_reader(cls, path: Path, image_cache: Optional[Any] = None) -> ImageReader:
        """Create an OIIO reader for the given file."""
        extension = FileUtils.get_file_extension(path)
        reader_class = cls._readers.get(extension, OIIOReader)
        try:
            return reader_class(image_cache=image_cache)
        except TypeError:
            return reader_class()

    @classmethod
    def register_reader(cls, extension: str, reader_class: type[ImageReader]) -> None:
        """Register a custom image reader."""
        cls._readers[extension.lower()] = reader_class
