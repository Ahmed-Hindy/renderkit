"""Stage a portable FFmpeg binary for packaging workflows."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

PLATFORM_DIRS = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "macos",
}
REQUIRED_ENCODERS = ("libx264", "libx265", "libaom-av1")
FFMPEG_VERIFY_TIMEOUT_SECONDS = 30


def _target_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _make_executable(path: Path) -> None:
    if sys.platform == "win32":
        return

    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _verify_ffmpeg(path: Path) -> None:
    version_result = subprocess.run(
        [str(path), "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFMPEG_VERIFY_TIMEOUT_SECONDS,
    )
    first_line = (
        version_result.stdout.splitlines()[0] if version_result.stdout else "ffmpeg version unknown"
    )
    print(first_line)

    encoders_result = subprocess.run(
        [str(path), "-hide_banner", "-encoders"],
        check=True,
        capture_output=True,
        text=True,
        timeout=FFMPEG_VERIFY_TIMEOUT_SECONDS,
    )
    encoders = encoders_result.stdout
    missing = [encoder for encoder in REQUIRED_ENCODERS if encoder not in encoders]
    if missing:
        raise RuntimeError(f"FFmpeg is missing required encoders: {', '.join(missing)}")


def main() -> int:
    platform_dir = PLATFORM_DIRS.get(sys.platform)
    if platform_dir is None:
        raise RuntimeError(f"Unsupported platform for FFmpeg staging: {sys.platform}")

    repo_root = Path(__file__).resolve().parent.parent
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not source.is_file():
        raise RuntimeError(f"imageio-ffmpeg did not provide a usable binary: {source}")

    target_dir = repo_root / "vendor" / "ffmpeg" / platform_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _target_name()

    if target.exists():
        target.unlink()

    shutil.copy2(source, target)
    _make_executable(target)

    os.environ["IMAGEIO_FFMPEG_EXE"] = str(target)
    _verify_ffmpeg(target)
    print(f"Staged portable FFmpeg: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
