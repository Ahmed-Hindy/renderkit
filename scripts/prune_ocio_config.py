import shutil
from pathlib import Path

import PyOpenColorIO as OCIO

# Add src to path to import constants
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
from renderkit.constants import COLOR_SPACE_UI_OPTIONS  # noqa: E402

# Configuration
SYSTEM_ACES_PATH = Path(r"C:\OCIOConfigs\configs\aces_1.2\config.ocio")
OUTPUT_DIR = PROJECT_ROOT / "src" / "renderkit" / "data" / "ocio"

# Extra required spaces not in UI options
EXTRA_REQUIRED_SPACES = [
    "Output - sRGB",  # Explicitly requested output
]

# Roles we want to preserve if their target spaces exist
REQUIRED_ROLES = [
    "scene_linear",
    "rendering",
    "color_picking",
    "texture_paint",
    "matte_paint",
    "default",
    "reference",
]


def get_processor_luts(config, src_space_name, dst_space_name="ACES - ACES2065-1"):
    """
    Get list of LUT files used by a transform.
    This is tricky with just PyOpenColorIO as it doesn't expose file dependencies directly easily.
    We effectively have to parse the text or trust that we copy the luts folder?

    Actually, PyOpenColorIO Config.getProcessor -> Processor.
    But Processor doesn't list files easily.

    Alternative approach:
    1. Parse the ColorSpace definition.
    2. Look for FileTransform, GroupTransform containing FileTransform.
    """
    luts = set()

    def extract_from_transform(transform):
        if not transform:
            return

        if isinstance(transform, OCIO.FileTransform):
            luts.add(transform.getSrc())

        elif isinstance(transform, OCIO.GroupTransform):
            for tr in transform:
                extract_from_transform(tr)

        # Handle other transforms if they refer to files? Usually just FileTransform.

    space = config.getColorSpace(src_space_name)
    if not space:
        print(f"Warning: Space '{src_space_name}' not found in source config.")
        return set()

    # Check to_reference and from_reference
    extract_from_transform(space.getTransform(OCIO.COLORSPACE_DIR_TO_REFERENCE))
    extract_from_transform(space.getTransform(OCIO.COLORSPACE_DIR_FROM_REFERENCE))

    return luts


def prune_config():
    if not SYSTEM_ACES_PATH.exists():
        print(f"Error: ACES config not found at {SYSTEM_ACES_PATH}")
        return

    print(f"Loading system ACES config from {SYSTEM_ACES_PATH}...")
    src_config = OCIO.Config.CreateFromFile(str(SYSTEM_ACES_PATH))

    # 1. Identify all required spaces
    required_spaces = set(COLOR_SPACE_UI_OPTIONS)
    required_spaces.update(EXTRA_REQUIRED_SPACES)

    # Add dependency spaces (e.g. if a View uses a space, or if a role points to a space)
    # Also add "ACES - ACES2065-1" as it is usually the reference connection
    required_spaces.add("ACES - ACES2065-1")

    # 2. Collect used LUTs
    used_luts = set()

    # We also need to traverse required_spaces to see if they refer to aliases or specific transforms
    # For ACES 1.2, many use FileTransforms.

    print(" Analyzing dependencies...")

    # Prepare Output Config
    dst_config = OCIO.Config()
    dst_config.setSearchPath("luts")  # Relative path in bundle
    dst_config.setDescription("Pruned ACES 1.2 Config for RenderKit")

    # Copy essential roles
    for role in REQUIRED_ROLES:
        # Check what the source config has
        if src_config.hasRole(role):
            role_space = src_config.getRoleColorSpace(role)
            # If we decide to keep this role, we must keep the space
            # For now, let's strictly keep only what we need.
            # But 'scene_linear' is critical for apps.
            if role in ["scene_linear", "rendering", "default"]:
                required_spaces.add(role_space)
                dst_config.setRole(role, role_space)

    # Explicitly set user request Output - sRGB as color_picking role if generic sRGB not there?
    if "Output - sRGB" in required_spaces:
        dst_config.setRole("color_picking", "Output - sRGB")

    # 3. Build new config and gather files
    # 3. Build new config and gather files

    # Validate existence
    valid_spaces = []
    for name in required_spaces:
        if src_config.getColorSpace(name):
            valid_spaces.append(name)
        else:
            print(f"  [Warn] Required space '{name}' not found in source.")

    for name in valid_spaces:
        print(f"  Including space: {name}")
        space = src_config.getColorSpace(name)
        dst_config.addColorSpace(space)

        # Extract LUTs
        luts = get_processor_luts(src_config, name)
        used_luts.update(luts)

    # 4. Setup Views (Displays)
    # We only want "Output - sRGB" really.
    # Check what displays exist for this space
    display = "sRGB Monitor"  # Custom display name for our app
    # Or mirror source displays if they reference our kept spaces.

    # Let's create a clean display list
    dst_config.addDisplayView(display, "sRGB", "Output - sRGB")
    dst_config.setActiveViews("sRGB")

    # 5. Output
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    luts_dir = OUTPUT_DIR / "luts"
    luts_dir.mkdir()

    print(f"Copying {len(used_luts)} LUT files...")
    src_luts_dir = SYSTEM_ACES_PATH.parent / "luts"

    for lut_file in used_luts:
        src_lut = src_luts_dir / lut_file
        dst_lut = luts_dir / lut_file

        if src_lut.exists():
            shutil.copy2(src_lut, dst_lut)
        else:
            print(f"  [Error] Missing LUT file: {lut_file}")

    dst_config_path = OUTPUT_DIR / "config.ocio"
    try:
        dst_config.validate()
        with open(dst_config_path, "w") as f:
            f.write(dst_config.serialize())
        print(f"Pruned config saved to {dst_config_path}")
    except Exception as e:
        print(f"Failed to validate/save config: {e}")


if __name__ == "__main__":
    prune_config()
