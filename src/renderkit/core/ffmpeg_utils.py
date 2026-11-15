"""Helpers for locating bundled FFmpeg binaries."""

import builtins
import logging
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

_FFMPEG_ENV_VAR = "IMAGEIO_FFMPEG_EXE"
_AUTO_BUNDLED_FFMPEG: Optional[str] = None
_VIDEO_CONTAINER_DEMUXERS = frozenset({"mov", "mp4", "matroska", "avi"})

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


def _iter_bundled_ffmpeg_candidates() -> list[Path]:
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

    return candidates


def ensure_ffmpeg_env() -> None:
    """Set IMAGEIO_FFMPEG_EXE if a bundled FFmpeg binary is available."""
    global _AUTO_BUNDLED_FFMPEG
    existing = os.environ.get(_FFMPEG_ENV_VAR)
    if existing:
        existing_norm = _normalize_exe_path(existing)
        if any(
            _normalize_exe_path(str(c)) == existing_norm for c in _iter_bundled_ffmpeg_candidates()
        ):
            _AUTO_BUNDLED_FFMPEG = existing
        return

    for candidate in _iter_bundled_ffmpeg_candidates():
        if candidate.is_file():
            resolved = str(candidate)
            os.environ[_FFMPEG_ENV_VAR] = resolved
            _AUTO_BUNDLED_FFMPEG = resolved
            logger.info("Using bundled ffmpeg: %s", candidate)
            return

    logger.debug("No bundled ffmpeg found; falling back to system ffmpeg.")


def _normalize_exe_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def is_auto_bundled_ffmpeg(ffmpeg_exe: str) -> bool:
    """Return True if ``ffmpeg_exe`` points to an auto-configured or bundled minimal binary."""
    if not ffmpeg_exe:
        return False
    exe_norm = _normalize_exe_path(ffmpeg_exe)
    if _AUTO_BUNDLED_FFMPEG and exe_norm == _normalize_exe_path(_AUTO_BUNDLED_FFMPEG):
        return True
    return any(_normalize_exe_path(str(c)) == exe_norm for c in _iter_bundled_ffmpeg_candidates())


def find_system_ffmpeg_executables() -> list[str]:
    """Return ordered FFmpeg executable paths from ``PATH``, excluding the bundled binary."""
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    auto_norm = _normalize_exe_path(_AUTO_BUNDLED_FFMPEG) if _AUTO_BUNDLED_FFMPEG else None
    seen: set[str] = set()
    results: list[str] = []

    def _add_if_valid(candidate_path: str) -> None:
        if not candidate_path:
            return
        norm = _normalize_exe_path(candidate_path)
        if norm == auto_norm or norm in seen:
            return
        if Path(candidate_path).is_file():
            seen.add(norm)
            results.append(candidate_path)

    for entry in os.environ.get("PATH", "").split(os.pathsep):
        cleaned = entry.strip().strip('"')
        if not cleaned:
            continue
        _add_if_valid(str(Path(cleaned) / name))

    which_exe = shutil.which("ffmpeg")
    if which_exe:
        _add_if_valid(which_exe)

    return results


def _run_ffmpeg_query(ffmpeg_exe: str, flag: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [ffmpeg_exe, "-hide_banner", flag],
            capture_output=True,
            text=True,
            **popen_kwargs(prevent_sigint=True),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "") + "\n" + (result.stderr or "")


def parse_ffmpeg_encoders(text: str) -> frozenset[str]:
    """Parse video encoder names from ``ffmpeg -encoders`` output."""
    encoders: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Encoders:") or line.startswith("-"):
            continue
        if not line[0].isalpha() or len(line) < 2:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] == "=":
            continue
        if parts[0].startswith("V"):
            encoders.add(parts[1])
    return frozenset(encoders)


@lru_cache(maxsize=16)
def _probe_ffmpeg_encoders(ffmpeg_exe: str) -> Optional[frozenset[str]]:
    text = _run_ffmpeg_query(ffmpeg_exe, "-encoders")
    if text is None:
        return None
    return parse_ffmpeg_encoders(text)


@lru_cache(maxsize=16)
def _probe_ffmpeg_filters(ffmpeg_exe: str) -> Optional[frozenset[str]]:
    text = _run_ffmpeg_query(ffmpeg_exe, "-filters")
    if text is None:
        return None
    filters: set[str] = set()
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 3 or parts[1] == "=":
            continue
        flags = parts[0]
        if flags and set(flags) <= {".", "T", "S", "C"}:
            filters.add(parts[1])
    return frozenset(filters)


@lru_cache(maxsize=16)
def _probe_ffmpeg_demuxers(ffmpeg_exe: str) -> Optional[frozenset[str]]:
    text = _run_ffmpeg_query(ffmpeg_exe, "-demuxers")
    if text is None:
        return None
    demuxers: set[str] = set()
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 2 or parts[1] == "=":
            continue
        if "D" in parts[0] and set(parts[0]) <= {"D", "."}:
            for name in parts[1].split(","):
                if name:
                    demuxers.add(name)
    return frozenset(demuxers)


def ffmpeg_supports_encoder(ffmpeg_exe: str, encoder: str) -> Optional[bool]:
    """Return whether ``ffmpeg_exe`` advertises video ``encoder`` (None if probe failed)."""
    encoders = _probe_ffmpeg_encoders(ffmpeg_exe)
    return None if encoders is None else (encoder in encoders)


def ffmpeg_supports_filter(ffmpeg_exe: str, filter_name: str) -> Optional[bool]:
    """Return whether ``ffmpeg_exe`` advertises filter ``filter_name`` (None if probe failed)."""
    filters = _probe_ffmpeg_filters(ffmpeg_exe)
    return None if filters is None else (filter_name in filters)


def ffmpeg_supports_video_decode(ffmpeg_exe: str) -> Optional[bool]:
    """Return whether ``ffmpeg_exe`` can demux common container formats (None if probe failed)."""
    demuxers = _probe_ffmpeg_demuxers(ffmpeg_exe)
    return None if demuxers is None else bool(demuxers & _VIDEO_CONTAINER_DEMUXERS)


def resolve_ffmpeg_for_encoder(default_exe: str, ffmpeg_codec: str) -> str:
    """Resolve an FFmpeg binary supporting ``ffmpeg_codec`` when bundled FFmpeg lacks it."""
    if not is_auto_bundled_ffmpeg(default_exe):
        return default_exe
    if ffmpeg_supports_encoder(default_exe, ffmpeg_codec) is not False:
        return default_exe
    for candidate in find_system_ffmpeg_executables():
        if ffmpeg_supports_encoder(candidate, ffmpeg_codec) is True:
            logger.info("Using system ffmpeg for encoder '%s': %s", ffmpeg_codec, candidate)
            return candidate
    return default_exe


def resolve_ffmpeg_for_decoding(default_exe: str) -> str:
    """Resolve an FFmpeg binary supporting video demuxing when bundled FFmpeg lacks it."""
    if not is_auto_bundled_ffmpeg(default_exe):
        return default_exe
    if ffmpeg_supports_video_decode(default_exe) is not False:
        return default_exe
    for candidate in find_system_ffmpeg_executables():
        if ffmpeg_supports_video_decode(candidate) is True:
            logger.info("Using system ffmpeg for video decoding: %s", candidate)
            return candidate
    return default_exe


def get_ffmpeg_exe() -> str:
    """Return the best FFmpeg executable path for the current environment."""
    env_exe = os.environ.get(_FFMPEG_ENV_VAR)
    if env_exe:
        return env_exe

    ensure_ffmpeg_env()
    env_exe = os.environ.get(_FFMPEG_ENV_VAR)
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
