"""Qt compatibility layer for PyQt5, PyQt6, PySide2, and PySide6."""

import os
from typing import Optional

# Try to detect which Qt backend to use
# Priority: Environment variable > PySide6 > PySide2 > PyQt6 > PyQt5

QT_BACKEND: Optional[str] = os.environ.get("QT_BACKEND", "").lower()

if QT_BACKEND:
    # User specified backend
    if QT_BACKEND in ("pyside6", "pyside2", "pyqt6", "pyqt5"):
        _backend = QT_BACKEND
    else:
        raise ValueError(
            f"Invalid QT_BACKEND: {QT_BACKEND}. Must be one of: pyside6, pyside2, pyqt6, pyqt5"
        )
else:
    # Auto-detect: try in order of preference
    _backend = None
    for backend in ["pyside6", "pyside2", "pyqt6", "pyqt5"]:
        try:
            if backend == "pyside6":
                import PySide6  # noqa: F401

                _backend = "pyside6"
                break
            elif backend == "pyside2":
                import PySide2  # noqa: F401

                _backend = "pyside2"
                break
            elif backend == "pyqt6":
                import PyQt6  # noqa: F401

                _backend = "pyqt6"
                break
            elif backend == "pyqt5":
                import PyQt5  # noqa: F401

                _backend = "pyqt5"
                break
        except ImportError:
            continue

if _backend is None:
    raise ImportError(
        "No Qt backend found. Please install one of: PySide6, PySide2, PyQt6, or PyQt5"
    )

# Import based on detected backend
if _backend == "pyside6":
    from PySide6.QtCore import QSettings, Qt, QThread, Signal
    from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
elif _backend == "pyside2":
    from PySide2.QtCore import QSettings, Qt, QThread, Signal
    from PySide2.QtGui import QFont, QIcon, QImage, QPixmap
    from PySide2.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
elif _backend == "pyqt6":
    from PyQt6.QtCore import QSettings, Qt, QThread
    from PyQt6.QtCore import pyqtSignal as Signal
    from PyQt6.QtGui import QFont, QIcon, QImage, QPixmap
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
elif _backend == "pyqt5":
    from PyQt5.QtCore import QSettings, Qt, QThread
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtGui import QFont, QIcon, QImage, QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

# Export backend info
QT_BACKEND_NAME = _backend

__all__ = [
    # Qt Core
    "QSettings",
    "QThread",
    "Signal",
    "Qt",
    # Qt Gui
    "QFont",
    "QIcon",
    "QPixmap",
    "QImage",
    # Qt Widgets
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QFileDialog",
    "QFormLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QLineEdit",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QSizePolicy",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSplitter",
    "QTabWidget",
    "QVBoxLayout",
    "QWidget",
    "QSlider",
    # Backend info
    "QT_BACKEND_NAME",
]


def get_qt_backend() -> str:
    """Get the currently used Qt backend.

    Returns:
        Backend name: 'pyside6', 'pyside2', 'pyqt6', or 'pyqt5'
    """
    return QT_BACKEND_NAME
