# RenderKit

A high-performance image and video processor for VFX workflows, built with Python and PySide6.

## Features

- **EXR to Video Conversion**: High-quality conversion of EXR sequences to MP4/ProRes.
- **Color Space Management**: Presets for common VFX workflows (Linear to Rec.709, etc.).
- **Automatic Sequence Detection**: Smart frame formatting detection (e.g., `%04d` or `#`).
- **Modern UI**: Dark-themed, responsive interface using PySide6.
- **CLI Support**: Fully functional command-line interface for batch processing.

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
