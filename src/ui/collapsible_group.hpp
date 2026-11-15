#pragma once
#include <QWidget>

class QVBoxLayout;
class QToolButton;
namespace rk {
class CollapsibleGroup : public QWidget {
  public:
    explicit CollapsibleGroup(const QString &title, bool expanded = false,
                              QWidget *parent = nullptr);
    QVBoxLayout *content_layout() const {
        return content_layout_;
    }
    void set_expanded(bool expanded);
    bool is_expanded() const;

  private:
    QToolButton *header_;
    QWidget *content_;
    QVBoxLayout *content_layout_;
};
} // namespace rk
