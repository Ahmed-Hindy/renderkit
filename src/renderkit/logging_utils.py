"""Logging helpers for RenderKit."""

from __future__ import annotations

import logging
import os
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

_LOGGER_NAME = "renderkit"


class CallbackHandler(logging.Handler):
    """Forward log messages to a callable sink."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        try:
            self._callback(msg)
        except Exception:
            self.handleError(record)


def _has_handler(logger: logging.Logger, handler_key: str) -> bool:
    return any(
        getattr(handler, "renderkit_handler", None) == handler_key for handler in logger.handlers
    )


def _log_level() -> int:
    level_name = os.environ.get("RENDERKIT_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _log_path() -> Path:
    configured = os.environ.get("RENDERKIT_LOG_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "renderkit.log"


def setup_logging(
    ui_sink: Callable[[str], None] | None = None,
    enable_console: bool | None = None,
) -> Path:
    """Configure RenderKit logging with optional UI forwarding.

    Returns:
        Path to the log file.
    """
    # 1. Configure RenderKit logger specifically
    # We want to see INFO+ from our own app by default
    rk_logger = logging.getLogger(_LOGGER_NAME)
    rk_logger.setLevel(_log_level())
    rk_logger.propagate = True  # Ensure logs bubble up to root

    # 2. Configure Root logger
    # We generally only want WARNING+ from third-party libs to avoid spam
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)

    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    added_file = False
    # Check handlers on ROOT logger now
    if not _has_handler(root_logger, "file"):
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.renderkit_handler = "file"
        # File handler should capture everything (INFO from app, WARNING from libs)
        # We set it to INFO so it *can* receive INFO logs that bubble up
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        root_logger.addHandler(file_handler)
        added_file = True

    if enable_console is None:
        enable_console = ui_sink is None
    if enable_console and not _has_handler(root_logger, "console"):
        console_handler = logging.StreamHandler()
        console_handler.renderkit_handler = "console"
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        root_logger.addHandler(console_handler)

    if ui_sink is not None and not _has_handler(root_logger, "ui"):
        ui_handler = CallbackHandler(ui_sink)
        ui_handler.renderkit_handler = "ui"
        ui_handler.setLevel(logging.INFO)
        ui_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root_logger.addHandler(ui_handler)

    if added_file:
        rk_logger.info("Logging to %s", log_path)
    return log_path
