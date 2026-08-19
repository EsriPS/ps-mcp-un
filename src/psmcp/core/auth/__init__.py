"""ArcGIS Enterprise authentication helpers for PS-MCP.

Public API:

- :func:`resolve_token` — three-tier token resolution shared by every router.
- :class:`ArcGISAuthProvider` — FastMCP ``RemoteAuthProvider`` subclass.
- :class:`ArcGISTokenVerifier` — token verifier that calls the portal REST API.
- :class:`AuthenticationError` — generic auth-failure exception.
"""

from __future__ import annotations

import logging
import os

from fastmcp.server.dependencies import get_access_token

from psmcp.core.auth.arcgis_provider import ArcGISAuthProvider
from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when token resolution or verification fails."""


def resolve_token(token: str | None = None, required: bool = False) -> str | None:
    """Resolve the authentication token using a fixed precedence.

    Resolution order:

        1. Explicit ``token`` argument.
        2. FastMCP authentication context (per-request).
        3. ``ARCGIS_TOKEN`` environment variable.

    Args:
        token: Optional explicit token from the caller.
        required: If ``True`` and no token can be resolved, raise ``ValueError``.

    Returns:
        The resolved token string, or ``None`` if none is available and
        ``required`` is ``False``.

    Raises:
        ValueError: If ``required=True`` and no token is found.
    """
    if token:
        return token

    try:
        access_token = get_access_token()
        if access_token and access_token.token:
            return access_token.token
    except Exception as exc:
        logger.debug("Could not get token from authentication context: %s", exc)

    env_token = os.getenv("ARCGIS_TOKEN")
    if env_token:
        return env_token

    if required:
        raise ValueError(
            "No authentication token available. Provide a token argument or "
            "ensure the request has an authenticated FastMCP context / "
            "ARCGIS_TOKEN env var set."
        )

    return None


__all__ = [
    "ArcGISAuthProvider",
    "ArcGISTokenVerifier",
    "AuthenticationError",
    "resolve_token",
]
