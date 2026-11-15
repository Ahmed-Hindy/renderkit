"""Batch conversion CLI command."""

import logging
import sys
from pathlib import Path
from typing import Any, Optional

import click

from renderkit.api.processor import RenderKit
from renderkit.cli.conversion import (
    COLOR_SPACE_CHOICES,
    COLOR_SPACE_MAP,
    OCIO_GRADE_OPTIONS,
    ClickOptionSpec,
    apply_click_options,
    apply_frame_range,
    base_conversion_config_builder,
    is_cli_param_set,
    validate_paired_resolution,
)
from renderkit.core.batch import (
    BatchManifestRecord,
    BatchSequence,
    append_jsonl_manifest,
    build_safe_output_path,
    deduplicate_output_path,
    discover_frame_sequences,
    watch_and_convert_sequences,
    write_csv_manifest,
)
from renderkit.core.config import ConversionConfig
from renderkit.core.presets import load_preset, resolve_preset_path
from renderkit.exceptions import RenderKitError
from renderkit.processing.video_encoder import get_codec_profile

logger = logging.getLogger("renderkit.cli.batch")


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
                list(COLOR_SPACE_CHOICES),
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
    *OCIO_GRADE_OPTIONS,
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
    (
        ("--preset",),
        {
            "type": str,
            "default": None,
            "help": "Load base conversion settings from a preset name or JSON file.",
        },
    ),
    (
        ("--watch",),
        {
            "is_flag": True,
            "default": False,
            "help": "Continuously poll ROOT for newly settled sequences and convert them.",
        },
    ),
    (
        ("--watch-interval",),
        {
            "type": float,
            "default": 5.0,
            "show_default": True,
            "help": "Seconds between watch folder polls.",
        },
    ),
    (
        ("--settle-seconds",),
        {
            "type": float,
            "default": 2.0,
            "show_default": True,
            "help": "Minimum age in seconds since last frame write before converting.",
        },
    ),
    (
        ("--max-polls",),
        {
            "type": int,
            "default": None,
            "help": "Maximum number of watch polls before exiting (default: unlimited).",
        },
    ),
)


@click.command(name="batch-convert")
@click.argument("root", type=click.Path(path_type=Path))
@apply_click_options(BATCH_CONVERT_OPTIONS)
@click.pass_context
def batch_convert(
    ctx: click.Context,
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
    ocio: Optional[str],
    input_space: Optional[str],
    display: Optional[str],
    view: Optional[str],
    exposure: float,
    gamma: float,
    overwrite: bool,
    manifest_csv: Optional[Path],
    manifest_jsonl: Optional[Path],
    no_progress: bool,
    preset: Optional[str],
    watch: bool,
    watch_interval: float,
    settle_seconds: float,
    max_polls: Optional[int],
) -> None:
    """Recursively convert discovered frame sequences under ROOT to review videos."""
    validate_paired_resolution(width, height)
    if watch_interval <= 0:
        raise click.BadParameter("must be greater than 0", param_hint="'--watch-interval'")
    if settle_seconds < 0:
        raise click.BadParameter("must be >= 0", param_hint="'--settle-seconds'")
    if max_polls is not None and max_polls < 1:
        raise click.BadParameter("must be >= 1", param_hint="'--max-polls'")

    root = root.resolve()
    if not root.is_dir():
        click.echo(f"Error: root directory does not exist: {root}", err=True)
        sys.exit(1)

    preset_data: dict[str, Any] = {}
    if preset is not None:
        try:
            preset_path = resolve_preset_path(preset)
            preset_data = load_preset(preset_path)
        except RenderKitError as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(1)

    effective_codec = (
        codec
        if preset is None or is_cli_param_set(ctx, "codec")
        else str(preset_data.get("codec", codec))
    )
    container_ext = get_codec_profile(effective_codec).container_ext

    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    def _build_config_for_sequence(sequence: BatchSequence, output_path: Path) -> ConversionConfig:
        return _build_batch_conversion_config_with_preset(
            ctx,
            preset_data=preset_data if preset is not None else None,
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
            ocio=ocio,
            input_space=input_space,
            display=display,
            view=view,
            exposure=exposure,
            gamma=gamma,
        )

    processor = RenderKit()

    if watch:

        class _BatchWatchConverter:
            def __init__(self, config: ConversionConfig) -> None:
                self._config = config

            def convert(self) -> None:
                processor.convert_with_config(
                    self._config,
                    show_progress=False if no_progress else None,
                )

        def _build_watch_config(sequence: BatchSequence) -> ConversionConfig:
            output_path = build_safe_output_path(
                root,
                output_dir,
                sequence,
                container_ext=container_ext,
            )
            return _build_config_for_sequence(sequence, output_path)

        produced = watch_and_convert_sequences(
            root,
            _build_watch_config,
            extension=ext,
            settle_seconds=settle_seconds,
            poll_interval=watch_interval,
            max_polls=max_polls,
            converter_factory=_BatchWatchConverter,
        )
        click.echo(f"Watch complete: {len(produced)} sequence(s) converted.")
        return

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

    records: list[BatchManifestRecord] = []
    succeeded = 0
    failed = 0
    skipped = 0
    planned_outputs: set[Path] = set()

    for sequence in sequences:
        output_path = build_safe_output_path(
            root,
            output_dir,
            sequence,
            container_ext=container_ext,
        )
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
            config = _build_config_for_sequence(sequence, output_path)
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


