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
    level: int | None = None,
) -> Path:
    """Configure RenderKit logging with optional UI forwarding.

    Args:
        ui_sink: Optional callback for UI logging.
        enable_console: Whether to enable console logging.
        level: Logging level (defaults to RENDERKIT_LOG_LEVEL env var or INFO).

    Returns:
        Path to the log file.
    """
    log_level = level if level is not None else _log_level()

    # 1. Configure RenderKit logger
    rk_logger = logging.getLogger(_LOGGER_NAME)
    rk_logger.setLevel(log_level)
    rk_logger.propagate = True

    # 2. Configure Root logger for third-party libraries
    root_logger = logging.getLogger()
    # We keep root at WARNING to avoid third-party noise,
    # but our file handler can still capture our INFO logs because they propagate.
    if root_logger.level > logging.WARNING or root_logger.level == logging.NOTSET:
        root_logger.setLevel(logging.WARNING)

    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Formatter definitions
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")
    ui_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )

    # 3. Manage File Handler
    if not _has_handler(root_logger, "file"):
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.renderkit_handler = "file"
        file_handler.setLevel(logging.INFO)  # File captures INFO+
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        rk_logger.info("Logging to %s", log_path)

    # 4. Manage Console Handler
    if enable_console is None:
        # Default: enable console if no UI sink and not already added
        enable_console = ui_sink is None

    if enable_console:
        if not _has_handler(root_logger, "console"):
            console_handler = logging.StreamHandler()
            console_handler.renderkit_handler = "console"
            console_handler.setLevel(log_level)
            console_handler.setFormatter(console_formatter)
            root_logger.addHandler(console_handler)
    else:
        # Explicitly disabled - remove if exists
        for h in list(root_logger.handlers):
            if getattr(h, "renderkit_handler", None) == "console":
                root_logger.removeHandler(h)

    # 5. Manage UI Handler
    if ui_sink is not None:
        # Remove old UI handler if it exists to allow updating callback
        for h in list(root_logger.handlers):
            if getattr(h, "renderkit_handler", None) == "ui":
                root_logger.removeHandler(h)

        ui_handler = CallbackHandler(ui_sink)
        ui_handler.renderkit_handler = "ui"
        ui_handler.setLevel(log_level)
        ui_handler.setFormatter(ui_formatter)
        root_logger.addHandler(ui_handler)
    elif ui_sink is None:
        # Explicitly removed
        for h in list(root_logger.handlers):
            if getattr(h, "renderkit_handler", None) == "ui":
                root_logger.removeHandler(h)

    return log_path
