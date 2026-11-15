#pragma once
#include "core/config.hpp"
#include <OpenImageIO/imagebuf.h>
#include <filesystem>
#include <optional>
#include <string>

namespace rk {
class ColorSpaceConverter {
  public:
    ColorSpaceConverter(ColorSpacePreset preset, std::filesystem::path config_path)
        : preset_(preset), config_path_(std::move(config_path)) {}
    OIIO::ImageBuf convert_buf(const OIIO::ImageBuf &buffer,
                               const std::optional<std::string> &input_space = {}) const;

  private:
    ColorSpacePreset preset_;
    std::filesystem::path config_path_;
};
} // namespace rk
