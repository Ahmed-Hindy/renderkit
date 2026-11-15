#pragma once
#include <string>
#include <string_view>
#include <utility>

namespace rk {
std::pair<bool, std::string> validate_output_filename(std::string_view path);
std::string convert_path_to_pattern(std::string_view path);
} // namespace rk
