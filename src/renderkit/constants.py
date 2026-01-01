"""Centralized constants for renderkit."""

# Metadata Keys
FPS_METADATA_KEYS = [
    "framesPerSecond",
    "exr/FramesPerSecond",  # Nuke
    "fps",
    "arnold/fps",  # Arnold
    "rs/fps",  # Redshift
    "vray/fps",  # V-Ray
    "mantra/fps",  # Mantra (Houdini)
    "karma/fps",  # Karma (Houdini)
    "cap_fps",  # Blender
]

COLOR_SPACE_METADATA_KEYS = [
    "exr/oiio:ColorSpace",
    "oiio:ColorSpace",
    "colorSpace",
    "interchange/color_space",
    "acesImageContainerFlag",
]

# OCIO
OCIO_OUTPUT_CANDIDATES = [
    "Output - sRGB",
    "sRGB",
    "srgb_display",
    "out_srgb",
]

# UI Options
COLOR_SPACE_UI_LINEAR = "Linear (Default)"
COLOR_SPACE_UI_ACES_CG = "ACES - ACEScg"
COLOR_SPACE_UI_ACES_2065_1 = "ACES - ACES2065-1"
COLOR_SPACE_UI_SRGB = "sRGB"
COLOR_SPACE_UI_REC709 = "Rec.709"
COLOR_SPACE_UI_RAW = "Raw (No Conversion)"

COLOR_SPACE_UI_OPTIONS = [
    COLOR_SPACE_UI_LINEAR,
    COLOR_SPACE_UI_ACES_CG,
    COLOR_SPACE_UI_ACES_2065_1,
    COLOR_SPACE_UI_SRGB,
    COLOR_SPACE_UI_REC709,
    COLOR_SPACE_UI_RAW,
]

# Supported Formats
OIIO_SUPPORTED_EXTENSIONS = {"exr", "png", "jpg", "jpeg", "tif", "tiff", "dpx"}
SUPPORTED_VIDEO_EXTENSIONS = {"mp4", "mkv", "mov", "avi"}
