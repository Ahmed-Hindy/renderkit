# Development

## Setting up Development Environment

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/Ahmed-Hindy/renderkit.git
cd renderkit

# Install with dev dependencies
uv pip install -e ".[dev]"
```

### Using pip

```bash
# Install with dev dependencies
pip install -e ".[dev]"
```

## Testing

Run tests with pytest:

```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=image_video_processor --cov-report=html

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

## Architecture

The package is organized with clear separation of concerns:

### Core Modules
- **`core/sequence.py`**: Frame sequence detection and parsing
- **`core/converter.py`**: Main conversion orchestrator
- **`core/config.py`**: Configuration classes using Builder pattern

### I/O Modules
- **`io/image_reader.py`**: Image reading with Factory pattern
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

1. **Factory Pattern**: `ImageReaderFactory` for creating appropriate image readers
2. **Strategy Pattern**: `ColorSpaceConverter` with different color space strategies
3. **Builder Pattern**: `ConversionConfigBuilder` for flexible configuration
4. **Command Pattern**: CLI commands

## CI/CD

The project uses GitHub Actions for:
- Linting (Ruff)
- Type Checking (mypy)
- Tests (Python 3.9-3.12, Linux/Windows/macOS)
- UI Tests
- Documentation Deployment
