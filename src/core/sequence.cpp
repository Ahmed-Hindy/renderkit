#include "sequence.hpp"
#include "exceptions.hpp"
#include "path_utils.hpp"

#include <algorithm>
#include <iomanip>
#include <regex>
#include <sstream>

namespace rk {
namespace {
std::string escape_regex(const std::string &input) {
    static const std::regex special(R"([.^$|()\[\]{}*+?\\])");
    return std::regex_replace(input, special, R"(\$&)");
}
std::string padded(int value, int width) {
    std::ostringstream out;
    out << std::internal << std::setfill('0') << std::setw(width) << value;
    return out.str();
}
} // namespace

std::filesystem::path FrameSequence::get_file_path(int frame_number) const {
    std::string result = pattern;
    std::smatch match;
    for (const auto &[expression, kind] :
         std::vector<std::pair<std::regex, int>>{{std::regex(R"(%0?(\d+)d)"), 0},
                                                 {std::regex(R"(\$F\d+)"), 1},
                                                 {std::regex(R"(#+)"), 2}}) {
        std::string output;
        auto remaining = result;
        while (std::regex_search(remaining, match, expression)) {
            output += match.prefix().str();
            int width = kind == 0 ? std::stoi(match[1].str()) : padding;
            if (kind == 2)
                width = std::max(width, static_cast<int>(match.length()));
            output += padded(frame_number, width);
            remaining = match.suffix().str();
        }
        result = output + remaining;
    }
    return base_path / path_from_utf8(result);
}

FrameSequence SequenceDetector::detect_sequence(const std::string &pattern) {
    const auto path = path_from_utf8(pattern);
    auto base = path.parent_path();
    if (base.empty())
        base = ".";
    std::string name = path_to_utf8(path.filename()), detected = name;
    std::smatch match;
    std::size_t start = std::string::npos, length = 0;
    int padding = 0;
    if (std::regex_search(name, match, std::regex(R"(%(\d+)d)"))) {
        start = match.position();
        length = match.length();
        padding = std::stoi(match[1].str());
    } else if (std::regex_search(name, match, std::regex(R"(\$F(\d+))"))) {
        start = match.position();
        length = match.length();
        padding = std::stoi(match[1].str());
    } else if (std::regex_search(name, match, std::regex(R"(#+)"))) {
        start = match.position();
        length = match.length();
        padding = static_cast<int>(length);
    } else {
        // Inspect every dot-delimited field so adjacent numeric fields are not skipped.
        for (std::size_t dot = name.find('.'); dot != std::string::npos;
             dot = name.find('.', dot + 1)) {
            const auto end = name.find('.', dot + 1);
            if (end == std::string::npos)
                break;
            auto field = name.substr(dot + 1, end - dot - 1);
            if (field.size() >= 3 && field.size() <= 5 &&
                std::all_of(field.begin(), field.end(),
                            [](unsigned char c) { return c >= '0' && c <= '9'; })) {
                start = dot + 1;
                length = field.size();
                padding = static_cast<int>(length);
            }
        }
        if (start != std::string::npos)
            detected.replace(start, length, "%0" + std::to_string(padding) + "d");
    }
    if (start == std::string::npos || padding <= 0 || padding > 9)
        throw SequenceDetectionError("Could not detect frame sequence.");
    const std::regex re("^" + escape_regex(name.substr(0, start)) + "([0-9]{" +
                        std::to_string(padding) + "})" + escape_regex(name.substr(start + length)) +
                        "$");
    std::vector<int> frames;
    std::error_code ec;
    for (std::filesystem::directory_iterator it(base, ec), end; !ec && it != end;
         it.increment(ec)) {
        if (!it->is_regular_file(ec))
            continue;
        const auto candidate = path_to_utf8(it->path().filename());
        if (std::regex_match(candidate, match, re))
            frames.push_back(std::stoi(match[1].str()));
    }
    if (frames.empty())
        throw SequenceDetectionError("Could not detect frame sequence.");
    std::sort(frames.begin(), frames.end());
    return {base, detected, frames, padding};
}
} // namespace rk
