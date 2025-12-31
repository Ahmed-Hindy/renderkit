"""CLI interface for the image video processor."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from image_video_processor.api.processor import ImageVideoProcessor
from image_video_processor.core.config import ConversionConfigBuilder
from image_video_processor.processing.color_space import ColorSpacePreset

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Image and Video Processor - VFX workflow tools."""
    pass


@main.command()
@click.argument("input_pattern", type=str)
@click.argument("output_path", type=click.Path())
@click.option(
    "--fps",
    type=float,
    default=None,
    help="Frame rate (fps). If not provided, will attempt auto-detection.",
)
@click.option(
    "--color-space",
    type=click.Choice(
        ["linear_to_srgb", "linear_to_rec709", "srgb_to_linear", "no_conversion"],
        case_sensitive=False,
    ),
    default="linear_to_srgb",
    help="Color space conversion preset (default: linear_to_srgb)",
)
@click.option("--width", type=int, default=None, help="Output width (default: source width)")
@click.option("--height", type=int, default=None, help="Output height (default: source height)")
@click.option(
    "--codec",
    type=str,
    default="mp4v",
    help="Video codec (default: mp4v, use 'avc1' for H.264)",
)
@click.option("--start-frame", type=int, default=None, help="Start frame number")
@click.option("--end-frame", type=int, default=None, help="End frame number")
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite output file if it exists",
)
def convert_exr_sequence(
    input_pattern: str,
    output_path: str,
    fps: Optional[float],
    color_space: str,
    width: Optional[int],
    height: Optional[int],
    codec: str,
    start_frame: Optional[int],
    end_frame: Optional[int],
    overwrite: bool,
) -> None:
    """Convert an EXR sequence to MP4 video.

    INPUT_PATTERN: File pattern with frame number (e.g., "render.%04d.exr", "render.$F4.exr", "render.####.exr")

    OUTPUT_PATH: Output video file path (e.g., "output.mp4")

    Examples:

    \b
        # Basic conversion
        ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24

    \b
        # With custom resolution
        ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --width 1920 --height 1080

    \b
        # With frame range
        ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --start-frame 100 --end-frame 200
    """
    output_path_obj = Path(output_path)

    # Check if output exists
    if output_path_obj.exists() and not overwrite:
        click.echo(f"Error: Output file already exists: {output_path}", err=True)
        click.echo("Use --overwrite to overwrite it.", err=True)
        sys.exit(1)

    # Map color space string to enum
    color_space_map = {
        "linear_to_srgb": ColorSpacePreset.LINEAR_TO_SRGB,
        "linear_to_rec709": ColorSpacePreset.LINEAR_TO_REC709,
        "srgb_to_linear": ColorSpacePreset.SRGB_TO_LINEAR,
        "no_conversion": ColorSpacePreset.NO_CONVERSION,
    }
    color_space_preset = color_space_map[color_space.lower()]

    # Build configuration
    config_builder = (
        ConversionConfigBuilder()
        .with_input_pattern(input_pattern)
        .with_output_path(output_path)
        .with_color_space_preset(color_space_preset)
        .with_codec(codec)
    )

    if fps is not None:
        config_builder.with_fps(fps)

    if width is not None and height is not None:
        config_builder.with_resolution(width, height)

    if start_frame is not None and end_frame is not None:
        config_builder.with_frame_range(start_frame, end_frame)
    elif start_frame is not None:
        config_builder.with_frame_range(start_frame, start_frame)
    elif end_frame is not None:
        config_builder.with_frame_range(0, end_frame)

    try:
        config = config_builder.build()
        processor = ImageVideoProcessor()
        processor.convert_with_config(config)
        click.echo(f"Successfully converted to: {output_path}")
    except Exception as e:
        logger.exception("Conversion failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
