#pragma once
#include "core/config.hpp"
#include <OpenImageIO/imagebuf.h>
#include <filesystem>
#include <utility>

namespace rk {
std::pair<int, int> contact_sheet_label_metrics(const ContactSheetConfig &config);
class ContactSheetGenerator {
  public:
    explicit ContactSheetGenerator(ContactSheetConfig config) : config_(std::move(config)) {
        config_.validate();
    }
    std::pair<int, int> canvas_size(int layers, int source_width, int source_height) const;
    OIIO::ImageBuf composite_layers(const std::filesystem::path &frame_path) const;

  private:
    ContactSheetConfig config_;
};
} // namespace rk
