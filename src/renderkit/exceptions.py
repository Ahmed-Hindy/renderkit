"""Custom exceptions for the Render Kit package."""


class RenderKitError(Exception):
    """Base exception for all Render Kit errors."""

    pass


class SequenceDetectionError(RenderKitError):
    """Raised when sequence detection fails."""

    pass


class ImageReadError(RenderKitError):
    """Raised when image reading fails."""

    pass


class ColorSpaceError(RenderKitError):
    """Raised when color space conversion fails."""

    pass


class VideoEncodingError(RenderKitError):
    """Raised when video encoding fails."""

    pass


class ConfigurationError(RenderKitError):
    """Raised when configuration is invalid."""

    pass


class ConversionCancelledError(RenderKitError):
    """Raised when conversion is cancelled by the user."""

    pass
