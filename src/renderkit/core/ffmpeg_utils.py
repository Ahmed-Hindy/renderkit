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


def ensure_ffmpeg_env() -> None:
    """Set IMAGEIO_FFMPEG_EXE if a bundled FFmpeg binary is available."""
    if os.environ.get("IMAGEIO_FFMPEG_EXE"):
        return

    candidates = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
        candidates.append(base / "ffmpeg" / "ffmpeg.exe")
        candidates.append(base / "ffmpeg.exe")

    package_root = Path(__file__).resolve().parents[1]
    candidates.append(package_root / "vendor" / "ffmpeg" / "ffmpeg.exe")

    repo_root = _find_repo_root(Path(__file__).resolve().parent)
    if repo_root:
        candidates.append(repo_root / "vendor" / "ffmpeg" / "ffmpeg.exe")

    for candidate in candidates:
        if candidate.is_file():
            os.environ["IMAGEIO_FFMPEG_EXE"] = str(candidate)
            logger.info("Using bundled ffmpeg: %s", candidate)
            return

    logger.debug("No bundled ffmpeg found; using imageio-ffmpeg default.")
