import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path("g:/Projects/Dev/Github/image_video_processor/src")))

from renderkit.io.image_reader import OIIOReader

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
        img = reader.read(path, layer=target_layer)
        print(f"Sucessfully read '{target_layer}'! Shape: {img.shape}")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
