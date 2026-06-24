#!/usr/bin/env python3
"""One-shot migration: sync_events/attempts -> sync_jobs/candidates/decisions.

This script is run ONCE manually (not by the application). It:

1. Inspects the current state of both old and new tables
2. Migrates any remaining sync_events -> sync_candidates (idempotent)
3. Migrates any remaining sync_attempts -> sync_jobs (idempotent)
4. Patches empty decision values in already-migrated candidates
5. Records the migration version in schema_migrations
6. Drops the old tables (sync_events, sync_attempts)
7. Creates a backup of the old data as JSON files

Usage:
    python scripts/migrate_v1_to_v2.py [--db data/withings_tokens.db] [--backup-dir data/backup_v1]

The migration is idempotent -- if run twice it will skip already-done tables.
"""

import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


MIGRATION_VERSION = "001"
MIGRATION_DESCRIPTION = "Migrate sync_events/attempts to sync_jobs/candidates + drop legacy tables"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def migration_already_applied(conn: sqlite3.Connection) -> bool:
    if not table_exists(conn, "schema_migrations"):
        return False
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version=?",
        (MIGRATION_VERSION,),
    ).fetchone()
    return row is not None


def record_migration(conn: sqlite3.Connection) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO schema_migrations (version, description, applied_at)
           VALUES (?, ?, datetime('now'))""",
        (MIGRATION_VERSION, MIGRATION_DESCRIPTION),
    )
    conn.commit()


def backup_old_tables(conn: sqlite3.Connection, backup_dir: Path) -> dict:
    """Backup old tables to JSON files before dropping them. Returns stats."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stats = {}

    for table in ("sync_events", "sync_attempts"):
        if not table_exists(conn, table):
            print(f"  [i] {table}: table does not exist, skipping backup")
            stats[table] = {"rows": 0, "backup": None}
            continue

        rows = conn.execute(f"SELECT * FROM \"{table}\"").fetchall()
        data = [dict(r) for r in rows]
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{table}_{timestamp}.json"
        backup_file.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        print(f"  [OK] {table}: {len(data)} rows -> {backup_file}")
        stats[table] = {"rows": len(data), "backup": str(backup_file)}

    return stats


