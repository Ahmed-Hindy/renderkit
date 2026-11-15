#pragma once
#include "file_info.hpp"
#include <OpenImageIO/imagebuf.h>
#include <filesystem>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace rk {
struct LayerMapEntry {
    int subimage_index = 0;
    std::vector<int> channel_indices;
};
using LayerMap = std::unordered_map<std::string, LayerMapEntry>;
class OIIOReader {
  public:
    FileInfo get_file_info(const std::filesystem::path &path) const;
    LayerMap get_layer_map(const std::filesystem::path &path) const;
    OIIO::ImageBuf read_subimagebuf(const std::filesystem::path &path, int subimage_index) const;
    OIIO::ImageBuf read_imagebuf(const std::filesystem::path &path,
                                 const std::optional<std::string> &layer = {}) const;
    std::optional<double> get_metadata_fps(const std::filesystem::path &path) const;
};
} // namespace rk
