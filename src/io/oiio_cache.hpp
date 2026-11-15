#pragma once
#include <memory>

#include <OpenImageIO/imagecache.h>

namespace rk {
std::shared_ptr<OIIO::ImageCache> shared_image_cache();
} // namespace rk
