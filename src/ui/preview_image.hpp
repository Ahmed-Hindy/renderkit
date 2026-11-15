#pragma once
#include <OpenImageIO/imagebuf.h>
#include <QImage>

namespace rk {
QImage preview_image(const OIIO::ImageBuf &buffer);
} // namespace rk
