#pragma once
#include <QPixmap>
#include <QString>

namespace rk {
inline constexpr int kSplashMinDurationMs = 1200;
QPixmap build_splash_pixmap(const QString &version, int width = 620, int height = 320);
} // namespace rk
