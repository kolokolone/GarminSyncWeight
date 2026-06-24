"""SQLite database initialisation and connection management."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SYNC_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    withings_measure_id TEXT,
    source_measured_at_utc TEXT,
    local_date TEXT NOT NULL,
    weight_kg TEXT,
    payload_hash TEXT,
    status TEXT NOT NULL,
    garmin_write_method TEXT,
    garmin_measure_id TEXT,
    garmin_response_json TEXT,
    error_message TEXT,
    report_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ATTEMPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT,
    error_message TEXT
);
"""

TOKEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    userid          TEXT,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    token_type      TEXT NOT NULL DEFAULT 'Bearer',
    expires_at      REAL NOT NULL,
    scope           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_oauth_states (
    state       TEXT PRIMARY KEY,
    created_at  REAL NOT NULL
);
"""

GARMIN_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS garmin_measurements_cache (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT    NOT NULL,
    source_type      TEXT    NOT NULL,
    data_json        TEXT    NOT NULL,
    fetched_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    cache_expires_at TEXT    NOT NULL,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source_type)
);
"""

WITHINGS_MEAS_SCHEMA = """
CREATE TABLE IF NOT EXISTS withings_measurements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_measure_group_id TEXT    UNIQUE NOT NULL,
    source_device_id        TEXT,
    date                    TEXT    NOT NULL,
    measured_at_utc         TEXT    NOT NULL,
    measured_at_local       TEXT    NOT NULL,
    weight_kg               TEXT,
    fat_percent             TEXT,
    fat_mass_kg             TEXT,
    fat_free_mass_kg        TEXT,
    muscle_mass_kg          TEXT,
    bone_mass_kg            TEXT,
    hydration_mass_kg       TEXT,
    hydration_percent       TEXT,
    bmi                     TEXT,
    visceral_fat_mass       TEXT,
    basal_met               TEXT,
    active_met              TEXT,
    metabolic_age           INTEGER,
    visceral_fat_rating     INTEGER,
    physique_rating         INTEGER,
    raw_json                TEXT,
    fetched_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_withings_meas_date ON withings_measurements(date);
CREATE INDEX IF NOT EXISTS idx_withings_meas_utc  ON withings_measurements(measured_at_utc);
"""

