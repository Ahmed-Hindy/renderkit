"""Dataclass for consolidated file information."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FileInfo:
    """Consolidated information about an image file.

    This dataclass holds all metadata that can be extracted from a single
    file read operation, reducing redundant I/O operations especially for
    network files.
    """

    width: int
    """Image width in pixels."""

    height: int
    """Image height in pixels."""

    channels: int
    """Number of color channels."""

    layers: list[str]
    """Available layers/AOVs in the file."""

    fps: Optional[float] = None
    """Frame rate from metadata, if available."""

    color_space: Optional[str] = None
    """Color space from metadata, if available."""

    subimages: int = 1
    """Number of subimages/parts in the file."""

    pixel_aspect: float = 1.0
    """Pixel aspect ratio from metadata, defaulting to 1.0."""

    display_window: Optional[tuple[int, int, int, int]] = None
    """Display window (x, y, width, height) in pixels, if available."""

    data_window: Optional[tuple[int, int, int, int]] = None
    """Data window (x, y, width, height) in pixels, if available."""

    attributes: dict[str, object] = field(default_factory=dict)
    """Scalar extra attributes extracted from the image specification."""
