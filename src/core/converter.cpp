#include "converter.hpp"
#include "exceptions.hpp"
#include "io/image_reader.hpp"
#include "path_utils.hpp"
#include "processing/contact_sheet.hpp"
#include "processing/frame_pipeline.hpp"
#include "processing/video_encoder.hpp"
#include "sequence.hpp"
#include <QString>
#include <algorithm>
#include <deque>
#include <future>
#include <limits>
#include <set>

namespace rk {
void SequenceConverter::convert(const ProgressCallback &progress) const {
    config_.validate();
    auto sequence = SequenceDetector::detect_sequence(config_.input_pattern);
    std::vector<int> frames;
    for (auto frame : sequence.frame_numbers)
        if ((!config_.start_frame || frame >= *config_.start_frame) &&
            (!config_.end_frame || frame <= *config_.end_frame))
            frames.push_back(frame);
    if (frames.empty())
        throw std::invalid_argument("No frames found in specified range");
    const auto sample = sequence.get_file_path(frames.front());
    OIIOReader reader;
    auto info = reader.get_file_info(sample);
    auto fps = config_.fps ? config_.fps : SequenceDetector::auto_detect_fps(frames, {}, sample);
    if (!fps || *fps <= 0)
        throw std::invalid_argument("Could not determine FPS");
    auto input_space = config_.explicit_input_color_space;
    auto preset = config_.color_space_preset;
    if (!input_space && info.color_space &&
        (preset == ColorSpacePreset::LinearToSrgb || preset == ColorSpacePreset::OcioConversion)) {
        input_space = info.color_space;
        preset = ColorSpacePreset::OcioConversion;
    }
    const int first = config_.start_frame.value_or(frames.front());
    const int last = config_.end_frame.value_or(frames.back());
    const auto count = static_cast<long long>(last) - first + 1;
    if (count <= 0 || count > std::numeric_limits<int>::max())
        throw ConfigurationError("Invalid frame range");
    const std::set<int> existing(frames.begin(), frames.end());
    int output_width = config_.width.value_or(info.width);
    int output_height = config_.height.value_or(info.height);
    auto sheet_config = config_.contact_sheet_mode ? config_.contact_sheet_config : std::nullopt;
    if (sheet_config) {
        if (!sheet_config->layer_width && !sheet_config->layer_height) {
            sheet_config->layer_width = config_.width;
            sheet_config->layer_height = config_.height;
        }
        const auto size =
            ContactSheetGenerator(*sheet_config)
                .canvas_size(static_cast<int>(info.layers.size()), info.width, info.height);
        output_width = size.first;
        output_height = size.second;
    }
    auto prepare = [this, &sequence, preset, &input_space, fps, output_width, output_height,
                    sheet_config](int frame_number) {
        auto frame_path = sequence.get_file_path(frame_number);
        FramePreparationOptions options;
        options.frame_path = frame_path;
        options.ocio_config = ocio_config_;
        options.preset = preset;
        options.input_space = input_space;
        options.layer = config_.layer;
        options.contact_sheet = sheet_config;
        options.burnin = config_.burnin_config;
        options.output_width = output_width;
        options.output_height = output_height;
        options.metadata = {frame_number, path_to_utf8(frame_path.filename()), *fps,
                            sheet_config ? "Contact Sheet" : config_.layer.value_or("RGBA"),
                            input_space.value_or("")};
        return prepare_frame_buffer(options).buffer;
    };
    VideoEncoder encoder(QString::fromStdString(config_.output_path), output_width, output_height,
                         *fps, QString::fromStdString(config_.codec), config_.quality,
                         config_.bitrate);
    std::deque<std::future<OIIO::ImageBuf>> queue;
    std::size_t next = 0;
    const int workers = std::max(1, config_.prefetch_workers);
    auto fill_queue = [&] {
        while (next < frames.size() && static_cast<int>(queue.size()) < workers) {
            const auto policy = workers == 1 ? std::launch::deferred : std::launch::async;
            queue.push_back(std::async(policy, prepare, frames[next++]));
        }
    };
    fill_queue();
    std::optional<OIIO::ImageBuf> previous;
    for (long long frame = first; frame <= last; ++frame) {
        const int index = static_cast<int>(frame - first);
        if (progress && !progress(index, static_cast<int>(count)))
            throw ConversionCancelledError("Conversion cancelled by user");
        if (existing.contains(static_cast<int>(frame))) {
            previous = queue.front().get();
            queue.pop_front();
            fill_queue();
        }
        if (previous)
            encoder.write_frame(*previous);
    }
    encoder.finish();
    if (progress)
        progress(static_cast<int>(count), static_cast<int>(count));
}
} // namespace rk
