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
