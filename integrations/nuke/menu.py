"""Foundry Nuke ``menu.py`` integration helper for RenderKit dailies and UI."""

from __future__ import annotations

import importlib
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from renderkit.integrations.nuke import (
    build_nuke_ui_command,
    convert_nuke_node_to_dailies,
)

logger = logging.getLogger(__name__)


def _get_nuke() -> Any:
    """Import Foundry Nuke's ``nuke`` module optionally."""
    try:
        return importlib.import_module("nuke")
    except ImportError:
        return None


def _get_selected_node(node: Any = None) -> Any:
    """Return ``node`` if provided, or the active selected node in Nuke."""
    if node is not None:
        return node

    nuke = _get_nuke()
    if nuke is None:
        return None

    selected_fn = getattr(nuke, "selectedNode", None)
    if callable(selected_fn):
        try:
            return selected_fn()
        except ValueError:
            pass

    selected_nodes_fn = getattr(nuke, "selectedNodes", None)
    if callable(selected_nodes_fn):
        nodes = selected_nodes_fn()
        if nodes:
            return nodes[0]

    return None


def generate_dailies_for_selected_node(
    node: Any = None,
    *,
    preset: Optional[str | Path] = None,
    codec: str = "prores_422",
) -> Optional[Path]:
    """Convert the selected Nuke Write/Read node's sequence to a dailies movie.

    Args:
        node: Optional Nuke node. Defaults to the currently selected node in Nuke.
        preset: Optional RenderKit preset name or JSON preset path.
        codec: Target video codec (defaults to ``'prores_422'`` unless overridden by preset).

    Returns:
        Path to the generated dailies movie, or ``None`` if no node is selected.
    """
    target_node = _get_selected_node(node)
    if target_node is None:
        logger.warning("RenderKit: no Nuke node selected for dailies generation.")
        return None

    return convert_nuke_node_to_dailies(target_node, preset=preset, codec=codec)


def open_selected_node_in_renderkit_ui(
    node: Any = None,
    *,
    preset: Optional[str | Path] = None,
) -> Optional[subprocess.Popen[Any]]:
    """Launch the RenderKit desktop UI for the selected Nuke Write/Read node.

    Args:
        node: Optional Nuke node. Defaults to the currently selected node in Nuke.
        preset: Optional RenderKit preset name or JSON preset path.

    Returns:
        Started :class:`subprocess.Popen` handle, or ``None`` if no node is selected.
    """
    target_node = _get_selected_node(node)
    if target_node is None:
        logger.warning("RenderKit: no Nuke node selected to open in RenderKit UI.")
        return None

    cmd = build_nuke_ui_command(target_node, preset=preset)
    return subprocess.Popen(cmd)


def create_dailies_menu(menu: Any = None) -> Any:
    """Register RenderKit dailies actions on a Nuke menu.

    Args:
        menu: Optional Nuke menu object. When ``None``, resolves ``nuke.menu("Nuke")``
            and creates/retrieves a ``"RenderKit"`` submenu.

    Returns:
        The menu object that received the commands, or ``None`` when running outside Nuke.
    """
    target_menu = menu
    if target_menu is None:
        nuke = _get_nuke()
        if nuke is None:
            return None
        menubar = nuke.menu("Nuke")
        if menubar is None:
            return None
        target_menu = menubar.addMenu("RenderKit") if hasattr(menubar, "addMenu") else menubar
    elif not hasattr(target_menu, "addCommand") and hasattr(target_menu, "addMenu"):
        target_menu = target_menu.addMenu("RenderKit")

    target_menu.addCommand(
        "Generate Dailies (RenderKit)",
        generate_dailies_for_selected_node,
    )
    target_menu.addCommand(
        "Open in RenderKit UI",
        open_selected_node_in_renderkit_ui,
    )
    return target_menu


if _get_nuke() is not None:
    create_dailies_menu()
