"""Dump the whole bot.db into one JSON file so the data can be moved elsewhere.

Usage:
    python export_data.py            # reads ./bot.db, writes ./data_export.json
    python export_data.py path.db out.json

This is read-only. It never modifies bot.db.
"""
import json
import sqlite3
import sys
from pathlib import Path


def export(db_path: str, out_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    dump = {}
    for t in tables:
        rows = [dict(r) for r in con.execute(f"SELECT * FROM {t}")]
        dump[t] = rows
    con.close()

    Path(out_path).write_text(json.dumps(dump, indent=2, default=str), encoding="utf-8")
    print(f"Exported {db_path} -> {out_path}")
    for t, rows in dump.items():
        print(f"  {t}: {len(rows)} rows")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    out = sys.argv[2] if len(sys.argv) > 2 else "data_export.json"
    if not Path(db).exists():
        raise SystemExit(f"No database at {db}")
    export(db, out)
