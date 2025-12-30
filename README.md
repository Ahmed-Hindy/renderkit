# Image Video Processor

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

### Using uv (Recommended)

```bash
# Install uv if you haven't already
pip install uv

# Install the package
cd image_video_processor
uv pip install -e .

# Or install with dev dependencies
uv pip install -e ".[dev]"
```

### Using pip

```bash
pip install -e .
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

Run tests with pytest:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=image_video_processor --cov-report=html

# Run with benchmarks
pytest --benchmark-only
```

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
cd image_video_processor

# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format .
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

Contributions are welcome! Please ensure:
- Code follows PEP 8 style guidelines
- All tests pass
- Type hints are included
- Documentation is updated

## Author

Ahmed Hindy

