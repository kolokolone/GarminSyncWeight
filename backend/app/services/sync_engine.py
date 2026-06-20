"""Sync engine: orchestrates the Withings→Garmin pipeline.

This is the central coordinator that wires together:
  1. Fetch Withings measurements
  2. Parse raw groups into canonical models
  3. Map to Garmin candidates
  4. Fetch existing Garmin data
  5. Deduplicate / conflict-detect
  6. Build dry-run report (or optionally execute)

In v1, ONLY dry-run mode is active. Actual writes are guarded
by multiple safety checks.
"""

from datetime import date, datetime, timezone
from typing import Any, Literal

from app.config import Settings
from app.models.garmin import GarminBodyCompositionCandidate
from app.models.sync import (
    DedupStatus,
    DryRunCandidate,
    DryRunReport,
    DryRunSummary,
    SyncEventStatus,
)
from app.models.withings import BodyCompositionMeasurement
from app.services.deduplicator import Deduplicator
from app.services.garmin_client import GarminClient
from app.services.mapper import WithingsToGarminMapper
from app.services.report_builder import ReportBuilder
from app.services.withings_auth import WithingsAuthService
from app.services.withings_client import WithingsClient
from app.services.withings_parser import WithingsParser
from app.storage.sync_store import SyncStore

_logger = None


def _log() -> Any:
    global _logger
    if _logger is None:
        from app.logging_config import get_logger

        _logger = get_logger("sync")
    return _logger


