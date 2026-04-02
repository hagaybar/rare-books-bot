"""
Fix 04: Subject Scheme Normalization

Normalize subject scheme 'NLI' to lowercase 'nli' for consistency.
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
FIX_ID = "fix_04_subject_scheme_normalize"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return subjects with scheme='NLI' (uppercase)."""
    cur = conn.execute(
        """
        SELECT s.id, s.record_id, s.value, s.scheme, r.mms_id
        FROM subjects s
        JOIN records r ON r.id = s.record_id
        WHERE s.scheme = 'NLI'
        ORDER BY s.id
        """
    )
    return [
        {
            "subject_id": row[0],
            "record_id": row[1],
            "value": row[2],
            "scheme_old": row[3],
            "mms_id": row[4],
        }
        for row in cur.fetchall()
    ]


def archive(rows: list[dict], archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "records": rows,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(conn: sqlite3.Connection) -> int:
    """Bulk update: NLI -> nli. Returns rows changed.

    We temporarily drop the subjects_fts_update trigger because the FTS5
    content-sync trigger fails when deleting from subjects_fts (the content
    table 'subjects' lacks the 'mms_id' column that FTS expects).  Since we
    only change 'scheme' (not the FTS-indexed 'value'), the FTS index stays
    correct without the trigger firing.
    """
    # Save & drop the trigger
    trigger_sql = (
        "CREATE TRIGGER subjects_fts_update AFTER UPDATE ON subjects BEGIN\n"
        "    DELETE FROM subjects_fts WHERE rowid = OLD.id;\n"
        "    INSERT INTO subjects_fts(rowid, mms_id, value)\n"
        "    SELECT NEW.id, r.mms_id, NEW.value\n"
        "    FROM records r WHERE r.id = NEW.record_id;\n"
        "END"
    )
    conn.execute("DROP TRIGGER IF EXISTS subjects_fts_update")
    try:
        cur = conn.execute("UPDATE subjects SET scheme = 'nli' WHERE scheme = 'NLI'")
        conn.commit()
    finally:
        # Restore the trigger regardless of success/failure
        conn.execute(trigger_sql)
        conn.commit()
    return cur.rowcount


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Normalize subject scheme 'NLI' to lowercase 'nli'",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["scheme"],
        "method": "case_normalize",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true", help="Report only, no DB changes")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    try:
        rows = find_affected(conn)
        if not rows:
            print(f"[{FIX_ID}] No affected rows found (already fixed or no 'NLI' schemes).")
            return

        unique_mms = set(r["mms_id"] for r in rows)
        print(f"[{FIX_ID}] Found {len(rows)} subject rows with scheme='NLI' "
              f"across {len(unique_mms)} records.")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN — no changes made.")
            return

        archive_path = archive(rows, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(rows)} original values to {archive_path}")

        count = apply_fixes(conn)
        print(f"[{FIX_ID}] Updated {count} subject rows (scheme: NLI -> nli).")

        append_fix_log(rows, count)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