def migrate_events_to_candidates(conn: sqlite3.Connection) -> dict:
    """Migrate sync_events -> sync_candidates. Returns stats."""
    stats = {"already_present": 0, "inserted": 0, "errors": 0, "total_in_events": 0}

    if not table_exists(conn, "sync_events"):
        print("  [i]  sync_events table does not exist, skipping")
        return stats

    # Count existing candidates to know if already migrated
    existing = conn.execute("SELECT COUNT(*) AS cnt FROM sync_candidates").fetchone()["cnt"]
    stats["already_present"] = existing

    # Count events to migrate
    total = conn.execute("SELECT COUNT(*) AS cnt FROM sync_events").fetchone()["cnt"]
    stats["total_in_events"] = total

    if total == 0:
        print("  [i]  sync_events is empty, nothing to migrate")
        return stats

    # Get all events
    rows = conn.execute(
        """SELECT idempotency_key, source, withings_measure_id,
                  source_measured_at_utc, local_date, weight_kg, status,
                  garmin_write_method, garmin_response_json, error_message,
                  report_json, created_at
           FROM sync_events"""
    ).fetchall()

    inserted = 0
    errors = 0
    for row in rows:
        decision = _legacy_status_to_decision(row["status"])
        report = {}
        if row["report_json"]:
            try:
                report = json.loads(row["report_json"])
            except Exception:
                report = {}
        mapped = report.get("mapped_fields") if isinstance(report, dict) else None
        reason = f"migrated from sync_events (status={row['status']})"

        try:
            conn.execute(
                """INSERT OR IGNORE INTO sync_candidates
                   (idempotency_key, source, source_measure_group_id,
                    measured_at_local, date, weight_kg,
                    garmin_write_method, garmin_response_json, error_message,
                    mapped_fields_json, dedup_status, decision, reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["idempotency_key"],
                    row["source"] or "withings",
                    row["withings_measure_id"],
                    row["source_measured_at_utc"],
                    row["local_date"],
                    row["weight_kg"],
                    row["garmin_write_method"],
                    row["garmin_response_json"],
                    row["error_message"],
                    json.dumps(mapped, ensure_ascii=False) if mapped else None,
                    row["status"],
                    decision,
                    reason,
                ),
            )
            inserted += 1
        except Exception as exc:
            print(f"    [WARN]  Failed to migrate event {row['idempotency_key']}: {exc}")
            errors += 1

    stats["inserted"] = inserted
    stats["errors"] = errors
    return stats


def migrate_attempts_to_jobs(conn: sqlite3.Connection) -> dict:
    """Migrate sync_attempts -> sync_jobs. Returns stats."""
    stats = {"already_present": 0, "inserted": 0, "errors": 0, "total_in_attempts": 0}

    if not table_exists(conn, "sync_attempts"):
        print("  [i]  sync_attempts table does not exist, skipping")
        return stats

    # Count existing jobs
    existing = conn.execute("SELECT COUNT(*) AS cnt FROM sync_jobs").fetchone()["cnt"]
    stats["already_present"] = existing

    # Count attempts
    total = conn.execute("SELECT COUNT(*) AS cnt FROM sync_attempts").fetchone()["cnt"]
    stats["total_in_attempts"] = total

    if total == 0:
        print("  [i]  sync_attempts is empty, nothing to migrate")
        return stats

    rows = conn.execute(
        """SELECT started_at, completed_at, start_date, end_date,
                  status, summary_json, error_message
           FROM sync_attempts"""
    ).fetchall()

    inserted = 0
    errors = 0
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

        # Parse summary to extract candidate counts
        summary = {}
        candidates_total = 0
        candidates_synced = 0
        candidates_skipped = 0
        candidates_conflict = 0
        candidates_invalid = 0
        candidates_failed = 0
        if row["summary_json"]:
            try:
                summary = json.loads(row["summary_json"])
                candidates_total = summary.get("candidates_count", 0)
                candidates_synced = summary.get("synced_count", 0)
                candidates_skipped = summary.get("skipped_existing_count", 0)
                candidates_conflict = summary.get("conflicts_count", 0)
                candidates_invalid = summary.get("invalid_count", 0)
                candidates_failed = summary.get("failed_count", 0)
            except Exception:
                pass

        try:
            conn.execute(
                """INSERT OR IGNORE INTO sync_jobs
                   (run_id, started_at, completed_at, start_date, end_date,
                    trigger, status, duration_seconds, error_message,
                    report_json, candidates_total,
                    candidates_synced, candidates_skipped,
                    candidates_conflict, candidates_invalid, candidates_failed)
                   VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex[:16],
                    row["started_at"],
                    row["completed_at"],
                    row["start_date"],
                    row["end_date"],
                    new_status,
                    duration,
                    row["error_message"],
                    row["summary_json"],
                    candidates_total,
                    candidates_synced,
                    candidates_skipped,
                    candidates_conflict,
                    candidates_invalid,
                    candidates_failed,
                ),
            )
            inserted += 1
        except Exception as exc:
            print(f"    [WARN]  Failed to migrate attempt {row['started_at']}: {exc}")
            errors += 1

    stats["inserted"] = inserted
    stats["errors"] = errors
    return stats


def patch_existing_decisions(conn: sqlite3.Connection) -> dict:
    """Fix NULL decisions in already-migrated candidates by inferring from dedup_status."""
    patched = 0
    errors = 0

    rows = conn.execute(
        """SELECT id, idempotency_key, dedup_status, decision
           FROM sync_candidates
           WHERE decision IS NULL"""
    ).fetchall()

    for row in rows:
        try:
            decision = _legacy_status_to_decision(row["dedup_status"] or "unknown")
            conn.execute(
                "UPDATE sync_candidates SET decision = ? WHERE id = ?",
                (decision, row["id"]),
            )
            patched += 1
        except Exception as exc:
            print(f"    [WARN]  Failed to patch candidate {row['id']}: {exc}")
            errors += 1

    if patched:
        conn.commit()
    return {"patched": patched, "errors": errors}


