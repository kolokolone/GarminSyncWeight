"""Tests for TTLCache and stale_while_revalidate."""

import asyncio
import time

import pytest
from app.cache import TTLCache, get_cache, stale_while_revalidate

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure a fresh cache for each test."""
    cache = get_cache()
    cache.invalidate_all()
    # Reset the module-level singleton for isolation
    import app.cache as cache_module
    cache_module._cache = None
    yield
    cache_module._cache = None


# ─── TTLCache basics ──────────────────────────────────────────────


class TestTTLCache:
    def test_get_miss(self) -> None:
        c = TTLCache()
        assert c.get("missing") is None

    def test_set_and_get(self) -> None:
        c = TTLCache()
        c.set("key", "value", ttl_seconds=60)
        assert c.get("key") == "value"

    def test_ttl_expiry(self) -> None:
        c = TTLCache()
        c.set("key", "value", ttl_seconds=0)  # expires immediately
        # TTLCache.get() checks time.monotonic(), which should have advanced
        # at least 1 tick, so the entry is already expired
        time.sleep(0.01)
        assert c.get("key") is None

    def test_invalidate_all(self) -> None:
        c = TTLCache()
        c.set("a", 1)
        c.set("b", 2)
        c.invalidate_all()
        assert c.get("a") is None
        assert c.get("b") is None

    def test_different_ttls(self) -> None:
        c = TTLCache()
        c.set("short", "fast", ttl_seconds=0.05)
        c.set("long", "slow", ttl_seconds=60)
        time.sleep(0.06)
        assert c.get("short") is None
        assert c.get("long") == "slow"


# ─── stale_while_revalidate ───────────────────────────────────────


class TestStaleWhileRevalidate:
    @pytest.mark.asyncio
    async def test_cache_miss_fetches(self) -> None:
        """No cache → fetch_func is awaited."""
        fetched = False

        async def fetch():
            nonlocal fetched
            fetched = True
            return "fresh"

        result = await stale_while_revalidate("miss_key", fetch, ttl=30, stale_ttl=60)
        assert result == "fresh"
        assert fetched

    @pytest.mark.asyncio
    async def test_cache_hit_returns_immediately(self) -> None:
        """Fresh cache → returns immediately, no fetch."""
        cache = get_cache()
        cache.set("hit_key", "cached", ttl_seconds=60)
        cache.set("hit_key:meta", {"cached_at": time.monotonic()}, ttl_seconds=60)

        fetched = False

        async def fetch():
            nonlocal fetched
            fetched = True
            return "should_not_be_called"

        result = await stale_while_revalidate("hit_key", fetch, ttl=30, stale_ttl=60)
        assert result == "cached"
        assert not fetched

    @pytest.mark.asyncio
    async def test_stale_triggers_background_refresh(self) -> None:
        """Stale but within stale_ttl → returns stale + fires background task."""
        cache = get_cache()
        cache.set("stale_key", "stale_value", ttl_seconds=120)
        # Set meta in the past so age > ttl but < stale_ttl
        past = time.monotonic() - 40  # 40s old — >30 ttl, <120 stale_ttl
        cache.set("stale_key:meta", {"cached_at": past}, ttl_seconds=120)

        bg_started = asyncio.Event()

        async def fetch():
            bg_started.set()
            return "refreshed_value"

        result = await stale_while_revalidate("stale_key", fetch, ttl=30, stale_ttl=120)
        assert result == "stale_value"  # stale served immediately
        # Allow background task to run
        await asyncio.wait_for(bg_started.wait(), timeout=2)

    @pytest.mark.asyncio
    async def test_too_stale_fetches_sync(self) -> None:
        """Beyond stale_ttl → fetch synchronously."""
        cache = get_cache()
        cache.set("old_key", "old_value", ttl_seconds=200)
        # Set meta very far in the past
        very_past = time.monotonic() - 500  # > stale_ttl (300 default)
        cache.set("old_key:meta", {"cached_at": very_past}, ttl_seconds=200)

        fetched = False

        async def fetch():
            nonlocal fetched
            fetched = True
            return "new_value"

        result = await stale_while_revalidate("old_key", fetch, ttl=30, stale_ttl=60)
        assert result == "new_value"
        assert fetched

    @pytest.mark.asyncio
    async def test_background_refresh_updates_cache(self) -> None:
        """After background refresh, subsequent calls get fresh data."""
        cache = get_cache()
        cache.set("bg_key", "stale", ttl_seconds=120)
        past = time.monotonic() - 40
        cache.set("bg_key:meta", {"cached_at": past}, ttl_seconds=120)

        async def fetch():
            await asyncio.sleep(0.05)
            return "refreshed"

        # First call: returns stale, triggers background
        result1 = await stale_while_revalidate("bg_key", fetch, ttl=30, stale_ttl=120)
        assert result1 == "stale"

        # Wait for background to complete
        await asyncio.sleep(0.1)

        # Cache should now be fresh with refreshed value
        meta = cache.get("bg_key:meta")
        assert meta is not None
        age = time.monotonic() - meta["cached_at"]
        assert age < 30  # freshly cached
