# ArcGIS Enterprise Authentication for FastMCP

Authenticate MCP server users against an external ArcGIS Enterprise Portal.

## Overview

The `ArcGISAuthProvider` integrates with FastMCP's authentication system to:

- **Validate Tokens**: Verify ArcGIS Enterprise tokens against your Portal
- **Extract User Info**: Retrieve username, role, organization, and privileges
- **Map Scopes**: Convert ArcGIS roles to OAuth-style scopes
- **Expose Discovery Endpoints**: Provide OAuth 2.0 Protected Resource metadata

## Quick Start

### 1. Configure Environment Variables

```bash
# .env file

# Required: Your ArcGIS Enterprise Portal URL
ARCGIS_PORTAL_URL=https://your-portal.example.com/portal

# Required: Enable ArcGIS authentication
USE_ARCGIS_AUTH=True

# Optional: SSL verification (default: True)
ARCGIS_VERIFY_SSL=True

# Optional: Your MCP server's public URL (for OAuth discovery)
MCP_SERVER_BASE_URL=http://localhost:8888
```

### 2. Start the Server

```bash
python -m psmcp
```

You'll see in the logs:
```
ArcGIS Enterprise authentication enabled
ArcGIS Auth Provider initialized for portal: https://your-portal.example.com/portal
```

## How It Works

### Authentication Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  MCP Client │────▶│  MCP Server  │────▶│ ArcGIS Portal   │
│             │     │  (FastMCP)   │     │                 │
│ 1. Get token│     │              │     │                 │
│    from     │◀────│              │◀────│ 2. Validate     │
│    Portal   │     │              │     │    token        │
│             │     │              │     │                 │
│ 3. Call MCP │────▶│ 4. Check     │     │                 │
│    tool     │     │    auth      │     │                 │
│    with     │     │              │     │                 │
│    Bearer   │◀────│ 5. Return    │     │                 │
│    token    │     │    result    │     │                 │
└─────────────┘     └──────────────┘     └─────────────────┘
```

### Token Validation Process

1. Client sends request with `Authorization: Bearer <token>` header
2. `ArcGISTokenVerifier` calls Portal's `/sharing/rest/portals/self` endpoint
3. If valid, fetches user details from `/sharing/rest/community/self`
4. Creates `AccessToken` with user claims and mapped scopes
5. Tool can access user info via `get_access_token()`

## Client Usage

### Obtaining a Token

Get a token from your ArcGIS Enterprise Portal using one of these methods:

**Option 1: Portal Token Generator UI**
```
https://<your-portal>/sharing/rest/generateToken
```

**Option 2: ArcGIS Python API**
```python
from arcgis.gis import GIS

gis = GIS("https://your-portal.example.com/portal", "username", "password")
token = gis._con.token
```

**Option 3: REST API**
```bash
curl -X POST "https://your-portal/sharing/rest/generateToken" \
  -d "username=your_user" \
  -d "password=your_pass" \
  -d "referer=https://your-app.com" \
  -d "f=json"
```

### Calling MCP Tools

**Python with FastMCP Client**
```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

token = "your-arcgis-enterprise-token"

async with Client(
    transport=StreamableHttpTransport(
        "http://localhost:8888/mcp",
        headers={"Authorization": f"Bearer {token}"}
    )
) as client:
    result = await client.call_tool("your_tool_name", {"arg": "value"})
    print(result)
```

**Using curl**
```bash
curl -X POST http://localhost:8888/mcp \
  -H "Authorization: Bearer YOUR_ARCGIS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "tool_name", "arguments": {}}}'
```

## Accessing User Info in Tools

Use FastMCP's `get_access_token()` dependency to access the authenticated user:

```python
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

mcp = FastMCP(name="my-server")

@mcp.tool
async def whoami() -> dict:
    """Return information about the authenticated user."""
    token = get_access_token()
    
    if token is None:
        return {"authenticated": False, "error": "No valid token provided"}
    
    return {
        "authenticated": True,
        "username": token.claims.get("username"),
        "fullName": token.claims.get("fullName"),
        "email": token.claims.get("email"),
        "role": token.claims.get("role"),
        "organization": token.claims.get("orgId"),
        "scopes": token.scopes,
    }

@mcp.tool
async def admin_only_tool() -> dict:
    """A tool that requires admin privileges."""
    token = get_access_token()
    
    if token is None:
        return {"error": "Authentication required"}
    
    if "admin" not in token.scopes:
        return {"error": "Admin privileges required"}
    
    # Perform admin operation...
    return {"success": True}
