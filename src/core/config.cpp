#include "config.hpp"
#include "exceptions.hpp"

#include <algorithm>
#include <cmath>

namespace rk {
void ContactSheetConfig::validate() const {
    if (font_size <= 0)
        throw ConfigurationError("Font size must be greater than 0");
    if (columns <= 0)
        throw ConfigurationError("Columns must be greater than 0");
    if (thumbnail_width && *thumbnail_width <= 0)
        throw ConfigurationError("Thumbnail width must be greater than 0");
    if (padding < 0)
        throw ConfigurationError("Padding cannot be negative");
    if (layer_width && *layer_width <= 0)
        throw ConfigurationError("Layer width must be greater than 0");
    if (layer_height && *layer_height <= 0)
        throw ConfigurationError("Layer height must be greater than 0");
}

std::pair<int, int> ContactSheetConfig::resolve_layer_size(int source_width,
                                                           int source_height) const {
    validate();
    if (source_width <= 0 || source_height <= 0)
        throw ConfigurationError("Source dimensions must be greater than 0");
    auto w = layer_width, h = layer_height;
    if (!w && !h) {
        if (!thumbnail_width)
            return {source_width, source_height};
        w = thumbnail_width;
    }
    if (!w)
        w = std::max(1, static_cast<int>(source_width * (double(*h) / source_height)));
    if (!h)
        h = std::max(1, static_cast<int>(source_height * (double(*w) / source_width)));
    return {*w, *h};
}

void ConversionConfig::validate() const {
    if (input_pattern.empty())
        throw ConfigurationError("Input pattern is required");
    if (output_path.empty())
        throw ConfigurationError("Output path is required");
    if (prefetch_workers <= 0)
        throw ConfigurationError("Prefetch workers must be greater than 0");
    if (fps && (!std::isfinite(*fps) || *fps <= 0))
        throw ConfigurationError("FPS must be greater than 0");
    if (width && *width <= 0)
        throw ConfigurationError("Width must be greater than 0");
    if (height && *height <= 0)
        throw ConfigurationError("Height must be greater than 0");
    if (bitrate && *bitrate <= 0)
        throw ConfigurationError("Bitrate must be greater than 0");
    if (quality < 0 || quality > 10)
        throw ConfigurationError("Quality must be between 0 and 10");
    if (start_frame && end_frame && *start_frame > *end_frame)
        throw ConfigurationError("Start frame must be <= end frame");
    if (contact_sheet_mode && !contact_sheet_config)
        throw ConfigurationError(
            "Contact sheet config is required when contact sheet mode is enabled");
    if (contact_sheet_config)
        contact_sheet_config->validate();
}
} // namespace rk
