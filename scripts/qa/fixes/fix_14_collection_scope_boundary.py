"""
Fix 14: Collection Scope Boundary Flags

Create a record_scope_flags table and flag records whose dates fall outside
the expected rare-book collection boundaries:

- date_start > 1950  -> flag='modern_reprint_or_edition'
- date_start < 1400  -> flag='needs_date_review'

This is metadata tagging only -- no data deletion or modification of existing
tables.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_14_collection_scope_boundary"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS record_scope_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    flag TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(record_id, flag)
);
"""

SCOPE_RULES: list[dict] = [
    {
        "flag": "modern_reprint_or_edition",
        "query": """
            SELECT DISTINCT i.record_id, i.date_start
            FROM imprints i
            WHERE i.date_start > 1950
            ORDER BY i.record_id
        """,
        "reason_template": "date_start={date_start} (>1950)",
    },
    {
        "flag": "needs_date_review",
        "query": """
            SELECT DISTINCT i.record_id, i.date_start
            FROM imprints i
            WHERE i.date_start IS NOT NULL AND i.date_start < 1400
            ORDER BY i.record_id
        """,
        "reason_template": "date_start={date_start} (<1400)",
    },
]


def find_flaggable(conn: sqlite3.Connection) -> list[dict]:
    """Find records that should be flagged by scope rules."""
    results = []
    for rule in SCOPE_RULES:
        cur = conn.execute(rule["query"])
        for row in cur.fetchall():
            record_id = row[0]
            date_start = row[1]
            reason = rule["reason_template"].format(date_start=date_start)
            results.append({
                "record_id": record_id,
                "flag": rule["flag"],
                "reason": reason,
                "date_start": date_start,
            })
    return results


def count_existing_flags(conn: sqlite3.Connection) -> int:
    """Count existing flags (if table exists)."""
    try:
        cur = conn.execute("SELECT COUNT(*) FROM record_scope_flags")
        return cur.fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def archive_state(flaggable: list[dict], archive_dir: Path) -> Path:
    """Archive the plan before modifications."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    by_flag: dict[str, int] = {}
    for f in flaggable:
        by_flag[f["flag"]] = by_flag.get(f["flag"], 0) + 1
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "total_flags": len(flaggable),
        "by_flag": by_flag,
        "sample": flaggable[:20],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_flags(conn: sqlite3.Connection, flaggable: list[dict]) -> dict:
    """Create the table (if needed) and insert flags. Returns counts."""
    conn.execute(CREATE_TABLE_SQL)

    inserted = 0
    skipped = 0
    by_flag: dict[str, int] = {}

    for item in flaggable:
        try:
            conn.execute(
                """
                INSERT INTO record_scope_flags (record_id, flag, reason)
                VALUES (?, ?, ?)
                """,
                (item["record_id"], item["flag"], item["reason"]),
            )
            inserted += 1
            by_flag[item["flag"]] = by_flag.get(item["flag"], 0) + 1
        except sqlite3.IntegrityError:
            # UNIQUE constraint: already flagged
            skipped += 1

    conn.commit()
    return {"inserted": inserted, "skipped": skipped, "by_flag": by_flag}


def append_fix_log(flaggable: list[dict], counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Create record_scope_flags table and flag out-of-scope dates",
        "total_candidates": len(flaggable),
        "inserted": counts["inserted"],
        "skipped_existing": counts["skipped"],
        "by_flag": counts["by_flag"],
        "tables_changed": ["record_scope_flags (created/populated)"],
        "method": "date_boundary_flags",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only, no DB changes")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        existing_count = count_existing_flags(conn)
        flaggable = find_flaggable(conn)

        by_flag: dict[str, list[dict]] = {}
        for item in flaggable:
            by_flag.setdefault(item["flag"], []).append(item)

        print(f"[{FIX_ID}] Scope boundary analysis:")
        print(f"  Existing flags in table: {existing_count}")
        print(f"  Candidates to flag: {len(flaggable)}")
        print()
        for flag_name, items in by_flag.items():
            print(f"  {flag_name}: {len(items)} records")
            for item in items[:5]:
                print(f"    record_id={item['record_id']}  {item['reason']}")
            if len(items) > 5:
                print(f"    ... and {len(items) - 5} more")

        if not flaggable:
            print(f"\n[{FIX_ID}] No records to flag.")
            return

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- would create table and insert "
                  f"{len(flaggable)} flags.")
            return

        archive_path = archive_state(flaggable, ARCHIVE_DIR)
        print(f"\n[{FIX_ID}] Archived state to {archive_path}")

        counts = apply_flags(conn, flaggable)
        print(f"[{FIX_ID}] Results:")
        print(f"  Flags inserted: {counts['inserted']}")
        print(f"  Skipped (already exist): {counts['skipped']}")
        for flag_name, cnt in counts["by_flag"].items():
            print(f"    {flag_name}: {cnt}")

        append_fix_log(flaggable, counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
