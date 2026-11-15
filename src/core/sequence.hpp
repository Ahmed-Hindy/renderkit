#pragma once
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace rk {
struct FrameSequence {
    std::filesystem::path base_path;
    std::string pattern;
    std::vector<int> frame_numbers;
    int padding;
    std::filesystem::path get_file_path(int frame_number) const;
};
class SequenceDetector {
  public:
    static FrameSequence detect_sequence(const std::string &pattern);
    static std::optional<double>
    auto_detect_fps(const std::vector<int> &frame_numbers, std::optional<double> default_fps = {},
                    const std::optional<std::filesystem::path> &sample_path = {});
};
} // namespace rk
