# Copilot / Agent Instructions for RenderKit 🔧

Short, actionable tips to get an AI coding agent productive quickly in this repo.

## Quick orientation
- Package name: **RenderKit** (installed as `renderkit`); source is under `src/renderkit/`.
- Major subsystems:
  - `api/` — public API (`RenderKit` in `api/processor.py`).
  - `cli/` — Click CLI commands (`cli/main.py`) and examples in `examples/`.
  - `core/` — sequence parsing, converter orchestration, config builders (`core/config.py`).
  - `io/` — image readers & OIIO integration (`io/image_reader.py`).
  - `processing/` — color-space, scaling, video encoding logic.
  - `ui/` — PySide6 GUI and Qt compatibility helpers.
- Docs live in `docs/` and top-level `README.md`; use them as canonical guidance for behavior and examples.

## How to run & test locally (exact commands used in CI) ✅
- Install dev deps (preferred):
  - uv op: `uv pip install -e ".[dev]"` (CI uses `astral-sh/setup-uv` and `uv.lock`).
  - fallback: `pip install -e ".[dev]"`
- Lint/format:
  - `ruff format .` (format)
  - `ruff check .` (lint)
  - ruff config is in `pyproject.toml` (line-length = 100, double quotes).
- Type check (strict config in `pyproject.toml`): `mypy src/` (CI allows it to fail with `continue-on-error`).
- Unit tests: `python -m pytest tests/ -v` (CI excludes UI tests with `-k "not test_ui"`).
- UI tests (Linux/Xvfb): `xvfb-run -a python -m pytest tests/test_ui.py -v` (requires `pytest-qt` and a display server).
- Build package: `python -m build` then `python -m twine check dist/*` (CI uses `hatchling` backend).

## Important coding patterns & conventions 💡
- Builder pattern for configs: `ConversionConfigBuilder`, `ContactSheetConfigBuilder`, `BurnInConfig` in `core/config.py`. New features that affect configuration should extend these builders.
- Factories & strategies: `ImageReaderFactory` / color-space strategy classes. Follow existing pattern when adding readers/strategies.
- Input file patterns: supports `%04d`, Houdini `$F4`, and `####` — see sequence parsing in `core/sequence.py` and tests.
- Public API surface: `RenderKit` methods are stability boundary (see `src/renderkit/api/processor.py`). Prefer small, backwards-compatible API changes and update `src/renderkit/__init__.py` if exporting new symbols.
- CLI -> API mapping: CLI (`cli/main.py`) converts arguments into builder calls; mirror that flow when adding options.

## Tests & test style ✳️
- Use `tmp_path` fixtures for temporary files; tests isolate filesystem effects.
- UI tests rely on `pytest-qt`; they exercise widget behavior and QSettings persistence (see `tests/test_ui.py`). Avoid flaking: prefer `qtbot.waitUntil` for async UI waits.
- CI test matrix covers Windows and Ubuntu. When adding tests that require system libs (e.g., OIIO/EXR), add those to CI's apt install step and to `apt-packages.txt` if applicable.

## CI / Packaging notes ⚠️
- CI uses `uv` and `uv.lock`. Mirror CI when changing dependency setup.
- Linux test jobs install system deps (libopenexr-dev, libilmbase-dev, PySide6 for UI tests). If you add platform-specific native dependencies, update CI and `apt-packages.txt` (used for cache keys).
- Formatting & linting are enforced via Ruff in CI: `ruff format --check .` and `ruff check .`.
- Type checks are enforced but allowed to fail in CI; still aim to respect `pyproject.toml` mypy settings.

## Files to inspect when modifying conversion behavior 🔍
- `src/renderkit/core/converter.py` — core conversion orchestration
- `src/renderkit/processing/video_encoder.py` — encoding & CRF logic
- `src/renderkit/io/image_reader.py` — OIIO image IO
- `src/renderkit/core/config.py` — builders & config objects
- `src/renderkit/api/processor.py` — public API adapter
- `src/renderkit/cli/main.py` and `examples/` — for CLI usage examples and expected behavior

## Pull request guidance for agents
- Update or add tests for behavior changes (unit tests or UI tests as needed).
- Run `ruff format .` and `ruff check .` locally before creating PR.
- Keep changes small and focused; update docs in `docs/` and `README.md` for UX/CLI changes.

> Note: CI references `uv.lock` and `apt-packages.txt` for caching and system deps. Be careful when changing OS package requirements — update CI jobs accordingly.

If anything above is ambiguous or you'd like more targeted rules (e.g., how to add a new image reader or encoder), tell me which area to expand and I'll iterate. ✨
