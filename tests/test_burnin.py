import pytest

from renderkit.core.config import BurnInConfig, BurnInElement
from renderkit.processing.burnin import BurnInProcessor


def test_burnin_processor_initialization():
    processor = BurnInProcessor()
    assert processor is not None


def test_token_replacement():
    processor = BurnInProcessor()
    metadata = {
        "frame": 101,
        "file": "shot_01.0101.exr",
        "fps": 24.0,
        "layer": "diffuse",
        "colorspace": "ACEScg",
    }

    template = (
        "Frame: {frame} | File: {file} | FPS: {fps:.1f} | Layer: {layer} | Space: {colorspace}"
    )
    expected = "Frame: 101 | File: shot_01.0101.exr | FPS: 24.0 | Layer: diffuse | Space: ACEScg"

    result = processor._replace_tokens(template, metadata)
    assert result == expected


def test_token_replacement_missing_token_raises():
    processor = BurnInProcessor()

    with pytest.raises(ValueError, match="Missing burn-in metadata token"):
        processor._replace_tokens("Frame: {frame} | Shot: {shot}", {"frame": 101})


def test_apply_burnins_logic():
    # This test verifies that the logic flows correctly.
    # Mocking OIIO might be complex, so we check if the processor handles empty configs gracefully.
    processor = BurnInProcessor()

    # Create a dummy image buffer (mock or minimal)
    try:
        import OpenImageIO as oiio

        spec = oiio.ImageSpec(100, 100, 3, oiio.FLOAT)
        buf = oiio.ImageBuf(spec)
    except ImportError:
        pytest.skip("OpenImageIO not available for full buffer test")

    config = BurnInConfig(elements=[BurnInElement(text_template="Test {frame}", x=10, y=10)])

    metadata = {"frame": 1}

    # We just want to ensure it doesn't crash
    result_buf = processor.apply_burnins(buf, metadata, config)
    assert result_buf is buf


