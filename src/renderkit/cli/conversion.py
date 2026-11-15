"""Shared conversion helpers for CLI commands."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional, TypeVar

import click

from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfigBuilder,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.core.presets import load_preset, resolve_preset_path
from renderkit.processing.color_space import ColorSpacePreset

F = TypeVar("F", bound=Callable[..., Any])
ClickOptionSpec = tuple[tuple[str, ...], dict[str, Any]]

COLOR_SPACE_MAP = {
    "linear_to_srgb": ColorSpacePreset.LINEAR_TO_SRGB,
    "linear_to_rec709": ColorSpacePreset.LINEAR_TO_REC709,
    "srgb_to_linear": ColorSpacePreset.SRGB_TO_LINEAR,
    "no_conversion": ColorSpacePreset.NO_CONVERSION,
    "ocio_conversion": ColorSpacePreset.OCIO_CONVERSION,
}
COLOR_SPACE_CHOICES = tuple(COLOR_SPACE_MAP.keys())

OCIO_GRADE_OPTIONS: tuple[ClickOptionSpec, ...] = (
    (
        ("--ocio",),
        {
            "type": str,
            "default": None,
            "help": "Path to a custom OpenColorIO config file.",
        },
    ),
    (
        ("--input-space",),
        {
            "type": str,
            "default": None,
            "help": "Explicit input color space name (for OCIO).",
        },
    ),
    (
        ("--display",),
        {
            "type": str,
            "default": None,
            "help": "OCIO display name.",
        },
    ),
    (
        ("--view",),
        {
            "type": str,
            "default": None,
            "help": "OCIO view name.",
        },
    ),
    (
        ("--exposure",),
        {
            "type": float,
            "default": 0.0,
            "show_default": True,
            "help": "Exposure adjustment in stops.",
        },
    ),
    (
        ("--gamma",),
        {
            "type": float,
            "default": 1.0,
            "show_default": True,
            "help": "Gamma adjustment (> 0).",
        },
    ),
)


def apply_click_options(option_specs: tuple[ClickOptionSpec, ...]) -> Callable[[F], F]:
    """Attach a tuple of Click option specifications to a command function."""

    def decorator(func: F) -> F:
        decorated = func
        for param_decls, attrs in reversed(option_specs):
            decorated = click.option(*param_decls, **attrs)(decorated)
        return decorated

    return decorator


def validate_paired_resolution(width: Optional[int], height: Optional[int]) -> None:
    """Require CLI resolution overrides to include both dimensions."""
    if (width is None) != (height is None):
        raise click.UsageError("--width and --height must be used together.")


def is_cli_param_set(ctx: Optional[click.Context], param_name: str) -> bool:
    """Return whether a Click parameter was explicitly provided by the caller."""
    if ctx is None:
        return False
    source = ctx.get_parameter_source(param_name)
    return source is not None and source != click.core.ParameterSource.DEFAULT


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
    ocio: Optional[str] = None,
    input_space: Optional[str] = None,
    display: Optional[str] = None,
    view: Optional[str] = None,
    exposure: float = 0.0,
    gamma: float = 1.0,
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
        .with_grade(exposure=exposure, gamma=gamma)
    )

    if any(value is not None for value in (ocio, input_space, display, view)):
        config_builder.with_ocio(
            config_path=ocio,
            input_space=input_space,
            display=display,
            view=view,
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


def build_cli_conversion_builder(
    ctx: Optional[click.Context],
    *,
    input_pattern: str,
    output_path: str,
    preset_path: Optional[Path],
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
    ocio: Optional[str],
    input_space: Optional[str],
    display: Optional[str],
    view: Optional[str],
    exposure: float,
    gamma: float,
    burnin_frame: bool,
    burnin_layer: bool,
    burnin_fps: bool,
    burnin_opacity: int,
    contact_sheet: bool,
    cs_columns: int,
    cs_thumb_width: Optional[int],
    cs_padding: int,
    cs_no_labels: bool,
    slate: bool,
    slate_title: str,
    slate_show: str,
    slate_shot: str,
    slate_artist: str,
    slate_notes: str,
    watermark_text: Optional[str] = None,
    watermark_opacity: int = 25,
    watermark_tiled: bool = False,
) -> ConversionConfigBuilder:
    """Build a ConversionConfigBuilder merging optional preset defaults with CLI flags."""
    resolved_preset_path = resolve_preset_path(preset_path) if preset_path is not None else None
    preset_data: dict[str, Any] = (
        load_preset(resolved_preset_path) if resolved_preset_path is not None else {}
    )

    def _pick(param_name: str, cli_val: Any, preset_key: Optional[str] = None) -> Any:
        if preset_path is None or is_cli_param_set(ctx, param_name):
            return cli_val
        key = preset_key or param_name
        return preset_data.get(key, cli_val)

    eff_prefetch = _pick("prefetch_workers", prefetch_workers)
    eff_fps = _pick("fps", fps)
    eff_codec = _pick("codec", codec)
    eff_quality = _pick("quality", quality)
    eff_layer = _pick("layer", layer)
    eff_start = _pick("start_frame", start_frame)
    eff_end = _pick("end_frame", end_frame)
    eff_ocio = _pick("ocio", ocio, "ocio_config_path")
    eff_input_space = _pick("input_space", input_space, "explicit_input_color_space")
    eff_display = _pick("display", display, "ocio_display")
    eff_view = _pick("view", view, "ocio_view")
    eff_output_space = preset_data.get("ocio_output_space")
    eff_exposure = _pick("exposure", exposure)
    eff_gamma = _pick("gamma", gamma)

    if preset_path is not None and not is_cli_param_set(ctx, "width"):
        eff_width = preset_data.get("width", width)
        eff_height = preset_data.get("height", height)
    else:
        eff_width = width
        eff_height = height

    if preset_path is not None and not is_cli_param_set(ctx, "color_space"):
        eff_color_preset = preset_data.get(
            "color_space_preset", COLOR_SPACE_MAP[color_space.lower()]
        )
        eff_color_str = eff_color_preset.value
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

    if (
        preset_path is not None
        and is_cli_param_set(ctx, "color_space")
        and not any(is_cli_param_set(ctx, name) for name in ("ocio", "display", "view"))
    ):
        config_builder.with_color_space_preset(COLOR_SPACE_MAP[color_space.lower()])

    if "bitrate" in preset_data and preset_data["bitrate"] is not None:
        config_builder.with_bitrate(preset_data["bitrate"])

    apply_frame_range(config_builder, eff_start, eff_end)

    if contact_sheet:
        cs_config = ContactSheetConfig(
            columns=cs_columns,
            thumbnail_width=cs_thumb_width,
            padding=cs_padding,
            show_labels=not cs_no_labels,
        )
        config_builder.with_contact_sheet(True, cs_config)
    elif (
        preset_path is not None
        and not is_cli_param_set(ctx, "contact_sheet")
        and preset_data.get("contact_sheet_mode")
        and preset_data.get("contact_sheet_config") is not None
    ):
        config_builder.with_contact_sheet(True, preset_data["contact_sheet_config"])

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
    elif preset_data.get("burnin_config") is not None:
        config_builder.with_burnin(preset_data["burnin_config"])

    preset_slate: Optional[SlateConfig] = preset_data.get("slate_config")
    slate_fields_set = any(
        is_cli_param_set(ctx, name)
        for name in (
            "slate",
            "slate_title",
            "slate_show",
            "slate_shot",
            "slate_artist",
            "slate_notes",
        )
    )
    if slate or (preset_slate is not None and slate_fields_set):
        base_slate = preset_slate if preset_slate is not None else SlateConfig(enabled=slate)
        config_builder.with_slate(
            SlateConfig(
                enabled=True if slate else base_slate.enabled,
                title=slate_title if is_cli_param_set(ctx, "slate_title") else base_slate.title,
                show=slate_show if is_cli_param_set(ctx, "slate_show") else base_slate.show,
                shot=slate_shot if is_cli_param_set(ctx, "slate_shot") else base_slate.shot,
                artist=slate_artist if is_cli_param_set(ctx, "slate_artist") else base_slate.artist,
                notes=slate_notes if is_cli_param_set(ctx, "slate_notes") else base_slate.notes,
                background_color=base_slate.background_color,
            )
        )
    elif preset_slate is not None:
        config_builder.with_slate(preset_slate)

    preset_watermark: Optional[WatermarkConfig] = preset_data.get("watermark_config")
    if watermark_text is not None:
        config_builder.with_watermark(
            WatermarkConfig(
                text=watermark_text,
                opacity=watermark_opacity,
                tiled=watermark_tiled,
                font_size=preset_watermark.font_size if preset_watermark is not None else 36,
                spacing=preset_watermark.spacing if preset_watermark is not None else 240,
            )
        )
    elif preset_watermark is not None:
        config_builder.with_watermark(
            WatermarkConfig(
                text=preset_watermark.text,
                opacity=(
                    watermark_opacity
                    if is_cli_param_set(ctx, "watermark_opacity")
                    else preset_watermark.opacity
                ),
                font_size=preset_watermark.font_size,
                tiled=(
                    watermark_tiled
                    if is_cli_param_set(ctx, "watermark_tiled")
                    else preset_watermark.tiled
                ),
                spacing=preset_watermark.spacing,
            )
        )

    return config_builder
