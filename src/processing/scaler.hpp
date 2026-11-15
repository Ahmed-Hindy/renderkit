#pragma once
#include <OpenImageIO/imagebuf.h>
#include <string>

namespace rk {
class ImageScaler {
  public:
    static OIIO::ImageBuf scale_buf(const OIIO::ImageBuf &source, int width, int height,
                                    const std::string &filter = "lanczos3");
};
} // namespace rk
