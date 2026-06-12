"""Shared pytest fixtures for RenderKit tests."""

import logging

import pytest

from renderkit.ui.qt_compat import QApplication


def _close_renderkit_logging_handlers() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers.copy():
        if getattr(handler, "renderkit_handler", None):
            root_logger.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def cleanup_renderkit_logging_handlers():
    """Keep RenderKit root handlers from leaking between tests."""
    _close_renderkit_logging_handlers()
    yield
    _close_renderkit_logging_handlers()


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for Qt widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()
