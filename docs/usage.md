# Usage Guide

This page is the CLI-focused reference for power users, pipeline TDs, and automation.
For the end-user desktop workflow, start with the README and launch the UI with `renderkit ui`.

## Install For CLI Use

From a source checkout:

```powershell
uv sync
uv run renderkit --help
```

If RenderKit is already installed or you are using a release build that adds the executable to `PATH`, use `renderkit` directly.

## Command Overview

```bash
renderkit --help
renderkit ui
renderkit convert-exr-sequence INPUT_PATTERN OUTPUT_PATH [OPTIONS]
renderkit batch-convert ROOT [OPTIONS]
renderkit replace-sequence-with-mp4 INPUT_PATTERN OUTPUT_MP4 [OPTIONS]
renderkit batch-replace ROOT_PATH [OPTIONS]
renderkit contact-sheet INPUT_PATTERN OUTPUT_PATH [OPTIONS]
```

`INPUT_PATTERN` accepts common sequence styles:

```text
render.%04d.exr
render.####.exr
render.$F4.exr
```

## Conversion Recipes

### Basic Review Movie

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24
```

### Frame Range

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --start-frame 1001 --end-frame 1100
```

### Resolution Override

Set both width and height when overriding resolution:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --width 1920 --height 1080
```

### Color Space Preset

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --color-space linear_to_rec709
```

Available presets:

- `linear_to_srgb`
- `linear_to_rec709`
- `srgb_to_linear`
- `no_conversion`

### Codec And Quality

H.264 is the default. Use H.265 or AV1 when the review target supports it.

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec libx265 --quality 8
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec libaom-av1 --quality 8
```

`--quality` uses a 0-10 scale where 10 is highest quality.

### Specific EXR Layer

```bash
renderkit convert-exr-sequence render.%04d.exr diffuse.mp4 --layer diffuse
```

### Burn-ins

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-layer --burnin-fps
```

Tune the burn-in background:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-opacity 45
```

### Multi-AOV Contact Sheet Movie

Use contact-sheet mode on conversion when you want an MP4 grid of EXR layers/AOVs:

```bash
renderkit convert-exr-sequence render.%04d.exr contact_sheet.mp4 --contact-sheet --cs-columns 4
```

Useful grid controls:

```bash
renderkit convert-exr-sequence render.%04d.exr contact_sheet.mp4 --contact-sheet --cs-columns 3 --cs-thumb-width 512 --cs-padding 8
renderkit convert-exr-sequence render.%04d.exr contact_sheet.mp4 --contact-sheet --cs-no-labels
```

### Still Contact Sheet

Use the `contact-sheet` command when you want one image instead of a video:

```bash
renderkit contact-sheet render.%04d.exr contact_sheet.jpg --columns 4 --thumb-width 512
```

Frame-range and layer filters work here too:

```bash
renderkit contact-sheet render.%04d.exr contact_sheet.jpg --layer diffuse --start-frame 1001 --end-frame 1012
```

### Profiling

For one-off profiling:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --profile
```

