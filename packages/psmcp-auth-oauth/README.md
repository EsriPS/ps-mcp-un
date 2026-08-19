# psmcp-auth-oauth

PS-MCP auth plugin: ArcGIS OAuth proxy via FastMCP `OAuthProxy`.

This package is part of the [PS-MCP monorepo](../../README.md). It plugs into a
running PS-MCP server via a `psmcp.auth` entry point and is discovered
automatically once installed. When activated, the server acts as an OAuth 2.1
proxy — MCP clients authenticate using standard OAuth flows while the server
proxies authorization to the upstream ArcGIS identity provider.

**Supports both ArcGIS Online and ArcGIS Enterprise.** The OAuth 2.0 protocol
is identical across both platforms; only the base URL differs.

## Install

```bash
# In the workspace (recommended for development):
uv sync --all-packages

# Or install standalone:
uv pip install psmcp-auth-oauth
```

## Activation

Set `USE_ARCGIS_OAUTH=true` in your environment (or `.env` file) to enable
OAuth proxy mode. The plugin is discovered at server startup via the
`psmcp.auth` entry point group and activates only when this variable is set.

```bash
# Minimal activation
export USE_ARCGIS_OAUTH=true
export ARCGIS_PORTAL_URL=https://www.arcgis.com        # ArcGIS Online
export ARCGIS_OAUTH_CLIENT_ID=your-client-id
export ARCGIS_OAUTH_CLIENT_SECRET=your-client-secret
```

When active, the OAuth proxy takes precedence over the legacy `USE_ARCGIS_AUTH`
token-passthrough mode. If both are set, a warning is logged and OAuth proxy
mode is used.

## Platform Support

### ArcGIS Online

Set `ARCGIS_PORTAL_URL` to your ArcGIS Online organization URL:

| URL Format | Example |
|------------|---------|
| Default org | `https://www.arcgis.com` |
| Custom org subdomain | `https://myorg.maps.arcgis.com` |

OAuth credentials are created in ArcGIS Online by registering an application
item (Settings → App Registration) or via the developer dashboard. Both a
`client_id` and `client_secret` are required for server-side proxy use.

> **Note:** `ARCGIS_VERIFY_SSL` can be left at its default (`True`) for ArcGIS
> Online — Esri's cloud infrastructure always uses valid public TLS certificates.

### ArcGIS Enterprise

Set `ARCGIS_PORTAL_URL` to your portal's base URL:

| URL Format | Example |
|------------|---------|
| Portal with web adaptor | `https://gis.example.com/portal` |
| Portal direct | `https://portal.example.com:7443/arcgis` |

OAuth credentials are created in the Enterprise portal by adding an
"OAuth credentials" item (Content → My Content → New Item → Application).

> **Tip:** Set `ARCGIS_VERIFY_SSL=false` if your Enterprise portal uses
> self-signed TLS certificates.

### URL Normalization

The plugin automatically normalizes `ARCGIS_PORTAL_URL`. All of the following
are equivalent and resolve to the same upstream endpoints:

```
https://www.arcgis.com
https://www.arcgis.com/
https://www.arcgis.com/sharing/rest
https://www.arcgis.com/sharing/rest/
https://gis.example.com/portal
https://gis.example.com/portal/sharing/rest
https://gis.example.com/portal/sharing/rest/oauth2/authorize
```

The plugin strips any trailing `/sharing/rest[/...]` suffix before deriving
OAuth endpoints, so you don't need to worry about the exact format.

## Environment Variables

### Required (when `USE_ARCGIS_OAUTH=true`)

