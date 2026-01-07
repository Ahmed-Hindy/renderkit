# Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create a feature branch.
2. **Follow code style**: The project uses [Ruff](https://docs.astral.sh/ruff/) for formatting and linting.
3. **Write tests**: Add tests for new features and ensure all tests pass.
4. **Type hints**: Include type hints for all functions and methods.
5. **Update documentation**: Keep README and docstrings up to date.

## Pull Request Workflow

1.  Clone your fork.
2.  Install dev dependencies:

    ```bash
    uv venv
    uv pip install -e ".[dev]"
    ```
3.  Create a branch.
4.  Make changes.
5.  Verify tests: `pytest`
6.  Verify linting: `ruff check` and `ruff format`
7.  Push and create PR.
