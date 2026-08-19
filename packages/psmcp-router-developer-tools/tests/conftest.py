"""Shared test fixtures for the developer-tools router."""

import pytest
from psmcp_router_developer_tools.cache import TTLCache


@pytest.fixture
def ttl_cache() -> TTLCache:
    """Provide a fresh TTLCache instance with a 5-minute TTL."""
    return TTLCache(ttl_seconds=300)
