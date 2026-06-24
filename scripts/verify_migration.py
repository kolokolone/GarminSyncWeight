"""Verify migration result and print a summary."""
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/withings_tokens.db")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

tables = [r["name"] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

print("=== TABLES AFTER MIGRATION ===")
for t in tables:
    if t == "sqlite_sequence":
        continue
    cnt = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  {t:35s} {cnt} rows")

print()
print("=== SCHEMA_MIGRATIONS ===")
for r in conn.execute("SELECT * FROM schema_migrations").fetchall():
    print(f"  version={r['version']} desc={r['description']} at={r['applied_at']}")

print()
print("=== SYNC_CANDIDATES BY DECISION ===")
for r in conn.execute(
    "SELECT decision, COUNT(*) as cnt FROM sync_candidates GROUP BY decision ORDER BY cnt DESC"
).fetchall():
    print(f"  {str(r['decision']):20s} {r['cnt']}")

print()
print("=== SYNC_JOBS BY STATUS ===")
for r in conn.execute(
    "SELECT status, COUNT(*) as cnt FROM sync_jobs GROUP BY status"
).fetchall():
    print(f"  {str(r['status']):15s} {r['cnt']}")

print()
# Check old tables are gone
for old in ("sync_events", "sync_attempts"):
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (old,)
    ).fetchone()
    print(f"  Table {old}: {'GONE' if not exists else 'STILL EXISTS!'}")

# Check WAL checkpoint
conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
conn.close()
print()
print("Migration verification complete.")
