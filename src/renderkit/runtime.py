"""Runtime bootstrap helpers for frozen builds."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("renderkit.runtime")


def _dedupe_path(entries: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in entries:
        if not entry:
            continue
        key = entry.lower() if os.name == "nt" else entry
        if key in seen:
            continue
        seen.add(key)
        ordered.append(entry)
    return ordered


def _add_dll_dirs(paths: Iterable[Path]) -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return
    for path in paths:
        if not path.is_dir():
            continue
        try:
            os.add_dll_directory(str(path))
        except OSError as exc:
            logger.debug("Failed to add DLL directory %s: %s", path, exc)


def bootstrap_runtime() -> None:
    """Prepare env and DLL paths so bundled OCIO/OIIO are used in frozen builds."""
    if not getattr(sys, "frozen", False):
        return

    internal_root = Path(getattr(sys, "_MEIPASS", "")).resolve()
    if not internal_root.exists():
        return

    for key in list(os.environ.keys()):
        upper_key = key.upper()
        if upper_key == "OCIO" or upper_key.startswith("OCIO_"):
            os.environ.pop(key, None)

    ocio_config = internal_root / "renderkit" / "data" / "ocio" / "config.ocio"
    if ocio_config.is_file():
        os.environ["OCIO"] = str(ocio_config)
        luts_dir = ocio_config.parent / "luts"
        if luts_dir.is_dir():
            os.environ["OCIO_SEARCH_PATH"] = str(luts_dir)

    dll_dirs = [
        internal_root / "OpenImageIO" / "bin",
        internal_root / "PyOpenColorIO" / "bin",
        internal_root / "ffmpeg",
    ]
    _add_dll_dirs(dll_dirs)

    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    new_entries = [str(internal_root)] + [str(path) for path in dll_dirs if path.is_dir()]
    os.environ["PATH"] = os.pathsep.join(_dedupe_path(new_entries + path_entries))
