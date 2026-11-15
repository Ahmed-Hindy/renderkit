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
renderkit ui [OPTIONS]
renderkit convert-exr-sequence INPUT_PATTERN OUTPUT_PATH [OPTIONS]
renderkit batch-convert ROOT [OPTIONS]
renderkit replace-sequence-with-mp4 INPUT_PATTERN OUTPUT_MP4 [OPTIONS]
renderkit batch-replace ROOT_PATH [OPTIONS]
renderkit contact-sheet INPUT_PATTERN OUTPUT_PATH [OPTIONS]
renderkit video-to-exr INPUT_VIDEO OUTPUT_PATTERN [OPTIONS]
renderkit transcode INPUT_VIDEO OUTPUT_VIDEO [OPTIONS]
renderkit proxy INPUT_VIDEO [OPTIONS]
```

`INPUT_PATTERN` accepts common sequence styles:

```text
render.%03d.exr
render.%04d.exr
render.%05d.exr
render.####.exr
render.$F4.exr
```

Printf-style patterns support the padding width used by the sequence, such as `%03d`, `%04d`,
`%05d`, or another `%0Nd` width.

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

### Color Space Preset & OCIO Display/View Grading

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --color-space linear_to_rec709
```

Available `--color-space` presets:

- `linear_to_srgb`
- `linear_to_rec709`
- `srgb_to_linear`
- `no_conversion`
- `ocio_conversion`

For full OpenColorIO Display/View transforms and look grading, use `--ocio`, `--input-space`,
`--display`, `--view`, `--exposure`, and `--gamma` (providing OCIO options automatically selects
`ocio_conversion`):

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 \
  --ocio /studio/ocio/config.ocio \
  --input-space "ACES - ACEScg" \
  --display sRGB \
  --view "ACES 1.0 - SDR Video" \
  --exposure 0.5 \
  --gamma 1.0
```

### Codec, Profiles, And Quality

H.264 (`libx264`) is the default. RenderKit supports delivery MP4 codecs, 10-bit HEVC,
10/12-bit ProRes and DNxHR `.mov` editorial profiles, and hardware-accelerated encoders with
automatic fallback to software (`libx264` / `libx265`) when hardware drivers are unavailable:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec libx265 --quality 8
renderkit convert-exr-sequence render.%04d.exr output_10bit.mp4 --codec hevc_10bit --quality 8
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec libaom-av1 --quality 8
renderkit convert-exr-sequence render.%04d.exr editorial.mov --codec prores_422 --quality 10
renderkit convert-exr-sequence render.%04d.exr editorial_dnx.mov --codec dnxhr_hqx --quality 10
```

| Profile | FFmpeg Encoder | Container | Bit Depth | Notes |
|---|---|---|---|---|
| `libx264`, `h264` | `libx264` | `.mp4` | 8-bit | Default web/dailies delivery |
| `libx265`, `hevc` | `libx265` | `.mp4` | 8-bit | High-efficiency MP4 |
| `hevc_10bit`, `libx265_10bit` | `libx265` | `.mp4` | 10-bit | `yuv420p10le`, `hvc1` tag |
| `libaom-av1`, `av1` | `libaom-av1` | `.mp4` | 8-bit | AV1 delivery |
| `prores_proxy`, `prores_lt`, `prores_422`, `prores_hq`, `prores` | `prores_ks` | `.mov` | 10-bit | Apple ProRes 422 profiles |
| `prores_4444`, `prores_xq` | `prores_ks` | `.mov` | 12-bit | ProRes 4444 with alpha |
| `dnxhr_hq` | `dnxhd` | `.mov` | 8-bit | Avid DNxHR HQ |
| `dnxhr_hqx` | `dnxhd` | `.mov` | 10-bit | Avid DNxHR HQX |
| `h264_nvenc`, `hevc_nvenc` | NVENC | `.mp4` | 8-bit | NVIDIA GPU; falls back to software |
| `h264_qsv`, `hevc_qsv` | Intel QSV | `.mp4` | 8-bit | Intel Quick Sync; falls back to software |
| `h264_videotoolbox`, `hevc_videotoolbox` | VideoToolbox | `.mp4` | 8-bit | macOS hardware; falls back to software |
| `h264_vaapi` | VAAPI | `.mp4` | 8-bit | Linux VA-API; falls back to software |

