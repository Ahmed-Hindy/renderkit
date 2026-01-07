"""Example: Using the Python API programmatically."""

from renderkit import RenderKit
from renderkit.core.config import ContactSheetConfig, ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

# Initialize processor
processor = RenderKit()

# Method 1: Using convenience method
processor.convert_exr_sequence_to_mp4(
    input_pattern="sequences/render.%04d.exr",
    output_path="output/render.mp4",
    fps=24.0,
    color_space_preset=ColorSpacePreset.LINEAR_TO_SRGB,
)

# Method 2: Using builder pattern for more control
config = (
    ConversionConfigBuilder()
    .with_input_pattern("sequences/render.$F4.exr")  # Houdini style
    .with_output_path("output/render.mp4")
    .with_fps(24.0)
    .with_color_space_preset(ColorSpacePreset.LINEAR_TO_SRGB)
    .with_resolution(1920, 1080)
    .with_codec("avc1")  # H.264
    .with_frame_range(1, 100)
    .with_layer("beauty")
    .build()
)

processor.convert_with_config(config)

# Method 3: Contact sheet video (multi-AOV grid)
contact_sheet_config = ContactSheetConfig(
    columns=4,
    thumbnail_width=512,
    padding=10,
    show_labels=True,
)

config = (
    ConversionConfigBuilder()
    .with_input_pattern("sequences/render.%04d.exr")
    .with_output_path("output/contact_sheet.mp4")
    .with_fps(24.0)
    .with_contact_sheet(True, contact_sheet_config)
    .build()
)

processor.convert_with_config(config)

# Method 4: Batch processing multiple sequences
sequences = [
    ("render.%04d.exr", "output/render.mp4"),
    ("beauty.%04d.exr", "output/beauty.mp4"),
    ("diffuse.%04d.exr", "output/diffuse.mp4"),
]

for input_pattern, output_path in sequences:
    processor.convert_exr_sequence_to_mp4(
        input_pattern=input_pattern,
        output_path=output_path,
        fps=24.0,
    )
