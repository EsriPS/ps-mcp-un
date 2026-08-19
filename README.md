# PS-MCP

PS-MCP is a [FastMCP](https://gofastmcp.com) (v3) server for ArcGIS-first
workflows. It bundles ArcGIS portal tools, geoprocessing task discovery /
execution, feature-service querying, address geocoding, and optional
MongoDB / PostgreSQL vector search behind pluggable router packages.

Each router is a separate installable Python wheel discovered at startup via
Python entry points. Install only the routers you need, or install them all.

## Quick start

```bash
# 1. Clone, set up Python 3.13 + uv
uv sync --all-packages --all-extras    # or: make install

# 2. Configure
cp .env.sample .env                    # edit with your portal URL, tokens, etc.

# 3. Run
source .venv/bin/activate              # Windows: .venv\Scripts\Activate.ps1
psmcp serve                            # http on 0.0.0.0:8888
```

Default endpoints:

- Server: `http://localhost:8888`
- Health check: `http://localhost:8888/health`

CLI shortcuts:

```bash
psmcp serve --transport stdio          # stdio mode for desktop MCP clients
psmcp serve --token <arcgis-token>     # inject an ArcGIS token
psmcp --env-file .env serve            # load env file at startup
psmcp --config-dir /path serve         # override routers.json location
```

### Or run with Docker

```bash
docker compose up --build
```

## Architecture

```
src/psmcp/                   ← server, CLI, and shared core utilities
├── core/                    ← psmcp.core.* — shared library used by all routers
│   ├── auth/                ← resolve_token + ArcGIS auth provider/verifier
│   ├── config.py            ← config dir + routers.json management
│   └── utils.py             ← logging setup
├── cli.py                   ← `psmcp` command implementation
├── server.py                ← root FastMCP instance + plugin discovery
└── __main__.py              ← entry point for `python -m psmcp`

packages/psmcp-router-*/     ← one independent package per router plugin
```

The `psmcp` package is a single wheel containing the server, the CLI, and the
shared `psmcp.core` utilities. Routers depend on `ps-mcp>=0.1.0,<1.0` and
import from `psmcp.core.*` — there is no separate `psmcp-core` package.

## Router management

Routers register themselves via the `psmcp.routers` Python entry point. The
server discovers them automatically.

```bash
psmcp router list                      # see what's installed + enabled
psmcp router enable <name>             # update routers.json
psmcp router disable <name>
psmcp router install <path-to-whl>     # pip install + auto-enable (dev)
```

Built-in routers:

| Router | Package | What it covers |
|---|---|---|
| `arcgis` | `psmcp-router-arcgis` | Portal search, item inspection, group lookup, system GP discovery, MCP App map rendering |
| `feature_service` | `psmcp-router-feature-service` | Feature layer queries, service / layer metadata, sample feature retrieval |
| `geoprocessing` | `psmcp-router-geoprocessing` | GP service / task discovery, schema inspection, sync + async job execution |
| `location_services` | `psmcp-router-location-services` | Address geocoding with ArcGIS candidate results |
| `mongo` | `psmcp-router-mongo` | MongoDB Atlas vector search, collection / index inspection |
| `postgres` | `psmcp-router-postgres` | PostgreSQL pgvector search, sample lookup, schema inspection |

### Controlling which routers are active

Priority order:

1. **`ENABLED_ROUTERS` env var** (comma-separated) — overrides everything.
2. **`routers.json`** in the config dir — managed by `psmcp router enable/disable`.
3. **All discovered routers** — default when neither is set.

Config directory resolution: `--config-dir` flag → `PSMCP_CONFIG_DIR` env var
→ `.psmcp/` in CWD → `~/.psmcp/`.

For a minimal ArcGIS-focused setup:

```dotenv
ENABLED_ROUTERS=arcgis,feature_service,geoprocessing,location_services
```

## Versioning

PS-MCP uses **tag-driven versioning** via [`hatch-vcs`](https://github.com/ofek/hatch-vcs).
The version of `ps-mcp` and every router package in the monorepo is derived
from the latest reachable git tag (e.g. `v0.1.0`). All packages share the
same version on every release.

Routers in this repo pin `ps-mcp>=X.Y.Z,<X+1` so a major-version bump fails
loudly downstream until they're updated. See [CHANGELOG.md](CHANGELOG.md) for
the SemVer policy and [CONTRIBUTING.md](CONTRIBUTING.md) for the release flow.

## Configuration at a glance

Server-wide settings (`.env`):

- `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `ENABLED_ROUTERS`, `LOG_LEVEL`
- `PSMCP_CONFIG_DIR` — override config directory location

Common ArcGIS settings (used by `psmcp.core.auth` and most routers):

- `ARCGIS_PORTAL_URL`, `ARCGIS_VERIFY_SSL`, `USE_ARCGIS_AUTH`, `ARCGIS_TOKEN`
- `MCP_SERVER_BASE_URL` — public base URL when using `ArcGISAuthProvider`

Vector-search routers need extra database and Azure OpenAI settings. See each
router package's `README.md`.

## Testing

```bash
make test                              # unit tests (default)
make test-integration                  # requires a running server
make test-all                          # everything

pytest tests/test_config.py -v         # individual files
pytest -m integration -v               # only integration tests
```

| Test file | What it covers |
|---|---|
| `test_config.py` | Config dir resolution, routers.json CRUD, corrupt file handling |
| `test_discovery.py` | Entry-point discovery, enablement priority logic |
| `test_router_imports.py` | Router / core package imports, `resolve_token`, `__version__` |
| `test_cli.py` | CLI subprocess tests (help, list, enable/disable) |
| `test_resources.py` | Integration test — requires a running server |

## Notes

- Health route at `/health`, registered in `server._init_server()`.
- Router loading is dynamic via entry points — no hardcoded registry.
- ArcGIS tokens can be supplied explicitly to tools, resolved from the FastMCP
  auth context, or set globally with `--token` / `ARCGIS_TOKEN`.
- Optional ArcGIS map HTML generation can use OpenAI / Azure OpenAI settings
  when `USE_ARCGIS_LLM=true`.

## Deployment

PS-MCP is designed to be deployed via pre-built wheel packages. Build a
deployment archive on a development machine and transfer it to the target:

```bash
psmcp build                            # or: make build
psmcp build --include-deps             # include third-party deps for offline installs
```

The resulting `.tar.gz` archive contains wheels, install scripts
(`install.sh` / `install.ps1`), config, and an `.env.sample`. On the target:

```bash
tar xzf ps-mcp-deploy-*.tar.gz && cd ps-mcp-deploy-*/
./install.sh /opt/ps-mcp               # Linux / macOS
# .\install.ps1 -InstallDir C:\ps-mcp  # Windows
```

| Method | Docs |
|---|---|
| **Deployment package** | `psmcp build` (or `make build`) — builds wheels + config + install scripts into a `.tar.gz` |
| **Linux systemd service** | [`deploy/LINUX_DEPLOYMENT.md`](deploy/LINUX_DEPLOYMENT.md) |
| **Windows (NSSM service)** | [`deploy/WINDOWS_DEPLOYMENT.md`](deploy/WINDOWS_DEPLOYMENT.md) |
| **Docker (from wheels)** | [`deploy/DOCKER_QUICKREF.md`](deploy/DOCKER_QUICKREF.md) |

## Development

```bash
# Install all packages + dev extras (pytest, ruff, pre-commit, etc.)
uv sync --all-packages --extra dev
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full developer workflow
(workspace setup, lint/format, test, release flow). For details on building
your own router plugin, see
[**Creating a Custom Router**](docs/CREATING_A_ROUTER.md).

Project conventions and architecture notes for AI agents live in
[`AGENTS.md`](AGENTS.md).
