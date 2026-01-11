"""Modern main window for RenderKit using the qt_compat abstraction."""

import logging
import os
import sys
from importlib import resources
from pathlib import Path
from typing import Optional

from renderkit import __version__, constants
from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfigBuilder,
)
from renderkit.core.ffmpeg_utils import ensure_ffmpeg_env
from renderkit.io.file_utils import FileUtils
from renderkit.logging_utils import setup_logging
from renderkit.processing.color_space import (
    ColorSpacePreset,
    get_ocio_colorspace_label,
    get_ocio_role_display_options,
    resolve_ocio_role_label_for_colorspace,
)
from renderkit.processing.video_encoder import get_available_encoders, select_available_encoder
from renderkit.ui.conversion_worker import ConversionWorker
from renderkit.ui.icons import icon_manager
from renderkit.ui.qt_compat import (
    QT_BACKEND_NAME,
    QApplication,
    QCheckBox,
    QComboBox,
    QDesktopServices,
    QDoubleSpinBox,
    QFileDialog,
    QFont,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QObject,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSettings,
    QSize,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    Qt,
    QUrl,
    QVBoxLayout,
    QWidget,
    Signal,
)
from renderkit.ui.widgets import PreviewWidget

logger = logging.getLogger(__name__)

RECENT_PATTERNS_LIMIT = 10
RECENT_PATTERNS_KEY = "recent_patterns"
RECENT_PATTERNS_CLEAR_LABEL = "Clear recent patterns"


