"""ArcGIS Enterprise authentication provider for FastMCP."""

from __future__ import annotations

import logging
import os

from fastmcp.server.auth import RemoteAuthProvider
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

logger = logging.getLogger(__name__)


class ArcGISAuthProvider(RemoteAuthProvider):
    """Authentication provider that delegates to an ArcGIS Enterprise portal.

    Wraps :class:`ArcGISTokenVerifier` and exposes a couple of helper HTTP
    routes (``/auth/arcgis/token-info`` and ``/auth/arcgis/portal-info``) on
    top of the standard FastMCP OAuth-style routes.

    Usage::

        from psmcp.core.auth import ArcGISAuthProvider

        mcp = FastMCP(name="my-server", auth=ArcGISAuthProvider())

    Environment variables:
        ARCGIS_PORTAL_URL: Portal base URL.
        ARCGIS_VERIFY_SSL: ``"true"`` to verify TLS (default ``True``).
        MCP_SERVER_BASE_URL: Public base URL of this MCP server (used for
            OAuth discovery responses). Defaults to ``http://localhost:8888``.
    """

    def __init__(
        self,
        portal_url: str | None = None,
        verify_ssl: bool | None = None,
        base_url: str | None = None,
    ):
        portal_url = portal_url or os.getenv("ARCGIS_PORTAL_URL")
        base_url = base_url or os.getenv("MCP_SERVER_BASE_URL", "http://localhost:8888")

        if not portal_url:
            raise ValueError(
                "ArcGIS Portal URL is required. Set the ARCGIS_PORTAL_URL "
                "environment variable or pass portal_url."
            )

        self.token_verifier = ArcGISTokenVerifier(
            portal_url=portal_url,
            verify_ssl=verify_ssl,
        )

        portal_url = portal_url.rstrip("/")
        self._portal_url = portal_url

        super().__init__(
            token_verifier=self.token_verifier,
            authorization_servers=[AnyHttpUrl(portal_url)],
            base_url=base_url,
        )

        logger.info("ArcGIS Auth Provider initialized for portal: %s", portal_url)

    def get_routes(self, mcp_path: str = "/mcp") -> list[Route]:
        """Return FastMCP standard routes plus ArcGIS-specific helpers."""
        routes = super().get_routes(mcp_path=mcp_path)

        routes.append(Route("/auth/arcgis/token-info", self._token_info_endpoint, methods=["POST"]))
        routes.append(
            Route("/auth/arcgis/portal-info", self._portal_info_endpoint, methods=["GET"])
        )
        return routes

    async def _token_info_endpoint(self, request: Request) -> JSONResponse:
        """``POST /auth/arcgis/token-info`` — inspect a token without consuming it."""
        try:
            body = await request.json()
            token = body.get("token")

            if not token:
                return JSONResponse({"error": "Token is required"}, status_code=400)

            access_token = await self.token_verifier.verify_token(token)

            if access_token is None:
                return JSONResponse({"error": "Invalid or expired token"}, status_code=401)

            return JSONResponse(
                {
                    "valid": True,
                    "client_id": access_token.client_id,
                    "scopes": access_token.scopes,
                    "claims": access_token.claims,
                }
            )

        except Exception as exc:
            logger.error("Token info endpoint error: %s", exc)
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    async def _portal_info_endpoint(self, _request: Request) -> JSONResponse:
        """``GET /auth/arcgis/portal-info`` — public portal metadata."""
        return JSONResponse(
            {
                "portal_url": self._portal_url,
                "auth_type": "arcgis-enterprise",
                "token_endpoint": f"{self._portal_url}/sharing/rest/generateToken",
                "oauth_authorize": f"{self._portal_url}/sharing/rest/oauth2/authorize",
            }
        )
