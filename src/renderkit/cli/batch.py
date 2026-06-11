"""Batch conversion CLI command."""

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, TypeVar

import click

from renderkit.api.processor import RenderKit
from renderkit.cli.conversion import base_conversion_config_builder
from renderkit.core.batch import (
    BatchManifestRecord,
    BatchSequence,
    append_jsonl_manifest,
    build_safe_output_path,
    deduplicate_output_path,
    discover_frame_sequences,
    write_csv_manifest,
)
from renderkit.core.config import ConversionConfig
from renderkit.exceptions import RenderKitError

logger = logging.getLogger("renderkit.cli.batch")

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


@click.command(name="batch-convert")
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
        output_path = deduplicate_output_path(output_path, planned_outputs)
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


def _build_batch_conversion_config(
    input_pattern: str,
    output_path: str | Path,
    prefetch_workers: int,
    fps: Optional[float],
    color_space: str,
    width: Optional[int],
    height: Optional[int],
    codec: str,
    quality: int,
    layer: Optional[str],
) -> ConversionConfig:
    return base_conversion_config_builder(
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
