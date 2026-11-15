"""JSON preset serialization and deserialization for conversion settings."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfig,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.exceptions import ConfigurationError
from renderkit.processing.color_space import ColorSpacePreset

PRESET_SCHEMA_VERSION = 1


def resolve_preset_path(preset_arg: str | Path) -> Path:
    """Resolve a preset file path directly or via ``RENDERKIT_PRESET_PATH``.

    Args:
        preset_arg: Direct file path or preset name/relative path to search.

    Returns:
        Resolved existing preset ``Path``.

    Raises:
        ConfigurationError: If no matching preset file exists.
    """
    arg_str = str(preset_arg).strip()
    if not arg_str:
        raise ConfigurationError(f"Preset file not found: {preset_arg}")

    path = Path(preset_arg)
    if path.is_file():
        return path

    search_env = os.environ.get("RENDERKIT_PRESET_PATH", "")
    for raw_dir in search_env.split(os.pathsep):
        directory = raw_dir.strip()
        if not directory:
            continue
        base_dir = Path(directory)
        candidate = base_dir / path
        if candidate.is_file():
            return candidate
        if not arg_str.endswith(".json"):
            json_candidate = base_dir / f"{arg_str}.json"
            if json_candidate.is_file():
                return json_candidate

    raise ConfigurationError(f"Preset file not found: {preset_arg}")


def _serialize_burnin_config(config: Optional[BurnInConfig]) -> Optional[dict[str, Any]]:
    if config is None:
        return None
    return {
        "elements": [
            {
                "text_template": el.text_template,
                "x": el.x,
                "y": el.y,
                "font": el.font,
                "font_size": el.font_size,
                "color": list(el.color),
                "alignment": el.alignment,
                "zone": el.zone,
            }
            for el in config.elements
        ],
        "use_background": config.use_background,
        "background_opacity": config.background_opacity,
    }


def _deserialize_burnin_config(raw: Any) -> Optional[BurnInConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigurationError("Preset 'burnin_config' must be an object or null.")
    raw_elements = raw.get("elements", [])
    if not isinstance(raw_elements, list):
        raise ConfigurationError("Preset 'burnin_config.elements' must be a list.")

    elements: list[BurnInElement] = []
    for item in raw_elements:
        if not isinstance(item, dict):
            raise ConfigurationError("Each burn-in element in preset must be an object.")
        color_raw = item.get("color", (1.0, 1.0, 1.0))
        if not isinstance(color_raw, (list, tuple)) or len(color_raw) != 3:
            raise ConfigurationError("Burn-in element 'color' must have 3 numeric components.")
        color = (float(color_raw[0]), float(color_raw[1]), float(color_raw[2]))
        try:
            elements.append(
                BurnInElement(
                    text_template=item["text_template"],
                    x=item.get("x", 50),
                    y=item.get("y", 50),
                    font=item.get("font", ""),
                    font_size=item.get("font_size", 24),
                    color=color,
                    alignment=item.get("alignment", "left"),
                    zone=item.get("zone"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid burn-in element in preset: {exc}") from exc

    try:
        return BurnInConfig(
            elements=elements,
            use_background=bool(raw.get("use_background", True)),
            background_opacity=int(raw.get("background_opacity", 30)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid burn-in configuration in preset: {exc}") from exc


def _serialize_contact_sheet_config(
    config: Optional[ContactSheetConfig],
) -> Optional[dict[str, Any]]:
    if config is None:
        return None
    data = asdict(config)
    data["background_color"] = list(config.background_color)
    return data


def _deserialize_contact_sheet_config(raw: Any) -> Optional[ContactSheetConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigurationError("Preset 'contact_sheet_config' must be an object or null.")
    bg_raw = raw.get("background_color", (0.1, 0.1, 0.1))
    if not isinstance(bg_raw, (list, tuple)) or len(bg_raw) != 3:
        raise ConfigurationError("Contact sheet 'background_color' must have 3 numeric components.")
    kwargs = dict(raw)
    kwargs["background_color"] = (float(bg_raw[0]), float(bg_raw[1]), float(bg_raw[2]))
    try:
        return ContactSheetConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid contact sheet configuration in preset: {exc}") from exc


def _serialize_slate_config(config: Optional[SlateConfig]) -> Optional[dict[str, Any]]:
    if config is None:
        return None
    data = asdict(config)
    data["background_color"] = list(config.background_color)
    return data


def _deserialize_slate_config(raw: Any) -> Optional[SlateConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigurationError("Preset 'slate_config' must be an object or null.")
    bg_raw = raw.get("background_color", (0.06, 0.06, 0.08, 1.0))
    if not isinstance(bg_raw, (list, tuple)) or len(bg_raw) != 4:
        raise ConfigurationError("Slate 'background_color' must have 4 numeric components.")
    kwargs = dict(raw)
    kwargs["background_color"] = (
        float(bg_raw[0]),
        float(bg_raw[1]),
        float(bg_raw[2]),
        float(bg_raw[3]),
    )
    try:
        return SlateConfig(**kwargs)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid slate configuration in preset: {exc}") from exc


def _serialize_watermark_config(config: Optional[WatermarkConfig]) -> Optional[dict[str, Any]]:
    if config is None:
        return None
    return asdict(config)


def _deserialize_watermark_config(raw: Any) -> Optional[WatermarkConfig]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigurationError("Preset 'watermark_config' must be an object or null.")
    try:
        return WatermarkConfig(
            text=raw["text"],
            opacity=int(raw.get("opacity", 25)),
            font_size=int(raw.get("font_size", 36)),
            tiled=bool(raw.get("tiled", False)),
            spacing=int(raw.get("spacing", 240)),
        )
    except ConfigurationError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid watermark configuration in preset: {exc}") from exc


def save_preset(config: ConversionConfig, path: Path) -> None:
    """Serialize non-path conversion settings from a ConversionConfig to a JSON preset file.

    Args:
        config: Conversion configuration to save.
        path: Destination JSON file path.

    Raises:
        ConfigurationError: If the preset file cannot be written.
    """
    payload: dict[str, Any] = {
        "schema_version": PRESET_SCHEMA_VERSION,
        "prefetch_workers": config.prefetch_workers,
        "fps": config.fps,
        "color_space_preset": config.color_space_preset.value,
        "width": config.width,
        "height": config.height,
        "codec": config.codec,
        "bitrate": config.bitrate,
        "quality": config.quality,
        "layer": config.layer,
        "start_frame": config.start_frame,
        "end_frame": config.end_frame,
        "explicit_input_color_space": config.explicit_input_color_space,
        "ocio_config_path": config.ocio_config_path,
        "ocio_display": config.ocio_display,
        "ocio_view": config.ocio_view,
        "ocio_output_space": config.ocio_output_space,
        "exposure": config.exposure,
        "gamma": config.gamma,
        "burnin_config": _serialize_burnin_config(config.burnin_config),
        "contact_sheet_mode": config.contact_sheet_mode,
        "contact_sheet_config": _serialize_contact_sheet_config(config.contact_sheet_config),
        "slate_config": _serialize_slate_config(config.slate_config),
        "watermark_config": _serialize_watermark_config(config.watermark_config),
    }

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Failed to save preset to '{path}': {exc}") from exc


def load_preset(path: Path) -> dict[str, Any]:
    """Load and validate conversion settings from a JSON preset file.

    Args:
        path: Source JSON preset file path.

    Returns:
        Dictionary of deserialized non-path conversion settings.

    Raises:
        ConfigurationError: If the preset file is missing, unreadable, malformed,
            or uses an unsupported schema version.
    """
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Failed to read preset file '{path}': {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in preset file '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError(f"Preset file '{path}' must contain a JSON object.")

    schema_version = data.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != PRESET_SCHEMA_VERSION
    ):
        raise ConfigurationError(
            f"Unsupported preset schema_version '{schema_version}'; expected {PRESET_SCHEMA_VERSION}."
        )

    result: dict[str, Any] = {}
    scalar_keys = (
        "prefetch_workers",
        "fps",
        "width",
        "height",
        "codec",
        "bitrate",
        "quality",
        "layer",
        "start_frame",
        "end_frame",
        "explicit_input_color_space",
        "ocio_config_path",
        "ocio_display",
        "ocio_view",
        "ocio_output_space",
        "exposure",
        "gamma",
        "contact_sheet_mode",
    )
    for key in scalar_keys:
        if key in data:
            result[key] = data[key]

    if "color_space_preset" in data and data["color_space_preset"] is not None:
        raw_preset = data["color_space_preset"]
        if not isinstance(raw_preset, str):
            raise ConfigurationError("Preset 'color_space_preset' must be a string.")
        try:
            result["color_space_preset"] = ColorSpacePreset(raw_preset.lower())
        except ValueError as exc:
            raise ConfigurationError(
                f"Invalid color_space_preset '{raw_preset}' in preset."
            ) from exc

    if "burnin_config" in data:
        result["burnin_config"] = _deserialize_burnin_config(data["burnin_config"])

    if "contact_sheet_config" in data:
        result["contact_sheet_config"] = _deserialize_contact_sheet_config(
            data["contact_sheet_config"]
        )

    if "slate_config" in data:
        result["slate_config"] = _deserialize_slate_config(data["slate_config"])

    if "watermark_config" in data:
        result["watermark_config"] = _deserialize_watermark_config(data["watermark_config"])

    return result
