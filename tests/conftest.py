"""Shared pytest fixtures for RenderKit tests."""

import pytest

from renderkit.ui.qt_compat import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for Qt widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()
