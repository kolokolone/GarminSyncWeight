"""SQLite database initialisation and connection management."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

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
    conn.executescript(GARMIN_CACHE_SCHEMA)
    conn.executescript(WITHINGS_MEAS_SCHEMA)
    conn.executescript(SYNC_JOBS_SCHEMA)
    conn.executescript(SYNC_CANDIDATES_SCHEMA)
    conn.executescript(SYNC_DECISIONS_SCHEMA)
    conn.executescript(SCHEMA_MIGRATIONS_SCHEMA)
    _ensure_column(conn, "withings_tokens", "userid", "TEXT")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
