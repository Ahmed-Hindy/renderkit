"""Guards for bundled OCIO asset integrity."""

import re
from pathlib import Path

import pytest


OCIO_ROOT = Path("src/renderkit/data/ocio")
CONFIG_PATH = OCIO_ROOT / "config.ocio"


def _asset_files() -> list[Path]:
    files: list[Path] = [CONFIG_PATH]
    files.extend(sorted((OCIO_ROOT / "luts").glob("*.spi1d")))
    files.extend(sorted((OCIO_ROOT / "luts").glob("*.spi3d")))
    return files


def test_ocio_assets_use_lf_line_endings() -> None:
    """Ensure OCIO text assets stay LF-only for stable packaged behavior."""
    for path in _asset_files():
        data = path.read_bytes()
        assert b"\r\n" not in data, f"CRLF detected in {path}"


def test_ocio_config_file_transforms_exist() -> None:
    """Ensure all FileTransform sources referenced by config are present."""
    config_text = CONFIG_PATH.read_text(encoding="utf-8")
    srcs = re.findall(r"src:\s*([^\s,}]+)", config_text)
    assert srcs, "No FileTransform src entries found in config.ocio"

    for src in srcs:
        lut_path = OCIO_ROOT / "luts" / src
        assert lut_path.exists(), f"Missing LUT referenced by config.ocio: {src}"


def test_ocio_primary_processor_creation() -> None:
    """Smoke-test primary OCIO processor when PyOpenColorIO is available."""
    OCIO = pytest.importorskip("PyOpenColorIO")
    config = OCIO.Config.CreateFromFile(str(CONFIG_PATH.resolve()))
    config.validate()
    config.getProcessor("ACES - ACEScg", "Output - sRGB")
