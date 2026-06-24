"""Tests for GarminCacheStore — persistent SQLite cache with 1h TTL."""

from datetime import UTC, datetime, timedelta

import pytest

from app.storage.garmin_cache import GarminCacheStore, GARMIN_CACHE_TTL_SECONDS


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def cache(settings) -> GarminCacheStore:
    store = GarminCacheStore(settings.resolved_data_dir)
    store.clear()
    yield store
    store.close()


# ── Helpers ───────────────────────────────────────────────────────


_SAMPLE_DATA = [
    {"date": "2026-06-01", "weight_kg": 78.5, "bmi": 23.1},
    {"date": "2026-06-01", "weight_kg": 78.6, "bmi": 23.2},
]


# ─── HIT / MISS / TTL ────────────────────────────────────────────


class TestCacheHitMiss:
    def test_miss_on_empty(self, cache: GarminCacheStore) -> None:
        assert cache.get("weigh_in", "2026-06-01") is None

    def test_hit_after_set(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        result = cache.get("weigh_in", "2026-06-01")
        assert result == _SAMPLE_DATA

    def test_miss_after_ttl_expiry(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        # Manually push cache_expires_at into the past
        cache.conn.execute(
            """UPDATE garmin_measurements_cache
               SET cache_expires_at = ?
               WHERE date = '2026-06-01' AND source_type = 'weigh_in'""",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(),),
        )
        cache.conn.commit()
        assert cache.get("weigh_in", "2026-06-01") is None

    def test_fresh_within_ttl(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        # Should still be fresh
        assert cache.get("weigh_in", "2026-06-01") == _SAMPLE_DATA


# ─── SOURCE TYPE SEPARATION ───────────────────────────────────────


class TestSourceTypeSeparation:
    def test_weigh_in_and_body_comp_separate(self, cache: GarminCacheStore) -> None:
        wi_data = [{"weight_kg": 78.5}]
        bc_data = [{"weight_kg": 78.5, "percent_fat": 15.0}]
        cache.set("weigh_in", "2026-06-01", wi_data)
        cache.set("body_composition", "2026-06-01", bc_data)
        assert cache.get("weigh_in", "2026-06-01") == wi_data
        assert cache.get("body_composition", "2026-06-01") == bc_data

    def test_replace_same_key(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", [{"weight_kg": 78.5}])
        cache.set("weigh_in", "2026-06-01", [{"weight_kg": 79.0}])
        result = cache.get("weigh_in", "2026-06-01")
        assert result is not None
        assert result[0]["weight_kg"] == 79.0


# ─── INVALIDATION ─────────────────────────────────────────────────


class TestInvalidation:
    def test_invalidate_date_removes_both_types(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        cache.set("body_composition", "2026-06-01", _SAMPLE_DATA)
        cache.invalidate_date("2026-06-01")
        assert cache.get("weigh_in", "2026-06-01") is None
        assert cache.get("body_composition", "2026-06-01") is None

    def test_invalidate_range(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        cache.set("weigh_in", "2026-06-02", _SAMPLE_DATA)
        cache.set("weigh_in", "2026-06-03", _SAMPLE_DATA)
        cache.invalidate_range("2026-06-02", "2026-06-02")
        assert cache.get("weigh_in", "2026-06-01") is not None  # untouched
        assert cache.get("weigh_in", "2026-06-02") is None  # invalidated
        assert cache.get("weigh_in", "2026-06-03") is not None  # untouched

    def test_clear_removes_all(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        cache.set("body_composition", "2026-06-02", _SAMPLE_DATA)
        cache.clear()
        assert cache.get("weigh_in", "2026-06-01") is None
        assert cache.get("body_composition", "2026-06-02") is None


# ─── EDGE CASES ───────────────────────────────────────────────────


class TestEdgeCases:
    def test_corrupted_json_returns_none(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", _SAMPLE_DATA)
        cache.conn.execute(
            "UPDATE garmin_measurements_cache SET data_json = '{bad' WHERE date = '2026-06-01'",
        )
        cache.conn.commit()
        assert cache.get("weigh_in", "2026-06-01") is None

    def test_missing_date_returns_none(self, cache: GarminCacheStore) -> None:
        assert cache.get("weigh_in", "2099-12-31") is None

    def test_empty_list_can_be_cached(self, cache: GarminCacheStore) -> None:
        cache.set("weigh_in", "2026-06-01", [])
        result = cache.get("weigh_in", "2026-06-01")
        assert result == []
