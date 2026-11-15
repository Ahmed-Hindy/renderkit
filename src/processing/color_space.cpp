#include "color_space.hpp"
#include "core/constants.hpp"
#include "core/exceptions.hpp"
#include "core/path_utils.hpp"
#include <OpenImageIO/color.h>
#include <OpenImageIO/imagebufalgo.h>
#include <algorithm>
#include <cctype>
#include <vector>

namespace rk {
namespace {
std::string lower(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return value;
}
std::string resolve(const OIIO::ColorConfig &config, const std::string &name) {
    for (int index = 0; index < config.getNumColorSpaces(); ++index) {
        const char *candidate = config.getColorSpaceNameByIndex(index);
        if (candidate && lower(candidate) == lower(name))
            return candidate;
    }
    if (const char *role = config.getColorSpaceNameByRole(name))
        return role;
    for (const auto &role : config.getRoles()) {
        if (lower(role) == lower(name)) {
            if (const char *space = config.getColorSpaceNameByRole(role))
                return space;
        }
    }
    return {};
}
std::vector<std::string> available(const OIIO::ColorConfig &config,
                                   const std::vector<std::string> &candidates) {
    std::vector<std::string> result;
    for (const auto &candidate : candidates) {
        auto space = resolve(config, candidate);
        if (!space.empty() && std::find(result.begin(), result.end(), space) == result.end())
            result.push_back(space);
    }
    return result;
}
OIIO::ImageBuf checked(OIIO::ImageBuf value) {
    if (value.has_error())
        throw ColorSpaceError(value.geterror());
    return value;
}
} // namespace
OIIO::ImageBuf
ColorSpaceConverter::convert_buf(const OIIO::ImageBuf &buffer,
                                 const std::optional<std::string> &input_space) const {
    auto source = checked(OIIO::ImageBufAlgo::copy(buffer, OIIO::TypeDesc::FLOAT));
    if (preset_ == ColorSpacePreset::NoConversion)
        return source;
    if (source.nchannels() != 3 && source.nchannels() != 4)
        throw ColorSpaceError("Color conversion expects 3 or 4 channel images.");
    if (!std::filesystem::is_regular_file(config_path_))
        throw ColorSpaceError("Bundled OCIO config not found.");
    OIIO::ColorConfig config(path_to_utf8(config_path_));
    if (auto error = config.geterror(); !error.empty())
        throw ColorSpaceError(error);
    const std::vector<std::string> linear{"linear", "Linear", "scene_linear", "scene-linear"};
    const std::vector<std::string> srgb{"sRGB", "srgb", "Output - sRGB", "srgb_display",
                                        "out_srgb"};
    const std::vector<std::string> rec709{"Rec709", "Rec.709",          "rec709",         "BT.709",
                                          "bt709",  "Output - Rec.709", "Output - Rec709"};
    std::vector<std::string> from, to;
    if (preset_ == ColorSpacePreset::OcioConversion) {
        if (!input_space || input_space->empty())
            throw ColorSpaceError("OCIO input color space is required.");
        auto resolved = resolve(config, *input_space);
        from.push_back(resolved.empty() ? *input_space : resolved);
        std::vector<std::string> outputs;
        for (auto candidate : constants::kOcioOutputCandidates)
            outputs.emplace_back(candidate);
        to = available(config, outputs);
        if (to.empty()) {
            const char *display = config.getDefaultDisplayName();
            const char *view = display ? config.getDefaultViewName(display) : nullptr;
            const char *space =
                display && view ? config.getDisplayViewColorSpaceName(display, view) : nullptr;
            if (space && *space)
                to.emplace_back(space);
        }
    } else if (preset_ == ColorSpacePreset::SrgbToLinear) {
        source = checked(OIIO::ImageBufAlgo::clamp(source, 0.0f, 1.0f));
        from = available(config, srgb);
        to = available(config, linear);
    } else {
        auto denominator = checked(OIIO::ImageBufAlgo::add(source, 1.0f));
        source = checked(OIIO::ImageBufAlgo::clamp(
            checked(OIIO::ImageBufAlgo::div(source, denominator)), 0.0f, 1.0f));
        from = available(config, linear);
        to = available(config, preset_ == ColorSpacePreset::LinearToRec709 ? rec709 : srgb);
    }
    std::string error;
    for (const auto &source_space : from)
        for (const auto &target_space : to) {
            auto result = OIIO::ImageBufAlgo::colorconvert(source, source_space, target_space, true,
                                                           "", "", &config);
            if (!result.has_error()) {
                if (preset_ == ColorSpacePreset::LinearToSrgb ||
                    preset_ == ColorSpacePreset::LinearToRec709)
                    return checked(OIIO::ImageBufAlgo::clamp(result, 0.0f, 1.0f));
                return result;
            }
            error = result.geterror();
        }
    throw ColorSpaceError(error.empty() ? "Could not resolve color spaces in OCIO config." : error);
}
} // namespace rk