class NoWheelSpinBox(QSpinBox):
    """Spin box that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Double spin box that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelComboBox(QComboBox):
    """Combo box that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        size_adjust_policy = getattr(QComboBox, "SizeAdjustPolicy", None)
        if size_adjust_policy is not None:
            self.setSizeAdjustPolicy(size_adjust_policy.AdjustToMinimumContentsLengthWithIcon)
        else:
            self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelSlider(QSlider):
    """Slider that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class UiLogForwarder(QObject):
    """Signal-based forwarder for log messages."""

    message = Signal(str)


class ModernMainWindow(QMainWindow):
    """Modern main application window with comprehensive features."""

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.settings = QSettings("RenderKit", "RenderKit")
        self.worker: Optional[ConversionWorker] = None
        self._conversion_finished_flag = False
        self._log_forwarder: Optional[UiLogForwarder] = None
        self._ocio_role_display_map: dict[str, str] = {}
        self._recent_patterns: list[str] = []
        self._last_pattern_text = ""
        self._convert_btn_handler: Optional[str] = None
        self._input_pattern_valid = False
        self._input_pattern_validated = False
        self._is_cancelling = False
        self._startup_logs: list[str] = []

        self._setup_logging()
        self._ensure_ocio_env()

        # UI element references for responsive layout
        self.main_splitter: Optional[QSplitter] = None
        self.left_splitter: Optional[QSplitter] = None
        self.preview_panel: Optional[QWidget] = None
        self._current_layout_mode: str = "standard"

        self._apply_theme()
        self._setup_ui()
        self._load_settings()
        self._setup_connections()

    def _ensure_ocio_env(self) -> None:
        """Ensure OCIO environment variable is set, using bundled config if needed."""
        if os.environ.get("OCIO"):
            logger.info(f"Using existing OCIO environment variable: {os.environ['OCIO']}")
            return

        # Look for bundled config
        # In PyInstaller, sys._MEIPASS is the root. We added it to 'renderkit/data/ocio/config.ocio'
        bundled_config = None

        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidate = Path(sys._MEIPASS) / "renderkit" / "data" / "ocio" / "config.ocio"
            if candidate.exists():
                bundled_config = candidate
        else:
            # Dev mode: assuming this file is in src/renderkit/ui/main_window.py
            # Config is in src/renderkit/data/ocio/config.ocio
            # ../../data/ocio/config.ocio
            current_dir = Path(__file__).parent
            candidate = current_dir.parent / "data" / "ocio" / "config.ocio"
            if candidate.exists():
                bundled_config = candidate

        if bundled_config:
            logger.info(f"Setting OCIO environment variable to bundled config: {bundled_config}")
            os.environ["OCIO"] = str(bundled_config.resolve())
        else:
            logger.warning("Could not find bundled ocio/config.ocio and OCIO env var is not set.")

    def keyPressEvent(self, event) -> None:
        """Handle global key presses for the main window."""
        escape_key = getattr(Qt, "Key_Escape", None)
        if escape_key is None:
            key_enum = getattr(Qt, "Key", None)
            if key_enum is not None:
                escape_key = getattr(key_enum, "Key_Escape", None)

        if escape_key is not None and event.key() == escape_key:
            if self.worker and self.worker.isRunning():
                self._cancel_conversion()
                event.accept()
                return

        super().keyPressEvent(event)

    def _setup_logging(self) -> None:
        """Route renderkit logs into the UI log widget."""
        if self._log_forwarder is not None:
            return
        forwarder = UiLogForwarder(self)
        forwarder.message.connect(self._on_log_message)
        setup_logging(ui_sink=forwarder.message.emit, enable_console=False)
        self._log_forwarder = forwarder

    def _apply_theme(self) -> None:
        """Apply a theme from QSS file."""
        theme_name = "dark"
        self.setProperty("theme", theme_name)
        icon_manager.set_default_color("#e6edf3" if theme_name == "dark" else "#1f2328")
        try:
            qss_text = (
                resources.files("renderkit.ui")
                .joinpath("stylesheets", "matcha.qss")
                .read_text(encoding="utf-8")
            )
        except Exception as e:
            logger.error(f"Could not load stylesheet: {e}")
            return

        self.setStyleSheet(qss_text)

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle(f"RenderKit v{__version__}")
        self.setMinimumSize(500, 450)
        self.resize(1400, 950)
        self._last_preview_path: Optional[Path] = None

        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 5)  # Reduced bottom margin
        main_layout.setSpacing(5)  # Reduced spacing

        # Create main splitter for resizable panels
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter, 1)  # 1 = stretch to fill space

        # Left panel - Settings and Preview
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        settings_panel = self._create_settings_panel()
        settings_panel.setObjectName("Card")
        self.left_splitter.addWidget(settings_panel)

        # Preview panel
        self.preview_panel = self._create_preview_panel()
        self.preview_panel.setObjectName("Card")
        self.left_splitter.addWidget(self.preview_panel)
        self.left_splitter.setSizes([400, 180])

        self.main_splitter.addWidget(self.left_splitter)

        # Right panel - Log and Progress
        right_panel = self._create_log_panel()
        right_panel.setObjectName("Card")
        self.main_splitter.addWidget(right_panel)

        # Set splitter proportions (70% left, 30% right)
        self.main_splitter.setSizes([700, 300])
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)

        # Bottom panel - Action buttons
        action_panel = self._create_action_panel()
        main_layout.addWidget(action_panel, 0)  # 0 = no stretch, stays at bottom

        # Menu bar
        self._create_menu_bar()

        # Status bar
        self.statusBar().showMessage("Ready")

        # Flush startup logs
        if self._startup_logs:
            for msg in self._startup_logs:
                self.log_text.appendPlainText(msg)
            self._startup_logs.clear()

    def _set_form_growth_policy(self, form_layout: QFormLayout) -> None:
        policy_enum = getattr(QFormLayout, "FieldGrowthPolicy", None)
        if policy_enum is not None:
            form_layout.setFieldGrowthPolicy(policy_enum.AllNonFixedFieldsGrow)
        else:
            form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

    def resizeEvent(self, event):
        """Handle window resize to adjust layout responsively."""
        super().resizeEvent(event)
        height = event.size().height()

        # Determine layout mode based on height
        if height < 900:
            new_mode = "compact"
        elif height < 1100:
            new_mode = "standard"
        else:
            new_mode = "comfortable"

        # Only apply if mode changed
        if new_mode != self._current_layout_mode:
            self._current_layout_mode = new_mode
            if new_mode == "compact":
                self._apply_compact_mode()
            elif new_mode == "standard":
                self._apply_standard_mode()
            else:
                self._apply_comfortable_mode()

    def _apply_compact_mode(self):
        """Apply compact layout for small windows (<900px)."""
        if self.preview_panel:
            self.preview_panel.setVisible(False)
        # Adjust splitter to give more space to settings
        if self.main_splitter:
            self.main_splitter.setSizes([800, 200])

    def _apply_standard_mode(self):
        """Apply standard layout (900-1100px)."""
        if self.preview_panel:
            self.preview_panel.setVisible(True)
        # Standard splitter sizes
        if self.main_splitter:
            self.main_splitter.setSizes([700, 300])
        if self.left_splitter:
            self.left_splitter.setSizes([400, 180])

    def _apply_comfortable_mode(self):
        """Apply comfortable layout for large windows (>1100px)."""
        if self.preview_panel:
            self.preview_panel.setVisible(True)
        # Give more space to preview
        if self.main_splitter:
            self.main_splitter.setSizes([750, 250])
        if self.left_splitter:
            self.left_splitter.setSizes([350, 450])

    def _create_settings_panel(self) -> QWidget:
        """Create the settings panel with collapsible sections."""
        from renderkit.ui.collapsible_group import CollapsibleGroupBox

        panel = QWidget()
        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area for collapsible sections
        from renderkit.ui.qt_compat import QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Container for all collapsible sections
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(5, 5, 5, 5)
        container_layout.setSpacing(8)

        # Input Sequence Section (includes color space)
        input_section = CollapsibleGroupBox("Input Sequence")
        input_section.set_content_layout(self._create_input_sequence_content())
        container_layout.addWidget(input_section)

        # Output Settings Section
        output_section = CollapsibleGroupBox("Output Settings")
        output_section.set_content_layout(self._create_output_content())
        output_section.set_collapsed(True)
        container_layout.addWidget(output_section)

        # Burn-in Overlays Section
        burnin_section = CollapsibleGroupBox("Burn-in Overlays")
        burnin_section.set_content_layout(self._create_burnin_content())
        burnin_section.set_collapsed(True)
        container_layout.addWidget(burnin_section)

        # Contact Sheet Section
        cs_section = CollapsibleGroupBox("Contact Sheet")
        cs_section.set_content_layout(self._create_contact_sheet_content())
        cs_section.set_collapsed(True)
        container_layout.addWidget(cs_section)

        # Advanced Options Section (includes video encoding)
        advanced_section = CollapsibleGroupBox("Advanced Options")
        advanced_section.set_content_layout(self._create_advanced_content())
        advanced_section.set_collapsed(True)
        container_layout.addWidget(advanced_section)

        container_layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        self.reset_settings_btn = QPushButton("Reset to defaults")
        self.reset_settings_btn.setToolTip("Reset settings panels to default values.")
        reset_layout.addWidget(self.reset_settings_btn)
        main_layout.addLayout(reset_layout)

        return panel

    def _create_input_sequence_content(self) -> QVBoxLayout:
        """Create content for input sequence section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        # Input pattern
        input_pattern_layout = QHBoxLayout()
        self.input_pattern_combo = NoWheelComboBox()
        self.input_pattern_combo.setEditable(True)
        insert_policy = getattr(QComboBox, "InsertPolicy", None)
        if insert_policy is not None:
            self.input_pattern_combo.setInsertPolicy(insert_policy.NoInsert)
        else:
            self.input_pattern_combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = self.input_pattern_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("e.g., render.%04d.exr or render.####.exr")
        self.input_pattern_combo.setToolTip("Enter a pattern or pick a recent one.")
        self.input_pattern_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_pattern_combo.setMinimumWidth(0)
        input_pattern_layout.addWidget(self.input_pattern_combo)
        self.browse_input_btn = QPushButton("Browse")
        self.browse_input_btn.setMaximumWidth(100)
        self.browse_input_btn.setIcon(icon_manager.get_icon("browse"))
        input_pattern_layout.addWidget(self.browse_input_btn)
        input_pattern_layout.setStretch(0, 1)
        input_pattern_layout.setStretch(1, 0)
        form_layout.addRow("Pattern:", input_pattern_layout)

        # Frame Range
        frame_range_layout = QHBoxLayout()
        self.start_frame_spin = NoWheelSpinBox()
        self.start_frame_spin.setMinimum(0)
        self.start_frame_spin.setMaximum(999999)
        self.start_frame_spin.setSpecialValueText("Auto")
        self.start_frame_spin.setValue(0)
        frame_range_layout.addWidget(QLabel("Start:"))
        frame_range_layout.addWidget(self.start_frame_spin)

        self.end_frame_spin = NoWheelSpinBox()
        self.end_frame_spin.setMinimum(0)
        self.end_frame_spin.setMaximum(999999)
        self.end_frame_spin.setSpecialValueText("Auto")
        self.end_frame_spin.setValue(0)
        frame_range_layout.addWidget(QLabel("End:"))
        frame_range_layout.addWidget(self.end_frame_spin)
        frame_range_layout.addStretch()
        form_layout.addRow("Frame Range:", frame_range_layout)

        # Sequence Info
        self.sequence_info_label = QLabel("No sequence detected")
        self.sequence_info_label.setWordWrap(True)
        self.sequence_info_label.setMinimumHeight(40)
        form_layout.addRow("Info:", self.sequence_info_label)

        # Layer Selection
        self.layer_combo = NoWheelComboBox()
        self.layer_combo.addItems(["RGBA"])
        self.layer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layer_combo.setMinimumWidth(0)
        self.layer_combo.setEnabled(False)
        self.layer_combo.setToolTip("Select EXR layer (AOV) to process.")
        form_layout.addRow("Layer:", self.layer_combo)

        layout.addLayout(form_layout)

        # Color Space (merged from separate section)
        color_form = QFormLayout()
        color_form.setSpacing(10)
        self._set_form_growth_policy(color_form)

        self.color_space_combo = NoWheelComboBox()
        self.color_space_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.color_space_combo.setMinimumWidth(0)
        self.color_space_combo.setEditable(True)
        self.color_space_combo.setEditable(False)
        self._populate_color_space_combo(self.color_space_combo)
        self.color_space_combo.setToolTip("Select input color space. Output is always sRGB.")
        color_form.addRow("Color Space:", self.color_space_combo)

        layout.addLayout(color_form)

        # Preview button
        return layout

    def _create_output_content(self) -> QVBoxLayout:
        """Create content for output settings section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        # Output path
        output_path_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output video file...")
        self.output_path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.output_path_edit.setMinimumWidth(0)
        output_path_layout.addWidget(self.output_path_edit)
        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.setMaximumWidth(100)
        self.browse_output_btn.setIcon(icon_manager.get_icon("browse"))
        output_path_layout.addWidget(self.browse_output_btn)
        output_path_layout.setStretch(0, 1)
        output_path_layout.setStretch(1, 0)
        form_layout.addRow("Output Path:", output_path_layout)

        layout.addLayout(form_layout)

        if not hasattr(self, "play_btn") or self.play_btn is None:
            self.play_btn = QPushButton("Play Result (Flipbook)")
            self.play_btn.setEnabled(False)
            self.play_btn.clicked.connect(self._play_output)
            self.play_btn.setToolTip("Open the conversion result in the default system player.")
            self.play_btn.setObjectName("IconButton")
            self.play_btn.setIcon(icon_manager.get_icon("play"))
        layout.addWidget(self.play_btn)

        return layout

    def _create_input_tab(self) -> QWidget:
        """Create input settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Input Pattern Group
        input_group = QGroupBox("Input Sequence")
        input_layout = QFormLayout(input_group)
        input_layout.setSpacing(10)
        self._set_form_growth_policy(input_layout)
        input_layout.setContentsMargins(12, 18, 12, 12)

        # Input pattern
        input_pattern_layout = QHBoxLayout()
        self.input_pattern_combo = NoWheelComboBox()
        self.input_pattern_combo.setEditable(True)
        insert_policy = getattr(QComboBox, "InsertPolicy", None)
        if insert_policy is not None:
            self.input_pattern_combo.setInsertPolicy(insert_policy.NoInsert)
        else:
            self.input_pattern_combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = self.input_pattern_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("e.g., render.%04d.exr or render.####.exr")
        self.input_pattern_combo.setToolTip("Enter a pattern or pick a recent one.")
        self.input_pattern_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_pattern_combo.setMinimumWidth(0)
        input_pattern_layout.addWidget(self.input_pattern_combo)
        self.browse_input_btn = QPushButton("Browse")
        self.browse_input_btn.setMaximumWidth(100)
        input_pattern_layout.addWidget(self.browse_input_btn)
        input_pattern_layout.setStretch(0, 1)
        input_pattern_layout.setStretch(1, 0)
        input_layout.addRow("Pattern:", input_pattern_layout)

        # Frame Range
        frame_range_layout = QHBoxLayout()
        self.start_frame_spin = NoWheelSpinBox()
        self.start_frame_spin.setMinimum(0)
        self.start_frame_spin.setMaximum(999999)
        self.start_frame_spin.setSpecialValueText("Auto")
        self.start_frame_spin.setValue(0)
        frame_range_layout.addWidget(QLabel("Start:"))
        frame_range_layout.addWidget(self.start_frame_spin)

        self.end_frame_spin = NoWheelSpinBox()
        self.end_frame_spin.setMinimum(0)
        self.end_frame_spin.setMaximum(999999)
        self.end_frame_spin.setSpecialValueText("Auto")
        self.end_frame_spin.setValue(0)
        frame_range_layout.addWidget(QLabel("End:"))
        frame_range_layout.addWidget(self.end_frame_spin)
        frame_range_layout.addStretch()
        input_layout.addRow("Frame Range:", frame_range_layout)

        # Sequence Info
        self.sequence_info_label = QLabel("No sequence detected")
        self.sequence_info_label.setWordWrap(True)
        self.sequence_info_label.setMinimumHeight(40)
        input_layout.addRow("Info:", self.sequence_info_label)

        # Layer Selection
        self.layer_combo = NoWheelComboBox()
        self.layer_combo.addItems(["RGBA"])
        self.layer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layer_combo.setMinimumWidth(0)
        self.layer_combo.setEnabled(False)
        self.layer_combo.setToolTip("Select EXR layer (AOV) to process.")
        input_layout.addRow("Layer:", self.layer_combo)

        layout.addWidget(input_group)

        # Input Color Space Group
        color_group = QGroupBox("Input Color Space")
        color_layout = QFormLayout(color_group)
        color_layout.setSpacing(10)
        self._set_form_growth_policy(color_layout)
        color_layout.setContentsMargins(12, 18, 12, 12)

        self.color_space_combo = NoWheelComboBox()
        self.color_space_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.color_space_combo.setMinimumWidth(0)
        self.color_space_combo.setEditable(True)  # Allow custom input space names
        self.color_space_combo.setEditable(False)
        self._populate_color_space_combo(self.color_space_combo)
        self.color_space_combo.setToolTip("Select input color space. Output is always sRGB.")
        color_layout.addRow("Input Space:", self.color_space_combo)

        layout.addWidget(color_group)

        # Preview button
        if not hasattr(self, "load_preview_btn") or self.load_preview_btn is None:
            self.load_preview_btn = QPushButton("Load Preview")
            self.load_preview_btn.clicked.connect(self._load_preview)
            self.load_preview_btn.setIcon(icon_manager.get_icon("preview"))

        layout.addStretch()

        return widget

    def _create_output_tab(self) -> QWidget:
        """Create output settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Output File Group
        output_group = QGroupBox("Output File")
        output_layout = QFormLayout(output_group)
        output_layout.setSpacing(10)
        self._set_form_growth_policy(output_layout)
        output_layout.setContentsMargins(12, 18, 12, 12)

        # Output path
        output_path_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output video file...")
        self.output_path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.output_path_edit.setMinimumWidth(0)
        output_path_layout.addWidget(self.output_path_edit)
        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.setMaximumWidth(100)
        output_path_layout.addWidget(self.browse_output_btn)
        output_path_layout.setStretch(0, 1)
        output_path_layout.setStretch(1, 0)
        output_layout.addRow("Output Path:", output_path_layout)

        layout.addWidget(output_group)

        # Video Settings Group
        video_group = QGroupBox("Video Settings")
        video_layout = QFormLayout(video_group)
        video_layout.setSpacing(10)
        self._set_form_growth_policy(video_layout)
        video_layout.setContentsMargins(12, 18, 12, 12)

        # FPS
        self.fps_spin = NoWheelDoubleSpinBox()
        self.fps_spin.setRange(0.01, 120.0)
        self.fps_spin.setDecimals(3)
        self.fps_spin.setValue(24.0)
        self.fps_spin.setSuffix(" fps")
        video_layout.addRow("Frame Rate:", self.fps_spin)

        # Resolution
        resolution_layout = QHBoxLayout()
        self.keep_resolution_check = QCheckBox("Keep source resolution")
        self.keep_resolution_check.setChecked(True)
        self.keep_resolution_check.toggled.connect(self._on_keep_resolution_toggled)
        resolution_layout.addWidget(self.keep_resolution_check)

        self.width_spin = NoWheelSpinBox()
        self.width_spin.setMinimum(1)
        self.width_spin.setMaximum(7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Width:"))
        resolution_layout.addWidget(self.width_spin)

        self.height_spin = NoWheelSpinBox()
        self.height_spin.setMinimum(1)
        self.height_spin.setMaximum(4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Height:"))
        resolution_layout.addWidget(self.height_spin)

        resolution_layout.addStretch()
        video_layout.addRow("Resolution:", resolution_layout)

        # Codec - detect available codecs
        self.codec_combo = NoWheelComboBox()
        self._populate_codecs()
        video_layout.addRow("Codec:", self.codec_combo)

        # Quality Slider
        quality_layout = QHBoxLayout()
        self.quality_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(0, 10)
        self.quality_slider.setValue(10)
        self.quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.quality_slider.setTickInterval(1)
        self.quality_slider.setToolTip("Quality (0-10), 10 is best (visually lossless).")

        self.quality_label = QLabel("10 (Max)")
        self.quality_label.setFixedWidth(60)

        quality_layout.addWidget(self.quality_slider)
        quality_layout.addWidget(self.quality_label)
        quality_layout.setStretch(0, 1)
        quality_layout.setStretch(1, 0)
        video_layout.addRow("Visual Quality:", quality_layout)

        layout.addWidget(video_group)
        layout.addStretch()

        return widget

    def _create_burnin_tab(self) -> QWidget:
        """Create burn-in settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Basic Burn-ins Group
        burnin_group = QGroupBox("Basic Overlays")
        burnin_layout = QVBoxLayout(burnin_group)
        burnin_layout.setSpacing(10)

        self.burnin_enable_check = QCheckBox("Enable Burn-ins")
        self.burnin_enable_check.setToolTip("Enable or disable all burn-in overlays")
        self.burnin_enable_check.setStyleSheet("font-weight: bold;")
        self.burnin_enable_check.toggled.connect(self._on_burnin_enable_toggled)
        burnin_layout.addWidget(self.burnin_enable_check)

        self.burnin_frame_check = QCheckBox("Frame Number")
        self.burnin_frame_check.setToolTip("Overlay the current frame number (top-left)")
        burnin_layout.addWidget(self.burnin_frame_check)

        self.burnin_layer_check = QCheckBox("EXR Layer Name")
        self.burnin_layer_check.setToolTip("Overlay the active EXR layer name (top-left)")
        burnin_layout.addWidget(self.burnin_layer_check)

        self.burnin_fps_check = QCheckBox("Frame Rate (FPS)")
        self.burnin_fps_check.setToolTip("Overlay the video frame rate (top-left)")
        burnin_layout.addWidget(self.burnin_fps_check)

        # Opacity
        self.burnin_opacity_layout = QHBoxLayout()
        self.burnin_opacity_layout.addWidget(QLabel("Background Opacity:"))
        self.burnin_opacity_spin = NoWheelSpinBox()
        self.burnin_opacity_spin.setRange(0, 100)
        self.burnin_opacity_spin.setValue(30)
        self.burnin_opacity_spin.setSuffix("%")
        self.burnin_opacity_layout.addWidget(self.burnin_opacity_spin)
        self.burnin_opacity_layout.addStretch()
        burnin_layout.addLayout(self.burnin_opacity_layout)

        layout.addWidget(burnin_group)
        layout.addStretch()

        return widget

    def _create_contact_sheet_tab(self) -> QWidget:
        """Create contact sheet settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Grid Group
        grid_group = QGroupBox("Grid Layout")
        grid_layout = QFormLayout(grid_group)
        grid_layout.setSpacing(10)
        self._set_form_growth_policy(grid_layout)

        self.cs_enable_check = QCheckBox("Enable Contact Sheet")
        self.cs_enable_check.setToolTip("Enable or disable contact sheet generation")
        self.cs_enable_check.setStyleSheet("font-weight: bold;")
        self.cs_enable_check.toggled.connect(self._on_cs_enable_toggled)
        grid_layout.addRow(self.cs_enable_check)

        self.cs_columns_spin = NoWheelSpinBox()
        self.cs_columns_spin.setRange(1, 20)
        self.cs_columns_spin.setValue(4)
        grid_layout.addRow("Columns:", self.cs_columns_spin)

        self.cs_thumb_width_spin = NoWheelSpinBox()
        self.cs_thumb_width_spin.setRange(128, 4096)
        self.cs_thumb_width_spin.setValue(512)
        self.cs_thumb_width_spin.setSuffix(" px")
        grid_layout.addRow("Thumbnail Width:", self.cs_thumb_width_spin)

        self.cs_padding_spin = NoWheelSpinBox()
        self.cs_padding_spin.setRange(0, 100)
        self.cs_padding_spin.setValue(4)
        self.cs_padding_spin.setSuffix(" px")
        grid_layout.addRow("Padding:", self.cs_padding_spin)

        layout.addWidget(grid_group)

        # Labels Group
        labels_group = QGroupBox("Labels")
        labels_layout = QFormLayout(labels_group)
        self._set_form_growth_policy(labels_layout)

        self.cs_show_labels_check = QCheckBox("Show filename labels")
        self.cs_show_labels_check.setChecked(True)
        labels_layout.addRow("Enable Labels:", self.cs_show_labels_check)

        self.cs_font_size_spin = NoWheelSpinBox()
        self.cs_font_size_spin.setRange(6, 48)
        self.cs_font_size_spin.setValue(12)
        labels_layout.addRow("Font Size:", self.cs_font_size_spin)

        layout.addWidget(labels_group)

        layout.addStretch()
        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create advanced settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # Performance Group
        perf_group = QGroupBox("Performance")
        perf_layout = QFormLayout(perf_group)
        perf_layout.setSpacing(10)
        self._set_form_growth_policy(perf_layout)

        self.multiprocessing_check = QCheckBox("Enable multiprocessing")
        self.multiprocessing_check.setToolTip("Use multiple CPU cores for faster processing")
        perf_layout.addRow("Multiprocessing:", self.multiprocessing_check)

        self.num_workers_spin = NoWheelSpinBox()
        self.num_workers_spin.setMinimum(1)
        self.num_workers_spin.setMaximum(32)
        self.num_workers_spin.setValue(4)
        self.num_workers_spin.setSuffix(" workers")
        self.num_workers_spin.setEnabled(False)
        self.multiprocessing_check.toggled.connect(self.num_workers_spin.setEnabled)
        perf_layout.addRow("Workers:", self.num_workers_spin)

        layout.addWidget(perf_group)

        # Options Group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self.overwrite_check = QCheckBox("Overwrite existing output file")
        self.overwrite_check.setChecked(True)  # Default to checked
        options_layout.addWidget(self.overwrite_check)

        layout.addWidget(options_group)
        layout.addStretch()

        return widget

    def _create_log_panel(self) -> QWidget:
        """Create log and progress panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Progress Group
        progress_group = QGroupBox()
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(10)

        progress_header = QHBoxLayout()
        self.progress_status_icon = QLabel()
        self.progress_status_icon.setFixedSize(16, 16)
        self.progress_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_title = QLabel("Progress")
        progress_title.setStyleSheet("font-weight: 600;")
        progress_header.addWidget(self.progress_status_icon)
        progress_header.addWidget(progress_title)
        progress_header.addStretch()
        progress_layout.addLayout(progress_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_play_btn = QPushButton()
        self.progress_play_btn.setFixedSize(22, 22)
        self.progress_play_btn.setIcon(icon_manager.get_icon("play"))
        self.progress_play_btn.setIconSize(QSize(14, 14))
        self.progress_play_btn.setToolTip("Play output")
        self.progress_play_btn.setVisible(False)
        self.progress_play_btn.clicked.connect(self._play_output)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        status_layout.addStretch()
        status_layout.addWidget(self.progress_label)
        status_layout.addWidget(self.progress_play_btn)
        status_layout.addStretch()
        progress_layout.addLayout(status_layout)

        layout.addWidget(progress_group)

        # Log Group
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(5, 5, 5, 5)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumBlockCount(1000)  # Limit log lines
        self.log_text.setObjectName("LogBox")
        log_layout.addWidget(self.log_text)

        # Clear log button
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.log_text.clear)
        clear_log_btn.setIcon(icon_manager.get_icon("close"))
        log_layout.addWidget(clear_log_btn)

        layout.addWidget(log_group)

        self._set_status_icons("idle")

        return panel

    def _create_preview_panel(self) -> QWidget:
        """Create preview panel."""
        panel = QWidget()
        panel.setMinimumHeight(180)
        panel.setMaximumHeight(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(5, 5, 5, 5)

        self.preview_widget = PreviewWidget()
        preview_layout.addWidget(self.preview_widget)

        layout.addWidget(preview_group)
        return panel

    def _create_action_panel(self) -> QWidget:
        """Create action buttons panel."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 5, 10, 5)  # Reduced vertical margins
        layout.setSpacing(10)

        layout.addStretch()

        self.convert_hint_label = QLabel("")
        self.convert_hint_label.setObjectName("InlineHint")
        self.convert_hint_label.setStyleSheet("color: #9aa4ad; font-size: 11px;")
        self.convert_hint_label.setVisible(False)
        layout.addWidget(self.convert_hint_label)

        # Convert button
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setMinimumWidth(150)
        self.convert_btn.setObjectName("PrimaryButton")
        self.convert_btn.setIcon(icon_manager.get_icon("convert"))
        layout.addWidget(self.convert_btn)

        # Cancel button
        self.cancel_btn = QPushButton("Quit")
        self.cancel_btn.setEnabled(True)  # Always enabled
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setIcon(icon_manager.get_icon("close"))
        layout.addWidget(self.cancel_btn)

        return panel

    def _create_menu_bar(self) -> None:
        """Create menu bar with Help menu."""
        menubar = self.menuBar()

        # Help menu
        help_menu = menubar.addMenu("Help")

        # About action
        about_action = help_menu.addAction("About")
        about_action.setIcon(icon_manager.get_icon("help"))
        about_action.triggered.connect(self._show_about)
        about_action.setShortcut("F1")

    def _show_about(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>RenderKit - Render Kit</h2>
        <p><b>Version:</b> {__version__}</p>
        <p><b>Qt Backend:</b> {QT_BACKEND_NAME}</p>
        <p>A high-performance Python package for image and video processing in VFX workflows.</p>
        <p>Designed for converting image sequences (EXR, PNG, JPEG) to video formats (MP4) with proper color space handling.</p>
        <hr>
        <p><b>Author:</b> Ahmed Hindy</p>
        <p><b>License:</b> MIT</p>
        <p><b>Repository:</b> <a href="https://github.com/Ahmed-Hindy/renderkit">GitHub</a></p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle("About RenderKit")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(about_text)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.exec()

    def _populate_codecs(self) -> None:
        """Populate codec combo box with standard FFmpeg codecs."""
        # Codecs supported by the bundled FFmpeg build.
        codecs = [
            ("libx264", "H.264 (AVC) - Default"),
            ("libx265", "H.265 (HEVC)"),
            ("libaom-av1", "AV1 - Maximum Compression"),
        ]

        available_codecs = []
        self._codec_map = {}

        for i, (codec_id, codec_label) in enumerate(codecs):
            available_codecs.append(codec_label)
            self._codec_map[i] = codec_id

        self.codec_combo.clear()
        self.codec_combo.addItems(available_codecs)
        self.codec_combo.setCurrentIndex(0)

    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self.browse_input_btn.clicked.connect(self._browse_input_pattern)
        self.browse_output_btn.clicked.connect(self._browse_output_path)
        self.cancel_btn.clicked.connect(self._cancel_conversion)
        line_edit = self.input_pattern_combo.lineEdit()
        if line_edit is not None:
            line_edit.textChanged.connect(self._on_pattern_changed)
            line_edit.editingFinished.connect(self._detect_sequence)
        self.input_pattern_combo.activated.connect(self._on_recent_pattern_selected)
        self.output_path_edit.textChanged.connect(self._update_play_button_state)
        self.color_space_combo.currentIndexChanged.connect(self._on_color_space_changed)
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)
        self.reset_settings_btn.clicked.connect(self._reset_settings_to_defaults)
        self._set_convert_button_state(False)
        self._update_output_path_validation()

        # Keyboard shortcuts
        self.convert_btn.setShortcut("Ctrl+Return")

    def _set_convert_button_state(self, is_converting: bool) -> None:
        if is_converting:
            self.convert_btn.setText("Cancel")
            self.convert_btn.setIcon(icon_manager.get_icon("close"))
            self.convert_btn.setToolTip("Cancel the running conversion.")
            if self._convert_btn_handler != "cancel":
                if self._convert_btn_handler == "start":
                    try:
                        self.convert_btn.clicked.disconnect(self._start_conversion)
                    except TypeError:
                        pass
                self.convert_btn.clicked.connect(self._cancel_conversion)
                self._convert_btn_handler = "cancel"
            return

        self.convert_btn.setText("Convert")
        self.convert_btn.setIcon(icon_manager.get_icon("convert"))
        self.convert_btn.setToolTip("Start conversion.")
        if self._convert_btn_handler != "start":
            if self._convert_btn_handler == "cancel":
                try:
                    self.convert_btn.clicked.disconnect(self._cancel_conversion)
                except TypeError:
                    pass
            self.convert_btn.clicked.connect(self._start_conversion)
            self._convert_btn_handler = "start"
        self._update_convert_gate()

    def _load_recent_patterns(self) -> None:
        recent = self.settings.value(RECENT_PATTERNS_KEY, [], type=list)
        if recent is None:
            recent_list = []
        elif isinstance(recent, str):
            recent_list = [recent]
        else:
            recent_list = list(recent)

        self._recent_patterns = [
            pattern.strip()
            for pattern in recent_list
            if isinstance(pattern, str) and pattern.strip()
        ]
        self._refresh_recent_patterns_combo()

    def _save_recent_patterns(self) -> None:
        self.settings.setValue(RECENT_PATTERNS_KEY, self._recent_patterns)

    def _refresh_recent_patterns_combo(self) -> None:
        if not hasattr(self, "input_pattern_combo"):
            return

        current_text = self.input_pattern_combo.currentText()
        self.input_pattern_combo.blockSignals(True)
        self.input_pattern_combo.clear()

        for pattern in self._recent_patterns:
            self.input_pattern_combo.addItem(pattern)

        if self._recent_patterns:
            self.input_pattern_combo.addItem(RECENT_PATTERNS_CLEAR_LABEL)

        self.input_pattern_combo.setCurrentIndex(-1)
        self.input_pattern_combo.setEditText(current_text)
        self.input_pattern_combo.blockSignals(False)

    def _add_recent_pattern(self, pattern: str) -> None:
        cleaned = pattern.strip()
        if not cleaned:
            return

        if cleaned in self._recent_patterns:
            self._recent_patterns.remove(cleaned)
        self._recent_patterns.insert(0, cleaned)
        self._recent_patterns = self._recent_patterns[:RECENT_PATTERNS_LIMIT]
        self._save_recent_patterns()
        self._refresh_recent_patterns_combo()

    def _clear_recent_patterns(self) -> None:
        self._recent_patterns = []
        self._save_recent_patterns()
        self._refresh_recent_patterns_combo()
        self.statusBar().showMessage("Recent patterns cleared", 3000)

    def _on_recent_pattern_selected(self, index_or_text) -> None:
        if isinstance(index_or_text, str):
            pattern = index_or_text.strip()
        else:
            index = int(index_or_text)
            if index < 0:
                return
            pattern = self.input_pattern_combo.itemText(index).strip()
        if not pattern:
            return
        if pattern == RECENT_PATTERNS_CLEAR_LABEL:
            self._clear_recent_patterns()
            self.input_pattern_combo.setEditText(self._last_pattern_text)
            return

        self.input_pattern_combo.setEditText(pattern)
        self._detect_sequence()

    def _set_output_validation_state(self, is_valid: Optional[bool], message: str) -> None:
        if not hasattr(self, "output_path_edit"):
            return

        if is_valid is None:
            self.output_path_edit.setStyleSheet("")
            self.output_path_edit.setToolTip("")
            return

        if is_valid:
            self.output_path_edit.setStyleSheet(
                "border: 1px solid #4CAF50; padding: 6px 10px; border-radius: 6px;"
            )
            self.output_path_edit.setToolTip(message or "Output path looks valid.")
            return

        self.output_path_edit.setStyleSheet(
            "border: 1px solid #f44336; padding: 6px 10px; border-radius: 6px;"
        )
        self.output_path_edit.setToolTip(message)

    def _set_input_validation_state(self, is_valid: Optional[bool], message: str) -> None:
        if not hasattr(self, "input_pattern_combo"):
            return

        if is_valid is None:
            self.input_pattern_combo.setProperty("validationState", "")
            self.input_pattern_combo.setToolTip("")
            line_edit = self.input_pattern_combo.lineEdit()
            if line_edit is not None:
                line_edit.setToolTip("")
            self.input_pattern_combo.style().unpolish(self.input_pattern_combo)
            self.input_pattern_combo.style().polish(self.input_pattern_combo)
            return

        state = "valid" if is_valid else "invalid"
        self.input_pattern_combo.setProperty("validationState", state)
        tooltip = message or "Input pattern looks valid."
        self.input_pattern_combo.setToolTip(tooltip)
        line_edit = self.input_pattern_combo.lineEdit()
        if line_edit is not None:
            line_edit.setToolTip(tooltip)
        self.input_pattern_combo.style().unpolish(self.input_pattern_combo)
        self.input_pattern_combo.style().polish(self.input_pattern_combo)

    def _get_theme_name(self) -> str:
        theme = self.property("theme")
        if isinstance(theme, str) and theme:
            return theme
        return "dark"

    def _get_status_color(self, status: str) -> str:
        theme = self._get_theme_name()
        if theme == "light":
            colors = {
                "idle": "#656d76",
                "running": "#0969da",
                "success": "#1a7f37",
                "error": "#d1242f",
                "cancelled": "#9a6700",
            }
        else:
            colors = {
                "idle": "#848d97",
                "running": "#4493f8",
                "success": "#3fb950",
                "error": "#f85149",
                "cancelled": "#d29922",
            }
        return colors.get(status, colors["idle"])

    def _set_status_icons(self, status: str) -> None:
        if not hasattr(self, "progress_status_icon"):
            return

        icon_map = {
            "idle": "info",
            "running": "loader",
            "success": "check",
            "error": "error",
            "cancelled": "warning",
        }
        icon_name = icon_map.get(status, "info")
        color = self._get_status_color(status)
        icon = icon_manager.get_icon(icon_name, color=color, size=16)
        pixmap = icon.pixmap(16, 16)
        self.progress_status_icon.setPixmap(pixmap)

    def _update_output_path_validation(self) -> None:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            self._set_output_validation_state(None, "")
            self._update_convert_gate()
            return

        is_valid, error_msg = FileUtils.validate_output_filename(output_path)
        if is_valid:
            self._set_output_validation_state(True, "Output path looks valid.")
        else:
            self._set_output_validation_state(False, error_msg)
        self._update_convert_gate()

    def _is_output_path_valid(self) -> bool:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            return False
        is_valid, _ = FileUtils.validate_output_filename(output_path)
        return is_valid

    def _update_convert_gate(self) -> None:
        if not hasattr(self, "convert_btn"):
            return

        if self._convert_btn_handler == "cancel":
            self.convert_btn.setEnabled(True)
            if hasattr(self, "convert_hint_label"):
                self.convert_hint_label.setVisible(False)
            return

        input_valid = self._input_pattern_valid
        output_valid = self._is_output_path_valid()
        enabled = input_valid and output_valid
        self.convert_btn.setEnabled(enabled)

        if not hasattr(self, "convert_hint_label"):
            return

        if enabled:
            self.convert_hint_label.setVisible(False)
            self.convert_hint_label.setText("")
            return

        missing = []
        if not output_valid:
            missing.append("output path")
        if self._input_pattern_validated and not input_valid:
            missing.append("input pattern")
        hint = "Enter a valid " + " and ".join(missing) + " to enable Convert."
        self.convert_hint_label.setText(hint)
        self.convert_hint_label.setVisible(bool(missing))

    def _reset_settings_to_defaults(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Reset settings panels to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.fps_spin.setValue(24)
        self.width_spin.setValue(1920)
        self.height_spin.setValue(1080)
        self.codec_combo.setCurrentIndex(0)
        self.keep_resolution_check.setChecked(True)
        self.quality_slider.setValue(10)
        self.multiprocessing_check.setChecked(False)
        self.num_workers_spin.setValue(4)

        self.burnin_enable_check.setChecked(True)
        self.burnin_frame_check.setChecked(True)
        self.burnin_layer_check.setChecked(True)
        self.burnin_fps_check.setChecked(True)
        self.burnin_opacity_spin.setValue(30)

        self.cs_enable_check.setChecked(False)
        self.cs_columns_spin.setValue(4)
        self.cs_thumb_width_spin.setValue(512)
        self.cs_padding_spin.setValue(4)
        self.cs_show_labels_check.setChecked(True)
        self.cs_font_size_spin.setValue(12)
        if hasattr(self, "overwrite_check"):
            self.overwrite_check.setChecked(True)

        self._save_settings()
        self.statusBar().showMessage("Settings reset to defaults", 3000)

    def _on_keep_resolution_toggled(self, checked: bool) -> None:
        """Handle keep resolution checkbox toggle."""
        self.width_spin.setEnabled(not checked)
        self.height_spin.setEnabled(not checked)

    def _on_burnin_enable_toggled(self, checked: bool) -> None:
        """Handle burn-in enable checkbox toggle."""
        self.burnin_frame_check.setEnabled(checked)
        self.burnin_layer_check.setEnabled(checked)
        self.burnin_fps_check.setEnabled(checked)
        self.burnin_opacity_spin.setEnabled(checked)

    def _on_cs_enable_toggled(self, checked: bool) -> None:
        """Handle contact sheet enable checkbox toggle."""
        self.cs_columns_spin.setEnabled(checked)
        self.cs_thumb_width_spin.setEnabled(checked)
        self.cs_padding_spin.setEnabled(checked)
        self.cs_show_labels_check.setEnabled(checked)
        self.cs_font_size_spin.setEnabled(checked)

    def _on_quality_changed(self, value: int) -> None:
        """Handle quality slider change."""
        labels = {
            0: "0 (Min)",
            1: "1",
            2: "2",
            3: "3",
            4: "4",
            5: "5 (Med)",
            6: "6",
            7: "7",
            8: "8 (VFX)",
            9: "9",
            10: "10 (Max)",
        }
        self.quality_label.setText(labels.get(value, str(value)))

    def _update_play_button_state(self) -> None:
        """Enable or disable play button based on output file existence."""
        self._update_output_path_validation()
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            self.play_btn.setEnabled(False)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(False)
            return

        try:
            path = Path(output_path)
            enabled = path.exists() and path.is_file()
            self.play_btn.setEnabled(enabled)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(enabled)
        except Exception:
            self.play_btn.setEnabled(False)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(False)

    def _pattern_has_frame_token(self, filename: str) -> bool:
        if "%" in filename:
            percent_index = filename.find("%")
            i = percent_index + 1
            while i < len(filename) and filename[i].isdigit():
                i += 1
            if i < len(filename) and filename[i] == "d":
                return True

        if "$F" in filename:
            return True

        if "#" in filename:
            return True

        stem = Path(filename).stem
        if not stem:
            return False
        i = len(stem) - 1
        while i >= 0 and stem[i].isdigit():
            i -= 1
        return i < len(stem) - 1

    def _validate_input_pattern(self, pattern: str) -> tuple[bool, str]:
        if not pattern:
            return False, "No pattern specified."

        pattern_path = Path(pattern)
        if pattern_path.exists() and pattern_path.is_dir():
            return False, "Pattern must include a filename, not just a folder."

        filename = pattern_path.name
        if not filename:
            return False, "Pattern must include a filename."

        suffix = pattern_path.suffix.lower().lstrip(".")
        if not suffix:
            return False, "Pattern must include an image extension (e.g., .exr)."
        if suffix not in constants.OIIO_SUPPORTED_EXTENSIONS:
            return False, f"Unsupported image extension: .{suffix}"

        if not self._pattern_has_frame_token(filename):
            return (
                False,
                "Pattern must include a frame token (e.g., %04d, ####, $F4) or frame number.",
            )

        return True, ""

    def _on_pattern_changed(self) -> None:
        """Handle input pattern text change."""
        # Clear preview when pattern changes
        self.preview_widget.clear_preview()
        self._last_pattern_text = self.input_pattern_combo.currentText()
        self._input_pattern_valid = False
        self._input_pattern_validated = False
        self._set_input_validation_state(None, "")
        self.sequence_info_label.setText("No sequence detected")
        self._update_convert_gate()

    def _on_color_space_changed(self) -> None:
        """Handle color space change."""
        # Reload preview with new color space if available
        if hasattr(self, "_last_preview_path") and self._last_preview_path:
            self._load_preview()

    def _on_layer_changed(self) -> None:
        """Handle layer selection change."""
        if hasattr(self, "_last_preview_path") and self._last_preview_path:
            self._load_preview()

    def _load_preview(self) -> None:
        """Load preview of first frame."""
        pattern = self.input_pattern_combo.currentText().strip()
        if not pattern:
            QMessageBox.warning(self, "No Pattern", "Please specify an input pattern first.")
            return

        try:
            from renderkit.core.sequence import SequenceDetector

            sequence = SequenceDetector.detect_sequence(pattern)
            first_frame_path = sequence.get_file_path(sequence.frame_numbers[0])
            self._load_preview_from_path(first_frame_path)
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", f"Could not load preview:\n{e}")
            self.log_text.appendPlainText(f"Preview error: {str(e)}")

    def _load_preview_from_path(self, sample_path: Path) -> None:
        """Load preview using an already resolved frame path."""
        if not sample_path.exists():
            QMessageBox.warning(self, "File Not Found", f"Frame file not found:\n{sample_path}")
            return

        preset, input_space = self._get_current_color_space_config()
        layer = self.layer_combo.currentText()

        self._last_preview_path = sample_path
        self.preview_widget.load_preview(sample_path, preset, input_space=input_space, layer=layer)
        self.log_text.appendPlainText(f"Loading preview: {sample_path.name} (Layer: {layer})")

    def _browse_input_pattern(self) -> None:
        """Browse for input file pattern."""
        # Try to open a file to help user construct pattern
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a Frame File (to detect pattern)",
            self.settings.value("last_input_dir", ""),
            "Image Files (*.exr *.png *.jpg *.jpeg);;All Files (*.*)",
        )
        if file_path:
            path_obj = Path(file_path)
            self.settings.setValue("last_input_dir", str(path_obj.parent))

            # Try to detect pattern from filename
            # Find the last sequence of digits before the extension
            import re

            # filename = path_obj.name
            name_part, ext = path_obj.stem, path_obj.suffix

            # Find all sequences of digits in the name part
            digit_matches = list(re.finditer(r"\d+", name_part))

            if digit_matches:
                # Get the last (rightmost) sequence of digits
                last_match = digit_matches[-1]
                frame_number = last_match.group(0)
                padding = len(frame_number)

                # Replace only the last sequence with pattern
                pattern_name = (
                    name_part[: last_match.start()]
                    + f"%0{padding}d"
                    + name_part[last_match.end() :]
                )
                pattern_filename = pattern_name + ext
                full_pattern = str(path_obj.parent / pattern_filename)

                self.input_pattern_combo.setEditText(full_pattern)
                self._detect_sequence()
            else:
                # No digits found, just use the filename as-is
                self.input_pattern_combo.setEditText(str(file_path))
                QMessageBox.information(
                    self,
                    "No Frame Number",
                    "Could not detect frame number in filename.\n"
                    "Please manually enter the pattern (e.g., render.%04d.exr)",
                )

    def _browse_output_path(self) -> None:
        """Browse for output video path."""
        default_path = self.settings.value("last_output_dir", "")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", default_path, "MP4 Files (*.mp4);;All Files (*.*)"
        )
        if file_path:
            path_obj = Path(file_path)
            # Add .mp4 if no supported extension is present
            if path_obj.suffix.lower().lstrip(".") not in constants.SUPPORTED_VIDEO_EXTENSIONS:
                file_path += ".mp4"

            self.output_path_edit.setText(file_path)
            self.settings.setValue("last_output_dir", str(Path(file_path).parent))

    def _detect_sequence(self) -> None:
        """Detect and display sequence information."""
        pattern = self.input_pattern_combo.currentText().strip()
        if not pattern:
            self.sequence_info_label.setText("No pattern specified")
            self.preview_widget.clear_preview()
            self._input_pattern_valid = False
            self._input_pattern_validated = True
            self._set_input_validation_state(None, "")
            self._update_convert_gate()
            return

        self._input_pattern_validated = True
        is_valid, message = self._validate_input_pattern(pattern)
        if not is_valid:
            self.sequence_info_label.setText(message)
            self.statusBar().showMessage(message, 3000)
            self.preview_widget.clear_preview()
            self._input_pattern_valid = False
            self._set_input_validation_state(False, message)
            self._update_convert_gate()
            return

        try:
            from renderkit.core.sequence import SequenceDetector

            sequence = SequenceDetector.detect_sequence(pattern)
            frame_count = len(sequence)
            frame_range = f"{sequence.frame_numbers[0]}-{sequence.frame_numbers[-1]}"

            info_text = (
                f"Detected {frame_count} frames\n"
                f"Frame range: {frame_range}\n"
                f"Pattern: {Path(pattern).name}"
            )
            self.sequence_info_label.setText(info_text)
            # self.sequence_info_label.setStyleSheet("color: #4CAF50; font-style: normal;")

            # Auto-set frame range if not set
            if self.start_frame_spin.value() == 0:
                self.start_frame_spin.setValue(sequence.frame_numbers[0])
            if self.end_frame_spin.value() == 0:
                self.end_frame_spin.setValue(sequence.frame_numbers[-1])

            # Auto-detect FPS from metadata
            sample_path = sequence.get_file_path(sequence.frame_numbers[0])
            self.log_text.appendPlainText(f"Checking metadata for FPS: {sample_path.name}")
            detected_fps = SequenceDetector.auto_detect_fps(
                sequence.frame_numbers, sample_path=sample_path
            )
            if detected_fps:
                self.fps_spin.setValue(detected_fps)
                self.log_text.appendPlainText(f"Auto-detected FPS from metadata: {detected_fps}")
            else:
                self.log_text.appendPlainText("No FPS metadata found in sequence.")

            # Auto-detect color space
            from renderkit.io.image_reader import ImageReaderFactory

            reader = ImageReaderFactory.create_reader(sample_path)
            detected_color_space = reader.get_metadata_color_space(sample_path)
            if detected_color_space:
                self.log_text.appendPlainText(f"Auto-detected Color Space: {detected_color_space}")

                preferred_label = resolve_ocio_role_label_for_colorspace(
                    detected_color_space,
                    preferred_roles=["rendering", "scene_linear", "compositing_linear"],
                )
                if preferred_label:
                    index = self.color_space_combo.findText(
                        preferred_label, Qt.MatchFlag.MatchExactly
                    )
                else:
                    index = self.color_space_combo.findText(
                        detected_color_space, Qt.MatchFlag.MatchContains
                    )

                if index >= 0:
                    self.color_space_combo.setCurrentIndex(index)
                else:
                    # If exact match not found, try setting text directly since it's editable
                    self.color_space_combo.setEditText(detected_color_space)
            else:
                self.log_text.appendPlainText("No specific Color Space metadata found.")

            # Detect Layers
            layers = reader.get_layers(sample_path)
            self.layer_combo.blockSignals(True)
            self.layer_combo.clear()
            self.layer_combo.addItems(layers)
            self.layer_combo.setEnabled(len(layers) > 1 or layers[0] != "RGBA")
            self.layer_combo.blockSignals(False)

            if len(layers) > 1:
                self.log_text.appendPlainText(f"Found {len(layers)} layers.")
                logger.debug(f"Found {len(layers)} layers: {', '.join(layers)}")

            self._load_preview_from_path(sample_path)

            # Auto-detect output path in same folder as input
            pattern_path = Path(pattern)
            output_dir = pattern_path.parent
            # Generate output filename from input pattern
            pattern_name = pattern_path.stem
            # Replace pattern tokens with base name
            import re

            # Remove pattern tokens (%04d, $F4, ####, etc.)
            base_name = re.sub(r"%0?\d+d", "", pattern_name)
            base_name = re.sub(r"\$F\d+", "", base_name)
            base_name = re.sub(r"#+", "", base_name)
            base_name = base_name.strip("._-")  # Clean up separators
            if not base_name:
                base_name = "output"
            output_path = output_dir / f"{base_name}.mp4"
            self.output_path_edit.setText(str(output_path))

            self.log_text.appendPlainText(f"Sequence detected: {frame_count} frames")
            self.log_text.appendPlainText(f"Auto-detected output: {output_path.name}")
            self.statusBar().showMessage(f"Sequence detected: {frame_count} frames")
            self._add_recent_pattern(pattern)
            self._input_pattern_valid = True
            self._set_input_validation_state(True, "Input pattern looks valid.")
            self._update_convert_gate()
        except Exception as e:
            error_text = f"Error: {str(e)}"
            self.sequence_info_label.setText(error_text)
            # self.sequence_info_label.setStyleSheet("color: #f44336; font-style: normal;")
            self.log_text.appendPlainText(f"Sequence detection failed: {str(e)}")
            self.statusBar().showMessage("Sequence detection failed", 3000)
            self.preview_widget.clear_preview()
            self._input_pattern_valid = False
            self._set_input_validation_state(False, error_text)
            self._update_convert_gate()

    def _get_current_color_space_config(self) -> tuple[ColorSpacePreset, Optional[str]]:
        """Determine color space preset and input space name from UI.

        Returns:
            Tuple of (ColorSpacePreset, input_space_str)
        """
        selected_text = self.color_space_combo.currentText()
        role_name = self._ocio_role_display_map.get(selected_text)
        return ColorSpacePreset.OCIO_CONVERSION, role_name or selected_text

    def _populate_color_space_combo(self, combo: QComboBox) -> None:
        combo.clear()
        role_options = get_ocio_role_display_options()
        utility_linear = get_ocio_colorspace_label("Utility - Linear - sRGB")

        if utility_linear:
            combo.addItem(utility_linear)

        if role_options:
            combo.addItems([label for label, _ in role_options])
            self._ocio_role_display_map = dict(role_options)
        else:
            self._ocio_role_display_map = {}

    def _start_conversion(self) -> None:
        """Start the conversion process."""
        # Validate inputs
        if not self.input_pattern_combo.currentText().strip():
            QMessageBox.warning(self, "Validation Error", "Please specify an input pattern.")
            return

        output_path_str = self.output_path_edit.text().strip()
        is_valid, error_msg = FileUtils.validate_output_filename(output_path_str)
        if not is_valid:
            QMessageBox.warning(self, "Validation Error", f"Invalid output path: {error_msg}")
            return

        # Check if output exists and overwrite not enabled
        output_path = Path(output_path_str).absolute()
        if output_path.exists() and not self.overwrite_check.isChecked():
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"Output file already exists:\n{output_path}\n\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # Build configuration
        try:
            config_builder = (
                ConversionConfigBuilder()
                .with_input_pattern(self.input_pattern_combo.currentText().strip())
                .with_output_path(str(output_path))
                .with_fps(float(self.fps_spin.value()))
                .with_quality(self.quality_slider.value())
                .with_layer(self.layer_combo.currentText())
            )

            # Color space
            preset, input_space = self._get_current_color_space_config()

            config_builder.with_color_space_preset(preset)
            if input_space:
                config_builder.with_explicit_input_color_space(input_space)

            # Resolution
            if not self.keep_resolution_check.isChecked():
                config_builder.with_resolution(self.width_spin.value(), self.height_spin.value())

            # Codec
            codec_index = self.codec_combo.currentIndex()
            codec_id = self._codec_map.get(codec_index, "libx264")
            available_encoders = get_available_encoders()
            resolved_codec, fallback_warning = select_available_encoder(
                codec_id, available_encoders
            )
            if available_encoders and resolved_codec not in available_encoders:
                available = ", ".join(sorted(available_encoders))
                QMessageBox.critical(
                    self,
                    "Encoder Unavailable",
                    (
                        f"Requested encoder '{codec_id}' is not available.\n\n"
                        f"Available encoders: {available}"
                    ),
                )
                return
            if fallback_warning:
                QMessageBox.warning(
                    self,
                    "Encoder Unavailable",
                    f"{fallback_warning}\n\nUsing '{resolved_codec}' for this conversion.",
                )
                self.log_text.appendPlainText(f"WARNING: {fallback_warning}")
                for idx, mapped_codec in self._codec_map.items():
                    if mapped_codec == resolved_codec:
                        self.codec_combo.setCurrentIndex(idx)
                        break
            config_builder.with_codec(resolved_codec)

            # Frame range
            start_frame = self.start_frame_spin.value()
            end_frame = self.end_frame_spin.value()
            if start_frame > 0 and end_frame > 0 and end_frame >= start_frame:
                config_builder.with_frame_range(start_frame, end_frame)

            # Multiprocessing
            if self.multiprocessing_check.isChecked():
                num_workers = self.num_workers_spin.value()
                config_builder.with_multiprocessing(True, num_workers)

            # Contact Sheet Mode
            if self.cs_enable_check.isChecked():
                cs_config = ContactSheetConfig(
                    columns=self.cs_columns_spin.value(),
                    thumbnail_width=self.cs_thumb_width_spin.value(),
                    padding=self.cs_padding_spin.value(),
                    show_labels=self.cs_show_labels_check.isChecked(),
                    font_size=self.cs_font_size_spin.value(),
                )
                config_builder.with_contact_sheet(True, cs_config)

            # Setup burn-ins
            burnin_elements = []
            font_size = 20
            if self.burnin_frame_check.isChecked():
                burnin_elements.append(
                    BurnInElement(
                        text_template="Frame: {frame}",
                        x=0,
                        y=10,
                        font_size=font_size,
                        alignment="left",
                    )
                )
            if self.burnin_layer_check.isChecked():
                burnin_elements.append(
                    BurnInElement(
                        text_template="Layer: {layer}",
                        x=0,
                        y=10,
                        font_size=font_size,
                        alignment="center",
                    )
                )
            if self.burnin_fps_check.isChecked():
                burnin_elements.append(
                    BurnInElement(
                        text_template="FPS: {fps:.2f}",
                        x=0,
                        y=10,
                        font_size=font_size,
                        alignment="right",
                    )
                )

            if self.burnin_enable_check.isChecked() and burnin_elements:
                config_builder.with_burnin(
                    BurnInConfig(
                        elements=burnin_elements,
                        background_opacity=self.burnin_opacity_spin.value(),
                    )
                )

            config = config_builder.build()

        except Exception as e:
            QMessageBox.critical(self, "Configuration Error", f"Error building configuration:\n{e}")
            self.log_text.appendPlainText(f"Configuration error: {str(e)}")
            return

        # Update UI
        self._set_convert_button_state(True)
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self._set_status_icons("running")
        self._is_cancelling = False
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_label.setText("Starting conversion...")
        self.statusBar().showMessage("Starting conversion...")
        self.log_text.appendPlainText("=" * 50)
        self.log_text.appendPlainText("Starting conversion...")
        self.log_text.appendPlainText(f"Input: {config.input_pattern}")
        self.log_text.appendPlainText(f"Output: {config.output_path}")

        # Reset flag
        self._conversion_finished_flag = False

        # Start worker thread
        self.worker = ConversionWorker(config)
        self.worker.finished.connect(self._on_conversion_finished)
        self.worker.error.connect(self._on_conversion_error)
        self.worker.cancelled.connect(self._on_conversion_cancelled)
        self.worker.log_message.connect(self._on_log_message)
        self.worker.progress.connect(self._on_progress_update)
        self.worker.start()

        self._save_settings()

    def _cancel_conversion(self) -> None:
        """Cancel the current conversion or quit the application."""
        if self.worker and self.worker.isRunning():
            # Cancel running conversion
            reply = QMessageBox.question(
                self,
                "Cancel Conversion",
                "Are you sure you want to cancel the conversion?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Disconnect signals to prevent double popup
                try:
                    self.worker.finished.disconnect()
                    self.worker.error.disconnect()
                    self.worker.cancelled.disconnect()
                except TypeError:
                    pass  # Already disconnected

                # Request graceful cancel
                self._is_cancelling = True
                self.progress_label.setText("Cancelling conversion...")
                self.worker.request_cancel()

                # If it doesn't stop in 2 seconds, terminate
                if not self.worker.wait(2000):
                    logger.warning("Worker did not stop gracefully, terminating...")
                    self.worker.terminate()
                    self.worker.wait()

                # Manually reset UI
                self.convert_btn.setEnabled(True)
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(0)
                self.progress_label.setText("Conversion cancelled")
                self.statusBar().showMessage("Conversion cancelled", 3000)
                self.log_text.appendPlainText("Conversion cancelled by user")
                self._set_convert_button_state(False)
                self._set_status_icons("cancelled")
                if hasattr(self, "progress_play_btn"):
                    self.progress_play_btn.setVisible(False)
        else:
            QApplication.instance().quit()

    def _on_conversion_finished(self) -> None:
        """Handle conversion completion."""
        # Prevent double popup with flag
        if self._conversion_finished_flag:
            return
        self._conversion_finished_flag = True
        self._is_cancelling = False

        # Disconnect signals to prevent multiple calls
        if self.worker:
            try:
                self.worker.finished.disconnect()
                self.worker.error.disconnect()
            except TypeError:
                pass  # Already disconnected

        self.convert_btn.setEnabled(True)
        self._set_convert_button_state(False)
        # Cancel button remains enabled (for quit)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText("Conversion completed!")
        self.statusBar().showMessage("Conversion completed successfully!", 5000)
        self.play_btn.setEnabled(True)
        self._set_status_icons("success")
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(True)
            self._update_play_button_state()

        output_path = Path(self.output_path_edit.text().strip()).absolute()
        message_box = QMessageBox(self)
        message_box.setWindowTitle("Success")
        icon_enum = getattr(QMessageBox, "Icon", None)
        info_icon = icon_enum.NoIcon if icon_enum is not None else QMessageBox.NoIcon
        message_box.setIcon(info_icon)
        theme = self.property("theme")
        if not isinstance(theme, str) or not theme:
            theme = "dark"
        check_color = "#1a7f37" if theme == "light" else "#3fb950"
        check_icon = icon_manager.get_icon("check", color=check_color, size=48)
        message_box.setIconPixmap(check_icon.pixmap(48, 48))
        message_box.setText("Conversion completed successfully!")
        message_box.setInformativeText(f"Output: {output_path}")
        role_enum = getattr(QMessageBox, "ButtonRole", None)
        action_role = role_enum.ActionRole if role_enum is not None else QMessageBox.ActionRole
        open_folder_btn = message_box.addButton("Open output folder", action_role)
        copy_path_btn = message_box.addButton("Copy output path", action_role)
        message_box.addButton(QMessageBox.StandardButton.Ok)
        message_box.exec()

        clicked_button = message_box.clickedButton()
        if clicked_button == open_folder_btn:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_path.parent)))
        elif clicked_button == copy_path_btn:
            QApplication.clipboard().setText(str(output_path))

    def _on_conversion_cancelled(self) -> None:
        """Handle conversion cancellation."""
        self._is_cancelling = False
        self.convert_btn.setEnabled(True)
        self._set_convert_button_state(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Conversion cancelled")
        self.statusBar().showMessage("Conversion cancelled", 5000)
        self.log_text.appendPlainText("Conversion cancelled")
        self._set_status_icons("cancelled")
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)

    def _on_conversion_error(self, error_msg: str) -> None:
        """Handle conversion error."""
        self._is_cancelling = False
        self.convert_btn.setEnabled(True)
        self._set_convert_button_state(False)
        # Cancel button remains enabled (for quit)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Conversion failed")
        self.statusBar().showMessage("Conversion failed", 5000)
        # Cancel button remains enabled (for quit)
        self.log_text.appendPlainText(f"ERROR: {error_msg}")
        self._set_status_icons("error")
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)

        # Determine error type for better messaging if possible
        full_msg = f"Conversion failed:\n\n{error_msg}"
        QMessageBox.critical(self, "Conversion Error", full_msg)

    def _play_output(self) -> None:
        """Play the output video file."""
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            return

        path = Path(output_path).absolute()
        if not path.exists():
            QMessageBox.warning(self, "File Not Found", f"Output file does not exist:\n{path}")
            return

        success = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if not success:
            QMessageBox.warning(
                self, "Error", f"Could not open the file with the default player:\n{path}"
            )

    def _on_log_message(self, message: str) -> None:
        """Handle log message from worker."""
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.appendPlainText(message)
        else:
            self._startup_logs.append(message)

    def _save_settings(self) -> None:
        """Save current settings."""
        self.settings.setValue("fps", self.fps_spin.value())
        self.settings.setValue("width", self.width_spin.value())
        self.settings.setValue("height", self.height_spin.value())
        self.settings.setValue("codec_text", self.codec_combo.currentText())
        self.settings.setValue("keep_resolution", self.keep_resolution_check.isChecked())
        self.settings.setValue("quality", self.quality_slider.value())
        self.settings.setValue("multiprocessing", self.multiprocessing_check.isChecked())
        self.settings.setValue("num_workers", self.num_workers_spin.value())
        self.settings.setValue("burnin_enable", self.burnin_enable_check.isChecked())
        self.settings.setValue("burnin_frame", self.burnin_frame_check.isChecked())
        self.settings.setValue("burnin_layer", self.burnin_layer_check.isChecked())
        self.settings.setValue("burnin_fps", self.burnin_fps_check.isChecked())
        self.settings.setValue("burnin_opacity", self.burnin_opacity_spin.value())

        # Contact Sheet settings
        self.settings.setValue("cs_enable", self.cs_enable_check.isChecked())
        self.settings.setValue("cs_columns", self.cs_columns_spin.value())
        self.settings.setValue("cs_thumb_width", self.cs_thumb_width_spin.value())
        self.settings.setValue("cs_padding", self.cs_padding_spin.value())
        self.settings.setValue("cs_show_labels", self.cs_show_labels_check.isChecked())
        self.settings.setValue("cs_font_size", self.cs_font_size_spin.value())

    def _on_progress_update(self, current: int, total: int) -> None:
        """Handle progress update from worker.

        Args:
            current: Current frame number (0-indexed)
            total: Total number of frames
        """
        if self._is_cancelling:
            return
        if total > 0:
            if self.progress_bar.maximum() != total:
                self.progress_bar.setRange(0, total)

            self.progress_bar.setValue(current)
            percentage = int((current / total) * 100)
            self.progress_label.setText(f"Processing frame {current}/{total} ({percentage}%)")
            self.statusBar().showMessage(f"Processing frame {current}/{total}...")

    def _load_settings(self) -> None:
        """Load saved settings."""
        self.fps_spin.setValue(self.settings.value("fps", 24, type=int))
        self.width_spin.setValue(self.settings.value("width", 1920, type=int))
        self.height_spin.setValue(self.settings.value("height", 1080, type=int))

        # Use string-based settings for better robustness across UI changes
        if self.color_space_combo.count() > 0:
            self.color_space_combo.setCurrentIndex(0)
        self.codec_combo.setCurrentText(self.settings.value("codec_text", "", type=str))

        self.keep_resolution_check.setChecked(
            self.settings.value("keep_resolution", True, type=bool)
        )
        self.quality_slider.setValue(self.settings.value("quality", 10, type=int))
        # Trigger initial toggle states
        self._on_keep_resolution_toggled(self.keep_resolution_check.isChecked())
        self._on_quality_changed(self.quality_slider.value())
        self._update_play_button_state()  # Call it here

        self.multiprocessing_check.setChecked(
            self.settings.value("multiprocessing", False, type=bool)
        )

        self.num_workers_spin.setValue(self.settings.value("num_workers", 4, type=int))

        self.burnin_enable_check.setChecked(self.settings.value("burnin_enable", True, type=bool))
        self.burnin_frame_check.setChecked(self.settings.value("burnin_frame", True, type=bool))
        self.burnin_layer_check.setChecked(self.settings.value("burnin_layer", True, type=bool))
        self.burnin_fps_check.setChecked(self.settings.value("burnin_fps", True, type=bool))
        self.burnin_opacity_spin.setValue(self.settings.value("burnin_opacity", 30, type=int))

        # Contact Sheet settings
        self.cs_enable_check.setChecked(self.settings.value("cs_enable", False, type=bool))
        self.cs_columns_spin.setValue(self.settings.value("cs_columns", 4, type=int))
        self.cs_thumb_width_spin.setValue(self.settings.value("cs_thumb_width", 512, type=int))
        self.cs_padding_spin.setValue(self.settings.value("cs_padding", 4, type=int))
        self.cs_show_labels_check.setChecked(self.settings.value("cs_show_labels", True, type=bool))
        self.cs_font_size_spin.setValue(self.settings.value("cs_font_size", 12, type=int))
        # Initial refresh of enabled states
        self._on_burnin_enable_toggled(self.burnin_enable_check.isChecked())
        self._on_cs_enable_toggled(self.cs_enable_check.isChecked())
        self._load_recent_patterns()

    def _create_burnin_content(self) -> QVBoxLayout:
        """Create content for burn-in overlays section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        self.burnin_enable_check = QCheckBox("Enable Burn-ins")
        self.burnin_enable_check.setToolTip("Enable or disable all burn-in overlays")
        self.burnin_enable_check.setStyleSheet("font-weight: bold;")
        self.burnin_enable_check.setChecked(True)
        self.burnin_enable_check.toggled.connect(self._on_burnin_enable_toggled)
        layout.addWidget(self.burnin_enable_check)

        self.burnin_frame_check = QCheckBox("Frame Number")
        self.burnin_frame_check.setToolTip("Overlay the current frame number (top-left)")
        self.burnin_frame_check.setChecked(True)
        layout.addWidget(self.burnin_frame_check)

        self.burnin_layer_check = QCheckBox("EXR Layer Name")
        self.burnin_layer_check.setToolTip("Overlay the active EXR layer name (top-left)")
        self.burnin_layer_check.setChecked(True)
        layout.addWidget(self.burnin_layer_check)

        self.burnin_fps_check = QCheckBox("Frame Rate (FPS)")
        self.burnin_fps_check.setToolTip("Overlay the video frame rate (top-left)")
        self.burnin_fps_check.setChecked(True)
        layout.addWidget(self.burnin_fps_check)

        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Background Opacity:"))
        self.burnin_opacity_spin = NoWheelSpinBox()
        self.burnin_opacity_spin.setRange(0, 100)
        self.burnin_opacity_spin.setValue(30)
        self.burnin_opacity_spin.setSuffix("%")
        opacity_layout.addWidget(self.burnin_opacity_spin)
        opacity_layout.addStretch()
        layout.addLayout(opacity_layout)

        return layout

    def _create_contact_sheet_content(self) -> QVBoxLayout:
        """Create content for contact sheet section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        self.cs_enable_check = QCheckBox("Enable Contact Sheet")
        self.cs_enable_check.setToolTip("Enable or disable contact sheet generation")
        self.cs_enable_check.setStyleSheet("font-weight: bold;")
        self.cs_enable_check.toggled.connect(self._on_cs_enable_toggled)
        form_layout.addRow(self.cs_enable_check)

        self.cs_columns_spin = NoWheelSpinBox()
        self.cs_columns_spin.setRange(1, 20)
        self.cs_columns_spin.setValue(4)
        form_layout.addRow("Columns:", self.cs_columns_spin)

        self.cs_thumb_width_spin = NoWheelSpinBox()
        self.cs_thumb_width_spin.setRange(128, 4096)
        self.cs_thumb_width_spin.setValue(512)
        self.cs_thumb_width_spin.setSuffix(" px")
        form_layout.addRow("Thumbnail Width:", self.cs_thumb_width_spin)

        self.cs_padding_spin = NoWheelSpinBox()
        self.cs_padding_spin.setRange(0, 100)
        self.cs_padding_spin.setValue(4)
        self.cs_padding_spin.setSuffix(" px")
        form_layout.addRow("Padding:", self.cs_padding_spin)

        self.cs_show_labels_check = QCheckBox("Show Layer Labels")
        self.cs_show_labels_check.setChecked(True)
        form_layout.addRow(self.cs_show_labels_check)

        self.cs_font_size_spin = NoWheelSpinBox()
        self.cs_font_size_spin.setRange(6, 72)
        self.cs_font_size_spin.setValue(12)
        self.cs_font_size_spin.setSuffix(" pt")
        form_layout.addRow("Font Size:", self.cs_font_size_spin)

        layout.addLayout(form_layout)
        return layout

    def _create_advanced_content(self) -> QVBoxLayout:
        """Create content for advanced options section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        # Video Encoding Settings (merged from separate section)
        # FPS
        self.fps_spin = NoWheelDoubleSpinBox()
        self.fps_spin.setRange(0.01, 120.0)
        self.fps_spin.setDecimals(3)
        self.fps_spin.setValue(24.0)
        self.fps_spin.setSuffix(" fps")
        form_layout.addRow("Frame Rate:", self.fps_spin)

        # Resolution
        resolution_layout = QHBoxLayout()
        self.width_spin = NoWheelSpinBox()
        self.width_spin.setMinimum(1)
        self.width_spin.setMaximum(7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Width:"))
        resolution_layout.addWidget(self.width_spin)

        self.height_spin = NoWheelSpinBox()
        self.height_spin.setMinimum(1)
        self.height_spin.setMaximum(4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Height:"))
        resolution_layout.addWidget(self.height_spin)

        self.keep_resolution_check = QCheckBox("Keep source resolution")
        self.keep_resolution_check.setChecked(True)
        self.keep_resolution_check.toggled.connect(self._on_keep_resolution_toggled)
        resolution_layout.addWidget(self.keep_resolution_check)
        resolution_layout.addStretch()
        form_layout.addRow("Resolution:", resolution_layout)

        # Codec
        self.codec_combo = NoWheelComboBox()
        self._populate_codecs()
        form_layout.addRow("Codec:", self.codec_combo)

        # Quality Slider
        quality_layout = QHBoxLayout()
        self.quality_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(0, 10)
        self.quality_slider.setValue(10)
        self.quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.quality_slider.setTickInterval(1)
        self.quality_slider.setToolTip("Quality (0-10), 10 is best (visually lossless).")

        self.quality_label = QLabel("10 (Max)")
        self.quality_label.setFixedWidth(60)

        quality_layout.addWidget(self.quality_slider)
        quality_layout.addWidget(self.quality_label)
        quality_layout.setStretch(0, 1)
        quality_layout.setStretch(1, 0)
        form_layout.addRow("Visual Quality:", quality_layout)

        # Multiprocessing Options
        self.multiprocessing_check = QCheckBox("Enable Multiprocessing")
        self.multiprocessing_check.setToolTip("Use multiple CPU cores for faster processing")
        form_layout.addRow(self.multiprocessing_check)

        self.num_workers_spin = NoWheelSpinBox()
        self.num_workers_spin.setRange(1, 32)
        self.num_workers_spin.setValue(4)
        self.num_workers_spin.setToolTip("Number of worker processes")
        form_layout.addRow("Worker Processes:", self.num_workers_spin)

        self.overwrite_check = QCheckBox("Overwrite existing files")
        self.overwrite_check.setToolTip("Automatically overwrite output files if they exist")
        self.overwrite_check.setChecked(True)
        form_layout.addRow(self.overwrite_check)

        layout.addLayout(form_layout)
        return layout


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
