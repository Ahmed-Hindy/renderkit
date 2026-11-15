#include "sequence_names.hpp"
#include "path_utils.hpp"
#include <algorithm>
#include <cctype>
#include <regex>
#include <stdexcept>

namespace rk {
namespace {
std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return s;
}
} // namespace
std::optional<std::tuple<std::string, std::string, std::string>>
split_numbered_frame_name(const std::filesystem::path &path,
                          std::optional<std::string_view> required_extension) {
    const auto ext = path_to_utf8(path.extension());
    if (required_extension) {
        auto expected = std::string(*required_extension);
        expected.erase(0, expected.find_first_not_of(" \t\r\n"));
        const auto last = expected.find_last_not_of(" \t\r\n");
        if (last == std::string::npos)
            throw std::invalid_argument("Extension cannot be empty");
        expected.erase(last + 1);
        if (expected.front() != '.')
            expected.insert(expected.begin(), '.');
        if (lower(ext) != lower(expected))
            return std::nullopt;
    }
    const auto stem = path_to_utf8(path.stem());
    auto pos = stem.size();
    while (pos > 0 && stem[pos - 1] >= '0' && stem[pos - 1] <= '9')
        --pos;
    if (pos == stem.size())
        return std::nullopt;
    return std::tuple(stem.substr(0, pos), stem.substr(pos), ext);
}
bool pattern_has_frame_token(std::string_view filename) {
    const auto name = std::string(filename);
    return std::regex_search(name, std::regex(R"(%\d+d|\$F|#)")) ||
           split_numbered_frame_name(path_from_utf8(name)).has_value();
}
std::optional<int> extract_frame_number(const std::filesystem::path &path) {
    auto parts = split_numbered_frame_name(path);
    if (!parts)
        return std::nullopt;
    try {
        return std::stoi(std::get<1>(*parts));
    } catch (const std::out_of_range &) {
        return std::nullopt;
    }
}
std::string derive_sequence_stem(std::string_view pattern) {
    auto stem = path_to_utf8(path_from_utf8(pattern).stem());
    stem = std::regex_replace(stem, std::regex(R"(%\d+d|\$F\d*|#+)"), "");
    stem = std::regex_replace(stem, std::regex(R"(\d+$)"), "");
    const auto last = stem.find_last_not_of("._- \t\r\n");
    return last == std::string::npos ? "" : stem.substr(0, last + 1);
}
std::optional<std::string> build_pattern_from_path(const std::filesystem::path &path) {
    if (!std::filesystem::is_regular_file(path) || path.stem().empty() || path.extension().empty())
        return std::nullopt;
    auto stem = path_to_utf8(path.stem());
    static const std::regex digits(R"(\d+)");
    auto begin = std::sregex_iterator(stem.begin(), stem.end(), digits),
         end = std::sregex_iterator();
    if (begin == end)
        return std::nullopt;
    std::smatch last;
    for (auto it = begin; it != end; ++it)
        last = *it;
    stem.replace(last.position(), last.length(), "%0" + std::to_string(last.length()) + "d");
    return path_to_utf8(path.parent_path() / path_from_utf8(stem + path_to_utf8(path.extension())));
}
} // namespace rk
