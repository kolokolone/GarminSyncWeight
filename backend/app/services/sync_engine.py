"""Controlled Withings → Garmin synchronization engine."""

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import Settings
from app.models.garmin import GarminBodyCompositionCandidate, GarminWeighIn
from app.models.sync import DedupStatus, SyncCandidate, SyncReport, SyncSummary
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
    """Orchestrates active checks, reads, dedupe, writes and audit trail."""

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

    async def run_sync(
        self,
        start_date: str,
        end_date: str,
        tz_name: str | None = None,
    ) -> SyncReport:
        """Run a real, guarded, idempotent synchronization."""
        tz = self._load_timezone(tz_name or self._settings.app_timezone)
        start_day = self._parse_date(start_date)
        end_day = self._parse_date(end_date)
        if end_day < start_day:
            raise ValueError("end_date must be greater than or equal to start_date")

        attempt_id = self._sync_store.start_attempt(start_date, end_date)
        _log().info("Sync starting — period=%s → %s", start_date, end_date)
        try:
            prerequisites = await self._check_prerequisites()
            self._require_connected(prerequisites)

            dt_start, dt_end = self._local_day_window(start_day, end_day, tz)
            withings_raw_groups = await self._withings_client.get_measurements(dt_start, dt_end)
            parsed = self._parser.parse_measure_groups(withings_raw_groups)
            parsed = self._filter_period(self._apply_per_day_strategy(parsed), start_day, end_day)

            candidates = self._map_measurements(parsed)
            garmin_weigh_ins = await self._fetch_garmin_weigh_ins(start_day, end_day)
            garmin_bc = await self._garmin.get_body_composition(
                start_day - timedelta(days=self._settings.garmin_lookback_days),
                end_day + timedelta(days=self._settings.garmin_lookahead_days),
            )

            report_candidates: list[SyncCandidate] = []
            summary = SyncSummary(
                withings_raw_count=len(withings_raw_groups),
                withings_parsed_count=len(parsed),
                garmin_existing_count=len(garmin_weigh_ins) + len(garmin_bc),
                candidates_count=len(candidates),
            )

            for candidate in candidates:
                item = await self._process_candidate(
                    candidate,
                    garmin_weigh_ins,
                    garmin_bc,
                    summary,
                )
                report_candidates.append(item)

            report = SyncReport(
                period={"start_date": start_date, "end_date": end_date, "timezone": str(tz)},
                prerequisites=prerequisites,
                withings={
                    "raw_groups_count": len(withings_raw_groups),
                    "parsed_measurements_count": len(parsed),
                    "measurements": [self._measurement_summary(m) for m in parsed],
                },
                garmin={
                    "existing_weigh_ins_count": len(garmin_weigh_ins),
                    "existing_body_composition_count": len(garmin_bc),
                },
                candidates=report_candidates,
                summary=summary,
            )
            self._report_builder.save(report)
            self._sync_store.finish_attempt(attempt_id, "completed", report.summary.model_dump())
            _log().info(
                "Sync completed — synced=%d existing=%d conflicts=%d invalid=%d failed=%d",
                summary.synced_count,
                summary.skipped_existing_count,
                summary.conflicts_count,
                summary.invalid_count,
                summary.failed_count,
            )
            return report
        except Exception as exc:
            self._sync_store.finish_attempt(attempt_id, "failed", error_message=str(exc))
            _log().error("Sync refused or failed: %s", exc)
            raise

    async def _check_prerequisites(self) -> dict[str, Any]:
        withings = await self._withings_auth.check_connection()
        garmin = await self._garmin.check_connection()
        return {"withings": withings, "garmin": garmin}

    @staticmethod
    def _require_connected(prerequisites: dict[str, Any]) -> None:
        failures = []
        for name in ("withings", "garmin"):
            status = prerequisites.get(name, {})
            if not status.get("connected"):
                failures.append(f"{name}: {status.get('message', 'not connected')}")
        if failures:
            raise RuntimeError("Synchronisation refusée: " + "; ".join(failures))

    async def _fetch_garmin_weigh_ins(self, start_day: date, end_day: date) -> list[GarminWeighIn]:
        search_start = start_day - timedelta(days=self._settings.garmin_lookback_days)
        search_end = end_day + timedelta(days=self._settings.garmin_lookahead_days)
        results: list[GarminWeighIn] = []
        current = search_start
        while current <= search_end:
            results.extend(await self._garmin.get_daily_weigh_ins(current))
            current += timedelta(days=1)
        return results

    def _map_measurements(
        self,
        measurements: list[BodyCompositionMeasurement],
    ) -> list[GarminBodyCompositionCandidate]:
        candidates: list[GarminBodyCompositionCandidate] = []
        for measurement in measurements:
            try:
                candidates.append(self._mapper.map(measurement))
            except Exception as exc:
                _log().error(
                    "Mapping failed for measurement %s: %s",
                    measurement.source_measure_group_id,
                    exc,
                )
        return candidates

    async def _process_candidate(
        self,
        candidate: GarminBodyCompositionCandidate,
        garmin_weigh_ins: list[GarminWeighIn],
        garmin_bc: list[Any],
        summary: SyncSummary,
    ) -> SyncCandidate:
        status = self._dedup.classify(candidate, garmin_weigh_ins, garmin_bc)
        if self._dedup.should_skip(status):
            decision, reason = self._decision_for_status(status)
            self._increment_summary(summary, decision)
            self._save_candidate_event(candidate, decision, reason)
            return self._candidate_report(candidate, status, decision, reason)

        garmin_params = candidate.garmin_params()
        garmin_params["date"] = candidate.date.isoformat()
        try:
            response = await self._garmin.add_body_composition(**garmin_params)
            summary.synced_count += 1
            self._save_candidate_event(candidate, "synced", "Écriture Garmin réussie.", response)
            return self._candidate_report(
                candidate,
                status,
                "synced",
                "Écriture Garmin réussie.",
                response,
            )
        except Exception as exc:
            summary.failed_count += 1
            self._save_candidate_event(
                candidate,
                "failed",
                "Écriture Garmin échouée.",
                error_message=str(exc),
            )
            return self._candidate_report(
                candidate,
                status,
                "failed",
                "Écriture Garmin échouée.",
                error_message=str(exc),
            )

    @staticmethod
    def _decision_for_status(status: DedupStatus) -> tuple[str, str]:
        if status in (
            "duplicate_exact_or_near",
            "duplicate_body_composition",
            "already_synced_by_garminsync",
        ):
            return "skipped_existing", "Mesure déjà présente ou déjà traitée."
        if status in ("possible_duplicate", "conflict_same_day"):
            return "skipped_conflict", "Mesure Garmin proche ou différente le même jour."
        return "invalid", "Mesure source incomplète ou incohérente."

    @staticmethod
    def _increment_summary(summary: SyncSummary, decision: str) -> None:
        if decision == "skipped_existing":
            summary.skipped_existing_count += 1
        elif decision == "skipped_conflict":
            summary.conflicts_count += 1
        elif decision == "invalid":
            summary.invalid_count += 1

    def _save_candidate_event(
        self,
        candidate: GarminBodyCompositionCandidate,
        status: str,
        reason: str,
        garmin_response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        self._sync_store.save_event(
            idempotency_key=candidate.idempotency_key,
            source="withings",
            source_measure_group_id=candidate.source_measure_group_id,
            source_measured_at_utc=(
                candidate.measured_at_local.isoformat() if candidate.measured_at_local else None
            ),
            garmin_date=candidate.date.isoformat(),
            weight_kg=str(candidate.weight) if candidate.weight else None,
            status=status,
            garmin_write_method="add_body_composition" if status == "synced" else None,
            garmin_response=garmin_response,
            error_message=error_message,
            report={"reason": reason, "mapped_fields": candidate.mapped_fields},
        )

    @staticmethod
    def _candidate_report(
        candidate: GarminBodyCompositionCandidate,
        dedup_status: DedupStatus,
        decision: str,
        reason: str,
        garmin_response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> SyncCandidate:
        return SyncCandidate(
            date=candidate.date.isoformat(),
            measured_at_local=(
                candidate.measured_at_local.isoformat() if candidate.measured_at_local else None
            ),
            source_measure_group_id=candidate.source_measure_group_id,
            mapped_fields=candidate.mapped_fields,
            ignored_fields=candidate.ignored_fields,
            null_fields=candidate.null_fields,
            warnings=candidate.mapping_warnings,
            dedup_status=dedup_status,
            decision=decision,  # type: ignore[arg-type]
            reason=reason,
            garmin_call={"method": "add_body_composition", "params": candidate.garmin_params()},
            garmin_response=garmin_response,
            error_message=error_message,
            idempotency_key=candidate.idempotency_key,
        )

    def _apply_per_day_strategy(
        self,
        measurements: list[BodyCompositionMeasurement],
    ) -> list[BodyCompositionMeasurement]:
        if self._settings.withings_per_day_strategy != "latest_per_day":
            return measurements
        by_date: dict[date, BodyCompositionMeasurement] = {}
        for measurement in measurements:
            existing = by_date.get(measurement.garmin_date)
            if existing is None or measurement.measured_at_utc > existing.measured_at_utc:
                by_date[measurement.garmin_date] = measurement
        return list(by_date.values())

    @staticmethod
    def _filter_period(
        measurements: list[BodyCompositionMeasurement],
        start_day: date,
        end_day: date,
    ) -> list[BodyCompositionMeasurement]:
        return [m for m in measurements if start_day <= m.garmin_date <= end_day]

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"Invalid date format: {value}. Expected YYYY-MM-DD.") from exc

    @staticmethod
    def _load_timezone(tz_name: str) -> tzinfo:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            _log().warning("Timezone '%s' unavailable; falling back to UTC", tz_name)
            return UTC

    @staticmethod
    def _local_day_window(start_day: date, end_day: date, tz: tzinfo) -> tuple[datetime, datetime]:
        local_start = datetime.combine(start_day, time.min, tzinfo=tz)
        local_end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)
        return local_start.astimezone(UTC), local_end.astimezone(UTC)

    @staticmethod
    def _measurement_summary(m: BodyCompositionMeasurement) -> dict[str, Any]:
        return {
            "group_id": m.source_measure_group_id,
            "date_local": m.measured_at_local.isoformat(),
            "weight_kg": str(m.weight_kg) if m.weight_kg else None,
            "fat_percent": str(m.fat_percent) if m.fat_percent else None,
            "muscle_mass_kg": str(m.muscle_mass_kg) if m.muscle_mass_kg else None,
            "bone_mass_kg": str(m.bone_mass_kg) if m.bone_mass_kg else None,
        }
