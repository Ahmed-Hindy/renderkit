"""Shared UI widgets for the RenderKit main window."""

from typing import Any

from renderkit.ui.qt_compat import (
    QComboBox,
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
    Signal,
    qt_enum,
    resolve_enum_member,
)

COMBO_POPUP_OBJECT_NAME = "ComboBoxPopup"
_QT_LEFT_BUTTON = qt_enum("MouseButton", "LeftButton")
MOUSE_MOVE_EVENT = resolve_enum_member(QEvent, "Type", "MouseMove")
_POLICY_EXPANDING = resolve_enum_member(QSizePolicy, "Policy", "Expanding")
_POLICY_FIXED = resolve_enum_member(QSizePolicy, "Policy", "Fixed")
_ADJUST_TO_MIN_CONTENTS = resolve_enum_member(
    QComboBox, "SizeAdjustPolicy", "AdjustToMinimumContentsLengthWithIcon"
)


class NoWheelSpinBox(QSpinBox):
    """Spin box that ignores wheel events unless focused."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: Any) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Double spin box that ignores wheel events unless focused."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: Any) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class ComboPopupView(QListView):
    """List view that highlights combo popup rows as the mouse moves."""

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == MOUSE_MOVE_EVENT:
            self._highlight_index_at_event(event)
        return super().viewportEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        self._highlight_index_at_event(event)
        super().mouseMoveEvent(event)

    def _highlight_index_at_event(self, event: Any) -> None:
        position = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(position)
        if index.isValid():
            self.setCurrentIndex(index)


class NoWheelComboBox(QComboBox):
    """Combo box that ignores wheel events unless focused."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setView(ComboPopupView(self))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(_POLICY_EXPANDING, _POLICY_FIXED)
        self.setMinimumWidth(0)
        self._configure_popup_view()
        self.setSizeAdjustPolicy(_ADJUST_TO_MIN_CONTENTS)
        self.setMinimumContentsLength(12)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _configure_popup_view(self) -> None:
        view = self.view()
        view.setObjectName(COMBO_POPUP_OBJECT_NAME)
        view.setMouseTracking(True)
        viewport = view.viewport()
        if viewport is not None:
            viewport.setMouseTracking(True)

    def wheelEvent(self, event: Any) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class NoWheelSlider(QSlider):
    """Slider that ignores wheel events unless focused."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(_POLICY_EXPANDING, _POLICY_FIXED)
        self.setMinimumWidth(0)

    def wheelEvent(self, event: Any) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class JumpToClickSlider(NoWheelSlider):
    """Slider that jumps to the clicked position."""

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == _QT_LEFT_BUTTON:
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
                bool(getattr(option, "upsideDown", False)),
            )
            self.setValue(value)
        super().mousePressEvent(event)


class UiLogForwarder(QObject):
    """Signal-based forwarder for log messages."""

    message = Signal(str)
