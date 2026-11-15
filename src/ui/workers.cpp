#include "workers.hpp"
#include "core/converter.hpp"
#include "core/exceptions.hpp"
#include "core/path_utils.hpp"
#include "core/sequence_names.hpp"
#include "io/image_reader.hpp"
#include "preview_image.hpp"

namespace rk {
ConversionWorker::ConversionWorker(ConversionConfig config, std::filesystem::path ocio_config,
                                   QObject *parent)
    : QThread(parent), config_(std::move(config)), ocio_config_(std::move(ocio_config)) {}
void ConversionWorker::run() {
    try {
        SequenceConverter(config_, ocio_config_).convert([this](int current, int total) {
            emit progress_changed(current, total);
            return !cancelled_.load();
        });
        emit conversion_finished(QString::fromStdString(config_.output_path));
    } catch (const ConversionCancelledError &) {
        emit conversion_cancelled();
    } catch (const std::exception &error) {
        emit conversion_failed(QString::fromUtf8(error.what()));
    }
}
PreviewWorker::PreviewWorker(FramePreparationOptions options, QObject *parent)
    : QThread(parent), options_(std::move(options)) {}
void PreviewWorker::run() {
    try {
        emit preview_ready(preview_image(prepare_frame_buffer(options_).buffer));
    } catch (const std::exception &error) {
        emit preview_failed(QString::fromUtf8(error.what()));
    }
}
FileInfoWorker::FileInfoWorker(QString path, QObject *parent)
    : QThread(parent), path_(std::move(path)) {}
void FileInfoWorker::run() {
    try {
#ifdef Q_OS_WIN
        const std::filesystem::path path(path_.toStdWString());
#else
        const std::filesystem::path path(path_.toStdString());
#endif
        const auto pattern = build_pattern_from_path(path).value_or(path_to_utf8(path));
        auto sequence = SequenceDetector::detect_sequence(pattern);
        auto info =
            OIIOReader().get_file_info(sequence.get_file_path(sequence.frame_numbers.front()));
        emit info_ready(QString::fromStdString(pattern), sequence, info);
    } catch (const std::exception &error) {
        emit info_failed(QString::fromUtf8(error.what()));
    }
}
} // namespace rk
