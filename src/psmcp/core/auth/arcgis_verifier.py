"""ArcGIS Enterprise token verifier for FastMCP authentication."""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from typing import Protocol, runtime_checkable

import httpx
from fastmcp.server.auth import AccessToken

logger = logging.getLogger(__name__)

# Default cache TTL in seconds (2 minutes). Override via ARCGIS_TOKEN_CACHE_TTL.
_DEFAULT_TOKEN_CACHE_TTL = 120

# Maximum number of tokens to cache. Prevents unbounded memory growth.
_MAX_CACHE_SIZE = 1000


@runtime_checkable
class TokenVerifier(Protocol):
    """Structural type for token verifiers compatible with FastMCP."""

    async def verify_token(self, token: str) -> AccessToken | None:  # pragma: no cover - protocol
        ...


class ArcGISTokenVerifier:
    """Verify ArcGIS Enterprise tokens against the portal REST API.

    The verifier hits ``/sharing/rest/portals/self`` to confirm validity, then
    ``/sharing/rest/community/self`` to pull user info that becomes the
    ``AccessToken.claims`` payload returned to FastMCP.

    Verified tokens are cached in memory for a configurable TTL to avoid
    redundant portal round-trips on consecutive tool calls. The cache is keyed
    on the raw token string and stores the resulting :class:`AccessToken`.

    Environment variables:
        ARCGIS_PORTAL_URL: Portal base URL (overridable via constructor).
        ARCGIS_VERIFY_SSL: ``"true"`` to verify TLS certificates (default ``True``).
        ARCGIS_TOKEN_CACHE_TTL: Cache lifetime in seconds for verified tokens
            (default ``120``). Set to ``0`` to disable caching entirely.
    """

    def __init__(
        self,
        portal_url: str | None = None,
        verify_ssl: bool | None = None,
        required_scopes: list[str] | None = None,
        cache_ttl: int | None = None,
    ):
        self.portal_url = portal_url or os.getenv("ARCGIS_PORTAL_URL")

        if not self.portal_url:
            raise ValueError(
                "ArcGIS Portal URL is required. Set the ARCGIS_PORTAL_URL "
                "environment variable or pass portal_url."
            )

        if verify_ssl is not None:
            self.verify_ssl = verify_ssl
        else:
            self.verify_ssl = os.getenv("ARCGIS_VERIFY_SSL", "True").lower() == "true"

        self.required_scopes = required_scopes or []
        self.portal_url = self.portal_url.rstrip("/")

        # Token verification cache: OrderedDict for LRU behavior
        # {token_str: (AccessToken, timestamp)}
        self._cache: OrderedDict[str, tuple[AccessToken, float]] = OrderedDict()
        self._max_cache_size = _MAX_CACHE_SIZE
        self._last_cleanup = time.monotonic()
        if cache_ttl is not None:
            self._cache_ttl = cache_ttl
        else:
            try:
                self._cache_ttl = int(
                    os.getenv("ARCGIS_TOKEN_CACHE_TTL", str(_DEFAULT_TOKEN_CACHE_TTL))
                )
            except ValueError:
                logger.warning(
                    "Invalid ARCGIS_TOKEN_CACHE_TTL value, using default %ds",
                    _DEFAULT_TOKEN_CACHE_TTL,
                )
                self._cache_ttl = _DEFAULT_TOKEN_CACHE_TTL

        logger.info(
            "ArcGIS Token Verifier initialized for portal: %s (cache_ttl=%ds)",
            self.portal_url,
            self._cache_ttl,
        )

    @property
    def scopes_supported(self) -> list[str]:
        """Scopes advertised in OAuth metadata discovery."""
        return ["read", "write", "admin", "manage", "publish", "create", "delete", "update"]

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate ``token`` and return an :class:`AccessToken` on success.

        Results are cached for up to ``cache_ttl`` seconds. A cache hit skips
        the portal round-trips entirely. Failed verifications (returning None)
        are never cached.
        """
        # Check cache first
        cached = self._get_cached(token)
        if cached is not None:
            logger.debug("Token cache hit for user: %s", cached.claims.get("username"))
            return cached

        try:
            portal_info = await self._validate_with_portal(token)
            if not portal_info:
                return None

            user_info = await self._get_user_info(token)
            if not user_info:
                return None

            username = user_info.get("username", "unknown")

            claims = {
                "sub": username,
                "username": username,
                "fullName": user_info.get("fullName"),
                "email": user_info.get("email"),
                "role": user_info.get("role"),
                "orgId": user_info.get("orgId"),
                "privileges": user_info.get("privileges", []),
                "portal_url": self.portal_url,
            }

            scopes = self._role_to_scopes(user_info.get("role"), user_info.get("privileges", []))

            access_token = AccessToken(
                token=token,
                client_id=user_info.get("orgId", "arcgis-enterprise"),
                scopes=scopes,
                expires_at=None,
                claims=claims,
            )

            self._put_cached(token, access_token)
            return access_token

        except Exception as exc:
            logger.warning("Token verification failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _get_cached(self, token: str) -> AccessToken | None:
        """Return a cached AccessToken if present and not expired."""
        if self._cache_ttl <= 0:
            return None

        # Periodic cleanup of expired entries (every 60 seconds)
        now = time.monotonic()
        if now - self._last_cleanup > 60:
            self._cleanup_expired()
            self._last_cleanup = now

        entry = self._cache.get(token)
        if entry is None:
            return None

        access_token, cached_at = entry
        if (now - cached_at) > self._cache_ttl:
            # Expired — evict
            del self._cache[token]
            return None

        # Move to end for LRU behavior
        self._cache.move_to_end(token)
        return access_token

    def _put_cached(self, token: str, access_token: AccessToken) -> None:
        """Store a verified AccessToken in the cache with LRU eviction."""
        if self._cache_ttl <= 0:
            return

        # If token already exists, update it and move to end
        if token in self._cache:
            self._cache[token] = (access_token, time.monotonic())
            self._cache.move_to_end(token)
            return

        # Evict oldest entry if at max size
        if len(self._cache) >= self._max_cache_size:
            oldest_token = next(iter(self._cache))
            del self._cache[oldest_token]
            logger.debug("Cache full, evicted oldest token")

        self._cache[token] = (access_token, time.monotonic())

    def _cleanup_expired(self) -> None:
        """Remove all expired entries from the cache."""
        if self._cache_ttl <= 0:
            return

        now = time.monotonic()
        expired_tokens = [
            token
            for token, (_, cached_at) in self._cache.items()
            if (now - cached_at) > self._cache_ttl
        ]

        for token in expired_tokens:
            del self._cache[token]

        if expired_tokens:
            logger.debug("Cleaned up %d expired token(s) from cache", len(expired_tokens))

    def invalidate_token(self, token: str) -> None:
        """Remove a specific token from the cache.

        Useful when a downstream call indicates the token has been revoked.
        """
        self._cache.pop(token, None)

    def clear_cache(self) -> None:
        """Remove all cached tokens."""
        self._cache.clear()

    async def _validate_with_portal(self, token: str) -> dict | None:
        """GET ``/portals/self`` to confirm the token is recognized."""
        url = f"{self.portal_url}/sharing/rest/portals/self"
        params = {"token": token, "f": "json"}
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.warning("Portal validation failed with status: %s", response.status_code)
                    return None

                data = response.json()
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    logger.warning("Portal returned error: %s", error_msg)
                    return None
                return data
        except httpx.RequestError as exc:
            logger.error("Failed to connect to ArcGIS Portal: %s", exc)
            return None

    async def _get_user_info(self, token: str) -> dict | None:
        """GET ``/community/self`` to fetch user metadata for token claims."""
        url = f"{self.portal_url}/sharing/rest/community/self"
        params = {"token": token, "f": "json"}
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=30.0) as client:
                response = await client.get(url, params=params)
                if response.status_code != 200:
                    logger.warning(
                        "User info request failed with status: %s",
                        response.status_code,
                    )
                    return None

                data = response.json()
                if "error" in data:
                    error_msg = data["error"].get("message", "Unknown error")
                    logger.warning("User info returned error: %s", error_msg)
                    return None

                return {
                    "username": data.get("username"),
                    "fullName": data.get("fullName"),
                    "email": data.get("email"),
                    "role": data.get("role"),
                    "orgId": data.get("orgId"),
                    "privileges": data.get("privileges", []),
                }
        except httpx.RequestError as exc:
            logger.error("Failed to get user info: %s", exc)
            return None

    @staticmethod
    def _role_to_scopes(role: str | None, privileges: list) -> list[str]:
        """Translate ArcGIS role + privileges into OAuth-style scope strings."""
        scopes = ["read"]

        if role:
            role_lower = role.lower()
            if "admin" in role_lower:
                scopes.extend(["write", "admin", "manage"])
            elif "publisher" in role_lower:
                scopes.extend(["write", "publish"])
            elif "user" in role_lower:
                scopes.append("write")

        for privilege in privileges:
            priv_lower = privilege.lower()
            if "create" in priv_lower:
                scopes.append("create")
            if "delete" in priv_lower:
                scopes.append("delete")
            if "update" in priv_lower:
                scopes.append("update")

        return list(set(scopes))
