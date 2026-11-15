#pragma once
#include <OpenImageIO/imagebuf.h>
#include <QProcess>
#include <QString>
#include <QTemporaryFile>
#include <optional>

namespace rk {
class VideoEncoder {
  public:
    VideoEncoder(const QString &output_path, int width, int height, double fps,
                 QString codec = "libx264", int quality = 10, std::optional<int> bitrate = {},
                 const QString &ffmpeg_executable = {});
    ~VideoEncoder();
    void write_frame(const OIIO::ImageBuf &frame);
    void finish();
    int width() const {
        return width_;
    }
    int height() const {
        return height_;
    }

  private:
    QProcess process_;
    QTemporaryFile report_;
    QString destination_;
    QString temporary_path_;
    int width_;
    int height_;
    bool finished_ = false;
};
} // namespace rk
