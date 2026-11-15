"""Tests for color space conversion."""

import logging
import os
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from renderkit.processing.color_space import (
    _OIIO_COLOR_SPACE_MAP_CACHE,
    ColorSpaceConverter,
    ColorSpaceError,
    ColorSpacePreset,
    NoConversionStrategy,
    OCIOColorSpaceStrategy,
    _apply_exposure_buf,
    _apply_gamma_buf,
    get_bundled_ocio_config_path,
    get_ocio_displays,
    get_ocio_views,
    resolve_ocio_config_path,
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

    def test_linear_to_srgb_uses_bundled_config_when_ocio_env_is_invalid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test OIIO color conversion ignores an invalid OCIO environment variable."""
        monkeypatch.setenv("OCIO", "C:/does/not/exist/config.ocio")
        converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)

        linear_image = np.array([[[0.18, 0.18, 0.18]]], dtype=np.float32)
        result_buf = converter.convert_buf(_make_buf(linear_image))
        result = _buf_to_array(result_buf)

        assert result.shape == linear_image.shape
        assert os.environ["OCIO"] == "C:/does/not/exist/config.ocio"

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


class TestOCIOColorSpaceStrategyDiagnostics:
    """Tests for OCIO fallback diagnostics."""

    def test_resolve_input_space_logs_role_resolution_failures(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test role API failures are visible while preserving fallback behavior."""

        strategy = object.__new__(OCIOColorSpaceStrategy)
        strategy.config = Mock()
        strategy.config.getColorSpaceNames.return_value = ["ACEScg"]
        strategy.config.hasRole.return_value = True
        strategy.config.getRoleColorSpace.side_effect = RuntimeError("role API drift")
        strategy.config.getColorSpaceNameByRole.side_effect = RuntimeError("OIIO role API drift")

        with caplog.at_level(logging.DEBUG, logger="renderkit.processing.color_space"):
            resolved = strategy._resolve_input_space("scene_linear")

        assert resolved == "scene_linear"
        assert "Failed to resolve OCIO input role" in caplog.text
        assert "Failed to resolve OCIO role via OIIO API" in caplog.text

    def test_failure_diagnostics_records_unavailable_probe_values(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test diagnostic probe failures are captured in the final log."""

        strategy = object.__new__(OCIOColorSpaceStrategy)
        strategy.config = Mock()
        strategy.config.getMajorVersion.side_effect = RuntimeError("version unavailable")
        strategy.config.getSearchPath.side_effect = RuntimeError("search path unavailable")
        strategy.config.getColorSpaceNames.side_effect = RuntimeError("colorspaces unavailable")
        strategy.config.getRoleNames.side_effect = RuntimeError("roles unavailable")
        strategy.config.getDefaultDisplay.side_effect = RuntimeError("display unavailable")

        with caplog.at_level(logging.ERROR, logger="renderkit.processing.color_space"):
            strategy._log_ocio_failure_diagnostics(
                requested_input_space="scene_linear",
                resolved_input_space=None,
                resolved_output_space=None,
                error=RuntimeError("conversion failed"),
            )

        assert "config_version=unavailable: version unavailable" in caplog.text
        assert "search_path=unavailable: search path unavailable" in caplog.text
        assert "colorspaces_sample=['unavailable: colorspaces unavailable']" in caplog.text
        assert "roles=['unavailable: roles unavailable']" in caplog.text
        assert "default_display=unavailable: display unavailable" in caplog.text


_MINIMAL_OCIO_CONFIG = """ocio_profile_version: 2

roles:
  default: raw
  scene_linear: lin_test

displays:
  TestDisplay:
    - !<View> {name: RawView, colorspace: raw}
    - !<View> {name: DoubleGamma, colorspace: gamma2}
  SecondaryDisplay:
    - !<View> {name: AltView, colorspace: raw}

active_displays: [TestDisplay, SecondaryDisplay]
active_views: [RawView, DoubleGamma, AltView]

colorspaces:
  - !<ColorSpace>
    name: raw
    isdata: true

  - !<ColorSpace>
    name: lin_test
    isdata: false

  - !<ColorSpace>
    name: gamma2
    isdata: false
    from_reference: !<ExponentTransform> {value: [0.5, 0.5, 0.5, 1.0]}
"""


def _write_custom_ocio_config(tmp_path: Path, name: str = "custom.ocio") -> Path:
    cfg_path = tmp_path / name
    cfg_path.write_text(_MINIMAL_OCIO_CONFIG, encoding="utf-8")
    return cfg_path


class TestOCIOConfigResolutionAndInspection:
    """Tests for OCIO config resolution and display/view discovery."""

    def test_resolve_ocio_config_path_defaults_to_bundled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Return bundled config when neither explicit path nor OCIO env var is set."""
        monkeypatch.delenv("OCIO", raising=False)
        assert resolve_ocio_config_path() == get_bundled_ocio_config_path()

    def test_resolve_ocio_config_path_invalid_explicit_raises(self, tmp_path: Path) -> None:
        """Raise ColorSpaceError when explicit config path is missing or invalid."""
        missing = tmp_path / "missing.ocio"
        with pytest.raises(ColorSpaceError):
            resolve_ocio_config_path(missing)

        bad_file = tmp_path / "invalid.ocio"
        bad_file.write_text("not: a valid: ocio: config: [", encoding="utf-8")
        with pytest.raises(ColorSpaceError):
            resolve_ocio_config_path(bad_file)

    def test_resolve_ocio_config_path_valid_explicit_and_env_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Support valid explicit/env configs and warn+fallback on invalid env config."""
        custom_cfg = _write_custom_ocio_config(tmp_path)
        assert resolve_ocio_config_path(custom_cfg) == custom_cfg.resolve()

        monkeypatch.setenv("OCIO", str(custom_cfg))
        assert resolve_ocio_config_path() == custom_cfg.resolve()

        missing_env = str(tmp_path / "does_not_exist.ocio")
        monkeypatch.setenv("OCIO", missing_env)
        with caplog.at_level(logging.WARNING, logger="renderkit.processing.color_space"):
            resolved = resolve_ocio_config_path()
        assert resolved == get_bundled_ocio_config_path()
        assert os.environ["OCIO"] == missing_env
        assert "falling back to bundled config" in caplog.text

    def test_get_ocio_displays_and_views(self, tmp_path: Path) -> None:
        """Discover displays and views from both bundled and custom OCIO configs."""
        bundled_displays = get_ocio_displays()
        assert len(bundled_displays) >= 1
        first_display = bundled_displays[0]
        bundled_views = get_ocio_views(first_display)
        assert len(bundled_views) >= 1

        custom_cfg = _write_custom_ocio_config(tmp_path)
        assert get_ocio_displays(custom_cfg) == ["TestDisplay", "SecondaryDisplay"]
        assert get_ocio_views("TestDisplay", custom_cfg) == ["RawView", "DoubleGamma"]
        assert get_ocio_views("SecondaryDisplay", custom_cfg) == ["AltView"]

        with pytest.raises(ColorSpaceError):
            get_ocio_displays(tmp_path / "nope.ocio")


class TestOCIODisplayViewAndGrade:
    """Tests for OCIO display/view transforms and exposure/gamma math."""

    def test_exposure_buf_math_and_alpha_preservation(self) -> None:
        """Scale RGB by 2**exposure while leaving alpha unchanged."""
        pixels = np.array([[[0.25, 0.5, 0.125, 0.75]]], dtype=np.float32)
        buf = _make_buf(pixels)

        unchanged = _apply_exposure_buf(buf, 0.0)
        assert unchanged is buf

        brighter = _buf_to_array(_apply_exposure_buf(buf, 1.0))
        np.testing.assert_allclose(brighter, [[[0.5, 1.0, 0.25, 0.75]]], atol=1e-6)

        darker = _buf_to_array(_apply_exposure_buf(buf, -1.0))
        np.testing.assert_allclose(darker, [[[0.125, 0.25, 0.0625, 0.75]]], atol=1e-6)

        rgb_pixels = np.array([[[0.25, 0.5, 0.125]]], dtype=np.float32)
        rgb_brighter = _buf_to_array(_apply_exposure_buf(_make_buf(rgb_pixels), 2.0))
        np.testing.assert_allclose(rgb_brighter, [[[1.0, 2.0, 0.5]]], atol=1e-6)

    def test_gamma_buf_math_clamps_negatives_and_preserves_alpha(self) -> None:
        """Clamp negatives to 0, apply 1/gamma exponent to RGB, and preserve alpha."""
        pixels = np.array([[[-0.5, 0.25, 1.0, 0.4]]], dtype=np.float32)
        buf = _make_buf(pixels)

        unchanged = _apply_gamma_buf(buf, 1.0)
        assert unchanged is buf

        gamma_applied = _buf_to_array(_apply_gamma_buf(buf, 2.0))
        np.testing.assert_allclose(gamma_applied, [[[0.0, 0.5, 1.0, 0.4]]], atol=1e-6)

        with pytest.raises(ColorSpaceError):
            _apply_gamma_buf(buf, 0.0)
        with pytest.raises(ColorSpaceError):
            _apply_gamma_buf(buf, -1.5)

    def test_converter_exposure_gamma_for_non_ocio_presets(self) -> None:
        """Apply exposure before and gamma after non-OCIO strategy conversion."""
        with pytest.raises(ColorSpaceError):
            ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB, gamma=0.0)

        converter = ColorSpaceConverter(
            ColorSpacePreset.NO_CONVERSION,
            exposure=1.0,
            gamma=2.0,
        )
        # 0.125 * (2**1) = 0.25 -> 0.25**(1/2) = 0.5; alpha preserved
        pixels = np.array([[[0.125, 0.5, 0.0, 0.6]]], dtype=np.float32)
        result = _buf_to_array(converter.convert_buf(_make_buf(pixels)))
        np.testing.assert_allclose(result, [[[0.5, 1.0, 0.0, 0.6]]], atol=1e-6)

        base_srgb = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)
        graded_srgb = ColorSpaceConverter(
            ColorSpacePreset.LINEAR_TO_SRGB,
            exposure=1.0,
            gamma=1.2,
        )
        lin = np.array([[[0.18, 0.18, 0.18]]], dtype=np.float32)
        base_out = _buf_to_array(base_srgb.convert_buf(_make_buf(lin)))
        graded_out = _buf_to_array(graded_srgb.convert_buf(_make_buf(lin)))
        assert np.all(graded_out > base_out)

    def test_ocio_strategy_display_view_and_custom_config(self, tmp_path: Path) -> None:
        """Verify display/view validation, conversion, and per-config cache isolation."""
        custom_cfg = _write_custom_ocio_config(tmp_path)

        with pytest.raises(ColorSpaceError, match="Available displays"):
            OCIOColorSpaceStrategy(config_path=custom_cfg, display="NoSuchDisplay")

        with pytest.raises(ColorSpaceError, match="Available views"):
            OCIOColorSpaceStrategy(config_path=custom_cfg, display="TestDisplay", view="NoSuchView")

        with pytest.raises(ColorSpaceError):
            OCIOColorSpaceStrategy(config_path=custom_cfg, gamma=0.0)

        # Omitted view resolves to default view ("RawView"), which passes linear RGB through.
        raw_strategy = OCIOColorSpaceStrategy(
            input_space="lin_test",
            config_path=custom_cfg,
            display="TestDisplay",
        )
        assert raw_strategy._resolved_display == "TestDisplay"
        assert raw_strategy._resolved_view == "RawView"

        # DoubleGamma view raises RGB to 0.5 (sqrt); exposure=+2 multiplies 0.0625 -> 0.25 -> sqrt=0.5.
        # Post-OCIO gamma=2.0 applies another sqrt -> 0.5**0.5 = 0.70710677.
        graded_strategy = OCIOColorSpaceStrategy(
            input_space="lin_test",
            config_path=custom_cfg,
            display="TestDisplay",
            view="DoubleGamma",
            exposure=2.0,
            gamma=2.0,
        )
        src = np.array([[[0.0625, 0.0625, 0.0625]]], dtype=np.float32)
        out = _buf_to_array(graded_strategy.convert_buf(_make_buf(src)))
        np.testing.assert_allclose(out, [[[0.70710677, 0.70710677, 0.70710677]]], atol=1e-4)

        # ColorSpaceConverter routes to OCIOColorSpaceStrategy when OCIO kwargs are provided.
        converter = ColorSpaceConverter(
            ocio_config_path=custom_cfg,
            ocio_output_space="gamma2",
        )
        assert isinstance(converter.strategy, OCIOColorSpaceStrategy)
        out_cc = _buf_to_array(
            converter.convert_buf(
                _make_buf(np.array([[[0.25, 0.25, 0.25]]], dtype=np.float32)),
                input_space="lin_test",
            )
        )
        np.testing.assert_allclose(out_cc, [[[0.5, 0.5, 0.5]]], atol=1e-4)
        assert str(custom_cfg.resolve()) in _OIIO_COLOR_SPACE_MAP_CACHE

    def test_ocio_display_view_cpu_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fall back to PyOpenColorIO CPUProcessor when OIIO ociodisplay fails."""
        if oiio is None:
            pytest.skip("OpenImageIO not available")
        custom_cfg = _write_custom_ocio_config(tmp_path)
        strategy = OCIOColorSpaceStrategy(
            input_space="lin_test",
            config_path=custom_cfg,
            display="TestDisplay",
            view="DoubleGamma",
        )
        monkeypatch.setattr(oiio.ImageBufAlgo, "ociodisplay", lambda *args, **kwargs: False)

        pixels = np.array([[[0.25, 0.25, 0.25, 0.8]]], dtype=np.float32)
        out = _buf_to_array(strategy.convert_buf(_make_buf(pixels)))
        np.testing.assert_allclose(out, [[[0.5, 0.5, 0.5, 0.8]]], atol=1e-4)


def _has_oiio_colorspace_candidates(candidates: list[str]) -> bool:
    try:
        import OpenImageIO as oiio
    except ImportError:
        return False

    try:
        config = oiio.ColorConfig(str(get_bundled_ocio_config_path()))
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
