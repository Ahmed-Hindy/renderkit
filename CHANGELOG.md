# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `renderkit replace-sequence-with-mp4` for safe replacement of detected source frame sequences with approved MP4s.
- `renderkit batch-replace` for scanning EXR sequence trees and applying the same verified replacement workflow in bulk.
- JSONL audit records for sequence replacement cleanup, including dry-run, verification, copy, deletion, and reclaimed-byte details.

### Changed
- Batch conversion output planning now deduplicates colliding MP4 paths within a run.
- Batch CLI implementation is split into dedicated command and shared conversion modules.

### Fixed
- Sequence replacement validates replacement MP4 existence during dry runs and preflights audit report writability before copy/delete work.
- FPS metadata probing and OCIO conversion diagnostics now log expected failure details instead of silently dropping them.

## [1.0.0] - 2026-06-06

### Added
- Public `renderkit ui` command for launching the desktop app from the CLI.
- Stricter runtime failure propagation.

### Changed
- switched log and preview widgets places.
- Tightened runtime error handling so failures surface explicitly instead of producing partial success.

### Fixed
- fixed preview burn-ins scaling issue.
- Validated encoder quality range.
- fixed combobox hovering styling.

## [0.10.0] - 2026-02-08

### Added
- Full-window drag-and-drop overlay with theme-aware styling.
- Aspect-ratio link toggle for width/height controls with persisted state.
- One-click preview thumbnail export to JPEG in the output folder.
- Timeline scrubber for sequence preview with exact frame tracking.
- Branded startup splash screen with minimum display timing helpers.
- OCIO bundle integrity tests for line endings and LUT references.

### Changed
- Refactored timeline scrubbing into a dedicated controller for cleaner UI behavior.
- Centralized UI settings persistence with a shared settings schema.
- Consolidated burn-in and output-action UI state handling in main window logic.
- Updated README with an application screenshot.
- Improved FFmpeg piping by routing stdout to `DEVNULL` for cleaner runtime behavior.

### Fixed
- **OCIO Configuration**: Aligned bundled OCIO profile to 2.4 for OpenImageIO compatibility.
- Hardened OCIO/OIIO diagnostics for packaged color-conversion failures.
- Enforced LF line endings for bundled OCIO config and LUT assets.
- Hidden FFmpeg console window on Windows during conversion.
- Ensured explicit bitrate takes precedence over quality tuning in video encoding.
- Fixed FFmpeg-dependent contact-sheet test behavior when FFmpeg is unavailable.

## [0.9.0] - 2026-01-20

### Fixed
- **OCIO Configuration**: Fixed a crash on systems with incompatible `OCIO` environment variables by prioritizing the packaged configuration within the application.


### Added
- Concurrency support for processing workflows.
- Burn-ins applied to preview output.

### Changed
- Contact sheet UI and defaults refined.
- Contact sheet output actions updated.

## [0.7.0] - 2026-01-16

### Added
- Shared OIIO ImageCache singleton to reuse EXR file handles and decoded tiles across reads.
- Prefetch workers to overlap network IO during conversion with configurable worker counts (CLI/UI/config).
- Contact sheet subimage caching per frame to avoid re-opening EXRs per layer.
- Tests covering prefetch workers, contact sheet caching, and shared OIIO cache behavior.

### Changed
- Switched FFmpeg resolution to an internal resolver and updated override documentation.
- Refactored OIIO reader layer parsing and metadata helpers for clarity and reuse.
- Contact sheet layout and label calculations extracted for readability.
- Contact sheet thumbnail width now respects "Keep Resolution" paths when enabled.

### Removed
- Removed `imageio` and `imageio-ffmpeg` runtime dependencies and PyInstaller metadata payload.

## [0.5.0] - 2026-01-12

### Added
- **Asynchronous Metadata Loading**: Heavy EXR sequences on network paths no longer hang the UI during detection.
- **Log Buffering**: Early startup logs are now buffered and flushed to the UI console once initialized.
- **Pruned OCIO Config**: Bundled a minimal ACES 1.2 OCIO configuration, reducing distribution size while maintaining color accuracy.
- **PR Template**: Standardized contribution workflow with a comprehensive GitHub Pull Request template.