`--quality` uses a 0-10 scale where 10 is highest quality.

### Specific EXR Layer

```bash
renderkit convert-exr-sequence render.%04d.exr diffuse.mp4 --layer diffuse
```

### Burn-ins, HUD Zones, And Metadata Tokens

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-layer --burnin-fps
```

Tune the burn-in background:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-opacity 45
```

When configuring burn-ins in JSON presets or the Python API (`BurnInElement`), elements can be
placed into 6 named HUD zones (`top_left`, `top_center`, `top_right`, `bottom_left`,
`bottom_center`, `bottom_right`) and reference dynamic tokens:

- Standard tokens: `{frame}`, `{frame_range}`, `{shot}`, `{layer}`, `{fps}`, `{fps:.2f}`,
  `{user}`, `{resolution}`, `{colorspace}`, `{date}`, `{file}`, `{filename}`, `{stem}`
- EXR header attribute tokens: `{exr:<attr>}` (for example `{exr:compression}` or
  `{exr:camera}`)

### Intro Slates

Prepend a styled intro slate frame containing show/shot/artist/date/frame-range/codec metadata:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 \
  --slate \
  --slate-title "Lighting Dailies" \
  --slate-show "SHOW" \
  --slate-shot "sh010" \
  --slate-artist "Alex" \
  --slate-notes "Check rim key and spec lobes"
```

### Watermarks

Apply a centered or staggered tiled watermark overlay (supports `{user}`, `{shot}`, `{date}`,
and `{exr:<attr>}` tokens):

```bash
renderkit convert-exr-sequence render.%04d.exr client_review.mp4 \
  --watermark "CONFIDENTIAL - {user}" \
  --watermark-opacity 25 \
  --watermark-tiled
```

### JSON Presets & `RENDERKIT_PRESET_PATH`

Load a JSON preset or save the active CLI flags as a reusable preset:

```bash
renderkit convert-exr-sequence render.%04d.exr output.mp4 --preset presets/studio_dailies.json
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec prores_422 --save-preset my_prores.json
```

When `RENDERKIT_PRESET_PATH` is set (colon-separated on POSIX, semicolon-separated on Windows),
presets can be referenced by short name (with or without `.json`):

```powershell
$env:RENDERKIT_PRESET_PATH = "G:\Projects\Dev\Github\renderkit\presets"
renderkit convert-exr-sequence render.%04d.exr output.mp4 --preset studio_dailies
```

Included sample presets in `presets/`:

- `presets/studio_dailies.json`: `libx264`, quality 8, `ocio_conversion` (`ACES - ACEScg`), 6-zone HUD burn-ins.
- `presets/client_review_watermarked.json`: `libx264`, quality 7, `ocio_conversion`, intro slate, tiled `"CONFIDENTIAL - {user}"` watermark, and HUD burn-ins.
- `presets/editorial_prores422.json`: `prores_422`, quality 10, `ocio_conversion`, 10-bit editorial `.mov` output.

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

## Editorial Video Workflows (`video-to-exr`, `transcode`, `proxy`)

### Video-to-EXR Plate Ingest

Decode a video file into atomic 16-bit half-float (or 32-bit float) OpenEXR plates:

```bash
renderkit video-to-exr plate.mov plates/shot.%04d.exr --start-frame 1001 --compression dwaa
```

### Editorial Video Transcode

Transcode an existing movie with optional scaling, OCIO display/view grading, and watermarks:

```bash
renderkit transcode master.mov review_h264.mp4 --codec libx264 --width 1280 --watermark "REVIEW" --watermark-opacity 25
```

### Proxy Generation

Generate a scaled editorial proxy (defaults to `<input_dir>/Proxy/<stem>_proxy.mp4` or `.mov`):

```bash
renderkit proxy master.mov --scale 0.5 --codec libx264
```

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

Use `batch-convert` when RenderKit should discover sequences recursively and write review MP4s/MOVs
plus audit manifests:

```powershell
renderkit batch-convert G:\Projects\Data_folder --ext exr --out _review_mp4s --fps 24 --overwrite
```

Apply a preset (including ProRes `.mov` container selection, burn-ins, slates, or watermarks):

```powershell
renderkit batch-convert G:\Projects\Data_folder --preset studio_dailies --overwrite
```

By default, relative output and manifest paths are resolved under `ROOT`. Existing outputs are
skipped unless `--overwrite` is set. The command keeps processing after per-sequence failures and
exits nonzero if any sequence failed.

Extension matching is case-insensitive, so `--ext exr` also finds `.EXR` frames. Output names are
built from the relative folder path and sequence prefix. If multiple discovered sequences would
write the same output path in one run, RenderKit appends a numeric suffix such as `_2`.

Default manifests:

- `_review_mp4s/renderkit_batch_manifest.csv`
- `_review_mp4s/renderkit_batch_results.jsonl`

Each manifest record includes the source pattern, output path, frame count, frame range, output
size, status, and error text. Use the JSONL file for automation that tails results while a batch is
running, and the CSV file for review in spreadsheets or asset-management tools.

### Watch Folder Automation (`batch-convert --watch`)

Continuously poll a render output directory, wait for active frame writes to settle, and convert
new or re-rendered sequences automatically:

```powershell
renderkit batch-convert G:\Projects\Renders --out _review_mp4s --preset studio_dailies --watch --watch-interval 5.0 --settle-seconds 2.0
```

Use `--max-polls` in CI or cron jobs to bound the number of polling passes.

### Verify Review MP4s

Use `ffprobe` when you need an independent readability check before publish or cleanup:

```powershell
$reviews = Get-ChildItem G:\Projects\Data_folder\_review_mp4s -Filter *.mp4 -Recurse
foreach ($review in $reviews) {
    ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $review.FullName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ffprobe failed for $($review.FullName)"
    }
}
```

`replace-sequence-with-mp4 --verify` and `batch-replace --verify` run the same kind of MP4
readability check before replacement cleanup.

### Compare Work And Publish Folders

Before replacing source EXRs, compare the work render tree against the publish tree so missing or
extra sequence groups are visible. This PowerShell helper compares sequence keys by relative folder,
filename prefix, extension, and frame padding:

```powershell
function Get-RenderSequenceKeys($root) {
    Get-ChildItem $root -Recurse -File -Filter *.exr |
        ForEach-Object {
            if ($_.BaseName -match '^(.*?)(\d+)$') {
                $relativeDir = [System.IO.Path]::GetRelativePath($root, $_.DirectoryName)
                "$relativeDir\$($Matches[1])%0$($Matches[2].Length)d$($_.Extension.ToLower())"
            }
        } |
        Sort-Object -Unique
}

