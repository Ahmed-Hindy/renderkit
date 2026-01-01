# Contributing to RenderKit

Thank you for your interest in contributing to RenderKit! This document provides guidelines and instructions for contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/Ahmed-Hindy/renderkit.git
   cd renderkit
   ```
3. **Set up development environment**:
   ```bash
   # Using uv (recommended)
   uv pip install -e ".[dev]"
   
   # Or using pip
   pip install -e ".[dev]"
   ```

## Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Write clean, readable code
   - Follow the existing code style
   - Add type hints to all functions
   - Write docstrings for public APIs

3. **Run tests**:
   ```bash
   # Run all tests
   uv run python -m pytest tests/ -v
   
   # Run with coverage
   uv run python -m pytest tests/ --cov=renderkit
   ```

4. **Format and lint**:
   ```bash
   uv run ruff format .
   uv run ruff check .
   ```

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add: descriptive commit message"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request** on GitHub

## Code Style

- **Formatting**: Use Ruff (configured in `pyproject.toml`)
- **Type Hints**: Include type hints for all functions and methods
- **Docstrings**: Write docstrings for all public functions and classes
- **Line Length**: Maximum 100 characters
- **Imports**: Use absolute imports, sorted with isort

### Running Code Quality Checks

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Type checking (optional)
uv run mypy src/
```

## Testing

- **Write tests** for all new features
- **Ensure all tests pass** before submitting a PR
- **Aim for high test coverage** (currently ~60%)
- **Include integration tests** for real-world scenarios when applicable

### Running Tests

```bash
# All tests
uv run python -m pytest tests/ -v

# Specific test file
uv run python -m pytest tests/test_sequence.py -v

# With coverage
uv run python -m pytest tests/ --cov=renderkit --cov-report=html
```

## Pull Request Guidelines

- **Clear description**: Describe what your PR does and why
- **Reference issues**: Link to any related issues
- **Update documentation**: Update README.md if needed
- **All tests pass**: Ensure CI checks pass
- **No merge conflicts**: Keep your branch up to date

## Types of Contributions

### Bug Reports

- Use the GitHub issue tracker
- Include steps to reproduce
- Provide error messages and stack traces
- Specify your environment (OS, Python version, etc.)

### Feature Requests

- Open an issue to discuss the feature first
- Explain the use case and benefits
- Consider implementation complexity

### Code Contributions

- Follow the development workflow above
- Write tests for new features
- Update documentation as needed
- Keep PRs focused on a single feature/fix

## Questions?

Feel free to open an issue for questions or discussions about contributions.

Thank you for contributing! 🎉

