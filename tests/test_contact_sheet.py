import shutil
from pathlib import Path

import pytest

from renderkit.core.config import ContactSheetConfigBuilder
from renderkit.core.ffmpeg_utils import get_ffmpeg_exe
from renderkit.exceptions import ImageReadError
from renderkit.io.image_reader import LayerMapEntry
from renderkit.processing.contact_sheet import ContactSheetGenerator


def _ffmpeg_available() -> bool:
    exe = get_ffmpeg_exe()
    if Path(exe).is_file():
        return True
    return shutil.which(exe) is not None


def test_contact_sheet_composite_layers(tmp_path):
    """Test generating a composite grid for a single frame with multiple layers."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    # 1. Create a dummy multi-layer image
    frame_path = tmp_path / "test_frame.exr"
    spec = oiio.ImageSpec(100, 100, 3, oiio.FLOAT)

    # We'll simulate layers by creating multiple buffers and merging them if we could,
    # but for testing our generator, we just need the reader to find layers.
    # Since we can't easily write multi-part EXR with just ImageBuf.write,
    # we'll test the grid calculation and image creation logic.

    # Actually, let's just use 4 single images as 'layers' (simulated by the reader)
    # or just trust the generator to handle those it finds.

    # Write a simple image
    buf = oiio.ImageBuf(spec)
    oiio.ImageBufAlgo.fill(buf, (0.5, 0.5, 0.5))
    buf.write(str(frame_path))

    # 2. Build config
    config = (
        ContactSheetConfigBuilder()
        .with_columns(2)
        .with_thumbnail_width(50)
        .with_padding(5)
        .with_labels(True, font_size=8)
        .build()
    )

    # 3. Generate composite
    generator = ContactSheetGenerator(config)
    # The reader will only find 1 layer ("RGBA" or similar) for our dummy file
    composite = generator.composite_layers(frame_path)

    # 4. Verify dimensions
    # 1 layer -> 1 row, 1 col active (but canvas is 2x1 cell if it thinks there are more? No, rows calculation uses len(layers))
    # layers = reader.get_layers(frame_path) -> usually ["RGBA"] for simple file
    # num_layers = 1 -> rows = 1, cols = 2 (config)
    # cell_w = 50 + 10 = 60
    # cell_h = 50 + 10 + 20 = 80
    # canvas = 60*2 x 80*1 = 120 x 80

    spec = composite.spec()
    assert spec.width == 120
    assert spec.height == 75
    assert spec.nchannels == 3


def test_contact_sheet_full_conversion(tmp_path):
    """Test the full conversion pipeline with contact sheet mode enabled."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    if not _ffmpeg_available():
        pytest.skip("FFmpeg not available in test environment")

    # 1. Create dummy image sequence
    seq_dir = tmp_path / "sequence"
    seq_dir.mkdir()

    for i in range(1, 4):
        frame_path = seq_dir / f"test.{i:04d}.exr"
        spec = oiio.ImageSpec(100, 100, 3, oiio.FLOAT)
        buf = oiio.ImageBuf(spec)
        oiio.ImageBufAlgo.fill(buf, (i / 10.0, 0.5, 0.5))
        buf.write(str(frame_path))

    output_path = tmp_path / "output.mp4"

    # 2. Build ConversionConfig with ContactSheetConfig
    from renderkit.core.config import ContactSheetConfig, ConversionConfigBuilder

    cs_config = ContactSheetConfig(
        columns=2, thumbnail_width=50, padding=5, show_labels=True, font_size=8
    )

    config = (
        ConversionConfigBuilder()
        .with_input_pattern(str(seq_dir / "test.%04d.exr"))
        .with_output_path(str(output_path))
        .with_contact_sheet(True, cs_config)
        .with_fps(24.0)
        .build()
    )

    # 3. Run conversion
    from renderkit.core.converter import SequenceConverter

    converter = SequenceConverter(config)
    converter.convert()

    # 4. Verify output
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_contact_sheet_uses_subimage_cache(tmp_path):
    """Ensure contact sheet avoids per-layer reads when layer map is available."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    class FakeReader:
        def __init__(self) -> None:
            self.subimage_calls: list[int] = []
            self.image_calls: list[str] = []

        def read_subimagebuf(self, path, subimage_index: int):
            self.subimage_calls.append(subimage_index)
            spec = oiio.ImageSpec(16, 8, 3, oiio.FLOAT)
            buf = oiio.ImageBuf(spec)
            oiio.ImageBufAlgo.fill(buf, (0.2, 0.3, 0.4))
            return buf

        def read_imagebuf(self, path, layer=None, layer_map=None):
            self.image_calls.append(str(layer))
            spec = oiio.ImageSpec(16, 8, 3, oiio.FLOAT)
            buf = oiio.ImageBuf(spec)
            oiio.ImageBufAlgo.fill(buf, (0.1, 0.1, 0.1))
            return buf

    layers = ["RGBA", "diffuse", "specular", "mask"]
    layer_map = {
        "RGBA": LayerMapEntry(0, None),
        "diffuse": LayerMapEntry(0, (0, 1, 2)),
        "specular": LayerMapEntry(0, (0, 1, 2)),
        "mask": LayerMapEntry(1, (0,)),
    }

    config = (
        ContactSheetConfigBuilder()
        .with_columns(2)
        .with_thumbnail_width(16)
        .with_padding(2)
        .with_labels(False)
        .build()
    )

    reader = FakeReader()
    generator = ContactSheetGenerator(config, reader=reader, layers=layers, layer_map=layer_map)
    composite = generator.composite_layers(tmp_path / "dummy.exr")

    assert composite is not None
    assert reader.image_calls == []
    assert set(reader.subimage_calls) == {0, 1}


def test_contact_sheet_layer_failure_raises(tmp_path):
    """Contact sheets should fail loudly when a requested layer cannot be read."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    class FakeReader:
        def get_layers(self, path):
            return ["RGBA", "broken"]

        def read_imagebuf(self, path, layer=None, layer_map=None):
            if layer == "broken":
                raise ImageReadError("missing layer")
            spec = oiio.ImageSpec(16, 8, 3, oiio.FLOAT)
            buf = oiio.ImageBuf(spec)
            oiio.ImageBufAlgo.fill(buf, (0.2, 0.3, 0.4))
            return buf

    config = (
        ContactSheetConfigBuilder()
        .with_columns(2)
        .with_thumbnail_width(16)
        .with_labels(False)
        .build()
    )

    generator = ContactSheetGenerator(config, reader=FakeReader())

    with pytest.raises(ImageReadError, match="Failed to read layer 'broken'"):
        generator.composite_layers(tmp_path / "dummy.exr")


