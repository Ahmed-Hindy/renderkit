"""Houdini 21.0 ROP/LOP post-render and UI launcher integrations."""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import ContactSheetConfig, ConversionConfig, ConversionConfigBuilder
from renderkit.core.converter import SequenceConverter
from renderkit.core.presets import load_preset, resolve_preset_path
from renderkit.exceptions import ConfigurationError
from renderkit.processing.video_encoder import get_codec_profile

_ROP_OUTPUT_PARMS = (
    "vm_picture",
    "picture",
    "lopoutput",
    "sopoutput",
    "outputimage",
)
_DEFAULT_HOUDINI_FPS = 24.0


def _get_hou() -> Any:
    """Import Houdini's ``hou`` module optionally."""
    try:
        return importlib.import_module("hou")
    except ImportError:
        return None


def _eval_parm(node: Any, parm_name: str) -> Any:
    if node is None:
        return None
    parm_fn = getattr(node, "parm", None)
    if not callable(parm_fn):
        return None
    parm = parm_fn(parm_name)
    if parm is None:
        return None
    eval_fn = getattr(parm, "eval", None)
    if callable(eval_fn):
        return eval_fn()
    eval_str_fn = getattr(parm, "evalAsString", None)
    if callable(eval_str_fn):
        return eval_str_fn()
    return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _default_output_video_path(output_pattern: str | Path, container_ext: str) -> Path:
    pattern_path = Path(output_pattern)
    stem = pattern_path.stem
    cleaned = re.sub(r"(?:[._-])?(?:%0?\d*d|\$F\d*|#+|\d{3,5})$", "", stem)
    base_name = cleaned or stem or "render"
    return pattern_path.parent / f"{base_name}{container_ext}"


def _apply_preset_to_builder(
    builder: ConversionConfigBuilder,
    preset_data: Mapping[str, Any],
) -> None:
    if preset_data.get("prefetch_workers") is not None:
        builder.with_prefetch_workers(int(preset_data["prefetch_workers"]))
    if preset_data.get("color_space_preset") is not None:
        builder.with_color_space_preset(preset_data["color_space_preset"])
    if preset_data.get("width") is not None and preset_data.get("height") is not None:
        builder.with_resolution(int(preset_data["width"]), int(preset_data["height"]))
    if preset_data.get("bitrate") is not None:
        builder.with_bitrate(int(preset_data["bitrate"]))
    if preset_data.get("quality") is not None:
        builder.with_quality(int(preset_data["quality"]))
    if preset_data.get("layer") is not None:
        builder.with_layer(str(preset_data["layer"]))
    if preset_data.get("start_frame") is not None or preset_data.get("end_frame") is not None:
        builder.with_frame_range(preset_data.get("start_frame"), preset_data.get("end_frame"))
    if any(
        preset_data.get(key) is not None
        for key in (
            "ocio_config_path",
            "explicit_input_color_space",
            "ocio_display",
            "ocio_view",
            "ocio_output_space",
        )
    ):
        builder.with_ocio(
            config_path=preset_data.get("ocio_config_path"),
            input_space=preset_data.get("explicit_input_color_space"),
            display=preset_data.get("ocio_display"),
            view=preset_data.get("ocio_view"),
            output_space=preset_data.get("ocio_output_space"),
        )
    if preset_data.get("exposure") is not None or preset_data.get("gamma") is not None:
        builder.with_grade(
            exposure=float(preset_data.get("exposure", 0.0)),
            gamma=float(preset_data.get("gamma", 1.0)),
        )
    if preset_data.get("burnin_config") is not None:
        builder.with_burnin(preset_data["burnin_config"])
    if (
        preset_data.get("contact_sheet_mode")
        and preset_data.get("contact_sheet_config") is not None
    ):
        builder.with_contact_sheet(True, preset_data["contact_sheet_config"])
    if preset_data.get("slate_config") is not None:
        builder.with_slate(preset_data["slate_config"])
    if preset_data.get("watermark_config") is not None and hasattr(builder, "with_watermark"):
        builder.with_watermark(preset_data["watermark_config"])


