# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- EXR metadata FPS detection (supports Arnold, Karma, Nuke, Redshift, V-Ray, etc.)
- Case-insensitive metadata key matching and support for rational/string formats
- `QDoubleSpinBox` for high-precision frame rate control in UI
- Integration tests for real EXR sequence files
- Automatic frame resizing for inconsistent frame dimensions
- Comprehensive test suite with 60% code coverage
- CONTRIBUTING.md with contribution guidelines
- CHANGELOG.md for tracking changes

### Fixed
- Empty video output (258B) caused by 4-channel (RGBA) input and backend conflicts
- Inconsistent FPS display in UI (now detects on pattern change)
- Regex replacement issue in sequence detection (fixed escape sequence error)
- Frame dimension mismatch handling in video encoder
- Pytest configuration (removed --benchmark-only from default options)

### Changed
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

