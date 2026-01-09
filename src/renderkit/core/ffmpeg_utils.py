"""Helpers for locating bundled FFmpeg binaries."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

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
    candidates = []
    if platform_dir:
        platform_root = vendor_root / platform_dir
        candidates.extend(platform_root / name for name in names)
    return candidates


def ensure_ffmpeg_env() -> None:
    """Set IMAGEIO_FFMPEG_EXE if a bundled FFmpeg binary is available."""
    if os.environ.get("IMAGEIO_FFMPEG_EXE"):
        return

    candidates = []
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

    logger.debug("No bundled ffmpeg found; using imageio-ffmpeg default.")