def test_burnin_six_zones_placement_and_stacking() -> None:
    """Verify all 6 named HUD zones place text in expected regions and stack cleanly."""
    try:
        import numpy as np
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from types import SimpleNamespace

    processor = BurnInProcessor()
    width, height = 600, 300
    spec = oiio.ImageSpec(width, height, 3, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    oiio.ImageBufAlgo.fill(buf, (0.0, 0.0, 0.0))

    def _el(template: str, zone: str, font_size: int = 16):
        return SimpleNamespace(
            text_template=template,
            x=0,
            y=0,
            font="",
            font_size=font_size,
            color=(1.0, 1.0, 1.0),
            alignment="left",
            zone=zone,
        )

    config = SimpleNamespace(
        elements=[
            _el("TL1", "top_left"),
            _el("TL2", "top_left"),
            _el("TC", "top_center"),
            _el("TR", "top_right"),
            _el("BL1", "bottom_left"),
            _el("BL2", "bottom_left"),
            _el("BC", "bottom_center"),
            _el("BR", "bottom_right"),
        ],
        use_background=False,
        background_opacity=0,
    )

    processor.apply_burnins(buf, {}, config)
    pixels = buf.get_pixels(oiio.FLOAT)

    # Check each of the 6 regions has lit pixels
    assert np.max(pixels[: height // 2, : width // 3, :]) > 0.5  # top_left
    assert np.max(pixels[: height // 2, width // 3 : 2 * width // 3, :]) > 0.5  # top_center
    assert np.max(pixels[: height // 2, 2 * width // 3 :, :]) > 0.5  # top_right
    assert np.max(pixels[height // 2 :, : width // 3, :]) > 0.5  # bottom_left
    assert np.max(pixels[height // 2 :, width // 3 : 2 * width // 3, :]) > 0.5  # bottom_center
    assert np.max(pixels[height // 2 :, 2 * width // 3 :, :]) > 0.5  # bottom_right

    # Verify stacking in top_left creates two separated horizontal bands of lit rows
    tl_rows = np.where(np.max(pixels[: height // 2, : width // 3, :], axis=(1, 2)) > 0.5)[0]
    gaps = np.where(np.diff(tl_rows) > 1)[0]
    assert len(gaps) >= 1


def test_burnin_top_and_bottom_background_bars() -> None:
    """Background bars should darken only the active top/bottom bands."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from types import SimpleNamespace

    processor = BurnInProcessor()
    width, height = 400, 200

    # Top-only element
    top_buf = oiio.ImageBuf(oiio.ImageSpec(width, height, 3, oiio.FLOAT))
    oiio.ImageBufAlgo.fill(top_buf, (1.0, 1.0, 1.0))
    top_cfg = SimpleNamespace(
        elements=[
            SimpleNamespace(
                text_template="TOP",
                x=0,
                y=0,
                font="",
                font_size=16,
                color=(0.0, 0.0, 0.0),
                alignment="left",
                zone="top_left",
            )
        ],
        use_background=True,
        background_opacity=50,
    )
    processor.apply_burnins(top_buf, {}, top_cfg)
    top_pixels = top_buf.get_pixels(oiio.FLOAT)
    # Row 2 (inside top bar, away from text at x=width-2) should be darkened to 0.5
    assert top_pixels[2, width - 2, 0] == pytest.approx(0.5, abs=1e-4)
    # Bottom row should remain untouched (1.0)
    assert top_pixels[height - 2, width - 2, 0] == pytest.approx(1.0, abs=1e-4)

    # Bottom-only element
    bot_buf = oiio.ImageBuf(oiio.ImageSpec(width, height, 3, oiio.FLOAT))
    oiio.ImageBufAlgo.fill(bot_buf, (1.0, 1.0, 1.0))
    bot_cfg = SimpleNamespace(
        elements=[
            SimpleNamespace(
                text_template="BOT",
                x=0,
                y=0,
                font="",
                font_size=16,
                color=(0.0, 0.0, 0.0),
                alignment="right",
                zone="bottom_right",
            )
        ],
        use_background=True,
        background_opacity=40,
    )
    processor.apply_burnins(bot_buf, {}, bot_cfg)
    bot_pixels = bot_buf.get_pixels(oiio.FLOAT)
    # Top row untouched
    assert bot_pixels[2, 2, 0] == pytest.approx(1.0, abs=1e-4)
    # Bottom row darkened to 0.6
    assert bot_pixels[height - 2, 2, 0] == pytest.approx(0.6, abs=1e-4)


def test_default_burnin_metadata_enriched_and_protects_core_tokens(tmp_path) -> None:
    """_default_burnin_metadata should include enriched tokens and not overwrite core ones."""
    from datetime import datetime
    from types import SimpleNamespace

    from renderkit.processing.frame_pipeline import (
        FramePreparationOptions,
        _default_burnin_metadata,
    )

    file_info = SimpleNamespace(
        width=1920,
        height=1080,
        channels=4,
        layers=["RGBA"],
        attributes={
            "camera": "cam_main",
            "artist": "alice",
            # Attempt to collide with core tokens; must be ignored
            "frame": 9999,
            "shot": "wrong_shot",
            "resolution": "1x1",
            "date": "1999-01-01",
            "filename": "evil.exr",
            "stem": "evil",
            "fps": 12.0,
            "layer": "wrong_layer",
            "colorspace": "wrong_cs",
        },
    )

    options = FramePreparationOptions(
        frame_path=tmp_path / "shot_010.0101.exr",
        frame_num=101,
        output_width=1280,
        output_height=720,
        source_width=1920,
        source_height=1080,
        scaler=object(),
        input_space="ACEScg",
        color_converter=object(),
        layer="diffuse",
        fps=24.0,
        file_info=file_info,
    )

    metadata = _default_burnin_metadata(options)

    assert metadata["frame"] == 101
    assert metadata["file"] == "shot_010.0101.exr"
    assert metadata["filename"] == "shot_010.0101.exr"
    assert metadata["stem"] == "shot_010.0101"
    assert metadata["shot"] == "shot_010"
    assert metadata["fps"] == 24.0
    assert metadata["layer"] == "diffuse"
    assert metadata["colorspace"] == "ACEScg"
    assert metadata["resolution"] == "1280x720"
    assert metadata["date"] == datetime.now().strftime("%Y-%m-%d")
    assert metadata["camera"] == "cam_main"
    assert metadata["artist"] == "alice"


def test_slate_generator_creates_four_channel_float_buf() -> None:
    """SlateGenerator should create a 4-channel float slate with accent rule and text."""
    try:
        import numpy as np
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from types import SimpleNamespace

    from renderkit.processing.slate import SlateGenerator

    bg = (0.06, 0.06, 0.08, 1.0)
    slate_cfg = SimpleNamespace(
        enabled=True,
        title="Dailies Review",
        show="SHOW_A",
        shot="SH010",
        artist="Bob",
        notes="Check spec highlights",
        background_color=bg,
    )
    generator = SlateGenerator(slate_cfg)
    buf = generator.generate_slate_buf(
        640,
        360,
        {
            "date": "2026-11-15",
            "frame_range": "1001-1048",
            "fps": 24.0,
            "resolution": "640x360",
            "colorspace": "sRGB",
            "codec": "libx264",
        },
    )

    spec = buf.spec()
    assert spec.width == 640
    assert spec.height == 360
    assert spec.nchannels == 4
    assert spec.format == oiio.FLOAT

    pixels = buf.get_pixels(oiio.FLOAT)
    # Corner pixel should match background color
    np.testing.assert_allclose(pixels[0, 0, :], bg, atol=1e-5)
    # Drawn text and accent rule should produce pixels brighter than background
    assert float(np.max(pixels[:, :, :3])) > 0.8


def test_exr_token_replacement_nested_fallback_and_missing() -> None:
    """BurnInProcessor should resolve {exr:<attr>} from metadata['exr'] or top-level metadata."""
    processor = BurnInProcessor()

    metadata = {
        "exr": {
            "compression": "dwaa",
            "karma/renderTime": 42.345,
            "camera.focal": 35,
        },
        "custom_top": "top_val",
    }

    template = (
        "Comp: {exr:compression} | Time: {exr:karma/renderTime:.1f}s | "
        "Focal: {exr:camera.focal}mm | Top: {exr:custom_top}"
    )
    result = processor._replace_tokens(template, metadata)
    assert result == "Comp: dwaa | Time: 42.3s | Focal: 35mm | Top: top_val"

    with pytest.raises(ValueError, match="Missing burn-in metadata token: 'exr:missing/attr'"):
        processor._replace_tokens("{exr:missing/attr}", metadata)


def test_default_burnin_metadata_includes_user_frame_range_and_exr(tmp_path, monkeypatch) -> None:
    """_default_burnin_metadata should populate user, frame_range, and exr attributes."""
    import getpass
    from types import SimpleNamespace

    from renderkit.processing.frame_pipeline import (
        FramePreparationOptions,
        _default_burnin_metadata,
    )

    monkeypatch.setattr(getpass, "getuser", lambda: "artist_jane")
    file_info = SimpleNamespace(
        width=1920,
        height=1080,
        channels=3,
        layers=["RGBA"],
        attributes={"compression": "zip", "karma/renderTime": 12.5},
    )

    opts_default = FramePreparationOptions(
        frame_path=tmp_path / "sh010.1005.exr",
        frame_num=1005,
        output_width=1920,
        output_height=1080,
        source_width=1920,
        source_height=1080,
        scaler=object(),
        input_space="ACEScg",
        color_converter=object(),
        file_info=file_info,
    )
    meta_default = _default_burnin_metadata(opts_default)
    assert meta_default["user"] == "artist_jane"
    assert meta_default["frame_range"] == "1005"
    assert meta_default["exr"] == {"compression": "zip", "karma/renderTime": 12.5}

    opts_override = FramePreparationOptions(
        frame_path=tmp_path / "sh010.1005.exr",
        frame_num=1005,
        output_width=1920,
        output_height=1080,
        source_width=1920,
        source_height=1080,
        scaler=object(),
        input_space="ACEScg",
        color_converter=object(),
        file_info=file_info,
        burnin_metadata={"frame_range": "1001-1048", "exr": {"custom": "yes"}},
    )
    meta_override = _default_burnin_metadata(opts_override)
    assert meta_override["frame_range"] == "1001-1048"
    assert meta_override["exr"] == {
        "compression": "zip",
        "karma/renderTime": 12.5,
        "custom": "yes",
    }

    def _raise_oserror() -> str:
        raise OSError("no passwd entry")

    monkeypatch.setattr(getpass, "getuser", _raise_oserror)
    assert _default_burnin_metadata(opts_default)["user"] == "unknown"


def test_watermark_config_validation() -> None:
    """WatermarkConfig should validate text, opacity, font_size, and spacing."""
    from renderkit.core.config import WatermarkConfig
    from renderkit.exceptions import ConfigurationError

    cfg = WatermarkConfig(text="CONFIDENTIAL")
    assert cfg.opacity == 25
    assert cfg.font_size == 36
    assert cfg.tiled is False
    assert cfg.spacing == 240

    with pytest.raises(ConfigurationError, match="text"):
        WatermarkConfig(text="   ")
    with pytest.raises(ConfigurationError, match="opacity"):
        WatermarkConfig(text="X", opacity=-1)
    with pytest.raises(ConfigurationError, match="opacity"):
        WatermarkConfig(text="X", opacity=101)
    with pytest.raises(ConfigurationError, match="font_size"):
        WatermarkConfig(text="X", font_size=0)
    with pytest.raises(ConfigurationError, match="spacing"):
        WatermarkConfig(text="X", spacing=0)


def test_watermark_processor_centered_opacity_and_tiled(tmp_path) -> None:
    """WatermarkProcessor should blend opacity on 3-channel buffers and tile across quadrants."""
    try:
        import numpy as np
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from renderkit.core.config import WatermarkConfig
    from renderkit.processing.watermark import WatermarkProcessor

    processor = WatermarkProcessor()

    # None config / zero opacity are no-ops
    noop_buf = oiio.ImageBuf(oiio.ImageSpec(120, 80, 3, oiio.FLOAT))
    assert processor.apply_watermark(noop_buf, None) is noop_buf
    assert (
        processor.apply_watermark(noop_buf, WatermarkConfig(text="CONFIDENTIAL", opacity=0))
        is noop_buf
    )

    # Centered watermark on 3-channel RGB buffer with 50% opacity over 0.2 background
    bg_buf = oiio.ImageBuf(oiio.ImageSpec(320, 160, 3, oiio.FLOAT))
    oiio.ImageBufAlgo.fill(bg_buf, (0.2, 0.2, 0.2))
    centered_cfg = WatermarkConfig(
        text="CONFIDENTIAL {user}", opacity=50, font_size=28, tiled=False
    )
    centered_out = processor.apply_watermark(bg_buf, centered_cfg, {"user": "alex"})
    centered_px = centered_out.get_pixels(oiio.FLOAT)

    assert centered_out.spec().nchannels == 3
    # Blending white (1.0) at 50% over 0.2 yields max ~0.6 (must not clip to 1.0)
    assert float(np.max(centered_px)) == pytest.approx(0.6, abs=0.05)
    # Center region has lit watermark text while corner remains 0.2
    assert float(np.max(centered_px[40:120, 40:280, :])) > 0.4
    assert float(centered_px[0, 0, 0]) == pytest.approx(0.2, abs=1e-5)

    # Tiled watermark on 4-channel RGBA buffer
    rgba_buf = oiio.ImageBuf(oiio.ImageSpec(400, 300, 4, oiio.FLOAT))
    oiio.ImageBufAlgo.fill(rgba_buf, (0.0, 0.0, 0.0, 1.0))
    tiled_cfg = WatermarkConfig(
        text="WIP {missing}", opacity=25, font_size=20, tiled=True, spacing=120
    )
    tiled_out = processor.apply_watermark(rgba_buf, tiled_cfg, {"user": "alex"})
    tiled_px = tiled_out.get_pixels(oiio.FLOAT)

    assert tiled_out.spec().nchannels == 4
    # All four quadrants should have watermark pixels around 0.25
    assert float(np.max(tiled_px[:150, :200, :3])) == pytest.approx(0.25, abs=0.05)
    assert float(np.max(tiled_px[:150, 200:, :3])) == pytest.approx(0.25, abs=0.05)
    assert float(np.max(tiled_px[150:, :200, :3])) == pytest.approx(0.25, abs=0.05)
    assert float(np.max(tiled_px[150:, 200:, :3])) == pytest.approx(0.25, abs=0.05)


def test_prepare_frame_buffer_applies_watermark_after_burnin(tmp_path) -> None:
    """prepare_frame_buffer should apply watermark_config via WatermarkProcessor."""
    try:
        import numpy as np
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from renderkit.core.config import WatermarkConfig
    from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
    from renderkit.processing.frame_pipeline import FramePreparationOptions, prepare_frame_buffer
    from renderkit.processing.scaler import ImageScaler
    from renderkit.processing.watermark import WatermarkProcessor

    class _FakeReader:
        def read_imagebuf(self, *_args, **_kwargs):
            buf = oiio.ImageBuf(oiio.ImageSpec(240, 120, 3, oiio.FLOAT))
            oiio.ImageBufAlgo.fill(buf, (0.0, 0.0, 0.0))
            return buf

    prepared = prepare_frame_buffer(
        FramePreparationOptions(
            frame_path=tmp_path / "shot_01.1001.exr",
            frame_num=1001,
            output_width=240,
            output_height=120,
            source_width=240,
            source_height=120,
            scaler=ImageScaler(),
            input_space=None,
            color_converter=ColorSpaceConverter(ColorSpacePreset.NO_CONVERSION),
            reader=_FakeReader(),
            watermark_processor=WatermarkProcessor(),
            watermark_config=WatermarkConfig(text="REVIEW", opacity=40, font_size=24),
        )
    )
    pixels = prepared.buf.get_pixels(oiio.FLOAT)
    assert float(np.max(pixels)) == pytest.approx(0.4, abs=0.05)
