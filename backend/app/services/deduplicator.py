"""Duplicate detection logic for Garmin sync candidates.

Compares a ``GarminBodyCompositionCandidate`` against existing Garmin
data (weigh-ins, body composition) and local sync history to determine
whether the candidate is new, a duplicate, or in conflict.

Thresholds are configurable via settings:
  - WEIGHT_DUPLICATE_EPSILON_KG  (default 0.05)
  - WEIGHT_CONFLICT_EPSILON_KG   (default 0.2)
  - GARMIN_LOOKBACK_DAYS         (default 7)
  - GARMIN_LOOKAHEAD_DAYS        (default 1)
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.models.garmin import GarminBodyComposition, GarminBodyCompositionCandidate, GarminWeighIn
from app.models.sync import DedupStatus
from app.storage.sync_store import SyncStore

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("sync")
    return _logger


class Deduplicator:
    """Compare candidates against existing Garmin data to determine action."""

    def __init__(self, settings: Settings, sync_store: SyncStore) -> None:
        self._settings = settings
        self._sync_store = sync_store

    def classify(
        self,
        candidate: GarminBodyCompositionCandidate,
        weigh_ins: list[GarminWeighIn],
        body_compositions: list[GarminBodyComposition],
    ) -> DedupStatus:
        """Classify a candidate against existing Garmin data.

        Returns a ``DedupStatus`` string.
        """
        # ── Basic validation ───────────────────────────────────
        if not candidate.has_weight():
            return "invalid_missing_weight"

        if candidate.weight is not None and (
            candidate.weight < Decimal("20") or candidate.weight > Decimal("300")
        ):
            return "invalid_outlier"

        # ── Already synced by us? ──────────────────────────────
        if self._sync_store.event_exists(candidate.idempotency_key):
            return "already_synced_by_garminsync"

        # ── Compare against existing weigh-ins ─────────────────
        same_day_weigh_ins = [w for w in weigh_ins if w.date == candidate.date]

        for wi in same_day_weigh_ins:
            if wi.weight_kg is None:
                continue
            diff = abs(candidate.weight - wi.weight_kg) if candidate.weight else Decimal("Infinity")
            epsilon = Decimal(str(self._settings.weight_duplicate_epsilon_kg))
            conflict_epsilon = Decimal(str(self._settings.weight_conflict_epsilon_kg))

            if diff <= epsilon:
                return "duplicate_exact_or_near"
            if diff <= conflict_epsilon:
                return "possible_duplicate"
            # diff > conflict_epsilon
            return "conflict_same_day"

        # ── Compare against existing body composition ──────────
        same_day_bc = [bc for bc in body_compositions if bc.date == candidate.date]

        for bc in same_day_bc:
            if bc.weight_kg is not None and candidate.weight is not None:
                diff = abs(candidate.weight - bc.weight_kg)
                epsilon = Decimal(str(self._settings.weight_duplicate_epsilon_kg))
                if diff <= epsilon:
                    # Same weight — likely duplicate
                    return "duplicate_body_composition"
                conflict_epsilon = Decimal(str(self._settings.weight_conflict_epsilon_kg))
                if diff <= conflict_epsilon:
                    return "possible_duplicate"
                return "conflict_same_day"

        # ── No existing data for this day ──────────────────────
        return "new_candidate"

    def search_window(self) -> tuple[date, date]:
        """Return the (start, end) date window for querying Garmin data."""
        today = date.today()
        start = today - timedelta(days=self._settings.garmin_lookback_days)
        end = today + timedelta(days=self._settings.garmin_lookahead_days)
        return start, end

    @staticmethod
    def is_duplicate_or_conflict(status: DedupStatus) -> bool:
        """Return True if the status indicates existing data."""
        return status in (
            "duplicate_exact_or_near",
            "possible_duplicate",
            "duplicate_body_composition",
            "conflict_same_day",
        )

    @staticmethod
    def should_skip(status: DedupStatus) -> bool:
        """Return True if this candidate should NOT be written."""
        return status in (
            "duplicate_exact_or_near",
            "possible_duplicate",
            "duplicate_body_composition",
            "conflict_same_day",
            "invalid_missing_weight",
            "invalid_date",
            "invalid_outlier",
            "already_synced_by_garminsync",
        )
