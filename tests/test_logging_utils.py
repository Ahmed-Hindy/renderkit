"""Tests for RenderKit logging helpers."""

from __future__ import annotations

import logging
from pathlib import Path

from renderkit.logging_utils import setup_logging


def _flush_renderkit_handlers() -> None:
    for handler in logging.getLogger().handlers:
        if getattr(handler, "renderkit_handler", None):
            handler.flush()


def test_env_debug_level_reaches_file_log(monkeypatch, tmp_path: Path) -> None:
    """RENDERKIT_LOG_LEVEL should control the file sink level."""
    log_path = tmp_path / "renderkit-debug.log"
    monkeypatch.setenv("RENDERKIT_LOG_PATH", str(log_path))
    monkeypatch.setenv("RENDERKIT_LOG_LEVEL", "DEBUG")

    setup_logging(enable_console=False)
    logging.getLogger("renderkit.test").debug("debug sentinel")
    logging.getLogger("renderkit.test").info("info sentinel")
    _flush_renderkit_handlers()

    log_text = log_path.read_text(encoding="utf-8")
    assert "debug sentinel" in log_text
    assert "info sentinel" in log_text


def test_explicit_debug_level_reaches_file_log(monkeypatch, tmp_path: Path) -> None:
    """The explicit setup_logging level should control the file sink."""
    log_path = tmp_path / "renderkit-explicit-debug.log"
    monkeypatch.setenv("RENDERKIT_LOG_PATH", str(log_path))
    monkeypatch.setenv("RENDERKIT_LOG_LEVEL", "INFO")

    setup_logging(enable_console=False, level=logging.DEBUG)
    logging.getLogger("renderkit.test").debug("explicit debug sentinel")
    _flush_renderkit_handlers()

    log_text = log_path.read_text(encoding="utf-8")
    assert "explicit debug sentinel" in log_text


def test_reconfigured_debug_level_updates_existing_file_handler(
    monkeypatch, tmp_path: Path
) -> None:
    """Repeated setup should update the existing file handler level."""
    log_path = tmp_path / "renderkit-reconfigured-debug.log"
    monkeypatch.setenv("RENDERKIT_LOG_PATH", str(log_path))

    setup_logging(enable_console=False, level=logging.INFO)
    logging.getLogger("renderkit.test").debug("hidden debug sentinel")
    setup_logging(enable_console=False, level=logging.DEBUG)
    logging.getLogger("renderkit.test").debug("updated debug sentinel")
    _flush_renderkit_handlers()

    log_text = log_path.read_text(encoding="utf-8")
    assert "hidden debug sentinel" not in log_text
    assert "updated debug sentinel" in log_text
