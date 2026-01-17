"""Tests for the UI toggles in ModernMainWindow."""

import pytest

from renderkit.ui.qt_compat import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()


def test_burnin_toggle(qtbot, qapp):
    """Test that burn-in toggle correctly enables/disables child widgets."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Initially disabled (as per settings/default)
    window.burnin_enable_check.setChecked(False)
    assert window.burnin_frame_check.isEnabled() is False
    assert window.burnin_layer_check.isEnabled() is False
    assert window.burnin_fps_check.isEnabled() is False
    assert window.burnin_opacity_spin.isEnabled() is False

    # Enable
    window.burnin_enable_check.setChecked(True)
    assert window.burnin_frame_check.isEnabled() is True
    assert window.burnin_layer_check.isEnabled() is True
    assert window.burnin_fps_check.isEnabled() is True
    assert window.burnin_opacity_spin.isEnabled() is True

    # Disable again
    window.burnin_enable_check.setChecked(False)
    assert window.burnin_frame_check.isEnabled() is False


def test_contact_sheet_toggle_sync(qtbot, qapp):
    """Test that contact sheet toggle correctly enables/disables related settings."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Initially disabled
    window.cs_enable_check.setChecked(False)
    assert window.cs_columns_spin.isEnabled() is False
    assert window.cs_padding_spin.isEnabled() is False
    assert window.cs_show_labels_check.isEnabled() is False
    assert window.cs_font_size_spin.isEnabled() is False

    # Enable
    window.cs_enable_check.setChecked(True)
    assert window.cs_columns_spin.isEnabled() is True
    assert window.cs_padding_spin.isEnabled() is True
    assert window.cs_show_labels_check.isEnabled() is True
    assert window.cs_font_size_spin.isEnabled() is True
    assert window.layer_combo.isEnabled() is False

    # Disable again
    window.cs_enable_check.setChecked(False)
    assert window.cs_columns_spin.isEnabled() is False
    assert window.cs_padding_spin.isEnabled() is False
    assert window.cs_show_labels_check.isEnabled() is False
    assert window.cs_font_size_spin.isEnabled() is False
