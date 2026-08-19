"""ArcGIS OAuth proxy plugin for PS-MCP.

Supports both ArcGIS Online and ArcGIS Enterprise as the upstream identity
provider. The OAuth 2.0 endpoints are identical across both platforms — only
the base URL differs.
"""

from __future__ import annotations

import logging
import os
import re

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.oauth_proxy import OAuthProxy

from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

logger = logging.getLogger(__name__)

# Regex to strip a trailing /sharing/rest[/...] suffix that users may
# accidentally include in ARCGIS_PORTAL_URL.  The code appends
# /sharing/rest/oauth2/... itself, so we need just the portal root.
_SHARING_REST_SUFFIX_RE = re.compile(r"/sharing/rest(?:/.*)?$", re.IGNORECASE)


class ArcGISOAuthConfigError(Exception):
    """Raised when required OAuth proxy configuration is missing."""


class ArcGISOAuthProxy(OAuthProxy):
    """OAuthProxy subclass that respects ARCGIS_VERIFY_SSL for upstream calls."""

    def __init__(self, *, verify_ssl: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self._verify_ssl = verify_ssl

    def _create_upstream_oauth_client(self) -> AsyncOAuth2Client:
        """Create upstream OAuth client with configurable SSL verification."""
        return AsyncOAuth2Client(
            client_id=self._upstream_client_id,
            client_secret=(
                self._upstream_client_secret.get_secret_value()
                if self._upstream_client_secret is not None
                else None
            ),
            token_endpoint_auth_method=self._token_endpoint_auth_method,
            timeout=30,
            verify=self._verify_ssl,
        )


def normalize_portal_url(url: str) -> str:
    """Normalize a portal URL to its root, stripping any /sharing/rest suffix.

    Users may provide URLs in various forms:
        - https://www.arcgis.com
        - https://www.arcgis.com/sharing/rest
        - https://org.maps.arcgis.com/sharing/rest/
        - https://portal.example.com/portal
        - https://portal.example.com/portal/sharing/rest/oauth2/authorize

    This function strips trailing slashes and any ``/sharing/rest[/...]``
    suffix so the result is always the portal root suitable for appending
    ``/sharing/rest/oauth2/...``.

    Args:
        url: Raw portal URL from environment or configuration.

    Returns:
        Normalized portal root URL without trailing slash.
    """
    url = url.strip().rstrip("/")
    url = _SHARING_REST_SUFFIX_RE.sub("", url)
    return url.rstrip("/")


def create_auth_provider() -> AuthProvider | None:
    """Auth plugin factory: create an OAuthProxy for ArcGIS Online or Enterprise.

    Returns None if USE_ARCGIS_OAUTH is not enabled, allowing the server
    to fall through to other auth modes. Raises ArcGISOAuthConfigError if
    enabled but misconfigured.

    The upstream portal URL is normalized automatically — users can provide
    the bare portal root (``https://www.arcgis.com``) or a longer path
    including ``/sharing/rest``; both are handled correctly.

    Returns:
        Configured OAuthProxy instance, or None if not activated.

    Raises:
        ArcGISOAuthConfigError: If USE_ARCGIS_OAUTH=True but required
            environment variables are missing.
    """
    use_oauth = os.getenv("USE_ARCGIS_OAUTH", "").strip().lower()
    if use_oauth != "true":
        return None

    portal_url = os.getenv("ARCGIS_PORTAL_URL", "").strip()
    client_id = os.getenv("ARCGIS_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("ARCGIS_OAUTH_CLIENT_SECRET", "").strip()
    default_base_url = "http://localhost:8888"
    raw_base_url = os.getenv("MCP_SERVER_BASE_URL")
    if raw_base_url is None:
        base_url = default_base_url
    else:
        base_url = raw_base_url.strip().rstrip("/") or default_base_url

    missing: list[str] = []
    if not portal_url:
        missing.append("ARCGIS_PORTAL_URL")
    if not client_id:
        missing.append("ARCGIS_OAUTH_CLIENT_ID")
    if not client_secret:
        missing.append("ARCGIS_OAUTH_CLIENT_SECRET")

    if missing:
        raise ArcGISOAuthConfigError(
            f"OAuth proxy mode requires the following environment variables: {', '.join(missing)}"
        )

    portal_url = normalize_portal_url(portal_url)
    verify_ssl = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"

    token_verifier = ArcGISTokenVerifier(
        portal_url=portal_url,
        verify_ssl=verify_ssl,
    )

    proxy = ArcGISOAuthProxy(
        upstream_authorization_endpoint=f"{portal_url}/sharing/rest/oauth2/authorize",
        upstream_token_endpoint=f"{portal_url}/sharing/rest/oauth2/token",
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        token_verifier=token_verifier,
        base_url=base_url,
        forward_pkce=True,
        token_endpoint_auth_method="client_secret_post",
        verify_ssl=verify_ssl,
    )

    logger.info(
        "ArcGIS OAuth proxy initialized for portal: %s (base_url: %s, verify_ssl: %s)",
        portal_url,
        base_url,
        verify_ssl,
    )

    return proxy
