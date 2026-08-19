# Contributing to PS-MCP

Thanks for working on PS-MCP! This guide covers the development workflow,
quality bars, and the release process.

## Project layout

```
src/psmcp/                   ← server, CLI, and shared core (psmcp.core.*)
packages/psmcp-router-*/     ← one package per router plugin
tests/                       ← pytest suite
```

The repo is a [`uv` workspace](https://docs.astral.sh/uv/concepts/workspaces/),
so all packages share a single lockfile and resolve cross-package dependencies
from the local source tree.

## Development setup

You need **Python 3.13** and [`uv`](https://docs.astral.sh/uv/).

```bash
# One-shot setup: creates .venv, installs every workspace package editable, dev deps
make install

# Or manually:
uv sync --all-packages --all-extras
```

After install, activate the environment and install the pre-commit hooks:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

```bash
pre-commit install            # register Git hooks (one-time, per clone)
psmcp router list             # should show all six built-in routers
```

> **Note:** `pre-commit install` is per-clone — each developer must run it once
> after cloning. It ensures `ruff` linting, formatting, and file-hygiene checks
> run automatically on every commit.

> **Windows users:** `make` is not installed by default. You can either:
>
> - Install GNU Make via [Chocolatey](https://chocolatey.org/) (`choco install make`)
>   or [winget](https://learn.microsoft.com/en-us/windows/package-manager/) and
>   use the `make` targets as documented.
> - Run the underlying commands directly (see the table below for equivalents).
>
> | Make target | Direct command |
> | --- | --- |
> | `make install` | `uv sync --all-packages --all-extras` |
> | `make test` | `pytest -v` |
> | `make lint` | `ruff check` |
> | `make format` | `ruff format` |
> | `make build` | `psmcp build` |

## Make targets

| Target | What it does |
| --- | --- |
| `make install` | Sync the workspace + dev extras |
| `make test` | Run unit tests (excludes integration) |
| `make test-integration` | Run integration tests against a running server |
| `make test-all` | Run everything |
| `make lint` | `ruff check` |
| `make format` | `ruff format` (in-place) |
| `make build` | `psmcp build` (deployment package) |
| `make tag VERSION=0.2.0` | Tag and push `v0.2.0`, triggering a release |

## Code style

- **Lint/format:** [ruff](https://docs.astral.sh/ruff/). Configuration lives
  in `pyproject.toml` under `[tool.ruff]`.
- **Pre-commit:** install once with `pre-commit install`. Hooks run `ruff`,
  `ruff-format`, and a few sanity checks on every commit.
- **Logging:** call `setup_logging()` only from `psmcp.cli.main()`, after
  `--env-file` has been loaded. Do not initialize logging earlier (for
  example, in `src/psmcp/__main__.py`). Every other module should just do
  `logger = logging.getLogger(__name__)` and use lazy formatting
  (`logger.info("got %d", n)`, never `logger.info(f"got {n}")`).
- **HTTP:** prefer `httpx.AsyncClient` over `requests` for new code.

## Testing

```bash
make test                          # default: unit tests only
make test-integration              # requires a running server (psmcp serve)
pytest tests/test_config.py -v     # individual files
pytest -m integration -v           # only integration tests
```

Add tests alongside any new feature. Keep them deterministic — mock external
services with `httpx.MockTransport` or the fixtures in `tests/conftest.py`.

## Adding a new router

See [`docs/CREATING_A_ROUTER.md`](docs/CREATING_A_ROUTER.md) for the full
guide. The short version:

1. Copy an existing `packages/psmcp-router-*/` as a template.
2. Depend on `"ps-mcp>=X.Y.Z,<X+1"` (matching the current major version).
3. Use `from psmcp.core.auth import resolve_token` (and other helpers from
   `psmcp.core.*`).
4. Declare a `psmcp.routers` entry point in your `pyproject.toml`.
5. Add the package to the workspace by running `uv sync --all-packages`.

## Releasing

PS-MCP uses **tag-driven versioning** with [`hatch-vcs`](https://github.com/ofek/hatch-vcs).
The published version is whatever the latest reachable git tag says it is.

```bash
# 1. Make sure main is green and the changelog is updated.
make test && make lint

# 2. Update CHANGELOG.md: move items from [Unreleased] to a new [X.Y.Z] section.

# 3. Tag and push.
make tag VERSION=0.2.0
# (this runs `git tag v0.2.0 && git push origin v0.2.0`)

# 4. Build the deployment package.
make build
```

Between tags, builds get PEP 440 dev versions like `0.2.0.dev3+g1234abc` —
useful for local testing but not for distribution.

### Versioning rules

See [CHANGELOG.md](CHANGELOG.md#versioning-policy) for what bumps each
component. In short: breaking imports/CLI = major, new features = minor,
fixes = patch.

## Reporting issues / security

- Bugs and feature requests: open a GitHub issue.
- Security vulnerabilities: see [`SECURITY.md`](SECURITY.md).

