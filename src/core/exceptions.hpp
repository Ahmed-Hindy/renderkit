#pragma once

#include <stdexcept>

namespace rk {
class RenderKitError : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};
class SequenceDetectionError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class ImageReadError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class ColorSpaceError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class VideoEncodingError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class SequenceReplacementError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class ConfigurationError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
class ConversionCancelledError : public RenderKitError {
  public:
    using RenderKitError::RenderKitError;
};
} // namespace rk