Choose an output file or directory:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --profile --profile-out ./profiles
```

Profiling writes `.prof` data and a readable `.prof.txt` summary.

## Automation Patterns

### PowerShell Batch

```powershell
$shots = Get-ChildItem .\shots -Directory
foreach ($shot in $shots) {
    $pattern = Join-Path $shot.FullName "render.%04d.exr"
    $output = Join-Path $shot.FullName "review.mp4"
    uv --native-tls run renderkit convert-exr-sequence $pattern $output --fps 24 --overwrite --no-progress
}
```

Use `--no-progress` when capturing stdout or stderr from automation. RenderKit also disables
progress bars automatically when stderr is not an interactive terminal.

### Bash Batch

```bash
for shot in shots/*; do
  renderkit convert-exr-sequence "$shot/render.%04d.exr" "$shot/review.mp4" --fps 24 --overwrite
done
```

### Recursive Batch Convert

Use `batch-convert` when RenderKit should discover sequences recursively and write review MP4s
plus audit manifests:

```powershell
renderkit batch-convert G:\Projects\Data_folder --ext exr --out _review_mp4s --fps 24 --overwrite
```

By default, relative output and manifest paths are resolved under `ROOT`. Existing MP4s are
skipped unless `--overwrite` is set. The command keeps processing after per-sequence failures and
exits nonzero if any sequence failed.

Extension matching is case-insensitive, so `--ext exr` also finds `.EXR` frames. Output names are
built from the relative folder path and sequence prefix. If multiple discovered sequences would
write the same MP4 path in one run, RenderKit appends a numeric suffix such as `_2`.

Default manifests:

- `_review_mp4s/renderkit_batch_manifest.csv`
- `_review_mp4s/renderkit_batch_results.jsonl`

### Safe Sequence Replacement

Use `replace-sequence-with-mp4` after review movies have been approved and source frames can be
replaced by the MP4. Start with a dry run:

```powershell
renderkit replace-sequence-with-mp4 render.%04d.exr G:\reviews\render.mp4 --verify --delete-source --dry-run
```

When the dry run looks correct, remove `--dry-run`:

```powershell
renderkit replace-sequence-with-mp4 render.%04d.exr G:\reviews\render.mp4 --verify --delete-source
```

The command detects the exact frames in `INPUT_PATTERN`, copies the replacement MP4 into the source
sequence folder, optionally verifies the MP4 with `ffprobe`, and writes a JSONL audit record. When
`--delete-source` is used without `--dry-run`, RenderKit verifies the copied MP4 before deleting
source frames. Dry runs still require the replacement MP4 to exist, so the preflight cannot report a
missing movie as replaceable.

By default, the audit file is written next to the source sequence:

```text
renderkit-replacement-audit.jsonl
```

### Batch Replacement Cleanup

Use `batch-replace` when a folder tree contains EXR sequences and a review folder contains matching
MP4s named after each sequence prefix:

```powershell
renderkit batch-replace G:\Projects\Data_folder --mp4-dir _review_mp4s --verify --delete-source --dry-run
```

`--mp4-dir` is relative to `ROOT_PATH` unless it is absolute. For each detected EXR sequence,
RenderKit derives the expected MP4 name from the sequence prefix, such as `render.%04d.exr` to
`render.mp4`, runs the same verification and audit workflow as `replace-sequence-with-mp4`, and
appends results to:

```text
renderkit-batch-replace-audit.jsonl
```

## `convert-exr-sequence` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_PATTERN` | File pattern with a frame placeholder. | Required |
| `OUTPUT_PATH` | Output video file path. | Required |
| `--prefetch-workers` | Number of frame prefetch workers; use `1` to disable concurrent prefetch. | `2` |
| `--fps` | Frame rate. If omitted, RenderKit attempts auto-detection. | Auto-detect |
| `--quality` | Visual quality on a 0-10 scale. | `10` |
| `--color-space` | `linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, or `no_conversion`. | `linear_to_srgb` |
| `--width` | Output width. Must be paired with `--height`. | Source width |
| `--height` | Output height. Must be paired with `--width`. | Source height |
| `--codec` | FFmpeg codec, commonly `libx264`, `libx265`, or `libaom-av1`. | `libx264` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--start-frame` | Start frame number. | First frame |
| `--end-frame` | End frame number. | Last frame |
| `--overwrite` | Overwrite output file if it exists. | `False` |
| `--burnin-frame` | Burn in frame number. | `False` |
| `--burnin-layer` | Burn in layer name. | `False` |
| `--burnin-fps` | Burn in frame rate. | `False` |
| `--burnin-opacity` | Burn-in background opacity from 0-100. | `30` |
| `--contact-sheet` | Enable multi-AOV grid movie mode. | `False` |
| `--cs-columns` | Contact sheet columns. | `4` |
| `--cs-thumb-width` | Width of each contact sheet layer cell. | Source resolution |
| `--cs-padding` | Spacing between contact sheet cells. | `4` |
| `--cs-no-labels` | Disable layer name labels. | `False` |
| `--profile` | Enable cProfile output for this conversion. | `False` |
| `--profile-out` | Output `.prof` path or directory. | Temp dir |
| `--no-progress` | Disable progress bars for stable captured logs. | `False` |

## `batch-convert` Options

| Option | Description | Default |
|---|---|---|
| `ROOT` | Directory tree to scan recursively. | Required |
| `--ext` | Frame extension to discover, with or without a leading dot. | `exr` |
| `--out` | Output directory for generated MP4 files. Relative paths resolve under `ROOT`. | `_review_mp4s` |
| `--prefetch-workers` | Number of frame prefetch workers; use `1` to disable concurrent prefetch. | `2` |
| `--fps` | Frame rate. If omitted, RenderKit attempts auto-detection per sequence. | Auto-detect |
| `--quality` | Visual quality on a 0-10 scale. | `10` |
| `--color-space` | `linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, or `no_conversion`. | `linear_to_srgb` |
| `--width` | Output width. Must be paired with `--height`. | Source width |
| `--height` | Output height. Must be paired with `--width`. | Source height |
| `--codec` | FFmpeg codec, commonly `libx264`, `libx265`, or `libaom-av1`. | `libx264` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--overwrite` | Overwrite output files if they exist. | `False` |
| `--manifest-csv` | CSV manifest path. Relative paths resolve under `ROOT`. | `OUTPUT_DIR/renderkit_batch_manifest.csv` |
| `--manifest-jsonl` | JSONL results path. Relative paths resolve under `ROOT`. | `OUTPUT_DIR/renderkit_batch_results.jsonl` |
| `--no-progress` | Disable progress bars for stable captured logs. | `False` |

## `replace-sequence-with-mp4` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_PATTERN` | Source sequence pattern with a frame placeholder. | Required |
| `OUTPUT_MP4` | Replacement MP4 to copy into the source sequence folder. | Required |
| `--delete-source` | Delete source frames after the replacement MP4 is verified. | `False` |
| `--verify` | Verify the replacement MP4 with `ffprobe` before replacing frames. | `False` |
| `--dry-run` | Print and audit planned changes without copying or deleting files. | `False` |
| `--audit-report` | JSONL audit report path. | Source folder `renderkit-replacement-audit.jsonl` |

## `batch-replace` Options

| Option | Description | Default |
|---|---|---|
| `ROOT_PATH` | Directory tree to scan for EXR sequences. | Required |
| `--mp4-dir` | Directory containing replacement MP4s. Relative paths resolve under `ROOT_PATH`. | `_review_mp4s` |
| `--delete-source` | Delete source frames after each replacement MP4 is verified. | `False` |
| `--verify` | Verify each replacement MP4 with `ffprobe` before replacing frames. | `False` |
| `--dry-run` | Print and audit planned changes without copying or deleting files. | `False` |
| `--audit-report` | JSONL audit report path. | `ROOT_PATH/renderkit-batch-replace-audit.jsonl` |

## `contact-sheet` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_PATTERN` | File pattern with a frame placeholder. | Required |
| `OUTPUT_PATH` | Output image path. | Required |
| `--columns` | Number of grid columns. | `4` |
| `--thumb-width` | Width of each thumbnail. | Source resolution |
| `--padding` | Padding between thumbnails. | `4` |
| `--no-labels` | Disable filename labels below thumbnails. | `False` |
| `--font-size` | Label font size. | `16` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--start-frame` | Start frame number. | First frame |
| `--end-frame` | End frame number. | Last frame |
| `--overwrite` | Overwrite output file if it exists. | `False` |

## Environment Variables

- `OCIO`: Path to your system OCIO config when using custom/ACES input spaces.
- `IMAGEIO_FFMPEG_EXE`: Path to a custom ffmpeg binary; overrides the bundled or PATH ffmpeg.
- `RENDERKIT_FFMPEG_LOG`: FFmpeg report logging. Use `0` to disable, `1` for a temp log, or a full file path.
- `RENDERKIT_PROFILE`: Enable cProfile output for UI/CLI when set to `1`, `true`, or `yes`.
- `RENDERKIT_PROFILE_OUT`: Output `.prof` path or directory.
- `RENDERKIT_LOG_PATH`: Override RenderKit log file path.
- `RENDERKIT_LOG_LEVEL`: Logging level, such as `DEBUG`, `INFO`, or `WARNING`.
- `QT_BACKEND`: Force a Qt backend. PySide6 is the supported backend.

## Operational Notes

- FPS auto-detection logs a warning when metadata probing is unavailable or image metadata cannot
  be read, then falls back to the configured/default FPS behavior.
- OCIO conversion failures include diagnostics in the RenderKit log, including role and color-space
  resolution details, available color-space samples, and bundled LUT/config checks where possible.

## Desktop UI From The CLI

```bash
renderkit ui
```

The hidden `renderkit gui` alias also launches the desktop UI for older scripts, but `renderkit ui` is the public command.

## Python API

Use the API when integrating RenderKit into another tool instead of shelling out.

```python
from renderkit import RenderKit

processor = RenderKit()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0,
    quality=10,
    codec="libx264",
)
```

For complex setups, build an explicit config:

```python
from renderkit import RenderKit
from renderkit.core.config import ContactSheetConfig, ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

config = (
    ConversionConfigBuilder()
    .with_input_pattern("render.%04d.exr")
    .with_output_path("output.mp4")
    .with_fps(24.0)
    .with_color_space_preset(ColorSpacePreset.OCIO_CONVERSION)
    .with_explicit_input_color_space("ACES - ACEScg")
    .with_resolution(3840, 2160)
    .with_codec("libx264")
    .with_contact_sheet(
        True,
        ContactSheetConfig(columns=4, padding=10, show_labels=True),
    )
    .build()
)

processor = RenderKit()
processor.convert_with_config(config)
```
