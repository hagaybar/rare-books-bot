"""
Fix 07: Germany Place Norm

7 records have place_norm='germany' — the normalization is too coarse
(country instead of city). This script examines place_raw and record
context to determine whether a specific city can be identified.

After analysis: all 7 records have place_raw that genuinely says
"[Germany]", "Germanien", or "Deutschland" — the MARC cataloguer could
not identify a specific city. We normalize place_norm to '[germany]'
(bracketed, indicating uncertainty) and set place_method to 'country_only'
to distinguish these from proper city normalizations.
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
FIX_ID = "fix_07_germany_place_norm"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return imprints where place_norm='germany' (country-level, not city)."""
    cur = conn.execute(
        """
        SELECT i.id, i.record_id, i.place_raw, i.place_norm, i.place_display,
               i.place_method, i.place_confidence, i.country_code,
               r.mms_id, i.date_start, i.publisher_raw,
               (SELECT t.value FROM titles t
                WHERE t.record_id = r.id AND t.title_type = 'main'
                LIMIT 1) as title
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.place_norm = 'germany'
        ORDER BY r.mms_id
        """
    )
    rows = []
    for row in cur.fetchall():
        rows.append({
            "imprint_id": row[0],
            "record_id": row[1],
            "place_raw": row[2],
            "place_norm_old": row[3],
            "place_display_old": row[4],
            "place_method_old": row[5],
            "place_confidence_old": row[6],
            "country_code": row[7],
            "mms_id": row[8],
            "date_start": row[9],
            "publisher_raw": row[10],
            "title": row[11],
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
    """Mark place_norm as '[germany]' (bracketed = uncertain) and
    set place_method='country_only' to flag these for future research."""
    count = 0
    for row in rows:
        # Only update if still 'germany' (idempotent check)
        if row["place_norm_old"] != "germany":
            continue
        conn.execute(
            """
            UPDATE imprints
            SET place_norm = '[germany]',
                place_method = 'country_only',
                place_confidence = 0.3
            WHERE id = ? AND place_norm = 'germany'
            """,
            (row["imprint_id"],),
        )
        count += 1
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Flag 7 germany-level place_norm records as country_only (no city in MARC data)",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["place_norm", "place_method", "place_confidence"],
        "method": "country_only_flag",
        "note": "place_raw contains '[Germany]', 'Germanien', or 'Deutschland' — "
                "no city specified in the MARC source. Requires external research.",
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
            print(f"[{FIX_ID}] No affected rows found (already fixed or no 'germany' place_norm).")
            return

        print(f"[{FIX_ID}] Found {len(rows)} imprints with place_norm='germany':")
        for row in rows:
            print(f"  imprint_id={row['imprint_id']}  mms_id={row['mms_id']}  "
                  f"place_raw={row['place_raw']!r}  date={row['date_start']}  "
                  f"publisher={row['publisher_raw']!r}")
        print()
        print("  NOTE: All 7 records have place_raw that says '[Germany]', 'Germanien',")
        print("  or 'Deutschland'. The MARC cataloguer could not identify a specific city.")
        print("  Fixing place_norm to '[germany]' (bracketed) and method to 'country_only'.")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN — {len(rows)} imprints would be updated. No changes made.")
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
