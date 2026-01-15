"""Tests for color space conversion."""

import numpy as np
import pytest

from renderkit.processing.color_space import (
    ColorSpaceConverter,
    ColorSpaceError,
    ColorSpacePreset,
    NoConversionStrategy,
)

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None


def _make_buf(pixels: np.ndarray):
    if oiio is None:
        pytest.skip("OpenImageIO not available")
    h, w, c = pixels.shape
    spec = oiio.ImageSpec(w, h, c, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    buf.set_pixels(oiio.ROI(), pixels.astype(np.float32))
    return buf


def _buf_to_array(buf):
    pixels = buf.get_pixels(oiio.FLOAT)
    if pixels is None or pixels.size == 0:
        return None
    spec = buf.spec()
    if pixels.ndim == 1:
        return pixels.reshape((spec.height, spec.width, spec.nchannels))
    return pixels


class TestColorSpaceConverter:
    """Tests for ColorSpaceConverter."""

    def test_linear_to_srgb_conversion(self) -> None:
        """Test linear to sRGB conversion."""
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)

        # Test with linear values
        linear_image = np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32)
        buf = _make_buf(linear_image)
        srgb_buf = converter.convert_buf(buf)
        srgb_image = _buf_to_array(srgb_buf)

        assert srgb_image.dtype == np.float32
        assert np.all(srgb_image >= 0.0)
        assert np.all(srgb_image <= 1.0)

    def test_no_conversion(self) -> None:
        """Test no conversion strategy."""
        converter = ColorSpaceConverter(ColorSpacePreset.NO_CONVERSION)

        test_image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
        buf = _make_buf(test_image)
        result_buf = converter.convert_buf(buf)
        result = _buf_to_array(result_buf)

        np.testing.assert_array_equal(test_image, result)

    def test_hdr_tone_mapping(self) -> None:
        """Test that HDR values are tone mapped."""
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)

        # HDR values > 1.0
        hdr_image = np.array([[[10.0, 5.0, 2.0]]], dtype=np.float32)
        buf = _make_buf(hdr_image)
        result_buf = converter.convert_buf(buf)
        result = _buf_to_array(result_buf)

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
                    converter.convert_buf(_make_buf(test_image))
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
                result_buf = converter.convert_buf(_make_buf(test_image))
                result = _buf_to_array(result_buf)
                assert result.shape == test_image.shape
            else:
                result_buf = converter.convert_buf(_make_buf(test_image))
                result = _buf_to_array(result_buf)
                assert result.shape == test_image.shape

    def test_ocio_requires_input_space(self) -> None:
        """Test OCIO conversion requires an input space."""
        converter = ColorSpaceConverter(ColorSpacePreset.OCIO_CONVERSION)
        test_image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
        with pytest.raises(ColorSpaceError):
            converter.convert_buf(_make_buf(test_image))


class TestNoConversionStrategy:
    """Tests for NoConversionStrategy."""

    def test_passthrough(self) -> None:
        """Test that image passes through unchanged."""
        strategy = NoConversionStrategy()

        test_image = np.array([[[0.1, 0.5, 0.9]]], dtype=np.float32)
        buf = _make_buf(test_image)
        result_buf = strategy.convert_buf(buf)
        result = _buf_to_array(result_buf)

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
