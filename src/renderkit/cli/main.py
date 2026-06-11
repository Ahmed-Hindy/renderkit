"""CLI interface for the Render Kit."""

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, TypeVar

import click

from renderkit import __version__
from renderkit.api.processor import RenderKit
from renderkit.core.batch import (
    BatchManifestRecord,
    BatchSequence,
    append_jsonl_manifest,
    build_safe_output_path,
    discover_frame_sequences,
    write_csv_manifest,
)
from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfigBuilder,
    ConversionConfig,
    ConversionConfigBuilder,
)
from renderkit.core.ffmpeg_utils import ensure_ffmpeg_env
from renderkit.core.profiler import get_profile_env_config, profile_context
from renderkit.core.sequence_replacement import (
    find_exr_sequences,
    find_replacement_mp4,
    replace_sequence_with_mp4,
)
from renderkit.exceptions import RenderKitError
from renderkit.logging_utils import setup_logging
from renderkit.processing.color_space import ColorSpacePreset

logger = logging.getLogger("renderkit.cli.main")


COLOR_SPACE_MAP = {
    "linear_to_srgb": ColorSpacePreset.LINEAR_TO_SRGB,
    "linear_to_rec709": ColorSpacePreset.LINEAR_TO_REC709,
    "srgb_to_linear": ColorSpacePreset.SRGB_TO_LINEAR,
    "no_conversion": ColorSpacePreset.NO_CONVERSION,
}

F = TypeVar("F", bound=Callable[..., Any])
ClickOptionSpec = tuple[tuple[str, ...], dict[str, Any]]


BATCH_CONVERT_OPTIONS: tuple[ClickOptionSpec, ...] = (
    (
        ("--ext",),
        {"type": str, "default": "exr", "show_default": True, "help": "Input frame extension."},
    ),
    (
        ("--out", "output_dir"),
        {
            "type": click.Path(path_type=Path),
            "default": Path("_review_mp4s"),
            "show_default": True,
            "help": "Output directory for generated MP4 files.",
        },
    ),
    (
        ("--prefetch-workers",),
        {
            "type": int,
            "default": 2,
            "show_default": True,
            "help": "Number of frame prefetch workers (set to 1 to disable).",
        },
    ),
    (
        ("--fps",),
        {
            "type": float,
            "default": None,
            "help": "Frame rate (fps). If not provided, will attempt auto-detection per sequence.",
        },
    ),
    (
        ("--color-space",),
        {
            "type": click.Choice(
                ["linear_to_srgb", "linear_to_rec709", "srgb_to_linear", "no_conversion"],
                case_sensitive=False,
            ),
            "default": "linear_to_srgb",
            "help": "Color space conversion preset (default: linear_to_srgb)",
        },
    ),
    (("--width",), {"type": int, "default": None, "help": "Output width (default: source width)"}),
    (
        ("--height",),
        {"type": int, "default": None, "help": "Output height (default: source height)"},
    ),
    (
        ("--codec",),
        {
            "type": str,
            "default": "libx264",
            "help": "Video codec (default: libx264, use 'libaom-av1' for AV1)",
        },
    ),
    (
        ("--quality",),
        {
            "type": click.IntRange(0, 10),
            "default": 10,
            "help": "Video quality (0-10), 10 is best (default: 10). Sets CRF.",
        },
    ),
    (
        ("--layer",),
        {"type": str, "default": None, "help": "Specific EXR layer to extract (e.g., 'diffuse')."},
    ),
    (
        ("--overwrite",),
        {"is_flag": True, "default": False, "help": "Overwrite output files if they exist."},
    ),
    (
        ("--manifest-csv",),
        {
            "type": click.Path(path_type=Path),
            "default": None,
            "help": "CSV manifest path (default: OUTPUT_DIR/renderkit_batch_manifest.csv).",
        },
    ),
    (
        ("--manifest-jsonl",),
        {
            "type": click.Path(path_type=Path),
            "default": None,
            "help": "JSONL results path (default: OUTPUT_DIR/renderkit_batch_results.jsonl).",
        },
    ),
    (
        ("--no-progress",),
        {
            "is_flag": True,
            "default": False,
            "help": "Disable progress bars for stable captured logs.",
        },
    ),
)


