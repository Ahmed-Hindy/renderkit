"""UI construction mixin for the RenderKit main window."""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path
from typing import Optional

from renderkit import __version__
from renderkit.core.config import ContactSheetConfig
from renderkit.ui.collapsible_group import CollapsibleGroupBox
from renderkit.ui.icons import icon_manager
from renderkit.ui.main_window_widgets import (
    JumpToClickSlider,
    NoWheelComboBox,
    NoWheelDoubleSpinBox,
    NoWheelSlider,
    NoWheelSpinBox,
)
from renderkit.ui.qt_compat import (
    QT_BACKEND_NAME,
    QCheckBox,
    QComboBox,
    QFont,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSize,
    QSizePolicy,
    QSlider,
    QSplitter,
    QSystemTrayIcon,
    Qt,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
    qt_enum,
)
from renderkit.ui.widgets import PreviewWidget

_MIN_WINDOW_WIDTH = 650
_MIN_WINDOW_HEIGHT = 500
_DEFAULT_WINDOW_WIDTH = 1350
_DEFAULT_WINDOW_HEIGHT = 860
_COMPACT_HEIGHT_THRESHOLD = 750
_COMFORTABLE_HEIGHT_THRESHOLD = 1000
_LOG_MAX_BLOCK_COUNT = 1000
_TIMELINE_MAX_HEIGHT = 50
_CONTACT_SHEET_DEFAULT_COLUMNS = ContactSheetConfig().columns
_CONTACT_SHEET_DEFAULT_PADDING = ContactSheetConfig().padding
_QT_ALIGN_CENTER = qt_enum("AlignmentFlag", "AlignCenter")
_QT_ALIGN_LEFT = qt_enum("AlignmentFlag", "AlignLeft")
_QT_ALIGN_RIGHT = qt_enum("AlignmentFlag", "AlignRight")
_QT_ALIGN_VCENTER = qt_enum("AlignmentFlag", "AlignVCenter")

logger = logging.getLogger("renderkit.ui.main_window")