SYNC_JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT    UNIQUE NOT NULL,
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    tz_name         TEXT,
    trigger         TEXT    NOT NULL DEFAULT 'manual',
    status          TEXT    NOT NULL DEFAULT 'running',
    candidates_total    INTEGER DEFAULT 0,
    candidates_synced   INTEGER DEFAULT 0,
    candidates_skipped  INTEGER DEFAULT 0,
    candidates_conflict INTEGER DEFAULT 0,
    candidates_invalid  INTEGER DEFAULT 0,
    candidates_failed   INTEGER DEFAULT 0,
    duration_seconds    REAL,
    error_message   TEXT,
    report_json     TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_dates  ON sync_jobs(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status ON sync_jobs(status);
"""

SYNC_CANDIDATES_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_candidates (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id                  INTEGER REFERENCES sync_jobs(id),
    idempotency_key         TEXT    UNIQUE NOT NULL,
    source                  TEXT    NOT NULL DEFAULT 'withings',
    source_measure_group_id TEXT,
    source_device_id        TEXT,
    date                    TEXT    NOT NULL,
    measured_at_local       TEXT,
    weight_kg               TEXT,
    fat_percent             TEXT,
    muscle_mass_kg          TEXT,
    bone_mass_kg            TEXT,
    hydration_percent       TEXT,
    bmi                     TEXT,
    mapped_fields_json      TEXT,
    ignored_fields_json     TEXT,
    null_fields_json        TEXT,
    mapping_warnings_json   TEXT,
    dedup_status            TEXT,
    decision                TEXT,
    reason                  TEXT,
    garmin_write_method     TEXT,
    garmin_params_json      TEXT,
    garmin_response_json    TEXT,
    error_message           TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_job  ON sync_candidates(job_id);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_date ON sync_candidates(date);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_key  ON sync_candidates(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_sync_candidates_dec  ON sync_candidates(decision);
"""

SYNC_DECISIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id    INTEGER NOT NULL REFERENCES sync_candidates(id),
    decision        TEXT    NOT NULL,
    reason          TEXT    NOT NULL,
    weight_epsilon  REAL,
    existing_weight REAL,
    existing_date   TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sync_decisions_candidate ON sync_decisions(candidate_id);
"""

SCHEMA_MIGRATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    version     TEXT    NOT NULL UNIQUE,
    description TEXT,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    checksum    TEXT
);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Open or create the SQLite database and ensure all tables exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(TOKEN_SCHEMA)
    conn.executescript(STATE_SCHEMA)
    _migrate_sync_events_if_needed(conn)
    conn.executescript(SYNC_SCHEMA)
    conn.executescript(ATTEMPT_SCHEMA)
    conn.executescript(GARMIN_CACHE_SCHEMA)
    conn.executescript(WITHINGS_MEAS_SCHEMA)
    conn.executescript(SYNC_JOBS_SCHEMA)
    conn.executescript(SYNC_CANDIDATES_SCHEMA)
    conn.executescript(SYNC_DECISIONS_SCHEMA)
    conn.executescript(SCHEMA_MIGRATIONS_SCHEMA)
    _migrate_sync_events_to_candidates(conn)
    _migrate_sync_attempts_to_jobs(conn)
    _ensure_column(conn, "withings_tokens", "userid", "TEXT")
    return conn


def _migrate_sync_events_to_candidates(conn):
    """Migrate old sync_events → sync_candidates (one-shot, idempotent).

    sync_events columns: idempotency_key, source, withings_measure_id,
    source_measured_at_utc, local_date, weight_kg, status, 
    garmin_write_method, garmin_response_json, error_message, report_json.
    """
    cur = conn.execute("SELECT COUNT(*) FROM sync_candidates")
    if cur.fetchone()[0] > 0:
        logger.info("sync_candidates already populated — skipping migration")
        return
    try:
        cur = conn.execute("SELECT COUNT(*) FROM sync_events")
        event_count = cur.fetchone()[0]
    except Exception:
        logger.info("No legacy sync_events table — skipping migration")
        return
    if event_count == 0:
        logger.info("sync_events is empty — skipping migration")
        return

    logger.info("Migrating %d sync_events → sync_candidates ...", event_count)
    rows = conn.execute(
        """SELECT idempotency_key, source, withings_measure_id,
                  source_measured_at_utc, local_date, weight_kg, status,
                  garmin_write_method, garmin_response_json, error_message,
                  report_json
           FROM sync_events"""
    ).fetchall()

    inserted = 0
    for row in rows:
        (key, source, src_meas_id, src_utc, local_date,
         wt, status, write_method, resp_json, err_msg, report_json) = row

        decision = _legacy_status_to_decision(status)
        report = {}
        if report_json:
            try:
                report = json.loads(report_json)
            except Exception:
                report = {}
        mapped = report.get("mapped_fields") if isinstance(report, dict) else None
        reason = f"migrated from sync_events (status={status})"

        try:
            conn.execute(
                """INSERT OR IGNORE INTO sync_candidates
                   (idempotency_key, source, source_measure_group_id,
                    measured_at_local, date, weight_kg,
                    garmin_write_method, garmin_response_json, error_message,
                    mapped_fields_json, dedup_status, decision, reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, source or "withings", src_meas_id,
                 src_utc, local_date, wt,
                 write_method, resp_json, err_msg,
                 json.dumps(mapped, ensure_ascii=False) if mapped else None,
                 status, decision, reason),
            )
            inserted += 1
        except Exception as exc:
            logger.warning("Failed to migrate event %s: %s", key, exc)

    conn.commit()
    logger.info("Migrated %d / %d sync_events to sync_candidates", inserted, event_count)