### Changed
- **Modern UI Refresh**: Switched to OKLCH-based color system for more perceptually uniform styling.
- **Enhanced Task Control**: Added master toggles for burn-in and contact sheet sections with improved visual hierarchy.
- **Video Encoding Improvements**: Added BT.709 color tags for SDR deliverables and made video macro-block size configurable.
- **Thread Management**: Centralized worker pooling for more robust background operations and crash prevention.
- **Consolidated Versioning**: Unified version definition across the API, CLI, and UI title bar.
- Moved Contact Sheet toggle to Input Sequence section for better visibility.
- Enforced mutual exclusivity between Contact Sheet mode and single Layer selection with visual cues.
- Auto-expand Contact Sheet settings when mode is enabled.
- Preview window now displays a contact sheet grid when in Contact Sheet mode.
- Added Fullscreen Preview window with interactive zooming (mouse wheel) and panning (middle mouse).
- Implemented "Zoom to Mouse" behavior and 1000% maximum zoom cap for high-detail inspection.
- Added configurable Preview Scale percentage (Advanced settings) for optimized performance (default 25%).
- Offloaded contact sheet preview generation to a background thread to prevent UI hangs.
- Implemented robust thread management with worker pooling to prevent crashes during rapid UI interactions.
- Added real-time configuration updates for the contact sheet preview with debouncing.

## [0.4.0] - 2026-01-09

### Added
- Recent patterns dropdown with history and a reset-to-defaults action in settings panels.
- Inline output path validation and UI log forwarding.
- Conversion completion quick actions and status icons (including a success check) in the UI.
- Centralized logging module to unify app logging output.
- Color space role names with Utility Linear sRGB as the default role.
- Encoder preflight popup and an MSYS2 wrapper for Windows FFmpeg builds.
- Caching for FFmpeg build artifacts and minimal Windows FFmpeg build support in CI.

### Changed
- Preview now scales to the panel size while preserving aspect ratio, with a tighter default footprint.
- Preview panel height is capped for a more balanced UI layout.
- Preview auto-load behavior and flow refined in the UI.
- Convert swaps to Cancel during runs, with refined cancel UX and preview flow.
- Sequence detection runs after typing completes; removed the manual Detect button.
- Color conversion now requires OCIO configuration and uses OIIO/OCIO exclusively.
- Default codec/build defaults updated (H.264 default, x264 build, trimmed output extensions).
- UI labels and styling refined (Matcha QSS, validation presentation, icons, defaults).
- Contact Sheet UI simplified by removing the duplicate toggle (single "Enable Contact Sheet" control).
- CI now caches platform FFmpeg bundles for faster Linux/macOS builds.

### Fixed
- Large empty padding around previews when the panel grew beyond the pixmap size.
- Pattern validation edge cases in the main window.
- Accidental value changes from mouse-wheel scrolling without focus.
- Windows FFmpeg build issues (stdin/report handling, libaom AV1 encoder, dependency updates).

## [0.3.0] - 2026-01-01

### Added
- **OpenImageIO (OIIO) Migration**: Migrated Image reading library from ImageIO to OIIO library.
- **Multi-Layer EXR Selection**: Choose specific AOVs/Layers from EXR sequences in UI and CLI.
- **AV1 Codec Support**: Integrated `libaom-av1` for maximum compression efficiency.
- **UI Progress Tracking**: Determinate progress bar in the main window with frame-by-frame status updates and percentage display.
- **Graceful Cancellation**: Ability to cancel long-running conversions from the UI with proper resource cleanup.

### Fixed
- Regression where deleted UI elements were being accessed during conversion startup.
- FFmpeg "Hang" during AV1 encoding by providing proper CPU utilization and quality parameters.
- Membership test lint error in `_browse_output_path`.
- **MP4 Compatibility**: Enforced `yuv420p` pixel format to ensure encoding works across all standard media players (QuickTime, WMP) and web browsers.
- **Web Playback Utility**: Added FFmpeg `+faststart` flag to optimize video files for web streaming and progressive loading.
- **Improved Diagnostics**: Added descriptive error messages when FFmpeg dependencies are missing.

### Changed
- Removed legacy dependencies: `Pillow`, `OpenEXR`, and `Imath`.
- Standardized default codec to `libx264` (Recommended).
- Updated public `RenderKit` API to include `quality` and `codec` controls.
- **Predictable Quality Mapping**: Replaced generic quality parameters with precise mappings to codec-specific controls (CRF for x264/x265/AV1, `-q:v` for MPEG-4).
- **Refactored Converter**: Updated `SequenceConverter` to allow external progress callbacks, enabling UI-agnostic progress reporting.

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

