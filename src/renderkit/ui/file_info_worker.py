"""Worker thread for async file metadata discovery."""

import logging
from pathlib import Path

from renderkit.io.image_reader import ImageReaderFactory
from renderkit.ui.qt_compat import QThread, Signal

logger = logging.getLogger(__name__)


class FileInfoWorker(QThread):
    """Background worker for discovering file metadata without blocking UI.

    This worker runs file I/O operations in a background thread, which is
    especially important for heavy EXR files accessed over network paths.
    """

    # Signal emitted when file info is ready: (file_path, FileInfo)
    file_info_ready = Signal(str, object)

    # Signal emitted on error: (file_path, error_message)
    error_occurred = Signal(str, str)

    def __init__(self, file_path: Path, parent=None) -> None:
        """Initialize the worker.

        Args:
            file_path: Path to file to analyze
            parent: Parent QObject
        """
        super().__init__(parent)
        self.file_path = file_path
        self._should_stop = False

    def run(self) -> None:
        """Execute file info discovery in background thread."""
        try:
            logger.debug(f"FileInfoWorker: Starting discovery for {self.file_path}")

            if self._should_stop:
                return

            reader = ImageReaderFactory.create_reader(self.file_path)
            file_info = reader.get_file_info(self.file_path)

            if not self._should_stop:
                logger.debug(f"FileInfoWorker: Discovery complete for {self.file_path}")
                self.file_info_ready.emit(str(self.file_path), file_info)

        except Exception as e:
            if not self._should_stop:
                logger.error(f"FileInfoWorker: Error discovering file info: {e}")
                self.error_occurred.emit(str(self.file_path), str(e))

    def stop(self) -> None:
        """Request the worker to stop."""
        self._should_stop = True
