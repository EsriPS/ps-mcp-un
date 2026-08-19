# PS-MCP Project Conventions

This project is a FastMCP v3 server exposing ArcGIS Enterprise workflows as MCP tools, resources, and prompts. It uses a plugin-based architecture where routers and auth providers are separate installable Python packages discovered at startup via entry points.

---

## Architecture

```
src/psmcp/              → main installable wheel (ps-mcp)
  cli.py                → CLI entry point (serve, router, build subcommands)
  server.py             → root FastMCP, plugin discovery, mounting
  core/                 → shared utilities
    auth/               → token resolution, ArcGIS auth provider, OAuth verifier
    config.py           → config dir + routers.json management
    utils.py            → logging setup

packages/psmcp-router-* → each router is an independent uv-workspace member
packages/psmcp-auth-*   → auth plugins (e.g., psmcp-auth-oauth)
```

There is no separate `psmcp-core` package. All shared utilities live inside the `ps-mcp` wheel under `psmcp.core.*`. Routers depend on `ps-mcp>=0.1.0,<1.0`.

---

## Plugin Discovery

Two entry-point groups are used for plugin discovery:

| Group | Purpose | Example |
|-------|---------|---------|
| `psmcp.routers` | Router plugins (tools/resources/prompts) | `arcgis = "psmcp_router_arcgis:arcgis_router"` |
| `psmcp.auth` | Auth provider plugins | `arcgis_oauth = "psmcp_auth_oauth:create_auth_provider"` |

Auth plugin priority: `psmcp.auth` plugin → `USE_ARCGIS_AUTH=True` → no auth.

---

## Key Conventions

### Token Resolution

Every tool accepts an optional `token` param. Always use:

```python
from psmcp.core.auth import resolve_token
```

It checks: explicit param → FastMCP auth context (`get_access_token()`) → `ARCGIS_TOKEN` env var.

### HTTP Clients

Use `httpx.AsyncClient` for async REST calls. Never use `requests` in new code.

> Note: `psmcp-router-arcgis` still has a legacy `requests` dependency. New routers must use `httpx`.

### Logging

- Initialize logging via `setup_logging()` only in `psmcp.cli.main()`.
- All other modules: `logger = logging.getLogger(__name__)`.
- Use lazy formatting: `logger.info("got %d items", n)` — never f-strings in log calls.

### Config from Environment

- Module-level constants read `os.getenv(...)` at import time.
- No Pydantic settings model. The CLI `--env-file` flag loads `.env` via `python-dotenv`.

### SSL Verification

ArcGIS-facing modules may read `ARCGIS_VERIFY_SSL` (default `"True"`). Set to `"false"` only for self-signed ArcGIS Enterprise installs.

### SSL/TLS for the Server

The server supports HTTPS via `--ssl-keyfile` and `--ssl-certfile` CLI flags (or `MCP_SSL_KEYFILE` / `MCP_SSL_CERTFILE` env vars). Both must be set for SSL to activate.

### Versioning

Tag-driven via `hatch-vcs`. Never hand-edit a version. `git tag vX.Y.Z` is the source of truth. Between tags, `__version__` is a PEP 440 dev string. All packages in the monorepo share the same version derived from the repo's git tags.

### Import Names

Each router uses a separate top-level import name (e.g., `psmcp_router_feature_service`), not a namespace package under `psmcp`. Auth plugins follow the same pattern (e.g., `psmcp_auth_oauth`).

---

## Code Style

- Python 3.13 required.
- Formatter/linter: `ruff` (v0.15.12), configured in `pyproject.toml`.
- Line length: 100 characters.
- Quote style: double quotes.
- Indent: spaces.
- Line endings: LF.
- Type hints on all function signatures.
- Pre-commit hooks enforce formatting and linting on every commit.

---

## Router Pattern

1. Create `FastMCP(name="...")` instance in the service file.
2. Decorate functions with `@router.tool`, `@router.resource`, or `@router.prompt`.
3. Export the router from `__init__.py`.
4. Declare an entry point in `pyproject.toml`:
   ```toml
   [project.entry-points."psmcp.routers"]
   my_router = "psmcp_router_my_router:my_router"
   ```
5. Document env vars in the router's `README.md`.

---

## Auth Plugin Pattern

1. Create a factory function that returns an auth provider (or `None` to skip).
2. Export the factory from `__init__.py`.
3. Declare an entry point:
   ```toml
   [project.entry-points."psmcp.auth"]
   my_auth = "psmcp_auth_my_auth:create_auth_provider"
   ```

---

## Dependencies

- Use `uv` as the package manager. Single lockfile (`uv.lock`) across the monorepo.
- Pin versions in `pyproject.toml`. The lockfile handles exact resolution.
- Minimize new dependencies. Prefer the standard library when possible.
- All routers and auth plugins depend on `ps-mcp>=0.1.0,<1.0`.

### Current Workspace Members

| Package | Entry Point Name | Description |
|---------|-----------------|-------------|
| `psmcp-router-arcgis` | `arcgis` | Portal search, item info |
| `psmcp-router-developer-tools` | `developer_tools` | Skills and code samples from GitHub/local |
| `psmcp-router-dynamic-app` | `dynamic_app` | MCP Apps map viewer with app-side tools |
| `psmcp-router-feature-service` | `feature_service` | ArcGIS FeatureServer queries |
| `psmcp-router-geoprocessing` | `geoprocessing` | GP catalog + task execution |
| `psmcp-router-location-services` | `location_services` | ArcGIS geocoding |
| `psmcp-router-mongo` | `mongo` | MongoDB Atlas vector search |
| `psmcp-router-postgres` | `postgres` | pgvector search via LangChain |
| `psmcp-auth-oauth` | `arcgis_oauth` | OAuth 2.1 proxy for ArcGIS |