def _legacy_status_to_decision(status):
    mapping = {
        "synced": "synced",
        "skipped_existing": "skipped_existing",
        "skipped_conflict": "skipped_conflict",
        "invalid": "invalid",
        "failed": "failed",
        "conflict": "skipped_conflict",
        "new_candidate": "new_candidate",
        "duplicate_exact_or_near": "skipped_existing",
        "duplicate_body_composition": "skipped_existing",
        "already_synced_by_garminsync": "skipped_existing",
        "possible_duplicate": "skipped_conflict",
        "conflict_same_day": "skipped_conflict",
        "invalid_missing_weight": "invalid",
        "invalid_outlier": "invalid",
    }
    # Also handle legacy short codes
    mapping_legacy = {
        "written": "synced",
        "synced": "synced",
        "skipped": "skipped_existing",
        "conflict": "skipped_conflict",
        "invalid": "invalid",
        "failed": "failed",
    }
    return mapping.get(status) or mapping_legacy.get(status)


def drop_legacy_tables(conn: sqlite3.Connection, backup_stats: dict) -> dict:
    """Drop old tables. Only drops if backup was successful."""
    dropped = []
    skipped = []

    for table in ("sync_events", "sync_attempts"):
        if not table_exists(conn, table):
            skipped.append(table)
            continue

        # Safety check: confirm backup exists
        backup_info = backup_stats.get(table, {})
        if backup_info.get("backup") and Path(backup_info["backup"]).exists():
            conn.execute(f"DROP TABLE IF EXISTS \"{table}\"")
            print(f"  [OK] {table}: dropped (backup at {backup_info['backup']})")
            dropped.append(table)
        else:
            print(f"  [WARN]  {table}: NOT dropping -- no backup found!")
            skipped.append(table)

    if dropped:
        conn.commit()
    return {"dropped": dropped, "skipped": skipped}


def verify_data_integrity(conn: sqlite3.Connection) -> dict:
    """Verify data integrity after migration. Returns issues found."""
    issues = []

    # Check candidates have non-null decisions
    null_decisions = conn.execute(
        "SELECT COUNT(*) AS cnt FROM sync_candidates WHERE decision IS NULL"
    ).fetchone()["cnt"]
    if null_decisions > 0:
        issues.append(f"{null_decisions} sync_candidates have NULL decision")

    # Check jobs have run_ids
    null_run_ids = conn.execute(
        "SELECT COUNT(*) AS cnt FROM sync_jobs WHERE run_id IS NULL"
    ).fetchone()["cnt"]
    if null_run_ids > 0:
        issues.append(f"{null_run_ids} sync_jobs have NULL run_id")

    # Check no orphaned data
    if table_exists(conn, "sync_candidates"):
        orphans = conn.execute(
            """SELECT COUNT(*) AS cnt FROM sync_candidates
               WHERE job_id IS NOT NULL
                 AND job_id NOT IN (SELECT id FROM sync_jobs)"""
        ).fetchone()["cnt"]
        if orphans > 0:
            issues.append(f"{orphans} sync_candidates reference non-existent jobs")

    # Check old tables are gone
    for table in ("sync_events", "sync_attempts"):
        if table_exists(conn, table):
            count = conn.execute(f"SELECT COUNT(*) AS cnt FROM \"{table}\"").fetchone()["cnt"]
            issues.append(f"{table} still exists with {count} rows (should be dropped)")

    return {"issues": issues, "clean": len(issues) == 0}


