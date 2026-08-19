# Build and Test Workflows

## Package Manager

This is a `uv` workspace. A single `uv sync` resolves and installs every package (root + all routers + auth plugins).

```bash
# Full workspace install (editable, all extras + dependency groups)
make install
# or equivalently:
uv sync --all-packages --all-extras --all-groups
```

> **Note:** `--all-groups` is required to install dependency-group packages like `hypothesis`.
> Without it, only `[project.optional-dependencies]` extras are installed.

---

## Running Tests

Tests use **pytest** with `pytest-asyncio` (auto mode). Integration tests are excluded by default. Property-based testing uses **hypothesis**.

```bash
make test                  # unit tests only (default)
make test-integration      # integration tests (require running server)
make test-all              # everything
make coverage              # unit tests + coverage report (term + htmlcov/)
```

Raw invocations:

```bash
uv run pytest              # unit tests
uv run pytest -m integration -v   # integration only
```

### pytest configuration (`pytest.ini`)

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
markers =
    integration: tests that require a running server or external services
filterwarnings =
    ignore::DeprecationWarning:authlib
addopts =
    -m "not integration"
    --strict-markers
```

### Test markers

- `@pytest.mark.integration` — requires a running PS-MCP server on `http://localhost:8888/mcp`.
- All other tests run without external dependencies.

### Test fixtures (conftest.py)

- `tmp_config_dir` — temporary config directory for isolated config tests (sets `PSMCP_CONFIG_DIR`).
- `clean_env` — clears PS-MCP-related env vars for the test scope.
- `fake_router_entry_points` — factory for monkeypatching `importlib.metadata.entry_points`.

### Dev dependencies

Declared in `[project.optional-dependencies].dev`:
- `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-cov>=5.0` — test runner
- `respx>=0.21` — httpx mocking
- `ruff==0.15.12` — lint/format
- `pre-commit>=3.5` — git hooks

Declared in `[dependency-groups].dev` (requires `--all-groups`):
- `hypothesis>=6.100` — property-based testing

---

## Linting and Formatting

```bash
make lint      # ruff check .
make format    # ruff format . (in-place)
```

Pre-commit hooks run `ruff --fix` and `ruff-format` automatically on staged files. Install once:

```bash
pre-commit install
```

Additional pre-commit checks: `check-toml`, `check-yaml`, `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending` (enforces LF).

---

## Building

```bash
make build     # creates deployment package via psmcp CLI
```

The `psmcp build` command produces a self-contained deployment directory in `dist/` with wheels, install scripts, config, and a `.tar.gz` archive.

Options:

```bash
psmcp build --outdir /tmp/deploy       # custom output directory
psmcp build --include-deps             # download third-party deps for offline install
psmcp --env-file .env build            # load env to determine enabled routers
psmcp --config-dir /path/to/config build  # use specific routers.json
```

The build command:
1. Builds wheels for all enabled routers + the server package.
2. Copies `.env.sample` and `routers.json` config.
3. Generates `install.sh` (Linux/macOS) and `install.ps1` (Windows) scripts.
4. Creates a `.tar.gz` archive of the deployment directory.

---

## Releasing

Tag-driven via `hatch-vcs`. Never edit version strings manually.

```bash
# 1. Update CHANGELOG.md ([Unreleased] → [X.Y.Z])
# 2. Tag and push
make tag VERSION=0.2.0
# 3. Build artifacts
make build
```

---

## Cleanup

```bash
make clean     # removes dist/, build/, caches, __pycache__, .egg-info
```

---

## Docker

```bash
docker compose up --build
```

- Compose file: `compose.yaml`
- Base image: `python:3.13.12-slim-trixie`
- Uses `ENV_FILE` variable to select a deployment `.env` (defaults to `.env`).
- Uses `IMAGE_TAG` variable for image tagging (defaults to `latest`).
- Per-deployment env files live in `env-files/<deployment>/`.
- Health check: `GET /health` on the configured port.
- Runs as non-root user (`mcp`, UID 1000).
- Uses `uv sync --all-packages --frozen --no-dev` for reproducible installs.
