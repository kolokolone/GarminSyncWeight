"""Fix duplicate sync_jobs after double-migration."""
import sqlite3
from pathlib import Path

db_path = Path("data/withings_tokens.db")
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

before = conn.execute("SELECT COUNT(*) FROM sync_jobs").fetchone()[0]
print(f"sync_jobs before: {before}")

pairs = conn.execute("""
    SELECT started_at, completed_at, COUNT(*) as cnt
    FROM sync_jobs
    GROUP BY started_at, completed_at
    HAVING cnt > 1
""").fetchall()

print(f"Duplicate pairs: {len(pairs)}")
removed = 0
for p in pairs:
    rows = conn.execute("""
        SELECT id, candidates_total, started_at
        FROM sync_jobs
        WHERE started_at = ? AND completed_at = ?
        ORDER BY id ASC
    """, (p["started_at"], p["completed_at"])).fetchall()
    best = None
    for r in rows:
        if r["candidates_total"] and r["candidates_total"] > 0:
            best = r
            break
    if best is None:
        best = rows[0]
    for r in rows:
        if r["id"] != best["id"]:
            conn.execute("DELETE FROM sync_jobs WHERE id = ?", (r["id"],))
            removed += 1
            print(f"  Removed id={r['id']} (total={r['candidates_total']}), kept id={best['id']} (total={best['candidates_total']})")

conn.commit()

after = conn.execute("SELECT COUNT(*) FROM sync_jobs").fetchone()[0]
print(f"\nsync_jobs after: {after}, removed: {removed}")

remaining = conn.execute("""
    SELECT started_at, COUNT(*) as cnt
    FROM sync_jobs
    GROUP BY started_at
    HAVING cnt > 1
""").fetchall()
if remaining:
    print(f"WARNING: {len(remaining)} remaining!")
else:
    print("All duplicates resolved!")

conn.close()
