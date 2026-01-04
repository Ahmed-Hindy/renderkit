# src/renderkit/ui/exr_converter_prototype_window.py


import sys

from renderkit.ui.qt_compat import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    Qt,
    QVBoxLayout,
    QWidget,
)


class ExrConverterPrototypeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("EXR Converter (Prototype)")

        self.setMinimumSize(1100, 720)
        self.setProperty("theme", "dark")  # Default to dark mode

        central = QWidget()

        self.setCentralWidget(central)

        root = QHBoxLayout(central)

        root.setContentsMargins(0, 0, 0, 0)

        root.setSpacing(0)

        sidebar = self._build_sidebar()

        root.addWidget(sidebar)

        right = QWidget()

        right_layout = QVBoxLayout(right)

        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.setSpacing(0)

        root.addWidget(right)

        header = self._build_header()

        right_layout.addWidget(header)

        scroll = QScrollArea()

        scroll.setWidgetResizable(True)

        scroll.setFrameShape(QFrame.Shape.NoFrame)

        right_layout.addWidget(scroll, 1)

        scroll_body = QWidget()

        scroll.setWidget(scroll_body)

        body_layout = QVBoxLayout(scroll_body)

        body_layout.setContentsMargins(24, 24, 24, 24)

        body_layout.setSpacing(16)

        body_layout.addWidget(self._build_dropzone())

        body_layout.addWidget(self._build_info_grid())

        body_layout.addWidget(self._build_settings())

        body_layout.addWidget(self._build_log())

        body_layout.addStretch(1)

        footer = self._build_footer()

        right_layout.addWidget(footer)

        self._apply_styles()

    def _build_sidebar(self) -> QWidget:
        w = QFrame()

        w.setObjectName("Sidebar")

        w.setFixedWidth(256)

        layout = QVBoxLayout(w)

        layout.setContentsMargins(12, 12, 12, 12)

        layout.setSpacing(12)

        top = QFrame()

        top.setObjectName("SidebarTop")

        top_layout = QVBoxLayout(top)

        top_layout.setContentsMargins(12, 12, 12, 12)

        top_layout.setSpacing(2)

        title = QLabel("EXR Converter")

        title.setObjectName("SidebarTitle")

        subtitle = QLabel("Sequence to MP4")

        subtitle.setObjectName("SidebarSubtitle")

        top_layout.addWidget(title)

        top_layout.addWidget(subtitle)

        layout.addWidget(top)

        nav = QFrame()

        nav_layout = QVBoxLayout(nav)

        nav_layout.setContentsMargins(0, 0, 0, 0)

        nav_layout.setSpacing(6)

        self.btn_convert = QPushButton("Convert")

        self.btn_convert.setObjectName("NavActive")

        self.btn_history = QPushButton("History")

        self.btn_batch = QPushButton("Batch Process")

        self.btn_presets = QPushButton("Presets")

        for b in [self.btn_convert, self.btn_history, self.btn_batch, self.btn_presets]:
            b.setCursor(Qt.CursorShape.PointingHandCursor)

            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            nav_layout.addWidget(b)

        nav_layout.addStretch(1)

        layout.addWidget(nav, 1)

        bottom = QFrame()

        bottom_layout = QVBoxLayout(bottom)

        bottom_layout.setContentsMargins(0, 0, 0, 0)

        bottom_layout.setSpacing(6)

        self.btn_settings = QPushButton("Settings")

        self.btn_about = QPushButton("About")

        for b in [self.btn_settings, self.btn_about]:
            b.setCursor(Qt.CursorShape.PointingHandCursor)

            bottom_layout.addWidget(b)

        layout.addWidget(bottom)

        return w

    def _build_header(self) -> QWidget:
        w = QFrame()

        w.setObjectName("Header")

        w.setFixedHeight(56)

        layout = QHBoxLayout(w)

        layout.setContentsMargins(24, 8, 24, 8)

        layout.setSpacing(12)

        title = QLabel("EXR Sequence Converter")

        title.setObjectName("HeaderTitle")

        layout.addWidget(title)

        badge = QLabel("Ready")

        badge.setObjectName("BadgeReady")

        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(badge)

        layout.addStretch(1)

        help_btn = QPushButton("Help")

        help_btn.setObjectName("HeaderButton")

        notif_btn = QPushButton("Notifications")

        notif_btn.setObjectName("HeaderButton")

        theme_btn = QPushButton("Toggle Theme")
        theme_btn.setObjectName("SecondaryButton")
        theme_btn.clicked.connect(self._toggle_theme)

        layout.addWidget(theme_btn)
        layout.addWidget(help_btn)
        layout.addWidget(notif_btn)

        return w

    def _toggle_theme(self) -> None:
        current = self.property("theme")
        new_theme = "light" if current == "dark" else "dark"
        self.setProperty("theme", new_theme)

        # Refresh style
        self.style().unpolish(self)
        self.style().polish(self)
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)

        # Also need to manually update some visuals if needed,
        # but polishing should trigger QSS re-evaluation.
        self.update()

    def _build_dropzone(self) -> QWidget:
        w = QFrame()

        w.setObjectName("Dropzone")

        layout = QVBoxLayout(w)

        layout.setContentsMargins(24, 24, 24, 24)

        layout.setSpacing(6)

        t1 = QLabel("Drag and drop your EXR files")

        t1.setObjectName("DropzoneTitle")

        t2 = QLabel("or click to browse from your computer")

        t2.setObjectName("DropzoneSubtitle")

        t3 = QLabel("Supports .exr sequence files • Max 10,000 frames")

        t3.setObjectName("DropzoneHint")

        layout.addWidget(t1, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(t2, 0, Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(t3, 0, Qt.AlignmentFlag.AlignHCenter)

        return w

    def _build_info_grid(self) -> QWidget:
        w = QWidget()

        layout = QHBoxLayout(w)

        layout.setContentsMargins(0, 0, 0, 0)

        layout.setSpacing(16)

        layout.addWidget(
            self._build_card(
                "Sequence Info",
                [
                    ("File Pattern", "sc01_render_v03.exr"),
                    ("Frame Range", "1001 - 1120 (120f)"),
                    ("Resolution", "1920 x 1080"),
                    ("Input Colorspace", "ACEScg"),
                ],
            )
        )

        layout.addWidget(
            self._build_card(
                "Output Summary",
                [
                    ("Format", "MP4 (H.264)"),
                    ("Frame Rate", "24 fps"),
                    ("Quality", "High (CRF 18)"),
                    ("Est. Size", "-- MB"),
                ],
            )
        )

        return w

    def _build_card(self, title: str, rows: list[tuple[str, str]]) -> QWidget:
        card = QFrame()

        card.setObjectName("Card")

        layout = QVBoxLayout(card)

        layout.setContentsMargins(16, 16, 16, 16)

        layout.setSpacing(10)

        hdr = QLabel(title)

        hdr.setObjectName("CardTitle")

        layout.addWidget(hdr)

        for k, v in rows:
            row = QWidget()

            row_l = QHBoxLayout(row)

            row_l.setContentsMargins(0, 0, 0, 0)

            row_l.setSpacing(8)

            lk = QLabel(k)

            lk.setObjectName("RowKey")

            lv = QLabel(v)

            lv.setObjectName("RowValue")

            lv.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_l.addWidget(lk, 1)

            row_l.addWidget(lv, 1)

            layout.addWidget(row)

        layout.addStretch(1)
        return card

    def _build_settings(self) -> QWidget:
        card = QFrame()

        card.setObjectName("Card")

        layout = QVBoxLayout(card)

        layout.setContentsMargins(16, 16, 16, 16)

        layout.setSpacing(12)

        title = QLabel("Conversion Settings")

        title.setObjectName("CardHeaderBig")

        layout.addWidget(title)

        grid = QWidget()

        g = QHBoxLayout(grid)

        g.setContentsMargins(0, 0, 0, 0)

        g.setSpacing(16)

        left = QWidget()

        left_l = QVBoxLayout(left)

        left_l.setContentsMargins(0, 0, 0, 0)

        left_l.setSpacing(12)

        right = QWidget()

        right_l = QVBoxLayout(right)

        right_l.setContentsMargins(0, 0, 0, 0)

        right_l.setSpacing(12)

        self.fps_combo = QComboBox()

        self.fps_combo.addItems(["23.976", "24", "25", "30", "60"])

        self.fps_combo.setCurrentText("24")

        self.codec_combo = QComboBox()

        self.codec_combo.addItems(["H.264 (libx264)", "H.265 (HEVC)", "ProRes 422", "DNxHD"])

        self.quality_combo = QComboBox()

        self.quality_combo.addItems(
            ["Lossless", "High Quality", "Medium Quality", "Low Quality (Proxy)"]
        )

        self.quality_combo.setCurrentText("High Quality")

        self.bitrate_edit = QLineEdit()

        self.bitrate_edit.setPlaceholderText("Auto")

        left_l.addWidget(self._field("Frame Rate (fps)", self.fps_combo))

        left_l.addWidget(self._field("Codec", self.codec_combo))

        left_l.addStretch(1)

        right_l.addWidget(self._field("Quality Preset", self.quality_combo))

        right_l.addWidget(self._field("Bitrate Limit (Mbps)", self.bitrate_edit))

        right_l.addStretch(1)

        g.addWidget(left, 1)

        g.addWidget(right, 1)

        layout.addWidget(grid)

        return card

    def _field(self, label: str, widget: QWidget) -> QWidget:
        w = QWidget()
        vboxlayout = QVBoxLayout(w)
        vboxlayout.setContentsMargins(0, 0, 0, 0)
        vboxlayout.setSpacing(6)

        lab = QLabel(label)

        lab.setObjectName("FieldLabel")
        vboxlayout.addWidget(lab)
        vboxlayout.addWidget(widget)

        widget.setObjectName("FieldControl")

        return w

    def _build_log(self) -> QWidget:
        card = QFrame()

        card.setObjectName("LogCard")

        layout = QVBoxLayout(card)

        layout.setContentsMargins(12, 12, 12, 12)

        layout.setSpacing(8)

        hdr = QLabel("Log Output")

        hdr.setObjectName("LogTitle")

        layout.addWidget(hdr)

        self.log = QPlainTextEdit()

        self.log.setReadOnly(True)

        self.log.setPlainText(
            "INFO: Application started v2.1.0\n"
            "INFO: GPU acceleration enabled (Metal)\n"
            "READY: Waiting for input sequence...\n"
        )

        self.log.setObjectName("LogBox")

        self.log.setFixedHeight(90)

        layout.addWidget(self.log)

        return card

    def _build_footer(self) -> QWidget:
        w = QFrame()

        w.setObjectName("Footer")

        w.setFixedHeight(56)

        layout = QHBoxLayout(w)

        layout.setContentsMargins(16, 8, 16, 8)

        layout.setSpacing(12)

        left = QLabel("Ready to convert")

        left.setObjectName("FooterLeft")

        layout.addWidget(left, 1)

        self.start_btn = QPushButton("Start Conversion")

        self.start_btn.setObjectName("PrimaryButton")

        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.start_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        right = QWidget()

        r = QHBoxLayout(right)

        r.setContentsMargins(0, 0, 0, 0)

        r.setSpacing(10)

        pct = QLabel("0%")

        pct.setObjectName("FooterPercent")

        r.addWidget(pct)

        pause = QPushButton("Pause")

        pause.setObjectName("IconButton")

        stop = QPushButton("Stop")

        stop.setObjectName("IconButton")

        r.addWidget(pause)

        r.addWidget(stop)

        layout.addWidget(right, 1, Qt.AlignmentFlag.AlignRight)

        return w

    def _apply_styles(self) -> None:
        from pathlib import Path

        qss_path = Path(__file__).parent / "stylesheets" / "kitsu_theme.qss"
        if qss_path.exists():
            with open(qss_path) as f:
                self.setStyleSheet(f.read())


def run_prototype_ui() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("RenderKit - Prototype")
    # Set modern style
    app.setStyle("Fusion")

    # Neutralize system palette overrides to prevent purple "leaks"
    from renderkit.ui.qt_compat import QPalette

    palette = app.palette()
    # Explicitly set accents to standard neutral/blue if they were overridden by system
    palette.setColor(QPalette.ColorRole.Highlight, Qt.GlobalColor.blue)
    app.setPalette(palette)

    w = ExrConverterPrototypeWindow()

    w.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_prototype_ui()
