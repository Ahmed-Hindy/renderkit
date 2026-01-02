# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-01-02

### Added
- **UI Progress Tracking**: Determinate progress bar in the main window with frame-by-frame status updates and percentage display.
- **Graceful Cancellation**: Ability to cancel long-running conversions from the UI with proper resource cleanup.

### Fixed
- **MP4 Compatibility**: Enforced `yuv420p` pixel format to ensure encoding works across all standard media players (QuickTime, WMP) and web browsers.
- **Web Playback Utility**: Added FFmpeg `+faststart` flag to optimize video files for web streaming and progressive loading.
- **Improved Diagnostics**: Added descriptive error messages when FFmpeg dependencies are missing.

### Changed
- **Predictable Quality Mapping**: Replaced generic quality parameters with precise mappings to codec-specific controls (CRF for x264/x265/AV1, `-q:v` for MPEG-4).
- **Refactored Converter**: Updated `SequenceConverter` to allow external progress callbacks, enabling UI-agnostic progress reporting.

## [0.3.0] - 2026-01-01

### Added
- **OpenImageIO (OIIO) Migration**: Migrated Image reading library from ImageIO to OIIO library.
- **Multi-Layer EXR Selection**: Choose specific AOVs/Layers from EXR sequences in UI and CLI.
- **AV1 Codec Support**: Integrated `libaom-av1` for maximum compression efficiency.

### Fixed
- Regression where deleted UI elements were being accessed during conversion startup.
- FFmpeg "Hang" during AV1 encoding by providing proper CPU utilization and quality parameters.
- Membership test lint error in `_browse_output_path`.

### Changed
- Removed legacy dependencies: `Pillow`, `OpenEXR`, and `Imath`.
- Standardized default codec to `libx264` (Recommended).
- Updated public `RenderKit` API to include `quality` and `codec` controls.

## [0.2.0] - 2026-01-01

### Added
- OpenColorIO (OCIO) integration for professional color space management
- Automatic input color space detection from EXR metadata (e.g., `ACEScg`, `sRGB`)
- Editable "Input Color Space" dropdown in UI with auto-selection capabilities
- Centralized constants module (`renderkit.constants`) for metadata keys and UI strings
- EXR metadata FPS detection (supports Arnold, Karma, Nuke, Redshift, V-Ray, etc.)
- Case-insensitive metadata key matching and support for rational/string formats
- `QDoubleSpinBox` for high-precision frame rate control in UI
- Integration tests for real EXR sequence files
- Automatic frame resizing for inconsistent frame dimensions
- Comprehensive test suite with 60% code coverage
- CONTRIBUTING.md with contribution guidelines
- CHANGELOG.md for tracking changes

### Fixed
- OCIO 2.5.0 API incompatibility (`getNumColorSpaces` replaced with modern equivalent)
- Empty video output (258B) caused by 4-channel (RGBA) input and backend conflicts
- Inconsistent FPS display in UI (now detects on pattern change)
- Regex replacement issue in sequence detection (fixed escape sequence error)
- Frame dimension mismatch handling in video encoder
- Pytest configuration (removed --benchmark-only from default options)

### Changed
- Refactored core modules to use unified constants instead of hardcoded "magic numbers"
- `VideoEncoder` now automatically drops Alpha channel and converts to BGR for compatibility
- Forced `CAP_FFMPEG` backend preference on Windows for better stability
- Improved codec fallback logic in `VideoEncoder` (avc1 -> mp4v -> XVID)
- Updated README.md with better structure and uv instructions
- Enhanced .gitignore with additional entries
- Improved test documentation and examples

## [0.1.0] - 2025-12-30

### Added
- Initial release
- EXR sequence to MP4 video conversion
- Support for multiple frame naming conventions (%04d, $F4, ####, numeric)
- Color space conversion presets (Linear to sRGB, Linear to Rec.709, etc.)
- CLI interface with `renderkit` command
- Python API with builder pattern
- PySide6/Qt GUI (basic implementation)
- Frame sequence detection and parsing
- Image scaling utilities
- Video encoding with OpenCV/FFmpeg

