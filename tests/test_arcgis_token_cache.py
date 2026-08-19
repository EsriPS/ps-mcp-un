"""Tests for ArcGIS token cache behavior in ArcGISTokenVerifier."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient with proper response structure."""
    portal_data = {"id": "portal123", "name": "Test Portal"}
    user_data = {
        "username": "testuser",
        "fullName": "Test User",
        "email": "test@example.com",
        "role": "org_user",
        "orgId": "org123",
        "privileges": ["portal:user:createItem"],
    }

    async def mock_get(url, **kwargs):
        response = MagicMock()
        response.status_code = 200
        if "portals/self" in url:
            response.json = MagicMock(return_value=portal_data)
        elif "community/self" in url:
            response.json = MagicMock(return_value=user_data)
        return response

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.get = mock_get

    return mock_client


class TestTokenCacheHitAndExpiry:
    """Test cache hit and expiry behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_portal_request(self, monkeypatch, mock_httpx_client):
        """Second verification with same token should hit cache and skip portal."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=120)

        call_count = 0
        original_get = mock_httpx_client.get

        async def counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_get(*args, **kwargs)

        mock_httpx_client.get = counting_get

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # First call - should hit portal
            result1 = await verifier.verify_token("test-token-123")
            assert result1 is not None
            assert result1.claims["username"] == "testuser"
            first_call_count = call_count

            # Second call - should hit cache
            result2 = await verifier.verify_token("test-token-123")
            assert result2 is not None
            assert result2.claims["username"] == "testuser"
            assert call_count == first_call_count, "Cache hit should not make new requests"

    @pytest.mark.asyncio
    async def test_cache_expiry_triggers_revalidation(self, monkeypatch, mock_httpx_client):
        """Expired cache entry should trigger new portal validation."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=1)

        call_count = 0
        original_get = mock_httpx_client.get

        async def counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_get(*args, **kwargs)

        mock_httpx_client.get = counting_get

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # First call
            result1 = await verifier.verify_token("test-token-123")
            assert result1 is not None
            first_call_count = call_count

            # Wait for expiry
            time.sleep(1.1)

            # Second call after expiry - should hit portal again
            result2 = await verifier.verify_token("test-token-123")
            assert result2 is not None
            assert call_count > first_call_count, "Expired cache should trigger revalidation"


class TestCacheDisabled:
    """Test cache disabled behavior (TTL=0)."""

    @pytest.mark.asyncio
    async def test_cache_disabled_with_ttl_zero(self, monkeypatch, mock_httpx_client):
        """When cache_ttl=0, every verification should hit portal."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=0)

        call_count = 0
        original_get = mock_httpx_client.get

        async def counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_get(*args, **kwargs)

        mock_httpx_client.get = counting_get

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # First call
            await verifier.verify_token("test-token-123")
            first_call_count = call_count

            # Second call - should still hit portal (no caching)
            await verifier.verify_token("test-token-123")
            assert call_count > first_call_count, "Cache disabled should always hit portal"

    @pytest.mark.asyncio
    async def test_cache_disabled_via_env(self, monkeypatch, mock_httpx_client):
        """ARCGIS_TOKEN_CACHE_TTL=0 should disable caching."""
        monkeypatch.setenv("ARCGIS_TOKEN_CACHE_TTL", "0")
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")
        assert verifier._cache_ttl == 0

        call_count = 0
        original_get = mock_httpx_client.get

        async def counting_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_get(*args, **kwargs)

        mock_httpx_client.get = counting_get

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            await verifier.verify_token("test-token-123")
            first_call_count = call_count

            await verifier.verify_token("test-token-123")
            assert call_count > first_call_count


class TestInvalidCacheTTL:
    """Test handling of invalid ARCGIS_TOKEN_CACHE_TTL values."""

    def test_invalid_ttl_falls_back_to_default(self, monkeypatch, caplog):
        """Non-integer ARCGIS_TOKEN_CACHE_TTL should fall back to default with warning."""
        monkeypatch.setenv("ARCGIS_TOKEN_CACHE_TTL", "not-a-number")
        from psmcp.core.auth.arcgis_verifier import _DEFAULT_TOKEN_CACHE_TTL, ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")

        assert verifier._cache_ttl == _DEFAULT_TOKEN_CACHE_TTL
        assert any(
            "Invalid ARCGIS_TOKEN_CACHE_TTL" in record.getMessage() for record in caplog.records
        )

    def test_empty_ttl_uses_default(self, monkeypatch):
        """Empty ARCGIS_TOKEN_CACHE_TTL should use default."""
        monkeypatch.setenv("ARCGIS_TOKEN_CACHE_TTL", "")
        from psmcp.core.auth.arcgis_verifier import _DEFAULT_TOKEN_CACHE_TTL, ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com")
        assert verifier._cache_ttl == _DEFAULT_TOKEN_CACHE_TTL


class TestLRUEviction:
    """Test LRU cache eviction behavior."""

    @pytest.mark.asyncio
    async def test_lru_evicts_oldest_when_full(self, monkeypatch, mock_httpx_client):
        """When cache is full, oldest entry should be evicted."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        # Create verifier with small cache size for testing
        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=120)
        verifier._max_cache_size = 3  # Small size for testing

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # Fill cache
            await verifier.verify_token("token-1")
            await verifier.verify_token("token-2")
            await verifier.verify_token("token-3")
            assert len(verifier._cache) == 3

            # Add one more - should evict token-1
            await verifier.verify_token("token-4")
            assert len(verifier._cache) == 3
            assert "token-1" not in verifier._cache
            assert "token-4" in verifier._cache

    @pytest.mark.asyncio
    async def test_lru_access_updates_order(self, monkeypatch, mock_httpx_client):
        """Accessing a cached token should move it to end (most recent)."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=120)
        verifier._max_cache_size = 3

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # Fill cache
            await verifier.verify_token("token-1")
            await verifier.verify_token("token-2")
            await verifier.verify_token("token-3")

            # Access token-1 (should move to end)
            await verifier.verify_token("token-1")

            # Add token-4 - should evict token-2 (now oldest)
            await verifier.verify_token("token-4")
            assert "token-2" not in verifier._cache
            assert "token-1" in verifier._cache


class TestPeriodicCleanup:
    """Test periodic cleanup of expired entries."""

    @pytest.mark.asyncio
    async def test_periodic_cleanup_removes_expired(self, monkeypatch, mock_httpx_client):
        """Periodic cleanup should remove expired entries."""
        from psmcp.core.auth.arcgis_verifier import ArcGISTokenVerifier

        verifier = ArcGISTokenVerifier(portal_url="https://portal.example.com", cache_ttl=1)

        with patch("httpx.AsyncClient", return_value=mock_httpx_client):
            # Add multiple tokens
            await verifier.verify_token("token-1")
            await verifier.verify_token("token-2")
            await verifier.verify_token("token-3")
            assert len(verifier._cache) == 3

            # Wait for expiry
            time.sleep(1.1)

            # Trigger cleanup by accessing cache (after 60s normally, but we'll force it)
            verifier._last_cleanup = time.monotonic() - 61  # Force cleanup on next access
            await verifier.verify_token("token-4")

            # Old tokens should be cleaned up
            assert "token-1" not in verifier._cache
            assert "token-2" not in verifier._cache
            assert "token-3" not in verifier._cache
