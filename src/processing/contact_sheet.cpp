#include "contact_sheet.hpp"
#include "core/exceptions.hpp"
#include "font.hpp"
#include "io/image_reader.hpp"
#include "scaler.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <algorithm>
#include <array>
#include <unordered_map>

namespace rk {
std::pair<int, int> contact_sheet_label_metrics(const ContactSheetConfig &config) {
    if (!config.show_labels)
        return {0, 0};
    const int gap = std::max(4, static_cast<int>(config.font_size * 0.01));
    return {gap, gap + static_cast<int>(config.font_size * 1.4)};
}
std::pair<int, int> ContactSheetGenerator::canvas_size(int layers, int source_width,
                                                       int source_height) const {
    if (layers <= 0)
        throw ConfigurationError("Contact sheet needs at least one layer");
    const auto [width, height] = config_.resolve_layer_size(source_width, source_height);
    const int rows = (layers + config_.columns - 1) / config_.columns;
    const auto [gap, label_height] = contact_sheet_label_metrics(config_);
    (void)gap;
    return {(width + config_.padding * 2) * config_.columns,
            (height + config_.padding * 2 + label_height) * rows};
}
OIIO::ImageBuf
ContactSheetGenerator::composite_layers(const std::filesystem::path &frame_path) const {
    OIIOReader reader;
    auto info = reader.get_file_info(frame_path);
    auto map = reader.get_layer_map(frame_path);
    const auto [thumb_width, thumb_height] = config_.resolve_layer_size(info.width, info.height);
    const auto [canvas_width, canvas_height] =
        canvas_size(static_cast<int>(info.layers.size()), info.width, info.height);
    const auto [label_gap, label_height] = contact_sheet_label_metrics(config_);
    const int cell_width = thumb_width + config_.padding * 2;
    const int cell_height = thumb_height + config_.padding * 2 + label_height;
    OIIO::ImageBuf canvas(OIIO::ImageSpec(canvas_width, canvas_height, 3, OIIO::TypeDesc::FLOAT));
    if (!OIIO::ImageBufAlgo::fill(canvas, config_.background_color))
        throw ImageReadError(canvas.geterror());
    std::unordered_map<int, OIIO::ImageBuf> subimages;
    for (std::size_t index = 0; index < info.layers.size(); ++index) {
        const auto &name = info.layers[index];
        const auto it = map.find(name);
        if (it == map.end())
            throw ImageReadError("Image layer not found: " + name);
        const auto &entry = it->second;
        if (!subimages.contains(entry.subimage_index))
            subimages.emplace(entry.subimage_index,
                              reader.read_subimagebuf(frame_path, entry.subimage_index));
        auto layer = subimages.at(entry.subimage_index);
        if (!entry.channel_indices.empty())
            layer = OIIO::ImageBufAlgo::channels(
                layer, static_cast<int>(entry.channel_indices.size()), entry.channel_indices);
        const std::array<int, 3> order =
            layer.nchannels() < 3 ? std::array<int, 3>{0, 0, 0} : std::array<int, 3>{0, 1, 2};
        layer = OIIO::ImageBufAlgo::channels(layer, 3, order);
        if (layer.has_error())
            throw ImageReadError(layer.geterror());
        if (layer.spec().width != thumb_width || layer.spec().height != thumb_height)
            layer = ImageScaler::scale_buf(layer, thumb_width, thumb_height);
        const int x = static_cast<int>(index % config_.columns) * cell_width + config_.padding;
        const int y = static_cast<int>(index / config_.columns) * cell_height + config_.padding;
        if (!OIIO::ImageBufAlgo::paste(canvas, x, y, 0, 0, layer))
            throw ImageReadError(canvas.geterror());
        if (config_.show_labels) {
            const int baseline = y + thumb_height + label_gap + config_.font_size -
                                 std::max(2, static_cast<int>(config_.font_size * 0.2));
            if (!OIIO::ImageBufAlgo::render_text(canvas, x, baseline, name, config_.font_size,
                                                 default_font()))
                throw ImageReadError(canvas.geterror());
        }
    }
    return canvas;
}
} // namespace rk