def test_prepare_frame_buffer_contact_sheet_renders_labels_after_color_conversion(tmp_path) -> None:
    """Contact sheet labels should be rendered after color conversion at pure white (1, 1, 1)."""
    try:
        import numpy as np
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
    from renderkit.processing.frame_pipeline import FramePreparationOptions, prepare_frame_buffer
    from renderkit.processing.scaler import ImageScaler

    class FakeReader:
        def get_layers(self, path):
            return ["beauty"]

        def read_imagebuf(self, path, layer=None, layer_map=None):
            spec = oiio.ImageSpec(160, 80, 3, oiio.FLOAT)
            buf = oiio.ImageBuf(spec)
            oiio.ImageBufAlgo.fill(buf, (0.0, 0.0, 0.0))
            return buf

    config = (
        ContactSheetConfigBuilder()
        .with_columns(1)
        .with_thumbnail_width(160)
        .with_padding(10)
        .with_labels(True, font_size=16)
        .build()
    )
    generator = ContactSheetGenerator(config, reader=FakeReader())

    # Wrap color_converter to verify labels are not on the buffer during color conversion
    inner_converter = ColorSpaceConverter(ColorSpacePreset.LINEAR_TO_SRGB)
    seen_during_color: list[float] = []

    class SpyColorConverter:
        def convert_buf(self, buf, input_space=None):
            pixels = buf.get_pixels(oiio.FLOAT)
            label_region = pixels[10 + 80 :, :, :]
            seen_during_color.append(float(np.max(label_region)))
            return inner_converter.convert_buf(buf, input_space=input_space)

    prepared = prepare_frame_buffer(
        FramePreparationOptions(
            frame_path=tmp_path / "beauty.0001.exr",
            frame_num=1,
            output_width=None,
            output_height=None,
            source_width=None,
            source_height=None,
            scaler=ImageScaler(),
            input_space=None,
            color_converter=SpyColorConverter(),
            contact_sheet_generator=generator,
            contact_sheet_config=config,
            contact_sheet_enabled=True,
        )
    )

    # During color conversion, label region had only background color (0.1), no label text (1.0)
    assert seen_during_color == [pytest.approx(0.1, abs=1e-5)]

    result_pixels = prepared.buf.get_pixels(oiio.FLOAT)
    label_region = result_pixels[10 + 80 :, :, :]
    max_rgb = np.max(label_region, axis=(0, 1))
    np.testing.assert_allclose(max_rgb, (1.0, 1.0, 1.0), atol=1e-5)


def test_prepare_frame_buffer_scales_before_color_conversion(tmp_path) -> None:
    """Non-contact-sheet frames should scale in scene-linear before color conversion."""
    try:
        import OpenImageIO as oiio
    except ImportError:
        pytest.skip("OpenImageIO not available")

    from renderkit.processing.frame_pipeline import FramePreparationOptions, prepare_frame_buffer
    from renderkit.processing.scaler import ImageScaler

    events: list[tuple[str, int, int]] = []

    class FakeReader:
        def read_imagebuf(self, path, layer=None, layer_map=None):
            spec = oiio.ImageSpec(64, 32, 3, oiio.FLOAT)
            buf = oiio.ImageBuf(spec)
            oiio.ImageBufAlgo.fill(buf, (0.2, 0.2, 0.2))
            return buf

    class SpyScaler(ImageScaler):
        def scale_buf(self, buf, width, height):
            events.append(("scale", width, height))
            return super().scale_buf(buf, width, height)

    class SpyColorConverter:
        def convert_buf(self, buf, input_space=None):
            spec = buf.spec()
            events.append(("color", spec.width, spec.height))
            return buf

    prepared = prepare_frame_buffer(
        FramePreparationOptions(
            frame_path=tmp_path / "shot.0001.exr",
            frame_num=1,
            output_width=32,
            output_height=16,
            source_width=64,
            source_height=32,
            scaler=SpyScaler(),
            input_space="linear",
            color_converter=SpyColorConverter(),
            reader=FakeReader(),
        )
    )

    assert events == [("scale", 32, 16), ("color", 32, 16)]
    assert prepared.applied_scale == pytest.approx(0.5)
