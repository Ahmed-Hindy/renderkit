"""Qt compatibility layer for PyQt5, PyQt6, PySide2, and PySide6."""

import importlib
import os
from typing import Optional

_BACKEND_ORDER = ("pyside6", "pyside2", "pyqt6", "pyqt5")
_BACKEND_MODULES = {
    "pyside6": "PySide6",
    "pyside2": "PySide2",
    "pyqt6": "PyQt6",
    "pyqt5": "PyQt5",
}

_QTCORE_NAMES = [
    "QEvent",
    "QObject",
    "QPoint",
    "QSettings",
    "QSize",
    "Qt",
    "QThread",
    "QTimer",
    "QUrl",
]
_QTGUI_NAMES = [
    "QColor",
    "QDesktopServices",
    "QFont",
    "QIcon",
    "QImage",
    "QPainter",
    "QPalette",
    "QPixmap",
]
_QTWIDGET_NAMES = [
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFormLayout",
    "QFrame",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QScrollArea",
    "QSizePolicy",
    "QSlider",
    "QSpinBox",
    "QSplitter",
    "QSystemTrayIcon",
    "QTabWidget",
    "QVBoxLayout",
    "QWidget",
]

# Try to detect which Qt backend to use
# Priority: Environment variable > PySide6 > PySide2 > PyQt6 > PyQt5
QT_BACKEND: Optional[str] = os.environ.get("QT_BACKEND", "").lower()

if QT_BACKEND:
    # User specified backend
    if QT_BACKEND in _BACKEND_MODULES:
        _backend = QT_BACKEND
    else:
        raise ValueError(
            f"Invalid QT_BACKEND: {QT_BACKEND}. Must be one of: pyside6, pyside2, pyqt6, pyqt5"
        )
else:
    # Auto-detect: try in order of preference
    _backend = None
    for backend in _BACKEND_ORDER:
        try:
            importlib.import_module(_BACKEND_MODULES[backend])
        except ImportError:
            continue
        _backend = backend
        break

if _backend is None:
    raise ImportError(
        "No Qt backend found. Please install one of: PySide6, PySide2, PyQt6, or PyQt5"
    )

# Import based on detected backend
_module = _BACKEND_MODULES[_backend]
_qtcore = importlib.import_module(f"{_module}.QtCore")
_qtgui = importlib.import_module(f"{_module}.QtGui")
_qtwidgets = importlib.import_module(f"{_module}.QtWidgets")

for name in _QTCORE_NAMES:
    globals()[name] = getattr(_qtcore, name)
for name in _QTGUI_NAMES:
    globals()[name] = getattr(_qtgui, name)
for name in _QTWIDGET_NAMES:
    globals()[name] = getattr(_qtwidgets, name)

if _backend in ("pyqt6", "pyqt5"):
    Signal = _qtcore.pyqtSignal
else:
    Signal = _qtcore.Signal

# Export backend info
QT_BACKEND_NAME = _backend

__all__ = [
    # Qt Core
    "QObject",
    "QSettings",
    "QThread",
    "Signal",
    "Qt",
    "QTimer",
    "QUrl",
    "QEvent",
    "QSize",
    "QPoint",
    # Qt Gui
    "QFont",
    "QIcon",
    "QPixmap",
    "QImage",
    "QDesktopServices",
    "QColor",
    "QPainter",
    "QPalette",
    # Qt Widgets
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QFileDialog",
    "QFormLayout",
    "QFrame",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QScrollArea",
    "QSizePolicy",
    "QSlider",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSplitter",
    "QSystemTrayIcon",
    "QTabWidget",
    "QVBoxLayout",
    "QWidget",
    # Backend info
    "QT_BACKEND_NAME",
]


def get_qt_backend() -> str:
    """Get the currently used Qt backend.

    Returns:
        Backend name: 'pyside6', 'pyside2', 'pyqt6', or 'pyqt5'
    """
    return QT_BACKEND_NAME
