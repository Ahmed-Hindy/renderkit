"""Worker thread for conversion to avoid blocking UI."""

import logging

from renderkit.core.config import ConversionConfig
from renderkit.ui.qt_compat import QThread, Signal

logger = logging.getLogger(__name__)


class ConversionWorker(QThread):
    """Worker thread for conversion to avoid blocking UI."""

    finished = Signal()
    error = Signal(str)
    cancelled = Signal()
    progress = Signal(int, int)  # current, total

    def __init__(self, config: ConversionConfig) -> None:
        """Initialize worker.

        Args:
            config: Conversion configuration
        """
        super().__init__()
        self.config = config
        self._is_cancelled = False

    def request_cancel(self) -> None:
        """Request the worker to stop gracefully."""
        self._is_cancelled = True

    def run(self) -> None:
        """Run the conversion."""
        try:
            from renderkit.core.converter import SequenceConverter
            from renderkit.exceptions import ConversionCancelledError

            logger.info("Starting conversion...")
            converter = SequenceConverter(self.config)

            def progress_callback(current, total):
                self.progress.emit(current, total)
                # Return True to continue, False to cancel
                return not self._is_cancelled

            converter.convert(progress_callback=progress_callback)
            self.finished.emit()
        except ConversionCancelledError:
            logger.info("Conversion cancelled by user.")
            self.cancelled.emit()
        except Exception as e:
            msg = f"Conversion failed: {e}"
            logger.exception(msg)
            self.error.emit(msg)
