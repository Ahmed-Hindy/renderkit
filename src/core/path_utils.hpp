#pragma once
#include <filesystem>
#include <string>
#include <string_view>

namespace rk {
inline std::filesystem::path path_from_utf8(std::string_view text) {
    std::u8string encoded;
    encoded.reserve(text.size());
    for (unsigned char byte : text)
        encoded.push_back(static_cast<char8_t>(byte));
    return std::filesystem::path(encoded);
}
inline std::string path_to_utf8(const std::filesystem::path &path) {
    auto encoded = path.u8string();
    return std::string(encoded.begin(), encoded.end());
}
} // namespace rk
