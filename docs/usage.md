# Usage Guide

## Command Line Interface (CLI)

The simplest way to use the tool is via the CLI command `renderkit`.

### Examples

```bash
# Basic conversion
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24

# With custom resolution
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --width 1920 --height 1080

# With frame range
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --start-frame 100 --end-frame 200

# With different color space
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --color-space linear_to_rec709
```

### Options

| Option | Description | Default |
|Params|---|---|
| `INPUT_PATTERN` | File pattern with placeholders | Required |
| `OUTPUT_PATH` | Output video file path | Required |
| `--fps` | Frame rate | Auto-detect |
| `--color-space` | Preset (`linear_to_srgb`, etc.) | `linear_to_srgb` |
| `--width` | Output width | Source width |
| `--height` | Output height | Source height |
| `--codec` | Video codec | `mp4v` |
| `--start-frame` | Start frame | First frame |
| `--end-frame` | End frame | Last frame |

## Python API

### Basic Usage

```python
from renderkit import RenderKit

processor = RenderKit()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0,
)
```

### Advanced Configuration

Use the Builder pattern for complex configurations:

```python
from renderkit import RenderKit
from renderkit.core.config import ConversionConfigBuilder
from renderkit.processing.color_space import ColorSpacePreset

config = (
    ConversionConfigBuilder()
    .with_input_pattern("render.%04d.exr")
    .with_output_path("output.mp4")
    .with_fps(24.0)
    .with_color_space_preset(ColorSpacePreset.LINEAR_TO_REC709)
    .with_resolution(3840, 2160)
    .with_codec("avc1")
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

### Qt Backends

You can control the backend using the `QT_BACKEND` environment variable:

```bash
export QT_BACKEND=pyside2  # For Houdini compatibility
```
