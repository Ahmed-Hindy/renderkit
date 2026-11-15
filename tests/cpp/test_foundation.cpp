#include "core/config.hpp"
#include "core/exceptions.hpp"
#include "core/sequence.hpp"
#include "core/sequence_names.hpp"
#include "io/file_utils.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

void check(bool condition) {
    if (!condition)
        throw std::runtime_error("check failed");
}
int main() try {
    namespace fs = std::filesystem;
    rk::ContactSheetConfig sheet;
    sheet.thumbnail_width = 100;
    check(sheet.resolve_layer_size(1920, 1080) == std::pair(100, 56));
    rk::ConversionConfig config;
    config.input_pattern = "input";
    config.output_path = "output";
    config.validate();
    config.quality = 11;
    try {
        config.validate();
        throw std::runtime_error("invalid quality accepted");
    } catch (const rk::ConfigurationError &) {
    }
    auto built = rk::ConversionConfigBuilder()
                     .with_input_pattern("frames.%04d.exr")
                     .with_output_path("output.mp4")
                     .with_frame_range(1001, 1010)
                     .with_quality(8)
                     .build();
    check(built.start_frame == 1001 && built.end_frame == 1010 && built.quality == 8);
    try {
        (void)rk::ContactSheetConfigBuilder().with_columns(0).build();
        throw std::runtime_error("invalid columns accepted");
    } catch (const rk::ConfigurationError &) {
    }
    auto dir = fs::temp_directory_path() /
               ("renderkit-native-foundation-test-" +
                std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    check(fs::create_directory(dir));
    const auto a = dir / "shot.01.v002.1001.exr", b = dir / "shot.01.v002.1003.exr";
    std::ofstream(a.string()).put('a');
    std::ofstream(b.string()).put('b');
    check(rk::build_pattern_from_path(a) == (dir / "shot.01.v002.%04d.exr").string());
    check(rk::extract_frame_number(a) == 1001);
    check(rk::derive_sequence_stem("shot.%04d.exr") == "shot");
    check(rk::validate_output_filename("video.MP4").first);
    check(!rk::validate_output_filename("video.png").first);
    check(rk::convert_path_to_pattern(a.string()) == (dir / "shot.01.v002.####.exr").string());
    for (const auto &name : {"shot.01.v002.%04d.exr", "shot.01.v002.$F4.exr",
                             "shot.01.v002.####.exr", "shot.01.v002.1001.exr"}) {
        auto seq = rk::SequenceDetector::detect_sequence((dir / name).string());
        check(seq.frame_numbers == std::vector<int>({1001, 1003}));
        check(seq.get_file_path(1003) == b);
    }
    fs::remove(a);
    fs::remove(b);
    fs::remove(dir);
    std::cout << "Native foundation checks passed\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
