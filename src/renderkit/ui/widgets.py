"""Custom widgets for the UI."""

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import OpenImageIO as oiio

from renderkit.core.config import BurnInConfig, ContactSheetConfig
from renderkit.io.image_reader import ImageReaderFactory
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.color_space import ColorSpaceConverter, ColorSpacePreset
from renderkit.ui.icons import icon_manager
from renderkit.ui.qt_compat import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QImage,
    QLabel,
    QPixmap,
    QPoint,
    QPushButton,
    QScrollArea,
    QSize,
    Qt,
    QThread,
    QTimer,
    QVBoxLayout,
    QWidget,
    Signal,
)

logger = logging.getLogger(__name__)


class PreviewWorker(QThread):
    """Worker thread for loading preview image."""

    preview_ready = Signal(QPixmap)
    error = Signal(str)

    def __init__(
        self,
        file_path: Path,
        color_space: ColorSpacePreset,
        input_space: Optional[str] = None,
        layer: Optional[str] = None,
        cs_config: Optional[ContactSheetConfig] = None,
        burnin_config: Optional[BurnInConfig] = None,
        burnin_metadata: Optional[dict[str, Any]] = None,
        preview_scale: float = 1.0,
    ) -> None:
        """Initialize preview worker.

        Args:
            file_path: Path to image file
            color_space: Color space preset for conversion
            input_space: Optional explicit input color space
            layer: Optional EXR layer to load
            cs_config: Optional contact sheet configuration
            burnin_config: Optional burn-in configuration
            burnin_metadata: Optional burn-in metadata for token replacement
        """
        super().__init__()
        self.file_path = file_path
        self.color_space = color_space
        self.input_space = input_space
        self.layer = layer
        self.cs_config = cs_config
        self.burnin_config = burnin_config
        self.burnin_metadata = burnin_metadata
        self.preview_scale = preview_scale

    def run(self) -> None:
        """Load and process preview image."""
        try:
            if self.cs_config:
                from renderkit.processing.contact_sheet import ContactSheetGenerator

                generator = ContactSheetGenerator(self.cs_config)
                buf = generator.composite_layers(self.file_path)
            else:
                reader = ImageReaderFactory.create_reader(
                    self.file_path, image_cache=get_shared_image_cache()
                )
                buf = reader.read_imagebuf(self.file_path, layer=self.layer)

            # Apply preview scale
            if self.preview_scale < 1.0:
                spec = buf.spec()
                h, w = spec.height, spec.width
                new_w = max(1, int(w * self.preview_scale))
                new_h = max(1, int(h * self.preview_scale))
                from renderkit.processing.scaler import ImageScaler

                buf = ImageScaler.scale_buf(buf, width=new_w, height=new_h)

            # Convert color space
            converter = ColorSpaceConverter(self.color_space)
            buf = converter.convert_buf(buf, input_space=self.input_space)

            if self.burnin_config and self.burnin_metadata:
                try:
                    from renderkit.processing.burnin import BurnInProcessor

                    processor = BurnInProcessor()
                    buf = processor.apply_burnins(
                        buf,
                        self.burnin_metadata,
                        self.burnin_config,
                    )
                except Exception as e:
                    logger.warning(f"Preview burn-in failed: {e}")

            image = buf.get_pixels(oiio.FLOAT)
            if image is None or image.size == 0:
                raise ValueError("Failed to extract preview pixels.")
            spec = buf.spec()
            if image.ndim == 1:
                image = image.reshape((spec.height, spec.width, spec.nchannels))

            # Convert to uint8
            if image.dtype != np.uint8:
                image_f32 = image.astype(np.float32, copy=False)
                image = np.clip(image_f32, 0.0, 1.0)
                image = (image * np.float32(255.0)).astype(np.uint8)

            # Convert to QImage
            height, width = image.shape[:2]
            # Handle different Qt versions - format access differs
            # PySide6/PyQt6: QImage.Format.Format_RGB888
            # PySide2/PyQt5: QImage.Format_RGB888
            try:
                # Try PySide6/PyQt6 style
                rgb_format = getattr(QImage.Format, "Format_RGB888", None)
                rgba_format = getattr(QImage.Format, "Format_RGBA8888", None)
            except (AttributeError, TypeError):
                # Try PySide2/PyQt5 style
                rgb_format = getattr(QImage, "Format_RGB888", None)
                rgba_format = getattr(QImage, "Format_RGBA8888", None)

            # Fallback to direct attribute access if getattr failed
            if rgb_format is None:
                try:
                    rgb_format = QImage.Format.Format_RGB888
                except AttributeError:
                    rgb_format = QImage.Format_RGB888

            if rgba_format is None:
                try:
                    rgba_format = QImage.Format.Format_RGBA8888
                except AttributeError:
                    rgba_format = QImage.Format_RGBA8888

            if image.shape[2] == 3:
                # RGB
                q_image = QImage(image.data, width, height, width * 3, rgb_format)
            elif image.shape[2] == 4:
                # RGBA
                q_image = QImage(image.data, width, height, width * 4, rgba_format)
            else:
                raise ValueError(f"Unsupported image channels: {image.shape[2]}")

            # Create pixmap
            pixmap = QPixmap.fromImage(q_image)

            self.preview_ready.emit(pixmap)
        except Exception as e:
            self.error.emit(str(e))


