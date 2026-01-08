"""Tests for color space conversion."""

import numpy as np
import pytest

from renderkit.processing.color_space import (
    ColorSpaceConverter,
    ColorSpaceError,
    ColorSpacePreset,
    LinearToSRGBStrategy,
    NoConversionStrategy,
)


class TestColorSpaceConverter:
    """Tests for ColorSpaceConverter."""

    def test_linear_to_srgb_conversion(self) -> None:
        """Test linear to sRGB conversion."""
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)

        # Test with linear values
        linear_image = np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32)
        srgb_image = converter.convert(linear_image)

        assert srgb_image.dtype == np.float32
        assert np.all(srgb_image >= 0.0)
        assert np.all(srgb_image <= 1.0)

    def test_no_conversion(self) -> None:
        """Test no conversion strategy."""
        converter = ColorSpaceConverter(ColorSpacePreset.NO_CONVERSION)

        test_image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
        result = converter.convert(test_image)

        np.testing.assert_array_equal(test_image, result)

    def test_hdr_tone_mapping(self) -> None:
        """Test that HDR values are tone mapped."""
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)

        # HDR values > 1.0
        hdr_image = np.array([[[10.0, 5.0, 2.0]]], dtype=np.float32)
        result = converter.convert(hdr_image)

        # Should be clamped to [0, 1]
        assert np.all(result >= 0.0)
        assert np.all(result <= 1.0)

    def test_invalid_preset(self) -> None:
        """Test error with invalid preset."""
        # This would require adding an invalid preset to the enum
        # For now, just test that valid presets work
        for preset in ColorSpacePreset:
            converter = ColorSpaceConverter(preset)
            test_image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
            if preset == ColorSpacePreset.OCIO_CONVERSION:
                with pytest.raises(ColorSpaceError):
                    converter.convert(test_image)
            elif preset == ColorSpacePreset.LINEAR_TO_REC709:
                if not _has_oiio_colorspace_candidates(
                    [
                        "Rec709",
                        "Rec.709",
                        "rec709",
                        "BT.709",
                        "bt709",
                        "Output - Rec.709",
                        "Output - Rec709",
                    ]
                ):
                    pytest.skip("Rec.709 colorspace not available in OCIO config.")
                result = converter.convert(test_image)
                assert result.shape == test_image.shape
            else:
                result = converter.convert(test_image)
                assert result.shape == test_image.shape

    def test_ocio_requires_input_space(self) -> None:
        """Test OCIO conversion requires an input space."""
        converter = ColorSpaceConverter(ColorSpacePreset.OCIO_CONVERSION)
        test_image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
        with pytest.raises(ColorSpaceError):
            converter.convert(test_image)


class TestLinearToSRGBStrategy:
    """Tests for LinearToSRGBStrategy."""

    def test_linear_to_srgb_function(self) -> None:
        """Test the linear to sRGB transfer function."""
        strategy = LinearToSRGBStrategy()

        # Test linear value 0
        linear_zero = np.array([0.0])
        srgb_zero = strategy._linear_to_srgb(linear_zero)
        assert srgb_zero[0] == 0.0

        # Test linear value 1.0
        linear_one = np.array([1.0])
        srgb_one = strategy._linear_to_srgb(linear_one)
        assert 0.0 < srgb_one[0] <= 1.0


class TestNoConversionStrategy:
    """Tests for NoConversionStrategy."""

    def test_passthrough(self) -> None:
        """Test that image passes through unchanged."""
        strategy = NoConversionStrategy()

        test_image = np.array([[[0.1, 0.5, 0.9]]], dtype=np.float32)
        result = strategy.convert(test_image)

        np.testing.assert_array_equal(test_image, result)


def _has_oiio_colorspace_candidates(candidates: list[str]) -> bool:
    try:
        import OpenImageIO as oiio
    except ImportError:
        return False

    try:
        config = oiio.ColorConfig()
        names = config.getColorSpaceNames()
    except Exception:
        return False

    if not names:
        return False

    lowered = {name.lower() for name in names}
    normalized = {name.replace("-", "_").replace(" ", "_") for name in lowered}
    for candidate in candidates:
        key = candidate.lower()
        if key in lowered:
            return True
        if key.replace("-", "_").replace(" ", "_") in normalized:
            return True

    return False
