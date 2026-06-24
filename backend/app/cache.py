"""Simple in-memory cache with TTL for read-only data.

Used to avoid redundant Withings/Garmin API calls within short windows.
Cache is invalidated after any write operation (sync) or on explicit refresh.
"""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

_logger: logging.Logger | None = None


def _log() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger(__name__)
    return _logger


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


async def stale_while_revalidate(
    key: str,
    fetch_func: Callable[[], Coroutine[Any, Any, Any]],
    ttl: float = 30.0,
    stale_ttl: float = 300.0,
) -> Any:
    """Serve stale cache while refreshing in background.

    *ttl* — cache is considered fresh within this window (seconds).  
    *stale_ttl* — cache may be served stale while a background refresh runs.

    When the cache is fresh → return immediately.  
    When stale but within *stale_ttl* → return immediately + kick off async refresh.  
    When stale beyond *stale_ttl* or missing → await the fetch.
    """
    cache = get_cache()
    meta_key = f"{key}:meta"

    cached_val = cache.get(key)
    meta = cache.get(meta_key) or {}

    if cached_val is not None and isinstance(meta, dict):
        cached_at = meta.get("cached_at")
        if cached_at:
            age = time.monotonic() - cached_at
            if age < ttl:
                return cached_val
            if age < stale_ttl:
                asyncio.ensure_future(_background_refresh(key, meta_key, fetch_func, ttl))
                return cached_val

    # Cache miss or too stale — fetch synchronously
    result = await fetch_func()
    now = time.monotonic()
    cache.set(key, result, ttl_seconds=stale_ttl)
    cache.set(meta_key, {"cached_at": now}, ttl_seconds=stale_ttl)
    return result


async def _background_refresh(
    key: str,
    meta_key: str,
    fetch_func: Callable[[], Coroutine[Any, Any, Any]],
    ttl: float,
) -> None:
    """Refresh cache in background (fire-and-forget)."""
    try:
        result = await fetch_func()
        cache = get_cache()
        now = time.monotonic()
        cache.set(key, result, ttl_seconds=ttl)
        cache.set(meta_key, {"cached_at": now}, ttl_seconds=ttl)
    except Exception as exc:
        _log().warning("Background refresh failed for %s: %s", key, exc)
        # Stale value remains in cache


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
