#pragma once
#include <QDir>
#include <QDirIterator>
#include <QFileInfo>
#include <QStandardPaths>
#include <QStringList>
#include <string>

namespace rk {
// OpenImageIO's built-in font search does not recurse through typical Linux font directories.
inline std::string default_font() {
    if (!qEnvironmentVariableIsEmpty("OPENIMAGEIO_FONTS"))
        return {};
    static const std::string font = [] {
        QStringList roots = QStandardPaths::standardLocations(QStandardPaths::FontsLocation);
#ifdef Q_OS_WIN
        roots << QDir(qEnvironmentVariable("WINDIR", "C:/Windows")).filePath("Fonts");
#elif defined(Q_OS_MACOS)
        roots << "/System/Library/Fonts"
              << "/Library/Fonts";
#else
        roots << "/usr/share/fonts"
              << "/usr/local/share/fonts";
#endif
        const QStringList preferred{"DejaVuSans.ttf", "LiberationSans-Regular.ttf",
                                    "FreeSans.ttf",   "NotoSans-Regular.ttf",
                                    "arial.ttf",      "segoeui.ttf"};
        QString fallback;
        QStringList matches;
        for (const auto &root : roots) {
            QDirIterator it(root, {"*.ttf", "*.otf", "*.TTF", "*.OTF"}, QDir::Files,
                            QDirIterator::Subdirectories);
            while (it.hasNext()) {
                const auto path = it.next();
                if (fallback.isEmpty())
                    fallback = path;
                if (preferred.contains(QFileInfo(path).fileName(), Qt::CaseInsensitive))
                    matches << path;
            }
        }
        for (const auto &name : preferred)
            for (const auto &path : matches)
                if (QFileInfo(path).fileName().compare(name, Qt::CaseInsensitive) == 0)
                    return path.toUtf8().toStdString();
        return fallback.toUtf8().toStdString();
    }();
    return font;
}
} // namespace rk
