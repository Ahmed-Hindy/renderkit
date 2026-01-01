# Image Video Processor

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://Ahmed-Hindy.github.io/renderkit/)

A high-performance Python package and CLI tool for converting image sequences (EXR, PNG, JPEG) to video (MP4) in VFX workflows.

📘 **[Full Documentation](https://Ahmed-Hindy.github.io/renderkit/)**

## Features

- **EXR to Video**: Convert high-bit depth EXR sequences to preview MP4s.
- **Smart Detection**: automatically handles `%04d`, `$F4`, `####` patterns.
- **Color Space**: Linear-to-sRGB and Rec.709 conversion presets.
- **Interfaces**: Python API, CLI (`ivp`), and PySide6 UI.

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
ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24
```

### Python API

```python
from image_video_processor import ImageVideoProcessor

processor = ImageVideoProcessor()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0
)
```

## Contributing

See our [Development Guide](https://Ahmed-Hindy.github.io/renderkit/development/) and [Contributing Guide](https://Ahmed-Hindy.github.io/renderkit/contributing/).
