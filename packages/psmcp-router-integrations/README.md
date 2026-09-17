# psmcp-router-integrations

PS-MCP router plugin: ArcGIS Utility Network integration transform and mapping tools.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a running
PS-MCP server via a `psmcp.routers` entry point and provides field-mapping validation and
subnetwork-export transformation primitives used by the Integrations agent.

## Install

```bash
uv pip install psmcp-router-integrations
```

Or, in the workspace:

```bash
uv sync --all-packages
```

## Environment Variables

This router operates on exported JSON files and mapping definitions; it does not
require a live ArcGIS connection for transformation, but shares the monorepo's
standard ArcGIS environment variables when a connection is needed.

| Variable | Required | Description |
|----------|----------|-------------|
| `ARCGIS_PORTAL_URL` | No | Portal URL for GIS connection. |
| `ARCGIS_TOKEN` | No | ArcGIS token. Resolved via `resolve_token()`. |
| `ARCGIS_VERIFY_SSL` | No | Set to `"false"` for self-signed certificates. Default: `"True"`. |

## Dependencies

- `ps-mcp>=0.1.0,<1.0` — shared core (token resolution, logging)
- `arcgis>=2.4,<3` — ArcGIS API for Python

## Development

See the repo-level [README](../../README.md) and
[docs/CREATING_A_ROUTER.md](../../docs/CREATING_A_ROUTER.md) for the broader router
development workflow.