```

### Available User Claims

| Claim | Type | Description |
|-------|------|-------------|
| `sub` | `str` | Subject identifier (same as username) |
| `username` | `str` | ArcGIS username |
| `fullName` | `str` | User's display name |
| `email` | `str` | User's email address |
| `role` | `str` | ArcGIS role: `org_admin`, `org_publisher`, `org_user` |
| `orgId` | `str` | Organization ID |
| `privileges` | `list[str]` | List of ArcGIS privilege strings |
| `portal_url` | `str` | Portal URL used for authentication |

### Scope Mapping

ArcGIS roles are automatically mapped to OAuth-style scopes:

| ArcGIS Role | Mapped Scopes |
|-------------|---------------|
| `org_admin` | `read`, `write`, `admin`, `manage` |
| `org_publisher` | `read`, `write`, `publish` |
| `org_user` | `read`, `write` |

Additional scopes are derived from privileges (e.g., `create`, `delete`, `update`).

## API Endpoints

The auth provider adds these endpoints to your MCP server:

### GET `/auth/arcgis/portal-info`

Returns Portal configuration (no authentication required).

```bash
curl http://localhost:8888/auth/arcgis/portal-info
```

Response:
```json
{
  "portal_url": "https://your-portal.example.com/portal",
  "auth_type": "arcgis-enterprise",
  "token_endpoint": "https://your-portal.example.com/portal/sharing/rest/generateToken",
  "oauth_authorize": "https://your-portal.example.com/portal/sharing/rest/oauth2/authorize"
}
```

### POST `/auth/arcgis/token-info`

Validates a token and returns user details.

```bash
curl -X POST http://localhost:8888/auth/arcgis/token-info \
  -H "Content-Type: application/json" \
  -d '{"token": "YOUR_ARCGIS_TOKEN"}'
```

Success Response (200):
```json
{
  "valid": true,
  "client_id": "org_id_here",
  "scopes": ["read", "write", "publish"],
  "claims": {
    "sub": "jsmith",
    "username": "jsmith",
    "fullName": "John Smith",
    "email": "jsmith@example.com",
    "role": "org_publisher",
    "orgId": "org_id_here",
    "privileges": ["portal:user:createItem", "..."],
    "portal_url": "https://your-portal.example.com/portal"
  }
}
```

Error Response (401):
```json
{
  "error": "Invalid or expired token"
}
```

## Advanced Configuration

### Programmatic Setup

Configure the auth provider directly in code instead of using environment variables:

```python
from fastmcp import FastMCP
from auth import ArcGISAuthProvider

auth = ArcGISAuthProvider(
    portal_url="https://your-portal.example.com/portal",
    verify_ssl=True,
    base_url="https://your-mcp-server.com"
)

mcp = FastMCP(
    name="my-mcp-server",
    auth=auth
)
```

### Direct Verifier Usage

Use the token verifier directly for custom authentication flows:

```python
from auth import ArcGISTokenVerifier

verifier = ArcGISTokenVerifier(
    portal_url="https://your-portal.example.com/portal",
    verify_ssl=True
)

# Validate a token
access_token = await verifier.verify_token("some-arcgis-token")
if access_token:
    print(f"Valid token for user: {access_token.claims['username']}")
else:
    print("Invalid token")
```

## Security Best Practices

### Production Checklist

- [ ] Enable SSL verification: `ARCGIS_VERIFY_SSL=True`
- [ ] Use HTTPS for your MCP server
- [ ] Set appropriate token expiration in ArcGIS Portal
- [ ] Restrict Portal access to necessary users
- [ ] Monitor authentication logs for suspicious activity

### Token Security

- Tokens are validated on every request
- Expired tokens are automatically rejected
- Token values are not logged (only validation results)
- Network calls to Portal use configurable SSL verification

## Troubleshooting

### "ArcGIS Portal URL is required"

The `ARCGIS_PORTAL_URL` environment variable is not set or empty.

```bash
# Check your .env file
cat .env | grep ARCGIS_PORTAL_URL

# Or set it directly
export ARCGIS_PORTAL_URL=https://your-portal.example.com/portal
```

### Token Validation Fails

1. **Check token expiration**: Generate a fresh token
2. **Verify Portal URL**: Ensure the URL is correct and accessible
   ```bash
   curl "https://your-portal/sharing/rest/info?f=json"
   ```
3. **Check SSL settings**: If using self-signed certs, set `ARCGIS_VERIFY_SSL=False`
4. **Review logs**: Check server logs for detailed error messages

### Connection Errors

1. **Network access**: Ensure the MCP server can reach the Portal
   ```bash
   curl -I https://your-portal.example.com/portal/sharing/rest/info
   ```
2. **Firewall rules**: Allow outbound HTTPS (443) to Portal
3. **VPN requirements**: Connect to VPN if Portal is on internal network

### "Authentication required" in Tools

The client is not sending the `Authorization` header correctly.

```python
# Correct format
headers={"Authorization": f"Bearer {token}"}

# NOT these:
headers={"Authorization": token}  # Missing "Bearer "
headers={"Token": token}          # Wrong header name
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ARCGIS_PORTAL_URL` | Yes | — | Full URL to ArcGIS Enterprise Portal |
| `USE_ARCGIS_AUTH` | Yes | `False` | Set to `True` to enable authentication |
| `ARCGIS_VERIFY_SSL` | No | `True` | Verify SSL certificates |
| `MCP_SERVER_BASE_URL` | No | `http://localhost:8888` | Public URL of your MCP server |

## Architecture

```
auth/
├── __init__.py           # Exports: ArcGISAuthProvider, ArcGISTokenVerifier
├── arcgis_provider.py    # FastMCP auth provider (extends RemoteAuthProvider)
├── arcgis_verifier.py    # Token validation logic
└── ARCGIS_AUTH.md        # This documentation
```

### Key Classes

**`ArcGISAuthProvider`** (`arcgis_provider.py`)
- Extends FastMCP's `RemoteAuthProvider`
- Integrates with FastMCP's OAuth system
- Adds `/auth/arcgis/*` endpoints

**`ArcGISTokenVerifier`** (`arcgis_verifier.py`)
- Validates tokens against Portal REST API
- Extracts user information
- Maps roles to scopes
- Returns FastMCP `AccessToken` objects
