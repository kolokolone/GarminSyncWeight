"""Simple in-memory cache with TTL for read-only data.

Used to avoid redundant Withings/Garmin API calls within short windows.
Cache is invalidated after any write operation (sync) or on explicit refresh.
"""

import time
from collections.abc import Callable
from typing import Any


class TTLCache:
    """In-memory cache with per-key TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """Return cached value if fresh, else None."""
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: float = 30.0) -> None:
        """Store value with TTL."""
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def invalidate(self, pattern: str | None = None) -> None:
        """Invalidate all keys (or keys containing pattern)."""
        if pattern is None:
            self._store.clear()
            return
        self._store = {k: v for k, v in self._store.items() if pattern not in k}

    def invalidate_all(self) -> None:
        self._store.clear()


# ── Global singleton ──────────────────────────────────────────────

_cache: TTLCache | None = None


def get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache()
    return _cache


def cached(key: str, ttl_seconds: float = 30.0) -> Callable:
    """Decorator: cache async function result with TTL.

    Usage:

        @cached("my_data", ttl_seconds=30)
        async def fetch_my_data():
            ...
    """
    def decorator(fn: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache()
            cached_val = cache.get(key)
            if cached_val is not None:
                return cached_val
            result = await fn(*args, **kwargs)
            cache.set(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator
