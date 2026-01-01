"""Example: Convert EXR sequence to MP4 using the API."""

from renderkit import RenderKit
from renderkit.core.config import ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

# Example 1: Simple conversion
processor = RenderKit()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0,
)

# Example 2: With custom resolution
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output_hd.mp4",
    fps=24.0,
    width=1920,
    height=1080,
)

# Example 3: With frame range
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output_range.mp4",
    fps=24.0,
    start_frame=100,
    end_frame=200,
)

# Example 4: Using ConversionConfigBuilder


config = (
    ConversionConfigBuilder()
    .with_input_pattern("render.%04d.exr")
    .with_output_path("output_custom.mp4")
    .with_fps(30.0)
    .with_color_space_preset(ColorSpacePreset.LINEAR_TO_REC709)
    .with_resolution(3840, 2160)
    .with_codec("avc1")
    .build()
)

processor.convert_with_config(config)
