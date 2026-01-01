"""Color space conversion using Strategy pattern."""

import logging
from enum import Enum
from typing import Protocol

import numpy as np

from renderkit import constants
from renderkit.exceptions import ColorSpaceError

logger = logging.getLogger(__name__)


class ColorSpacePreset(Enum):
    """Color space conversion presets."""

    LINEAR_TO_SRGB = "linear_to_srgb"
    LINEAR_TO_REC709 = "linear_to_rec709"
    SRGB_TO_LINEAR = "srgb_to_linear"
    NO_CONVERSION = "no_conversion"
    OCIO_CONVERSION = "ocio_conversion"


class ColorSpaceStrategy(Protocol):
    """Protocol for color space conversion strategies."""

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert image color space.

        Args:
            image: Input image array (H, W, C) in float32
            input_space: Optional name of input color space

        Returns:
            Converted image array
        """
        ...


class OCIOColorSpaceStrategy:
    """Strategy for converting using OpenColorIO."""

    def __init__(self) -> None:
        self.processor = None
        self.config = None
        try:
            import PyOpenColorIO as OCIO

            try:
                self.config = OCIO.GetCurrentConfig()
            except Exception as e:
                logger.warning(f"Failed to get OCIO config: {e}")
                self.config = None
        except ImportError:
            logger.warning("PyOpenColorIO not found. OCIO conversion disabled.")

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert image using OCIO.

        Args:
            image: Input image array (H, W, C) in float32
            input_space: Name of input color space (e.g. 'ACES - ACEScg')

        Returns:
            Converted image array
        """
        if not self.config or not input_space:
            # Fallback to linear-to-srgb if OCIO not available or input space unknown
            logger.warning(
                "OCIO not active or input space unknown. Falling back to simple Linear->sRGB."
            )
            return LinearToSRGBStrategy().convert(image)

        try:
            # Determine output space (assume sRGB for now, could be configurable)
            # Determine output space (assume sRGB for now, could be configurable)
            # Common display spaces in OCIO configs
            output_candidates = constants.OCIO_OUTPUT_CANDIDATES
            output_space = None

            # Simple heuristic matching
            all_spaces = self.config.getColorSpaceNames()
            for candidate in output_candidates:
                if candidate in all_spaces:
                    output_space = candidate
                    break

            if not output_space:
                # Try finding a display view
                display = self.config.getDefaultDisplay()
                view = self.config.getDefaultView(display)
                output_space = self.config.getDisplayViewColorSpaceName(display, view)

            if not output_space:
                logger.warning("Could not find suitable OCIO output space. Falling back.")
                return LinearToSRGBStrategy().convert(image)

            logger.info(f"OCIO Conversion: '{input_space}' -> '{output_space}'")

            processor = self.config.getProcessor(input_space, output_space)
            cpu_processor = processor.getDefaultCPUProcessor()

            # OCIO expects RGBA usually, or RGB.
            # It processes in place or returns new.
            # image is H, W, C

            # Ensure float32
            if image.dtype != np.float32:
                image = image.astype(np.float32)

            height, width, channels = image.shape

            # Flatten for OCIO
            flat_image = image.reshape(-1, channels)

            # Handle 3 channel vs 4 channel
            if channels == 3:
                # OCIO python bindings might expect RGBAPacked or RGBPacked depending on version
                # Usually applyRGB works on packed pixel data
                cpu_processor.applyRGB(flat_image)

            elif channels == 4:
                cpu_processor.applyRGBA(flat_image)

            return flat_image.reshape(height, width, channels)

        except Exception as e:
            logger.error(f"OCIO conversion error: {e}. Falling back.")
            return LinearToSRGBStrategy().convert(image)


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

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert linear image to sRGB.

        Args:
            image: Linear image array (H, W, C) in float32
            input_space: Ignored for fixed strategy

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

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert linear image to Rec.709.

        Args:
            image: Linear image array (H, W, C) in float32
            input_space: Ignored

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

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert sRGB image to linear.

        Args:
            image: sRGB image array (H, W, C) in float32 [0, 1]
            input_space: Ignored

        Returns:
            Linear image array
        """
        if image.dtype != np.float32:
            image = image.astype(np.float32)

        return self._srgb_to_linear(image)


class NoConversionStrategy:
    """Strategy for no color space conversion (passthrough)."""

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Return image unchanged.

        Args:
            image: Image array (H, W, C)
            input_space: Ignored

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
        ColorSpacePreset.OCIO_CONVERSION: OCIOColorSpaceStrategy,
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

    def convert(self, image: np.ndarray, input_space: str = None) -> np.ndarray:
        """Convert image color space.

        Args:
            image: Input image array (H, W, C) in float32
            input_space: Optional name of detected input space (used by OCIO strategy)

        Returns:
            Converted image array
        """
        return self._strategy.convert(image, input_space=input_space)

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
