"""Collapsible group box widget for accordion-style layouts."""

from renderkit.ui.qt_compat import (
    QFrame,
    QHBoxLayout,
    QLabel,
    Qt,
    QVBoxLayout,
    QWidget,
)


class CollapsibleGroupBox(QWidget):
    """A collapsible group box with animated expand/collapse."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        """Initialize the collapsible group box.

        Args:
            title: The title displayed in the header
            parent: Parent widget
        """
        super().__init__(parent)
        self.title = title
        self._is_collapsed = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        self.header = QFrame()
        self.header.setObjectName("CollapsibleHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        # Toggle indicator
        self.indicator = QLabel("▼")
        self.indicator.setObjectName("CollapsibleIndicator")
        header_layout.addWidget(self.indicator)

        # Title label
        title_label = QLabel(self.title)
        title_label.setObjectName("CollapsibleTitle")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Make header clickable
        self.header.mousePressEvent = lambda event: self.toggle()

        main_layout.addWidget(self.header)

        # Content container
        self.content_widget = QWidget()
        self.content_widget.setObjectName("CollapsibleContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addWidget(self.content_widget)

    def set_content_layout(self, layout: QVBoxLayout) -> None:
        """Set the content layout for this collapsible group.

        Args:
            layout: The layout containing the group's content
        """
        # Clear existing layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new content
        widget = QWidget()
        widget.setLayout(layout)
        self.content_layout.addWidget(widget)

    def toggle(self) -> None:
        """Toggle the collapsed state."""
        self._is_collapsed = not self._is_collapsed
        self.content_widget.setVisible(not self._is_collapsed)
        self.indicator.setText("▶" if self._is_collapsed else "▼")

    def set_collapsed(self, collapsed: bool) -> None:
        """Set the collapsed state.

        Args:
            collapsed: True to collapse, False to expand
        """
        if self._is_collapsed != collapsed:
            self.toggle()

    def is_collapsed(self) -> bool:
        """Check if the group is currently collapsed.

        Returns:
            True if collapsed, False if expanded
        """
        return self._is_collapsed
