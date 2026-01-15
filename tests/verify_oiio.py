import sys
from pathlib import Path

try:
    import OpenImageIO as oiio

    print(f"OIIO Version: {oiio.VERSION}")
except ImportError:
    print("OIIO not found")
    sys.exit(1)

# Add src to path
sys.path.append(str(Path("g:/Projects/Dev/Github/image_video_processor/src")))

from renderkit.io.image_reader import ImageReaderFactory
from renderkit.processing.scaler import ImageScaler


def test_oiio():
    # Use real sequence from integration tests
    base_path = Path(
        "G:/Projects/AYON_PROJECTS/Canyon_Run/sq001/sh001/publish/render/renderCompositingMain/v001"
    )
    samples = list(base_path.glob("*.exr"))

    if not samples:
        # Fallback to current dir glob if AYON path doesn't exist on this machine
        samples = list(Path("g:/Projects/Dev/Github/image_video_processor").glob("**/*.exr"))

    if not samples:
        print("No sample EXR found for testing.")
        return

    sample_path = samples[0]
    print(f"Testing with: {sample_path}")

    # Test Reader
    reader = ImageReaderFactory.create_reader(sample_path)
    print(f"Using reader: {type(reader).__name__}")

    buf = reader.read_imagebuf(sample_path)
    pixels = buf.get_pixels(oiio.FLOAT)
    if pixels is not None and pixels.ndim == 1:
        spec = buf.spec()
        pixels = pixels.reshape((spec.height, spec.width, spec.nchannels))
    print(f"Image shape: {pixels.shape}, dtype: {pixels.dtype}")

    res = reader.get_resolution(sample_path)
    print(f"Resolution: {res}")

    fps = reader.get_metadata_fps(sample_path)
    print(f"Metadata FPS: {fps}")

    colorspace = reader.get_metadata_color_space(sample_path)
    print(f"Metadata ColorSpace: {colorspace}")

    # Test Layers
    layers = reader.get_layers(sample_path)
    print(f"Available layers: {layers}")

    if len(layers) > 1:
        # Try reading a specific layer
        layer_to_read = layers[1]
        print(f"Attempting to read layer: {layer_to_read}")
        layer_buf = reader.read_imagebuf(sample_path, layer=layer_to_read)
        layer_pixels = layer_buf.get_pixels(oiio.FLOAT)
        if layer_pixels is not None and layer_pixels.ndim == 1:
            spec = layer_buf.spec()
            layer_pixels = layer_pixels.reshape((spec.height, spec.width, spec.nchannels))
        print(f"Layer image shape: {layer_pixels.shape}")

    # Test Scaler
    scaled_buf = ImageScaler.scale_buf(buf, width=100, height=100)
    scaled_pixels = scaled_buf.get_pixels(oiio.FLOAT)
    if scaled_pixels is not None and scaled_pixels.ndim == 1:
        spec = scaled_buf.spec()
        scaled_pixels = scaled_pixels.reshape((spec.height, spec.width, spec.nchannels))
    print(f"Scaled shape: {scaled_pixels.shape}")

    print("OIIO Verification Successful!")


if __name__ == "__main__":
    test_oiio()