$workSequences = Get-RenderSequenceKeys "G:\Projects\shot\work"
$publishSequences = Get-RenderSequenceKeys "G:\Projects\shot\publish"
Compare-Object $workSequences $publishSequences
```

Rows marked `<=` exist only in the work folder. Rows marked `=>` exist only in the publish folder.
Run the comparison before destructive cleanup and keep the command output with the batch manifests
when the result needs to be audited.

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

Safety behavior:

- RenderKit only deletes frame files that are detected from `INPUT_PATTERN`.
- The audit report path is checked before copy or delete work begins.
- `--dry-run` writes an audit record but does not copy the MP4 or delete frames.
- `--verify` checks the replacement MP4 with `ffprobe`; non-dry-run deletion also verifies the
  copied MP4 before removing source frames.
- If verification, copying, deletion, or audit writing fails, the command exits with an error.

By default, the audit file is written next to the source sequence:

```text
renderkit-replacement-audit.jsonl
```

Audit records are JSON objects with these fields:

| Field | Description |
|---|---|
| `timestamp` | UTC timestamp for the attempt. |
| `source_pattern` | Sequence pattern passed to the command. |
| `source_frames` | Exact source frame files detected for replacement. |
| `source_count` | Number of detected source frames. |
| `replacement_mp4` | MP4 path supplied to the command. |
| `copied_mp4` | Destination MP4 path in the source sequence folder. |
| `deleted_frames` | Frames deleted, or frames that would be deleted during dry-run cleanup. |
| `deleted_count` | Number of deleted frames. |
| `reclaimed_bytes` | Bytes reclaimed by deletion, or bytes that would be reclaimed in a dry run. |
| `dry_run` | Whether the command avoided copy/delete work. |
| `verified` | Whether MP4 verification ran successfully. |
| `copied` | Whether RenderKit copied the MP4 into the source sequence folder. |

### Batch Replacement Cleanup

Use `batch-replace` when a folder tree contains EXR sequences and a review folder contains matching
MP4s generated by `batch-convert`:

```powershell
renderkit batch-replace G:\Projects\Data_folder --mp4-dir _review_mp4s --verify --delete-source --dry-run
```

`--mp4-dir` is relative to `ROOT_PATH` unless it is absolute. For each detected EXR sequence,
RenderKit derives the expected MP4 name with the same relative-folder naming used by
`batch-convert`, such as `render.%04d.exr` to `render.mp4` at the root or
`shot_a/render.%04d.exr` to `shot_a_render.mp4` in a nested folder. It then runs the same
verification and audit workflow as `replace-sequence-with-mp4` and appends results to:

```text
renderkit-batch-replace-audit.jsonl
```

Before using `batch-replace`, confirm the approved MP4s still use the names produced by
`batch-convert`. If review movies were renamed by hand, use explicit `replace-sequence-with-mp4`
calls or stage renamed MP4s in `--mp4-dir`.

## `ui` Options

| Option | Description | Default |
|---|---|---|
| `--open` | Initial sequence pattern or file path to open in the UI. | None |
| `--layer` | Initial EXR layer/AOV name to select. | None |
| `--preset` | Preset name (via `RENDERKIT_PRESET_PATH`) or JSON preset path to apply on startup. | None |
| `--ocio` | Path to a custom OpenColorIO config file. | None |

## `convert-exr-sequence` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_PATTERN` | File pattern with a frame placeholder. | Required |
| `OUTPUT_PATH` | Output video file path. | Required |
| `--prefetch-workers` | Number of frame prefetch workers; use `1` to disable concurrent prefetch. | `2` |
| `--fps` | Frame rate. If omitted, RenderKit attempts auto-detection. | Auto-detect |
| `--quality` | Visual quality on a 0-10 scale. | `10` |
| `--color-space` | `linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, `no_conversion`, or `ocio_conversion`. | `linear_to_srgb` |
| `--width` | Output width. Must be paired with `--height`. | Source width |
| `--height` | Output height. Must be paired with `--width`. | Source height |
| `--codec` | Codec or profile (`libx264`, `libx265`, `hevc_10bit`, `libaom-av1`, `prores_422`, `prores_hq`, `prores_4444`, `dnxhr_hq`, `dnxhr_hqx`, `h264_nvenc`, `hevc_nvenc`, `h264_qsv`, `hevc_qsv`, `h264_videotoolbox`, `hevc_videotoolbox`, `h264_vaapi`). | `libx264` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--start-frame` | Start frame number. | First frame |
| `--end-frame` | End frame number. | Last frame |
| `--ocio` | Path to a custom OpenColorIO config file. | None |
| `--input-space` | Explicit input color space name (for OCIO). | Auto-detect |
| `--display` | OCIO display name. | Config default |
| `--view` | OCIO view name. | Display default |
| `--exposure` | Exposure adjustment in stops. | `0.0` |
| `--gamma` | Gamma adjustment (`> 0`). | `1.0` |
| `--preset` | Load conversion settings from a JSON preset file or `RENDERKIT_PRESET_PATH`. | None |
| `--save-preset` | Save conversion settings to a JSON preset file. | None |
| `--slate` | Prepend an intro slate frame before sequence frames. | `False` |
| `--slate-title` | Title text for the slate frame. | `""` |
| `--slate-show` | Show/project name for the slate frame. | `""` |
| `--slate-shot` | Shot name for the slate frame. | `""` |
| `--slate-artist` | Artist name for the slate frame. | `""` |
| `--slate-notes` | Notes text for the slate frame. | `""` |
| `--overwrite` | Overwrite output file if it exists. | `False` |
| `--burnin-frame` | Burn in frame number. | `False` |
| `--burnin-layer` | Burn in layer name. | `False` |
| `--burnin-fps` | Burn in frame rate. | `False` |
| `--burnin-opacity` | Burn-in background opacity from 0-100. | `30` |
| `--watermark` | Watermark text overlay applied across the output video. | None |
| `--watermark-opacity` | Watermark opacity percentage from 0-100. | `25` |
| `--watermark-tiled` | Tile watermark text across the frame instead of centering. | `False` |
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
| `--out` | Output directory for generated videos. Relative paths resolve under `ROOT`. | `_review_mp4s` |
| `--prefetch-workers` | Number of frame prefetch workers; use `1` to disable concurrent prefetch. | `2` |
| `--fps` | Frame rate. If omitted, RenderKit attempts auto-detection per sequence. | Auto-detect |
| `--quality` | Visual quality on a 0-10 scale. | `10` |
| `--color-space` | `linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, `no_conversion`, or `ocio_conversion`. | `linear_to_srgb` |
| `--width` | Output width. Must be paired with `--height`. | Source width |
| `--height` | Output height. Must be paired with `--width`. | Source height |
| `--codec` | Video codec or profile (`libx264`, `libx265`, `prores_422`, `dnxhr_hqx`, etc.). | `libx264` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--ocio` | Path to a custom OpenColorIO config file. | None |
| `--input-space` | Explicit input color space name (for OCIO). | Auto-detect |
| `--display` | OCIO display name. | Config default |
| `--view` | OCIO view name. | Display default |
| `--exposure` | Exposure adjustment in stops. | `0.0` |
| `--gamma` | Gamma adjustment (`> 0`). | `1.0` |
| `--overwrite` | Overwrite output files if they exist. | `False` |
| `--manifest-csv` | CSV manifest path. Relative paths resolve under `ROOT`. | `OUTPUT_DIR/renderkit_batch_manifest.csv` |
| `--manifest-jsonl` | JSONL results path. Relative paths resolve under `ROOT`. | `OUTPUT_DIR/renderkit_batch_results.jsonl` |
| `--no-progress` | Disable progress bars for stable captured logs. | `False` |
| `--preset` | Load base conversion settings from a preset name or JSON file. | None |
| `--watch` | Continuously poll `ROOT` for newly settled sequences and convert them. | `False` |
| `--watch-interval` | Seconds between watch folder polls. | `5.0` |
| `--settle-seconds` | Minimum age in seconds since last frame write before converting. | `2.0` |
| `--max-polls` | Maximum number of watch polls before exiting. | Unlimited |

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
| `--no-labels` | Disable layer labels below thumbnails. | `False` |
| `--font-size` | Label font size. | `16` |
| `--layer` | EXR layer/AOV to extract. | None |
| `--start-frame` | Start frame number. | First frame |
| `--end-frame` | End frame number. | Last frame |
| `--overwrite` | Overwrite output file if it exists. | `False` |

