"""Houdini 21.0 ROP / Solaris Husk / TOPs post-render dailies wrapper script."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Optional

from renderkit.integrations.houdini import (
    extract_houdini_rop_context,
    run_houdini_post_render,
)

logger = logging.getLogger(__name__)


def _get_hou() -> Any:
    """Import Houdini's ``hou`` module optionally when running inside Houdini."""
    try:
        return importlib.import_module("hou")
    except ImportError:
        return None


def main(
    node: Any = None,
    *,
    preset: Optional[str | Path] = None,
    contact_sheet: bool = False,
) -> Optional[Path]:
    """Generate a RenderKit review movie from a Houdini ROP/LOP/TOP node after rendering.

    Suitable for Houdini 21.0 ROP Post-Render Scripts, Solaris Husk USD Render ROPs,
    and TOPs/PDG post-render callbacks. Falls back gracefully when run outside ``hou``.

    Args:
        node: Optional Houdini node instance. Defaults to ``hou.pwd()`` inside Houdini.
        preset: Optional RenderKit preset name (resolved via ``RENDERKIT_PRESET_PATH``)
            or path to a JSON preset file.
        contact_sheet: Whether to enable multi-AOV contact sheet mode.

    Returns:
        Path to the generated video file, or ``None`` if no output sequence pattern
        could be resolved from the node.
    """
    hou = _get_hou()
    target_node = node
    if target_node is None and hou is not None and hasattr(hou, "pwd"):
        target_node = hou.pwd()

    context = extract_houdini_rop_context(target_node)
    output_pattern = context.get("output_pattern")
    if not output_pattern:
        logger.warning(
            "RenderKit post-render skipped: could not resolve an output sequence pattern."
        )
        return None

    return run_houdini_post_render(
        output_pattern,
        preset=preset,
        fps=context.get("fps") if hou is not None and preset is None else None,
        ocio_config_path=context.get("ocio_config_path"),
        contact_sheet=contact_sheet,
    )


if __name__ == "__main__":
    main()
