"""Custom exceptions for the image video processor package."""


class ImageVideoProcessorError(Exception):
    """Base exception for all image video processor errors."""

    pass


class SequenceDetectionError(ImageVideoProcessorError):
    """Raised when sequence detection fails."""

    pass


class ImageReadError(ImageVideoProcessorError):
    """Raised when image reading fails."""

    pass


class ColorSpaceError(ImageVideoProcessorError):
    """Raised when color space conversion fails."""

    pass


class VideoEncodingError(ImageVideoProcessorError):
    """Raised when video encoding fails."""

    pass


class ConfigurationError(ImageVideoProcessorError):
    """Raised when configuration is invalid."""

    pass

