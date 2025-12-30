# Image Video Processor

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A high-performance Python package for image and video processing in VFX workflows. Designed for converting image sequences (EXR, PNG, JPEG) to video formats (MP4) with proper color space handling and performance optimization.

## Features

- **Multi-format Support**: EXR, PNG, JPEG input formats
- **Frame Sequence Detection**: Supports multiple naming conventions:
  - `render.%04d.exr` (Houdini style)
  - `render.$F4.exr` (Houdini style)
  - `render.####.exr` (Maya style)
  - `render.0001.exr` (numeric)
- **Color Space Conversion**: Preset-based color space conversion with default linear to sRGB
- **Flexible Resolution**: Maintain source resolution or scale to custom dimensions
- **Auto FPS Detection**: Optional automatic frame rate detection
- **Multiple Interfaces**: CLI, Python API, and PySide/Qt UI
- **Performance Focused**: Efficient memory usage with optional multiprocessing
- **Clean Architecture**: Separation of concerns with design patterns (Factory, Strategy, Builder)

## Installation

### Prerequisites

- Python 3.9 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Using uv (Recommended)

```bash
# Install uv if you haven't already
pip install uv

# Clone the repository
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit

# Install the package in editable mode
uv pip install -e .

# Or install with dev dependencies for development
uv pip install -e ".[dev]"
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit

# Install the package
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

### Dependencies

The package requires:
- Python 3.9+
- OpenEXR and Imath (for EXR support)
- OpenCV (for video encoding)
- NumPy (for array operations)
- imageio (for standard image formats)

## Usage

### Command Line Interface

The simplest way to use the tool is via the CLI:

```bash
# Basic conversion
ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24

# With custom resolution
ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --width 1920 --height 1080

# With frame range
ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --start-frame 100 --end-frame 200

# With different color space
ivp convert-exr-sequence render.%04d.exr output.mp4 --fps 24 --color-space linear_to_rec709

# Using Houdini-style pattern
ivp convert-exr-sequence render.$F4.exr output.mp4 --fps 24

# Using Maya-style pattern
ivp convert-exr-sequence render.####.exr output.mp4 --fps 24
```

#### CLI Options

- `INPUT_PATTERN`: File pattern with frame number placeholder
- `OUTPUT_PATH`: Output video file path
- `--fps FLOAT`: Frame rate (optional, will attempt auto-detection if not provided)
- `--color-space`: Color space preset (`linear_to_srgb`, `linear_to_rec709`, `srgb_to_linear`, `no_conversion`)
- `--width INT`: Output width (default: source width)
- `--height INT`: Output height (default: source height)
- `--codec STR`: Video codec (default: `mp4v`, use `avc1` for H.264)
- `--start-frame INT`: Start frame number
- `--end-frame INT`: End frame number
- `--overwrite`: Overwrite output file if it exists

### Python API

#### Simple Usage

```python
from image_video_processor import ImageVideoProcessor

processor = ImageVideoProcessor()
processor.convert_exr_sequence_to_mp4(
    input_pattern="render.%04d.exr",
    output_path="output.mp4",
    fps=24.0,
)
```

#### Advanced Usage with Builder Pattern

```python
from image_video_processor import ImageVideoProcessor
from image_video_processor.core.config import ConversionConfigBuilder
from image_video_processor.processing.color_space import ColorSpacePreset

# Build configuration
config = (
    ConversionConfigBuilder()
    .with_input_pattern("render.%04d.exr")
    .with_output_path("output.mp4")
    .with_fps(24.0)
    .with_color_space_preset(ColorSpacePreset.LINEAR_TO_SRGB)
    .with_resolution(1920, 1080)
    .with_codec("avc1")
    .with_frame_range(1, 100)
    .build()
)

# Convert
processor = ImageVideoProcessor()
processor.convert_with_config(config)
```

#### Batch Processing

```python
from image_video_processor import ImageVideoProcessor

processor = ImageVideoProcessor()

sequences = [
    ("render.%04d.exr", "output/render.mp4"),
    ("beauty.%04d.exr", "output/beauty.mp4"),
    ("diffuse.%04d.exr", "output/diffuse.mp4"),
]

for input_pattern, output_path in sequences:
    processor.convert_exr_sequence_to_mp4(
        input_pattern=input_pattern,
        output_path=output_path,
        fps=24.0,
    )
```

### PySide/Qt UI

Launch the graphical interface:

```python
from image_video_processor.ui.main_window import run_ui

