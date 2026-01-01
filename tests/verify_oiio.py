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

    img = reader.read(sample_path)
    print(f"Image shape: {img.shape}, dtype: {img.dtype}")

    res = reader.get_resolution(sample_path)
    print(f"Resolution: {res}")

    fps = reader.get_metadata_fps(sample_path)
    print(f"Metadata FPS: {fps}")

    colorspace = reader.get_metadata_color_space(sample_path)
    print(f"Metadata ColorSpace: {colorspace}")

    # Test Scaler
    scaled = ImageScaler.scale_image(img, width=100)
    print(f"Scaled shape: {scaled.shape}")

    print("OIIO Verification Successful!")


if __name__ == "__main__":
    test_oiio()
