#include "ui/main_window.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <QApplication>
#include <QCheckBox>
#include <QComboBox>
#include <QDragEnterEvent>
#include <QDropEvent>
#include <QElapsedTimer>
#include <QFile>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QMimeData>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QSettings>
#include <QSlider>
#include <QSpinBox>
#include <QStyleFactory>
#include <QTemporaryDir>
#include <QThread>
#include <QUrl>
#include <cstdio>
#include <spdlog/spdlog.h>
#include <stdexcept>
#include <thread>
#ifdef _MSC_VER
#include <crtdbg.h>
#endif

void check(bool value) {
    if (!value)
        throw std::runtime_error("Main window check failed");
}
int main(int argc, char **argv) try {
#ifdef _MSC_VER
    _CrtSetReportMode(_CRT_ASSERT, _CRTDBG_MODE_FILE);
    _CrtSetReportFile(_CRT_ASSERT, _CRTDBG_FILE_STDERR);
#endif
    QApplication app(argc, argv);
    QApplication::setStyle(QStyleFactory::create("Fusion"));
    QTemporaryDir settings_dir;
    check(settings_dir.isValid());
    QSettings::setDefaultFormat(QSettings::IniFormat);
    QSettings::setPath(QSettings::IniFormat, QSettings::UserScope, settings_dir.path());
    QSettings::setPath(QSettings::IniFormat, QSettings::SystemScope, settings_dir.path());
    {
        rk::MainWindow window;
        if (qEnvironmentVariableIsSet("RENDERKIT_UI_SNAPSHOT")) {
            window.setAttribute(Qt::WA_DontShowOnScreen);
            QFile stylesheet(":/stylesheets/matcha.qss");
            if (stylesheet.open(QIODevice::ReadOnly))
                app.setStyleSheet(QString::fromUtf8(stylesheet.readAll()));
            window.show();
            app.processEvents();
            window.grab().save(qEnvironmentVariable("RENDERKIT_UI_SNAPSHOT"));
        }
        auto *layer = window.findChild<QComboBox *>("layer_combo");
        auto *sheet = window.findChild<QCheckBox *>("cs_enable_check");
        auto *width = window.findChild<QSpinBox *>("width_spin");
        auto *keep = window.findChild<QCheckBox *>("keep_resolution_check");
        auto *quality = window.findChild<QSlider *>("quality_slider");
        check(layer && sheet && width && keep && quality);
        auto *output = window.findChild<QLineEdit *>("output_path_edit");
        QPushButton *play = nullptr;
        QPushButton *folder = nullptr;
        for (auto *button : window.findChildren<QPushButton *>()) {
            if (button->text() == "Play Result (Flipbook)")
                play = button;
            if (button->text() == "Open Output Folder")
                folder = button;
        }
        check(output && play && folder);
        output->setText(settings_dir.filePath("missing.mp4"));
        check(!play->isEnabled() && !folder->isEnabled());
        output->setText(settings_dir.path());
        check(!play->isEnabled() && !folder->isEnabled());
        QFile video(settings_dir.filePath("existing.mp4"));
        check(video.open(QIODevice::WriteOnly));
        video.close();
        output->setText(video.fileName());
        check(play->isEnabled() && folder->isEnabled());
        sheet->setChecked(true);
        check(!layer->isEnabled());
        sheet->setChecked(false);
        check(layer->isEnabled());
        keep->setChecked(false);
        width->setValue(1000);
        quality->setValue(7);
        auto *quality_label = window.findChild<QLabel *>("quality_value_label");
        check(quality_label && quality_label->text() == "7");
        quality->setValue(8);
        check(quality_label->text() == "8 (VFX)");
        quality->setValue(7);
        window.close();
    }
    {
        rk::MainWindow window;
        check(window.findChild<QSlider *>("quality_slider")->value() == 7);
        check(window.findChild<QSpinBox *>("width_spin")->value() == 1000);
    }
    QTemporaryDir images;
    check(images.isValid());
    OIIO::ImageSpec spec(32, 16, 3, OIIO::TypeDesc::FLOAT);
    spec.attribute("colorSpace", "test_input_space");
    OIIO::ImageBuf frame(spec);
    check(OIIO::ImageBufAlgo::fill(frame, 0.5f));
    const auto first_frame = images.filePath("render.1001.exr");
    check(frame.write(first_frame.toStdString()));
    check(frame.write(images.filePath("render.1002.exr").toStdString()));
    {
        rk::MainWindow window;
        auto *input = window.findChild<QComboBox *>("input_pattern_combo");
        auto *color = window.findChild<QComboBox *>("color_space_combo");
        auto *timeline = window.findChild<QSlider *>("timeline_slider");
        input->setEditText(first_frame);
        QMetaObject::invokeMethod(input->lineEdit(), "editingFinished");
        QElapsedTimer timer;
        timer.start();
        while (!timeline->isEnabled() && timer.elapsed() < 20000) {
            app.processEvents();
            QThread::msleep(20);
        }
        check(timeline->isEnabled());
        check(color->currentText() == "Source: test_input_space");
        check(color->currentData(Qt::UserRole + 1).toString() == "test_input_space");
        auto *log = window.findChild<QPlainTextEdit *>("LogBox");
        auto *clear_log = window.findChild<QPushButton *>("clear_logs_btn");
        check(log && log->isReadOnly() && log->toPlainText().contains("Loaded sequence:"));
        check(clear_log);
        clear_log->click();
        check(log->toPlainText().isEmpty());
        auto logger = spdlog::get("renderkit");
        check(static_cast<bool>(logger));
        std::thread writer([logger] { logger->info("background log delivery"); });
        writer.join();
        app.processEvents();
        check(log->toPlainText().contains("background log delivery"));
        color->setCurrentIndex(0);
        check(color->currentText() == "Linear to sRGB");
    }
    {
        rk::MainWindow window;
        auto *input = window.findChild<QComboBox *>("input_pattern_combo");
        auto *timeline = window.findChild<QSlider *>("timeline_slider");
        input->setEditText(first_frame);
        QMetaObject::invokeMethod(input->lineEdit(), "editingFinished");
        QKeyEvent end_key(QEvent::KeyPress, Qt::Key_End, Qt::NoModifier);
        QApplication::sendEvent(input->lineEdit(), &end_key);
        QKeyEvent character(QEvent::KeyPress, Qt::Key_X, Qt::NoModifier, "x");
        QApplication::sendEvent(input->lineEdit(), &character);
        QElapsedTimer timer;
        timer.start();
        while (timer.elapsed() < 500) {
            app.processEvents();
            QThread::msleep(10);
        }
        check(input->currentText().endsWith("exrx"));
        check(!timeline->isEnabled());
    }
    {
        rk::MainWindow window;
        window.findChild<QComboBox *>("color_space_combo")->setCurrentIndex(3);
        auto *input = window.findChild<QComboBox *>("input_pattern_combo");
        input->setEditText(first_frame);
        QMetaObject::invokeMethod(input->lineEdit(), "editingFinished");
        window.show();
        auto *timeline = window.findChild<QSlider *>("timeline_slider");
        auto *expand = window.findChild<QPushButton *>("PreviewExpandButton");
        check(timeline && expand);
        QElapsedTimer timer;
        timer.start();
        while (timeline->maximum() != 1 && timer.elapsed() < 20000) {
            app.processEvents();
            QThread::msleep(20);
        }
        check(timeline->maximum() == 1);
        auto *current_label = window.findChild<QLabel *>("TimelineCurrentLabel");
        check(current_label && current_label->text() == "Frame: 1001");
        timeline->setValue(1);
        check(current_label->text() == "Frame: 1002");
        timeline->setValue(0);
        timer.restart();
        while (expand->isHidden() && timer.elapsed() < 20000) {
            app.processEvents();
            QThread::msleep(20);
        }
        check(!expand->isHidden());
        check(input->property("validationState").toString() == "valid");
        auto *line_edit = input->lineEdit();
        QKeyEvent end_key(QEvent::KeyPress, Qt::Key_End, Qt::NoModifier);
        QApplication::sendEvent(line_edit, &end_key);
        QKeyEvent character(QEvent::KeyPress, Qt::Key_X, Qt::NoModifier, "x");
        QApplication::sendEvent(line_edit, &character);
        check(!timeline->isEnabled());
        check(input->property("validationState").toString().isEmpty());

        for (int index = 1; index <= 3; ++index) {
            QFile sidecar(images.filePath(QString("notes.%1.txt").arg(index, 4, 10, QChar('0'))));
            check(sidecar.open(QIODevice::WriteOnly));
        }
        QMimeData mime;
        mime.setUrls({QUrl::fromLocalFile(images.path())});
        QDragEnterEvent drag(QPoint(10, 10), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(&window, &drag);
        check(drag.isAccepted());
        QDropEvent drop(QPointF(10, 10), Qt::CopyAction, &mime, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(&window, &drop);
        timer.restart();
        while (!timeline->isEnabled() && timer.elapsed() < 20000) {
            app.processEvents();
            QThread::msleep(20);
        }
        check(timeline->isEnabled());
        check(input->currentText().endsWith("render.%04d.exr"));
        check(input->property("validationState").toString() == "valid");
        window.close();
    }
} catch (const std::exception &error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
}
