"""Helpers for running cProfile and persisting results."""

from __future__ import annotations

import cProfile
import io
import logging
import os
import pstats
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_profile_env_config() -> tuple[bool, Optional[Path]]:
    """Return profiling enable flag and optional output path from env."""
    enabled = _truthy_env("RENDERKIT_PROFILE")
    output = os.environ.get("RENDERKIT_PROFILE_OUT", "").strip()
    return enabled, Path(output) if output else None


def _default_profile_name(label: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"renderkit-{label}-{stamp}.prof"


def _resolve_profile_path(output: Optional[Path], label: str) -> Path:
    if output is None:
        return Path(tempfile.gettempdir()) / _default_profile_name(label)

    output = output.expanduser()
    if output.suffix:
        return output

    if output.exists() and output.is_dir():
        return output / _default_profile_name(label)

    return output / _default_profile_name(label)


def _summary_path(profile_path: Path) -> Path:
    suffix = profile_path.suffix
    if suffix:
        return profile_path.with_suffix(f"{suffix}.txt")
    return profile_path.with_suffix(".txt")


def _write_summary(profile: cProfile.Profile, profile_path: Path) -> None:
    try:
        stream = io.StringIO()
        stats = pstats.Stats(profile, stream=stream)
        stats.strip_dirs().sort_stats("cumulative").print_stats(50)
        _summary_path(profile_path).write_text(stream.getvalue(), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write profiler summary: %s", exc)


@contextmanager
def profile_context(
    enabled: bool,
    output_path: Optional[Path],
    label: str,
) -> cProfile.Profile | None:
    """Context manager to run cProfile and persist results to disk."""
    if not enabled:
        yield None
        return

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        yield profiler
    finally:
        profiler.disable()
        profile_path = _resolve_profile_path(output_path, label)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(profile_path))
        _write_summary(profiler, profile_path)
        logger.info("Profiler output written to %s", profile_path)
        print(f"Profiler output written to {profile_path}")
