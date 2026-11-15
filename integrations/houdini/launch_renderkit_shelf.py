"""Houdini 21.0 shelf button entrypoint for launching the RenderKit UI."""

from __future__ import annotations

import importlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from renderkit.integrations.houdini import (
    extract_houdini_rop_context,
    launch_renderkit_ui_for_houdini,
)

logger = logging.getLogger(__name__)


def _get_hou() -> Any:
    """Import Houdini's ``hou`` module optionally when running inside Houdini."""
    try:
        return importlib.import_module("hou")
    except ImportError:
        return None


def _resolve_target_node(node: Any = None) -> Any:
    """Return ``node`` if given, otherwise the first selected Houdini node or ``hou.pwd()``."""
    if node is not None:
        return node

    hou = _get_hou()
    if hou is None:
        return None

    selected_fn = getattr(hou, "selectedNodes", None)
    if callable(selected_fn):
        selected = selected_fn()
        if selected:
            return selected[0]

    pwd_fn = getattr(hou, "pwd", None)
    if callable(pwd_fn):
        return pwd_fn()

    return None


def launch_selected_node_in_renderkit(
    node: Any = None,
    *,
    preset: Optional[str | Path] = None,
    layer: Optional[str] = None,
) -> Optional[subprocess.Popen[Any]]:
    """Launch the RenderKit UI pre-populated with a Houdini node's render sequence.

    Args:
        node: Optional Houdini node. When ``None``, inspects ``hou.selectedNodes()``
            and falls back to ``hou.pwd()``.
        preset: Optional RenderKit preset name or JSON preset path.
        layer: Optional EXR layer/AOV name to pre-select in the UI.

    Returns:
        Started :class:`subprocess.Popen` handle, or ``None`` if no output sequence
        pattern could be resolved from the node.
    """
    target_node = _resolve_target_node(node)
    context = extract_houdini_rop_context(target_node)
    output_pattern = context.get("output_pattern")
    if not output_pattern:
        logger.warning(
            "RenderKit shelf launcher skipped: selected node has no output sequence parameter."
        )
        return None

    return launch_renderkit_ui_for_houdini(
        output_pattern,
        layer=layer,
        preset=preset,
        ocio_config_path=context.get("ocio_config_path"),
    )


if __name__ == "__main__":
    launch_selected_node_in_renderkit()
