# AGENTS.md — PS-MCP

## Development guidance skills

The following guidance skills (sourced from [EsriPS/agent-skills](https://github.com/EsriPS/agent-skills)) **must be applied on every coding task** in this project. Read and follow them whenever generating, modifying, or reviewing code:

- [`.skills/guidance-best-practices.md`](.skills/guidance-best-practices.md) — Code quality, naming, error handling, security, logging, dependency management
- [`.skills/guidance-testing.md`](.skills/guidance-testing.md) — Proactive test coverage, mocking, test structure, CI integration
- [`.skills/guidance-deployment.md`](.skills/guidance-deployment.md) — Build scripts, containerization, CI/CD, environment config, secrets management
- [`.skills/guidance-documentation.md`](.skills/guidance-documentation.md) — Docstrings, inline comments, README updates, API docs, changelogs

## What this is

A FastMCP (v3) server exposing ArcGIS Enterprise workflows as MCP tools, resources, and prompts. It uses a **plugin-based architecture** — routers and auth providers are separate installable Python packages (wheels) discovered at startup via Python entry points.

For architecture, conventions, build/test workflows, and code style rules, see the steering files in `.kiro/steering/`:

- `project-conventions.md` — Architecture, plugin discovery, key conventions, router/auth patterns, dependencies
- `code-quality.md` — Python style, ruff rules, error handling, security, logging, testing, docs
- `build-and-test.md` — Package manager, test commands, linting, building, releasing, Docker
- `router-development.md` — Router structure, pyproject.toml template, service file pattern, checklist

## CLI quick reference

```bash
psmcp [--env-file <path>] [--config-dir <path>] serve [--transport] [--host] [--port] [--token] [--ssl-keyfile] [--ssl-certfile]
psmcp [--env-file <path>] [--config-dir <path>] router list
psmcp router enable <name>
psmcp router disable <name>
psmcp router install <path-to-whl>
psmcp [--env-file <path>] [--config-dir <path>] build [--outdir] [--include-deps]
```

## Environment configuration

Per-deployment `.env` files live in `env-files/<deployment>/`. The Docker Compose (`compose.yaml`) reads `ENV_FILE` to select one. Key groups:

| Group | Vars | Used by |
|---|---|---|
| Server | `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT`, `ENABLED_ROUTERS`, `LOG_LEVEL`, `MCP_SSL_KEYFILE`, `MCP_SSL_CERTFILE` | `cli.py`, `server.py` |
| Config | `PSMCP_CONFIG_DIR` | `psmcp.core.config` |
| ArcGIS | `ARCGIS_PORTAL_URL`, `ARCGIS_VERIFY_SSL`, `ARCGIS_TOKEN` | `psmcp.core.auth`, all routers |
| ArcGIS Server | `ARCGIS_SERVER_URL` | `psmcp-router-arcgis` |
| Auth (legacy) | `USE_ARCGIS_AUTH`, `MCP_SERVER_BASE_URL` | `psmcp.core.auth.arcgis_provider` |
| Auth (shared) | `ARCGIS_TOKEN_CACHE_TTL` | `psmcp.core.auth.arcgis_verifier` (legacy + OAuth) |
| Auth (OAuth) | `USE_ARCGIS_OAUTH`, `ARCGIS_OAUTH_CLIENT_ID`, `ARCGIS_OAUTH_CLIENT_SECRET`, `MCP_SERVER_BASE_URL` | `psmcp-auth-oauth` |
| LLM / OpenAI | `USE_ARCGIS_LLM`, `OPENAI_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `AZURE_OPENAI`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_DEPLOYMENT` | `psmcp-router-dynamic-app`, `psmcp-router-mongo`, `psmcp-router-postgres` |
| MongoDB | `MONGO_DB_CONN`, `MONGO_DB_NAME`, `CONTEXT_COUNT`, `CANDIDATES_MULTIPLIER`, `EMBEDDING_DEPLOYMENT`, `MONGO_OPENAI_BASE_URL`, `MONGO_OPENAI_API_VERSION` | `psmcp-router-mongo` |
| PostgreSQL | `POSTGRES_DB_CONN`, `POSTGRES_VECTOR_STORE_TABLE`, `POSTGRES_CONTEXT_COUNT`, `POSTGRES_VECTOR_STORE_*`, `POSTGRES_EMBEDDING_DEPLOYMENT`, `POSTGRES_OPENAI_*`, `POSTGRES_TABLES_CONFIG` | `psmcp-router-postgres` |
| Geocoding | `ARCGIS_GEOCODE_SERVICE_URL` | `psmcp-router-location-services` |
| GP filtering | `GP_CATALOG_DEFAULT_TAGS` | `psmcp-router-geoprocessing` |
| Developer Tools | `DEVTOOLS_SKILL_SOURCES`, `DEVTOOLS_SAMPLE_SOURCES`, `GITHUB_TOKEN`, `DEVTOOLS_CACHE_TTL_MINUTES` | `psmcp-router-developer-tools` |

## Workspace packages

| Package | Entry Point Group | Entry Point Name | Description |
|---------|------------------|-----------------|-------------|
| `ps-mcp` | — | — | Server, CLI, shared core |
| `psmcp-router-arcgis` | `psmcp.routers` | `arcgis` | Portal search, item info |
| `psmcp-router-developer-tools` | `psmcp.routers` | `developer_tools` | Skills and code samples from GitHub/local |
| `psmcp-router-dynamic-app` | `psmcp.routers` | `dynamic_app` | MCP Apps map viewer with app-side tools |
| `psmcp-router-feature-service` | `psmcp.routers` | `feature_service` | ArcGIS FeatureServer queries |
| `psmcp-router-geoprocessing` | `psmcp.routers` | `geoprocessing` | GP catalog + task execution |
| `psmcp-router-location-services` | `psmcp.routers` | `location_services` | ArcGIS geocoding |
| `psmcp-router-mongo` | `psmcp.routers` | `mongo` | MongoDB Atlas vector search |
| `psmcp-router-postgres` | `psmcp.routers` | `postgres` | pgvector search via LangChain |
| `psmcp-auth-oauth` | `psmcp.auth` | `arcgis_oauth` | OAuth 2.1 proxy for ArcGIS Online & Enterprise |

## File structure patterns

- Each router's `.md` files (e.g., `feature_service.md`, `geoprocessing_service.md`) are loaded as MCP resources at runtime — they are **not** just docs, they're served to LLM clients.
- `goose_recipes/` contains YAML recipes for the Goose AI agent — not part of the server runtime.
- `Components.md` is a design spec, not generated output.
- `_version.py` files are auto-generated by `hatch-vcs` and gitignored.
- `compose.yaml` is the Docker Compose file (not `docker-compose.yml`).
