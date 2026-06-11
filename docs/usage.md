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
renderkit contact-sheet INPUT_PATTERN OUTPUT_PATH [OPTIONS]
```

`INPUT_PATTERN` accepts common sequence styles:

```text
render.%04d.exr
render.%05d.exr
render.####.exr
render.$F4.exr
```

Printf-style `%0Nd` patterns use the requested padding width, so `%03d`, `%04d`,
`%05d`, and similar variants are valid when the source frames use that padding.

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

### Batch Review Movies With Verification

For farm or pipeline automation, treat conversion, verification, and cleanup as
separate steps. This keeps source EXRs safe until a review MP4 has been created
and checked.

1. Build a manifest of candidate sequences from the work and publish roots.
2. Convert each sequence with `--fps 24 --overwrite --no-progress`.
3. Verify every MP4 with `ffprobe`.
4. Write CSV and JSONL audit records before moving or deleting any source frames.
5. Archive or replace source EXRs only for rows whose conversion and verification
   both succeeded.

PowerShell example:

```powershell
$workRoot = "D:\show\shot010\work"
$publishRoot = "D:\show\shot010\publish"
$reviewRoot = "D:\show\shot010\review"
$manifestCsv = ".\renderkit-review-manifest.csv"
$auditJsonl = ".\renderkit-review-audit.jsonl"

$sequences = @(
    [pscustomobject]@{ Name = "beauty"; Pattern = "$workRoot\beauty.%04d.exr"; Output = "$reviewRoot\beauty.mp4" },
    [pscustomobject]@{ Name = "diffuse"; Pattern = "$workRoot\diffuse.`$F4.exr"; Output = "$reviewRoot\diffuse.mp4" },
    [pscustomobject]@{ Name = "crypto"; Pattern = "$publishRoot\crypto.####.exr"; Output = "$reviewRoot\crypto.mp4" }
)

$results = foreach ($seq in $sequences) {
    uv --native-tls run renderkit convert-exr-sequence `
        $seq.Pattern `
        $seq.Output `
        --fps 24 `
        --overwrite `
        --no-progress

    $converted = $LASTEXITCODE -eq 0 -and (Test-Path $seq.Output)
    $probeJson = $null
    $probeExitCode = $null
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($converted -and $ffprobe) {
        $probeJson = & $ffprobe.Path -v error -select_streams v:0 `
            -show_entries stream=codec_name,width,height,r_frame_rate,nb_frames `
            -of json $seq.Output
        $probeExitCode = $LASTEXITCODE
    }

    [pscustomobject]@{
        name = $seq.Name
        input_pattern = $seq.Pattern
        output_path = $seq.Output
        converted = $converted
        verified = $converted -and $probeExitCode -eq 0
        ffprobe = $probeJson
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
    }
}

$results | Export-Csv $manifestCsv -NoTypeInformation
$results | ForEach-Object { $_ | ConvertTo-Json -Compress } | Set-Content $auditJsonl
```

Before replacing source EXRs, compare the work and publish roots so the cleanup
step only touches the intended sequences:

```powershell
function Get-RelativeExrFrames($Root) {
    Get-ChildItem $Root -Recurse -Filter *.exr | ForEach-Object {
        [System.IO.Path]::GetRelativePath($Root, $_.FullName)
    } | Sort-Object
}

$workFrames = Get-RelativeExrFrames $workRoot
$publishFrames = Get-RelativeExrFrames $publishRoot
Compare-Object $workFrames $publishFrames
```

Then gate cleanup on the audit manifest. Prefer archiving first; only remove
source frames after the review MP4 exists and `ffprobe` verified it:

```powershell
$archiveRoot = "D:\show\shot010\archive\exr"

function ConvertTo-FrameNameRegex($LeafPattern) {
    $regex = [regex]::Escape($LeafPattern)
    $regex = [regex]::Replace($regex, '%0?(\d*)d', [System.Text.RegularExpressions.MatchEvaluator]{
        param($match)
        $width = $match.Groups[1].Value
        if ([string]::IsNullOrEmpty($width)) { '\d+' } else { "\d{$width}" }
    })
    $regex = [regex]::Replace($regex, '\\\$F(\d+)', [System.Text.RegularExpressions.MatchEvaluator]{
        param($match)
        "\d{$($match.Groups[1].Value)}"
    })
    $regex = [regex]::Replace($regex, '(\\#)+', [System.Text.RegularExpressions.MatchEvaluator]{
        param($match)
        $width = ($match.Value -replace '\\').Length
        "\d{$width}"
    })
    "^$regex$"
}

Import-Csv $manifestCsv | Where-Object { $_.converted -eq "True" -and $_.verified -eq "True" } |
    ForEach-Object {
        $archiveDir = Join-Path $archiveRoot $_.name
        $frameRegex = ConvertTo-FrameNameRegex (Split-Path $_.input_pattern -Leaf)
        New-Item -ItemType Directory -Force $archiveDir | Out-Null
        Get-ChildItem (Split-Path $_.input_pattern) -Filter *.exr |
            Where-Object { $_.Name -match $frameRegex } |
            Move-Item -Destination $archiveDir
    }
```

Keep the CSV/JSONL files with the review deliverables so a publish cleanup can be
audited later. If you need a dry run, replace `Move-Item` with `Write-Host` until
the manifest rows and destination paths are correct.

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
