#include "burnin.hpp"
#include "font.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <algorithm>
#include <array>
#include <fmt/format.h>
#include <stdexcept>

namespace rk {
std::string format_burnin(const std::string &text, const BurnInMetadata &metadata) {
    try {
        return fmt::format(fmt::runtime(text), fmt::arg("frame", metadata.frame),
                           fmt::arg("file", metadata.file), fmt::arg("fps", metadata.fps),
                           fmt::arg("layer", metadata.layer),
                           fmt::arg("colorspace", metadata.colorspace));
    } catch (const fmt::format_error &error) {
        throw std::invalid_argument(std::string("Invalid burn-in template: ") + error.what());
    }
}
void apply_burnins(OIIO::ImageBuf &buffer, const BurnInMetadata &metadata,
                   const BurnInConfig &config) {
    if (config.elements.empty())
        return;
    const auto &spec = buffer.spec();
    int max_size = 0;
    for (const auto &element : config.elements)
        max_size = std::max(max_size, element.font_size);
    const int bar_height = max_size * 2;
    if (config.use_background) {
        const float multiplier = 1.0f - std::clamp(config.background_opacity, 0, 100) / 100.0f;
        const std::array<float, 4> factors{multiplier, multiplier, multiplier, 1.0f};
        const OIIO::ROI roi(spec.x, spec.x + spec.width, spec.y,
                            std::min(spec.y + bar_height, spec.y + spec.height), spec.z,
                            spec.z + 1);
        if (!OIIO::ImageBufAlgo::mul(buffer, buffer, OIIO::cspan<float>(factors), roi))
            throw std::runtime_error("Could not draw burn-in background: " + buffer.geterror());
    }
    for (const auto &element : config.elements) {
        auto align = OIIO::ImageBufAlgo::TextAlignX::Left;
        if (element.alignment == "center")
            align = OIIO::ImageBufAlgo::TextAlignX::Center;
        else if (element.alignment == "right")
            align = OIIO::ImageBufAlgo::TextAlignX::Right;
        else if (element.alignment != "left")
            throw std::invalid_argument("Invalid burn-in alignment");
        int x = element.x;
        if (x == 0)
            x = element.alignment == "center"  ? spec.width / 2
                : element.alignment == "right" ? spec.width - 20
                                               : 20;
        int y = element.y;
        if (config.use_background && y < bar_height)
            y = static_cast<int>(bar_height * 0.7);
        const std::array<float, 4> color{element.color[0], element.color[1], element.color[2],
                                         1.0f};
        const auto text = format_burnin(element.text_template, metadata);
        if (text.empty())
            continue;
        const auto font = element.font.empty() ? default_font() : element.font;
        const auto bounds = OIIO::ImageBufAlgo::text_size(text, element.font_size, font);
        if (bounds.defined()) {
            int text_x = spec.x + x;
            if (align == OIIO::ImageBufAlgo::TextAlignX::Center)
                text_x -= bounds.width() / 2 + bounds.xbegin;
            else if (align == OIIO::ImageBufAlgo::TextAlignX::Right)
                text_x -= bounds.width();
            const int text_y = spec.y + y;
            if (text_x + bounds.xend <= spec.x || text_x + bounds.xbegin >= spec.x + spec.width ||
                text_y + bounds.yend <= spec.y || text_y + bounds.ybegin >= spec.y + spec.height)
                continue;
        }
        if (!OIIO::ImageBufAlgo::render_text(buffer, spec.x + x, spec.y + y, text,
                                             element.font_size, font, color, align))
            throw std::runtime_error("Could not render burn-in text: " + buffer.geterror());
    }
}
} // namespace rk
