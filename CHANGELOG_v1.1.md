# RenderKit v1.1.0 — Release Changelog

> Comparing `v1.0.0` → `main` · 67 files changed · ~6 500 insertions / ~1 300 deletions

---

## 🚀 New Features

### Batch EXR Sequence Conversion (CLI)
- **New `batch convert` CLI sub-command** — convert an entire directory tree of EXR sequences to MP4 in one shot. (#73, #78)
- New `src/renderkit/core/batch.py` and `src/renderkit/cli/batch.py` modules back the feature end-to-end.
- Dry-run support: validates replacement MP4s before committing any writes. (#70)

### Verified Sequence Replacement & Cleanup
- **`src/renderkit/core/sequence_replacement.py`** — new module that handles auditing, replacing, and cleaning up EXR sequences once a verified MP4 replacement exists. (#70, #100)
- Audit preflight checks were tightened so mismatched or incomplete sequences are caught early. (#72)
- Nested review-name lookup fixed for deeply-structured shot directories. (#100)

### Contact Sheet CLI
- `renderkit contact-sheet` is now a proper CLI command with a dedicated `src/renderkit/cli/conversion.py` module. (#91)
- Label help text was clarified and one-sided range / resolution options were fixed. (#89, #90)

### Automation-Friendly Progress Control
- `--no-progress` / `--progress` flags let headless or CI pipelines suppress the live progress bar without losing log output. (#69)

### Nuitka Standalone Packaging
- New **`.github/workflows/nuitka-standalone-zip.yml`** CI workflow builds self-contained Windows, macOS, and Linux zips. (#60, #61)
- New `scripts/build_nuitka.ps1` and `scripts/stage_portable_ffmpeg.py` support cross-platform portable FFmpeg bundling.
- PyInstaller archive layout is preserved in artifacts; macOS executable-data collision fixed. (#61)

---

## 🔧 Improvements & Refactors

### UI — Main Window Decomposition (#106)
- `main_window_logic.py` was split into four focused helper modules:
  - `main_window_preview.py` — preview-related logic
  - `main_window_sequence.py` — sequence loading / frame helpers
  - `main_window_settings.py` — settings persistence
  - `main_window_ui.py` — UI wiring
- `sequence_names.py` extracted from the sequence module to isolate name-normalisation helpers.

### Preview Pipeline — Thread Safety & Memory Safety (#107, #108, #109)
- QPixmap creation moved to the **UI thread**; worker threads now pass raw `bytes` / `numpy` arrays instead of Qt objects.
- `QImage` buffer lifetimes are explicitly managed so the underlying array is guaranteed to outlive the `QImage`.
- `qt_compat.py` added to centralise Qt version shims.

### Shared Preview Frame Preparation Pipeline (#105)
- `src/renderkit/processing/frame_pipeline.py` — new module that unifies the frame-prep path used by both the single-frame preview and the video encoder, eliminating the previous duplication.

### Conversion & UI Orchestration Refactor (#103)
- Conversion kickoff logic was extracted from `main_window_logic.py` into a clean orchestration layer, reducing coupling between UI and core.

### Magic Literal Extraction (#111)
- Numeric and string magic literals throughout the codebase replaced with named constants for readability and maintainability.

### Duplicate Render Helper Removal (#110)
- Duplicated colour-conversion and scaling helpers across `converter.py`, `video_encoder.py`, and `image_reader.py` consolidated into shared utilities in `oiio_utils.py` and `pixels.py`.

### OCIO Configuration (#102)
- Removed the `OCIO` environment-variable override path; the bundled config is now always used, making behaviour deterministic across environments.
- `Always use bundled OCIO config` commit closes the gap between developer and production runtime.

### FFmpeg Robustness (#101, #88)
- Finalisation failures (e.g. `moov` atom not written) now propagate as hard errors instead of silent no-ops.
- FFmpeg encoder probe handling tightened; unexpected codec outputs no longer cause silent fallbacks.
- FFmpeg verification now has timeouts to prevent CI hangs. (#61)

### Printf-Style Frame Pattern Resolution (#68)
- `%04d` / `%d` frame patterns in sequence paths are now resolved correctly before being passed to FFmpeg, fixing broken output filenames on certain sequence layouts.

### Sequence Replacement Complexity (#69)
- Regex-based batch grouping removed in favour of deterministic, glob-based grouping to reduce fragility and improve performance.

### Logging
- Debug-level log entries now correctly route to the file handler when file logging is enabled.
- `logging_utils.py` refactored for clarity.

### Data AOV Preview Fix (#59)
- Data AOVs (normals, depth, motion vectors) with values outside `[0, 1]` now display correctly in the preview instead of clamping to black/white.

---

## 🏗 Internal / Code Quality

| Area | Change |
|---|---|
| `src/renderkit/ui/preview_image.py` | +107 lines: explicit buffer management, thread-safe pixmap creation |
| `src/renderkit/processing/video_encoder.py` | Significant refactor; shared pipeline via `frame_pipeline.py` |
| `src/renderkit/processing/color_space.py` | Deduplication of OCIO transform helpers |
| `src/renderkit/core/converter.py` | ~515 lines refactored for shared pipeline; orchestration extracted |
| `tests/` | +~2 200 lines of new tests covering batch, CLI, sequence replacement, video encoder, UI helpers, and logging |
| mypy | Baseline established (`fe02f78`); incremental type-annotation enforcement begins |
| SonarCloud | Addressed camelCase dummy fields, test helper warnings, and batch-conversion findings |
| `.gitignore` | Added entry for new generated artefacts |

---

## 📚 Documentation

- `docs/usage.md` — expanded with batch convert, sequence replacement, and contact-sheet CLI examples (+213 lines).
- `docs/api/sequence_replacement.md` — new API reference page for the sequence-replacement module.
- `docs/development.md` — automation audit recipes and replacement cleanup safety notes added.
- `mkdocs.yml` — wired up new API docs page.

---

## 🐛 Bug Fixes

| Issue | Fix |
|---|---|
| Data AOV preview clamps (#59) | Values outside `[0,1]` now normalised correctly for display |
| `%04d` frame patterns not resolved (#68) | Printf patterns expanded before FFmpeg invocation |
| Audit preflight false-passes (#72) | Sequence completeness validated before replacement audit |
| CLI one-sided range / resolution options (#90) | Argument parsing corrected to accept half-bounded ranges |
| Nested review-name batch lookup (#100) | Recursive directory walk now resolves deeply nested review paths |
| FFmpeg finalization silent failure (#101) | `FinalizationError` raised and surfaced to the user |
| OCIO env override ignored on some machines (#102) | Bundled config path is now the sole source of truth |
| QImage use-after-free in preview worker (#108) | Array lifetime explicitly extended past `QImage` destruction |
| Duplicate regex hotspots in sequence helpers (#106) | Pre-compiled patterns cache introduced |
| PowerShell null comparisons in CI (#61) | `$null -eq $x` ordering fixed for PowerShell strict mode |

---

*Generated 2026-06-16 from `v1.0.0..HEAD` (30 merged PRs, ~80 commits).*
