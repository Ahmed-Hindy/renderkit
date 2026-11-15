#include "icon_manager.hpp"
#include <QPainter>
#include <QPixmap>
#include <QSvgRenderer>

static void init_icon_resources() {
    Q_INIT_RESOURCE(renderkit);
}

namespace {
const QHash<QString, QString> &icon_paths() {
    static const QHash<QString, QString> paths = {{"file_image", "file-image.svg"},
                                                  {"file_video", "file-video-camera.svg"},
                                                  {"file_folder", "folder-open.svg"},
                                                  {"play", "play.svg"},
                                                  {"pause", "pause.svg"},
                                                  {"stop", "square-pause.svg"},
                                                  {"convert", "wrench.svg"},
                                                  {"browse", "folder-open.svg"},
                                                  {"preview", "eye.svg"},
                                                  {"settings", "settings.svg"},
                                                  {"help", "info.svg"},
                                                  {"detect", "search.svg"},
                                                  {"scan", "scan.svg"},
                                                  {"close", "x.svg"},
                                                  {"warning", "triangle-alert.svg"},
                                                  {"error", "circle-alert.svg"},
                                                  {"info", "info.svg"},
                                                  {"ban", "ban.svg"},
                                                  {"check", "check.svg"},
                                                  {"loader", "loader.svg"},
                                                  {"link_on", "link-2.svg"},
                                                  {"link_off", "link-2-off.svg"}};
    return paths;
}
} // namespace
namespace rk {
bool IconManager::has_icon(const QString &name) const {
    return icon_paths().contains(name);
}
QIcon IconManager::icon(const QString &name, const QColor &color, int size) {
    if (size <= 0)
        return {};
    static const bool resources_ready = [] {
        init_icon_resources();
        return true;
    }();
    (void)resources_ready;
    const QString key = name + "_" + color.name(QColor::HexArgb) + "_" + QString::number(size);
    if (cache_.contains(key))
        return cache_.value(key);
    QPixmap pixmap(size, size);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    QSvgRenderer renderer(":/icons/" + icon_paths().value(name, "info.svg"));
    if (renderer.isValid()) {
        renderer.render(&painter);
        painter.setCompositionMode(QPainter::CompositionMode_SourceIn);
        painter.fillRect(pixmap.rect(), color);
    } else {
        painter.setPen(Qt::NoPen);
        painter.setBrush(color);
        painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 2, 2);
    }
    painter.end();
    QIcon result(pixmap);
    cache_.insert(key, result);
    return result;
}
} // namespace rk
