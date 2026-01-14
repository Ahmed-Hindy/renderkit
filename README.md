# RenderKit

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![VFX Platform CY2026](https://img.shields.io/badge/VFX_Platform-CY2026-2b7a78.svg)](https://vfxplatform.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://Ahmed-Hindy.github.io/renderkit/)

A high-performance Python package and CLI tool for converting image sequences (EXR, PNG, JPEG) to video (MP4) in VFX workflows.
Targets the VFX Platform CY2026 spec (Python 3.13.x, Qt 6.8/PySide6 6.8, OpenColorIO 2.5, NumPy 2.3).

**[Full Documentation](https://Ahmed-Hindy.github.io/renderkit/)**

## Features

- **VFX-Standard I/O**: High-performance image reading and scaling powered by **OpenImageIO**.
- **Broad Format Support**: Native support for **EXR, DPX, TIFF, PNG, and JPEG**.
- **Quality-First Video**: 0-10 Quality Slider using **Constant Rate Factor (CRF)** for professional results.
- **H.264 Default + AV1/HEVC**: Support for **H.264 (AVC)** by default, with **AV1** and **H.265 (HEVC)** options.
- **Smart Detection**: Automatically handles `%04d`, `$F4`, `####` and numeric sequences.
- **Multi-AOV Contact Sheets**: Generate a video grid of all AOVs (layers) for every frame.
- **Color Space**: Professional color management including **Linear-to-sRGB** and **Rec.709** presets.
- **Interfaces**: Python API, CLI (`renderkit`), and PySide6 UI.

## Installation

### Prebuilt App (Windows, Linux, MacOS)

Download a .zip file from the Releases section, unpack then run the executable:

Example for Windows:
```
RenderKit/RenderKit.exe
```

### From Source (uv)

```bash
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit
uv pip install -e .
```
Requires Python 3.13.x (VFX Platform CY2026).

## Quick Start

### CLI

```bash
# Convert EXR sequence to MP4
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24

# Generate a Multi-AOV Contact Sheet video
renderkit convert-exr-sequence render.%04d.exr output.mp4 --contact-sheet --cs-columns 4

# Add burn-ins
renderkit convert-exr-sequence render.%04d.exr output.mp4 --burnin-frame --burnin-fps
```

### UI

```bash
python -m renderkit.ui.main_window
```

### Environment Variables

- `OCIO`: Path to your system OCIO config (used when selecting ACES/custom input spaces).
- `IMAGEIO_FFMPEG_EXE`: Path to a custom ffmpeg binary (optional, for offline systems).
- `RENDERKIT_FFMPEG_LOG`: FFmpeg report logging (default: on). Set to `0` to disable, `1` for temp log, or a full file path.
- `RENDERKIT_LOG_PATH`: Override RenderKit log file path (default: temp dir `renderkit.log`).
- `RENDERKIT_LOG_LEVEL`: Logging level (`DEBUG`, `INFO`, `WARNING`, etc.).
- `QT_BACKEND`: Force a Qt backend (default is auto-detect; PySide6 is recommended).

### Python API

```python
from renderkit import RenderKit

processor = RenderKit()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0
)
```

## Contributing

See our [Development Guide](https://Ahmed-Hindy.github.io/renderkit/development/) and [Contributing Guide](https://Ahmed-Hindy.github.io/renderkit/contributing/).
