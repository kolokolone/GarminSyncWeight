"""Persistence layer for sync attempts and results."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlite3 import Connection
from typing import Any, NamedTuple


class JobResult(NamedTuple):
    run_id: str
    job_id: int

from app.storage.db import init_db


class SyncStore:
    """Sync event persistence for idempotency and audit trail."""

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "withings_tokens.db"
        self._conn: Connection | None = None

    @property
    def conn(self) -> Connection:
        if self._conn is None:
            self._conn = init_db(self._db_path)
        return self._conn

    def event_exists(self, idempotency_key: str) -> bool:
        """Check whether this key was really handled by a prior sync."""
        row = self.conn.execute(
            """SELECT 1 FROM sync_events
               WHERE idempotency_key = ?
                 AND status IN ('synced', 'skipped_existing')
               LIMIT 1""",
            (idempotency_key,),
        ).fetchone()
        return row is not None

    def start_attempt(self, start_date: str, end_date: str) -> int:
        now = datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            """INSERT INTO sync_attempts (started_at, start_date, end_date, status)
               VALUES (?, ?, ?, ?)""",
            (now, start_date, end_date, "running"),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def finish_attempt(
        self,
        attempt_id: int,
        status: str,
        summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """UPDATE sync_attempts
               SET completed_at = ?, status = ?, summary_json = ?, error_message = ?
               WHERE id = ?""",
            (
                datetime.now(UTC).isoformat(),
                status,
                json.dumps(summary, ensure_ascii=False) if summary else None,
                error_message,
                attempt_id,
            ),
        )
        self.conn.commit()

    def save_event(
        self,
        idempotency_key: str,
        source: str,
        source_measure_group_id: str | None,
        source_measured_at_utc: str | None,
        garmin_date: str,
        weight_kg: str | None,
        status: str,
        garmin_write_method: str | None = None,
        garmin_measure_id: str | None = None,
        garmin_response: dict[str, Any] | None = None,
        error_message: str | None = None,
        report: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update a sync event by idempotency key."""
        now = datetime.now(UTC).isoformat()
        payload_hash = self.payload_hash(report or garmin_response or {})
        self.conn.execute(
            """INSERT INTO sync_events
               (idempotency_key, source, withings_measure_id,
                source_measured_at_utc, local_date, weight_kg, payload_hash,
                status, garmin_write_method, garmin_measure_id,
                garmin_response_json, error_message, report_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(idempotency_key) DO UPDATE SET
                status = excluded.status,
                garmin_write_method = excluded.garmin_write_method,
                garmin_measure_id = excluded.garmin_measure_id,
                garmin_response_json = excluded.garmin_response_json,
                error_message = excluded.error_message,
                report_json = excluded.report_json,
                updated_at = excluded.updated_at""",
            (
                idempotency_key,
                source,
                source_measure_group_id,
                source_measured_at_utc,
                garmin_date,
                weight_kg,
                payload_hash,
                status,
                garmin_write_method,
                garmin_measure_id,
                json.dumps(garmin_response) if garmin_response else None,
                error_message,
                json.dumps(report) if report else None,
                now,
                now,
            ),
        )
        self.conn.commit()

    def get_event_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        """Return a sync event by its idempotency key."""
        row = self.conn.execute(
            "SELECT * FROM sync_events WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def last_sync_time(self) -> str | None:
        """Return the ISO timestamp of the most recent sync event."""
        row = self.conn.execute(
            """SELECT created_at FROM sync_events
               WHERE status = 'synced'
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return row["created_at"] if row else None

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    # ── sync_jobs (remplace progressivement sync_attempts) ──────────

    def create_job(self, start_date: str, end_date: str, tz_name: str | None = None,
                   trigger: str = "manual") -> JobResult:
        """Create a sync_job and return JobResult(run_id, job_id)."""
        run_id = uuid.uuid4().hex[:16]
        now = datetime.now(UTC).isoformat()
        cur = self.conn.execute(
            """INSERT INTO sync_jobs
               (run_id, started_at, start_date, end_date, tz_name, trigger, status)
               VALUES (?, ?, ?, ?, ?, ?, 'running')""",
            (run_id, now, start_date, end_date, tz_name, trigger),
        )
        self.conn.commit()
        job_id = cur.lastrowid or 0
        return JobResult(run_id, job_id)

    def finish_job(self, run_id: str, status: str, summary: dict[str, Any] | None = None,
                   error_message: str | None = None, report_json: str | None = None) -> None:
        """Mark a sync_job as completed/failed with result counts."""
        now = datetime.now(UTC).isoformat()
        # Compute duration from started_at
        started = self.conn.execute(
            "SELECT started_at FROM sync_jobs WHERE run_id = ?", (run_id,)
        ).fetchone()
        duration = None
        if started and started["started_at"]:
            duration = (datetime.fromisoformat(now) - datetime.fromisoformat(started["started_at"])).total_seconds()
        self.conn.execute(
            """UPDATE sync_jobs
               SET completed_at = ?,
                   status = ?,
                   candidates_total = ?,
                   candidates_synced = ?,
                   candidates_skipped = ?,
                   candidates_conflict = ?,
                   candidates_invalid = ?,
                   candidates_failed = ?,
                   duration_seconds = ?,
                   error_message = ?,
                   report_json = ?
               WHERE run_id = ?""",
            (
                now,
                status,
                (summary.get("candidates_count") if summary else None),
                (summary.get("synced_count") if summary else None),
                (summary.get("skipped_existing_count") if summary else None),
                (summary.get("conflicts_count") if summary else None),
                (summary.get("invalid_count") if summary else None),
                (summary.get("failed_count") if summary else None),
                duration,
                error_message,
                report_json,
                run_id,
            ),
        )
        self.conn.commit()

    def get_job(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM sync_jobs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM sync_jobs ORDER BY started_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_job_stats(self) -> dict[str, Any]:
        """Aggregated statistics across all sync_jobs."""
        row = self.conn.execute(
            """SELECT
                   COUNT(*)                                              AS total_jobs,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS successful_jobs,
                   SUM(CASE WHEN status = 'failed'     THEN 1 ELSE 0 END) AS failed_jobs,
                   SUM(candidates_synced)                                AS total_synced,
                   SUM(candidates_skipped)                               AS total_skipped,
                   SUM(candidates_conflict)                              AS total_conflicts,
                   SUM(candidates_invalid)                               AS total_invalid,
                   SUM(candidates_failed)                                AS total_failed,
                   MAX(started_at)                                       AS last_sync_at
               FROM sync_jobs"""
        ).fetchone()
        return dict(row)

    # ── sync_candidates (remplace progressivement sync_events) ─────

    def save_candidate(
        self,
        idempotency_key: str,
        job_id: int | None = None,
        source: str = "withings",
        source_measure_group_id: str | None = None,
        source_device_id: str | None = None,
        date: str | None = None,
        measured_at_local: str | None = None,
        weight_kg: str | None = None,
        fat_percent: str | None = None,
        muscle_mass_kg: str | None = None,
        bone_mass_kg: str | None = None,
        hydration_percent: str | None = None,
        bmi: str | None = None,
        mapped_fields: dict[str, Any] | None = None,
        ignored_fields: dict[str, Any] | None = None,
        null_fields: list[str] | None = None,
        mapping_warnings: list[str] | None = None,
        dedup_status: str | None = None,
        decision: str | None = None,
        reason: str | None = None,
        garmin_write_method: str | None = None,
        garmin_params: dict[str, Any] | None = None,
        garmin_response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> int:
        """Insert or ignore a sync_candidate. Returns the row id."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO sync_candidates
               (job_id, idempotency_key, source,
                source_measure_group_id, source_device_id,
                date, measured_at_local,
                weight_kg, fat_percent, muscle_mass_kg, bone_mass_kg,
                hydration_percent, bmi,
                mapped_fields_json, ignored_fields_json, null_fields_json,
                mapping_warnings_json,
                dedup_status, decision, reason,
                garmin_write_method, garmin_params_json,
                garmin_response_json, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job_id,
                idempotency_key,
                source,
                source_measure_group_id,
                source_device_id,
                date,
                measured_at_local,
                weight_kg,
                fat_percent,
                muscle_mass_kg,
                bone_mass_kg,
                hydration_percent,
                bmi,
                json.dumps(mapped_fields, ensure_ascii=False) if mapped_fields else None,
                json.dumps(ignored_fields, ensure_ascii=False) if ignored_fields else None,
                json.dumps(null_fields, ensure_ascii=False) if null_fields else None,
                json.dumps(mapping_warnings, ensure_ascii=False) if mapping_warnings else None,
                dedup_status,
                decision,
                reason,
                garmin_write_method,
                json.dumps(garmin_params, ensure_ascii=False) if garmin_params else None,
                json.dumps(garmin_response, ensure_ascii=False) if garmin_response else None,
                error_message,
            ),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def candidate_exists(self, idempotency_key: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sync_candidates WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        return row is not None

    def get_candidate_by_key(self, idempotency_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM sync_candidates WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row else None

    def get_candidates_by_job(self, job_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM sync_candidates WHERE job_id = ? ORDER BY date ASC",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_candidate_stats(self) -> dict[str, Any]:
        row = self.conn.execute(
            """SELECT
                   COUNT(*)                                          AS total_candidates,
                   SUM(CASE WHEN decision='sync'    THEN 1 ELSE 0 END) AS synced,
                   SUM(CASE WHEN decision='skip'    THEN 1 ELSE 0 END) AS skipped,
                   SUM(CASE WHEN decision='garmin_write'
                                 THEN 1 ELSE 0 END)                   AS conflicts,
                   COUNT(error_message)                              AS with_errors
               FROM sync_candidates"""
        ).fetchone()
        return dict(row)

    def get_candidate_daily_breakdown(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily breakdown of candidate decisions for the last N days."""
        threshold = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            """SELECT DATE(created_at) AS day, decision, COUNT(*) AS count
               FROM sync_candidates
               WHERE created_at >= ?
               GROUP BY DATE(created_at), decision
               ORDER BY day ASC""",
            (threshold,),
        ).fetchall()
        days_map: dict[str, dict[str, int]] = {}
        for row in rows:
            day = row["day"]
            if day not in days_map:
                days_map[day] = {}
            days_map[day][row["decision"] or "unknown"] = row["count"]
        return [
            {"date": day, **statuses} for day, statuses in sorted(days_map.items())
        ]

    # ── sync_decisions (traçabilité granulaire) ─────────────────────

    def save_decision(
        self,
        candidate_id: int,
        decision: str,
        reason: str,
        weight_epsilon: float | None = None,
        existing_weight: float | None = None,
        existing_date: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO sync_decisions
               (candidate_id, decision, reason, weight_epsilon, existing_weight, existing_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (candidate_id, decision, reason, weight_epsilon, existing_weight, existing_date),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def get_decisions_by_candidate(self, candidate_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM sync_decisions WHERE candidate_id = ? ORDER BY created_at ASC",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Close ───────────────────────────────────────────────────────

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
