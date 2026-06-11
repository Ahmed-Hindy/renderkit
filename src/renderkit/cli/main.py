"""CLI interface for the Render Kit."""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import click

from renderkit import __version__
from renderkit.api.processor import RenderKit
from renderkit.cli.batch import batch_convert
from renderkit.cli.conversion import base_conversion_config_builder
from renderkit.core.batch import deduplicate_output_path
from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
)
from renderkit.core.ffmpeg_utils import ensure_ffmpeg_env
from renderkit.core.profiler import get_profile_env_config, profile_context
from renderkit.core.sequence import SequenceDetector
from renderkit.core.sequence_replacement import (
    find_exr_sequences,
    find_replacement_mp4,
    replace_sequence_with_mp4,
)
from renderkit.exceptions import RenderKitError
from renderkit.io.image_reader import ImageReaderFactory
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.logging_utils import setup_logging
from renderkit.processing.scaler import ImageScaler

logger = logging.getLogger("renderkit.cli.main")


@click.group()
@click.version_option(__version__)
def main() -> None:
    """RenderKit - VFX workflow tools."""
    ensure_ffmpeg_env()
    setup_logging()
    pass


def _launch_ui() -> None:
    """Launch the RenderKit graphical interface."""
    from renderkit.ui.main_window import run_ui

    run_ui()


def _label_height(config: ContactSheetConfig) -> int:
    if not config.show_labels:
        return 0
    label_gap = max(4, int(config.font_size * 0.01))
    return label_gap + int(config.font_size * 1.4)


def _to_rgb_buf(oiio: Any, buf: Any) -> Any:
    spec = buf.spec()
    if spec.nchannels == 3:
        return buf
    if spec.nchannels >= 3:
        rgb_buf = oiio.ImageBufAlgo.channels(buf, (0, 1, 2), ("R", "G", "B"))
    elif spec.nchannels == 2:
        rgb_buf = oiio.ImageBufAlgo.channels(buf, (0, 1, 1), ("R", "G", "B"))
    else:
        rgb_buf = oiio.ImageBufAlgo.channels(buf, (0, 0, 0), ("R", "G", "B"))
    if rgb_buf.has_error:
        raise RuntimeError(f"Failed to convert contact sheet frame to RGB: {rgb_buf.geterror()}")
    return rgb_buf


