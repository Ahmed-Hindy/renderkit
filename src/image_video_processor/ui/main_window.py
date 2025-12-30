"""Main window for PySide/Qt UI."""

import logging
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from image_video_processor.api.processor import ImageVideoProcessor
from image_video_processor.core.config import ConversionConfig, ConversionConfigBuilder
from image_video_processor.processing.color_space import ColorSpacePreset

logger = logging.getLogger(__name__)


class ConversionWorker(QThread):
    """Worker thread for conversion to avoid blocking UI."""

    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int)  # current, total

    def __init__(self, config: ConversionConfig) -> None:
        """Initialize worker.

        Args:
            config: Conversion configuration
        """
        super().__init__()
        self.config = config

    def run(self) -> None:
        """Run the conversion."""
        try:
            from image_video_processor.core.converter import SequenceConverter

            converter = SequenceConverter(self.config)
            converter.convert()
            self.finished.emit()
        except Exception as e:
            logger.exception("Conversion failed")
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("Image Video Processor")
        self.setGeometry(100, 100, 800, 600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # Input pattern button
        self.input_button = QPushButton("Select Input Pattern")
        self.input_button.clicked.connect(self.select_input_pattern)
        layout.addWidget(self.input_button)

        # Output path button
        self.output_button = QPushButton("Select Output Path")
        self.output_button.clicked.connect(self.select_output_path)
        layout.addWidget(self.output_button)

        # Convert button
        self.convert_button = QPushButton("Convert")
        self.convert_button.clicked.connect(self.start_conversion)
        layout.addWidget(self.convert_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # State
        self.input_pattern: Optional[str] = None
        self.output_path: Optional[str] = None
        self.worker: Optional[ConversionWorker] = None

    def select_input_pattern(self) -> None:
        """Select input file pattern."""
        # For now, select a single file and extract pattern
        # In a full implementation, would have better pattern selection
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Input File (representative frame)", "", "EXR Files (*.exr)"
        )
        if file_path:
            # Extract pattern (simplified - would need better pattern detection)
            self.input_pattern = file_path
            self.input_button.setText(f"Input: {Path(file_path).name}")

    def select_output_path(self) -> None:
        """Select output video path."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", "", "MP4 Files (*.mp4)"
        )
        if file_path:
            self.output_path = file_path
            self.output_button.setText(f"Output: {Path(file_path).name}")

    def start_conversion(self) -> None:
        """Start the conversion process."""
        if not self.input_pattern or not self.output_path:
            QMessageBox.warning(self, "Error", "Please select input pattern and output path")
            return

        # Build configuration
        try:
            config = (
                ConversionConfigBuilder()
                .with_input_pattern(self.input_pattern)
                .with_output_path(self.output_path)
                .with_color_space_preset(ColorSpacePreset.LINEAR_TO_SRGB)
                .build()
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Configuration error: {e}")
            return

        # Disable convert button
        self.convert_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        # Start worker thread
        self.worker = ConversionWorker(config)
        self.worker.finished.connect(self.on_conversion_finished)
        self.worker.error.connect(self.on_conversion_error)
        self.worker.start()

    def on_conversion_finished(self) -> None:
        """Handle conversion completion."""
        self.convert_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(self, "Success", "Conversion completed successfully!")

    def on_conversion_error(self, error_msg: str) -> None:
        """Handle conversion error."""
        self.convert_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "Error", f"Conversion failed: {error_msg}")


def run_ui() -> None:
    """Run the UI application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_ui()

