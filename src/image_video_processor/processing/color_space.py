"""Color space conversion using Strategy pattern."""

import logging
from enum import Enum
from typing import Protocol

import numpy as np

from image_video_processor.exceptions import ColorSpaceError

logger = logging.getLogger(__name__)


class ColorSpacePreset(Enum):
    """Color space conversion presets."""

    LINEAR_TO_SRGB = "linear_to_srgb"
    LINEAR_TO_REC709 = "linear_to_rec709"
    SRGB_TO_LINEAR = "srgb_to_linear"
    NO_CONVERSION = "no_conversion"


class ColorSpaceStrategy(Protocol):
    """Protocol for color space conversion strategies."""

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Convert image color space.

        Args:
            image: Input image array (H, W, C) in float32

        Returns:
            Converted image array
        """
        ...


class LinearToSRGBStrategy:
    """Strategy for converting linear to sRGB color space."""

    @staticmethod
    def _linear_to_srgb(linear: np.ndarray) -> np.ndarray:
        """Convert linear RGB to sRGB.

        Args:
            linear: Linear RGB values [0, inf]

        Returns:
            sRGB values [0, 1]
        """
        # Clamp negative values
        linear = np.maximum(linear, 0.0)

        # sRGB transfer function
        mask = linear <= 0.0031308
        srgb = np.where(
            mask,
            linear * 12.92,
            1.055 * np.power(linear, 1.0 / 2.4) - 0.055,
        )

        return np.clip(srgb, 0.0, 1.0)

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Convert linear image to sRGB.

        Args:
            image: Linear image array (H, W, C) in float32

        Returns:
            sRGB image array [0, 1]
        """
        if image.dtype != np.float32:
            image = image.astype(np.float32)

        # Apply tone mapping for HDR values
        # Simple Reinhard tone mapping
        tone_mapped = image / (1.0 + image)

        # Convert to sRGB
        srgb = self._linear_to_srgb(tone_mapped)

        return srgb


class LinearToRec709Strategy:
    """Strategy for converting linear to Rec.709 color space."""

    @staticmethod
    def _linear_to_rec709(linear: np.ndarray) -> np.ndarray:
        """Convert linear RGB to Rec.709.

        Args:
            linear: Linear RGB values [0, inf]

        Returns:
            Rec.709 values [0, 1]
        """
        linear = np.maximum(linear, 0.0)

        # Rec.709 transfer function
        mask = linear < 0.018
        rec709 = np.where(
            mask,
            linear * 4.5,
            1.099 * np.power(linear, 0.45) - 0.099,
        )

        return np.clip(rec709, 0.0, 1.0)

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Convert linear image to Rec.709.

        Args:
            image: Linear image array (H, W, C) in float32

        Returns:
            Rec.709 image array [0, 1]
        """
        if image.dtype != np.float32:
            image = image.astype(np.float32)

        # Apply tone mapping
        tone_mapped = image / (1.0 + image)

        # Convert to Rec.709
        rec709 = self._linear_to_rec709(tone_mapped)

        return rec709


class SRGBToLinearStrategy:
    """Strategy for converting sRGB to linear color space."""

    @staticmethod
    def _srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
        """Convert sRGB to linear RGB.

        Args:
            srgb: sRGB values [0, 1]

        Returns:
            Linear RGB values [0, inf]
        """
        srgb = np.clip(srgb, 0.0, 1.0)

        # Inverse sRGB transfer function
        mask = srgb <= 0.04045
        linear = np.where(
            mask,
            srgb / 12.92,
            np.power((srgb + 0.055) / 1.055, 2.4),
        )

        return linear

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Convert sRGB image to linear.

        Args:
            image: sRGB image array (H, W, C) in float32 [0, 1]

        Returns:
            Linear image array
        """
        if image.dtype != np.float32:
            image = image.astype(np.float32)

        return self._srgb_to_linear(image)


class NoConversionStrategy:
    """Strategy for no color space conversion (passthrough)."""

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Return image unchanged.

        Args:
            image: Image array (H, W, C)

        Returns:
            Same image array
        """
        return image


class ColorSpaceConverter:
    """Color space converter using Strategy pattern."""

    _strategies: dict[ColorSpacePreset, type[ColorSpaceStrategy]] = {
        ColorSpacePreset.LINEAR_TO_SRGB: LinearToSRGBStrategy,
        ColorSpacePreset.LINEAR_TO_REC709: LinearToRec709Strategy,
        ColorSpacePreset.SRGB_TO_LINEAR: SRGBToLinearStrategy,
        ColorSpacePreset.NO_CONVERSION: NoConversionStrategy,
    }

    def __init__(self, preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB):
        """Initialize color space converter.

        Args:
            preset: Color space conversion preset
        """
        strategy_class = self._strategies.get(preset)
        if strategy_class is None:
            raise ColorSpaceError(f"Unknown color space preset: {preset}")

        self._strategy = strategy_class()
        self._preset = preset

    def convert(self, image: np.ndarray) -> np.ndarray:
        """Convert image color space.

        Args:
            image: Input image array (H, W, C) in float32

        Returns:
            Converted image array
        """
        return self._strategy.convert(image)

    @classmethod
    def register_strategy(
        cls, preset: ColorSpacePreset, strategy_class: type[ColorSpaceStrategy]
    ) -> None:
        """Register a custom color space conversion strategy.

        Args:
            preset: Color space preset enum
            strategy_class: Strategy class to register
        """
        cls._strategies[preset] = strategy_class
