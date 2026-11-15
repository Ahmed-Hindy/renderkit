#include "preview_image.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <array>
#include <stdexcept>

namespace rk {
QImage preview_image(const OIIO::ImageBuf &buffer) {
    auto channels = buffer.nchannels();
    if (channels != 1 && channels != 3 && channels != 4)
        throw std::invalid_argument("Preview images require one, three, or four channels");
    auto clamped = OIIO::ImageBufAlgo::clamp(buffer, 0.0f, 1.0f, true);
    if (clamped.has_error())
        throw std::runtime_error(clamped.geterror());
    if (channels == 1) {
        const std::array<int, 3> channel_order{0, 0, 0};
        clamped = OIIO::ImageBufAlgo::channels(clamped, 3, channel_order);
        if (clamped.has_error())
            throw std::runtime_error(clamped.geterror());
        channels = 3;
    }
    const auto &spec = clamped.spec();
    QImage image(spec.width, spec.height,
                 channels == 3 ? QImage::Format_RGB888 : QImage::Format_RGBA8888);
    if (image.isNull())
        throw std::runtime_error("Could not allocate preview image");
    const OIIO::ROI region(spec.x, spec.x + spec.width, spec.y, spec.y + spec.height, spec.z,
                           spec.z + 1, 0, channels);
    OIIO::span<unsigned char> pixels(image.bits(), static_cast<size_t>(image.sizeInBytes()));
    if (!clamped.get_pixels(region, pixels, channels, image.bytesPerLine()))
        throw std::runtime_error("Could not extract preview pixels: " + clamped.geterror());
    return image;
}
} // namespace rk
