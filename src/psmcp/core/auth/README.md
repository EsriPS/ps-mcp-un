# Auth module

The `auth/` package contains the shared ArcGIS authentication pieces used across the server. It is not mounted as its own router, but it provides the token provider, token verifier, and token-resolution helper that the ArcGIS-facing modules rely on.

## Components

- `resolve_token` — shared helper that resolves a token in this order:
  1. explicit `token` argument
  2. FastMCP auth context
  3. `ARCGIS_TOKEN` environment variable
- `ArcGISAuthProvider` — FastMCP remote auth provider for ArcGIS Enterprise
- `ArcGISTokenVerifier` — validates ArcGIS tokens against the portal and maps claims/scopes into FastMCP access tokens

## Configuration

- `USE_ARCGIS_AUTH`
- `ARCGIS_PORTAL_URL`
- `ARCGIS_VERIFY_SSL`
- `MCP_SERVER_BASE_URL`
- `ARCGIS_TOKEN`

## Notes

- When `USE_ARCGIS_AUTH == "True"`, the server (`__main__.py`) enables `ArcGISAuthProvider`.
- The provider adds auth helper routes, including `/auth/arcgis/token-info` and `/auth/arcgis/portal-info`.
- Even when the auth provider is disabled, ArcGIS tools can still use a token supplied directly or via `ARCGIS_TOKEN`.

## Related docs

- [`ARCGIS_AUTH.md`](ARCGIS_AUTH.md)