## `video-to-exr` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_VIDEO` | Source video file path. | Required |
| `OUTPUT_PATTERN` | Output EXR pattern (`%04d` or `####`). | Required |
| `--start-frame` | Starting frame number for output EXR files. | `1001` |
| `--source-start` | Optional 0-based inclusive start frame in `INPUT_VIDEO`. | Start of video |
| `--source-end` | Optional 0-based inclusive end frame in `INPUT_VIDEO`. | End of video |
| `--compression` | EXR compression (`none`, `rle`, `zip`, `zips`, `piz`, `pxr24`, `b44`, `b44a`, `dwaa`, `dwab`). | `dwaa` |
| `--float32` | Write 32-bit float EXRs instead of 16-bit half float. | `False` |
| `--input-space` | Input video color space. | `sRGB` |
| `--output-space` | Output EXR color space. | `Linear` |
| `--ocio` | Path to a custom OpenColorIO config file. | None |

## `transcode` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_VIDEO` | Source video file path. | Required |
| `OUTPUT_VIDEO` | Destination video file path. | Required |
| `--codec` | Target video codec or profile. | `libx264` |
| `--fps` | Override output frame rate. | Source FPS |
| `--quality` | Video quality on a 0-10 scale. | `10` |
| `--width` | Target width (preserves aspect ratio if used alone). | Source width |
| `--height` | Target height (preserves aspect ratio if used alone). | Source height |
| `--ocio` | Path to a custom OpenColorIO config file. | None |
| `--input-space` | Input video color space. | `sRGB` |
| `--output-space` | Output video color space. | `sRGB` |
| `--display` | OCIO display name. | None |
| `--view` | OCIO view name. | None |
| `--exposure` | Exposure adjustment in stops. | `0.0` |
| `--gamma` | Gamma adjustment (`> 0`). | `1.0` |
| `--watermark` | Watermark text overlay applied across the transcoded video. | None |
| `--watermark-opacity` | Watermark opacity percentage from 0-100. | `25` |
| `--watermark-tiled` | Tile watermark text across the frame instead of centering. | `False` |

