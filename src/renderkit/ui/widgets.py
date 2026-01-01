"""Custom widgets for the UI."""

from pathlib import Path
from typing import Optional

import numpy as np

from renderkit.io.image_reader import ImageReaderFactory
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.ui.qt_compat import (
    QImage,
    QLabel,
    QPixmap,
    Qt,
    QThread,
    QVBoxLayout,
    QWidget,
    Signal,
)


class PreviewWorker(QThread):
    """Worker thread for loading preview image."""

    preview_ready = Signal(QPixmap)
    error = Signal(str)

    def __init__(self, file_path: Path, color_space: ColorSpacePreset) -> None:
        """Initialize preview worker.

        Args:
            file_path: Path to image file
            color_space: Color space preset for conversion
        """
        super().__init__()
        self.file_path = file_path
        self.color_space = color_space

    def run(self) -> None:
        """Load and process preview image."""
        try:
            reader = ImageReaderFactory.create_reader(self.file_path)
            image = reader.read(self.file_path)

            # Convert color space
            converter = ColorSpaceConverter(self.color_space)
            image = converter.convert(image)

            # Convert to uint8
            if image.dtype != np.uint8:
                image = np.clip(image * 255.0, 0, 255).astype(np.uint8)

            # Convert to QImage
            height, width = image.shape[:2]
            # Handle different Qt versions - format access differs
            # PySide6/PyQt6: QImage.Format.Format_RGB888
            # PySide2/PyQt5: QImage.Format_RGB888
            try:
                # Try PySide6/PyQt6 style
                rgb_format = getattr(QImage.Format, "Format_RGB888", None)
                rgba_format = getattr(QImage.Format, "Format_RGBA8888", None)
            except (AttributeError, TypeError):
                # Try PySide2/PyQt5 style
                rgb_format = getattr(QImage, "Format_RGB888", None)
                rgba_format = getattr(QImage, "Format_RGBA8888", None)

            # Fallback to direct attribute access if getattr failed
            if rgb_format is None:
                try:
                    rgb_format = QImage.Format.Format_RGB888
                except AttributeError:
                    rgb_format = QImage.Format_RGB888

            if rgba_format is None:
                try:
                    rgba_format = QImage.Format.Format_RGBA8888
                except AttributeError:
                    rgba_format = QImage.Format_RGBA8888

            if image.shape[2] == 3:
                # RGB
                q_image = QImage(image.data, width, height, width * 3, rgb_format)
            elif image.shape[2] == 4:
                # RGBA
                q_image = QImage(image.data, width, height, width * 4, rgba_format)
            else:
                raise ValueError(f"Unsupported image channels: {image.shape[2]}")

            # Create pixmap and scale if needed
            pixmap = QPixmap.fromImage(q_image)
            if pixmap.width() > 400 or pixmap.height() > 300:
                pixmap = pixmap.scaled(
                    400,
                    300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

            self.preview_ready.emit(pixmap)
        except Exception as e:
            self.error.emit(str(e))


class PreviewWidget(QWidget):
    """Widget for displaying image preview."""

    def __init__(self) -> None:
        """Initialize preview widget."""
        super().__init__()
        self._setup_ui()
        self.worker: Optional[PreviewWorker] = None

    def _setup_ui(self) -> None:
        """Set up the preview UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 300)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label)

    def load_preview(self, file_path: Path, color_space: ColorSpacePreset) -> None:
        """Load preview from file.

        Args:
            file_path: Path to image file
            color_space: Color space preset
        """
        # Cancel previous worker if running
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()

        self.preview_label.setText("Loading preview...")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        self.worker = PreviewWorker(file_path, color_space)
        self.worker.preview_ready.connect(self._on_preview_ready)
        self.worker.error.connect(self._on_preview_error)
        self.worker.start()

    def _on_preview_ready(self, pixmap: QPixmap) -> None:
        """Handle preview ready."""
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setText("")

    def _on_preview_error(self, error: str) -> None:
        """Handle preview error."""
        self.preview_label.setText(f"Preview error:\n{error}")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #f44336;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

    def clear_preview(self) -> None:
        """Clear the preview."""
        self.preview_label.clear()
        self.preview_label.setText("No preview")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