run_ui()
```

Or from command line (if entry point is configured):

```bash
python -m image_video_processor.ui.main_window
```

## Architecture

The package is organized with clear separation of concerns:

### Core Modules

- **`core/sequence.py`**: Frame sequence detection and parsing
- **`core/converter.py`**: Main conversion orchestrator
- **`core/config.py`**: Configuration classes using Builder pattern

### I/O Modules

- **`io/image_reader.py`**: Image reading with Factory pattern for different formats
- **`io/file_utils.py`**: File I/O utilities

### Processing Modules

- **`processing/color_space.py`**: Color space conversion using Strategy pattern
- **`processing/scaler.py`**: Image scaling utilities
- **`processing/video_encoder.py`**: Video encoding using OpenCV/FFmpeg

### Interface Modules

- **`api/processor.py`**: Public Python API
- **`cli/main.py`**: Command-line interface
- **`ui/main_window.py`**: PySide/Qt graphical interface

## Design Patterns

The codebase uses several design patterns for maintainability and extensibility:

1. **Factory Pattern**: `ImageReaderFactory` for creating appropriate image readers
2. **Strategy Pattern**: `ColorSpaceConverter` with different color space strategies
3. **Builder Pattern**: `ConversionConfigBuilder` for flexible configuration
4. **Command Pattern**: CLI commands for different operations

## Color Space Presets

- **`LINEAR_TO_SRGB`** (default): Converts linear EXR to sRGB with tone mapping
- **`LINEAR_TO_REC709`**: Converts linear to Rec.709 color space
- **`SRGB_TO_LINEAR`**: Converts sRGB to linear
- **`NO_CONVERSION`**: Passthrough without conversion

## Performance Considerations

- Efficient memory usage with frame-by-frame processing
- Optional multiprocessing for batch operations (future enhancement)
- Optimized color space conversion algorithms
- Progress tracking with `tqdm`

## Testing

Run tests with pytest using `uv`:

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Run with coverage
uv run python -m pytest tests/ --cov=image_video_processor --cov-report=html

# Run only unit tests (excluding integration tests)
uv run python -m pytest tests/ -v -k "not test_integration_real_files"

# Run only integration tests
uv run python -m pytest tests/test_integration_real_files.py -v

# Run with benchmarks
uv run python -m pytest tests/ --benchmark-only
```

### Test Coverage

The project includes comprehensive tests:
- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test the full pipeline with real EXR sequences
- **Coverage**: Currently at ~60% code coverage

All tests pass successfully with the test suite.

## Code Style

The project uses:
- **Ruff** for linting and formatting
- **pytest** for testing
- **mypy** for type checking (optional)

Format code:

```bash
ruff format .
ruff check .
```

## Development

### Setting up Development Environment

```bash
# Clone the repository
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit

# Install with dev dependencies using uv
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"

# Run tests
uv run python -m pytest tests/ -v

# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking (optional)
uv run mypy src/
```

## Examples

See the `examples/` directory for more usage examples:
- `convert_exr_sequence.py`: Basic conversion examples
- `api_usage.py`: Python API usage patterns

## Roadmap

- [ ] Support for additional video codecs
- [ ] Batch processing with multiprocessing
- [ ] Additional image formats (TIFF, DPX)
- [ ] Video to image sequence conversion
- [ ] Image processing operations (resize, crop, filters)
- [ ] Metadata preservation
- [ ] GPU acceleration support

## License

MIT License

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Follow code style**: The project uses Ruff for formatting and linting
3. **Write tests**: Add tests for new features and ensure all tests pass
4. **Type hints**: Include type hints for all functions and methods
5. **Update documentation**: Keep README and docstrings up to date
6. **Commit messages**: Use clear, descriptive commit messages

### Development Workflow

```bash
# 1. Fork and clone the repository
git clone https://github.com/yourusername/image-video-processor.git
cd image-video-processor

# 2. Install dev dependencies
uv pip install -e ".[dev]"

# 3. Make your changes

# 4. Run tests
uv run python -m pytest tests/ -v

# 5. Format and lint
uv run ruff format .
uv run ruff check .

# 6. Commit and push
git commit -m "Your descriptive commit message"
git push origin your-feature-branch

# 7. Create a Pull Request
```

### Code Style

- Follow PEP 8 style guidelines
- Use Ruff for formatting (configured in `pyproject.toml`)
- Include type hints for better code documentation
- Write docstrings for all public functions and classes

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Ahmed Hindy**

## Acknowledgments

- Built for VFX workflows and image sequence processing
- Uses OpenEXR for high dynamic range image support
- Powered by OpenCV for video encoding

