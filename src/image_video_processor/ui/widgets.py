"""Custom widgets for the UI."""

from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from image_video_processor.io.image_reader import ImageReaderFactory
from image_video_processor.processing.color_space import ColorSpaceConverter, ColorSpacePreset


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
            if image.shape[2] == 3:
                # RGB
                q_image = QImage(
                    image.data,
                    width,
                    height,
                    width * 3,
                    QImage.Format.Format_RGB888
                )
            elif image.shape[2] == 4:
                # RGBA
                q_image = QImage(
                    image.data,
                    width,
                    height,
                    width * 4,
                    QImage.Format.Format_RGBA8888
                )
            else:
                raise ValueError(f"Unsupported image channels: {image.shape[2]}")

            # Create pixmap and scale if needed
            pixmap = QPixmap.fromImage(q_image)
            if pixmap.width() > 400 or pixmap.height() > 300:
                pixmap = pixmap.scaled(
                    400, 300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
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
