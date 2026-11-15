#pragma once
#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <tuple>

namespace rk {
std::optional<std::tuple<std::string, std::string, std::string>>
split_numbered_frame_name(const std::filesystem::path &path,
                          std::optional<std::string_view> required_extension = std::nullopt);
bool pattern_has_frame_token(std::string_view filename);
std::optional<int> extract_frame_number(const std::filesystem::path &path);
std::string derive_sequence_stem(std::string_view pattern);
std::optional<std::string> build_pattern_from_path(const std::filesystem::path &path);
} // namespace rk
