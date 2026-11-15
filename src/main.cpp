#include "core/logging.hpp"
#include "ui/main_window.hpp"
#include "ui/splash_screen.hpp"
#include <QApplication>
#include <QElapsedTimer>
#include <QFile>
#include <QSplashScreen>
#include <QStyleFactory>
#include <QTimer>
#include <algorithm>

int main(int argc, char **argv) {
    QApplication application(argc, argv);
    try {
        rk::setup_logging();
    } catch (const std::exception &) { /* The interface can still run without a log file. */
    }
    application.setOrganizationName("RenderKit");
    application.setApplicationName("RenderKit");
    QApplication::setStyle(QStyleFactory::create("Fusion"));
    Q_INIT_RESOURCE(renderkit);
    QFile stylesheet(":/stylesheets/matcha.qss");
    if (stylesheet.open(QIODevice::ReadOnly))
        application.setStyleSheet(QString::fromUtf8(stylesheet.readAll()));
    QElapsedTimer elapsed;
    elapsed.start();
    QSplashScreen splash(rk::build_splash_pixmap("2.0.0"));
    splash.show();
    application.processEvents();
    rk::MainWindow window(argc > 1 ? QString::fromLocal8Bit(argv[1]) : QString{});
    QTimer::singleShot(std::max(0, rk::kSplashMinDurationMs - static_cast<int>(elapsed.elapsed())),
                       &application, [&] {
                           window.show();
                           splash.finish(&window);
                       });
    return application.exec();
}
