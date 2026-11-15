#pragma once
#include "config.hpp"
#include <filesystem>
#include <functional>

namespace rk {
using ProgressCallback = std::function<bool(int current, int total)>;
class SequenceConverter {
  public:
    SequenceConverter(ConversionConfig config, std::filesystem::path ocio_config)
        : config_(std::move(config)), ocio_config_(std::move(ocio_config)) {}
    void convert(const ProgressCallback &progress = {}) const;

  private:
    ConversionConfig config_;
    std::filesystem::path ocio_config_;
};
} // namespace rk
