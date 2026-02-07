"""Splash screen rendering utilities for RenderKit."""

from __future__ import annotations

import time

from renderkit.ui.icons import icon_manager
from renderkit.ui.qt_compat import (
    QApplication,
    QColor,
    QFont,
    QPainter,
    QPixmap,
    QSplashScreen,
    Qt,
)

SPLASH_MIN_DURATION_MS = 1200


def compute_remaining_splash_ms(
    started_at: float, minimum_ms: int, now: float | None = None
) -> int:
    """Return remaining splash time to satisfy a minimum visible duration."""
    current = time.monotonic() if now is None else now
    elapsed_ms = int((current - started_at) * 1000)
    return max(0, minimum_ms - elapsed_ms)


def wait_for_minimum_splash_duration(
    app: QApplication,
    started_at: float,
    minimum_ms: int,
    step_ms: int = 16,
) -> None:
    """Keep the splash responsive until the minimum duration has elapsed."""
    safe_step_ms = max(1, step_ms)
    while True:
        remaining_ms = compute_remaining_splash_ms(started_at=started_at, minimum_ms=minimum_ms)
        if remaining_ms <= 0:
            return
        app.processEvents()
        sleep_ms = min(safe_step_ms, remaining_ms)
        time.sleep(sleep_ms / 1000)


def _interpolate_color(start: QColor, end: QColor, ratio: float) -> QColor:
    ratio = min(max(ratio, 0.0), 1.0)
    red = int(start.red() + (end.red() - start.red()) * ratio)
    green = int(start.green() + (end.green() - start.green()) * ratio)
    blue = int(start.blue() + (end.blue() - start.blue()) * ratio)
    return QColor(red, green, blue)


def build_splash_pixmap(version: str, width: int = 620, height: int = 320) -> QPixmap:
    """Build a branded dark splash pixmap."""
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#0b1117"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    top = QColor("#0b1117")
    bottom = QColor("#161b22")
    denominator = max(height - 1, 1)
    for y in range(height):
        ratio = y / denominator
        painter.setPen(_interpolate_color(top, bottom, ratio))
        painter.drawLine(0, y, width, y)

    card_margin = 26
    card_x = card_margin
    card_y = card_margin
    card_width = width - (card_margin * 2)
    card_height = height - (card_margin * 2)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(0, 0, 0, 90))
    painter.drawRoundedRect(card_x + 3, card_y + 5, card_width, card_height, 18, 18)
    painter.setBrush(QColor("#111923"))
    painter.drawRoundedRect(card_x, card_y, card_width, card_height, 18, 18)

    accent_height = 4
    accent_top = card_y + 10
    accent_start = QColor("#1f6feb")
    accent_end = QColor("#58a6ff")
    for x in range(card_x + 28, card_x + card_width - 28):
        ratio = (x - (card_x + 28)) / max(card_width - 56, 1)
        painter.setPen(_interpolate_color(accent_start, accent_end, ratio))
        painter.drawLine(x, accent_top, x, accent_top + accent_height)

    icon_size = 56
    icon_x = card_x + 30
    icon_y = card_y + 74
    text_x = card_x + 30

    icon = icon_manager.get_icon("loader", color="#58a6ff", size=icon_size)
    icon_pixmap = icon.pixmap(icon_size, icon_size)
    if not icon_pixmap.isNull():
        painter.drawPixmap(icon_x, icon_y, icon_pixmap)
        text_x = icon_x + icon_size + 18

    text_width = card_x + card_width - text_x - 30
    align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    title_font = QFont("Segoe UI", 30)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor("#e6edf3"))
    painter.drawText(text_x, card_y + 66, text_width, 52, align, "RenderKit")

    subtitle_font = QFont("Segoe UI", 12)
    painter.setFont(subtitle_font)
    painter.setPen(QColor("#9fb2c8"))
    painter.drawText(
        text_x,
        card_y + 120,
        text_width,
        30,
        align,
        "Image + Video Processor",
    )

    version_font = QFont("Consolas", 10)
    painter.setFont(version_font)
    painter.setPen(QColor("#7d8590"))
    painter.drawText(text_x, card_y + card_height - 74, text_width, 20, align, f"v{version}")

    footer_font = QFont("Segoe UI", 10)
    painter.setFont(footer_font)
    painter.setPen(QColor("#58a6ff"))
    painter.drawText(
        text_x,
        card_y + card_height - 44,
        text_width,
        24,
        align,
        "Loading workspace...",
    )

    painter.end()
    return pixmap


def create_splash_screen(version: str) -> QSplashScreen:
    """Create and configure the application splash screen."""
    splash = QSplashScreen(build_splash_pixmap(version))
    window_type = getattr(Qt, "WindowType", None)
    if window_type is not None:
        splash.setWindowFlag(window_type.FramelessWindowHint, True)
    else:
        splash.setWindowFlags(Qt.FramelessWindowHint)
    splash.setEnabled(False)
    return splash
