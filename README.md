# RenderKit

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://Ahmed-Hindy.github.io/renderkit/)

A high-performance Python package and CLI tool for converting image sequences (EXR, PNG, JPEG) to video (MP4) in VFX workflows.

📘 **[Full Documentation](https://Ahmed-Hindy.github.io/renderkit/)**

## Features

- **VFX-Standard I/O**: High-performance image reading and scaling powered by **OpenImageIO**.
- **Broad Format Support**: Native support for **EXR, DPX, TIFF, PNG, and JPEG**.
- **Quality-First Video**: 0-10 Quality Slider using **Constant Rate Factor (CRF)** for professional results.
- **AV1 & HEVC**: Support for modern codecs including **AV1** and **H.265 (HEVC)**.
- **Smart Detection**: Automatically handles `%04d`, `$F4`, `####` and numeric sequences.
- **Multi-AOV Contact Sheets**: Generate a video grid of all AOVs (layers) for every frame.
- **Color Space**: Professional color management including **Linear-to-sRGB** and **Rec.709** presets.
- **Interfaces**: Python API, CLI (`renderkit`), and PySide6 UI.

## Installation

```bash
# Clone the repository
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit

# Install the package in editable mode
uv pip install -e .
```

## Quick Start

### CLI

```bash
# Convert EXR sequence to MP4
renderkit convert-exr-sequence render.%04d.exr output.mp4 --fps 24

# Generate a Multi-AOV Contact Sheet video
renderkit convert-exr-sequence render.%04d.exr output.mp4 --contact-sheet --cs-columns 4
```

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