def extract_houdini_rop_context(
    node: Any = None,
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Extract render sequence context from a Houdini 21.0 ROP/LOP/SOP/COP node.

    Args:
        node: Optional Houdini node (defaults to ``hou.pwd()`` when inside Houdini).
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Dictionary containing ``output_pattern``, ``first_frame``, ``last_frame``,
        ``fps``, and ``ocio_config_path``.
    """
    hou = _get_hou()
    env_map = os.environ if env is None else env

    if node is None and hou is not None and hasattr(hou, "pwd"):
        node = hou.pwd()

    output_pattern: Optional[str] = None
    for parm_name in _ROP_OUTPUT_PARMS:
        value = _eval_parm(node, parm_name)
        if isinstance(value, str) and value.strip():
            output_pattern = value.strip()
            break

    first_frame = _coerce_int(_eval_parm(node, "f1"))
    last_frame = _coerce_int(_eval_parm(node, "f2"))
    if (first_frame is None or last_frame is None) and hou is not None:
        playbar = getattr(hou, "playbar", None)
        frame_range_fn = getattr(playbar, "frameRange", None) if playbar is not None else None
        if callable(frame_range_fn):
            try:
                frame_range = frame_range_fn()
                if len(frame_range) >= 2:
                    if first_frame is None:
                        first_frame = _coerce_int(frame_range[0])
                    if last_frame is None:
                        last_frame = _coerce_int(frame_range[1])
            except (TypeError, ValueError):
                pass

    fps = _DEFAULT_HOUDINI_FPS
    if hou is not None and hasattr(hou, "fps"):
        try:
            hou_fps = float(hou.fps())
            if hou_fps > 0:
                fps = hou_fps
        except (TypeError, ValueError):
            pass

    ocio_raw = env_map.get("OCIO", "")
    ocio_config_path = ocio_raw.strip() or None

    return {
        "output_pattern": output_pattern,
        "first_frame": first_frame,
        "last_frame": last_frame,
        "fps": fps,
        "ocio_config_path": ocio_config_path,
    }


def run_houdini_post_render(
    output_pattern: str | Path,
    *,
    output_video: Optional[str | Path] = None,
    preset: Optional[str | Path] = None,
    fps: Optional[float] = None,
    ocio_config_path: Optional[str] = None,
    codec: str = "libx264",
    contact_sheet: bool = False,
    env: Optional[Mapping[str, str]] = None,
) -> Path:
    """Convert a Houdini rendered frame sequence to review video after render completion.

    Args:
        output_pattern: Frame sequence pattern or sample frame path from the ROP.
        output_video: Optional target video path (derived from ``output_pattern`` if omitted).
        preset: Optional preset name or JSON preset path.
        fps: Optional explicit FPS override.
        ocio_config_path: Optional OCIO config path (falls back to ``$OCIO``).
        codec: Target video codec (defaults to ``'libx264'`` unless overridden by preset).
        contact_sheet: Whether to enable multi-AOV contact sheet mode.
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Path to the generated review video file.
    """
    pattern_str = str(output_pattern).strip()
    if not pattern_str:
        raise ConfigurationError("Houdini output_pattern cannot be empty.")

    env_map = os.environ if env is None else env
    preset_data: dict[str, Any] = {}
    if preset is not None:
        preset_data = load_preset(resolve_preset_path(preset))

    effective_codec = (
        str(preset_data["codec"])
        if preset_data.get("codec") is not None and codec == "libx264"
        else codec
    )
    container_ext = get_codec_profile(effective_codec).container_ext
    resolved_output = (
        Path(output_video)
        if output_video is not None
        else _default_output_video_path(pattern_str, container_ext)
    )

    builder = (
        ConversionConfigBuilder()
        .with_input_pattern(pattern_str)
        .with_output_path(str(resolved_output))
    )
    if preset_data:
        _apply_preset_to_builder(builder, preset_data)

    builder.with_codec(effective_codec)

    effective_fps = fps
    if effective_fps is None and preset_data.get("fps") is not None:
        effective_fps = float(preset_data["fps"])
    elif effective_fps is None:
        hou = _get_hou()
        if hou is not None and hasattr(hou, "fps"):
            try:
                hou_fps = float(hou.fps())
                if hou_fps > 0:
                    effective_fps = hou_fps
            except (TypeError, ValueError):
                pass
    if effective_fps is not None:
        builder.with_fps(effective_fps)

    effective_ocio = ocio_config_path
    if effective_ocio is None:
        env_ocio = env_map.get("OCIO", "").strip()
        if env_ocio:
            effective_ocio = env_ocio
    if effective_ocio is not None:
        builder.with_ocio(config_path=effective_ocio)

    if contact_sheet:
        cs_config = preset_data.get("contact_sheet_config") or ContactSheetConfig()
        builder.with_contact_sheet(True, cs_config)

    config: ConversionConfig = builder.build()
    SequenceConverter(config).convert()
    return resolved_output


def build_houdini_ui_command(
    output_pattern: str | Path,
    *,
    layer: Optional[str] = None,
    preset: Optional[str | Path] = None,
    ocio_config_path: Optional[str] = None,
    python_executable: Optional[str] = None,
) -> list[str]:
    """Build a CLI command to launch the RenderKit UI for a Houdini output sequence.

    Args:
        output_pattern: Sequence pattern or frame path to open in the UI.
        layer: Optional EXR layer/AOV name to pre-select.
        preset: Optional preset name or path to pre-load.
        ocio_config_path: Optional OCIO config path to forward.
        python_executable: Optional Python interpreter path (defaults to ``sys.executable``).

    Returns:
        Command argument list suitable for :class:`subprocess.Popen`.
    """
    exe = python_executable or sys.executable
    cmd = [
        exe,
        "-m",
        "renderkit.cli.main",
        "ui",
        "--open",
        str(output_pattern),
    ]
    if layer:
        cmd.extend(["--layer", layer])
    if preset is not None:
        cmd.extend(["--preset", str(preset)])
    if ocio_config_path:
        cmd.extend(["--ocio", ocio_config_path])
    return cmd


def launch_renderkit_ui_for_houdini(
    output_pattern: str | Path,
    *,
    layer: Optional[str] = None,
    preset: Optional[str | Path] = None,
    ocio_config_path: Optional[str] = None,
    python_executable: Optional[str] = None,
) -> subprocess.Popen[Any]:
    """Spawn the RenderKit UI process for a Houdini output sequence.

    Args:
        output_pattern: Sequence pattern or frame path to open in the UI.
        layer: Optional EXR layer/AOV name to pre-select.
        preset: Optional preset name or path to pre-load.
        ocio_config_path: Optional OCIO config path to forward.
        python_executable: Optional Python interpreter path.

    Returns:
        Started :class:`subprocess.Popen` process handle.
    """
    cmd = build_houdini_ui_command(
        output_pattern,
        layer=layer,
        preset=preset,
        ocio_config_path=ocio_config_path,
        python_executable=python_executable,
    )
    return subprocess.Popen(cmd)