class SyncEngine:
    """Orchestrates the full Withings→Garmin sync pipeline.

    In v1, only ``run_dry_run()`` is available.
    """

    def __init__(
        self,
        settings: Settings,
        withings_auth: WithingsAuthService,
        withings_client: WithingsClient,
        parser: WithingsParser,
        mapper: WithingsToGarminMapper,
        garmin_client: GarminClient,
        deduplicator: Deduplicator,
        sync_store: SyncStore,
        report_builder: ReportBuilder,
    ) -> None:
        self._settings = settings
        self._withings_auth = withings_auth
        self._withings_client = withings_client
        self._parser = parser
        self._mapper = mapper
        self._garmin = garmin_client
        self._dedup = deduplicator
        self._sync_store = sync_store
        self._report_builder = report_builder

    # ── Public API ─────────────────────────────────────────────

    async def run_dry_run(
        self,
        start_date: str,
        end_date: str,
        tz_name: str | None = None,
    ) -> DryRunReport:
        """Execute a dry-run of the Withings→Garmin sync pipeline.
    
        This is the main entry point for v1. It:
        - Fetches Withings data
        - Parses, maps, checks duplicates
        - Builds a detailed report
        - NEVER writes to Garmin
    
        Args:
            start_date: ISO date string (YYYY-MM-DD).
            end_date: ISO date string (YYYY-MM-DD).
            tz_name: Optional timezone override (default: settings value).

        Returns:
            A ``DryRunReport`` with full details.
        """
        _log().info(
            "DRY-RUN starting — period=%s → %s",
            start_date,
            end_date,
        )

        # ── 1. Parse dates ─────────────────────────────────────
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)  # noqa: UP017
            dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)  # noqa: UP017
        except ValueError as exc:
            raise ValueError(f"Invalid date format: {exc}") from exc

        tz = tz_name or self._settings.app_timezone

        # ── 2. Fetch Withings data ─────────────────────────────
        withings_raw_groups: list[dict[str, Any]] = []
        if self._withings_auth.has_token():
            try:
                withings_raw_groups = await self._withings_client.get_measurements(dt_start, dt_end)
            except Exception as exc:
                _log().error("Failed to fetch Withings data: %s", exc)
        else:
            _log().warning("No Withings token — skipping Withings fetch")

        # ── 3. Parse measurements ──────────────────────────────
        parsed: list[BodyCompositionMeasurement] = []
        if withings_raw_groups:
            parsed = self._parser.parse_measure_groups(withings_raw_groups)
            _log().info(
                "Parsed %d measurements from %d raw groups",
                len(parsed), len(withings_raw_groups),
            )

        # ── 4. Apply per-day strategy ─────────────────────────
        if self._settings.withings_per_day_strategy == "latest_per_day":
            parsed = self._keep_latest_per_day(parsed)

        # ── 5. Map to Garmin candidates ───────────────────────
        candidates: list[GarminBodyCompositionCandidate] = []
        for m in parsed:
            try:
                candidate = self._mapper.map(m)
                candidates.append(candidate)
            except Exception as exc:
                _log().error(
                    "Mapping failed for measurement %s: %s",
                    m.source_measure_group_id, exc,
                )

        # ── 6. Fetch existing Garmin data for search window ───
        search_start, search_end = self._dedup.search_window()
        garmin_weigh_ins = await self._garmin.get_daily_weigh_ins(search_end)  # single date
        garmin_bc = await self._garmin.get_body_composition(search_start, search_end)
        _log().info(
            "Garmin data: %d weigh-ins, %d body compositions in window",
            len(garmin_weigh_ins),
            len(garmin_bc),
        )

        # ── 7. Deduplicate each candidate ─────────────────────
        report_candidates: list[DryRunCandidate] = []
        summary = DryRunSummary()

        for candidate in candidates:
            status = self._dedup.classify(candidate, garmin_weigh_ins, garmin_bc)
            decision: Literal["would_write", "skip"]
            should_skip = self._dedup.should_skip(status)

            if should_skip:
                decision = "skip"
                self._increment_summary(summary, status)
            else:
                decision = "would_write"
                summary.would_write_count += 1

            # Build the Garmin call description
            garmin_method = candidate.garmin_write_method() if decision == "would_write" else "none"
            garmin_call = {
                "method": garmin_method,
                "params": candidate.garmin_params() if decision == "would_write" else {},
            }

            # Save to sync_events table
            self._sync_store.save_event(
                idempotency_key=candidate.idempotency_key,
                source="withings",
                source_measure_group_id=candidate.source_measure_group_id,
                source_measured_at_utc=(
                    candidate.measured_at_local.isoformat()
                    if candidate.measured_at_local else None
                ),
                garmin_date=candidate.date.isoformat(),
                weight_kg=str(candidate.weight) if candidate.weight else None,
                status=f"dry_run_{status}" if should_skip else "dry_run_new_candidate",
                dry_run=True,
                garmin_write_method=garmin_method if decision == "would_write" else None,
            )

            warnings = list(candidate.mapping_warnings)
            if warnings:
                summary.warnings_count += len(warnings)

            report_candidates.append(
                DryRunCandidate(
                    date=candidate.date.isoformat(),
                    measured_at_local=(
                        candidate.measured_at_local.isoformat()
                        if candidate.measured_at_local else None
                    ),
                    source_measure_group_id=candidate.source_measure_group_id,
                    mapped_fields=candidate.mapped_fields,
                    ignored_fields=candidate.ignored_fields,
                    null_fields=candidate.null_fields,
                    warnings=warnings,
                    dedup_status=status,
                    decision=decision,
                    garmin_call=garmin_call,
                    idempotency_key=candidate.idempotency_key,
                )
            )

        # ── 8. Build report ──────────────────────────────────
        report = DryRunReport(
            period={
                "start_date": start_date,
                "end_date": end_date,
                "timezone": tz if isinstance(tz, str) else str(tz),
            },
            withings={
                "raw_groups_count": len(withings_raw_groups),
                "parsed_measurements_count": len(parsed),
                "measurements": [
                    {
                        "group_id": m.source_measure_group_id,
                        "date_local": m.measured_at_local.isoformat(),
                        "weight_kg": str(m.weight_kg) if m.weight_kg else None,
                        "fields": self._measurement_fields(m),
                    }
                    for m in parsed
                ],
            },
            garmin={
                "daily_weigh_ins": [
                    {"date": str(w.date), "weight_kg": str(w.weight_kg) if w.weight_kg else None}
                    for w in garmin_weigh_ins
                ],
                "body_composition": [
                    {"date": str(bc.date), "weight_kg": str(bc.weight_kg) if bc.weight_kg else None}
                    for bc in garmin_bc
                ],
            },
            candidates=report_candidates,
            summary=summary,
        )

        # ── 9. Save report to disk ────────────────────────────
        self._report_builder.save(report)

        _log().info(
            "DRY-RUN completed — would_write=%d skipped=%d conflicts=%d invalid=%d",
            summary.would_write_count,
            summary.skipped_duplicates_count,
            summary.conflicts_count,
            summary.invalid_count,
        )
        return report

    # ── Internal helpers ───────────────────────────────────────

    @staticmethod
    def _keep_latest_per_day(
        measurements: list[BodyCompositionMeasurement],
    ) -> list[BodyCompositionMeasurement]:
        """Keep only the latest measurement per garmin_date."""
        by_date: dict[date, BodyCompositionMeasurement] = {}
        for m in measurements:
            existing = by_date.get(m.garmin_date)
            if existing is None or m.measured_at_utc > existing.measured_at_utc:
                by_date[m.garmin_date] = m
        return list(by_date.values())

    @staticmethod
    def _increment_summary(summary: DryRunSummary, status: DedupStatus) -> None:
        if status in (
            "duplicate_exact_or_near", "duplicate_body_composition",
            "already_synced_by_garminsync",
        ):
            summary.skipped_duplicates_count += 1
        elif status == "possible_duplicate":
            summary.possible_duplicates_count += 1
        elif status == "conflict_same_day":
            summary.conflicts_count += 1
        elif status.startswith("invalid"):
            summary.invalid_count += 1

    @staticmethod
    def _measurement_fields(m: BodyCompositionMeasurement) -> dict[str, str | None]:
        return {
            "weight_kg": str(m.weight_kg) if m.weight_kg else None,
            "fat_percent": str(m.fat_percent) if m.fat_percent else None,
            "fat_mass_kg": str(m.fat_mass_kg) if m.fat_mass_kg else None,
            "muscle_mass_kg": str(m.muscle_mass_kg) if m.muscle_mass_kg else None,
            "bone_mass_kg": str(m.bone_mass_kg) if m.bone_mass_kg else None,
            "hydration_mass_kg": str(m.hydration_mass_kg) if m.hydration_mass_kg else None,
            "bmi": str(m.bmi) if m.bmi else None,
        }

    @staticmethod
    def _dedup_status_to_event_status(status: DedupStatus) -> SyncEventStatus:
        mapping: dict[DedupStatus, SyncEventStatus] = {
            "new_candidate": "dry_run_new_candidate",
            "duplicate_exact_or_near": "dry_run_duplicate",
            "possible_duplicate": "dry_run_possible_duplicate",
            "duplicate_body_composition": "dry_run_duplicate",
            "conflict_same_day": "dry_run_conflict",
            "invalid_missing_weight": "dry_run_invalid",
            "invalid_date": "dry_run_invalid",
            "invalid_outlier": "dry_run_invalid",
            "already_synced_by_garminsync": "dry_run_duplicate",
        }
        return mapping.get(status, "dry_run_invalid")
