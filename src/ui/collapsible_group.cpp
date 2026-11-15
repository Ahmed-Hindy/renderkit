#include "collapsible_group.hpp"
#include <QHBoxLayout>
#include <QLabel>
#include <QToolButton>
#include <QVBoxLayout>

namespace rk {
CollapsibleGroup::CollapsibleGroup(const QString &title, bool expanded, QWidget *parent)
    : QWidget(parent), header_(new QToolButton(this)), content_(new QWidget(this)),
      content_layout_(new QVBoxLayout(content_)) {
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);
    header_->setObjectName("CollapsibleHeader");
    header_->setCheckable(true);
    header_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    header_->setMinimumHeight(36);
    auto *header_layout = new QHBoxLayout(header_);
    auto *indicator = new QLabel(header_);
    indicator->setObjectName("CollapsibleIndicator");
    auto *label = new QLabel(title, header_);
    label->setObjectName("CollapsibleTitle");
    header_layout->addWidget(indicator);
    header_layout->addWidget(label, 1);
    content_->setObjectName("CollapsibleContent");
    layout->addWidget(header_);
    layout->addWidget(content_);
    connect(header_, &QToolButton::toggled, this, [this, indicator](bool checked) {
        indicator->setText(checked ? QString::fromUtf8("▼") : QString::fromUtf8("▶"));
        content_->setVisible(checked);
    });
    set_expanded(expanded);
    // A newly checkable button starts unchecked, so initialize the collapsed indicator explicitly.
    if (!expanded) {
        indicator->setText(QString::fromUtf8("▶"));
        content_->hide();
    }
}
void CollapsibleGroup::set_expanded(bool expanded) {
    header_->setChecked(expanded);
}
bool CollapsibleGroup::is_expanded() const {
    return header_->isChecked();
}
} // namespace rk
