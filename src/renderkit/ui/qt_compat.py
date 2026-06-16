"""Qt compatibility layer for PyQt5, PyQt6, PySide2, and PySide6."""

import importlib
import os
from typing import TYPE_CHECKING, Optional

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
    "QCursor",
    "QDesktopServices",
    "QFont",
    "QIcon",
    "QImage",
    "QMouseEvent",
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
    "QGridLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QListView",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QScrollArea",
    "QSplashScreen",
    "QSizePolicy",
    "QSlider",
    "QSpinBox",
    "QSplitter",
    "QStyle",
    "QStyleOptionSlider",
    "QSystemTrayIcon",
    "QTabWidget",
    "QToolButton",
    "QVBoxLayout",
    "QWidget",
]

if TYPE_CHECKING:
    from PySide6.QtCore import (  # noqa: F401
        QEvent,
        QObject,
        QPoint,
        QSettings,
        QSize,
        Qt,
        QThread,
        QTimer,
        QUrl,
    )
    from PySide6.QtGui import (  # noqa: F401
        QColor,
        QCursor,
        QDesktopServices,
        QFont,
        QIcon,
        QImage,
        QMouseEvent,
        QPainter,
        QPalette,
        QPixmap,
    )
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListView,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplashScreen,
        QSplitter,
        QStyle,
        QStyleOptionSlider,
        QSystemTrayIcon,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

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
    "QMouseEvent",
    "QDesktopServices",
    "QColor",
    "QCursor",
    "QPainter",
    "QPalette",
    # Qt Widgets
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QFileDialog",
    "QFormLayout",
    "QFrame",
    "QGridLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QListView",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QScrollArea",
    "QSplashScreen",
    "QSizePolicy",
    "QSlider",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSplitter",
    "QStyle",
    "QStyleOptionSlider",
    "QSystemTrayIcon",
    "QTabWidget",
    "QToolButton",
    "QVBoxLayout",
    "QWidget",
    # Backend info
    "QT_BACKEND_NAME",
    "resolve_enum_member",
    "qt_enum",
]


def get_qt_backend() -> str:
    """Get the currently used Qt backend.

    Returns:
        Backend name: 'pyside6', 'pyside2', 'pyqt6', or 'pyqt5'
    """
    return QT_BACKEND_NAME


def resolve_enum_member(owner, enum_name: str, member_name: str):
    """Resolve Qt6 nested enum members with a Qt5 flat-attribute fallback."""
    enum = getattr(owner, enum_name, None)
    if enum is not None:
        value = getattr(enum, member_name, None)
        if value is not None:
            return value

    value = getattr(owner, member_name, None)
    if value is None:
        raise AttributeError(f"{owner!r} has no enum member {enum_name}.{member_name}")
    return value


def qt_enum(enum_name: str, member_name: str):
    """Resolve a Qt enum member across supported Qt bindings."""
    return resolve_enum_member(Qt, enum_name, member_name)
