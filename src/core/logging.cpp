#include "logging.hpp"

#include <spdlog/pattern_formatter.h>
#include <spdlog/sinks/base_sink.h>
#include <spdlog/sinks/rotating_file_sink.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <mutex>
#include <vector>

namespace rk {
namespace {
std::string level_name(spdlog::level::level_enum level) {
    const auto value = spdlog::level::to_string_view(level);
    std::string result(value.data(), value.size());
    std::transform(result.begin(), result.end(), result.begin(),
                   [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
    if (result == "WARN")
        result = "WARNING";
    return result;
}
class UpperLevelFlag : public spdlog::custom_flag_formatter {
  public:
    void format(const spdlog::details::log_msg &message, const std::tm &,
                spdlog::memory_buf_t &destination) override {
        auto value = level_name(message.level);
        destination.append(value.data(), value.data() + value.size());
    }
    std::unique_ptr<spdlog::custom_flag_formatter> clone() const override {
        return std::make_unique<UpperLevelFlag>();
    }
};
std::unique_ptr<spdlog::formatter> formatter(const std::string &pattern) {
    auto result = std::make_unique<spdlog::pattern_formatter>();
    result->add_flag<UpperLevelFlag>('K').set_pattern(pattern);
    return result;
}
class CallbackSink : public spdlog::sinks::base_sink<std::mutex> {
  public:
    explicit CallbackSink(LogCallback callback) : callback_(std::move(callback)) {
        set_pattern("%H:%M:%S - %v");
    }

  protected:
    void sink_it_(const spdlog::details::log_msg &message) override {
        spdlog::memory_buf_t formatted;
        formatter_->format(message, formatted);
        std::string line(formatted.data(), formatted.size());
        while (!line.empty() && (line.back() == '\n' || line.back() == '\r'))
            line.pop_back();
        auto level = level_name(message.level);
        if (line.size() >= 11)
            line.insert(11, level + " - ");
        try {
            callback_(line);
        } catch (...) { /* Logging must not abort conversion. */
        }
    }
    void flush_() override {}

  private:
    LogCallback callback_;
};
} // namespace
std::filesystem::path setup_logging(LogCallback ui_sink, std::optional<bool> enable_console) {
    const char *path_env = std::getenv("RENDERKIT_LOG_PATH");
    auto path = path_env && *path_env ? std::filesystem::path(path_env)
                                      : std::filesystem::temp_directory_path() / "renderkit.log";
    if (path.has_parent_path())
        std::filesystem::create_directories(path.parent_path());
    auto file =
        std::make_shared<spdlog::sinks::rotating_file_sink_mt>(path.string(), 5 * 1024 * 1024, 3);
    file->set_formatter(formatter("%Y-%m-%d %H:%M:%S,%e - %K - %n - %v"));
    std::vector<spdlog::sink_ptr> sinks{file};
    if (enable_console.value_or(!ui_sink)) {
        auto console = std::make_shared<spdlog::sinks::stderr_color_sink_mt>();
        console->set_formatter(formatter("%K: %v"));
        sinks.push_back(console);
    }
    if (ui_sink)
        sinks.push_back(std::make_shared<CallbackSink>(std::move(ui_sink)));
    auto logger = std::make_shared<spdlog::logger>("renderkit", sinks.begin(), sinks.end());
    std::string level =
        std::getenv("RENDERKIT_LOG_LEVEL") ? std::getenv("RENDERKIT_LOG_LEVEL") : "INFO";
    std::transform(level.begin(), level.end(), level.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (level == "warning")
        level = "warn";
    auto parsed = spdlog::level::from_str(level);
    logger->set_level(parsed == spdlog::level::off ? spdlog::level::info : parsed);
    spdlog::drop("renderkit");
    spdlog::register_logger(logger);
    return path;
}
} // namespace rk
