#pragma once
#include <filesystem>
#include <functional>
#include <optional>
#include <string>

namespace rk {
using LogCallback = std::function<void(const std::string &)>;
std::filesystem::path setup_logging(LogCallback ui_sink = {},
                                    std::optional<bool> enable_console = {});
} // namespace rk
