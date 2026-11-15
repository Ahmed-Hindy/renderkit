#include "video_encoder.hpp"
#include "core/exceptions.hpp"
#include "scaler.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcessEnvironment>
#include <QRegularExpression>
#include <QSet>
#include <QStandardPaths>
#include <QStringList>
#include <algorithm>
#include <array>
#include <filesystem>
#include <mutex>
#include <unordered_map>
#include <vector>
#ifdef Q_OS_WIN
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace rk {
namespace {
QString discover_ffmpeg() {
    auto configured = qEnvironmentVariable("IMAGEIO_FFMPEG_EXE");
    if (!configured.isEmpty())
        return configured;
#ifdef Q_OS_WIN
    const QString name = "ffmpeg.exe";
#else
    const QString name = "ffmpeg";
#endif
    QDir executable(QCoreApplication::applicationDirPath());
    for (const auto &path : {executable.filePath("ffmpeg/" + name), executable.filePath(name)})
        if (QFileInfo::exists(path))
            return path;
    const QString platform =
#ifdef Q_OS_WIN
        "windows";
#else
        "linux";
#endif
    QDir current(QDir::currentPath());
    for (int depth = 0; depth < 6; ++depth) {
        const auto path = current.filePath("vendor/ffmpeg/" + platform + "/" + name);
        if (QFileInfo::exists(path))
            return path;
        if (!current.cdUp())
            break;
    }
    auto system = QStandardPaths::findExecutable(name);
    if (system.isEmpty())
        throw VideoEncodingError("FFmpeg executable not found");
    return system;
}
QSet<QString> probe_encoders(const QString &executable) {
    static std::mutex mutex;
    static std::unordered_map<std::string, QSet<QString>> cache;
    std::lock_guard lock(mutex);
    const auto key = executable.toStdString();
    if (const auto found = cache.find(key); found != cache.end())
        return found->second;
    QProcess probe;
    probe.setProcessChannelMode(QProcess::MergedChannels);
    probe.start(executable, {"-hide_banner", "-encoders"});
    if (!probe.waitForStarted(10000) || !probe.waitForFinished(30000) || probe.exitCode() != 0)
        return cache.emplace(key, QSet<QString>{}).first->second;
    const auto output = QString::fromUtf8(probe.readAll());
    const QRegularExpression line(R"(^\s*V\S*\s+(\S+))", QRegularExpression::MultilineOption);
    QSet<QString> available;
    auto matches = line.globalMatch(output);
    while (matches.hasNext())
        available.insert(matches.next().captured(1));
    return cache.emplace(key, std::move(available)).first->second;
}
QString select_encoder(const QString &executable, const QString &requested) {
    const auto available = probe_encoders(executable);
    if (available.isEmpty() || available.contains(requested))
        return requested;
    QStringList fallback;
    if (requested == "libx264")
        fallback = {"libx265", "libaom-av1", "mpeg4"};
    else if (requested == "libx265")
        fallback = {"libaom-av1", "mpeg4"};
    else if (requested == "libaom-av1")
        fallback = {"libx265", "mpeg4"};
    else if (requested == "mpeg4")
        fallback = {"libx265", "libaom-av1"};
    else
        fallback = {"libx264", "libx265", "libaom-av1", "mpeg4"};
    for (const auto &candidate : fallback)
        if (available.contains(candidate))
            return candidate;
    return requested;
}
} // namespace
VideoEncoder::VideoEncoder(const QString &output_path, int width, int height, double fps,
                           QString codec, int quality, std::optional<int> bitrate,
                           const QString &ffmpeg_executable)
    : width_(((width + 15) / 16) * 16), height_(((height + 15) / 16) * 16) {
    if (width <= 0 || height <= 0 || fps <= 0 || quality < 0 || quality > 10 ||
        (bitrate && *bitrate <= 0))
        throw VideoEncodingError("Invalid video encoder settings");
    destination_ = QFileInfo(output_path).absoluteFilePath();
    const QFileInfo destination(destination_);
    if (!QDir().mkpath(destination.absolutePath()))
        throw VideoEncodingError("Could not create output directory");
    const auto executable = ffmpeg_executable.isEmpty() ? discover_ffmpeg() : ffmpeg_executable;
    const auto alias = codec.toLower();
    if (alias == "avc1")
        codec = "libx264";
    else if (alias == "hevc")
        codec = "libx265";
    else if (alias == "mp4v" || alias == "xvid")
        codec = "mpeg4";
    codec = select_encoder(executable, codec);
    QStringList args{"-y",
                     "-f",
                     "rawvideo",
                     "-vcodec",
                     "rawvideo",
                     "-s",
                     QString::number(width_) + "x" + QString::number(height_),
                     "-pix_fmt",
                     "rgb24",
                     "-r",
                     QString::number(fps, 'f', 2),
                     "-i",
                     "pipe:0",
                     "-an",
                     "-vcodec",
                     codec,
                     "-pix_fmt",
                     "yuv420p"};
    if (bitrate) {
        args << "-b:v" << (QString::number(*bitrate) + "k");
        if (codec == "libaom-av1")
            args << "-cpu-used"
                 << "6";
    }
    args << "-v"
         << "warning"
         << "-movflags"
         << "+faststart"
         << "-color_primaries"
         << "bt709"
         << "-color_trc"
         << "bt709"
         << "-colorspace"
         << "bt709";
    if (!bitrate) {
        if (codec == "libx264" || codec == "libx265")
            args << "-crf" << QString::number(static_cast<int>(18 + (10 - quality) * 1.7));
        else if (codec == "libaom-av1")
            args << "-crf" << QString::number(20 + (10 - quality) * 3) << "-cpu-used"
                 << "6"
                 << "-b:v"
                 << "0";
        else if (codec == "mpeg4")
            args << "-q:v" << QString::number(static_cast<int>(2 + (10 - quality) * 2.9));
    }
    const auto logging = qEnvironmentVariable("RENDERKIT_FFMPEG_LOG", "1").trimmed().toLower();
    if (logging != "0" && logging != "false" && logging != "no" && logging != "off") {
        report_.setFileTemplate(QDir::tempPath() + "/renderkit-ffmpeg-XXXXXX.log");
        if (report_.open()) {
            auto report_path = QDir::fromNativeSeparators(report_.fileName());
            report_.close();
            report_path.replace(":", "\\:");
            auto environment = QProcessEnvironment::systemEnvironment();
            environment.insert("FFREPORT", "file=" + report_path + ":level=48");
            process_.setProcessEnvironment(environment);
            args << "-report"
                 << "-loglevel"
                 << "info";
        }
    }
    {
        QTemporaryFile output(
            destination.dir().filePath(".renderkit-XXXXXX." + destination.suffix()));
        if (!output.open())
            throw VideoEncodingError("Could not create temporary output: " +
                                     output.errorString().toStdString());
        temporary_path_ = output.fileName();
        output.setAutoRemove(false);
    }
    args << temporary_path_;
    process_.setProcessChannelMode(QProcess::SeparateChannels);
    process_.start(executable, args, QIODevice::WriteOnly);
    if (!process_.waitForStarted(10000)) {
        QFile::remove(temporary_path_);
        throw VideoEncodingError("Could not start FFmpeg: " + process_.errorString().toStdString());
    }
}
VideoEncoder::~VideoEncoder() {
    if (process_.state() != QProcess::NotRunning) {
        process_.kill();
        process_.waitForFinished(5000);
    }
    QFile::remove(temporary_path_);
}
void VideoEncoder::write_frame(const OIIO::ImageBuf &frame) {
    if (finished_ || process_.state() == QProcess::NotRunning)
        throw VideoEncodingError("FFmpeg is not running");
    auto image = frame.spec().width == width_ && frame.spec().height == height_
                     ? frame
                     : ImageScaler::scale_buf(frame, width_, height_);
    if (image.nchannels() == 1) {
        const std::array<int, 3> order{0, 0, 0};
        image = OIIO::ImageBufAlgo::channels(image, 3, order);
    }
    if (image.nchannels() < 3)
        throw VideoEncodingError("Frame needs one or at least three channels");
    image = OIIO::ImageBufAlgo::clamp(image, 0.0f, 1.0f);
    if (image.has_error())
        throw VideoEncodingError(image.geterror());
    std::vector<unsigned char> bytes(static_cast<size_t>(width_) * height_ * 3);
    const auto &spec = image.spec();
    OIIO::ROI roi(spec.x, spec.x + width_, spec.y, spec.y + height_, spec.z, spec.z + 1, 0, 3);
    if (!image.get_pixels(roi, OIIO::span<unsigned char>(bytes.data(), bytes.size())))
        throw VideoEncodingError("Could not extract RGB frame: " + image.geterror());
    const auto written = process_.write(reinterpret_cast<const char *>(bytes.data()),
                                        static_cast<qint64>(bytes.size()));
    if (written != static_cast<qint64>(bytes.size()))
        throw VideoEncodingError("Could not write frame to FFmpeg");
    while (process_.bytesToWrite() > 4 * 1024 * 1024) {
        if (!process_.waitForBytesWritten(30000))
            throw VideoEncodingError("FFmpeg stopped accepting frames: " +
                                     process_.errorString().toStdString());
        process_.readAllStandardError();
    }
}
void VideoEncoder::finish() {
    if (finished_)
        return;
    process_.closeWriteChannel();
    if (!process_.waitForFinished(120000))
        throw VideoEncodingError("FFmpeg did not finish: " + process_.errorString().toStdString());
    if (process_.exitStatus() != QProcess::NormalExit || process_.exitCode() != 0) {
        auto detail = process_.readAllStandardError();
        QFile log(report_.fileName());
        if (log.open(QIODevice::ReadOnly)) {
            auto lines = log.readAll().split('\n');
            for (int i = std::max(0, static_cast<int>(lines.size()) - 80); i < lines.size(); ++i)
                if (!lines[i].trimmed().isEmpty())
                    detail += "\n" + lines[i];
        }
        throw VideoEncodingError("FFmpeg failed: " + detail.toStdString());
    }
#ifdef Q_OS_WIN
    if (!MoveFileExW(reinterpret_cast<const wchar_t *>(temporary_path_.utf16()),
                     reinterpret_cast<const wchar_t *>(destination_.utf16()),
                     MOVEFILE_REPLACE_EXISTING))
        throw VideoEncodingError("Could not replace output file (Windows error " +
                                 std::to_string(GetLastError()) + ")");
#else
    std::error_code error;
    std::filesystem::rename(temporary_path_.toStdString(), destination_.toStdString(), error);
    if (error)
        throw VideoEncodingError("Could not replace output file: " + error.message());
#endif
    finished_ = true;
}
} // namespace rk
