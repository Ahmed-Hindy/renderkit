"""Nuke Write/Read node dailies conversion and UI launcher integrations."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

from renderkit.core.config import ConversionConfig, ConversionConfigBuilder
from renderkit.core.converter import SequenceConverter
from renderkit.core.presets import load_preset, resolve_preset_path
from renderkit.exceptions import ConfigurationError
from renderkit.integrations.houdini import (
    _apply_preset_to_builder,
    _coerce_int,
    _default_output_video_path,
)
from renderkit.processing.video_encoder import get_codec_profile


def _get_nuke() -> Any:
    """Import Foundry Nuke's ``nuke`` module optionally."""
    try:
        return importlib.import_module("nuke")
    except ImportError:
        return None


def _get_knob(node: Any, knob_name: str) -> Any:
    if node is None:
        return None
    knob_fn = getattr(node, "knob", None)
    if callable(knob_fn):
        knob = knob_fn(knob_name)
        if knob is not None:
            return knob
    try:
        return node[knob_name]
    except (KeyError, IndexError, TypeError):
        return None


def _read_knob_value(node: Any, knob_name: str, *, prefer_evaluate: bool = False) -> Any:
    knob = _get_knob(node, knob_name)
    if knob is None:
        return None
    if prefer_evaluate:
        evaluate_fn = getattr(knob, "evaluate", None)
        if callable(evaluate_fn):
            evaluated = evaluate_fn()
            if evaluated is not None and str(evaluated).strip():
                return evaluated
    value_fn = getattr(knob, "value", None)
    if callable(value_fn):
        return value_fn()
    return None


def extract_nuke_node_context(
    node: Any,
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Extract sequence path, frame range, and color metadata from a Nuke node.

    Args:
        node: Nuke Write or Read node object.
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Dictionary containing ``output_pattern``, ``first_frame``, ``last_frame``,
        ``colorspace``, and ``ocio_config_path``.
    """
    if node is None:
        raise ConfigurationError("A Nuke node is required to extract context.")

    _get_nuke()
    env_map = os.environ if env is None else env

    raw_file = _read_knob_value(node, "file", prefer_evaluate=True)
    output_pattern = (
        str(raw_file).strip() if raw_file is not None and str(raw_file).strip() else None
    )

    first_frame = _coerce_int(_read_knob_value(node, "first"))
    if first_frame is None and callable(getattr(node, "firstFrame", None)):
        first_frame = _coerce_int(node.firstFrame())

    last_frame = _coerce_int(_read_knob_value(node, "last"))
    if last_frame is None and callable(getattr(node, "lastFrame", None)):
        last_frame = _coerce_int(node.lastFrame())

    raw_colorspace = _read_knob_value(node, "colorspace", prefer_evaluate=True)
    colorspace = (
        str(raw_colorspace).strip()
        if raw_colorspace is not None and str(raw_colorspace).strip()
        else None
    )

    ocio_raw = env_map.get("OCIO", "")
    ocio_config_path = ocio_raw.strip() or None

    return {
        "output_pattern": output_pattern,
        "first_frame": first_frame,
        "last_frame": last_frame,
        "colorspace": colorspace,
        "ocio_config_path": ocio_config_path,
    }


def convert_nuke_node_to_dailies(
    node: Any,
    *,
    output_video: Optional[str | Path] = None,
    preset: Optional[str | Path] = None,
    fps: float = 24.0,
    codec: str = "prores_422",
    ocio_config_path: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Path:
    """Convert a Nuke Write or Read node's sequence to a dailies movie.

    Args:
        node: Nuke node with a ``file`` knob.
        output_video: Optional destination movie path.
        preset: Optional preset name or JSON preset path.
        fps: Frame rate for dailies encoding (default: ``24.0``).
        codec: Target codec (default: ``'prores_422'`` unless overridden by preset).
        ocio_config_path: Optional OCIO config path (falls back to ``$OCIO``).
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Path to the generated dailies video file.
    """
    ctx = extract_nuke_node_context(node, env=env)
    output_pattern = ctx["output_pattern"]
    if not output_pattern:
        raise ConfigurationError("Nuke node does not have a valid 'file' knob value.")

    preset_data: dict[str, Any] = {}
    if preset is not None:
        preset_data = load_preset(resolve_preset_path(preset))

    effective_codec = (
        str(preset_data["codec"])
        if preset_data.get("codec") is not None and codec == "prores_422"
        else codec
    )
    container_ext = get_codec_profile(effective_codec).container_ext
    resolved_output = (
        Path(output_video)
        if output_video is not None
        else _default_output_video_path(output_pattern, container_ext)
    )

    builder = (
        ConversionConfigBuilder()
        .with_input_pattern(output_pattern)
        .with_output_path(str(resolved_output))
    )
    if preset_data:
        _apply_preset_to_builder(builder, preset_data)

    builder.with_codec(effective_codec)
    effective_fps = (
        float(preset_data["fps"]) if preset_data.get("fps") is not None and fps == 24.0 else fps
    )
    builder.with_fps(effective_fps)

    if ctx["first_frame"] is not None or ctx["last_frame"] is not None:
        builder.with_frame_range(ctx["first_frame"], ctx["last_frame"])

    effective_ocio = ocio_config_path if ocio_config_path is not None else ctx["ocio_config_path"]
    node_colorspace = ctx["colorspace"]
    if effective_ocio is not None:
        builder.with_ocio(config_path=effective_ocio, input_space=node_colorspace)
    elif node_colorspace and node_colorspace.lower() != "default":
        builder.with_explicit_input_color_space(node_colorspace)

    config: ConversionConfig = builder.build()
    SequenceConverter(config).convert()
    return resolved_output


def build_nuke_ui_command(
    node: Any,
    *,
    preset: Optional[str | Path] = None,
    python_executable: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> list[str]:
    """Build a CLI command to launch the RenderKit UI for a Nuke node's sequence.

    Args:
        node: Nuke node with a ``file`` knob.
        preset: Optional preset name or path to pre-load.
        python_executable: Optional Python interpreter path.
        env: Optional environment mapping (defaults to ``os.environ``).

    Returns:
        Command argument list suitable for launching the UI subprocess.
    """
    ctx = extract_nuke_node_context(node, env=env)
    output_pattern = ctx["output_pattern"]
    if not output_pattern:
        raise ConfigurationError("Nuke node does not have a valid 'file' knob value.")

    exe = python_executable or sys.executable
    cmd = [
        exe,
        "-m",
        "renderkit.cli.main",
        "ui",
        "--open",
        str(output_pattern),
    ]
    if preset is not None:
        cmd.extend(["--preset", str(preset)])
    if ctx["ocio_config_path"]:
        cmd.extend(["--ocio", ctx["ocio_config_path"]])
    return cmd
