#include "scaler.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <stdexcept>

namespace rk {
OIIO::ImageBuf ImageScaler::scale_buf(const OIIO::ImageBuf &source, int width, int height,
                                      const std::string &filter) {
    if (width <= 0 || height <= 0)
        throw std::invalid_argument("Image dimensions must be positive");
    OIIO::ImageBuf destination(
        OIIO::ImageSpec(width, height, source.nchannels(), OIIO::TypeDesc::FLOAT));
    if (!OIIO::ImageBufAlgo::resize(destination, source, {{"filtername", filter}}))
        throw std::runtime_error("OIIO resize failed: " + destination.geterror());
    return destination;
}
} // namespace rk
