#pragma once

#include <array>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace rk {
enum class ColorSpacePreset {
    LinearToSrgb,
    LinearToRec709,
    SrgbToLinear,
    NoConversion,
    OcioConversion
};

struct BurnInElement {
    std::string text_template;
    int x = 50, y = 50;
    std::string font;
    int font_size = 24;
    std::array<float, 3> color = {1, 1, 1};
    std::string alignment = "left";
};
struct BurnInConfig {
    std::vector<BurnInElement> elements;
    bool use_background = true;
    int background_opacity = 30;
};
struct ContactSheetConfig {
    int columns = 4;
    std::optional<int> thumbnail_width;
    int padding = 4;
    std::array<float, 4> background_color = {0.1f, 0.1f, 0.1f, 1.0f};
    bool show_labels = true;
    int font_size = 16;
    std::optional<int> layer_width, layer_height;
    void validate() const;
    std::pair<int, int> resolve_layer_size(int source_width, int source_height) const;
};
class ContactSheetConfigBuilder {
  public:
    ContactSheetConfigBuilder &with_columns(int value) {
        config_.columns = value;
        return *this;
    }
    ContactSheetConfigBuilder &with_thumbnail_width(int value) {
        config_.thumbnail_width = value;
        return *this;
    }
    ContactSheetConfigBuilder &with_layer_size(int width, std::optional<int> height = {}) {
        config_.layer_width = width;
        config_.layer_height = height;
        return *this;
    }
    ContactSheetConfigBuilder &with_padding(int value) {
        config_.padding = value;
        return *this;
    }
    ContactSheetConfigBuilder &with_labels(bool show, int font_size = 16) {
        config_.show_labels = show;
        config_.font_size = font_size;
        return *this;
    }
    ContactSheetConfig build() const {
        config_.validate();
        return config_;
    }

  private:
    ContactSheetConfig config_;
};
struct ConversionConfig {
    std::string input_pattern, output_path;
    int prefetch_workers = 1;
    std::optional<double> fps;
    ColorSpacePreset color_space_preset = ColorSpacePreset::LinearToSrgb;
    std::optional<int> width, height;
    std::string codec = "libx264";
    std::optional<int> bitrate;
    int quality = 10;
    std::optional<std::string> layer;
    std::optional<int> start_frame, end_frame;
    std::optional<std::string> explicit_input_color_space;
    std::optional<BurnInConfig> burnin_config;
    bool contact_sheet_mode = false;
    std::optional<ContactSheetConfig> contact_sheet_config;
    void validate() const;
};
class ConversionConfigBuilder {
  public:
    ConversionConfigBuilder &with_input_pattern(std::string value) {
        config_.input_pattern = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_output_path(std::string value) {
        config_.output_path = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_prefetch_workers(int value) {
        config_.prefetch_workers = value;
        return *this;
    }
    ConversionConfigBuilder &with_fps(double value) {
        config_.fps = value;
        return *this;
    }
    ConversionConfigBuilder &with_color_space_preset(ColorSpacePreset value) {
        config_.color_space_preset = value;
        return *this;
    }
    ConversionConfigBuilder &with_explicit_input_color_space(std::string value) {
        config_.explicit_input_color_space = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_resolution(int width, int height) {
        config_.width = width;
        config_.height = height;
        return *this;
    }
    ConversionConfigBuilder &with_codec(std::string value) {
        config_.codec = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_bitrate(int value) {
        config_.bitrate = value;
        return *this;
    }
    ConversionConfigBuilder &with_quality(int value) {
        config_.quality = value;
        return *this;
    }
    ConversionConfigBuilder &with_layer(std::string value) {
        config_.layer = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_frame_range(std::optional<int> start, std::optional<int> end) {
        config_.start_frame = start;
        config_.end_frame = end;
        return *this;
    }
    ConversionConfigBuilder &with_burnin(BurnInConfig value) {
        config_.burnin_config = std::move(value);
        return *this;
    }
    ConversionConfigBuilder &with_contact_sheet(bool enabled,
                                                std::optional<ContactSheetConfig> value = {}) {
        config_.contact_sheet_mode = enabled;
        config_.contact_sheet_config = std::move(value);
        return *this;
    }
    ConversionConfig build() const {
        config_.validate();
        return config_;
    }

  private:
    ConversionConfig config_;
};
} // namespace rk