def _migrate_sync_attempts_to_jobs(conn: sqlite3.Connection) -> None:
    """Migrate legacy ``sync_attempts`` → ``sync_jobs`` (one-shot, idempotent).

    Each attempt becomes a ``sync_job`` with a generated ``run_id``.
    ``duration_seconds`` is computed from ``started_at`` / ``completed_at``.
    Old columns ``summary_json`` is mapped to ``report_json``.
    """
    cur = conn.execute("SELECT COUNT(*) FROM sync_jobs")
    if cur.fetchone()[0] > 0:
        logger.info("sync_jobs already populated — skipping migration")
        return
    try:
        cur = conn.execute("SELECT COUNT(*) FROM sync_attempts")
        attempt_count = cur.fetchone()[0]
    except Exception:
        logger.info("No legacy sync_attempts table — skipping migration")
        return
    if attempt_count == 0:
        logger.info("sync_attempts is empty — skipping migration")
        return

    logger.info("Migrating %d sync_attempts → sync_jobs ...", attempt_count)
    rows = conn.execute(
        """SELECT started_at, completed_at, start_date, end_date,
                  status, summary_json, error_message
           FROM sync_attempts"""
    ).fetchall()

    inserted = 0
    for row in rows:
        duration = None
        if row["completed_at"] and row["started_at"]:
            try:
                s = datetime.fromisoformat(row["started_at"])
                c = datetime.fromisoformat(row["completed_at"])
                duration = (c - s).total_seconds()
            except (ValueError, TypeError):
                pass
        new_status = row["status"]
        if new_status not in ("completed", "failed"):
            new_status = "completed" if row["completed_at"] else "failed"
        try:
            conn.execute(
                """INSERT OR IGNORE INTO sync_jobs
                   (run_id, started_at, completed_at, start_date, end_date,
                    trigger, status, duration_seconds, error_message,
                    report_json, candidates_total)
                   VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, ?, ?, 0)""",
                (
                    uuid.uuid4().hex[:16],
                    row["started_at"],
                    row["completed_at"],
                    row["start_date"],
                    row["end_date"],
                    new_status,
                    duration,
                    row["error_message"],
                    row["summary_json"],  # mapped to report_json
                ),
            )
            inserted += 1
        except Exception as exc:
            logger.warning("Failed to migrate attempt %s: %s", row["started_at"], exc)

    conn.commit()
    logger.info("Migrated %d / %d sync_attempts to sync_jobs", inserted, attempt_count)


def _legacy_status_to_decision(status):
    mapping = {
        "synced": "sync",
        "skipped": "skip",
        "conflict": "garmin_write",
        "invalid": "skip",
        "failed": "skip",
    }
    return mapping.get(status)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_sync_events_if_needed(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sync_events)").fetchall()}
    legacy_column = "dry" + "_run"
    if legacy_column not in columns:
        return
    conn.execute("ALTER TABLE sync_events RENAME TO sync_events_legacy")
    conn.executescript(SYNC_SCHEMA)
    legacy_rows = conn.execute(
        """SELECT idempotency_key, source, source_measure_group_id,
                  source_measured_at_utc, garmin_date, weight_kg, status,
                  garmin_write_method, garmin_response_json, report_json, created_at
           FROM sync_events_legacy"""
    ).fetchall()
    for row in legacy_rows:
        status = str(row["status"])
        if "duplicate" in status:
            new_status = "skipped_existing"
        elif "conflict" in status:
            new_status = "skipped_conflict"
        elif "invalid" in status:
            new_status = "invalid"
        elif "written" in status:
            new_status = "synced"
        else:
            new_status = "failed"
        conn.execute(
            """INSERT OR IGNORE INTO sync_events
               (idempotency_key, source, withings_measure_id, source_measured_at_utc,
                local_date, weight_kg, status, garmin_write_method, garmin_response_json,
                report_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["idempotency_key"],
                row["source"],
                row["source_measure_group_id"],
                row["source_measured_at_utc"],
                row["garmin_date"],
                row["weight_kg"],
                new_status,
                row["garmin_write_method"],
                row["garmin_response_json"],
                row["report_json"],
                row["created_at"],
                row["created_at"],
            ),
        )
    conn.execute("DROP TABLE sync_events_legacy")