## `proxy` Options

| Option | Description | Default |
|---|---|---|
| `INPUT_VIDEO` | Source video file path. | Required |
| `--output` | Optional destination proxy path. | `Proxy/<stem>_proxy.mp4\|.mov` |
| `--scale` | Proxy resolution scale factor in `(0.0, 1.0]`. | `0.5` |
| `--codec` | Target proxy codec or profile. | `libx264` |
| `--quality` | Video quality on a 0-10 scale. | `10` |

## DCC Integrations (Houdini 21.0 & Nuke)

Drop-in wrapper scripts live in `integrations/` and delegate to `renderkit.integrations.houdini`
and `renderkit.integrations.nuke`.

### Houdini 21.0 (ROP / Solaris Husk / TOPs / Shelf)

Add RenderKit's environment to `PYTHONPATH` (or launch via a virtual environment with RenderKit
installed).

**Post-Render Script (`integrations/houdini/post_render_dailies.py`):**

In a Karma/Mantra ROP, Solaris USD Render ROP, or TOPs Post-Render Script (Python):

```python
from integrations.houdini import post_render_dailies

post_render_dailies.main(preset="studio_dailies", contact_sheet=False)
```

`main(node=None, *, preset=None, contact_sheet=False)` inspects `vm_picture`, `picture`,
`lopoutput`, `sopoutput`, or `outputimage`, inherits `hou.fps()` and `$OCIO`, and produces a review
`.mp4` or `.mov` alongside the rendered sequence.

