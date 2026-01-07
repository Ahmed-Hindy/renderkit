# Development

## Setting up Development Environment

### Using uv (Recommended)

```bash
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit
uv venv
uv pip install -e ".[dev]"
```

### Using pip

```bash
pip install -e ".[dev]"
```

## Testing

Run tests with pytest:

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=renderkit --cov-report=html

# Run only unit tests
python -m pytest tests/ -v -k "not test_integration_real_files"

# Run UI tests (requires pytest-qt and xvfb on Linux)
python -m pytest tests/test_ui.py -v
```

## Code Style

The project uses:
- **Ruff** for linting and formatting
- **mypy** for type checking

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy src/
```

## Build (PyInstaller)

```bash
uv pip install -e . pyinstaller
python -m PyInstaller --noconfirm RenderKit.spec
```

The distributable output is in `dist/RenderKit/`.

## Bundled FFmpeg (Windows, Hybrid)

The repo does not commit `vendor/ffmpeg/`. You can build and stage a minimal
GPL FFmpeg locally (x265 + AV1 only), and CI will also generate it for releases.

### Prerequisites (MSYS2 UCRT64)

```bash
pacman -S --needed \
  base-devel git \
  mingw-w64-ucrt-x86_64-toolchain \
  mingw-w64-ucrt-x86_64-nasm mingw-w64-ucrt-x86_64-yasm \
  mingw-w64-ucrt-x86_64-pkg-config \
  mingw-w64-ucrt-x86_64-x265 \
  mingw-w64-ucrt-x86_64-aom
```

### Build and Stage

```bash
./scripts/build_ffmpeg_windows_msys2.sh
```

This script writes `ffmpeg.exe` and required DLLs to `vendor/ffmpeg/`, which the
PyInstaller spec bundles automatically. To build a different version, set
`FFMPEG_VERSION` (default: 8.0.1):

```bash
FFMPEG_VERSION=8.0.1 ./scripts/build_ffmpeg_windows_msys2.sh
```

## Architecture

The package is organized with clear separation of concerns:

### Core Modules
- **`core/sequence.py`**: Frame sequence detection and parsing
- **`core/converter.py`**: Main conversion orchestrator
- **`core/config.py`**: Configuration classes using Builder pattern

### I/O Modules
- **`io/image_reader.py`**: Unified image reading using **OpenImageIO** (OIIO).
- **`io/file_utils.py`**: File I/O utilities and output path validation.

### Processing Modules
- **`processing/color_space.py`**: Color space conversion using OCIO-inspired strategies.
- **`processing/scaler.py`**: High-quality image scaling using **OpenImageIO** (Lanczos3).
- **`processing/video_encoder.py`**: Quality-first video encoding (CRF) using FFmpeg.

### Interface Modules
- **`api/processor.py`**: Public Python API
- **`cli/main.py`**: Command-line interface
- **`ui/main_window.py`**: PySide/Qt graphical interface

## Design Patterns

1. **Factory Pattern**: `ImageReaderFactory` for creating appropriate image readers
2. **Strategy Pattern**: `ColorSpaceConverter` with different color space strategies
3. **Builder Pattern**: `ConversionConfigBuilder` for flexible configuration
4. **Command Pattern**: CLI commands

## CI/CD

The project uses GitHub Actions for:
- Linting and formatting (Ruff)
- Type checking (mypy, non-blocking)
- Tests on Windows and Ubuntu (Python 3.10)
- UI tests on Ubuntu (xvfb)
- Python package build on Ubuntu
- PyInstaller builds on Windows, Linux, and macOS (Build workflow)
