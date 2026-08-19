"""PS-MCP Auth Plugin: ArcGIS OAuth Proxy (Online & Enterprise)."""

from psmcp_auth_oauth.provider import (
    ArcGISOAuthConfigError,
    create_auth_provider,
    normalize_portal_url,
)

try:
    from psmcp_auth_oauth._version import __version__
except ImportError:
    __version__ = "0.0.0+unknown"

__all__ = ["ArcGISOAuthConfigError", "__version__", "create_auth_provider", "normalize_portal_url"]
