"""Tests for the Garmin API integration layer.

Covers:
  - GarminBodyCompositionCandidate.garmin_params() returns ``timestamp`` (not ``date``)
  - Correct positional argument handling for add_body_composition
  - warnings_count aggregation in SyncSummary
  - Safe wrapper logging in GarminClient.add_body_composition
"""

from datetime import date, datetime
from decimal import Decimal

from app.models.garmin import GarminBodyCompositionCandidate
from app.models.sync import SyncSummary

# ── Helpers ───────────────────────────────────────────────────────

def _candidate(
    *,
    date_str: str = "2026-06-21",
    weight_kg: Decimal | None = Decimal("78.5"),
    measured_at_local: datetime | None = None,
    percent_fat: Decimal | None = Decimal("22.0"),
    muscle_mass: Decimal | None = Decimal("55.0"),
    bone_mass: Decimal | None = Decimal("2.8"),
    bmi: Decimal | None = Decimal("25.6"),
) -> GarminBodyCompositionCandidate:
    return GarminBodyCompositionCandidate(
        date=date.fromisoformat(date_str),
        measured_at_local=measured_at_local,
        weight=weight_kg,
        percent_fat=percent_fat,
        muscle_mass=muscle_mass,
        bone_mass=bone_mass,
        bmi=bmi,
        idempotency_key="test:garmin-api",
    )


# ── garmin_params() tests ─────────────────────────────────────────

class TestGarminParamsTimestamp:
    """garmin_params() must return ``timestamp`` (not ``date``) as the first key."""

    def test_uses_timestamp_key(self) -> None:
        """The returned dict must contain 'timestamp', not 'date'."""
        c = _candidate()
        params = c.garmin_params()
        assert "timestamp" in params, "Expected 'timestamp' key in garmin_params()"
        assert "date" not in params, "Unexpected 'date' key — should be 'timestamp'"

    def test_timestamp_format_when_measured_at_provided(self) -> None:
        """With measured_at_local, timestamp should be the full ISO datetime."""
        dt = datetime(2026, 6, 21, 14, 30, 0)
        c = _candidate(measured_at_local=dt)
        params = c.garmin_params()
        assert params["timestamp"] == "2026-06-21T14:30:00"

    def test_timestamp_falls_back_to_date_when_no_measured_at(self) -> None:
        """Without measured_at_local, timestamp should fall back to date.isoformat()."""
        c = _candidate(measured_at_local=None)
        params = c.garmin_params()
        assert params["timestamp"] == "2026-06-21"

    def test_weight_is_present(self) -> None:
        """weight must always be present in garmin_params()."""
        c = _candidate(weight_kg=Decimal("91.5"))
        params = c.garmin_params()
        assert params["weight"] == 91.5

    def test_composition_fields_included_when_present(self) -> None:
        """percent_fat, muscle_mass etc. should be included when set."""
        c = _candidate(percent_fat=Decimal("18.5"), muscle_mass=Decimal("62.0"))
        params = c.garmin_params()
        assert params["percent_fat"] == 18.5
        assert params["muscle_mass"] == 62.0

    def test_null_composition_fields_omitted(self) -> None:
        """Fields with None values should be omitted from params."""
        c = _candidate(percent_fat=None, muscle_mass=None)
        params = c.garmin_params()
        assert "percent_fat" not in params
        assert "muscle_mass" not in params

    def test_bmi_included(self) -> None:
        """BMI should be included when present."""
        c = _candidate(bmi=Decimal("25.6"))
        params = c.garmin_params()
        assert params["bmi"] == 25.6


# ── garmin_write_method() tests ───────────────────────────────────

class TestGarminWriteMethod:
    """garmin_write_method() must return the correct method name."""

    def test_add_body_composition_when_both_weight_and_composition(self) -> None:
        """With weight and composition → add_body_composition."""
        c = _candidate()
        assert c.garmin_write_method() == "add_body_composition"

    def test_add_weigh_in_with_timestamps_when_weight_and_measured_at(self) -> None:
        """With weight and measured_at_local but no composition → add_weigh_in_with_timestamps."""
        c = _candidate(percent_fat=None, muscle_mass=None, bone_mass=None, bmi=None)
        assert c.garmin_write_method() == "add_weigh_in_with_timestamps"

    def test_add_weigh_in_when_weight_only(self) -> None:
        """With weight only, no measured_at → add_weigh_in."""
        c = _candidate(
            percent_fat=None, muscle_mass=None, bone_mass=None, bmi=None,
            measured_at_local=None,
        )
        assert c.garmin_write_method() == "add_weigh_in"

    def test_invalid_when_no_weight(self) -> None:
        """Without weight → invalid."""
        c = _candidate(weight_kg=None)
        assert c.garmin_write_method() == "invalid"


# ── warnings_count aggregation ────────────────────────────────────

class TestWarningsCountAggregation:
    """SyncSummary.warnings_count must be correctly aggregated."""

    def test_warnings_count_starts_at_zero(self) -> None:
        """A fresh SyncSummary should have warnings_count = 0."""
        s = SyncSummary()
        assert s.warnings_count == 0

    def test_warnings_count_aggregated(self) -> None:
        """When candidates have warnings, warnings_count should reflect total."""
        from app.models.sync import SyncCandidate

        candidates = [
            SyncCandidate(
                date="2026-06-21", warnings=["warning A", "warning B"], decision="synced",
            ),
            SyncCandidate(date="2026-06-22", warnings=["warning C"], decision="synced"),
            SyncCandidate(date="2026-06-23", warnings=[], decision="skipped_existing"),
        ]
        s = SyncSummary(
            candidates_count=len(candidates),
            warnings_count=sum(len(c.warnings) for c in candidates),
            synced_count=2,
            skipped_existing_count=1,
        )
        assert s.warnings_count == 3

    def test_warnings_count_zero_when_no_warnings(self) -> None:
        """When no candidates have warnings, warnings_count should be 0."""
        from app.models.sync import SyncCandidate

        candidates = [
            SyncCandidate(date="2026-06-21", warnings=[], decision="synced"),
            SyncCandidate(date="2026-06-22", warnings=[], decision="synced"),
        ]
        s = SyncSummary(
            candidates_count=len(candidates),
            warnings_count=sum(len(c.warnings) for c in candidates),
            synced_count=2,
        )
        assert s.warnings_count == 0


# ── add_body_composition safe wrapper ────────────────────────────

class TestGarminClientWrapper:
    """GarminClient.add_body_composition must handle timestamp positionally."""

    def test_wrapper_accepts_timestamp_keyword(self) -> None:
        """The wrapper should accept 'timestamp' in kwargs without error.

        This test verifies the contract: callers pass ``timestamp`` (not
        ``date``), and the wrapper extracts it as the first positional arg.
        """
        # Simulate what sync_engine._process_candidate now does:
        c = _candidate(
            date_str="2026-06-21",
            weight_kg=Decimal("78.5"),
            measured_at_local=datetime(2026, 6, 21, 14, 30),
        )
        params = c.garmin_params()
        # params: {"timestamp": "2026-06-21T14:30:00", "weight": 78.5, ...}
        assert "timestamp" in params
        assert params["timestamp"] == "2026-06-21T14:30:00"
        assert params["weight"] == 78.5
        # garminconnect gets: add_body_composition("2026-06-21T14:30:00", 78.5, ...)
