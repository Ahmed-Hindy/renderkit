#include "image_reader.hpp"
#include "core/constants.hpp"
#include "core/exceptions.hpp"
#include "core/path_utils.hpp"
#include "oiio_cache.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <OpenImageIO/imageio.h>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <set>

namespace rk {
namespace {
std::string trim(std::string value) {
    const auto start = value.find_first_not_of(" \t\r\n");
    if (start == std::string::npos)
        return {};
    return value.substr(start, value.find_last_not_of(" \t\r\n") - start + 1);
}
bool default_part(std::string part) {
    std::transform(part.begin(), part.end(), part.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return part == "rgba" || part == "beauty" || part == "default";
}
LayerMapEntry default_layer(const OIIO::ImageSpec &spec, int subimage) {
    int red = -1, green = -1, blue = -1, alpha = -1;
    std::vector<int> unlayered;
    for (int index = 0; index < static_cast<int>(spec.channelnames.size()); ++index) {
        auto name = spec.channelnames[index];
        if (name.find('.') != std::string::npos)
            continue;
        unlayered.push_back(index);
        std::transform(name.begin(), name.end(), name.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (name == "r" || name == "red")
            red = index;
        else if (name == "g" || name == "green")
            green = index;
        else if (name == "b" || name == "blue")
            blue = index;
        else if (name == "a" || name == "alpha")
            alpha = index;
    }
    if (red >= 0 && green >= 0 && blue >= 0) {
        std::vector<int> rgba{red, green, blue};
        if (alpha >= 0)
            rgba.push_back(alpha);
        return {subimage, std::move(rgba)};
    }
    if (!unlayered.empty() && unlayered.size() != spec.channelnames.size())
        return {subimage, std::move(unlayered)};
    return {subimage, {}};
}
std::optional<double> metadata_fps(const OIIO::ImageSpec &spec) {
    const auto parse_number = [](const std::string &raw) {
        const auto text = trim(raw);
        std::size_t end = 0;
        const double number = std::stod(text, &end);
        if (end != text.size() || !std::isfinite(number))
            throw std::invalid_argument("Invalid FPS metadata");
        return number;
    };
    for (auto key : constants::kFpsMetadataKeys) {
        auto *attr = spec.find_attribute(std::string(key));
        if (!attr)
            continue;
        try {
            if (attr->type().basetype == OIIO::TypeDesc::STRING) {
                const auto value = trim(attr->get_string());
                const auto slash = value.find('/');
                auto fps = parse_number(value.substr(0, slash));
                if (slash != std::string::npos) {
                    const auto denominator = parse_number(value.substr(slash + 1));
                    if (denominator == 0)
                        continue;
                    fps /= denominator;
                }
                return fps;
            }
            if (attr->type().basevalues() * attr->nvalues() >= 2) {
                auto ratio = [attr](auto sample) -> std::optional<double> {
                    using T = decltype(sample);
                    const auto values = attr->as_cspan<T>();
                    if (values.size() < 2 || values[1] == 0)
                        return {};
                    return static_cast<double>(values[0]) / static_cast<double>(values[1]);
                };
                std::optional<double> value;
                switch (attr->type().basetype) {
                case OIIO::TypeDesc::INT:
                    value = ratio(int{});
                    break;
                case OIIO::TypeDesc::UINT:
                    value = ratio(static_cast<unsigned>(0));
                    break;
                case OIIO::TypeDesc::FLOAT:
                    value = ratio(float{});
                    break;
                case OIIO::TypeDesc::DOUBLE:
                    value = ratio(double{});
                    break;
                default:
                    break;
                }
                if (value && std::isfinite(*value))
                    return value;
                continue;
            }
            const auto value = attr->get_float();
            if (std::isfinite(value))
                return value;
        } catch (const std::exception &) {
        }
    }
    return {};
}
std::unique_ptr<OIIO::ImageInput> open_image(const std::filesystem::path &path) {
    auto input = OIIO::ImageInput::open(path_to_utf8(path));
    if (!input)
        throw ImageReadError("Could not open image: " + path_to_utf8(path) + ": " +
                             OIIO::geterror());
    return input;
}
} // namespace
FileInfo OIIOReader::get_file_info(const std::filesystem::path &path) const {
    auto input = open_image(path);
    const auto first = input->spec();
    FileInfo info;
    info.width = first.width;
    info.height = first.height;
    info.channels = first.nchannels;
    info.fps = metadata_fps(first);
    for (auto key : constants::kColorSpaceMetadataKeys) {
        auto *attr = first.find_attribute(std::string(key));
        if (attr) {
            auto value = trim(attr->get_string());
            if (!value.empty()) {
                info.color_space = value;
                break;
            }
        }
    }
    std::set<std::string> layers;
    int count = 0;
    OIIO::ImageSpec spec;
    while (input->seek_subimage(count, 0, spec)) {
        auto part = trim(spec.get_string_attribute("name"));
        if (!part.empty())
            layers.insert(default_part(part) ? "RGBA" : part);
        for (const auto &channel : spec.channelnames) {
            const auto dot = channel.rfind('.');
            if (dot != std::string::npos)
                layers.insert(channel.substr(0, dot));
            else if (part.empty() || default_part(part))
                layers.insert("RGBA");
        }
        ++count;
    }
    info.subimages = count;
    info.layers.assign(layers.begin(), layers.end());
    const auto rgba = std::find(info.layers.begin(), info.layers.end(), "RGBA");
    if (rgba != info.layers.end())
        std::rotate(info.layers.begin(), rgba, rgba + 1);
    return info;
}
LayerMap OIIOReader::get_layer_map(const std::filesystem::path &path) const {
    auto input = open_image(path);
    LayerMap result;
    std::optional<LayerMapEntry> default_entry;
    OIIO::ImageSpec spec;
    for (int index = 0; input->seek_subimage(index, 0, spec); ++index) {
        const auto part = trim(spec.get_string_attribute("name"));
        if (!part.empty() && !default_part(part))
            result.try_emplace(part, LayerMapEntry{index, {}});
        else if (!default_entry)
            default_entry = default_layer(spec, index);
        std::unordered_map<std::string, std::vector<int>> prefixes;
        for (int channel = 0; channel < static_cast<int>(spec.channelnames.size()); ++channel) {
            const auto &name = spec.channelnames[channel];
            auto dot = name.find('.');
            if (dot != std::string::npos) {
                prefixes[name.substr(0, dot)].push_back(channel);
                const auto last_dot = name.rfind('.');
                if (last_dot != dot)
                    prefixes[name.substr(0, last_dot)].push_back(channel);
            }
        }
        for (auto &[name, channels] : prefixes)
            result.try_emplace(name, LayerMapEntry{index, std::move(channels)});
    }
    if (default_entry)
        result.try_emplace("RGBA", *default_entry);
    return result;
}
OIIO::ImageBuf OIIOReader::read_subimagebuf(const std::filesystem::path &path,
                                            int subimage_index) const {
    OIIO::ImageBuf buffer(path_to_utf8(path), subimage_index, 0, shared_image_cache());
    if (!buffer.read(subimage_index, 0, true, OIIO::TypeDesc::FLOAT))
        throw ImageReadError("Could not read image: " + path_to_utf8(path) + ": " +
                             buffer.geterror());
    return buffer;
}
OIIO::ImageBuf OIIOReader::read_imagebuf(const std::filesystem::path &path,
                                         const std::optional<std::string> &layer) const {
    auto layers = get_layer_map(path);
    const bool explicit_layer = layer && !layer->empty();
    auto it = layers.find(explicit_layer ? *layer : "RGBA");
    if (it == layers.end() && !explicit_layer)
        return read_subimagebuf(path, 0);
    if (it == layers.end())
        throw ImageReadError("Image layer not found: " + *layer);
    auto buffer = read_subimagebuf(path, it->second.subimage_index);
    if (it->second.channel_indices.empty())
        return buffer;
    auto result = OIIO::ImageBufAlgo::channels(
        buffer, static_cast<int>(it->second.channel_indices.size()), it->second.channel_indices);
    if (result.has_error())
        throw ImageReadError("Could not extract layer: " + result.geterror());
    return result;
}
std::optional<double> OIIOReader::get_metadata_fps(const std::filesystem::path &path) const {
    return get_file_info(path).fps;
}
} // namespace rk
