#pragma once

#include <array>
#include <string_view>

namespace rk::constants {
inline constexpr std::string_view kAppVersion = "2.0.0";
inline constexpr std::array<std::string_view, 9> kFpsMetadataKeys = {
    "framesPerSecond", "exr/FramesPerSecond", "fps",       "arnold/fps", "rs/fps",
    "vray/fps",        "mantra/fps",          "karma/fps", "cap_fps"};
inline constexpr std::array<std::string_view, 5> kColorSpaceMetadataKeys = {
    "exr/oiio:ColorSpace", "oiio:ColorSpace", "colorSpace", "interchange/color_space",
    "acesImageContainerFlag"};
inline constexpr std::array<std::string_view, 4> kOcioOutputCandidates = {
    "Output - sRGB", "sRGB", "srgb_display", "out_srgb"};
inline constexpr std::array<std::string_view, 7> kOiioSupportedExtensions = {
    "exr", "png", "jpg", "jpeg", "tif", "tiff", "dpx"};
inline constexpr std::array<std::string_view, 2> kSupportedVideoExtensions = {"mp4", "mov"};
} // namespace rk::constants
