# RenderKit

A high-performance image and video processor for VFX workflows, built with Python and PySide6.

## Features

- **OpenImageIO Integration**: High-performance, VFX-standard image reading and scaling.
- **Broad Format Support**: Native handling of **EXR, DPX, TIFF, PNG, and JPEG**.
- **Quality-First UI**: Intuitive 0-10 Quality Slider using Constant Rate Factor (CRF).
- **AV1 & HEVC Support**: Modern codec support with multi-threading optimizations.
- **Smart Sequence Detection**: Automatic detection of Houdini, Maya, and generic frame patterns.
- **Modern UI**: Dark-themed, studio-grade interface using PySide6.
- **CLI Support**: Fully functional command-line interface for headless automation.

## Installation

```bash
pip install renderkit
```

## Quick Start

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

## Project Structure

- `src/`: Source code
- `tests/`: Test suite
- `examples/`: Usage examples
