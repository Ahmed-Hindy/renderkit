#include "file_utils.hpp"
#include "core/path_utils.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <regex>

namespace rk {
std::pair<bool, std::string> validate_output_filename(std::string_view path) {
    const auto first = path.find_first_not_of(" \t\r\n");
    if (first == std::string_view::npos)
        return {false, "Output path is empty."};
    auto value = std::string(path.substr(first, path.find_last_not_of(" \t\r\n") - first + 1));
    auto file = path_from_utf8(value);
    auto ext = path_to_utf8(file.extension());
    if (ext.empty())
        return {false, "Output path must have a file extension (e.g., .mp4)."};
    std::transform(ext.begin(), ext.end(), ext.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (ext != ".mp4" && ext != ".mov")
        return {false, "Unsupported video extension: " + ext + ". Supported: mp4, mov"};
    if (path_to_utf8(file.filename()).find_first_of("<>:\"|?*") != std::string::npos)
        return {false, "Filename contains invalid characters: <>:\"|?*"};
    return {true, ""};
}
std::string convert_path_to_pattern(std::string_view path) {
    auto file = path_from_utf8(path);
    auto name = path_to_utf8(file.filename());
    static const std::regex digits(R"(\d+)");
    auto begin = std::sregex_iterator(name.begin(), name.end(), digits),
         end = std::sregex_iterator();
    if (begin == end)
        return std::string(path);
    std::smatch last;
    for (auto it = begin; it != end; ++it)
        last = *it;
    name.replace(last.position(), last.length(), std::string(last.length(), '#'));
    return path_to_utf8(file.parent_path() / path_from_utf8(name));
}
} // namespace rk
