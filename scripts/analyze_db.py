"""Analyse la base SQLite : tables, colonnes, index, et comptage des données."""
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/withings_tokens.db")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# List all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print("=== TABLES ===")
for t in tables:
    print(f"  {t['name']}")

# Schema + row count for each
for t in tables:
    name = t["name"]
    if name == "sqlite_sequence":
        continue
    try:
        count = conn.execute(f"SELECT COUNT(*) AS cnt FROM \"{name}\"").fetchone()["cnt"]
    except Exception:
        count = -1
    print(f"\n=== SCHEMA: {name}  ({count} rows) ===")
    for row in conn.execute(f"PRAGMA table_info(\"{name}\")").fetchall():
        print(f"  {row['name']:30s} {row['type']:10s} null={row['notnull']}  pk={row['pk']}")
    idxs = conn.execute(f"PRAGMA index_list(\"{name}\")").fetchall()
    if idxs:
        print("  INDEXES:")
        for idx in idxs:
            print(f"    {idx['name']:40s} unique={idx['unique']}")

conn.close()
