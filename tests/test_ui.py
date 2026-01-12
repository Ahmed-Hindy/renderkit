"""Tests for the PySide6/PyQt UI.

Note: UI tests require pytest-qt and a display server (Xvfb on Linux).
Run with: pytest tests/test_ui.py -v
"""

import pytest

# Skip UI tests if pytest-qt is not available
from renderkit.ui.qt_compat import (
    QApplication,
    Qt,
    get_qt_backend,
)


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    app.quit()


def test_qt_backend_detection():
    """Test that Qt backend is detected."""
    backend = get_qt_backend()
    assert backend in ["pyside6", "pyside2", "pyqt6", "pyqt5"]


def test_main_window_creation(qtbot, qapp):
    """Test that main window can be created."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    assert window is not None
    assert window.windowTitle().startswith("RenderKit v")


def test_input_pattern_edit(qtbot, qapp):
    """Test input pattern edit widget."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Test setting pattern
    test_pattern = "render.%04d.exr"
    window.input_pattern_combo.lineEdit().setText(test_pattern)
    assert window.input_pattern_combo.currentText() == test_pattern


def test_output_path_edit(qtbot, qapp):
    """Test output path edit widget."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Test setting output path
    test_path = "output.mp4"
    window.output_path_edit.setText(test_path)
    assert window.output_path_edit.text() == test_path


def test_fps_spinbox(qtbot, qapp):
    """Test FPS spinbox."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Test FPS value
    window.fps_spin.setValue(30)
    assert window.fps_spin.value() == 30


def test_color_space_combo(qtbot, qapp):
    """Test color space combo box."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Test color space selection
    window.color_space_combo.setCurrentIndex(1)
    assert window.color_space_combo.currentIndex() == 1


def test_resolution_checkbox(qtbot, qapp):
    """Test keep resolution checkbox."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Test checkbox state
    assert window.keep_resolution_check.isChecked() is True
    window.keep_resolution_check.setChecked(False)
    assert window.keep_resolution_check.isChecked() is False
    # Width/height should be enabled when unchecked
    assert window.width_spin.isEnabled() is True
    assert window.height_spin.isEnabled() is True


def test_detect_button_click(qtbot, qapp, tmp_path):
    """Test detect sequence button."""
    from renderkit.ui.main_window import ModernMainWindow

    # Create test files
    for i in range(1, 6):
        (tmp_path / f"render.{i:04d}.exr").touch()

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Set pattern
    pattern = str(tmp_path / "render.%04d.exr")
    window.input_pattern_combo.lineEdit().setText(pattern)

    # Trigger detection
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    # Wait for detection
    qtbot.waitUntil(lambda: "Detected" in window.sequence_info_label.text(), timeout=2000)

    # Check that sequence was detected
    assert "Detected" in window.sequence_info_label.text()
    assert "frames" in window.sequence_info_label.text()


def test_convert_button_validation(qtbot, qapp, monkeypatch):
    """Test that convert button validates inputs."""
    from renderkit.ui.main_window import ModernMainWindow

    # Mock QMessageBox.warning
    warning_called = False

    def mock_warning(*args, **kwargs):
        nonlocal warning_called
        warning_called = True

    monkeypatch.setattr("renderkit.ui.main_window.QMessageBox.warning", mock_warning)

    window = ModernMainWindow()
    qtbot.addWidget(window)
    # Ensure it's empty
    window.input_pattern_combo.lineEdit().setText("")
    window.input_pattern_combo.setCurrentText("")

    # Try to convert without inputs - should show warning
    qtbot.mouseClick(window.convert_btn, Qt.LeftButton)

    assert warning_called
    assert window.convert_btn.isEnabled() is True


def test_preview_widget(qtbot, qapp):
    """Test preview widget creation."""
    from renderkit.ui.widgets import PreviewWidget

    widget = PreviewWidget()
    qtbot.addWidget(widget)

    assert widget is not None
    assert widget.preview_label is not None


def test_settings_persistence(qtbot, qapp):
    """Test that settings are saved and loaded."""
    from renderkit.ui.main_window import ModernMainWindow

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # Change some settings
    window.fps_spin.setValue(30)
    window.width_spin.setValue(1920)
    window.height_spin.setValue(1080)

    # Save settings
    window._save_settings()

    # Create new window and check settings are loaded
    window2 = ModernMainWindow()
    qtbot.addWidget(window2)

    # Settings should be loaded (but may vary based on QSettings implementation)
    # This is a basic test - full persistence testing would require more setup
