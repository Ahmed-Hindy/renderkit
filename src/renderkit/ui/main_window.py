"""Modern main window for RenderKit using the qt_compat abstraction."""

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

from renderkit import __version__
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
from renderkit.ui.splash_screen import (
    SPLASH_MIN_DURATION_MS,
    create_splash_screen,
    wait_for_minimum_splash_duration,
)
from renderkit.ui.timeline_controller import TimelineController

RECENT_PATTERNS_CLEAR_LABEL = _RECENT_PATTERNS_CLEAR_LABEL
RECENT_PATTERNS_KEY = _RECENT_PATTERNS_KEY
RECENT_PATTERNS_LIMIT = _RECENT_PATTERNS_LIMIT


class ModernMainWindow(MainWindowUiMixin, MainWindowLogicMixin, QMainWindow):
    """Modern main application window with comprehensive features."""

    if TYPE_CHECKING:
        burnin_zone_combo: Any
        slate_preview_check: Any

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setAcceptDrops(True)
        settings_org = "RenderKit"
        settings_app = "RenderKit"
        if os.environ.get("PYTEST_CURRENT_TEST"):
            settings_org = "RenderKitTest"
            settings_app = "RenderKitTest"
        self.settings = QSettings(settings_org, settings_app)
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
        self._auto_output_path: Optional[str] = None
        self._pending_layer: Optional[str] = None
        self._aspect_ratio: Optional[float] = None
        self._aspect_sync_guard = False
        self._last_preview_path: Optional[Path] = None
        self._codec_map: dict[int, str] = {}
        self._preset_burnin_zones: dict[str, Optional[str]] = {}
        # Debounce timer for real-time contact sheet preview updates
        self._cs_preview_timer = QTimer(self)
        self._cs_preview_timer.setSingleShot(True)
        self._cs_preview_timer.timeout.connect(self._load_preview)
        self.timeline_controller: Optional[TimelineController] = None

        self._setup_logging()
        self._ensure_bundled_ocio_config()

        # UI element references for responsive layout
        self.main_splitter: Optional[QSplitter] = None
        self.left_splitter: Optional[QSplitter] = None
        self.preview_panel: Optional[QWidget] = None
        self._current_layout_mode: str = "standard"

        self._apply_theme()
        self._setup_ui()
        self._setup_tray_icon()
        self._load_settings()
        self.timeline_controller = TimelineController(
            slider=self.timeline_slider,
            start_label=self.timeline_start_label,
            end_label=self.timeline_end_label,
            current_label=self.timeline_current_label,
            container=self.timeline_widget,
            load_preview=lambda path, scrubbing: self._load_preview_from_path(
                path, scrubbing=scrubbing
            ),
            parent=self,
        )
        self._setup_connections()


def run_ui(
    open_path: Optional[str] = None,
    layer: Optional[str] = None,
    preset: Optional[str] = None,
    ocio_path: Optional[str] = None,
) -> int:
    """Run the UI application.

    Args:
        open_path: Optional initial frame file, folder, or sequence pattern to open.
        layer: Optional EXR layer/AOV name to select once loaded.
        preset: Optional JSON preset path or name to apply on startup.
        ocio_path: Optional custom OCIO config path to apply on startup.

    Returns:
        Qt application exit code.
    """
    ensure_ffmpeg_env()
    existing_app = QApplication.instance() if hasattr(QApplication, "instance") else None
    app: QApplication = (
        cast(QApplication, existing_app) if existing_app is not None else QApplication(sys.argv)
    )
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

    splash_started_at = time.monotonic()
    splash = create_splash_screen(__version__)
    splash.show()
    app.processEvents()

    window = None
    try:
        window = ModernMainWindow()
    finally:
        if window is None:
            splash.close()

    if any(value is not None for value in (open_path, layer, preset, ocio_path)):
        window.apply_startup_options(
            open_path=open_path,
            layer=layer,
            preset=preset,
            ocio_path=ocio_path,
        )

    wait_for_minimum_splash_duration(
        app=app,
        started_at=splash_started_at,
        minimum_ms=SPLASH_MIN_DURATION_MS,
    )

    window.show()
    splash.finish(window)
    return int(app.exec())


if __name__ == "__main__":
    sys.exit(run_ui())
