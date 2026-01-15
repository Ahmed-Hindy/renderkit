import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path("g:/Projects/Dev/Github/image_video_processor/src")))

from renderkit.io.image_reader import OIIOReader

try:
    import OpenImageIO as oiio
except ImportError:
    print("OpenImageIO not available")
    sys.exit(1)

path = Path(
    r"G:\Projects\Data_folder\render\Canyon_Run\sq001\sh001\work\fx\render\CanRun_sh001_fx_v063\SH030_karma_all_render\SH030_karma_all_render.1001.exr"
)
reader = OIIOReader()

try:
    layers = reader.get_layers(path)
    print(f"Detected layers via OIIOReader: {layers}")

    if len(layers) > 1:
        # Try reading a layer from a non-zero part (e.g., 'albedo' was part 11)
        target_layer = "albedo" if "albedo" in layers else layers[1]
        print(f"Attempting to read layer: {target_layer}")
        buf = reader.read_imagebuf(path, layer=target_layer)
        pixels = buf.get_pixels(oiio.FLOAT)
        if pixels is not None and pixels.ndim == 1:
            spec = buf.spec()
            pixels = pixels.reshape((spec.height, spec.width, spec.nchannels))
        print(f"Sucessfully read '{target_layer}'! Shape: {pixels.shape}")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
