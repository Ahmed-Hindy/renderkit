#include "core/path_utils.hpp"
#include "core/sequence.hpp"
#include "io/image_reader.hpp"
#include "io/oiio_cache.hpp"
#include "processing/burnin.hpp"
#include "processing/color_space.hpp"
#include "processing/contact_sheet.hpp"
#include "processing/frame_pipeline.hpp"
#include "processing/scaler.hpp"
#include <OpenImageIO/imagebufalgo.h>
#include <OpenImageIO/imageio.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <stdexcept>

int main() try {
    auto first = rk::shared_image_cache();
    auto second = rk::shared_image_cache();
    if (!first || first != second)
        throw std::runtime_error("Image cache is not shared");
    auto path =
        std::filesystem::temp_directory_path() /
        ("renderkit-reader-" +
         std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".exr");
    OIIO::ImageSpec spec(2, 1, 4, OIIO::TypeDesc::FLOAT);
    spec.channelnames = {"R", "G", "B", "depth.Z"};
    spec.attribute("fps", 24.0f);
    const int rational_fps[] = {24000, 1001};
    spec.attribute("framesPerSecond", OIIO::TypeRational, rational_fps);
    auto output = OIIO::ImageOutput::create(path.string());
    float pixels[] = {0.1f, 0.2f, 0.3f, 0.4f, 0.5f, 0.6f, 0.7f, 0.8f};
    if (!output || !output->open(path.string(), spec) ||
        !output->write_image(OIIO::TypeDesc::FLOAT, pixels) || !output->close())
        throw std::runtime_error("Could not create test image");
    rk::OIIOReader reader;
    auto info = reader.get_file_info(path);
    if (info.width != 2 || info.height != 1 || info.channels != 4 || !info.fps ||
        std::abs(*info.fps - 24000.0 / 1001.0) > 0.001 ||
        info.layers != std::vector<std::string>({"RGBA", "depth"}))
        throw std::runtime_error("Unexpected image metadata");
    auto unicode_dir =
        path.parent_path() /
        rk::path_from_utf8(
            "renderkit-reader-\xE6\xBC\xA2-" +
            std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    std::filesystem::create_directory(unicode_dir);
    auto unicode_frame = unicode_dir / rk::path_from_utf8("shot-\xE6\xBC\xA2.exr");
    std::filesystem::copy_file(path, unicode_frame);
    if (reader.get_file_info(unicode_frame).width != 2 ||
        reader.read_imagebuf(unicode_frame).spec().height != 1)
        throw std::runtime_error("Could not read image from a Unicode path");
    first->invalidate(OIIO::ustring(rk::path_to_utf8(unicode_frame)));
    std::filesystem::remove(unicode_frame);
    std::filesystem::remove(unicode_dir);
    if (rk::SequenceDetector::auto_detect_fps({1001}, 30.0, path) != 23.976)
        throw std::runtime_error("Failed to detect FPS from metadata");
    auto depth = reader.read_imagebuf(path, "depth");
    if (depth.spec().nchannels != 1 || std::abs(depth.getchannel(0, 0, 0, 0) - 0.4f) > 0.001f)
        throw std::runtime_error("Incorrect depth layer pixels");
    auto multilayer_path = path.parent_path() / (path.stem().string() + "-rgba.exr");
    OIIO::ImageSpec multilayer_spec(1, 1, 7, OIIO::TypeDesc::FLOAT);
    multilayer_spec.channelnames = {"R", "G", "B", "A", "depth.Z", "motion.X", "motion.Y"};
    multilayer_spec.attribute("fps", "24invalid");
    multilayer_spec.attribute("arnold/fps", 30.0f);
    auto multilayer_output = OIIO::ImageOutput::create(multilayer_path.string());
    const float multilayer_pixels[] = {0.1f, 0.2f, 0.3f, 0.7f, 0.9f, 0.4f, 0.5f};
    if (!multilayer_output || !multilayer_output->open(multilayer_path.string(), multilayer_spec) ||
        !multilayer_output->write_image(OIIO::TypeDesc::FLOAT, multilayer_pixels) ||
        !multilayer_output->close())
        throw std::runtime_error("Could not create RGBA plus AOV test image");
    auto rgba = reader.read_imagebuf(multilayer_path, "RGBA");
    if (reader.get_metadata_fps(multilayer_path) != 30.0)
        throw std::runtime_error("Invalid FPS metadata did not fall back to the next key");
    if (rgba.nchannels() != 4 || std::abs(rgba.getchannel(0, 0, 0, 0) - 0.1f) > 0.001f ||
        std::abs(rgba.getchannel(0, 0, 0, 3) - 0.7f) > 0.001f)
        throw std::runtime_error("RGBA selection included AOVs or reordered channels");
    if (reader.read_imagebuf(multilayer_path).nchannels() != 4)
        throw std::runtime_error("Default image selection included AOV channels");
    rk::FramePreparationOptions rgba_options;
    rgba_options.frame_path = multilayer_path;
    rgba_options.layer = "RGBA";
    rgba_options.preset = rk::ColorSpacePreset::NoConversion;
    if (rk::prepare_frame_buffer(rgba_options).buffer.nchannels() != 4)
        throw std::runtime_error("Could not prepare RGBA from a multilayer EXR");
    rgba_options.layer = "motion";
    auto motion = rk::prepare_frame_buffer(rgba_options).buffer;
    if (motion.nchannels() != 3 || std::abs(motion.getchannel(0, 0, 0, 1) - 0.4f) > 0.001f)
        throw std::runtime_error("Could not prepare a two-channel data layer");
    first->invalidate(OIIO::ustring(rk::path_to_utf8(multilayer_path)));
    std::filesystem::remove(multilayer_path);
    auto multipart_path = path.parent_path() / (path.stem().string() + "-multipart.exr");
    OIIO::ImageSpec parts[] = {OIIO::ImageSpec(2, 1, 3, OIIO::TypeDesc::FLOAT),
                               OIIO::ImageSpec(2, 1, 1, OIIO::TypeDesc::FLOAT)};
    parts[0].channelnames = {"R", "G", "B"};
    parts[0].attribute("name", "beauty");
    parts[1].channelnames = {"Z"};
    parts[1].attribute("name", "depth");
    const float beauty_pixels[] = {0.2f, 0.4f, 0.6f, 0.3f, 0.5f, 0.7f};
    const float depth_pixels[] = {0.8f, 0.9f};
    auto multipart_output = OIIO::ImageOutput::create(multipart_path.string());
    if (!multipart_output || !multipart_output->open(multipart_path.string(), 2, parts) ||
        !multipart_output->write_image(OIIO::TypeDesc::FLOAT, beauty_pixels) ||
        !multipart_output->open(multipart_path.string(), parts[1],
                                OIIO::ImageOutput::AppendSubimage) ||
        !multipart_output->write_image(OIIO::TypeDesc::FLOAT, depth_pixels) ||
        !multipart_output->close())
        throw std::runtime_error("Could not create multipart EXR: " + OIIO::geterror());
    auto multipart_info = reader.get_file_info(multipart_path);
    auto multipart_beauty = reader.read_imagebuf(multipart_path);
    auto multipart_depth = reader.read_imagebuf(multipart_path, "depth");
    if (multipart_info.subimages != 2 ||
        multipart_info.layers != std::vector<std::string>({"RGBA", "depth"}) ||
        multipart_beauty.nchannels() != 3 || multipart_depth.nchannels() != 1 ||
        std::abs(multipart_beauty.getchannel(0, 0, 0, 2) - 0.6f) > 0.001f ||
        std::abs(multipart_depth.getchannel(0, 0, 0, 0) - 0.8f) > 0.001f)
        throw std::runtime_error("Incorrect multipart EXR layers or pixels");
    rk::ContactSheetConfig sheet_config;
    sheet_config.columns = 2;
    sheet_config.padding = 0;
    sheet_config.show_labels = false;
    auto multipart_sheet = rk::ContactSheetGenerator(sheet_config).composite_layers(multipart_path);
    if (multipart_sheet.spec().width != 4 || multipart_sheet.spec().height != 1 ||
        std::abs(multipart_sheet.getchannel(0, 0, 0, 2) - 0.6f) > 0.001f ||
        std::abs(multipart_sheet.getchannel(2, 0, 0, 1) - 0.8f) > 0.001f)
        throw std::runtime_error("Incorrect multipart EXR contact sheet");
    first->invalidate(OIIO::ustring(rk::path_to_utf8(multipart_path)));
    std::filesystem::remove(multipart_path);
    auto sheet = rk::ContactSheetGenerator(sheet_config).composite_layers(path);
    if (sheet.spec().width != 4 || sheet.spec().height != 1 ||
        std::abs(sheet.getchannel(2, 0, 0, 1) - 0.4f) > 0.001f)
        throw std::runtime_error("Incorrect contact sheet layout or pixels");
    rk::FramePreparationOptions options;
    options.frame_path = path;
    options.layer = "depth";
    options.output_width = 4;
    options.output_height = 2;
    auto prepared = rk::prepare_frame_buffer(options);
    if (prepared.buffer.nchannels() != 3 || prepared.buffer.spec().width != 4 ||
        prepared.applied_scale != 2.0)
        throw std::runtime_error("Incorrect frame preparation for a data layer");
    auto resized = rk::ImageScaler::scale_buf(depth, 4, 2);
    if (resized.spec().width != 4 || resized.spec().height != 2 || resized.spec().nchannels != 1)
        throw std::runtime_error("Incorrect scaled image dimensions");
    rk::BurnInMetadata metadata{1001, "frame.exr", 23.976, "depth", "linear"};
    if (rk::format_burnin("{frame} {fps:.2f} {layer}", metadata) != "1001 23.98 depth")
        throw std::runtime_error("Incorrect burn-in text formatting");
    try {
        (void)rk::format_burnin("{unknown}", metadata);
        throw std::runtime_error("Unknown token accepted");
    } catch (const std::invalid_argument &) {
    }
    OIIO::ImageBuf overlay(OIIO::ImageSpec(128, 64, 3, OIIO::TypeDesc::FLOAT));
    if (!OIIO::ImageBufAlgo::fill(overlay, 1.0f))
        throw std::runtime_error("Could not create burn-in test image");
    rk::BurnInConfig burnin;
    rk::BurnInElement element;
    element.text_template = "{frame}";
    element.x = 10;
    element.y = 12;
    element.font_size = 12;
    burnin.elements.push_back(element);
    rk::apply_burnins(overlay, metadata, burnin);
    if (std::abs(overlay.getchannel(127, 0, 0, 0) - 0.7f) > 0.001f ||
        overlay.getchannel(127, 50, 0, 0) != 1.0f)
        throw std::runtime_error("Incorrect burn-in background opacity");
    OIIO::ImageBuf text_image(OIIO::ImageSpec(128, 64, 3, OIIO::TypeDesc::FLOAT));
    if (!OIIO::ImageBufAlgo::fill(text_image, 0.0f))
        throw std::runtime_error("Could not create text test image");
    burnin.use_background = false;
    element.y = 40;
    burnin.elements = {element};
    rk::apply_burnins(text_image, metadata, burnin);
    bool drew_text = false;
    for (int y = 0; y < 64 && !drew_text; ++y)
        for (int x = 0; x < 128 && !drew_text; ++x)
            drew_text = text_image.getchannel(x, y, 0, 0) > 0.01f;
    if (!drew_text)
        throw std::runtime_error("Burn-in text did not render any pixels");
    burnin.use_background = true;
    OIIO::ImageBuf tiny(OIIO::ImageSpec(24, 12, 3, OIIO::TypeDesc::FLOAT));
    if (!OIIO::ImageBufAlgo::fill(tiny, 1.0f))
        throw std::runtime_error("Could not create small preview");
    element.x = 20;
    element.y = 0;
    element.font_size = 20;
    burnin.elements = {element};
    rk::apply_burnins(tiny, metadata, burnin);
    auto color = reader.read_imagebuf(path);
    rk::ColorSpaceConverter color_converter(rk::ColorSpacePreset::OcioConversion,
                                            RENDERKIT_TEST_OCIO_PATH);
    auto converted = color_converter.convert_buf(color, "rendering");
    if (converted.spec().nchannels != 3 || !std::isfinite(converted.getchannel(0, 0, 0, 0)))
        throw std::runtime_error("OCIO conversion did not produce color pixels");
    auto mixed_case_role = color_converter.convert_buf(color, "ReNdErInG");
    if (std::abs(mixed_case_role.getchannel(0, 0, 0, 0) - converted.getchannel(0, 0, 0, 0)) >
        0.00001f)
        throw std::runtime_error("OCIO role lookup is unexpectedly case-sensitive");
    rk::ColorSpaceConverter srgb_converter(rk::ColorSpacePreset::LinearToSrgb,
                                           RENDERKIT_TEST_OCIO_PATH);
    auto srgb = srgb_converter.convert_buf(color);
    if (const auto value = srgb.getchannel(0, 0, 0, 0);
        value < 0.0f || value > 1.0f || !std::isfinite(value))
        throw std::runtime_error("Linear-to-sRGB output was not clamped");
    first->invalidate(OIIO::ustring(path.string()));
    std::filesystem::remove(path);
} catch (const std::exception &error) {
    std::fprintf(stderr, "%s\n", error.what());
    return 1;
}
