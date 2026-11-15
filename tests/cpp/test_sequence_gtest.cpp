#include "core/config.hpp"
#include "core/exceptions.hpp"
#include "core/path_utils.hpp"
#include "core/sequence.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <gtest/gtest.h>
#include <limits>

namespace {
class SequenceTest : public ::testing::Test {
  protected:
    void SetUp() override {
        dir = std::filesystem::temp_directory_path() /
              ("renderkit-sequence-" +
               std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
        ASSERT_TRUE(std::filesystem::create_directory(dir));
    }
    void TearDown() override {
        for (const auto &name : files)
            std::filesystem::remove(dir / name);
        std::filesystem::remove(dir);
    }
    void add(const std::string &name) {
        files.push_back(name);
        std::ofstream(dir / name).put('x');
    }
    std::filesystem::path dir;
    std::vector<std::string> files;
};

TEST_F(SequenceTest, ParsesTokensAndPreservesMissingFrames) {
    add("shot.01.v002.1003.exr");
    add("shot.01.v002.1001.exr");
    for (const auto *pattern : {"shot.01.v002.%04d.exr", "shot.01.v002.$F4.exr",
                                "shot.01.v002.####.exr", "shot.01.v002.1001.exr"}) {
        auto sequence = rk::SequenceDetector::detect_sequence((dir / pattern).string());
        EXPECT_EQ(sequence.frame_numbers, (std::vector<int>{1001, 1003}));
        EXPECT_EQ(sequence.get_file_path(1003), dir / "shot.01.v002.1003.exr");
    }
}
TEST_F(SequenceTest, EscapesRegexCharactersInFilename) {
    add("shot[1].0001.exr");
    add("shot1.0002.exr");
    auto sequence = rk::SequenceDetector::detect_sequence((dir / "shot[1].%04d.exr").string());
    EXPECT_EQ(sequence.frame_numbers, (std::vector<int>{1}));
}
TEST_F(SequenceTest, ThrowsForUnmatchedPattern) {
    EXPECT_THROW(rk::SequenceDetector::detect_sequence((dir / "missing.%04d.exr").string()),
                 rk::SequenceDetectionError);
}
TEST_F(SequenceTest, DetectsUnicodeDirectoryAndFilename) {
    const auto unicode_dir = dir / rk::path_from_utf8("dir-\xE6\xBC\xA2");
    ASSERT_TRUE(std::filesystem::create_directory(unicode_dir));
    const auto frame = unicode_dir / rk::path_from_utf8("shot-\xE6\xBC\xA2.0001.exr");
    std::ofstream(frame).put('x');
    const auto pattern =
        rk::path_to_utf8(unicode_dir / rk::path_from_utf8("shot-\xE6\xBC\xA2.%04d.exr"));
    auto sequence = rk::SequenceDetector::detect_sequence(pattern);
    EXPECT_EQ(sequence.get_file_path(1), frame);
    std::filesystem::remove(frame);
    std::filesystem::remove(unicode_dir);
}
TEST(ConfigurationTest, RejectsInvalidRangeAndContactSheet) {
    EXPECT_THROW(rk::ConversionConfigBuilder()
                     .with_input_pattern("a.%04d.exr")
                     .with_output_path("b.mp4")
                     .with_frame_range(10, 1)
                     .build(),
                 rk::ConfigurationError);
    EXPECT_THROW(rk::ContactSheetConfigBuilder().with_columns(0).build(), rk::ConfigurationError);
    EXPECT_THROW(rk::ConversionConfigBuilder()
                     .with_input_pattern("a.%04d.exr")
                     .with_output_path("b.mp4")
                     .with_fps(std::numeric_limits<double>::quiet_NaN())
                     .build(),
                 rk::ConfigurationError);
}
} // namespace
