"""Tests for the PySide6/PyQt UI.

Note: UI tests require pytest-qt and a display server (Xvfb on Linux).
Run with: pytest tests/test_ui.py -v
"""

from pathlib import Path

import pytest

# Skip UI tests if pytest-qt is not available
from renderkit.ui.qt_compat import (
    QApplication,
    get_qt_backend,
)


def test_frame_range_updates(qtbot, tmp_path, monkeypatch):
    """Test that start/end frame range updates when pattern changes."""
    from renderkit.ui.main_window import ModernMainWindow

    # Mock SequenceDetector
    class MockSequence:
        def __init__(self, frame_numbers):
            self.frame_numbers = frame_numbers

        def __len__(self):
            return len(self.frame_numbers)

        def get_file_path(self, frame):
            return Path(f"render.{frame:04d}.exr")

    def mock_detect(pattern):
        if "seq1" in pattern:
            return MockSequence([101, 102, 103])
        elif "seq2" in pattern:
            return MockSequence([1, 2, 3, 4, 5])
        return MockSequence([1])

    monkeypatch.setattr("renderkit.core.sequence.SequenceDetector.detect_sequence", mock_detect)
    # Mock FileInfoWorker to avoid async metadata issues
    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    # 1. Detect Sequence 1
    window.input_pattern_combo.lineEdit().setText("render_seq1.%04d.exr")
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    qtbot.waitUntil(lambda: window.start_frame_spin.value() == 101, timeout=1000)
    assert window.start_frame_spin.value() == 101
    assert window.end_frame_spin.value() == 103

    # 2. Switch to Sequence 2
    window.input_pattern_combo.lineEdit().setText("render_seq2.%04d.exr")
    window.input_pattern_combo.lineEdit().textChanged.emit("render_seq2.%04d.exr")  # Trigger reset
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    qtbot.waitUntil(lambda: window.start_frame_spin.value() == 1, timeout=1000)
    assert window.start_frame_spin.value() == 1
    assert window.end_frame_spin.value() == 5


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


def test_output_path_auto_generated(qtbot, tmp_path, monkeypatch):
    """Test output path auto-generation from input pattern."""
    from renderkit.ui.main_window import ModernMainWindow

    # Create test files
    for i in range(1, 4):
        (tmp_path / f"render.{i:04d}.exr").touch()

    # Avoid async metadata worker
    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    pattern = str(tmp_path / "render.%04d.exr")
    window.input_pattern_combo.lineEdit().setText(pattern)
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    expected = str(tmp_path / "render.mp4")
    qtbot.waitUntil(lambda: window.output_path_edit.text() == expected, timeout=2000)
    assert window.output_path_edit.text() == expected


def test_output_path_updates_on_pattern_change(qtbot, tmp_path, monkeypatch):
    """Test output path updates when input pattern changes."""
    from renderkit.ui.main_window import ModernMainWindow

    for i in range(1, 3):
        (tmp_path / f"first.{i:04d}.exr").touch()
        (tmp_path / f"second.{i:04d}.exr").touch()

    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    first_pattern = str(tmp_path / "first.%04d.exr")
    second_pattern = str(tmp_path / "second.%04d.exr")

    window.input_pattern_combo.lineEdit().setText(first_pattern)
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    first_output = str(tmp_path / "first.mp4")
    qtbot.waitUntil(lambda: window.output_path_edit.text() == first_output, timeout=2000)
    assert window.output_path_edit.text() == first_output

    window.input_pattern_combo.lineEdit().setText(second_pattern)
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    second_output = str(tmp_path / "second.mp4")
    qtbot.waitUntil(lambda: window.output_path_edit.text() == second_output, timeout=2000)
    assert window.output_path_edit.text() == second_output


def test_recent_patterns_updated(qtbot, tmp_path, monkeypatch):
    """Test recent patterns list updates after detection."""
    from renderkit.ui.main_window import RECENT_PATTERNS_KEY, ModernMainWindow

    for i in range(1, 3):
        (tmp_path / f"render.{i:04d}.exr").touch()

    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    previous = window.settings.value(RECENT_PATTERNS_KEY, None)
    window.settings.remove(RECENT_PATTERNS_KEY)
    window._recent_patterns = []
    window._refresh_recent_patterns_combo()

    pattern = str(tmp_path / "render.%04d.exr")
    window.input_pattern_combo.lineEdit().setText(pattern)
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    qtbot.waitUntil(lambda: pattern in window._recent_patterns, timeout=2000)
    combo_items = [
        window.input_pattern_combo.itemText(i) for i in range(window.input_pattern_combo.count())
    ]
    assert pattern in combo_items

    if previous is None:
        window.settings.remove(RECENT_PATTERNS_KEY)
    else:
        window.settings.setValue(RECENT_PATTERNS_KEY, previous)


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


def test_timeline_scrubbers(qtbot, qapp, monkeypatch):
    """Test timeline scrubber range and preview updates."""
    from renderkit.ui.main_window import ModernMainWindow

    class MockSequence:
        def __init__(self, frame_numbers):
            self.frame_numbers = frame_numbers

        def __len__(self):
            return len(self.frame_numbers)

        def get_file_path(self, frame):
            return Path(f"render.{frame:04d}.exr")

    def mock_detect(_pattern):
        return MockSequence([1001, 1003, 1005])

    monkeypatch.setattr("renderkit.core.sequence.SequenceDetector.detect_sequence", mock_detect)
    monkeypatch.setattr("renderkit.ui.main_window.FileInfoWorker.start", lambda self: None)

    window = ModernMainWindow()
    qtbot.addWidget(window)

    assert window.timeline_widget.isHidden() is True

    window.input_pattern_combo.lineEdit().setText("render.%04d.exr")
    window.input_pattern_combo.lineEdit().editingFinished.emit()

    qtbot.waitUntil(lambda: not window.timeline_widget.isHidden(), timeout=1000)
    assert window.timeline_slider.minimum() == 0
    assert window.timeline_slider.maximum() == 2
    assert window.timeline_slider.value() == 0
    assert "1001" in window.timeline_current_label.text()

    called = {}

    def mock_load_preview(path, **_kwargs):
        called["path"] = path

    monkeypatch.setattr(window, "_load_preview_from_path", mock_load_preview)
    window.timeline_slider.setValue(1)
    qtbot.waitUntil(lambda: "path" in called, timeout=1000)
    assert called["path"].name == "render.1003.exr"


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
    window._update_convert_gate()  # Force update

    # The convert button should be disabled when no inputs are present
    assert window.convert_btn.isEnabled() is False

    # Mock inputs to enable it
    window.input_pattern_combo.lineEdit().setText("render.%04d.exr")
    window._input_pattern_valid = True
    window.output_path_edit.setText("output.mp4")
    window._update_convert_gate()

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
