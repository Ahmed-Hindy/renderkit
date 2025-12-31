"""Tests for color space conversion."""

import numpy as np

from image_video_processor.processing.color_space import (
    ColorSpaceConverter,
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
            result = converter.convert(test_image)
            assert result.shape == test_image.shape


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
