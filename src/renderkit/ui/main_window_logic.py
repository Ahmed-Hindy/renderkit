"""Logic and event handling mixin for the RenderKit main window."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from renderkit import constants
from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfigBuilder,
)
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
from renderkit.ui.file_info_worker import FileInfoWorker
from renderkit.ui.icons import icon_manager
from renderkit.ui.main_window_widgets import UiLogForwarder
from renderkit.ui.qt_compat import (
    QApplication,
    QComboBox,
    QDesktopServices,
    QFileDialog,
    QMessageBox,
    QSystemTrayIcon,
    Qt,
    QUrl,
)

logger = logging.getLogger("renderkit.ui.main_window")

RECENT_PATTERNS_LIMIT = 10
RECENT_PATTERNS_KEY = "recent_patterns"
RECENT_PATTERNS_CLEAR_LABEL = "Clear recent patterns"


class MainWindowLogicMixin:
    """Signal handlers, validation, and worker orchestration."""

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

        # Preview real-time updates
        self.cs_columns_spin.valueChanged.connect(self._on_cs_setting_changed)
        self.cs_padding_spin.valueChanged.connect(self._on_cs_setting_changed)
        self.cs_show_labels_check.toggled.connect(self._on_cs_setting_changed)
        self.cs_font_size_spin.valueChanged.connect(self._on_cs_setting_changed)
        self.preview_scale_spin.valueChanged.connect(self._on_cs_setting_changed)
        self.color_space_combo.currentIndexChanged.connect(self._on_cs_setting_changed)
        self.layer_combo.currentIndexChanged.connect(self._on_cs_setting_changed)
        self.burnin_enable_check.toggled.connect(self._on_cs_setting_changed)
        self.burnin_frame_check.toggled.connect(self._on_cs_setting_changed)
        self.burnin_layer_check.toggled.connect(self._on_cs_setting_changed)
        self.burnin_fps_check.toggled.connect(self._on_cs_setting_changed)
        self.burnin_opacity_spin.valueChanged.connect(self._on_cs_setting_changed)
        self.quality_slider.valueChanged.connect(self._on_quality_changed)
        self.reset_settings_btn.clicked.connect(self._reset_settings_to_defaults)
        self.convert_btn.clicked.connect(self._start_conversion)
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
        if self.input_pattern_combo.lineEdit():
            self.input_pattern_combo.lineEdit().blockSignals(True)

        self.input_pattern_combo.clear()

        for pattern in self._recent_patterns:
            self.input_pattern_combo.addItem(pattern)

        if self._recent_patterns:
            self.input_pattern_combo.addItem(RECENT_PATTERNS_CLEAR_LABEL)

        self.input_pattern_combo.setCurrentIndex(-1)
        self.input_pattern_combo.setEditText(current_text)

        if self.input_pattern_combo.lineEdit():
            self.input_pattern_combo.lineEdit().blockSignals(False)
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
        self.keep_source_fps_check.setChecked(True)
        self.keep_source_frame_range_check.setChecked(True)
        self.width_spin.setValue(1920)
        self.height_spin.setValue(1080)
        self.codec_combo.setCurrentIndex(0)
        self.keep_resolution_check.setChecked(True)
        self.quality_slider.setValue(10)
        if hasattr(self, "prefetch_workers_spin"):
            self.prefetch_workers_spin.setValue(2)

        self.burnin_enable_check.setChecked(True)
        self.burnin_frame_check.setChecked(True)
        self.burnin_layer_check.setChecked(True)
        self.burnin_fps_check.setChecked(True)
        self.burnin_opacity_spin.setValue(30)

        self.cs_enable_check.setChecked(False)
        self.cs_columns_spin.setValue(4)
        self.cs_padding_spin.setValue(4)
        self.cs_show_labels_check.setChecked(True)
        self.cs_font_size_spin.setValue(16)
        self.preview_scale_spin.setValue(75)
        if hasattr(self, "overwrite_check"):
            self.overwrite_check.setChecked(True)

        self._save_settings()
        self.statusBar().showMessage("Settings reset to defaults", 3000)

    def _on_keep_resolution_toggled(self, checked: bool) -> None:
        """Handle keep resolution checkbox toggle."""
        self.width_spin.setEnabled(not checked)
        self.height_spin.setEnabled(not checked)
        if checked:
            tooltip = "Using source resolution. Uncheck to set custom width/height."
        else:
            tooltip = "Set custom output resolution."
        self.width_spin.setToolTip(tooltip)
        self.height_spin.setToolTip(tooltip)

    def _on_keep_frame_range_toggled(self, checked: bool) -> None:
        """Handle keep source frame range checkbox toggle."""
        self.start_frame_spin.setEnabled(not checked)
        self.end_frame_spin.setEnabled(not checked)
        if checked:
            tooltip = "Using source frame range. Uncheck to set custom start/end."
        else:
            tooltip = "Set custom frame range."
        self.start_frame_spin.setToolTip(tooltip)
        self.end_frame_spin.setToolTip(tooltip)

    def _on_keep_source_fps_toggled(self, checked: bool) -> None:
        """Handle keep source FPS checkbox toggle."""
        self.fps_spin.setEnabled(not checked)
        if checked:
            tooltip = "Using source FPS. Uncheck to set a custom FPS."
        else:
            tooltip = "Set custom output FPS."
        self.fps_spin.setToolTip(tooltip)

    def _on_burnin_enable_toggled(self, checked: bool) -> None:
        """Handle burn-in enable checkbox toggle."""
        self.burnin_frame_check.setEnabled(checked)
        self.burnin_layer_check.setEnabled(checked)
        self.burnin_fps_check.setEnabled(checked)
        self.burnin_opacity_spin.setEnabled(checked)

    def _on_cs_enable_toggled(self, checked: bool) -> None:
        """Handle contact sheet enable checkbox toggle."""
        # Mutual exclusivity
        if checked:
            self.layer_combo.setEnabled(False)
            self.layer_combo.setToolTip("Layer selection disabled in Contact Sheet mode.")
            # Visual cue for disabled state
            self.layer_combo.setStyleSheet("color: #888; font-style: italic;")

            # Auto-expand settings
            if hasattr(self, "cs_section"):
                self.cs_section.set_collapsed(False)
        else:
            # Re-enable if we have layers (more than 1 or not just RGBA)
            should_enable = False
            if self.layer_combo.count() > 1:
                should_enable = True
            elif self.layer_combo.count() == 1 and self.layer_combo.itemText(0) != "RGBA":
                should_enable = True

            self.layer_combo.setEnabled(should_enable)
            self.layer_combo.setToolTip("Select EXR layer (AOV) to process.")
            self.layer_combo.setStyleSheet("")  # Reset style

        # Trigger preview update if we have a pattern (to show/hide grid)
        if self._is_output_path_valid() or self.input_pattern_combo.currentText().strip():
            if hasattr(self, "_last_preview_path") and self._last_preview_path:
                self._load_preview()

        self.cs_columns_spin.setEnabled(checked)
        self.cs_padding_spin.setEnabled(checked)
        self.cs_show_labels_check.setEnabled(checked)
        self.cs_font_size_spin.setEnabled(checked)
        if checked:
            self.cs_columns_spin.setToolTip("Number of columns in the contact sheet grid.")
            self.cs_padding_spin.setToolTip("Padding between thumbnails.")
            self.cs_show_labels_check.setToolTip("Show layer labels below thumbnails.")
            self.cs_font_size_spin.setToolTip("Label font size.")
        else:
            reason = "Enable Contact Sheet to edit."
            self.cs_columns_spin.setToolTip(reason)
            self.cs_padding_spin.setToolTip(reason)
            self.cs_show_labels_check.setToolTip(reason)
            self.cs_font_size_spin.setToolTip(reason)

    def _on_cs_setting_changed(self, *args) -> None:
        """Handle contact sheet or preview setting changes with debouncing."""
        # Trigger preview update after a short delay to avoid thread churning
        self._cs_preview_timer.start(300)  # 300ms debounce

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
            if hasattr(self, "open_output_btn"):
                self.open_output_btn.setEnabled(False)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(False)
            if hasattr(self, "progress_folder_btn"):
                self.progress_folder_btn.setEnabled(False)
            return

        try:
            path = Path(output_path)
            enabled = path.exists() and path.is_file()
            self.play_btn.setEnabled(enabled)
            if hasattr(self, "open_output_btn"):
                self.open_output_btn.setEnabled(enabled)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(enabled)
            if hasattr(self, "progress_folder_btn"):
                self.progress_folder_btn.setEnabled(enabled)
        except Exception:
            self.play_btn.setEnabled(False)
            if hasattr(self, "open_output_btn"):
                self.open_output_btn.setEnabled(False)
            if hasattr(self, "progress_play_btn"):
                self.progress_play_btn.setEnabled(False)
            if hasattr(self, "progress_folder_btn"):
                self.progress_folder_btn.setEnabled(False)

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

    def _extract_frame_number(self, path: Path) -> Optional[int]:
        """Extract trailing frame number from a filename."""
        stem = path.stem
        if not stem:
            return None
        import re

        match = re.search(r"(\d+)$", stem)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

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
        self._last_detected_pattern = ""  # Force re-detection
        self._input_pattern_valid = False
        self._input_pattern_validated = False
        self._set_input_validation_state(None, "")
        self.sequence_info_label.setText("No sequence detected")
        self._update_convert_gate()

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
            logger.error(f"Preview error: {str(e)}")

    def _load_preview_from_path(self, sample_path: Path) -> None:
        """Load preview using an already resolved frame path."""
        if not sample_path.exists():
            QMessageBox.warning(self, "File Not Found", f"Frame file not found:\n{sample_path}")
            return

        preset, input_space = self._get_current_color_space_config()

        # Determine if we are in Contact Sheet mode
        cs_config = None
        layer = self.layer_combo.currentText()

        if self.cs_enable_check.isChecked():
            # Build config from UI
            layer_width = None
            layer_height = None
            if not self.keep_resolution_check.isChecked():
                layer_width = self.width_spin.value()
                layer_height = self.height_spin.value()

            cs_config = ContactSheetConfig(
                columns=self.cs_columns_spin.value(),
                thumbnail_width=None,
                padding=self.cs_padding_spin.value(),
                show_labels=self.cs_show_labels_check.isChecked(),
                font_size=self.cs_font_size_spin.value(),
                background_color=(0.1, 0.1, 0.1, 1.0),  # Dark background for preview
                layer_width=layer_width,
                layer_height=layer_height,
            )
            # Set layer to None to avoid "Layer not found" warnings when generator handles it
            layer = None

        burnin_config = None
        burnin_metadata = None
        if self.burnin_enable_check.isChecked():
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

            if burnin_elements:
                burnin_config = BurnInConfig(
                    elements=burnin_elements,
                    background_opacity=self.burnin_opacity_spin.value(),
                )
                frame_number = self._extract_frame_number(sample_path)
                burnin_metadata = {
                    "frame": frame_number if frame_number is not None else 0,
                    "file": sample_path.name,
                    "fps": float(self.fps_spin.value()),
                    "layer": layer or "RGBA",
                    "colorspace": input_space or "Unknown",
                }

        self._last_preview_path = sample_path
        preview_scale = self.preview_scale_spin.value() / 100.0
        self.preview_widget.load_preview(
            sample_path,
            preset,
            input_space=input_space,
            layer=layer,
            cs_config=cs_config,
            burnin_config=burnin_config,
            burnin_metadata=burnin_metadata,
            preview_scale=preview_scale,
        )

        if cs_config:
            logger.info(f"Loading Contact Sheet preview: {sample_path.name}")
        else:
            logger.info(f"Loading preview: {sample_path.name} (Layer: {layer})")

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

        # Skip if already detected the same pattern
        if pattern == self._last_detected_pattern:
            return
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

            # Auto-set frame range and adjust minimums to match sequence
            min_frame = sequence.frame_numbers[0]
            max_frame = sequence.frame_numbers[-1]

            # Set spinbox ranges to match the detected sequence
            self.start_frame_spin.setMinimum(min_frame)
            self.start_frame_spin.setMaximum(max_frame)
            self.start_frame_spin.setValue(min_frame)

            self.end_frame_spin.setMinimum(min_frame)
            self.end_frame_spin.setMaximum(max_frame)
            self.end_frame_spin.setValue(max_frame)

            # Create a loading state in the UI immediately
            self.sequence_info_label.setText(f"Detected {frame_count} frames (Loading metadata...)")

            # Disable Convert until valid metadata (FPS etc) is loaded
            self._input_pattern_valid = False
            self._input_pattern_validated = True  # We have validated the pattern string itself
            self._set_input_validation_state(None, "Loading metadata...")
            self._update_convert_gate()

            # Start async file info discovery (FPS, Color Space, Layers)
            sample_path = sequence.get_file_path(sequence.frame_numbers[0])
            self._start_file_info_discovery(
                sample_path, sequence, frame_count, frame_range, pattern
            )

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

            logger.info(f"Sequence detected: {frame_count} frames")
            logger.info(f"Auto-detected output: {output_path.name}")
            self._last_detected_pattern = pattern
            QApplication.processEvents()
            self.statusBar().showMessage(f"Sequence detected: {frame_count} frames")
            self._add_recent_pattern(pattern)
            # DO NOT set _input_pattern_valid = True yet, wait for metadata worker
            # self._input_pattern_valid = True
            # self._set_input_validation_state(True, "Input pattern looks valid.")
            self._update_convert_gate()
        except Exception as e:
            error_text = f"Error: {str(e)}"
            self.sequence_info_label.setText(error_text)
            logger.error(f"Sequence detection failed: {str(e)}")
            self.statusBar().showMessage("Sequence detection failed", 3000)
            self.preview_widget.clear_preview()
            self._input_pattern_valid = False
            self._set_input_validation_state(False, error_text)
            self._update_convert_gate()

    def _start_file_info_discovery(self, sample_path, sequence, frame_count, frame_range, pattern):
        """Start async file info discovery to avoid blocking UI."""
        # Stop any existing worker and DISCONNECT signals to prevent stale updates
        if self._file_info_worker:
            try:
                self._file_info_worker.file_info_ready.disconnect()
                self._file_info_worker.error_occurred.disconnect()
            except RuntimeError:
                # Signals might already be disconnected
                pass

            if self._file_info_worker.isRunning():
                self._file_info_worker.stop()
                # Do NOT wait() here, as it blocks the UI. Let it die in background.

        # Create and start new worker
        self._file_info_worker = FileInfoWorker(sample_path, self)
        self._file_info_worker.file_info_ready.connect(
            lambda path, info: self._on_file_info_ready(
                path, info, sample_path, sequence, frame_count, frame_range, pattern
            )
        )
        self._file_info_worker.error_occurred.connect(
            lambda path, error: self._on_file_info_error(
                path, error, sample_path, sequence, frame_count, frame_range, pattern
            )
        )
        self._file_info_worker.start()

        logger.info(f"Checking metadata: {sample_path.name}")

    def _on_file_info_ready(
        self, path_str, file_info, sample_path, sequence, frame_count, frame_range, pattern
    ):
        """Handle file info ready from background worker."""
        try:
            # Update color space
            detected_color_space = file_info.color_space
            if detected_color_space:
                logger.info(f"Auto-detected Color Space: {detected_color_space}")

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
                    self.color_space_combo.setEditText(detected_color_space)
            else:
                logger.info("No specific Color Space metadata found.")

            # Update layers
            layers = file_info.layers
            self.layer_combo.blockSignals(True)
            self.layer_combo.clear()
            self.layer_combo.addItems(layers)

            should_enable = len(layers) > 1 or layers[0] != "RGBA"
            if self.cs_enable_check.isChecked():
                self.layer_combo.setEnabled(False)
            else:
                self.layer_combo.setEnabled(should_enable)

            self.layer_combo.blockSignals(False)

            if len(layers) > 1:
                logger.info(f"Found {len(layers)} layers.")
                logger.debug(f"Found {len(layers)} layers: {', '.join(layers)}")

            # Update FPS if available
            if file_info.fps:
                self.fps_spin.setValue(round(file_info.fps, 3))
                logger.info(f"Auto-detected FPS from metadata: {file_info.fps}")
            else:
                logger.info("No FPS information found in metadata.")

            # Update resolution from metadata
            if file_info.width and file_info.height:
                self.width_spin.setValue(file_info.width)
                self.height_spin.setValue(file_info.height)
                logger.info(
                    f"Auto-detected resolution from metadata: {file_info.width}x{file_info.height}"
                )

            # Update sequence info with final text
            info_text = (
                f"Detected {frame_count} frames\n"
                f"Frame range: {frame_range}\n"
                f"Pattern: {Path(pattern).name}"
            )
            self.sequence_info_label.setText(info_text)

            # Load preview
            self._load_preview_from_path(sample_path)

            # NOW enable the Convert button
            self._input_pattern_valid = True
            self._set_input_validation_state(True, "Input pattern and metadata valid.")
            self._update_convert_gate()

        except Exception as e:
            # Handle error
            self.sequence_info_label.setText(f"Error applying metadata: {e}")
            self._input_pattern_valid = False
            self._set_input_validation_state(False, f"Metadata Error: {e}")
            self._update_convert_gate()
            self._load_preview_from_path(sample_path)

    def _on_file_info_error(
        self, path_str, error, sample_path, sequence, frame_count, frame_range, pattern
    ):
        """Handle file info discovery error."""
        logger.warning(f"File info discovery failed: {error}")

        # Set default values
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        self.layer_combo.addItems(["RGBA"])
        self.layer_combo.setEnabled(False)
        self.layer_combo.blockSignals(False)

        # Update sequence info
        info_text = (
            f"Detected {frame_count} frames\n"
            f"Frame range: {frame_range}\n"
            f"Pattern: {Path(pattern).name}"
        )
        self.sequence_info_label.setText(info_text)

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
            if hasattr(self, "prefetch_workers_spin"):
                config_builder.with_prefetch_workers(self.prefetch_workers_spin.value())

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
                logger.warning(fallback_warning)
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

            # Contact Sheet Mode
            if self.cs_enable_check.isChecked():
                layer_width = None
                layer_height = None
                if not self.keep_resolution_check.isChecked():
                    layer_width = self.width_spin.value()
                    layer_height = self.height_spin.value()

                cs_config = ContactSheetConfig(
                    columns=self.cs_columns_spin.value(),
                    padding=self.cs_padding_spin.value(),
                    show_labels=self.cs_show_labels_check.isChecked(),
                    font_size=self.cs_font_size_spin.value(),
                    layer_width=layer_width,
                    layer_height=layer_height,
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
            logger.error(f"Configuration error: {str(e)}")
            return

        # Update UI
        self._set_convert_button_state(True)
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self._set_status_icons("running")
        self._is_cancelling = False
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)
        if hasattr(self, "progress_folder_btn"):
            self.progress_folder_btn.setVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_label.setText("Starting conversion...")
        self.statusBar().showMessage("Starting conversion...")
        logger.info("=" * 50)
        logger.info("Starting conversion...")
        logger.info(f"Input: {config.input_pattern}")
        logger.info(f"Output: {config.output_path}")

        # Reset flag
        self._conversion_finished_flag = False

        # Start worker thread
        self.worker = ConversionWorker(config)
        self.worker.finished.connect(self._on_conversion_finished)
        self.worker.error.connect(self._on_conversion_error)
        self.worker.cancelled.connect(self._on_conversion_cancelled)
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
                logger.info("Conversion cancelled by user")
                self._set_convert_button_state(False)
                self._set_status_icons("cancelled")
                if hasattr(self, "progress_play_btn"):
                    self.progress_play_btn.setVisible(False)
                if hasattr(self, "progress_folder_btn"):
                    self.progress_folder_btn.setVisible(False)
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
        if hasattr(self, "progress_folder_btn"):
            self.progress_folder_btn.setVisible(True)
        self._update_play_button_state()

        output_path = Path(self.output_path_edit.text().strip()).absolute()
        self._ping_user("Conversion completed", f"Output: {output_path}")
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

    def _ping_user(self, title: str, message: str) -> None:
        """Notify the user that the conversion finished."""
        if self.tray_icon and self.tray_icon.isVisible():
            icon_enum = getattr(QSystemTrayIcon, "MessageIcon", None)
            info_icon = (
                icon_enum.Information if icon_enum is not None else QSystemTrayIcon.Information
            )
            self.tray_icon.showMessage(title, message, info_icon, 5000)
            return

        QApplication.beep()
        QApplication.alert(self, 3000)

    def _on_conversion_cancelled(self) -> None:
        """Handle conversion cancellation."""
        self._is_cancelling = False
        self.convert_btn.setEnabled(True)
        self._set_convert_button_state(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Conversion cancelled")
        self.statusBar().showMessage("Conversion cancelled", 5000)
        logger.info("Conversion cancelled")
        self._set_status_icons("cancelled")
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)
        if hasattr(self, "progress_folder_btn"):
            self.progress_folder_btn.setVisible(False)

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
        logger.error(f"Conversion error: {error_msg}")
        self._set_status_icons("error")
        if hasattr(self, "progress_play_btn"):
            self.progress_play_btn.setVisible(False)
        if hasattr(self, "progress_folder_btn"):
            self.progress_folder_btn.setVisible(False)

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

    def _open_output_folder(self) -> None:
        """Open the output folder in the system file browser."""
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            return

        path = Path(output_path).absolute()
        if not path.exists():
            QMessageBox.warning(self, "File Not Found", f"Output file does not exist:\n{path}")
            return

        folder = path.parent
        success = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not success:
            QMessageBox.warning(self, "Error", f"Could not open the output folder:\n{folder}")

    def _on_log_message(self, message: str) -> None:
        """Handle log message from worker."""
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.appendPlainText(message)
        else:
            self._startup_logs.append(message)

    def _save_settings(self) -> None:
        """Save current settings."""
        self.settings.setValue("fps", self.fps_spin.value())
        self.settings.setValue("keep_source_fps", self.keep_source_fps_check.isChecked())
        self.settings.setValue(
            "keep_source_frame_range", self.keep_source_frame_range_check.isChecked()
        )
        self.settings.setValue("width", self.width_spin.value())
        self.settings.setValue("height", self.height_spin.value())
        self.settings.setValue("codec_text", self.codec_combo.currentText())
        self.settings.setValue("keep_resolution", self.keep_resolution_check.isChecked())
        self.settings.setValue("quality", self.quality_slider.value())
        if hasattr(self, "prefetch_workers_spin"):
            self.settings.setValue("prefetch_workers", self.prefetch_workers_spin.value())
        self.settings.setValue("burnin_enable", self.burnin_enable_check.isChecked())
        self.settings.setValue("burnin_frame", self.burnin_frame_check.isChecked())
        self.settings.setValue("burnin_layer", self.burnin_layer_check.isChecked())
        self.settings.setValue("burnin_fps", self.burnin_fps_check.isChecked())
        self.settings.setValue("burnin_opacity", self.burnin_opacity_spin.value())

        # Contact Sheet settings
        self.settings.setValue("cs_enable", self.cs_enable_check.isChecked())
        self.settings.setValue("cs_columns", self.cs_columns_spin.value())
        self.settings.setValue("cs_padding", self.cs_padding_spin.value())
        self.settings.setValue("cs_show_labels", self.cs_show_labels_check.isChecked())
        self.settings.setValue("cs_font_size", self.cs_font_size_spin.value())
        self.settings.setValue("preview_scale", self.preview_scale_spin.value())

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
        self.keep_source_fps_check.setChecked(
            self.settings.value("keep_source_fps", True, type=bool)
        )
        self.keep_source_frame_range_check.setChecked(
            self.settings.value("keep_source_frame_range", True, type=bool)
        )
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
        if hasattr(self, "prefetch_workers_spin"):
            self.prefetch_workers_spin.setValue(
                self.settings.value("prefetch_workers", 2, type=int)
            )
        # Trigger initial toggle states
        self._on_keep_source_fps_toggled(self.keep_source_fps_check.isChecked())
        self._on_keep_frame_range_toggled(self.keep_source_frame_range_check.isChecked())
        self._on_keep_resolution_toggled(self.keep_resolution_check.isChecked())
        self._on_quality_changed(self.quality_slider.value())
        self._update_play_button_state()  # Call it here

        self.burnin_enable_check.setChecked(self.settings.value("burnin_enable", True, type=bool))
        self.burnin_frame_check.setChecked(self.settings.value("burnin_frame", True, type=bool))
        self.burnin_layer_check.setChecked(self.settings.value("burnin_layer", True, type=bool))
        self.burnin_fps_check.setChecked(self.settings.value("burnin_fps", True, type=bool))
        self.burnin_opacity_spin.setValue(self.settings.value("burnin_opacity", 30, type=int))

        # Contact Sheet settings
        self.cs_enable_check.setChecked(self.settings.value("cs_enable", False, type=bool))
        self.cs_columns_spin.setValue(self.settings.value("cs_columns", 4, type=int))
        self.cs_padding_spin.setValue(self.settings.value("cs_padding", 4, type=int))
        self.cs_show_labels_check.setChecked(self.settings.value("cs_show_labels", True, type=bool))
        self.cs_font_size_spin.setValue(self.settings.value("cs_font_size", 16, type=int))
        self.preview_scale_spin.setValue(self.settings.value("preview_scale", 75, type=int))
        # Initial refresh of enabled states
        self._on_burnin_enable_toggled(self.burnin_enable_check.isChecked())

        # Don't auto-expand on load, respect default collapsed state unless we add persistence for it.
        # But we do need to set the state of enabled/disabled widgets
        # Force a toggle event to run logic without flipping the checked state if possible,
        # or just call the handler manually
        self._on_cs_enable_toggled(self.cs_enable_check.isChecked())

        # If checked from settings, we might want to expand, but usually load_settings implies app startup
        # where we might want things collapsed? Let's leave it to the toggle logic which handles it.
        # Although _on_cs_enable_toggled WILL expand it if true. That's probably fine/desired.

        self._load_recent_patterns()
