#pragma once
#include <optional>
#include <string>
#include <vector>

namespace rk {
struct FileInfo {
    int width = 0;
    int height = 0;
    int channels = 0;
    std::vector<std::string> layers;
    std::optional<double> fps;
    std::optional<std::string> color_space;
    int subimages = 1;
};
} // namespace rk
