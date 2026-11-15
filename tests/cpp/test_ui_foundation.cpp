#include "ui/collapsible_group.hpp"
#include "ui/icon_manager.hpp"
#include "ui/preview_widget.hpp"
#include "ui/splash_screen.hpp"
#include <QApplication>
#include <QFileInfo>
#include <QImage>
#include <QLabel>
#include <QPushButton>
#include <QTemporaryDir>
#include <QToolButton>
#include <cstdio>
#include <stdexcept>
#ifdef RENDERKIT_HAS_OIIO
#include "processing/frame_pipeline.hpp"
#include "processing/scaler.hpp"
#include "ui/preview_image.hpp"
#include "ui/workers.hpp"
#include <OpenImageIO/imagebufalgo.h>
#endif

void check(bool condition) {
    if (!condition)
        throw std::runtime_error("UI check failed");
}
int main(int argc, char **argv) try {
    QApplication app(argc, argv);
    rk::IconManager icons;
    check(icons.has_icon("play"));
    check(!icons.has_icon("missing"));
    const auto image = icons.icon("play", QColor("#ff0000"), 24).pixmap(24, 24).toImage();
    check(!image.isNull());
    check(image.pixelColor(0, 0).alpha() == 0);
    int painted = 0;
    for (int y = 0; y < image.height(); ++y) {
        for (int x = 0; x < image.width(); ++x) {
            const auto pixel = image.pixelColor(x, y);
            if (pixel.alpha() && pixel.red() > 200 && pixel.green() == 0)
                ++painted;
        }
    }
    check(painted > 0);
    check(image.pixelColor(12, 12).alpha() == 0);
    rk::CollapsibleGroup group("Settings");
    check(!group.is_expanded());
    group.set_expanded(true);
    check(group.is_expanded());
    check(group.findChild<QLabel *>("CollapsibleTitle")->text() == "Settings");
    group.resize(300, 100);
    group.show();
    app.processEvents();
    check(group.findChild<QToolButton *>("CollapsibleHeader")->width() >= 250);
    rk::PreviewWidget preview_widget;
    auto *expand = preview_widget.findChild<QPushButton *>("PreviewExpandButton");
    auto *export_button = preview_widget.findChild<QPushButton *>("PreviewExportButton");
    check(expand && export_button && expand->isHidden() && export_button->isHidden());
    QImage test_image(8, 8, QImage::Format_RGB888);
    test_image.fill(Qt::red);
    preview_widget.set_image(test_image);
    check(!expand->isHidden() && !export_button->isHidden());
    QTemporaryDir thumbnail_dir;
    check(thumbnail_dir.isValid());
    preview_widget.set_source_path(thumbnail_dir.filePath("source/render.1001.exr"));
    preview_widget.set_output_path(thumbnail_dir.filePath("output/result.mp4"));
    export_button->click();
    check(QFileInfo::exists(thumbnail_dir.filePath("output/render_thumb.jpg")));
    check(rk::build_splash_pixmap("2.0.0").size() == QSize(620, 320));
    check(rk::kSplashMinDurationMs == 1200);
#ifdef RENDERKIT_HAS_OIIO
    OIIO::ImageBuf source(OIIO::ImageSpec(1, 2, 3, OIIO::TypeDesc::FLOAT));
    const float first[] = {1.0f, 0.0f, 0.0f}, second[] = {0.0f, 1.0f, 0.0f};
    source.setpixel(0, 0, first);
    source.setpixel(0, 1, second);
    const auto preview = rk::preview_image(source);
    check(preview.pixelColor(0, 0) == QColor(255, 0, 0));
    check(preview.pixelColor(0, 1) == QColor(0, 255, 0));
    OIIO::ImageBuf large(OIIO::ImageSpec(32, 16, 3, OIIO::TypeDesc::FLOAT));
    check(OIIO::ImageBufAlgo::fill(large, 0.5f));
    auto reduced = rk::ImageScaler::scale_buf(large, 24, 12);
    check(rk::preview_image(reduced).size() == QSize(24, 12));
    QTemporaryDir frame_directory;
    check(frame_directory.isValid());
    const auto path = frame_directory.filePath("render.1001.exr");
    check(large.write(path.toStdString()));
    rk::FramePreparationOptions options;
    options.frame_path = path.toStdString();
    options.layer = "RGBA";
    options.preset = rk::ColorSpacePreset::NoConversion;
    options.output_scale = 0.75;
    auto prepared = rk::prepare_frame_buffer(options);
    check(rk::preview_image(prepared.buffer).size() == QSize(24, 12));
    QImage worker_image;
    rk::PreviewWorker worker(options);
    QObject::connect(
        &worker, &rk::PreviewWorker::preview_ready, &worker,
        [&worker_image](const QImage &image) { worker_image = image; }, Qt::DirectConnection);
    worker.start();
    check(worker.wait(30000));
    check(worker_image.size() == QSize(24, 12));
#endif
} catch (const std::exception &error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
}
