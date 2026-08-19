"""Simple TTL-based in-memory cache."""

import time
from typing import Any


class TTLCache:
    """In-memory cache with time-based expiration.

    Uses monotonic clock for reliable expiration tracking regardless of
    system clock adjustments. Designed for single-threaded asyncio use
    (no locks needed).
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Get a cached value if it exists and hasn't expired.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or None if the key is missing or expired.
            Expired entries are deleted on access.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        timestamp, value = entry
        if time.monotonic() - timestamp > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with the current timestamp.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        """Remove all cached entries."""
        self._store.clear()
