# Usage Guide

## Command Line Interface (CLI)

The CLI entrypoint is `renderkit`.

### Examples

```bash
# Basic conversion (high quality)
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24

# Set specific visual quality (7 is a good balance)
renderkit convert-exr-sequence render.%04d.exr output.mp4 --quality 7

# Using AV1 for maximum compression
renderkit convert-exr-sequence render.%04d.exr output.mp4 --codec libaom-av1 --quality 8

# Multi-AOV contact sheet video
renderkit convert-exr-sequence render.%04d.exr output.mp4 --contact-sheet --cs-columns 4

# Burn-in frame number and FPS
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-fps
```

### Options

| Option | Description | Default |
|---|---|---|
| `INPUT_PATTERN` | File pattern with placeholders | Required |
| `OUTPUT_PATH` | Output video file path | Required |
| `--fps` | Frame rate | Auto-detect |
| `--quality` | Visual Quality (0-10), 10 is best | `10` |
| `--color-space` | `linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, `no_conversion` | `linear_to_srgb` |
| `--width` | Output width | Source width |
| `--height` | Output height | Source height |
| `--codec` | Video codec (`libx264`, `libaom-av1`, `libx265`, etc.) | `libx264` |
| `--layer` | EXR layer/AOV to extract | None |
| `--start-frame` | Start frame number | First frame |
| `--end-frame` | End frame number | Last frame |
| `--overwrite` | Overwrite output file if it exists | `False` |
| `--burnin-frame` | Burn in frame number | `False` |
| `--burnin-layer` | Burn in layer name | `False` |
| `--burnin-fps` | Burn in frame rate | `False` |
| `--burnin-opacity` | Burn-in background opacity (0-100) | `30` |
| `--contact-sheet` | Enable multi-AOV grid mode | `False` |
| `--cs-columns` | Contact sheet columns | `4` |
| `--cs-thumb-width` | Width of each layer cell | `512` |
| `--cs-padding` | Spacing between cells | `10` |
| `--cs-no-labels` | Disable layer name labels | `False` |

## Python API

### Basic Usage

```python
from renderkit import RenderKit

processor = RenderKit()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0,
    quality=10,  # 0-10 scale
    codec="libx264",
)
```

### Advanced Configuration

Use the Builder pattern for complex configurations:

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
    .with_codec("avc1")
    .with_contact_sheet(
        True,
        ContactSheetConfig(columns=4, thumbnail_width=512, padding=10, show_labels=True),
    )
    .build()
)

processor = RenderKit()
processor.convert_with_config(config)
```

## Graphical Interface (UI)

Launch the UI from the terminal:

```bash
python -m renderkit.ui.main_window
```

If you have a Pre-compiled build, run the exe in the `RenderKit/` folder.

### Qt Backend

PySide6 is the supported backend. You can force a backend with `QT_BACKEND` if needed:

```bash
# macOS/Linux
export QT_BACKEND=pyside6
```

```powershell
# Windows PowerShell
$env:QT_BACKEND = "pyside6"
```

## Environment Variables

- `OCIO`: Path to your system OCIO config (used when selecting ACES/custom input spaces).
- `IMAGEIO_FFMPEG_EXE`: Path to a custom ffmpeg binary (optional, for offline systems).
- `QT_BACKEND`: Force a Qt backend (default is auto-detect; PySide6 is recommended).
