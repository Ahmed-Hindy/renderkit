#include "preview_widget.hpp"
#include "core/sequence_names.hpp"
#include "icon_manager.hpp"
#include <QApplication>
#include <QClipboard>
#include <QDialog>
#include <QDir>
#include <QFileInfo>
#include <QGraphicsPixmapItem>
#include <QGraphicsScene>
#include <QGraphicsView>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QMessageBox>
#include <QMouseEvent>
#include <QPushButton>
#include <QResizeEvent>
#include <QTimer>
#include <QVBoxLayout>
#include <QWheelEvent>
#include <algorithm>

namespace rk {
namespace {
class ImageView : public QGraphicsView {
  public:
    explicit ImageView(const QImage &image, QWidget *parent = nullptr) : QGraphicsView(parent) {
        auto *scene = new QGraphicsScene(this);
        setScene(scene);
        item_ = scene->addPixmap(QPixmap::fromImage(image));
        setRenderHint(QPainter::SmoothPixmapTransform);
        setTransformationAnchor(QGraphicsView::AnchorUnderMouse);
        setBackgroundBrush(Qt::black);
        setFrameShape(QFrame::NoFrame);
    }
    void fit_image() {
        resetTransform();
        fitInView(item_, Qt::KeepAspectRatio);
        scale(0.95, 0.95);
    }

  protected:
    void wheelEvent(QWheelEvent *event) override {
        const double current = transform().m11();
        const double desired =
            std::clamp(current * (event->angleDelta().y() > 0 ? 1.15 : 1.0 / 1.15), 0.01, 10.0);
        scale(desired / current, desired / current);
        event->accept();
    }
    void mousePressEvent(QMouseEvent *event) override {
        if (event->button() == Qt::MiddleButton) {
            panning_ = true;
            last_ = event->pos();
            setCursor(Qt::ClosedHandCursor);
            event->accept();
        } else
            QGraphicsView::mousePressEvent(event);
    }
    void mouseMoveEvent(QMouseEvent *event) override {
        if (panning_) {
            const auto delta = event->pos() - last_;
            last_ = event->pos();
            translate(delta.x() / transform().m11(), delta.y() / transform().m22());
            event->accept();
        } else
            QGraphicsView::mouseMoveEvent(event);
    }
    void mouseReleaseEvent(QMouseEvent *event) override {
        if (event->button() == Qt::MiddleButton && panning_) {
            panning_ = false;
            unsetCursor();
            event->accept();
        } else
            QGraphicsView::mouseReleaseEvent(event);
    }

  private:
    QGraphicsPixmapItem *item_;
    bool panning_ = false;
    QPoint last_;
};
class FullscreenPreview : public QDialog {
  public:
    explicit FullscreenPreview(const QImage &image, QWidget *parent = nullptr)
        : QDialog(parent), image_(image) {
        setWindowTitle("RenderKit Preview");
        setMinimumSize(800, 600);
        resize(1100, 750);
        setAttribute(Qt::WA_DeleteOnClose);
        auto *layout = new QVBoxLayout(this);
        view_ = new ImageView(image, this);
        layout->addWidget(view_, 1);
        auto *footer = new QWidget(this);
        footer->setObjectName("FullscreenFooter");
        auto *footer_layout = new QHBoxLayout(footer);
        footer_layout->addStretch();
        auto *copy = new QPushButton("Copy Image", footer);
        footer_layout->addWidget(copy);
        layout->addWidget(footer);
        connect(copy, &QPushButton::clicked, this, [this, copy] {
            QApplication::clipboard()->setImage(image_);
            copy->setText("Copied!");
            QTimer::singleShot(2000, copy, [copy] { copy->setText("Copy Image"); });
        });
        QTimer::singleShot(0, this, [this] { view_->fit_image(); });
    }

  protected:
    void keyPressEvent(QKeyEvent *event) override {
        if (event->key() == Qt::Key_F) {
            view_->fit_image();
            event->accept();
        } else if (event->key() == Qt::Key_Escape)
            close();
        else
            QDialog::keyPressEvent(event);
    }

  private:
    QImage image_;
    ImageView *view_;
};
} // namespace
PreviewWidget::PreviewWidget(QWidget *parent) : QWidget(parent) {
    setMinimumSize(160, 120);
    image_label_ = new QLabel("Preview", this);
    image_label_->setAlignment(Qt::AlignCenter);
    expand_ = new QPushButton(this);
    expand_->setObjectName("PreviewExpandButton");
    expand_->setFixedSize(30, 30);
    expand_->setToolTip("Open fullscreen preview");
    export_ = new QPushButton(this);
    export_->setObjectName("PreviewExportButton");
    export_->setFixedSize(30, 30);
    export_->setToolTip("Export thumbnail");
    IconManager icons;
    expand_->setIcon(icons.icon("scan"));
    export_->setIcon(icons.icon("file_image"));
    expand_->hide();
    export_->hide();
    connect(expand_, &QPushButton::clicked, this, [this] {
        if (!image_.isNull())
            (new FullscreenPreview(image_, this))->show();
    });
    connect(export_, &QPushButton::clicked, this, [this] {
        if (image_.isNull() || source_path_.isEmpty())
            return;
        if (output_path_.trimmed().isEmpty()) {
            QMessageBox::warning(this, "Thumbnail Export", "Set an output video path first.");
            return;
        }
        const QFileInfo source(source_path_);
        const auto stem = derive_sequence_stem(source.fileName().toStdString());
        const auto output_dir = QFileInfo(output_path_.trimmed()).absoluteDir();
        if (!output_dir.exists() && !QDir().mkpath(output_dir.absolutePath())) {
            QMessageBox::warning(this, "Thumbnail Export", "Could not create the output folder.");
            return;
        }
        const auto output = output_dir.filePath(QString::fromStdString(stem) + "_thumb.jpg");
        const auto thumbnail =
            image_.scaled(512, 512, Qt::KeepAspectRatio, Qt::SmoothTransformation);
        if (!thumbnail.save(output, "JPG", 90))
            QMessageBox::warning(this, "Export failed", "Could not save " + output);
    });
}
void PreviewWidget::set_image(const QImage &image) {
    image_ = image;
    expand_->setVisible(!image.isNull());
    export_->setVisible(!image.isNull());
    refresh();
}
void PreviewWidget::set_message(const QString &message) {
    image_ = {};
    image_label_->setText(message);
    expand_->hide();
    export_->hide();
}
void PreviewWidget::refresh() {
    if (!image_.isNull())
        image_label_->setPixmap(QPixmap::fromImage(image_).scaled(
            image_label_->size(), Qt::KeepAspectRatio, Qt::SmoothTransformation));
}
void PreviewWidget::resizeEvent(QResizeEvent *event) {
    QWidget::resizeEvent(event);
    image_label_->setGeometry(rect());
    expand_->move(width() - expand_->width() - 8, height() - expand_->height() - 8);
    export_->move(expand_->x() - export_->width() - 6, expand_->y());
    refresh();
}
} // namespace rk
