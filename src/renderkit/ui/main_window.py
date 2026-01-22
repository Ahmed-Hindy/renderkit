"""Modern main window for RenderKit using the qt_compat abstraction."""

import sys
from typing import Optional

from renderkit.runtime import bootstrap_runtime

bootstrap_runtime()

from renderkit.core.ffmpeg_utils import ensure_ffmpeg_env
from renderkit.ui.conversion_worker import ConversionWorker
from renderkit.ui.file_info_worker import FileInfoWorker
from renderkit.ui.main_window_logic import (
    RECENT_PATTERNS_CLEAR_LABEL as _RECENT_PATTERNS_CLEAR_LABEL,
)
from renderkit.ui.main_window_logic import (
    RECENT_PATTERNS_KEY as _RECENT_PATTERNS_KEY,
)
from renderkit.ui.main_window_logic import (
    RECENT_PATTERNS_LIMIT as _RECENT_PATTERNS_LIMIT,
)
from renderkit.ui.main_window_logic import (
    MainWindowLogicMixin,
)
from renderkit.ui.main_window_ui import MainWindowUiMixin
from renderkit.ui.main_window_widgets import UiLogForwarder
from renderkit.ui.qt_compat import (
    QApplication,
    QMainWindow,
    QMessageBox,  # noqa: F401
    QSettings,
    QSplitter,
    QSystemTrayIcon,
    Qt,
    QTimer,
    QWidget,
)

RECENT_PATTERNS_CLEAR_LABEL = _RECENT_PATTERNS_CLEAR_LABEL
RECENT_PATTERNS_KEY = _RECENT_PATTERNS_KEY
RECENT_PATTERNS_LIMIT = _RECENT_PATTERNS_LIMIT


class ModernMainWindow(MainWindowUiMixin, MainWindowLogicMixin, QMainWindow):
    """Modern main application window with comprehensive features."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.settings = QSettings("RenderKit", "RenderKit")
        self.worker: Optional[ConversionWorker] = None
        self._conversion_finished_flag = False
        self._log_forwarder: Optional[UiLogForwarder] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._ocio_role_display_map: dict[str, str] = {}
        self._recent_patterns: list[str] = []
        self._last_pattern_text = ""
        self._convert_btn_handler: Optional[str] = None
        self._input_pattern_valid = False
        self._input_pattern_validated = False
        self._is_cancelling = False
        self._startup_logs: list[str] = []
        self._file_info_worker: Optional[FileInfoWorker] = None
        self._last_detected_pattern = ""

        # Debounce timer for real-time contact sheet preview updates
        self._cs_preview_timer = QTimer(self)
        self._cs_preview_timer.setSingleShot(True)
        self._cs_preview_timer.timeout.connect(self._load_preview)

        self._setup_logging()
        self._ensure_ocio_env()

        # UI element references for responsive layout
        self.main_splitter: Optional[QSplitter] = None
        self.left_splitter: Optional[QSplitter] = None
        self.preview_panel: Optional[QWidget] = None
        self._current_layout_mode: str = "standard"

        self._apply_theme()
        self._setup_ui()
        self._setup_tray_icon()
        self._load_settings()
        self._setup_connections()


def run_ui() -> None:
    """Run the UI application."""
    ensure_ffmpeg_env()
    app = QApplication(sys.argv)
    app.setApplicationName("RenderKit")
    app.setOrganizationName("RenderKit")

    # Set modern style
    app.setStyle("Fusion")

    # Neutralize system palette overrides to prevent purple "leaks"
    from renderkit.ui.qt_compat import QPalette

    palette = app.palette()
    # Explicitly set accents to standard neutral/blue if they were overridden by system
    palette.setColor(QPalette.ColorRole.Highlight, Qt.GlobalColor.blue)
    app.setPalette(palette)

    window = ModernMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_ui()
