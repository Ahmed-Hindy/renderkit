import OpenImageIO as oiio
from pathlib import Path

path = r"G:\Projects\Data_folder\render\Canyon_Run\sq001\sh001\work\fx\render\CanRun_sh001_fx_v063\SH030_karma_all_render\SH030_karma_all_render.1001.exr"
buf = oiio.ImageBuf(path)
if buf.has_error:
    print(f"Error reading: {buf.geterror()}")
else:
    print(f"Subimages (Parts): {buf.nsubimages}")
    for i in range(buf.nsubimages):
        sub_buf = oiio.ImageBuf(path, i, 0)  # Initialize with subimage i
        spec = sub_buf.spec()
        print(
            f"Part {i} ('{spec.getattribute('name') or 'unnamed'}') Channels: {spec.channelnames}"
        )

    # Original logic (checking if grouped channels exist in part 0)
    spec = buf.spec()
    layers = set()
    for name in spec.channelnames:
        if "." in name:
            layers.add(name.rsplit(".", 1)[0])
        else:
            layers.add("RGBA")
    print(f"Detected layers in Part 0: {sorted(list(layers))}")