def _apply_click_options(option_specs: tuple[ClickOptionSpec, ...]) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        decorated = func
        for param_decls, attrs in reversed(option_specs):
            decorated = click.option(*param_decls, **attrs)(decorated)
        return decorated

    return decorator


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
    cs_thumb_width: int,
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
    config_builder = _base_conversion_config_builder(
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


@main.command(name="batch-convert")
@click.argument("root", type=click.Path(path_type=Path))
@_apply_click_options(BATCH_CONVERT_OPTIONS)
def batch_convert(
    root: Path,
    ext: str,
    output_dir: Path,
    prefetch_workers: int,
    fps: Optional[float],
    color_space: str,
    width: Optional[int],
    height: Optional[int],
    codec: str,
    quality: int,
    layer: Optional[str],
    overwrite: bool,
    manifest_csv: Optional[Path],
    manifest_jsonl: Optional[Path],
    no_progress: bool,
) -> None:
    """Recursively convert discovered frame sequences under ROOT to review MP4s."""
    root = root.resolve()
    if not root.is_dir():
        click.echo(f"Error: root directory does not exist: {root}", err=True)
        sys.exit(1)

    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_csv = _resolve_batch_manifest_path(
        root, output_dir, manifest_csv, "renderkit_batch_manifest.csv"
    )
    manifest_jsonl = _resolve_batch_manifest_path(
        root, output_dir, manifest_jsonl, "renderkit_batch_results.jsonl"
    )
    manifest_jsonl.parent.mkdir(parents=True, exist_ok=True)
    manifest_jsonl.write_text("", encoding="utf-8")

    try:
        sequences = discover_frame_sequences(root, ext)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    processor = RenderKit()
    records: list[BatchManifestRecord] = []
    succeeded = 0
    failed = 0
    skipped = 0
    planned_outputs: set[Path] = set()

    for sequence in sequences:
        output_path = build_safe_output_path(root, output_dir, sequence)
        output_path = _deduplicate_batch_output_path(output_path, planned_outputs)
        planned_outputs.add(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists() and not overwrite:
            record = _batch_record(sequence, output_path, "skipped", output_path.stat().st_size)
            records.append(record)
            append_jsonl_manifest(manifest_jsonl, record)
            skipped += 1
            click.echo(f"Skipped existing: {output_path}")
            continue

        try:
            config = _build_batch_conversion_config(
                input_pattern=str(sequence.input_pattern),
                output_path=str(output_path),
                prefetch_workers=prefetch_workers,
                fps=fps,
                color_space=color_space,
                width=width,
                height=height,
                codec=codec,
                quality=quality,
                layer=layer,
            )
            processor.convert_with_config(config, show_progress=False if no_progress else None)
            size_bytes = output_path.stat().st_size if output_path.exists() else None
            record = _batch_record(sequence, output_path, "success", size_bytes)
            succeeded += 1
            click.echo(f"Converted: {sequence.input_pattern} -> {output_path}")
        except (RenderKitError, OSError, RuntimeError, ValueError) as exc:
            logger.exception("Batch conversion failed for %s", sequence.input_pattern)
            record = _batch_record(sequence, output_path, "failed", None, str(exc))
            failed += 1
            click.echo(f"Failed: {sequence.input_pattern}: {exc}", err=True)

        records.append(record)
        append_jsonl_manifest(manifest_jsonl, record)

    write_csv_manifest(manifest_csv, records)

    click.echo(
        "Batch complete: "
        f"{succeeded} succeeded, {failed} failed, {skipped} skipped. "
        f"CSV: {manifest_csv} JSONL: {manifest_jsonl}"
    )

    if failed:
        sys.exit(1)


def _resolve_batch_manifest_path(
    root: Path, output_dir: Path, manifest_path: Optional[Path], default_name: str
) -> Path:
    if manifest_path is None:
        return output_dir / default_name
    if manifest_path.is_absolute():
        return manifest_path
    return root / manifest_path


def _deduplicate_batch_output_path(output_path: Path, planned_outputs: set[Path]) -> Path:
    if output_path not in planned_outputs:
        return output_path

    index = 2
    while True:
        candidate = output_path.with_name(f"{output_path.stem}_{index}{output_path.suffix}")
        if candidate not in planned_outputs:
            return candidate
        index += 1


def _base_conversion_config_builder(
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
) -> ConversionConfigBuilder:
    config_builder = (
        ConversionConfigBuilder()
        .with_input_pattern(input_pattern)
        .with_output_path(output_path)
        .with_prefetch_workers(prefetch_workers)
        .with_color_space_preset(COLOR_SPACE_MAP[color_space.lower()])
        .with_codec(codec)
        .with_quality(quality)
    )

    if layer is not None:
        config_builder.with_layer(layer)

    if fps is not None:
        config_builder.with_fps(fps)

    if width is not None and height is not None:
        config_builder.with_resolution(width, height)

    return config_builder


def _build_batch_conversion_config(
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
) -> ConversionConfig:
    return _base_conversion_config_builder(
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
    ).build()


def _batch_record(
    sequence: BatchSequence,
    output_path: Path,
    status: str,
    size_bytes: Optional[int],
    error: str = "",
) -> BatchManifestRecord:
    return BatchManifestRecord(
        input_pattern=str(sequence.input_pattern),
        output_path=str(output_path),
        frame_count=sequence.frame_count,
        frame_range=sequence.frame_range,
        size_bytes=size_bytes,
        status=status,
        error=error,
    )


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
    "--no-labels", is_flag=True, default=False, help="Disable filename labels below thumbnails"
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
    thumb_width: int,
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

    # Build configuration
    config_builder = (
        ContactSheetConfigBuilder()
        .with_input_pattern(input_pattern)
        .with_output_path(output_path)
        .with_columns(columns)
        .with_padding(padding)
        .with_labels(not no_labels, font_size=font_size)
    )

    if thumb_width is not None:
        config_builder = config_builder.with_thumbnail_width(thumb_width)

    if layer:
        config_builder.with_layer(layer)

    if start_frame is not None and end_frame is not None:
        config_builder.with_frame_range(start_frame, end_frame)

    try:
        config = config_builder.build()
        processor = RenderKit()
        processor.create_contact_sheet(config)
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
    try:
        for pattern in patterns:
            output_mp4 = find_replacement_mp4(pattern, mp4_root)
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
