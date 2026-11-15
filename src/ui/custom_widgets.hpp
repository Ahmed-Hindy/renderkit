#pragma once
#include <QComboBox>
#include <QDoubleSpinBox>
#include <QLineEdit>
#include <QListView>
#include <QMouseEvent>
#include <QSlider>
#include <QSpinBox>
#include <QStyle>
#include <QStyleOptionSlider>
#include <QWheelEvent>

namespace rk {
class NoWheelSpinBox : public QSpinBox {
  public:
    using QSpinBox::QSpinBox;

  protected:
    void wheelEvent(QWheelEvent *event) override {
        if (!hasFocus())
            event->ignore();
        else
            QSpinBox::wheelEvent(event);
    }
};
class NoWheelDoubleSpinBox : public QDoubleSpinBox {
  public:
    using QDoubleSpinBox::QDoubleSpinBox;

  protected:
    void wheelEvent(QWheelEvent *event) override {
        if (!hasFocus())
            event->ignore();
        else
            QDoubleSpinBox::wheelEvent(event);
    }
};
class NoWheelComboBox : public QComboBox {
  public:
    explicit NoWheelComboBox(QWidget *parent = nullptr) : QComboBox(parent) {
        auto *popup = new QListView(this);
        popup->setObjectName("ComboBoxPopup");
        setView(popup);
        setSizeAdjustPolicy(QComboBox::AdjustToMinimumContentsLengthWithIcon);
        setMinimumContentsLength(12);
    }

  protected:
    void wheelEvent(QWheelEvent *event) override {
        if (!hasFocus() && !(isEditable() && lineEdit() && lineEdit()->hasFocus()))
            event->ignore();
        else
            QComboBox::wheelEvent(event);
    }
};
class NoWheelSlider : public QSlider {
  public:
    using QSlider::QSlider;

  protected:
    void wheelEvent(QWheelEvent *event) override {
        if (!hasFocus())
            event->ignore();
        else
            QSlider::wheelEvent(event);
    }
};
class JumpToClickSlider : public NoWheelSlider {
  public:
    using NoWheelSlider::NoWheelSlider;

  protected:
    void mousePressEvent(QMouseEvent *event) override {
        if (event->button() == Qt::LeftButton) {
            QStyleOptionSlider option;
            initStyleOption(&option);
            const auto groove =
                style()->subControlRect(QStyle::CC_Slider, &option, QStyle::SC_SliderGroove, this);
            const auto handle =
                style()->subControlRect(QStyle::CC_Slider, &option, QStyle::SC_SliderHandle, this);
            const int length = orientation() == Qt::Horizontal ? handle.width() : handle.height();
            const int span =
                (orientation() == Qt::Horizontal ? groove.width() : groove.height()) - length;
            const int position = orientation() == Qt::Horizontal
                                     ? event->pos().x() - groove.x() - length / 2
                                     : event->pos().y() - groove.y() - length / 2;
            if (span > 0)
                setValue(QStyle::sliderValueFromPosition(minimum(), maximum(), position, span,
                                                         option.upsideDown));
        }
        NoWheelSlider::mousePressEvent(event);
    }
};
} // namespace rk
