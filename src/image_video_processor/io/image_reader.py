"""Image reading with Factory pattern for different image formats."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from image_video_processor.exceptions import ImageReadError
from image_video_processor.io.file_utils import FileUtils

logger = logging.getLogger(__name__)


class ImageReader(ABC):
    """Abstract base class for image readers."""

    @abstractmethod
    def read(self, path: Path) -> np.ndarray:
        """Read an image file and return as numpy array.

        Args:
            path: Path to the image file

        Returns:
            Image as numpy array (H, W, C) in float32 format [0.0, 1.0] or HDR range

        Raises:
            ImageReadError: If image cannot be read
        """
        pass

    @abstractmethod
    def get_channels(self, path: Path) -> int:
        """Get the number of channels in the image.

        Args:
            path: Path to the image file

        Returns:
            Number of channels
        """
        pass

    @abstractmethod
    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get the resolution of the image.

        Args:
            path: Path to the image file

        Returns:
            Tuple of (width, height)
        """
        pass


class EXRReader(ImageReader):
    """Reader for EXR files using OpenEXR."""

    def read(self, path: Path) -> np.ndarray:
        """Read an EXR file.

        Args:
            path: Path to the EXR file

        Returns:
            Image as numpy array (H, W, C) in float32 format, HDR range
        """
        try:
            import Imath
            import OpenEXR
        except ImportError as e:
            raise ImageReadError(
                "OpenEXR library not available. Install with: pip install OpenEXR Imath"
            ) from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            exr_file = OpenEXR.InputFile(str(path))
            header = exr_file.header()

            # Get image dimensions
            dw = header["dataWindow"]
            width = dw.max.x - dw.min.x + 1
            height = dw.max.y - dw.min.y + 1

            # Read channels
            channels = header["channels"].keys()
            channel_data = {}

            for channel in channels:
                channel_str = exr_file.channel(channel, Imath.PixelType(Imath.PixelType.FLOAT))
                channel_array = np.frombuffer(channel_str, dtype=np.float32)
                channel_array = channel_array.reshape((height, width))
                channel_data[channel] = channel_array

            # Determine output channels (prefer RGB/RGBA)
            if "R" in channels and "G" in channels and "B" in channels:
                if "A" in channels:
                    # RGBA
                    image = np.stack(
                        [
                            channel_data["R"],
                            channel_data["G"],
                            channel_data["B"],
                            channel_data["A"],
                        ],
                        axis=-1,
                    )
                else:
                    # RGB
                    image = np.stack(
                        [channel_data["R"], channel_data["G"], channel_data["B"]],
                        axis=-1,
                    )
            else:
                # Use first available channel or convert to grayscale
                first_channel = list(channels)[0]
                image = channel_data[first_channel][:, :, np.newaxis]

            exr_file.close()
            return image

        except Exception as e:
            raise ImageReadError(f"Failed to read EXR file: {path}") from e

    def get_channels(self, path: Path) -> int:
        """Get the number of channels in the EXR file."""
        try:
            import OpenEXR
        except ImportError as e:
            raise ImageReadError("OpenEXR library not available") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            exr_file = OpenEXR.InputFile(str(path))
            header = exr_file.header()
            channels = header["channels"].keys()
            exr_file.close()

            if "R" in channels and "G" in channels and "B" in channels:
                return 4 if "A" in channels else 3
            return 1

        except Exception as e:
            raise ImageReadError(f"Failed to read EXR header: {path}") from e

    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get the resolution of the EXR file."""
        try:
            import OpenEXR
        except ImportError as e:
            raise ImageReadError("OpenEXR library not available") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            exr_file = OpenEXR.InputFile(str(path))
            header = exr_file.header()
            dw = header["dataWindow"]
            width = dw.max.x - dw.min.x + 1
            height = dw.max.y - dw.min.y + 1
            exr_file.close()
            return (width, height)

        except Exception as e:
            raise ImageReadError(f"Failed to read EXR header: {path}") from e


class StandardImageReader(ImageReader):
    """Reader for standard image formats (PNG, JPEG) using imageio."""

    def read(self, path: Path) -> np.ndarray:
        """Read a standard image file.

        Args:
            path: Path to the image file

        Returns:
            Image as numpy array (H, W, C) in float32 format [0.0, 1.0]
        """
        try:
            import imageio
        except ImportError as e:
            raise ImageReadError("imageio library not available") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            image = imageio.imread(str(path))
            # Convert to float32 and normalize to [0, 1]
            if image.dtype == np.uint8:
                image = image.astype(np.float32) / 255.0
            elif image.dtype == np.uint16:
                image = image.astype(np.float32) / 65535.0
            else:
                image = image.astype(np.float32)

            # Ensure 3D array (H, W, C)
            if len(image.shape) == 2:
                image = image[:, :, np.newaxis]
            elif len(image.shape) == 3 and image.shape[2] > 4:
                # Handle unusual channel counts
                image = image[:, :, :3]

            return image

        except Exception as e:
            raise ImageReadError(f"Failed to read image file: {path}") from e

    def get_channels(self, path: Path) -> int:
        """Get the number of channels in the image."""
        try:
            import imageio
        except ImportError as e:
            raise ImageReadError("imageio library not available") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            image = imageio.imread(str(path))
            if len(image.shape) == 2:
                return 1
            return image.shape[2]

        except Exception as e:
            raise ImageReadError(f"Failed to read image: {path}") from e

    def get_resolution(self, path: Path) -> tuple[int, int]:
        """Get the resolution of the image."""
        try:
            import imageio
        except ImportError as e:
            raise ImageReadError("imageio library not available") from e

        if not path.exists():
            raise ImageReadError(f"File does not exist: {path}")

        try:
            image = imageio.imread(str(path))
            return (image.shape[1], image.shape[0])

        except Exception as e:
            raise ImageReadError(f"Failed to read image: {path}") from e


class ImageReaderFactory:
    """Factory for creating appropriate image readers."""

    _readers: dict[str, type[ImageReader]] = {
        "exr": EXRReader,
        "png": StandardImageReader,
        "jpg": StandardImageReader,
        "jpeg": StandardImageReader,
    }

    @classmethod
    def create_reader(cls, path: Path) -> ImageReader:
        """Create an appropriate image reader for the given file.

        Args:
            path: Path to the image file

        Returns:
            ImageReader instance

        Raises:
            ImageReadError: If no reader is available for the file type
        """
        extension = FileUtils.get_file_extension(path)
        reader_class = cls._readers.get(extension)

        if reader_class is None:
            raise ImageReadError(
                f"No reader available for file type: {extension}. "
                f"Supported types: {list(cls._readers.keys())}"
            )

        return reader_class()

    @classmethod
    def register_reader(cls, extension: str, reader_class: type[ImageReader]) -> None:
        """Register a custom image reader.

        Args:
            extension: File extension (without dot)
            reader_class: Reader class to register
        """
        cls._readers[extension.lower()] = reader_class
