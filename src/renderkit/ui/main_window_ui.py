"""UI construction mixin for the RenderKit main window."""

from __future__ import annotations

import logging
from importlib import resources
from pathlib import Path
from typing import Optional

from renderkit import __version__
from renderkit.ui.icons import icon_manager
from renderkit.ui.main_window_widgets import (
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
    QSize,
    QSizePolicy,
    QSlider,
    QSplitter,
    QSystemTrayIcon,
    Qt,
    QVBoxLayout,
    QWidget,
)
from renderkit.ui.widgets import PreviewWidget

logger = logging.getLogger("renderkit.ui.main_window")


class MainWindowUiMixin:
    """UI construction and layout helpers."""

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
        self.cs_section = CollapsibleGroupBox("Contact Sheet")
        self.cs_section.set_content_layout(self._create_contact_sheet_content())
        self.cs_section.set_collapsed(True)
        container_layout.addWidget(self.cs_section)

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

        # Mutual exclusivity: Contact Sheet toggle next to layer
        layer_layout = QHBoxLayout()
        layer_layout.addWidget(self.layer_combo)

        self.cs_enable_check = QCheckBox("Contact Sheet")
        self.cs_enable_check.setToolTip(
            "Enable contact sheet mode (disables single layer selection)"
        )
        self.cs_enable_check.toggled.connect(self._on_cs_enable_toggled)
        layer_layout.addWidget(self.cs_enable_check)

        form_layout.addRow("Layer:", layer_layout)

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

        return layout

    def _create_output_content(self) -> QVBoxLayout:
        """Create content for output settings section."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(8, 8, 8, 8)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        grid_layout.setColumnStretch(1, 0)
        grid_layout.setColumnStretch(2, 0)
        grid_layout.setColumnStretch(3, 1)

        def _row_layout(spacing: int = 6) -> QHBoxLayout:
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(spacing)
            return layout

        align_left = Qt.AlignmentFlag.AlignLeft

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
        grid_layout.addWidget(QLabel("Output Path:"), 0, 0)
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
        self.keep_source_frame_range_check = QCheckBox("Keep source framerange")
        self.keep_source_frame_range_check.setChecked(True)
        self.keep_source_frame_range_check.toggled.connect(self._on_keep_frame_range_toggled)
        grid_layout.addWidget(QLabel("Frame Range:"), 1, 0)
        grid_layout.addLayout(frame_range_layout, 1, 1, alignment=align_left)
        grid_layout.addWidget(
            self.keep_source_frame_range_check,
            1,
            2,
            alignment=align_left,
        )
        stretch_spacer = QWidget()
        stretch_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        grid_layout.addWidget(stretch_spacer, 1, 3, 3, 1)

        # Frame rate
        self.fps_spin = NoWheelDoubleSpinBox()
        self.fps_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.fps_spin.setRange(0.01, 120.0)
        self.fps_spin.setDecimals(3)
        self.fps_spin.setValue(24.0)
        self.fps_spin.setSuffix(" fps")
        fps_layout = _row_layout()
        fps_layout.addWidget(self.fps_spin)
        self.keep_source_fps_check = QCheckBox("Keep Source FPS")
        self.keep_source_fps_check.setChecked(True)
        self.keep_source_fps_check.toggled.connect(self._on_keep_source_fps_toggled)
        grid_layout.addWidget(QLabel("Frame Rate:"), 2, 0)
        grid_layout.addLayout(fps_layout, 2, 1, alignment=align_left)
        grid_layout.addWidget(
            self.keep_source_fps_check,
            2,
            2,
            alignment=align_left,
        )

        # Resolution
        resolution_layout = _row_layout()
        self.width_spin = NoWheelSpinBox()
        self.width_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.width_spin.setMinimum(1)
        self.width_spin.setMaximum(7680)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Width:"))
        resolution_layout.addWidget(self.width_spin)

        self.height_spin = NoWheelSpinBox()
        self.height_spin.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.height_spin.setMinimum(1)
        self.height_spin.setMaximum(4320)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        resolution_layout.addWidget(QLabel("Height:"))
        resolution_layout.addWidget(self.height_spin)

        self.keep_resolution_check = QCheckBox("Keep source resolution")
        self.keep_resolution_check.setChecked(True)
        self.keep_resolution_check.toggled.connect(self._on_keep_resolution_toggled)
        grid_layout.addWidget(QLabel("Resolution:"), 3, 0)
        grid_layout.addLayout(resolution_layout, 3, 1, alignment=align_left)
        grid_layout.addWidget(
            self.keep_resolution_check,
            3,
            2,
            alignment=align_left,
        )

        layout.addLayout(grid_layout)

        if not hasattr(self, "play_btn") or self.play_btn is None:
            self.play_btn = QPushButton("Play Result (Flipbook)")
            self.play_btn.setEnabled(False)
            self.play_btn.clicked.connect(self._play_output)
            self.play_btn.setToolTip("Open the conversion result in the default system player.")
            self.play_btn.setObjectName("IconButton")
            self.play_btn.setIcon(icon_manager.get_icon("play"))
        if not hasattr(self, "open_output_btn") or self.open_output_btn is None:
            self.open_output_btn = QPushButton("Open Output Folder")
            self.open_output_btn.setEnabled(False)
            self.open_output_btn.clicked.connect(self._open_output_folder)
            self.open_output_btn.setToolTip("Open the output folder in the system file browser.")
            self.open_output_btn.setObjectName("IconButton")
            self.open_output_btn.setIcon(icon_manager.get_icon("file_folder"))

        output_actions_layout = QHBoxLayout()
        output_actions_layout.setContentsMargins(0, 0, 0, 0)
        output_actions_layout.setSpacing(8)
        output_actions_layout.addWidget(self.play_btn)
        output_actions_layout.addWidget(self.open_output_btn)
        output_actions_layout.addStretch()
        layout.addLayout(output_actions_layout)

        return layout

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
        self.progress_folder_btn = QPushButton()
        self.progress_folder_btn.setFixedSize(22, 22)
        self.progress_folder_btn.setIcon(icon_manager.get_icon("file_folder"))
        self.progress_folder_btn.setIconSize(QSize(14, 14))
        self.progress_folder_btn.setToolTip("Open output folder")
        self.progress_folder_btn.setVisible(False)
        self.progress_folder_btn.clicked.connect(self._open_output_folder)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        status_layout.addStretch()
        status_layout.addWidget(self.progress_label)
        status_layout.addWidget(self.progress_play_btn)
        status_layout.addWidget(self.progress_folder_btn)
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
        self.burnin_layer_check.setToolTip(
            "Overlay the active EXR layer name (top-left) and toggle contact sheet labels."
        )
        self.burnin_layer_check.setChecked(True)
        layout.addWidget(self.burnin_layer_check)

        self.burnin_fps_check = QCheckBox("Frame Rate (FPS)")
        self.burnin_fps_check.setToolTip("Overlay the video frame rate (top-left)")
        self.burnin_fps_check.setChecked(True)
        layout.addWidget(self.burnin_fps_check)

        # Font size
        font_size_layout = QHBoxLayout()
        font_size_layout.addWidget(QLabel("Font Size:"))
        self.burnin_font_size_spin = NoWheelSpinBox()
        self.burnin_font_size_spin.setRange(6, 72)
        self.burnin_font_size_spin.setValue(20)
        self.burnin_font_size_spin.setSuffix(" pt")
        self.burnin_font_size_spin.setToolTip(
            "Font size for burn-ins and contact sheet layer labels."
        )
        font_size_layout.addWidget(self.burnin_font_size_spin)
        font_size_layout.addStretch()
        layout.addLayout(font_size_layout)

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

        self.cs_columns_spin = NoWheelSpinBox()
        self.cs_columns_spin.setRange(1, 20)
        self.cs_columns_spin.setValue(4)
        form_layout.addRow("Columns:", self.cs_columns_spin)

        self.cs_padding_spin = NoWheelSpinBox()
        self.cs_padding_spin.setRange(0, 100)
        self.cs_padding_spin.setValue(4)
        self.cs_padding_spin.setSuffix(" px")
        form_layout.addRow("Padding:", self.cs_padding_spin)

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

        self.overwrite_check = QCheckBox("Overwrite existing files")
        self.overwrite_check.setToolTip("Automatically overwrite output files if they exist")
        self.overwrite_check.setChecked(True)
        form_layout.addRow(self.overwrite_check)

        self.prefetch_workers_spin = NoWheelSpinBox()
        self.prefetch_workers_spin.setRange(1, 16)
        self.prefetch_workers_spin.setValue(2)
        self.prefetch_workers_spin.setToolTip(
            "Concurrent frame reads to saturate network bandwidth (1 disables prefetch)."
        )
        form_layout.addRow("Prefetch Workers:", self.prefetch_workers_spin)

        # Preview Scale
        self.preview_scale_spin = NoWheelSpinBox()
        self.preview_scale_spin.setRange(5, 100)
        self.preview_scale_spin.setValue(75)
        self.preview_scale_spin.setSuffix("%")
        self.preview_scale_spin.setToolTip(
            "Scale down the preview resolution to improve performance (5-100%)"
        )
        form_layout.addRow("Preview Scale:", self.preview_scale_spin)

        layout.addLayout(form_layout)
        return layout

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
