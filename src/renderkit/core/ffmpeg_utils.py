"""Helpers for locating bundled FFmpeg binaries."""

import builtins
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _find_repo_root(start: Path) -> Optional[Path]:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _get_vendor_ffmpeg_candidates(root: Path) -> list[Path]:
    vendor_root = root / "vendor" / "ffmpeg"
    platform_map = {
        "win32": "windows",
        "linux": "linux",
        "darwin": "macos",
    }
    platform_dir = platform_map.get(sys.platform)
    names = ["ffmpeg.exe"] if sys.platform == "win32" else ["ffmpeg"]
    candidates: list[Path] = []
    if platform_dir:
        platform_root = vendor_root / platform_dir
        candidates.extend(platform_root / name for name in names)
    return candidates


def ensure_ffmpeg_env() -> None:
    """Set IMAGEIO_FFMPEG_EXE if a bundled FFmpeg binary is available."""
    if os.environ.get("IMAGEIO_FFMPEG_EXE"):
        return

    candidates: list[Path] = []
    executable_dir = Path(sys.executable).resolve().parent
    compiled = getattr(builtins, "__compiled__", None)
    compiled_dir = Path(compiled.containing_dir) if compiled is not None else None

    for base in (compiled_dir, executable_dir):
        if base is None:
            continue
        if sys.platform == "win32":
            candidates.append(base / "ffmpeg" / "ffmpeg.exe")
            candidates.append(base / "ffmpeg.exe")
        else:
            candidates.append(base / "ffmpeg" / "ffmpeg")
            candidates.append(base / "ffmpeg")

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        if sys.platform == "win32":
            candidates.append(base / "ffmpeg" / "ffmpeg.exe")
            candidates.append(base / "ffmpeg.exe")
        else:
            candidates.append(base / "ffmpeg" / "ffmpeg")
            candidates.append(base / "ffmpeg")

    package_root = Path(__file__).resolve().parents[1]
    candidates.extend(_get_vendor_ffmpeg_candidates(package_root))

    repo_root = _find_repo_root(Path(__file__).resolve().parent)
    if repo_root:
        candidates.extend(_get_vendor_ffmpeg_candidates(repo_root))

    for candidate in candidates:
        if candidate.is_file():
            os.environ["IMAGEIO_FFMPEG_EXE"] = str(candidate)
            logger.info("Using bundled ffmpeg: %s", candidate)
            return

    logger.debug("No bundled ffmpeg found; falling back to system ffmpeg.")


def get_ffmpeg_exe() -> str:
    """Return the best FFmpeg executable path for the current environment."""
    env_exe = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env_exe:
        return env_exe

    ensure_ffmpeg_env()
    env_exe = os.environ.get("IMAGEIO_FFMPEG_EXE")
    if env_exe:
        return env_exe

    path_exe = shutil.which("ffmpeg")
    if path_exe:
        return path_exe

    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def get_ffprobe_exe() -> str:
    """Return the best FFprobe executable path for the current environment."""
    ffmpeg_exe = Path(get_ffmpeg_exe())
    name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
    if ffmpeg_exe.parent:
        sibling = ffmpeg_exe.with_name(name)
        if sibling.is_file():
            return str(sibling)

    path_exe = shutil.which(name)
    if path_exe:
        return path_exe

    return name


def popen_kwargs(prevent_sigint: bool = True) -> dict[str, Any]:
    """Return subprocess kwargs tuned for FFmpeg execution."""
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW
        if prevent_sigint:
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = creationflags
    elif prevent_sigint:
        kwargs["start_new_session"] = True
    return kwargs
