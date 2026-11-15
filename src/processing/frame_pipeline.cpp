#include "frame_pipeline.hpp"
#include "color_space.hpp"
#include "contact_sheet.hpp"
#include "core/exceptions.hpp"
#include "io/image_reader.hpp"
#include "scaler.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <algorithm>
#include <array>
#include <cmath>

namespace rk {
PreparedFrameBuffer prepare_frame_buffer(const FramePreparationOptions &options) {
    if (!std::isfinite(options.output_scale) || options.output_scale <= 0)
        throw ConfigurationError("Output scale must be positive");
    OIIOReader reader;
    auto buffer =
        options.contact_sheet
            ? ContactSheetGenerator(*options.contact_sheet).composite_layers(options.frame_path)
            : reader.read_imagebuf(options.frame_path, options.layer);
    if (buffer.nchannels() == 3 || buffer.nchannels() == 4)
        buffer = ColorSpaceConverter(options.preset, options.ocio_config)
                     .convert_buf(buffer, options.input_space);
    else if (buffer.nchannels() > 0) {
        const std::array<int, 3> order{0, 0, 0};
        buffer = OIIO::ImageBufAlgo::channels(buffer, 3, order);
        if (buffer.has_error())
            throw ImageReadError(buffer.geterror());
    } else
        throw ImageReadError("Unsupported channel count");
    const int source_width = buffer.spec().width, source_height = buffer.spec().height;
    const int width = options.output_width.value_or(
        std::max(1, static_cast<int>(source_width * options.output_scale)));
    const int height = options.output_height.value_or(
        std::max(1, static_cast<int>(source_height * options.output_scale)));
    if (width <= 0 || height <= 0)
        throw ConfigurationError("Output dimensions must be positive");
    if (width != source_width || height != source_height)
        buffer = ImageScaler::scale_buf(buffer, width, height);
    if (options.burnin)
        apply_burnins(buffer, options.metadata, *options.burnin);
    return {std::move(buffer),
            std::min(width / double(source_width), height / double(source_height))};
}
} // namespace rk
