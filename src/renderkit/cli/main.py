"""CLI interface for the Render Kit."""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from renderkit.api.processor import RenderKit
from renderkit.core.config import BurnInConfig, BurnInElement, ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version="0.3.0")
def main() -> None:
    """RenderKit - VFX workflow tools."""
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
    default="libx264",
    help="Video codec (default: libx264, use 'libaom-av1' for AV1)",
)
@click.option(
    "--quality",
    type=int,
    default=10,
    help="Video quality (0-10), 10 is best (default: 10). Sets CRF.",
)
@click.option(
    "--layer",
    type=str,
    default=None,
    help="Specific EXR layer to extract (e.g., 'diffuse').",
)
@click.option("--start-frame", type=int, default=None, help="Start frame number")
@click.option("--end-frame", type=int, default=None, help="End frame number")
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite output file if it exists",
)
@click.option("--burnin-frame", is_flag=True, default=False, help="Burn in frame number")
@click.option("--burnin-layer", is_flag=True, default=False, help="Burn in layer name")
@click.option("--burnin-fps", is_flag=True, default=False, help="Burn in frame rate (fps)")
@click.option(
    "--burnin-opacity",
    type=int,
    default=30,
    help="Opacity of the burn-in background bar (0-100, default: 30)",
)
def convert_exr_sequence(
    input_pattern: str,
    output_path: str,
    fps: Optional[float],
    color_space: str,
    width: Optional[int],
    height: Optional[int],
    codec: str,
    quality: int,
    layer: Optional[str],
    start_frame: Optional[int],
    end_frame: Optional[int],
    overwrite: bool,
    burnin_frame: bool,
    burnin_layer: bool,
    burnin_fps: bool,
    burnin_opacity: int,
) -> None:
    """Convert an EXR sequence to MP4 video.

    INPUT_PATTERN: File pattern with frame number (e.g., "render.%04d.exr", "render.$F4.exr", "render.####.exr")

    OUTPUT_PATH: Output video file path (e.g., "output.mp4")

    Examples:

    \b
        # Basic conversion
        renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24

    \b
        # With custom resolution
        renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --width 1920 --height 1080

    \b
        # With frame range
        renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --start-frame 100 --end-frame 200
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
        .with_quality(quality)
        .with_layer(layer)
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

    # Setup burn-ins
    burnin_elements = []
    # Assume source width for positioning if output width not yet final in config_builder
    # But wait, config_builder.width might be None.
    # Let's use alignment logic instead.

    # We'll need the actual width to position Center/Right correctly
    # since OIIO render_text takes absolute coordinates.
    # The converter will handle absolute positioning based on output_width.

    # Actually, I'll update converter.py to handle relative positioning
    # if I use special x values, or I'll just pass the intention.

    # For now, let's just use standard padding and smaller font.
    font_size = 20
    if burnin_frame:
        burnin_elements.append(
            BurnInElement(
                text_template="Frame: {frame}", x=20, y=10, font_size=font_size, alignment="left"
            )
        )
    if burnin_layer:
        # We can't know the exact center yet, so we'll fix this in converter.py
        # to interpret -1 as center or something.
        # Or better: update BurnInProcessor to handle 'left', 'center', 'right' specifically.
        burnin_elements.append(
            BurnInElement(
                text_template="Layer: {layer}", x=0, y=10, font_size=font_size, alignment="center"
            )
        )
    if burnin_fps:
        burnin_elements.append(
            BurnInElement(
                text_template="FPS: {fps:.2f}", x=0, y=10, font_size=font_size, alignment="right"
            )
        )

    if burnin_elements:
        config_builder.with_burnin(
            BurnInConfig(elements=burnin_elements, background_opacity=burnin_opacity)
        )

    try:
        config = config_builder.build()
        processor = RenderKit()
        processor.convert_with_config(config)
        click.echo(f"Successfully converted to: {output_path}")
    except Exception as e:
        logger.exception("Conversion failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
