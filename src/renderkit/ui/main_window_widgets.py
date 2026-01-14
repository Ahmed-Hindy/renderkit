"""Shared UI widgets for the RenderKit main window."""

from renderkit.ui.qt_compat import (
    QComboBox,
    QDoubleSpinBox,
    QObject,
    QSizePolicy,
    QSlider,
    QSpinBox,
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


class UiLogForwarder(QObject):
    """Signal-based forwarder for log messages."""

    message = Signal(str)
