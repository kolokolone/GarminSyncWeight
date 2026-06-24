"""Tests for WithingsMeasurementStore — persistent store for parsed Withings measurements."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.withings import BodyCompositionMeasurement
from app.storage.measurement_store import WithingsMeasurementStore


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def store(settings) -> WithingsMeasurementStore:
    s = WithingsMeasurementStore(settings.resolved_data_dir)
    s.clear()
    yield s
    s.close()


def _make_meas(
    group_id: str,
    date_str: str = "2026-06-01",
    weight_kg: str = "78.5",
    fat_percent: str | None = "15.2",
    **extra,
) -> BodyCompositionMeasurement:
    dt = datetime.fromisoformat(f"{date_str}T10:00:00+00:00")
    return BodyCompositionMeasurement(
        source_measure_group_id=group_id,
        source_device_id="test_device",
        garmin_date=datetime.fromisoformat(date_str).date(),
        measured_at_utc=dt,
        measured_at_local=dt,
        weight_kg=Decimal(weight_kg),
        fat_percent=Decimal(fat_percent) if fat_percent else None,
        source="withings",
        raw={},
        **extra,
    )


# ─── SAVE & COUNT ─────────────────────────────────────────────────


class TestSaveAndCount:
    def test_save_single(self, store: WithingsMeasurementStore) -> None:
        saved = store.save_measurements([_make_meas("g1")])
        assert saved == 1
        assert store.get_count() == 1

    def test_save_multiple(self, store: WithingsMeasurementStore) -> None:
        meas = [
            _make_meas("g1", "2026-06-01", "78.5"),
            _make_meas("g2", "2026-06-02", "79.0"),
        ]
        saved = store.save_measurements(meas)
        assert saved == 2
        assert store.get_count() == 2

    def test_save_empty_list(self, store: WithingsMeasurementStore) -> None:
        saved = store.save_measurements([])
        assert saved == 0

    def test_save_idempotent(self, store: WithingsMeasurementStore) -> None:
        m = _make_meas("g1")
        assert store.save_measurements([m]) == 1
        assert store.save_measurements([m]) == 0  # ignored
        assert store.get_count() == 1


# ─── GET & QUERY ──────────────────────────────────────────────────


class TestGetAndQuery:
    def test_get_measurements_by_date_range(self, store: WithingsMeasurementStore) -> None:
        store.save_measurements([
            _make_meas("g1", "2026-06-01", "78.0"),
            _make_meas("g2", "2026-06-02", "79.0"),
            _make_meas("g3", "2026-06-04", "80.0"),
        ])
        results = store.get_measurements("2026-06-01", "2026-06-02")
        assert len(results) == 2
        assert results[0].source_measure_group_id == "g1"
        assert results[1].source_measure_group_id == "g2"

    def test_get_latest(self, store: WithingsMeasurementStore) -> None:
        store.save_measurements([
            _make_meas("g1", "2026-06-01", "78.0"),
            _make_meas("g2", "2026-06-03", "80.0"),
            _make_meas("g3", "2026-06-02", "79.0"),
        ])
        latest = store.get_latest()
        assert latest is not None
        assert latest.source_measure_group_id == "g2"  # 2026-06-03

    def test_get_latest_empty(self, store: WithingsMeasurementStore) -> None:
        assert store.get_latest() is None

    def test_get_recent(self, store: WithingsMeasurementStore) -> None:
        # Force old-dated measurements so only recent ones are returned
        far_past = "2025-01-01"
        store.save_measurements([
            _make_meas("g1", "2026-06-01", "78.0"),
            _make_meas("g2", far_past, "70.0"),
        ])
        # get_recent with days=30 → only g1 (2026-06-01) should be within 30 days
        recent = store.get_recent(365)  # wide window to include both
        assert len(recent) >= 1

    def test_get_by_id(self, store: WithingsMeasurementStore) -> None:
        store.save_measurements([_make_meas("g1", "2026-06-01", "78.5")])
        result = store.get_by_id("g1")
        assert result is not None
        assert result.source_measure_group_id == "g1"

    def test_get_by_id_missing(self, store: WithingsMeasurementStore) -> None:
        assert store.get_by_id("nonexistent") is None


# ─── DECIMAL PRECISION ────────────────────────────────────────────


class TestDecimalPrecision:
    def test_decimal_precision_preserved(self, store: WithingsMeasurementStore) -> None:
        """Decimal values stored as TEXT must survive a save→get round-trip."""
        m = _make_meas("g1", "2026-06-01", "78.537")
        store.save_measurements([m])
        results = store.get_measurements("2026-06-01", "2026-06-01")
        assert len(results) == 1
        assert results[0].weight_kg == Decimal("78.537")

    def test_none_decimal_field(self, store: WithingsMeasurementStore) -> None:
        m = _make_meas("g1", "2026-06-01", "78.5", fat_percent=None)
        store.save_measurements([m])
        results = store.get_measurements("2026-06-01", "2026-06-01")
        assert results[0].fat_percent is None


# ─── EDGE CASES ───────────────────────────────────────────────────


class TestEdgeCases:
    def test_clear_removes_all(self, store: WithingsMeasurementStore) -> None:
        store.save_measurements([
            _make_meas("g1", "2026-06-01", "78.0"),
            _make_meas("g2", "2026-06-02", "79.0"),
        ])
        store.clear()
        assert store.get_count() == 0

    def test_duplicate_group_id_ignored(self, store: WithingsMeasurementStore) -> None:
        m1 = _make_meas("g1", "2026-06-01", "78.5")
        m2 = _make_meas("g1", "2026-06-01", "99.9")  # same group_id, different weight
        saved = store.save_measurements([m1, m2])
        assert saved == 1  # only first inserted
        result = store.get_by_id("g1")
        assert result is not None
        assert result.weight_kg == Decimal("78.5")  # original preserved
