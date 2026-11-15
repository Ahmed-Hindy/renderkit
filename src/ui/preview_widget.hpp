#pragma once
#include <QImage>
#include <QWidget>

class QLabel;
class QPushButton;
namespace rk {
class PreviewWidget : public QWidget {
  public:
    explicit PreviewWidget(QWidget *parent = nullptr);
    void set_image(const QImage &image);
    void set_message(const QString &message);
    void set_source_path(const QString &path) {
        source_path_ = path;
    }
    void set_output_path(const QString &path) {
        output_path_ = path;
    }

  protected:
    void resizeEvent(QResizeEvent *event) override;

  private:
    void refresh();
    QLabel *image_label_;
    QPushButton *expand_, *export_;
    QImage image_;
    QString source_path_;
    QString output_path_;
};
} // namespace rk
