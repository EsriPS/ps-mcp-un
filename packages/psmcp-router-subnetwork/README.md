# psmcp-router-subnetwork

PS-MCP router plugin: ArcGIS Utility Network subnetwork update and export tools.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a running
PS-MCP server via a `psmcp.routers` entry point and provides subnetwork listing,
update (recompute), and JSON export primitives used by the SubNetwork agent and the
backend export scheduler.

## Install

```bash
uv pip install psmcp-router-subnetwork
```

Or, in the workspace:

```bash
uv sync --all-packages
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `UTILITY_NETWORK_URL` | Yes | FeatureServer URL of the utility network service. |
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