| Variable | Description |
|----------|-------------|
| `USE_ARCGIS_OAUTH` | Set to `"true"` (case-insensitive) to enable OAuth proxy mode. Any other value or absence leaves it disabled. |
| `ARCGIS_PORTAL_URL` | Base URL of the ArcGIS portal or ArcGIS Online organization. Used to derive upstream OAuth endpoints. Trailing slashes and `/sharing/rest` suffixes are stripped automatically. See [Platform Support](#platform-support) for examples. |
| `ARCGIS_OAUTH_CLIENT_ID` | OAuth client ID registered in the ArcGIS portal as an "OAuth credentials" item (Enterprise) or application registration (Online). An empty string is treated as unset. |
| `ARCGIS_OAUTH_CLIENT_SECRET` | OAuth client secret corresponding to the registered client ID. An empty string is treated as unset. |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_BASE_URL` | `http://localhost:8888` | Base URL for constructing OAuth metadata and callback URLs. Trailing slashes are stripped before use. |
| `ARCGIS_VERIFY_SSL` | `"True"` | TLS certificate verification for upstream requests. Set to `"false"` (case-insensitive) to disable verification for self-signed certificates (Enterprise only — ArcGIS Online always uses valid certs). |
| `ARCGIS_TOKEN_CACHE_TTL` | `120` | Cache lifetime in seconds for verified tokens. After a token is successfully verified against the portal, the result is cached in memory to avoid redundant HTTP round-trips on subsequent tool calls. Set to `0` to disable caching entirely. |

### Startup Behavior

If `USE_ARCGIS_OAUTH=true` is set and any of the three required variables
(`ARCGIS_PORTAL_URL`, `ARCGIS_OAUTH_CLIENT_ID`, `ARCGIS_OAUTH_CLIENT_SECRET`)
is missing or empty, the server refuses to start and raises an error message
identifying each missing variable by name.

## How It Works

1. The plugin registers a `psmcp.auth` entry point (`arcgis_oauth`).
2. At server startup, PS-MCP discovers the plugin and calls its factory function.
3. If `USE_ARCGIS_OAUTH=true`, the factory normalizes the portal URL and configures a FastMCP `OAuthProxy` with:
   - Upstream authorization endpoint: `{ARCGIS_PORTAL_URL}/sharing/rest/oauth2/authorize`
   - Upstream token endpoint: `{ARCGIS_PORTAL_URL}/sharing/rest/oauth2/token`
   - PKCE forwarding enabled (S256)
   - `ArcGISTokenVerifier` for upstream token validation
4. MCP clients authenticate via standard OAuth 2.1 (authorization code + PKCE).
5. The proxy issues a JWT to the client containing the encrypted upstream ArcGIS token.
6. On tool calls, `resolve_token()` transparently returns the upstream ArcGIS token.

## OAuth Endpoints (Exposed by the Proxy)

| Endpoint | Description |
|----------|-------------|
| `{MCP_SERVER_BASE_URL}/.well-known/oauth-authorization-server` | OAuth metadata discovery |
| `{MCP_SERVER_BASE_URL}/authorize` | Authorization endpoint |
| `{MCP_SERVER_BASE_URL}/token` | Token endpoint |
| `{MCP_SERVER_BASE_URL}/auth/callback` | OAuth callback (internal) |

## Example `.env` — ArcGIS Online

```env
USE_ARCGIS_OAUTH=true
ARCGIS_PORTAL_URL=https://www.arcgis.com
ARCGIS_OAUTH_CLIENT_ID=AppItemId123
ARCGIS_OAUTH_CLIENT_SECRET=secret456
MCP_SERVER_BASE_URL=https://mcp.example.com
```

## Example `.env` — ArcGIS Enterprise

```env
USE_ARCGIS_OAUTH=true
ARCGIS_PORTAL_URL=https://gis.example.com/portal
ARCGIS_OAUTH_CLIENT_ID=AppItemId123
ARCGIS_OAUTH_CLIENT_SECRET=secret456
MCP_SERVER_BASE_URL=https://mcp.example.com
ARCGIS_VERIFY_SSL=false
```

## Compatibility

- Requires Python >=3.13, <3.14
- Depends on `ps-mcp>=0.1.0,<1.0` (provides `ArcGISTokenVerifier` and FastMCP)
- No additional dependencies beyond what `ps-mcp` already provides
- Works with ArcGIS Online and ArcGIS Enterprise (10.8.1+ for PKCE support)
