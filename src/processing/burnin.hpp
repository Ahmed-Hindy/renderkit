#pragma once
#include "core/config.hpp"
#include <OpenImageIO/imagebuf.h>
#include <string>

namespace rk {
struct BurnInMetadata {
    int frame = 0;
    std::string file;
    double fps = 0;
    std::string layer;
    std::string colorspace;
};
std::string format_burnin(const std::string &text, const BurnInMetadata &metadata);
void apply_burnins(OIIO::ImageBuf &buffer, const BurnInMetadata &metadata,
                   const BurnInConfig &config);
} // namespace rk
