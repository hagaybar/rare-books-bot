"""
Fix 05: Calendar Confusion Dates

Two specific records have incorrect date_start due to calendar confusion:

1. mms_id 990013146190204146: Hijri date 1244 parsed as Gregorian.
   Raw: [١٨٢٨ م.] ١٢٤٤ هج.  -- Gregorian equivalent is 1828.
   Fix: date_start=1828, date_end=1828, date_label='1828', date_method='hijri_corrected'

2. mms_id 990013766990204146: Hebrew gematria misparse.
   Raw: [הקד' תקצ"ד]  -- תקצ"ד = 5594 Hebrew = 1834 CE.
   Current: date_start=1349 (wrong gematria parse).
   Fix: date_start=1834, date_end=1834, date_label='1834', date_method='gematria_corrected'
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# (mms_id, corrected_start, corrected_end, corrected_label, corrected_method, explanation)
CALENDAR_FIXES = [
    {
        "mms_id": "990013146190204146",
        "date_start_new": 1828,
        "date_end_new": 1828,
        "date_label_new": "1828",
        "date_method_new": "hijri_corrected",
        "explanation": "Hijri 1244 -> Gregorian 1828. Raw: [١٨٢٨ م.] ١٢٤٤ هج.",
    },
    {
        "mms_id": "990013766990204146",
        "date_start_new": 1834,
        "date_end_new": 1834,
        "date_label_new": "1834",
        "date_method_new": "gematria_corrected",
        "explanation": "Hebrew gematria תקצ\"ד = 5594 = 1834 CE. Raw: [הקד' תקצ\"ד]",
    },
]

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_05_calendar_confusion_dates"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return current imprint data for the two known calendar-confusion records."""
    rows = []
    for fix in CALENDAR_FIXES:
        cur = conn.execute(
            """
            SELECT i.id, i.record_id, i.date_start, i.date_end, i.date_raw,
                   i.date_label, i.date_method, i.date_confidence, r.mms_id
            FROM imprints i
            JOIN records r ON r.id = i.record_id
            WHERE r.mms_id = ?
            """,
            (fix["mms_id"],),
        )
        for row in cur.fetchall():
            # Only fix if date_start still has the wrong value
            current_start = row[2]
            expected_wrong_values = {1244, 1349}
            if current_start not in expected_wrong_values:
                continue  # already fixed
            rows.append({
                "imprint_id": row[0],
                "record_id": row[1],
                "date_start_old": row[2],
                "date_end_old": row[3],
                "date_raw": row[4],
                "date_label_old": row[5],
                "date_method_old": row[6],
                "date_confidence_old": row[7],
                "mms_id": row[8],
                **{k: v for k, v in fix.items() if k != "mms_id"},
            })
    return rows


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


def apply_fixes(conn: sqlite3.Connection, rows: list[dict]) -> int:
    count = 0
    for row in rows:
        conn.execute(
            """
            UPDATE imprints
            SET date_start = ?, date_end = ?, date_label = ?,
                date_method = ?, date_confidence = 1.0
            WHERE id = ?
            """,
            (
                row["date_start_new"],
                row["date_end_new"],
                row["date_label_new"],
                row["date_method_new"],
                row["imprint_id"],
            ),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Fix 2 calendar-confusion dates (Hijri 1244->1828, gematria misparse 1349->1834)",
        "records_affected": count,
        "mms_ids": [r["mms_id"] for r in rows],
        "fields_changed": ["date_start", "date_end", "date_label", "date_method", "date_confidence"],
        "method": "manual_calendar_correction",
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
            print(f"[{FIX_ID}] No affected rows found (already fixed or records missing).")
            return

        print(f"[{FIX_ID}] Found {len(rows)} calendar-confusion dates to fix:")
        for row in rows:
            print(f"  mms_id={row['mms_id']}  "
                  f"date_start: {row['date_start_old']} -> {row['date_start_new']}  "
                  f"({row['explanation']})")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN — no changes made.")
            return

        archive_path = archive(rows, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(rows)} original values to {archive_path}")

        count = apply_fixes(conn, rows)
        print(f"[{FIX_ID}] Updated {count} imprint rows.")

        append_fix_log(rows, count)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
