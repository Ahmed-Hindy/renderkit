#include "splash_screen.hpp"
#include "icon_manager.hpp"
#include <QFont>
#include <QLinearGradient>
#include <QPainter>

namespace rk {
QPixmap build_splash_pixmap(const QString &version, int width, int height) {
    QPixmap pixmap(width, height);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    QLinearGradient background(0, 0, 0, height);
    background.setColorAt(0, QColor("#0b1117"));
    background.setColorAt(1, QColor("#161b22"));
    painter.fillRect(pixmap.rect(), background);
    QRect card(26, 26, width - 52, height - 52);
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor("#111923"));
    painter.drawRoundedRect(card, 18, 18);
    QLinearGradient accent(card.left(), 0, card.right(), 0);
    accent.setColorAt(0, QColor("#1f6feb"));
    accent.setColorAt(1, QColor("#58a6ff"));
    painter.fillRect(QRect(card.left() + 18, card.top(), card.width() - 36, 4), accent);
    IconManager icons;
    painter.drawPixmap(card.left() + 34, card.top() + 55,
                       icons.icon("loader", QColor("#58a6ff"), 56).pixmap(56, 56));
    painter.setPen(QColor("#e6edf3"));
    QFont title("Segoe UI", 30, QFont::Bold);
    painter.setFont(title);
    painter.drawText(card.left() + 110, card.top() + 100, "RenderKit");
    painter.setPen(QColor("#9fb2c8"));
    painter.setFont(QFont("Segoe UI", 12));
    painter.drawText(card.left() + 112, card.top() + 129, "Image + Video Processor");
    painter.setPen(QColor("#7d8590"));
    painter.setFont(QFont("Consolas", 10));
    painter.drawText(card.left() + 36, card.bottom() - 50, "v" + version);
    painter.setPen(QColor("#58a6ff"));
    painter.setFont(QFont("Segoe UI", 10));
    painter.drawText(card.left() + 36, card.bottom() - 25, "Loading workspace...");
    return pixmap;
}
} // namespace rk
