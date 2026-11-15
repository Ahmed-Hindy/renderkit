#pragma once
#include "burnin.hpp"
#include "core/config.hpp"
#include <OpenImageIO/imagebuf.h>
#include <filesystem>
#include <optional>
#include <string>

namespace rk {
struct FramePreparationOptions {
    std::filesystem::path frame_path;
    std::filesystem::path ocio_config;
    ColorSpacePreset preset = ColorSpacePreset::LinearToSrgb;
    std::optional<std::string> input_space;
    std::optional<std::string> layer;
    std::optional<ContactSheetConfig> contact_sheet;
    std::optional<BurnInConfig> burnin;
    BurnInMetadata metadata;
    std::optional<int> output_width;
    std::optional<int> output_height;
    double output_scale = 1.0;
};
struct PreparedFrameBuffer {
    OIIO::ImageBuf buffer;
    double applied_scale = 1.0;
};
PreparedFrameBuffer prepare_frame_buffer(const FramePreparationOptions &options);
} // namespace rk
