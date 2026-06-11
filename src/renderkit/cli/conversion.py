"""Shared conversion helpers for CLI commands."""

from pathlib import Path
from typing import Optional

import click

from renderkit.core.config import ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

COLOR_SPACE_MAP = {
    "linear_to_srgb": ColorSpacePreset.LINEAR_TO_SRGB,
    "linear_to_rec709": ColorSpacePreset.LINEAR_TO_REC709,
    "srgb_to_linear": ColorSpacePreset.SRGB_TO_LINEAR,
    "no_conversion": ColorSpacePreset.NO_CONVERSION,
}


def validate_paired_resolution(width: Optional[int], height: Optional[int]) -> None:
    """Require CLI resolution overrides to include both dimensions."""
    if (width is None) != (height is None):
        raise click.UsageError("--width and --height must be used together.")


def base_conversion_config_builder(
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
) -> ConversionConfigBuilder:
    """Build shared conversion settings used by CLI conversion commands."""
    validate_paired_resolution(width, height)

    config_builder = (
        ConversionConfigBuilder()
        .with_input_pattern(input_pattern)
        .with_output_path(str(output_path))
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


def apply_frame_range(
    config_builder: ConversionConfigBuilder,
    start_frame: Optional[int],
    end_frame: Optional[int],
) -> None:
    """Apply an optional open-ended frame range to a conversion builder."""
    if start_frame is not None or end_frame is not None:
        config_builder.with_frame_range(start_frame, end_frame)