**Shelf Tool (`integrations/houdini/launch_renderkit_shelf.py`):**

```python
from integrations.houdini import launch_renderkit_shelf

launch_renderkit_shelf.launch_selected_node_in_renderkit(preset="studio_dailies")
```

### Foundry Nuke (`integrations/nuke/menu.py`)

Add `integrations/nuke/menu.py` to your `NUKE_PATH` (or import it from `~/.nuke/menu.py` via
`from integrations.nuke.menu import create_dailies_menu; create_dailies_menu()`). It registers a
**RenderKit** menu with:

- **Generate Dailies (RenderKit)**: converts the selected `Write`/`Read` node (`file`, `first`,
  `last`, `colorspace`, `$OCIO`) to dailies (defaults to `prores_422` unless overridden by a preset).
- **Open in RenderKit UI**: spawns `renderkit ui --open ... --ocio ...` for the selected node.

## Environment Variables

- `OCIO`: Default OpenColorIO config path used when `--ocio` is not specified.
- `RENDERKIT_PRESET_PATH`: Search path list (`;` on Windows, `:` on POSIX) for `--preset` short names.
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
- OCIO conversions use `$OCIO` when set or fall back to RenderKit's bundled OCIO config.
- OCIO conversion failures include diagnostics in the RenderKit log, including role and color-space
  resolution details, available color-space samples, and bundled LUT/config checks where possible.

## Desktop UI From The CLI

```bash
renderkit ui --open render.%04d.exr --layer beauty --preset studio_dailies --ocio /studio/ocio/config.ocio
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
    exposure=0.25,
    gamma=1.0,
)
```

For complex setups, build an explicit config:

```python
from renderkit import RenderKit
from renderkit.core.config import (
    ContactSheetConfig,
    ConversionConfigBuilder,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.processing.color_space import ColorSpacePreset

config = (
    ConversionConfigBuilder()
    .with_input_pattern("render.%04d.exr")
    .with_output_path("output.mp4")
    .with_fps(24.0)
    .with_color_space_preset(ColorSpacePreset.OCIO_CONVERSION)
    .with_ocio(input_space="ACES - ACEScg", display="sRGB", view="ACES 1.0 - SDR Video")
    .with_grade(exposure=0.5, gamma=1.0)
    .with_slate(SlateConfig(enabled=True, title="Dailies", shot="sh010", artist="Alex"))
    .with_watermark(WatermarkConfig(text="CONFIDENTIAL - {user}", opacity=25, tiled=True))
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
