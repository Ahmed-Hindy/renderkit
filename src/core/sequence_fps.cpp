#include "exceptions.hpp"
#include "io/image_reader.hpp"
#include "sequence.hpp"
#include <cmath>

namespace rk {
std::optional<double>
SequenceDetector::auto_detect_fps(const std::vector<int> &frame_numbers,
                                  std::optional<double> default_fps,
                                  const std::optional<std::filesystem::path> &sample_path) {
    (void)frame_numbers;
    if (sample_path && std::filesystem::exists(*sample_path)) {
        try {
            auto fps = OIIOReader().get_metadata_fps(*sample_path);
            if (fps)
                return std::round(*fps * 1000.0) / 1000.0;
        } catch (const ImageReadError &) {
        }
    }
    return default_fps;
}
} // namespace rk
