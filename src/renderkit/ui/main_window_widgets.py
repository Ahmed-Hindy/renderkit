"""Shared UI widgets for the RenderKit main window."""

from renderkit.ui.qt_compat import (
    QComboBox,
    QDoubleSpinBox,
    QObject,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QStyleOptionSlider,
    Qt,
    Signal,
)


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
