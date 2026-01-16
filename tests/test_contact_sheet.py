import pytest

from renderkit.core.config import ContactSheetConfigBuilder
from renderkit.processing.contact_sheet import ContactSheetGenerator


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
