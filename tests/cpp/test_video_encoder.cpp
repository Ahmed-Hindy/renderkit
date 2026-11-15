#include "core/converter.hpp"
#include "core/exceptions.hpp"
#include "processing/video_encoder.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <cstdio>
#include <stdexcept>

int main(int argc, char **argv) try {
    QCoreApplication app(argc, argv);
    const auto fake_args_path = qEnvironmentVariable("RENDERKIT_TEST_FFMPEG_ARGS");
    if (!fake_args_path.isEmpty()) {
        if (app.arguments().contains("-encoders")) {
            std::fputs(" V..... mpeg4 test\n V..... libaom-av1 test\n"
                       " V..... libx264 test\n V..... libx265 test\n",
                       stdout);
            return 0;
        }
        QFile args_file(fake_args_path);
        if (!args_file.open(QIODevice::WriteOnly))
            return 1;
        args_file.write(app.arguments().join('\n').toUtf8());
        return 0;
    }
#ifdef RENDERKIT_TEST_FFMPEG
    const QString ffmpeg = QString::fromUtf8(RENDERKIT_TEST_FFMPEG);
#else
    const QString ffmpeg = QStandardPaths::findExecutable("ffmpeg");
#endif
    if (ffmpeg.isEmpty())
        return 77;
    QTemporaryDir directory;
    if (!directory.isValid())
        throw std::runtime_error("Could not create test directory");
    const auto recorded_args = directory.filePath("ffmpeg-args.txt");
    qputenv("RENDERKIT_TEST_FFMPEG_ARGS", recorded_args.toUtf8());
    for (const auto &codec : {QString("mpeg4"), QString("libaom-av1")}) {
        rk::VideoEncoder encoder(directory.filePath(codec + ".mp4"), 16, 16, 24.0, codec, 8, 5000,
                                 QCoreApplication::applicationFilePath());
        encoder.finish();
        QFile args_file(recorded_args);
        if (!args_file.open(QIODevice::ReadOnly))
            throw std::runtime_error("Could not inspect encoder arguments");
        const auto args = args_file.readAll().split('\n');
        const auto bitrate_index = args.indexOf("-b:v");
        if (bitrate_index < 0 || bitrate_index + 1 >= args.size() ||
            args[bitrate_index + 1] != "5000k")
            throw std::runtime_error("Video bitrate was not passed in kilobits per second");
        if (codec == "libaom-av1" && !args.contains("-cpu-used"))
            throw std::runtime_error("AV1 bitrate encoding did not select its speed setting");
    }
    for (const auto &[alias, expected] : {std::pair{QString("avc1"), QByteArray("libx264")},
                                          std::pair{QString("hevc"), QByteArray("libx265")},
                                          std::pair{QString("mp4v"), QByteArray("mpeg4")},
                                          std::pair{QString("XVID"), QByteArray("mpeg4")}}) {
        rk::VideoEncoder encoder(directory.filePath("new-folder/alias.mp4"), 16, 16, 24.0, alias, 8,
                                 {}, QCoreApplication::applicationFilePath());
        encoder.finish();
        QFile args_file(recorded_args);
        if (!args_file.open(QIODevice::ReadOnly))
            throw std::runtime_error("Could not inspect encoder arguments");
        const auto args = args_file.readAll().split('\n');
        const auto codec_index = args.lastIndexOf("-vcodec");
        if (codec_index < 0 || codec_index + 1 >= args.size() || args[codec_index + 1] != expected)
            throw std::runtime_error("Video codec alias was not resolved");
    }
    qunsetenv("RENDERKIT_TEST_FFMPEG_ARGS");
    const auto output = directory.filePath("test.mp4");
    const QString decoder = QStandardPaths::findExecutable("ffmpeg");
    if (decoder.isEmpty())
        return 77;
    qputenv("FFREPORT", "renderkit-parent-sentinel");
    OIIO::ImageBuf frame(OIIO::ImageSpec(13, 11, 3, OIIO::TypeDesc::FLOAT));
    const float red[] = {1.0f, 0.0f, 0.0f};
    if (!OIIO::ImageBufAlgo::fill(frame, red))
        throw std::runtime_error("Could not create frame");
    {
        QFile existing(output);
        if (!existing.open(QIODevice::WriteOnly) || existing.write("old video") != 9)
            throw std::runtime_error("Could not create existing output");
    }
    {
        rk::VideoEncoder encoder(output, 13, 11, 24.0, "mpeg4", 8, {}, ffmpeg);
        if (encoder.width() != 16 || encoder.height() != 16)
            throw std::runtime_error("Incorrect encoder dimensions");
        encoder.write_frame(frame);
        encoder.write_frame(frame);
        encoder.finish();
    }
    if (qgetenv("FFREPORT") != "renderkit-parent-sentinel")
        throw std::runtime_error("Encoder modified the parent FFREPORT environment");
    qunsetenv("FFREPORT");
    QProcess decode;
    decode.start(decoder,
                 {"-v", "error", "-i", output, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"});
    if (!decode.waitForStarted(10000) || !decode.waitForFinished(30000) || decode.exitCode() != 0)
        throw std::runtime_error("Encoded video could not be decoded: " + output.toStdString() +
                                 " " + std::to_string(QFileInfo(output).size()) + " " +
                                 decode.readAllStandardError().toStdString() + " " +
                                 decode.errorString().toStdString());
    const auto pixels = decode.readAllStandardOutput();
    if (pixels.size() != 16 * 16 * 3 * 2 || static_cast<unsigned char>(pixels[0]) < 180)
        throw std::runtime_error("Incorrect decoded video pixels");
    const auto unicode_dir = directory.filePath(QString::fromUtf8("render-\xE6\xBC\xA2"));
    if (!QDir().mkpath(unicode_dir))
        throw std::runtime_error("Could not create Unicode sequence directory");
    const auto frame_one = unicode_dir + "/render.1001.exr";
    const auto frame_three = unicode_dir + "/render.1003.exr";
    if (!frame.write(frame_one.toStdString()))
        throw std::runtime_error("Could not create first EXR");
    const float green[] = {0.0f, 1.0f, 0.0f};
    if (!OIIO::ImageBufAlgo::fill(frame, green) || !frame.write(frame_three.toStdString()))
        throw std::runtime_error("Could not create third EXR");
    qputenv("IMAGEIO_FFMPEG_EXE", ffmpeg.toUtf8());
    rk::ConversionConfig config;
    config.input_pattern = (unicode_dir + "/render.%04d.exr").toStdString();
    config.output_path =
        (unicode_dir + QString::fromUtf8("/sequence-\xE6\xBC\xA2.mp4")).toStdString();
    config.fps = 24.0;
    config.codec = "mpeg4";
    config.prefetch_workers = 2;
    config.color_space_preset = rk::ColorSpacePreset::NoConversion;
    int last_progress = -1;
    rk::SequenceConverter(config, {}).convert([&](int current, int) {
        last_progress = current;
        return true;
    });
    if (last_progress != 3)
        throw std::runtime_error("Conversion did not report completion");
    QProcess decode_sequence;
    decode_sequence.start(decoder, {"-v", "error", "-i", QString::fromStdString(config.output_path),
                                    "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"});
    if (!decode_sequence.waitForStarted(10000) || !decode_sequence.waitForFinished(30000) ||
        decode_sequence.exitCode() != 0)
        throw std::runtime_error("Converted sequence could not be decoded");
    const auto sequence_pixels = decode_sequence.readAllStandardOutput();
    const int frame_size = 16 * 16 * 3;
    if (sequence_pixels.size() != frame_size * 3 ||
        static_cast<unsigned char>(sequence_pixels[0]) < 180 ||
        static_cast<unsigned char>(sequence_pixels[frame_size]) < 180 ||
        static_cast<unsigned char>(sequence_pixels[2 * frame_size + 1]) < 180)
        throw std::runtime_error("Missing frame was not filled with the preceding image");
    config.output_path = directory.filePath("cancelled.mp4").toStdString();
    {
        QFile existing(QString::fromStdString(config.output_path));
        if (!existing.open(QIODevice::WriteOnly) || existing.write("old video") != 9)
            throw std::runtime_error("Could not create cancellation sentinel");
    }
    try {
        rk::SequenceConverter(config, {}).convert([](int current, int) { return current < 1; });
        throw std::runtime_error("Cancellation was ignored");
    } catch (const rk::ConversionCancelledError &) {
    }
    QFile existing(QString::fromStdString(config.output_path));
    if (!existing.open(QIODevice::ReadOnly) || existing.readAll() != "old video")
        throw std::runtime_error("Cancelled conversion changed the existing output");
    existing.close();
    const auto failed = directory.filePath("failed.mp4");
    try {
        rk::VideoEncoder encoder(failed, 13, 11, 24.0, "mpeg4", 8, {}, ffmpeg);
        OIIO::ImageBuf bad_frame(OIIO::ImageSpec(16, 16, 2, OIIO::TypeDesc::FLOAT));
        encoder.write_frame(bad_frame);
        throw std::runtime_error("Invalid frame was accepted");
    } catch (const rk::VideoEncodingError &) {
    }
    if (QFileInfo::exists(failed) ||
        !QDir(directory.path()).entryList({".renderkit-*"}, QDir::Files | QDir::Hidden).isEmpty())
        throw std::runtime_error("Failed or cancelled conversion left a partial output");
} catch (const std::exception &error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
}