def _build_batch_conversion_config_with_preset(
    ctx: Optional[click.Context],
    *,
    preset_data: Optional[dict[str, Any]],
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
    ocio: Optional[str] = None,
    input_space: Optional[str] = None,
    display: Optional[str] = None,
    view: Optional[str] = None,
    exposure: float = 0.0,
    gamma: float = 1.0,
) -> ConversionConfig:
    if preset_data is None:
        return _build_batch_conversion_config(
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
            ocio=ocio,
            input_space=input_space,
            display=display,
            view=view,
            exposure=exposure,
            gamma=gamma,
        )

    def _pick(param_name: str, cli_val: Any, preset_key: Optional[str] = None) -> Any:
        if is_cli_param_set(ctx, param_name):
            return cli_val
        key = preset_key or param_name
        return preset_data.get(key, cli_val)

    eff_prefetch = int(_pick("prefetch_workers", prefetch_workers))
    eff_fps = _pick("fps", fps)
    eff_codec = str(_pick("codec", codec))
    eff_quality = int(_pick("quality", quality))
    eff_layer = _pick("layer", layer)
    eff_ocio = _pick("ocio", ocio, "ocio_config_path")
    eff_input_space = _pick("input_space", input_space, "explicit_input_color_space")
    eff_display = _pick("display", display, "ocio_display")
    eff_view = _pick("view", view, "ocio_view")
    eff_output_space = preset_data.get("ocio_output_space")
    eff_exposure = float(_pick("exposure", exposure))
    eff_gamma = float(_pick("gamma", gamma))

    if not is_cli_param_set(ctx, "width"):
        eff_width = preset_data.get("width", width)
        eff_height = preset_data.get("height", height)
    else:
        eff_width = width
        eff_height = height

    if (
        not is_cli_param_set(ctx, "color_space")
        and preset_data.get("color_space_preset") is not None
    ):
        eff_color_str = str(preset_data["color_space_preset"].value)
    else:
        eff_color_str = color_space

    config_builder = base_conversion_config_builder(
        input_pattern=input_pattern,
        output_path=output_path,
        prefetch_workers=eff_prefetch,
        fps=eff_fps,
        color_space=eff_color_str,
        width=eff_width,
        height=eff_height,
        codec=eff_codec,
        quality=eff_quality,
        layer=eff_layer,
        ocio=eff_ocio,
        input_space=eff_input_space,
        display=eff_display,
        view=eff_view,
        exposure=eff_exposure,
        gamma=eff_gamma,
    )

    if eff_output_space is not None:
        config_builder.with_ocio(output_space=eff_output_space)

    if is_cli_param_set(ctx, "color_space") and not any(
        is_cli_param_set(ctx, name) for name in ("ocio", "display", "view")
    ):
        config_builder.with_color_space_preset(COLOR_SPACE_MAP[color_space.lower()])

    if preset_data.get("bitrate") is not None:
        config_builder.with_bitrate(int(preset_data["bitrate"]))

    apply_frame_range(
        config_builder,
        preset_data.get("start_frame"),
        preset_data.get("end_frame"),
    )

    if (
        preset_data.get("contact_sheet_mode")
        and preset_data.get("contact_sheet_config") is not None
    ):
        config_builder.with_contact_sheet(True, preset_data["contact_sheet_config"])

    if preset_data.get("burnin_config") is not None:
        config_builder.with_burnin(preset_data["burnin_config"])

    if preset_data.get("slate_config") is not None:
        config_builder.with_slate(preset_data["slate_config"])

    if preset_data.get("watermark_config") is not None and hasattr(
        config_builder, "with_watermark"
    ):
        config_builder.with_watermark(preset_data["watermark_config"])

    return config_builder.build()


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
    ocio: Optional[str] = None,
    input_space: Optional[str] = None,
    display: Optional[str] = None,
    view: Optional[str] = None,
    exposure: float = 0.0,
    gamma: float = 1.0,
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
        ocio=ocio,
        input_space=input_space,
        display=display,
        view=view,
        exposure=exposure,
        gamma=gamma,
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