class ZoomableScrollArea(QScrollArea):
    """A scroll area that ignores wheel events so they can be handled by the parent for zooming."""

    def wheelEvent(self, event) -> None:
        # Ignore wheel events to prevent scrolling, letting them bubble up to the parent window
        event.ignore()


class FullscreenPreviewWindow(QWidget):
    """A separate window for fullscreen preview with zoom and pan support."""

    def __init__(self, pixmap: QPixmap, title: str = "Fullscreen Preview"):
        """Initialize the fullscreen preview window.

        Args:
            pixmap: Pixmap to display
            title: Window title
        """
        super().__init__()
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self._pixmap = pixmap
        self._zoom_factor = 1.0  # 1.0 = Original size
        self._is_panning = False
        self._last_mouse_pos = QPoint()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Scroll area for zooming and panning
        self.scroll_area = ZoomableScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #111; border: none;")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)

        layout.addWidget(self.scroll_area, 1)

        # Footer for buttons
        self.footer = QFrame()
        self.footer.setObjectName("FullscreenFooter")
        self.footer.setStyleSheet("""
            #FullscreenFooter {
                background-color: #2b2b2b;
                border-top: 1px solid #444;
            }
        """)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(15, 8, 15, 8)

        self.res_label = QLabel()
        self.res_label.setStyleSheet("color: #888; font-family: Consolas; font-size: 11px;")
        footer_layout.addWidget(self.res_label)

        # Zoom label
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setStyleSheet("color: #aaa; margin-left: 15px; font-size: 11px;")
        footer_layout.addWidget(self.zoom_label)

        footer_layout.addStretch()

        self.copy_btn = QPushButton("Copy Image")
        self.copy_btn.setIcon(icon_manager.get_icon("check"))
        self.copy_btn.setMinimumHeight(28)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        footer_layout.addWidget(self.copy_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setIcon(icon_manager.get_icon("close"))
        self.close_btn.setMinimumHeight(28)
        self.close_btn.clicked.connect(self.close)
        footer_layout.addWidget(self.close_btn)

        layout.addWidget(self.footer, 0)

        # Initial fit
        QTimer.singleShot(10, self._fit_to_window)

    def _fit_to_window(self) -> None:
        """Scale image to fit the current window size."""
        if self._pixmap.isNull():
            return

        viewport_size = self.scroll_area.viewport().size()
        if viewport_size.width() <= 0 or viewport_size.height() <= 0:
            viewport_size = QSize(800, 600)

        w_scale = viewport_size.width() / self._pixmap.width()
        h_scale = viewport_size.height() / self._pixmap.height()
        self._zoom_factor = min(w_scale, h_scale) * 0.95  # Leave a small margin
        self._update_image()

    def _update_image(self) -> None:
        """Update the displayed image based on current zoom factor."""
        if self._pixmap.isNull():
            self.image_label.setText("No image")
            return

        new_width = int(self._pixmap.width() * self._zoom_factor)
        new_height = int(self._pixmap.height() * self._zoom_factor)

        # If image is smaller than viewport, use widget resizable
        # If larger, we need to manually size the label to trigger scrollbars
        self.image_label.setFixedSize(new_width, new_height)

        scaled = self._pixmap.scaled(
            new_width,
            new_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

        # Update labels
        self.res_label.setText(f"Resolution: {self._pixmap.width()} x {self._pixmap.height()}")
        self.zoom_label.setText(f"Zoom: {int(self._zoom_factor * 100)}%")

    def wheelEvent(self, event) -> None:
        """Handle mouse wheel for zooming."""
        # Calculate cursor position relative to the image
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        # Relative to viewport
        viewport_pos = self.scroll_area.viewport().mapFrom(self, pos)

        # Zoom to mouse logic
        old_zoom = self._zoom_factor
        angle = event.angleDelta().y()
        zoom_step = 1.15
        if angle > 0:
            self._zoom_factor *= zoom_step
        else:
            self._zoom_factor /= zoom_step

        # Clamp zoom: 1% to 1000%
        self._zoom_factor = max(0.01, min(self._zoom_factor, 10.0))

        # Update image
        self._update_image()

        # Adjust scrollbars to maintain position under mouse
        if old_zoom > 0:
            # Shift scrollbars
            factor = self._zoom_factor / old_zoom
            h_bar = self.scroll_area.horizontalScrollBar()
            v_bar = self.scroll_area.verticalScrollBar()

            new_h = int((h_bar.value() + viewport_pos.x()) * factor - viewport_pos.x())
            new_v = int((v_bar.value() + viewport_pos.y()) * factor - viewport_pos.y())

            h_bar.setValue(new_h)
            v_bar.setValue(new_v)

        event.accept()

    def mousePressEvent(self, event) -> None:
        """Start panning on middle click."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Perform panning."""
        if self._is_panning:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()

            h_bar = self.scroll_area.horizontalScrollBar()
            v_bar = self.scroll_area.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
            event.accept()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Stop panning."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.unsetCursor()
            event.accept()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_F:  # 'F' key to re-fit
            self._fit_to_window()
        super().keyPressEvent(event)

    def _copy_to_clipboard(self) -> None:
        """Copy current pixmap to clipboard."""
        QApplication.clipboard().setPixmap(self._pixmap)
        self.copy_btn.setText("Copied!")
        QTimer.singleShot(2000, lambda: self.copy_btn.setText("Copy Image"))


class PreviewWidget(QWidget):
    """Widget for displaying image preview."""

    thumbnail_requested = Signal(QPixmap)

    def __init__(self) -> None:
        """Initialize preview widget."""
        super().__init__()
        self._setup_ui()
        self._original_pixmap: Optional[QPixmap] = None
        self.worker: Optional[PreviewWorker] = None
        self._active_workers: list[PreviewWorker] = []
        self.fullscreen_win: Optional[FullscreenPreviewWindow] = None

    def _setup_ui(self) -> None:
        """Set up the preview UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Container for relative positioning
        self.container = QWidget()
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(240, 180)
        self.preview_label.setMaximumHeight(360)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        self.preview_label.setScaledContents(False)
        container_layout.addWidget(self.preview_label)

        # Floating expand button
        self.expand_btn = QPushButton(self.container)
        self.expand_btn.setIcon(icon_manager.get_icon("scan"))
        self.expand_btn.setFixedSize(30, 30)
        self.expand_btn.setToolTip("Fullscreen Preview")
        self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(45, 45, 45, 0.7);
                border: 1px solid #555;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 0.9);
                border-color: #0078d4;
            }
        """)
        self.expand_btn.clicked.connect(self._open_fullscreen)
        self.expand_btn.hide()

        self.export_btn = QPushButton(self.container)
        self.export_btn.setObjectName("PreviewExportButton")
        self.export_btn.setIcon(icon_manager.get_icon("file_image"))
        self.export_btn.setFixedSize(30, 30)
        self.export_btn.setToolTip("Export JPEG thumbnail")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self._request_thumbnail_export)
        self.export_btn.hide()

        layout.addWidget(self.container)

    def resizeEvent(self, event) -> None:
        """Scale preview pixmap to the current label size."""
        super().resizeEvent(event)
        self._update_scaled_pixmap()

        # Position expand button
        btn_x = self.container.width() - self.expand_btn.width() - 8
        btn_y = self.container.height() - self.expand_btn.height() - 8
        self.expand_btn.move(btn_x, btn_y)
        export_x = btn_x - self.export_btn.width() - 6
        self.export_btn.move(export_x, btn_y)

    def load_preview(
        self,
        file_path: Path,
        color_space: ColorSpacePreset,
        input_space: Optional[str] = None,
        layer: Optional[str] = None,
        cs_config: Optional[ContactSheetConfig] = None,
        burnin_config: Optional[BurnInConfig] = None,
        burnin_metadata: Optional[dict[str, Any]] = None,
        preview_scale: float = 1.0,
    ) -> None:
        """Load preview from file.

        Args:
            file_path: Path to file
            color_space: Color space preset
            input_space: Optional explicit input color space
            layer: Optional EXR layer
            cs_config: Optional contact sheet configuration
            burnin_config: Optional burn-in configuration
            burnin_metadata: Optional burn-in metadata for token replacement
            preview_scale: Scaling factor for preview performance
        """
        # Safety: Never terminate() a thread busy with I/O (like OIIO).
        # Instead, disconnect signals so its results are ignored, and let it finish.
        if self.worker and self.worker.isRunning():
            try:
                self.worker.preview_ready.disconnect(self._on_preview_ready)
                self.worker.error.disconnect(self._on_preview_error)
            except (RuntimeError, TypeError):
                # Signals might already be disconnected or worker deleted
                pass

            # Keep a reference alive until it finishes to avoid "QThread: Destroyed while still running"
            if self.worker not in self._active_workers:
                self._active_workers.append(self.worker)

            self.worker.finished.connect(self._on_worker_finished)
            self.worker.finished.connect(self.worker.deleteLater)

        self._original_pixmap = None
        self.preview_label.setText("Loading preview...")
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        self.worker = PreviewWorker(
            file_path,
            color_space,
            input_space=input_space,
            layer=layer,
            cs_config=cs_config,
            burnin_config=burnin_config,
            burnin_metadata=burnin_metadata,
            preview_scale=preview_scale,
        )
        self.worker.preview_ready.connect(self._on_preview_ready)
        self.worker.error.connect(self._on_preview_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_worker_finished(self) -> None:
        """Cleanup worker reference when finished."""
        worker = self.sender()
        if isinstance(worker, PreviewWorker) and worker in self._active_workers:
            self._active_workers.remove(worker)
        if worker == self.worker:
            self.worker = None

    def _on_preview_ready(self, pixmap: QPixmap) -> None:
        """Handle preview ready."""
        self._original_pixmap = pixmap
        self.preview_label.setText("")
        self._update_scaled_pixmap()
        self.expand_btn.show()
        self.export_btn.show()

    def _open_fullscreen(self) -> None:
        """Open fullscreen preview window."""
        if not self._original_pixmap:
            return

        self.fullscreen_win = FullscreenPreviewWindow(self._original_pixmap, "RenderKit - Preview")
        self.fullscreen_win.setWindowModality(Qt.WindowModality.NonModal)
        self.fullscreen_win.show()

    def _on_preview_error(self, error: str) -> None:
        """Handle preview error."""
        self._original_pixmap = None
        self.preview_label.setText(f"Preview error:\n{error}")
        self.expand_btn.hide()
        self.export_btn.hide()
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
        self._original_pixmap = None
        self.preview_label.clear()
        self.preview_label.setText("No preview")
        self.expand_btn.hide()
        self.export_btn.hide()
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #2b2b2b;
                color: #888;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

    def _request_thumbnail_export(self) -> None:
        """Emit request to export a preview thumbnail."""
        if not self._original_pixmap:
            return
        self.thumbnail_requested.emit(self._original_pixmap.copy())

    def _update_scaled_pixmap(self) -> None:
        """Scale stored pixmap to the label size, keeping aspect ratio."""
        if not self._original_pixmap:
            return

        target_size = self.preview_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        scaled = self._original_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
