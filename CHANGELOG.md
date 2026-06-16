# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-06-16

### Added
- **Batch EXR → MP4 CLI** — new `renderkit batch convert` sub-command converts an entire directory tree of EXR sequences in one shot, with dry-run support that validates replacement MP4s before committing any writes.
- **Sequence replacement & cleanup** — `renderkit replace-sequence-with-mp4` and `renderkit batch-replace` for safe, audited replacement of EXR frame sequences with verified MP4s. JSONL audit records capture dry-run, verification, copy, deletion, and reclaimed-byte details.
- **Contact-sheet CLI** promoted to a proper `renderkit contact-sheet` sub-command via a new dedicated `cli/conversion.py` module.
- **`--no-progress` / `--progress` flags** for suppressing the live progress bar in headless / CI pipelines without losing log output.
- **Nuitka standalone packaging** — new `nuitka-standalone-zip.yml` CI workflow produces self-contained zips for Windows, macOS, and Linux, backed by `scripts/build_nuitka.ps1` and `scripts/stage_portable_ffmpeg.py` for portable FFmpeg bundling.
- `src/renderkit/processing/frame_pipeline.py` — shared frame-preparation pipeline used by both the single-frame preview and the video encoder.
- `src/renderkit/core/sequence_replacement.py` — new module handling sequence audit, replacement, and cleanup workflows.
- `src/renderkit/core/batch.py` and `src/renderkit/cli/batch.py` backing the batch-convert feature end-to-end.
- `src/renderkit/core/sequence_names.py` extracted from the sequence module to isolate name-normalisation helpers.
- `src/renderkit/ui/qt_compat.py` to centralise Qt version shims.
- `src/renderkit/processing/pixels.py` and `src/renderkit/io/oiio_utils.py` for shared pixel and OIIO helpers.
- mypy baseline established; incremental type-annotation enforcement begins.
- New tests covering batch conversion, CLI, sequence replacement, video encoder, UI helper modules, and logging (+~2 200 lines).

### Changed
- **Main window decomposed** — `main_window_logic.py` split into four focused helper modules: `main_window_preview.py`, `main_window_sequence.py`, `main_window_settings.py`, and `main_window_ui.py`.
- **Preview pipeline thread safety** — QPixmap creation moved to the UI thread; worker threads now pass raw `bytes`/`numpy` arrays instead of Qt objects. `QImage` buffer lifetimes explicitly managed so the underlying array outlives the `QImage`.
- **Shared frame-prep pipeline** — preview and video-encoder paths now share `frame_pipeline.py`, eliminating the previous code duplication.
- **Conversion orchestration** — conversion kickoff logic extracted from `main_window_logic.py` into a clean orchestration layer, reducing UI/core coupling.
- **OCIO config simplified** — removed the `OCIO` environment-variable override; the bundled config is now always used for deterministic behaviour across environments.
- **Duplicate render helpers consolidated** — colour-conversion and scaling helpers that were duplicated across `converter.py`, `video_encoder.py`, and `image_reader.py` moved into `oiio_utils.py` and `pixels.py`.
- **Magic literals extracted** — numeric and string magic literals replaced with named constants throughout the codebase.
- Batch conversion output planning now deduplicates colliding MP4 paths within a run.
- Batch CLI implementation split into dedicated command and shared conversion modules.
- Regex-based batch sequence grouping replaced with deterministic glob-based grouping.
- Pre-compiled regex patterns introduced in sequence helpers to avoid hotspot recompilation.
- Debug-level log entries now correctly route to the file handler when file logging is enabled.
- FFmpeg finalisation failures (e.g. missing `moov` atom) now propagate as hard errors instead of silent no-ops.
- FFmpeg encoder probe handling tightened; unexpected codec outputs no longer cause silent fallbacks.
- FFmpeg verification in CI now has timeouts to prevent hangs.
- `Always use bundled OCIO config` closes the gap between developer and production runtimes.
- SonarCloud findings addressed: camelCase dummy fields, test helper warnings, batch-conversion findings.
- PyInstaller archive layout preserved in Nuitka artifacts; macOS executable-data collision fixed.
- PowerShell null comparisons in CI corrected to `$null -eq $x` ordering for strict mode.

### Fixed
- Data AOVs (normals, depth, motion vectors) with values outside `[0, 1]` now display correctly in the preview instead of clamping to black/white.
- `%04d` / `%d` printf-style frame patterns in sequence paths now resolved correctly before FFmpeg invocation.
- Sequence replacement validates replacement MP4 existence during dry runs and preflights audit-report writability before copy/delete work.
- Sequence replacement audit preflight now validates sequence completeness before proceeding.
- Nested review-name lookup in batch-replace now resolves deeply-nested shot directories correctly.
- CLI one-sided range and resolution options now parsed correctly.
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

