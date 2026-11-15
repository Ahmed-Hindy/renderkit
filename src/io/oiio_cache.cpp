#include "oiio_cache.hpp"

namespace rk {
std::shared_ptr<OIIO::ImageCache> shared_image_cache() {
    static auto cache = OIIO::ImageCache::create(false);
    return cache;
}
} // namespace rk