def _write_sequence_contact_sheet(
    input_pattern: str,
    output_path: Path,
    config: ContactSheetConfig,
    layer: Optional[str],
    start_frame: Optional[int],
    end_frame: Optional[int],
) -> None:
    """Write a still contact sheet made from frames in a sequence."""
    try:
        import OpenImageIO as oiio
    except ImportError as exc:
        raise RuntimeError("OpenImageIO library not available.") from exc

    sequence = SequenceDetector.detect_sequence(input_pattern)
    frame_numbers = sequence.frame_numbers
    if start_frame is not None:
        frame_numbers = [frame for frame in frame_numbers if frame >= start_frame]
    if end_frame is not None:
        frame_numbers = [frame for frame in frame_numbers if frame <= end_frame]
    if not frame_numbers:
        raise ValueError("No frames found in specified range")

    first_path = sequence.get_file_path(frame_numbers[0])
    reader = ImageReaderFactory.create_reader(first_path, image_cache=get_shared_image_cache())
    first_buf = _to_rgb_buf(oiio, reader.read_imagebuf(first_path, layer=layer))
    first_spec = first_buf.spec()
    thumb_w, thumb_h = config.resolve_layer_size(first_spec.width, first_spec.height)
    padding = config.padding
    label_h = _label_height(config)
    label_gap = max(4, int(config.font_size * 0.01)) if config.show_labels else 0
    cell_w = thumb_w + (padding * 2)
    cell_h = thumb_h + (padding * 2) + label_h
    rows = (len(frame_numbers) + config.columns - 1) // config.columns

    canvas_spec = oiio.ImageSpec(cell_w * config.columns, cell_h * rows, 3, oiio.FLOAT)
    canvas = oiio.ImageBuf(canvas_spec)
    oiio.ImageBufAlgo.fill(canvas, config.background_color)

    for index, frame_number in enumerate(frame_numbers):
        frame_path = sequence.get_file_path(frame_number)
        buf = (
            first_buf
            if index == 0
            else _to_rgb_buf(oiio, reader.read_imagebuf(frame_path, layer=layer))
        )
        spec = buf.spec()
        if spec.width != thumb_w or spec.height != thumb_h:
            buf = ImageScaler.scale_buf(buf, thumb_w, thumb_h)

        row = index // config.columns
        col = index % config.columns
        x_offset = col * cell_w + padding
        y_offset = row * cell_h + padding
        if not oiio.ImageBufAlgo.paste(canvas, x_offset, y_offset, 0, 0, buf):
            raise RuntimeError(f"Failed to paste frame {frame_number}: {oiio.geterror()}")

        if config.show_labels:
            label_y = y_offset + thumb_h + label_gap + config.font_size
            if not oiio.ImageBufAlgo.render_text(
                canvas,
                x_offset,
                label_y,
                str(frame_number),
                fontsize=config.font_size,
                textcolor=(1, 1, 1, 1),
            ):
                raise RuntimeError(
                    f"Failed to render frame label {frame_number}: {oiio.geterror()}"
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not canvas.write(str(output_path)):
        raise RuntimeError(f"Failed to write contact sheet: {canvas.geterror() or oiio.geterror()}")


@main.command(name="ui")
def ui() -> None:
    """Launch the RenderKit desktop UI."""
    _launch_ui()


@main.command(name="gui", hidden=True)
def gui() -> None:
    """Launch the RenderKit desktop UI."""
    _launch_ui()


@main.command()
@click.argument("input_pattern", type=str)
@click.argument("output_path", type=click.Path())
@click.option(
    "--prefetch-workers",
    type=int,
    default=2,
    show_default=True,
    help="Number of frame prefetch workers (set to 1 to disable).",
)
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
    type=click.IntRange(0, 10),
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
    type=click.IntRange(0, 100),
    default=30,
    help="Opacity of the burn-in background bar (0-100, default: 30)",
)
@click.option(
    "--contact-sheet", is_flag=True, default=False, help="Enable multi-AOV contact sheet mode"
)
@click.option(
    "--cs-columns",
    type=click.IntRange(1),
    default=4,
    help="Contact sheet columns (default: 4)",
)
@click.option(
    "--cs-thumb-width",
    type=int,
    default=None,
    help="Contact sheet thumbnail width (default: source resolution)",
)
@click.option("--cs-padding", type=int, default=4, help="Contact sheet padding (default: 4)")
@click.option("--cs-no-labels", is_flag=True, default=False, help="Disable contact sheet labels")
@click.option(
    "--profile",
    is_flag=True,
    default=False,
    help="Enable cProfile and write stats to disk.",
)
@click.option(
    "--profile-out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output .prof file or directory (default: temp directory).",
)
@click.option(
    "--no-progress",
    is_flag=True,
    default=False,
    help="Disable progress bars for stable captured logs.",
)
def convert_exr_sequence(
    input_pattern: str,
    output_path: str,
    prefetch_workers: int,
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
    contact_sheet: bool,
    cs_columns: int,
    cs_thumb_width: Optional[int],
    cs_padding: int,
    cs_no_labels: bool,
    profile: bool,
    profile_out: Optional[Path],
    no_progress: bool,
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
        logger.error(f"Output file already exists: {output_path}")
        click.echo("Use --overwrite to overwrite it.", err=True)
        sys.exit(1)

    # Build configuration
    config_builder = base_conversion_config_builder(
        input_pattern=input_pattern,
        output_path=output_path,
        prefetch_workers=prefetch_workers,
        fps=fps,
        color_space=color_space,
        width=width,
        height=height,
        codec=codec,
        quality=quality,
        layer=layer,
    )

    if contact_sheet:
        from renderkit.core.config import ContactSheetConfig

        cs_config = ContactSheetConfig(
            columns=cs_columns,
            thumbnail_width=cs_thumb_width,
            padding=cs_padding,
            show_labels=not cs_no_labels,
        )
        config_builder.with_contact_sheet(True, cs_config)

    if start_frame is not None and end_frame is not None:
        config_builder.with_frame_range(start_frame, end_frame)
    elif start_frame is not None:
        config_builder.with_frame_range(start_frame, start_frame)
    elif end_frame is not None:
        config_builder.with_frame_range(0, end_frame)

    burnin_elements = []
    font_size = 20
    if burnin_frame:
        burnin_elements.append(
            BurnInElement(
                text_template="Frame: {frame}", x=20, y=10, font_size=font_size, alignment="left"
            )
        )
    if burnin_layer:
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
        if profile:
            enabled = True
            output_path_opt = profile_out
        else:
            enabled, output_path_opt = get_profile_env_config()

        with profile_context(enabled, output_path_opt, label="cli-convert"):
            processor.convert_with_config(config, show_progress=False if no_progress else None)
        logger.info(f"Successfully converted to: {output_path}")
        click.echo(f"Successfully converted to: {output_path}")
    except (RenderKitError, OSError, RuntimeError, ValueError) as e:
        logger.exception("Conversion failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


main.add_command(batch_convert)


@main.command()
@click.argument("input_pattern", type=str)
@click.argument("output_path", type=click.Path())
@click.option("--columns", type=int, default=4, help="Number of columns in the grid (default: 4)")
@click.option(
    "--thumb-width",
    type=int,
    default=None,
    help="Width of each thumbnail (default: source resolution)",
)
@click.option("--padding", type=int, default=4, help="Padding between thumbnails (default: 4)")
@click.option(
    "--no-labels", is_flag=True, default=False, help="Disable layer labels below thumbnails"
)
@click.option("--font-size", type=int, default=16, help="Font size for labels (default: 16)")
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
def contact_sheet(
    input_pattern: str,
    output_path: str,
    columns: int,
    thumb_width: Optional[int],
    padding: int,
    no_labels: bool,
    font_size: int,
    layer: Optional[str],
    start_frame: Optional[int],
    end_frame: Optional[int],
    overwrite: bool,
) -> None:
    """Generate a contact sheet from an image sequence.

    INPUT_PATTERN: File pattern with frame number (e.g., "render.%04d.exr")

    OUTPUT_PATH: Output image path (e.g., "contact_sheet.jpg")
    """
    output_path_obj = Path(output_path)

    # Check if output exists
    if output_path_obj.exists() and not overwrite:
        logger.error(f"Output file already exists: {output_path}")
        click.echo("Use --overwrite to overwrite it.", err=True)
        sys.exit(1)

    try:
        config = ContactSheetConfig(
            columns=columns,
            thumbnail_width=thumb_width,
            padding=padding,
            show_labels=not no_labels,
            font_size=font_size,
        )
        _write_sequence_contact_sheet(
            input_pattern=input_pattern,
            output_path=output_path_obj,
            config=config,
            layer=layer,
            start_frame=start_frame,
            end_frame=end_frame,
        )
        logger.info(f"Successfully created contact sheet: {output_path}")
        click.echo(f"Successfully created contact sheet: {output_path}")
    except (RenderKitError, OSError, RuntimeError, ValueError) as e:
        logger.exception("Contact sheet generation failed")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command(name="replace-sequence-with-mp4")
@click.argument("input_pattern", type=str)
@click.argument("output_mp4", type=click.Path(path_type=Path))
@click.option(
    "--delete-source",
    is_flag=True,
    default=False,
    help="Delete source frames after the replacement MP4 is verified.",
)
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Verify the MP4 with ffprobe before replacing frames.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print and audit planned changes without copying or deleting files.",
)
@click.option(
    "--audit-report",
    type=click.Path(path_type=Path),
    default=None,
    help="JSONL audit report path (default: source folder).",
)
def replace_sequence_command(
    input_pattern: str,
    output_mp4: Path,
    delete_source: bool,
    verify: bool,
    dry_run: bool,
    audit_report: Optional[Path],
) -> None:
    """Replace one detected image sequence with an MP4."""
    try:
        result = replace_sequence_with_mp4(
            input_pattern,
            output_mp4,
            delete_source=delete_source,
            verify=verify,
            dry_run=dry_run,
            audit_report=audit_report,
        )
    except RenderKitError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    action = "Would replace" if dry_run else "Replaced"
    click.echo(f"{action}: {input_pattern}")
    click.echo(f"MP4: {result.copied_mp4}")
    if delete_source:
        verb = "would delete" if dry_run else "deleted"
        click.echo(f"Source frames {verb}: {result.deleted_count}")
        click.echo(f"Reclaimed bytes: {result.reclaimed_bytes}")
    click.echo(f"Audit report: {result.audit_report}")


@main.command(name="batch-replace")
@click.argument(
    "root_path",
    type=click.Path(path_type=Path, exists=True, file_okay=False, dir_okay=True),
)
@click.option(
    "--mp4-dir",
    type=click.Path(path_type=Path),
    default=Path("_review_mp4s"),
    show_default=True,
    help="Directory containing replacement MP4s, relative to ROOT_PATH unless absolute.",
)
@click.option(
    "--delete-source",
    is_flag=True,
    default=False,
    help="Delete source frames after each replacement MP4 is verified.",
)
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Verify each MP4 with ffprobe before replacing frames.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print and audit planned changes without copying or deleting files.",
)
@click.option(
    "--audit-report",
    type=click.Path(path_type=Path),
    default=None,
    help="JSONL audit report path (default: ROOT_PATH/renderkit-batch-replace-audit.jsonl).",
)
def batch_replace_command(
    root_path: Path,
    mp4_dir: Path,
    delete_source: bool,
    verify: bool,
    dry_run: bool,
    audit_report: Optional[Path],
) -> None:
    """Replace detected EXR sequences below ROOT_PATH with matching MP4s."""
    mp4_root = mp4_dir if mp4_dir.is_absolute() else root_path / mp4_dir
    report_path = audit_report or (root_path / "renderkit-batch-replace-audit.jsonl")
    patterns = find_exr_sequences(root_path)
    if not patterns:
        click.echo(f"No EXR sequences found below: {root_path}")
        return

    results = []
    planned_outputs: set[Path] = set()
    try:
        for pattern in patterns:
            output_mp4 = find_replacement_mp4(pattern, mp4_root, root_path)
            output_mp4 = deduplicate_output_path(output_mp4, planned_outputs)
            planned_outputs.add(output_mp4)
            result = replace_sequence_with_mp4(
                pattern,
                output_mp4,
                delete_source=delete_source,
                verify=verify,
                dry_run=dry_run,
                audit_report=report_path,
            )
            results.append(result)
    except RenderKitError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    action = "Would replace" if dry_run else "Replaced"
    click.echo(f"{action} sequences: {len(results)}")
    if delete_source:
        deleted_count = sum(result.deleted_count for result in results)
        reclaimed_bytes = sum(result.reclaimed_bytes for result in results)
        verb = "would delete" if dry_run else "deleted"
        click.echo(f"Source frames {verb}: {deleted_count}")
        click.echo(f"Reclaimed bytes: {reclaimed_bytes}")
    click.echo(f"Audit report: {report_path}")


if __name__ == "__main__":
    main()