def log_report(stats: dict, output_path: Path) -> None:
    """Write a detailed JSON report of the migration."""
    report = {
        "migration_version": MIGRATION_VERSION,
        "executed_at": datetime.now(UTC).isoformat(),
        "duration_seconds": stats.get("duration_seconds", 0),
        "backup": stats.get("backup", {}),
        "events_migration": stats.get("events_migration", {}),
        "attempts_migration": stats.get("attempts_migration", {}),
        "decision_patch": stats.get("decision_patch", {}),
        "drop": stats.get("drop", {}),
        "integrity": stats.get("integrity", {}),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
    )
    print(f"\n[FILE] Report written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate v1 -> v2 database schema")
    parser.add_argument(
        "--db",
        default="data/withings_tokens.db",
        help="Path to the SQLite database (default: data/withings_tokens.db)",
    )
    parser.add_argument(
        "--backup-dir",
        default="data/backup_v1",
        help="Directory for JSON backups of old tables (default: data/backup_v1)",
    )
    parser.add_argument(
        "--report",
        default=".sisyphus/log/migration_v2_report.json",
        help="Path for the JSON report output",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if migration is already recorded in schema_migrations",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERR] Database not found: {db_path}")
        sys.exit(1)

    backup_dir = Path(args.backup_dir)
    report_path = Path(args.report)

    print(f"{'='*60}")
    print(f"  Migration v1 -> v2")
    print(f"  Database: {db_path}")
    print(f"  Backup:   {backup_dir}/")
    print(f"{'='*60}\n")

    start_ts = time.time()
    conn = connect(db_path)

    # ── 0. Check if already applied ────────────────────────────
    if migration_already_applied(conn):
        print("[OK] Migration already recorded in schema_migrations.")
        if not args.force:
            print("   Use --force to re-run.")
            conn.close()
            return

    # ── 1. Backup old tables ───────────────────────────────────
    print("[1]  Backing up legacy tables...")
    backup_stats = backup_old_tables(conn, backup_dir)

    # ── 2. Migrate sync_events -> sync_candidates ───────────────
    print("\n[2]  Migrating sync_events -> sync_candidates...")
    events_stats = migrate_events_to_candidates(conn)
    conn.commit()
    print(f"    Total in sync_events: {events_stats['total_in_events']}")
    print(f"    Already in sync_candidates: {events_stats['already_present']}")
    print(f"    Newly inserted: {events_stats['inserted']}")
    if events_stats["errors"]:
        print(f"    [WARN]  Errors: {events_stats['errors']}")

    # ── 3. Migrate sync_attempts -> sync_jobs ───────────────────
    print("\n[3]  Migrating sync_attempts -> sync_jobs...")
    attempts_stats = migrate_attempts_to_jobs(conn)
    conn.commit()
    print(f"    Total in sync_attempts: {attempts_stats['total_in_attempts']}")
    print(f"    Already in sync_jobs: {attempts_stats['already_present']}")
    print(f"    Newly inserted: {attempts_stats['inserted']}")
    if attempts_stats["errors"]:
        print(f"    [WARN]  Errors: {attempts_stats['errors']}")

    # ── 4. Patch NULL decisions ─────────────────────────────────
    print("\n[4]  Patching NULL decisions in sync_candidates...")
    patch_stats = patch_existing_decisions(conn)
    print(f"    Patched: {patch_stats['patched']}")
    if patch_stats["errors"]:
        print(f"    [WARN]  Errors: {patch_stats['errors']}")

    # ── 5. Drop legacy tables ───────────────────────────────────
    print("\n[5]  Dropping legacy tables...")
    drop_stats = drop_legacy_tables(conn, backup_stats)
    print(f"    Dropped: {drop_stats['dropped']}")
    if drop_stats["skipped"]:
        print(f"    Skipped (no backup): {drop_stats['skipped']}")

    # ── 6. Record migration ─────────────────────────────────────
    print("\n[6]  Recording migration in schema_migrations...")
    record_migration(conn)
    print(f"    Version {MIGRATION_VERSION} recorded.")

    # ── 7. Verify ───────────────────────────────────────────────
    print("\n[7]  Verifying data integrity...")
    integrity = verify_data_integrity(conn)
    if integrity["clean"]:
        print("    [OK] All checks passed!")
    else:
        for issue in integrity["issues"]:
            print(f"    [WARN]  {issue}")

    duration = time.time() - start_ts
    conn.close()

    # ── Report ──────────────────────────────────────────────────
    stats = {
        "duration_seconds": round(duration, 3),
        "backup": backup_stats,
        "events_migration": events_stats,
        "attempts_migration": attempts_stats,
        "decision_patch": patch_stats,
        "drop": drop_stats,
        "integrity": integrity,
    }
    log_report(stats, report_path)

    print(f"\n{'='*60}")
    print(f"  Migration complete in {duration:.1f}s")
    if integrity["clean"]:
        print(f"  [OK] All data verified. Legacy tables dropped.")
    else:
        print(f"  [WARN] Migration finished with issues - review above.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
