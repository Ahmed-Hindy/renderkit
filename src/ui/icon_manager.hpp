#pragma once
#include <QColor>
#include <QHash>
#include <QIcon>
#include <QString>

namespace rk {
class IconManager {
  public:
    QIcon icon(const QString &name, const QColor &color = QColor("#e6edf3"), int size = 16);
    bool has_icon(const QString &name) const;

  private:
    QHash<QString, QIcon> cache_;
};
} // namespace rk
