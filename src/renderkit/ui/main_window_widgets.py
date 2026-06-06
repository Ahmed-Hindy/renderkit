"""Shared UI widgets for the RenderKit main window."""

from renderkit.ui.qt_compat import (
    QComboBox,
    QCursor,
    QDoubleSpinBox,
    QEvent,
    QListView,
    QObject,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    Qt,
    QTimer,
    Signal,
)

COMBO_POPUP_OBJECT_NAME = "ComboBoxPopup"
COMBO_POPUP_STYLESHEET = """
QListView,
QAbstractItemView {
    background-color: #0d1117;
    color: #e6edf3;
    selection-background-color: #4493f8;
    selection-color: #e6edf3;
    border: 1px solid #30363db3;
}

QListView::item,
QAbstractItemView::item {
    padding: 4px 8px;
}

QListView::item:selected,
QAbstractItemView::item:selected {
    background-color: #4493f8;
    color: #e6edf3;
}
"""
try:
    MOUSE_MOVE_EVENT = QEvent.Type.MouseMove
except AttributeError:
    MOUSE_MOVE_EVENT = QEvent.MouseMove


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


class ComboPopupView(QListView):
    """List view that keeps combo popup highlight under the cursor."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(16)
        self._hover_timer.timeout.connect(self._highlight_index_under_cursor)

    def start_hover_tracking(self) -> None:
        self._highlight_index_under_cursor()
        self._hover_timer.start()

    def stop_hover_tracking(self) -> None:
        self._hover_timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.start_hover_tracking()

    def hideEvent(self, event) -> None:
        self.stop_hover_tracking()
        super().hideEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == MOUSE_MOVE_EVENT:
            self._highlight_index_at_event(event)
        return super().viewportEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._highlight_index_at_event(event)
        super().mouseMoveEvent(event)

    def _highlight_index_at_event(self, event) -> None:
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)
        if index.isValid():
            self.setCurrentIndex(index)

    def _highlight_index_under_cursor(self) -> None:
        viewport = self.viewport()
        position = viewport.mapFromGlobal(QCursor.pos())
        if not viewport.rect().contains(position):
            return
        index = self.indexAt(position)
        if index.isValid():
            self.setCurrentIndex(index)


class NoWheelComboBox(QComboBox):
    """Combo box that ignores wheel events unless focused."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setView(ComboPopupView(self))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self._configure_popup_view()
        size_adjust_policy = getattr(QComboBox, "SizeAdjustPolicy", None)
        if size_adjust_policy is not None:
            self.setSizeAdjustPolicy(size_adjust_policy.AdjustToMinimumContentsLengthWithIcon)
        else:
            self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _configure_popup_view(self) -> None:
        view = self.view()
        view.setObjectName(COMBO_POPUP_OBJECT_NAME)
        view.setMouseTracking(True)
        view.setStyleSheet(COMBO_POPUP_STYLESHEET)
        viewport = view.viewport()
        if viewport is not None:
            viewport.setMouseTracking(True)

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)

    def showPopup(self) -> None:
        super().showPopup()
        view = self.view()
        if isinstance(view, ComboPopupView):
            view.start_hover_tracking()

    def hidePopup(self) -> None:
        view = self.view()
        if isinstance(view, ComboPopupView):
            view.stop_hover_tracking()
        super().hidePopup()


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


class JumpToClickSlider(NoWheelSlider):
    """Slider that jumps to the clicked position."""

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            position = event.position().toPoint() if hasattr(event, "position") else event.pos()

            groove = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderGroove,
                self,
            )
            handle = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderHandle,
                self,
            )

            if self.orientation() == Qt.Orientation.Horizontal:
                slider_min = groove.x()
                slider_max = groove.right() - handle.width() + 1
                pos = position.x()
            else:
                slider_min = groove.y()
                slider_max = groove.bottom() - handle.height() + 1
                pos = position.y()

            span = max(1, slider_max - slider_min)
            value = QStyle.sliderValueFromPosition(
                self.minimum(),
                self.maximum(),
                int(pos - slider_min),
                span,
                option.upsideDown,
            )
            self.setValue(value)
        super().mousePressEvent(event)


class UiLogForwarder(QObject):
    """Signal-based forwarder for log messages."""

    message = Signal(str)