class MainWindowUiMixin:
    """UI construction and layout helpers for RenderKit."""

    def _apply_theme(self) -> None:
        """Apply the calibrated dark/light theme from QSS file."""
        theme_name = "dark"
        self.setProperty("theme", theme_name)
        icon_manager.set_default_color("#e4e4e7" if theme_name == "dark" else "#0f172a")
        try:
            qss_text = (
                resources.files("renderkit.ui")
                .joinpath("stylesheets", "matcha.qss")
                .read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError) as e:
            logger.error(f"Could not load stylesheet: {e}")
            return

        self.setStyleSheet(qss_text)

    def _setup_ui(self) -> None:
        """Set up the user interface layout."""
        self.setWindowTitle(f"RenderKit v{__version__}")
        self.setMinimumSize(_MIN_WINDOW_WIDTH, _MIN_WINDOW_HEIGHT)
        self.resize(_DEFAULT_WINDOW_WIDTH, _DEFAULT_WINDOW_HEIGHT)
        self._last_preview_path: Optional[Path] = None

        # Central widget
        central_widget = QWidget()
        central_widget.setAcceptDrops(True)
        self.setCentralWidget(central_widget)

        root_layout = QGridLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.setRowStretch(0, 1)
        root_layout.setColumnStretch(0, 1)

        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)
        root_layout.addWidget(content_widget, 0, 0)

        # Drag & Drop overlay
        self.drop_overlay = QLabel("Drop sequence file or folder anywhere", central_widget)
        self.drop_overlay.setObjectName("DropOverlay")
        self.drop_overlay.setAlignment(_QT_ALIGN_CENTER)
        self.drop_overlay.setVisible(False)
        self.drop_overlay.setAcceptDrops(True)
        self.drop_overlay.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drop_overlay.setWordWrap(True)
        root_layout.addWidget(self.drop_overlay, 0, 0)

        central_widget.installEventFilter(self)
        self.drop_overlay.installEventFilter(self)
        self.drop_overlay_host = central_widget

        # Main horizontal splitter: Left = Hero Viewport & Log, Right = Tabbed Inspector
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        main_layout.addWidget(self.main_splitter, 1)

        # Left Column: Hero Viewport + Collapsible/Docked Log Drawer
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.setObjectName("LeftSplitter")

        self.preview_panel = self._create_preview_panel(height_capped=False)
        self.preview_panel.setObjectName("Card")
        self.left_splitter.addWidget(self.preview_panel)

        self.log_panel = self._create_log_panel()
        self.log_panel.setObjectName("Card")
        self.left_splitter.addWidget(self.log_panel)

        self.left_splitter.setSizes([540, 160])
        self.left_splitter.setStretchFactor(0, 4)
        self.left_splitter.setStretchFactor(1, 1)
        self.main_splitter.addWidget(self.left_splitter)

        # Right Column: Inspector Tabs
        settings_panel = self._create_settings_panel()
        settings_panel.setObjectName("Card")
        self.main_splitter.addWidget(settings_panel)

        # 60% Left Hero Viewport, 40% Right Inspector
        self.main_splitter.setSizes([760, 480])
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)

        # Bottom Command Deck
        action_panel = self._create_action_panel()
        action_panel.setObjectName("Card")
        main_layout.addWidget(action_panel, 0)

        # Menu bar
        self._create_menu_bar()

        # Status bar (hidden to keep UI modern and clean)
        self.statusBar().setVisible(False)

        # Flush startup logs
        if self._startup_logs:
            for msg in self._startup_logs:
                self.log_text.appendPlainText(msg)
            self._startup_logs.clear()

    def _setup_tray_icon(self) -> None:
        """Set up the system tray icon for notifications."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("System tray is not available; skipping tray icon setup.")
            return

        tray_icon = QSystemTrayIcon(self)
        tray_icon.setIcon(icon_manager.get_icon("info"))
        tray_icon.setToolTip("RenderKit")
        tray_icon.show()
        self.tray_icon = tray_icon

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

        if height < _COMPACT_HEIGHT_THRESHOLD:
            new_mode = "compact"
        elif height < _COMFORTABLE_HEIGHT_THRESHOLD:
            new_mode = "standard"
        else:
            new_mode = "comfortable"

        if new_mode != self._current_layout_mode:
            self._current_layout_mode = new_mode
            if new_mode == "compact":
                self._apply_compact_mode()
            elif new_mode == "standard":
                self._apply_standard_mode()
            else:
                self._apply_comfortable_mode()

    def _apply_compact_mode(self):
        """Apply compact layout for small windows."""
        if self.main_splitter:
            self.main_splitter.setSizes([600, 400])
        if self.left_splitter:
            self.left_splitter.setSizes([420, 120])

    def _apply_standard_mode(self):
        """Apply standard layout."""
        if self.preview_panel:
            self.preview_panel.setVisible(True)
        if self.main_splitter:
            self.main_splitter.setSizes([760, 480])
        if self.left_splitter:
            self.left_splitter.setSizes([540, 160])

    def _apply_comfortable_mode(self):
        """Apply comfortable layout for large windows."""
        if self.preview_panel:
            self.preview_panel.setVisible(True)
        if self.main_splitter:
            self.main_splitter.setSizes([880, 520])
        if self.left_splitter:
            self.left_splitter.setSizes([640, 200])

    def _create_settings_panel(self) -> QWidget:
        """Create the inspector tabbed panel."""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)
        panel_layout.setSpacing(6)

        # Tab Widget for Inspector Sections
        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("SettingsTabs")

        # Tab 1: Sequence / Source
        seq_scroll = QScrollArea()
        seq_scroll.setWidgetResizable(True)
        seq_scroll.setFrameShape(QFrame.Shape.NoFrame)
        seq_container = QWidget()
        seq_container.setLayout(self._create_input_sequence_content())
        seq_scroll.setWidget(seq_container)
        self.settings_tabs.addTab(seq_scroll, "Sequence")

        # Tab 2: Transcode / Output
        out_scroll = QScrollArea()
        out_scroll.setWidgetResizable(True)
        out_scroll.setFrameShape(QFrame.Shape.NoFrame)
        out_container = QWidget()
        out_container.setLayout(self._create_output_content())
        out_scroll.setWidget(out_container)
        self.settings_tabs.addTab(out_scroll, "Transcode")

        # Tab 3: Overlays & Contact Sheet
        overlay_scroll = QScrollArea()
        overlay_scroll.setWidgetResizable(True)
        overlay_scroll.setFrameShape(QFrame.Shape.NoFrame)
        overlay_container = QWidget()
        overlay_layout = QVBoxLayout(overlay_container)
        overlay_layout.setContentsMargins(4, 4, 4, 4)
        overlay_layout.setSpacing(8)

        # Burn-in section
        burnin_group = QGroupBox("Burn-in Metadata")
        burnin_group.setLayout(self._create_burnin_content())
        overlay_layout.addWidget(burnin_group)

        # Contact sheet section
        self.cs_section = CollapsibleGroupBox("Contact Sheet Grid")
        self.cs_section.set_content_layout(self._create_contact_sheet_content())
        self.cs_section.set_collapsed(True)
        overlay_layout.addWidget(self.cs_section)
        overlay_layout.addStretch()

        overlay_scroll.setWidget(overlay_container)
        self.settings_tabs.addTab(overlay_scroll, "Overlays")

        # Tab 4: Advanced
        adv_scroll = QScrollArea()
        adv_scroll.setWidgetResizable(True)
        adv_scroll.setFrameShape(QFrame.Shape.NoFrame)
        adv_container = QWidget()
        adv_container.setLayout(self._create_advanced_content())
        adv_scroll.setWidget(adv_container)
        self.settings_tabs.addTab(adv_scroll, "Advanced")

        panel_layout.addWidget(self.settings_tabs, 1)

        # Reset button footer
        reset_layout = QHBoxLayout()
        reset_layout.setContentsMargins(4, 2, 4, 2)
        reset_layout.addStretch()
        self.reset_settings_btn = QPushButton("Reset to defaults")
        self.reset_settings_btn.setToolTip("Reset all settings to default values.")
        reset_layout.addWidget(self.reset_settings_btn)
        panel_layout.addLayout(reset_layout)

        return panel

    def _create_input_sequence_content(self) -> QVBoxLayout:
        """Create content for input sequence section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(6, 8, 6, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        # Input pattern
        input_pattern_layout = QHBoxLayout()
        input_pattern_layout.setSpacing(6)
        self.input_pattern_combo = NoWheelComboBox()
        self.input_pattern_combo.setEditable(True)
        insert_policy = getattr(QComboBox, "InsertPolicy", None)
        if insert_policy is not None:
            self.input_pattern_combo.setInsertPolicy(insert_policy.NoInsert)
        else:
            self.input_pattern_combo.setInsertPolicy(QComboBox.NoInsert)
        line_edit = self.input_pattern_combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("e.g. render.%04d.exr or render.####.exr")
        self.input_pattern_combo.setToolTip("Enter a sequence pattern or select a recent one.")
        self.input_pattern_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.input_pattern_combo.setMinimumWidth(0)
        input_pattern_layout.addWidget(self.input_pattern_combo, 1)

        self.browse_input_btn = QPushButton("Browse")
        self.browse_input_btn.setMaximumWidth(90)
        self.browse_input_btn.setIcon(icon_manager.get_icon("browse"))
        input_pattern_layout.addWidget(self.browse_input_btn)
        form_layout.addRow("Pattern:", input_pattern_layout)

        # Sequence Info Badge
        self.sequence_info_label = QLabel("No sequence detected")
        self.sequence_info_label.setWordWrap(True)
        self.sequence_info_label.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.sequence_info_label.setMinimumHeight(32)
        form_layout.addRow("Info:", self.sequence_info_label)

        # Layer Selection & Contact Sheet Mode
        layer_layout = QHBoxLayout()
        layer_layout.setSpacing(8)
        self.layer_combo = NoWheelComboBox()
        self.layer_combo.addItems(["RGBA"])
        self.layer_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layer_combo.setMinimumWidth(0)
        self.layer_combo.setEnabled(False)
        self.layer_combo.setToolTip("Select EXR layer (AOV) to process.")
        layer_layout.addWidget(self.layer_combo, 1)

        self.cs_enable_check = QCheckBox("Contact Sheet")
        self.cs_enable_check.setToolTip(
            "Generate a multi-layer contact sheet grid across all detected AOVs."
        )
        self.cs_enable_check.toggled.connect(self._on_cs_enable_toggled)
        layer_layout.addWidget(self.cs_enable_check)
        form_layout.addRow("Layer / AOV:", layer_layout)

        # Color Space
        self.color_space_combo = NoWheelComboBox()
        self.color_space_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.color_space_combo.setMinimumWidth(0)
        self.color_space_combo.setEditable(False)
        self._populate_color_space_combo(self.color_space_combo)
        self.color_space_combo.setToolTip(
            "Select input color space (OCIO/Standard). Output is always sRGB."
        )
        form_layout.addRow("Color Space:", self.color_space_combo)

        layout.addLayout(form_layout)
        layout.addStretch()
        return layout

    def _create_output_content(self) -> QVBoxLayout:
        """Create content for transcode output settings."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(6, 8, 6, 8)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        grid_layout.setColumnStretch(1, 0)
        grid_layout.setColumnStretch(2, 0)
        grid_layout.setColumnStretch(3, 1)

        def _row_layout(spacing: int = 6) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(spacing)
            return row

        align_left = _QT_ALIGN_LEFT

        # Output file path
        output_path_layout = QHBoxLayout()
        output_path_layout.setSpacing(6)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output destination (.mp4)...")
        self.output_path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.output_path_edit.setMinimumWidth(0)
        output_path_layout.addWidget(self.output_path_edit, 1)

        self.browse_output_btn = QPushButton("Browse")
        self.browse_output_btn.setMaximumWidth(90)
        self.browse_output_btn.setIcon(icon_manager.get_icon("browse"))
        output_path_layout.addWidget(self.browse_output_btn)
        grid_layout.addWidget(QLabel("Output File:"), 0, 0)
        grid_layout.addLayout(output_path_layout, 0, 1, 1, 3)

        # Frame Range
        frame_range_layout = _row_layout()
        self.start_frame_spin = NoWheelSpinBox()
        self.start_frame_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.start_frame_spin.setMinimum(1)
        self.start_frame_spin.setMaximum(999999)
        self.start_frame_spin.setValue(1)
        frame_range_layout.addWidget(QLabel("Start:"))
        frame_range_layout.addWidget(self.start_frame_spin)

        self.end_frame_spin = NoWheelSpinBox()
        self.end_frame_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.end_frame_spin.setMinimum(1)
        self.end_frame_spin.setMaximum(999999)
        self.end_frame_spin.setValue(1)
        frame_range_layout.addWidget(QLabel("End:"))
        frame_range_layout.addWidget(self.end_frame_spin)

        self.keep_source_frame_range_check = QCheckBox("Keep source range")
        self.keep_source_frame_range_check.setChecked(True)
        self.keep_source_frame_range_check.toggled.connect(self._on_keep_frame_range_toggled)

        grid_layout.addWidget(QLabel("Frame Range:"), 1, 0)
        grid_layout.addLayout(frame_range_layout, 1, 1, alignment=align_left)
        grid_layout.addWidget(self.keep_source_frame_range_check, 1, 2, alignment=align_left)

        stretch_spacer = QWidget()
        stretch_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        grid_layout.addWidget(stretch_spacer, 1, 3, 3, 1)

        # Frame Rate
        self.fps_spin = NoWheelDoubleSpinBox()
        self.fps_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.fps_spin.setRange(0.01, 120.0)
        self.fps_spin.setDecimals(3)
        self.fps_spin.setValue(24.0)
        self.fps_spin.setSuffix(" fps")
        fps_layout = _row_layout()
        fps_layout.addWidget(self.fps_spin)

        self.keep_source_fps_check = QCheckBox("Keep source FPS")
        self.keep_source_fps_check.setChecked(True)
        self.keep_source_fps_check.toggled.connect(self._on_keep_source_fps_toggled)

        grid_layout.addWidget(QLabel("Frame Rate:"), 2, 0)
        grid_layout.addLayout(fps_layout, 2, 1, alignment=align_left)
        grid_layout.addWidget(self.keep_source_fps_check, 2, 2, alignment=align_left)

        # Resolution
        resolution_layout = _row_layout()
        self.width_spin = NoWheelSpinBox()
        self.width_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.width_spin.setMinimum(1)
        self.width_spin.setMaximum(7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("W:"))
        resolution_layout.addWidget(self.width_spin)

        self.aspect_link_btn = QToolButton()
        self.aspect_link_btn.setCheckable(True)
        self.aspect_link_btn.setChecked(True)
        self.aspect_link_btn.setObjectName("AspectLinkButton")
        self.aspect_link_btn.setToolTip("Lock aspect ratio")
        self.aspect_link_btn.setIcon(icon_manager.get_icon("link_on", size=14))
        self.aspect_link_btn.setIconSize(QSize(14, 14))
        self.aspect_link_btn.setFixedSize(26, 26)
        resolution_layout.addWidget(self.aspect_link_btn)

        self.height_spin = NoWheelSpinBox()
        self.height_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.height_spin.setMinimum(1)
        self.height_spin.setMaximum(4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("H:"))
        resolution_layout.addWidget(self.height_spin)

        self.keep_resolution_check = QCheckBox("Keep source resolution")
        self.keep_resolution_check.setChecked(True)
        self.keep_resolution_check.toggled.connect(self._on_keep_resolution_toggled)

        grid_layout.addWidget(QLabel("Resolution:"), 3, 0)
        grid_layout.addLayout(resolution_layout, 3, 1, alignment=align_left)
        grid_layout.addWidget(self.keep_resolution_check, 3, 2, alignment=align_left)

        layout.addLayout(grid_layout)

        # Codec & Visual Quality
        codec_form = QFormLayout()
        codec_form.setSpacing(10)
        self._set_form_growth_policy(codec_form)

        self.codec_combo = NoWheelComboBox()
        self._populate_codecs()
        codec_form.addRow("Video Codec:", self.codec_combo)

        quality_layout = QHBoxLayout()
        self.quality_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(0, 10)
        self.quality_slider.setValue(10)
        self.quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.quality_slider.setTickInterval(1)
        self.quality_slider.setToolTip("Visual Quality (0-10), 10 is visually lossless.")

        self.quality_label = QLabel("10 (Max)")
        self.quality_label.setFixedWidth(70)
        self.quality_label.setStyleSheet("font-weight: 600; font-family: monospace;")

        quality_layout.addWidget(self.quality_slider, 1)
        quality_layout.addWidget(self.quality_label)
        codec_form.addRow("Visual Quality:", quality_layout)

        layout.addLayout(codec_form)
        layout.addStretch()
        return layout

    def _create_burnin_content(self) -> QVBoxLayout:
        """Create content for burn-in overlays section."""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        self.burnin_enable_check = QCheckBox("Enable Overlays")
        self.burnin_enable_check.setToolTip("Enable or disable all burn-in overlays")
        self.burnin_enable_check.setStyleSheet("font-weight: 600;")
        self.burnin_enable_check.setChecked(True)
        self.burnin_enable_check.toggled.connect(self._on_burnin_enable_toggled)
        layout.addWidget(self.burnin_enable_check)

        toggles_layout = QGridLayout()
        toggles_layout.setSpacing(8)

        self.burnin_frame_check = QCheckBox("Frame Number")
        self.burnin_frame_check.setToolTip("Overlay the current frame number (top-left)")
        self.burnin_frame_check.setChecked(True)
        toggles_layout.addWidget(self.burnin_frame_check, 0, 0)

        self.burnin_layer_check = QCheckBox("Layer / AOV Name")
        self.burnin_layer_check.setToolTip("Overlay the active EXR layer name")
        self.burnin_layer_check.setChecked(True)
        toggles_layout.addWidget(self.burnin_layer_check, 0, 1)

        self.burnin_fps_check = QCheckBox("Frame Rate (FPS)")
        self.burnin_fps_check.setToolTip("Overlay the video frame rate")
        self.burnin_fps_check.setChecked(True)
        toggles_layout.addWidget(self.burnin_fps_check, 1, 0)

        layout.addLayout(toggles_layout)

        form = QFormLayout()
        form.setSpacing(8)

        self.burnin_font_size_spin = NoWheelSpinBox()
        self.burnin_font_size_spin.setRange(6, 72)
        self.burnin_font_size_spin.setValue(20)
        self.burnin_font_size_spin.setSuffix(" pt")
        form.addRow("Font Size:", self.burnin_font_size_spin)

        self.burnin_opacity_spin = NoWheelSpinBox()
        self.burnin_opacity_spin.setRange(0, 100)
        self.burnin_opacity_spin.setValue(30)
        self.burnin_opacity_spin.setSuffix(" %")
        form.addRow("Box Opacity:", self.burnin_opacity_spin)

        layout.addLayout(form)
        return layout

    def _create_contact_sheet_content(self) -> QVBoxLayout:
        """Create content for contact sheet section."""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        self._set_form_growth_policy(form_layout)

        self.cs_columns_spin = NoWheelSpinBox()
        self.cs_columns_spin.setRange(1, 20)
        self.cs_columns_spin.setValue(_CONTACT_SHEET_DEFAULT_COLUMNS)
        form_layout.addRow("Grid Columns:", self.cs_columns_spin)

        self.cs_padding_spin = NoWheelSpinBox()
        self.cs_padding_spin.setRange(0, 100)
        self.cs_padding_spin.setValue(_CONTACT_SHEET_DEFAULT_PADDING)
        self.cs_padding_spin.setSuffix(" px")
        form_layout.addRow("Tile Padding:", self.cs_padding_spin)

        layout.addLayout(form_layout)
        return layout

    def _create_advanced_content(self) -> QVBoxLayout:
        """Create content for advanced options section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(6, 8, 6, 8)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        self._set_form_growth_policy(form_layout)

        self.prefetch_workers_spin = NoWheelSpinBox()
        self.prefetch_workers_spin.setRange(1, 16)
        self.prefetch_workers_spin.setValue(2)
        self.prefetch_workers_spin.setToolTip(
            "Concurrent frame reads to saturate I/O bandwidth (1 disables prefetching)."
        )
        form_layout.addRow("Prefetch Workers:", self.prefetch_workers_spin)

        self.preview_scale_spin = NoWheelSpinBox()
        self.preview_scale_spin.setRange(5, 100)
        self.preview_scale_spin.setValue(75)
        self.preview_scale_spin.setSuffix(" %")
        self.preview_scale_spin.setToolTip(
            "Scale down preview resolution to enhance real-time responsiveness."
        )
        form_layout.addRow("Preview Scale:", self.preview_scale_spin)

        self.overwrite_check = QCheckBox("Overwrite existing output files")
        self.overwrite_check.setChecked(True)
        form_layout.addRow(self.overwrite_check)

        layout.addLayout(form_layout)
        layout.addStretch()
        return layout

    def _create_log_panel(self) -> QWidget:
        """Create the collapsible activity log panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._create_log_group())
        return panel

    def _create_preview_column(self) -> QWidget:
        """Create preview column container."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._create_progress_group())

        self.preview_panel = self._create_preview_panel(height_capped=False)
        layout.addWidget(self.preview_panel, 1)
        self._set_status_icons("idle")
        return panel

    def _create_progress_group(self) -> QGroupBox:
        """Create the progress status group."""
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(8)
        progress_layout.setContentsMargins(6, 6, 6, 6)

        progress_header = QHBoxLayout()
        self.progress_status_icon = QLabel()
        self.progress_status_icon.setFixedSize(16, 16)
        self.progress_status_icon.setAlignment(_QT_ALIGN_CENTER)
        self.progress_label = QLabel("Ready")
        self.progress_label.setStyleSheet("font-weight: 500;")
        progress_header.addWidget(self.progress_status_icon)
        progress_header.addWidget(self.progress_label)
        progress_header.addStretch()
        progress_layout.addLayout(progress_header)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.progress_play_btn = QPushButton()
        self.progress_play_btn.setFixedSize(24, 24)
        self.progress_play_btn.setObjectName("IconButton")
        self.progress_play_btn.setIcon(icon_manager.get_icon("play", size=14))
        self.progress_play_btn.setIconSize(QSize(14, 14))
        self.progress_play_btn.setToolTip("Play output")
        self.progress_play_btn.setVisible(False)
        self.progress_play_btn.clicked.connect(self._play_output)

        self.progress_folder_btn = QPushButton()
        self.progress_folder_btn.setFixedSize(24, 24)
        self.progress_folder_btn.setObjectName("IconButton")
        self.progress_folder_btn.setIcon(icon_manager.get_icon("file_folder", size=14))
        self.progress_folder_btn.setIconSize(QSize(14, 14))
        self.progress_folder_btn.setToolTip("Open output folder")
        self.progress_folder_btn.setVisible(False)
        self.progress_folder_btn.clicked.connect(self._open_output_folder)

        return progress_group

    def _create_log_group(self) -> QGroupBox:
        """Create the log output group."""
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 8, 6, 6)
        log_layout.setSpacing(6)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMaximumBlockCount(_LOG_MAX_BLOCK_COUNT)
        self.log_text.setObjectName("LogBox")
        log_layout.addWidget(self.log_text, 1)

        log_actions = QHBoxLayout()
        log_actions.addStretch()
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.clicked.connect(self.log_text.clear)
        clear_log_btn.setIcon(icon_manager.get_icon("close"))
        log_actions.addWidget(clear_log_btn)
        log_layout.addLayout(log_actions)

        return log_group

    def _create_preview_panel(self, *, height_capped: bool = True) -> QWidget:
        """Create hero preview panel."""
        panel = QWidget()
        panel.setMinimumHeight(240)
        if height_capped:
            panel.setMaximumHeight(400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("Hero Viewport Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(4)

        self.preview_widget = PreviewWidget()
        self.preview_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout.addWidget(self.preview_widget, 1)

        # Timeline Scrubber Bar
        self.timeline_widget = QWidget()
        self.timeline_widget.setObjectName("TimelineWidget")
        self.timeline_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.timeline_widget.setMaximumHeight(_TIMELINE_MAX_HEIGHT)
        timeline_layout = QVBoxLayout(self.timeline_widget)
        timeline_layout.setContentsMargins(4, 2, 4, 2)
        timeline_layout.setSpacing(2)

        timeline_row = QHBoxLayout()
        timeline_row.setContentsMargins(0, 0, 0, 0)
        timeline_row.setSpacing(6)

        self.timeline_start_label = QLabel("--")
        self.timeline_start_label.setObjectName("TimelineLabel")
        self.timeline_start_label.setAlignment(_QT_ALIGN_LEFT)
        self.timeline_end_label = QLabel("--")
        self.timeline_end_label.setObjectName("TimelineLabel")
        self.timeline_end_label.setAlignment(_QT_ALIGN_RIGHT)

        self.timeline_slider = JumpToClickSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setObjectName("TimelineSlider")
        self.timeline_slider.setTracking(True)
        self.timeline_slider.setEnabled(False)
        self.timeline_slider.setMinimum(0)
        self.timeline_slider.setMaximum(0)
        self.timeline_slider.setSingleStep(1)
        self.timeline_slider.setFixedHeight(20)

        timeline_row.addWidget(self.timeline_start_label)
        timeline_row.addWidget(self.timeline_slider, 1)
        timeline_row.addWidget(self.timeline_end_label)
        timeline_layout.addLayout(timeline_row)

        self.timeline_current_label = QLabel("Frame: -")
        self.timeline_current_label.setObjectName("TimelineCurrentLabel")
        self.timeline_current_label.setAlignment(_QT_ALIGN_CENTER)
        self.timeline_current_label.setFixedHeight(16)
        timeline_layout.addWidget(self.timeline_current_label)

        self.timeline_widget.setVisible(False)
        preview_layout.addWidget(self.timeline_widget, 0)

        layout.addWidget(preview_group)
        return panel

    def _create_action_panel(self) -> QWidget:
        """Create minimal bottom render & status deck."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Progress bar (cleanly filling left/center space)
        if not hasattr(self, "progress_bar"):
            self.progress_bar = QProgressBar()
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setTextVisible(True)
        self.progress_bar.setMinimumWidth(200)
        layout.addWidget(self.progress_bar, 1)

        # Quick action icon buttons (appear after conversion completes)
        if not hasattr(self, "progress_play_btn"):
            self.progress_play_btn = QPushButton()
            self.progress_play_btn.setFixedSize(26, 26)
            self.progress_play_btn.setObjectName("IconButton")
            self.progress_play_btn.setIcon(icon_manager.get_icon("play", size=14))
            self.progress_play_btn.setIconSize(QSize(14, 14))
            self.progress_play_btn.setToolTip("Play Output Video")
            self.progress_play_btn.setVisible(False)
            self.progress_play_btn.clicked.connect(self._play_output)
        layout.addWidget(self.progress_play_btn)

        if not hasattr(self, "progress_folder_btn"):
            self.progress_folder_btn = QPushButton()
            self.progress_folder_btn.setFixedSize(26, 26)
            self.progress_folder_btn.setObjectName("IconButton")
            self.progress_folder_btn.setIcon(icon_manager.get_icon("file_folder", size=14))
            self.progress_folder_btn.setIconSize(QSize(14, 14))
            self.progress_folder_btn.setToolTip("Open Output Folder")
            self.progress_folder_btn.setVisible(False)
            self.progress_folder_btn.clicked.connect(self._open_output_folder)
        layout.addWidget(self.progress_folder_btn)

        # Aliases so logic calling play_btn/open_output_btn controls these buttons directly
        self.play_btn = self.progress_play_btn
        self.open_output_btn = self.progress_folder_btn

        # Primary Convert CTA
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.setMinimumWidth(110)
        self.convert_btn.setObjectName("PrimaryButton")
        self.convert_btn.setIcon(icon_manager.get_icon("convert"))
        layout.addWidget(self.convert_btn)

        # Retain hidden helper objects for logic compatibility
        self.progress_status_icon = QLabel()
        self.progress_status_icon.setVisible(False)
        self.progress_label = QLabel("Ready")
        self.progress_label.setVisible(False)
        self.convert_hint_label = QLabel("")
        self.convert_hint_label.setVisible(False)
        self.cancel_btn = QPushButton("Quit")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.close)

        self._set_status_icons("idle")
        return panel

    def _create_menu_bar(self) -> None:
        """Create menu bar with Help menu."""
        menubar = self.menuBar()
        help_menu = menubar.addMenu("Help")
        about_action = help_menu.addAction("About")
        about_action.setIcon(icon_manager.get_icon("help"))
        about_action.triggered.connect(self._show_about)
        about_action.setShortcut("F1")

    def _show_about(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>RenderKit</h2>
        <p><b>Version:</b> {__version__}</p>
        <p><b>Qt Backend:</b> {QT_BACKEND_NAME}</p>
        <p>High-performance image sequence and video processing for VFX workflows.</p>
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
        codecs = [
            ("libx264", "H.264 (AVC) - Universal"),
            ("libx265", "H.265 (HEVC) - High Efficiency"),
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

    def _get_theme_name(self) -> str:
        theme = self.property("theme")
        if isinstance(theme, str) and theme:
            return theme
        return "dark"

    def _get_status_color(self, status: str) -> str:
        theme = self._get_theme_name()
        if theme == "light":
            colors = {
                "idle": "#64748b",
                "running": "#0969da",
                "success": "#16a34a",
                "error": "#dc2626",
                "cancelled": "#d97706",
            }
        else:
            colors = {
                "idle": "#71717a",
                "running": "#3b82f6",
                "success": "#22c55e",
                "error": "#ef4444",
                "cancelled": "#f59e0b",
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
