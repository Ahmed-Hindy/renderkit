#pragma once
#include "core/config.hpp"
#include "core/sequence.hpp"
#include "io/file_info.hpp"
#include "processing/frame_pipeline.hpp"
#include <QImage>
#include <QThread>
#include <atomic>
#include <filesystem>

namespace rk {
class ConversionWorker : public QThread {
    Q_OBJECT
  public:
    ConversionWorker(ConversionConfig config, std::filesystem::path ocio_config,
                     QObject *parent = nullptr);
    void cancel() {
        cancelled_.store(true);
    }
  signals:
    void progress_changed(int current, int total);
    void conversion_finished(const QString &output_path);
    void conversion_failed(const QString &message);
    void conversion_cancelled();

  protected:
    void run() override;

  private:
    ConversionConfig config_;
    std::filesystem::path ocio_config_;
    std::atomic<bool> cancelled_{false};
};
class PreviewWorker : public QThread {
    Q_OBJECT
  public:
    explicit PreviewWorker(FramePreparationOptions options, QObject *parent = nullptr);
  signals:
    void preview_ready(const QImage &image);
    void preview_failed(const QString &message);

  protected:
    void run() override;

  private:
    FramePreparationOptions options_;
};
class FileInfoWorker : public QThread {
    Q_OBJECT
  public:
    explicit FileInfoWorker(QString path, QObject *parent = nullptr);
  signals:
    void info_ready(const QString &pattern, const rk::FrameSequence &sequence,
                    const rk::FileInfo &info);
    void info_failed(const QString &message);

  protected:
    void run() override;

  private:
    QString path_;
};
} // namespace rk
Q_DECLARE_METATYPE(rk::FrameSequence)
Q_DECLARE_METATYPE(rk::FileInfo)
