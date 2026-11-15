#include "core/logging.hpp"
#include <chrono>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <spdlog/spdlog.h>
#include <stdexcept>

int main() try {
    auto path =
        std::filesystem::temp_directory_path() /
        ("renderkit-log-test-" +
         std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".log");
#ifdef _WIN32
    _putenv_s("RENDERKIT_LOG_PATH", path.string().c_str());
    _putenv_s("RENDERKIT_LOG_LEVEL", "warning");
#else
    setenv("RENDERKIT_LOG_PATH", path.string().c_str(), 1);
    setenv("RENDERKIT_LOG_LEVEL", "warning", 1);
#endif
    std::string callback;
    if (rk::setup_logging([&callback](const auto &text) { callback = text; }) != path)
        throw std::runtime_error("Incorrect log path");
    auto logger = spdlog::get("renderkit");
    logger->warn("test message");
    logger->flush();
    std::ifstream file(path);
    std::string content((std::istreambuf_iterator<char>(file)), {});
    file.close();
    if (callback.find("WARNING - test message") == std::string::npos ||
        content.find("WARNING - renderkit - test message") == std::string::npos)
        throw std::runtime_error("Incorrect log output");
    spdlog::drop("renderkit");
    logger.reset();
    std::filesystem::remove(path);
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
