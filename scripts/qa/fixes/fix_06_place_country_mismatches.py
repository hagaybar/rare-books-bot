"""
Fix 06: Place-Country Code Mismatches

Fix imprint rows where place_norm and country_code disagree.
Each mismatch was identified by cross-referencing MARC country codes
against known place-to-country mappings.

Only the country_code is changed; place_norm and place_raw are preserved.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Each entry: (place_norm, wrong_country_code, correct_country_code, explanation)
PLACE_COUNTRY_FIXES: list[tuple[str, str, str, str]] = [
    ("venice", "gw", "it", "Venice is in Italy, not Germany"),
    ("london", "ne", "enk", "London is in England, not Netherlands"),
    ("geneva", "it", "sz", "Geneva is in Switzerland, not Italy"),
    ("bologna", "gw", "it", "Bologna is in Italy, not Germany"),
    ("warsaw", "be", "pl", "Warsaw is in Poland, not Belgium"),
    ("lyon", "ne", "fr", "Lyon is in France, not Netherlands"),
    ("lisbon", "sp", "po", "Lisbon is in Portugal, not Spain"),
    ("istanbul", "is", "tu", "Istanbul is in Turkey, not Israel"),
    ("ferrara", "gw", "it", "Ferrara is in Italy, not Germany"),
    ("mainz", "fr", "gw", "Mainz is in Germany, not France"),
    ("regensburg", "it", "gw", "Regensburg is in Germany, not Italy"),
    ("kaliningrad", "ne", "gw", "Kaliningrad (hist. Koenigsberg) is in Germany/Russia, not Netherlands"),
]

DEFAULT_DB = Path("data/index/bibliographic.db")
ARCHIVE_DIR = Path("data/archive/data-quality-2026-04-02")
FIX_LOG = Path("data/qa/fix-log.jsonl")
FIX_ID = "fix_06_place_country_mismatches"


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Return imprint rows that match known place-country mismatches."""
    rows = []
    for place, wrong_cc, correct_cc, explanation in PLACE_COUNTRY_FIXES:
        cur = conn.execute(
            """
            SELECT i.id, i.record_id, i.place_norm, i.place_raw,
                   i.country_code, r.mms_id
            FROM imprints i
            JOIN records r ON r.id = i.record_id
            WHERE i.place_norm = ? AND i.country_code = ?
            ORDER BY i.id
            """,
            (place, wrong_cc),
        )
        for row in cur.fetchall():
            rows.append({
                "imprint_id": row[0],
                "record_id": row[1],
                "place_norm": row[2],
                "place_raw": row[3],
                "country_code_old": row[4],
                "country_code_new": correct_cc,
                "mms_id": row[5],
                "explanation": explanation,
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
        cur = conn.execute(
            """
            UPDATE imprints
            SET country_code = ?
            WHERE id = ? AND country_code = ?
            """,
            (row["country_code_new"], row["imprint_id"], row["country_code_old"]),
        )
        count += cur.rowcount
    conn.commit()
    return count


def append_fix_log(rows: list[dict], count: int) -> None:
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Fix place-country_code mismatches in imprints",
        "records_affected": count,
        "mms_ids": sorted(set(r["mms_id"] for r in rows)),
        "fields_changed": ["country_code"],
        "method": "place_country_crossref",
        "details": [
            {"place": r["place_norm"], "old_cc": r["country_code_old"],
             "new_cc": r["country_code_new"]}
            for r in rows
        ],
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
            print(f"[{FIX_ID}] No affected rows found (already fixed or no mismatches).")
            return

        print(f"[{FIX_ID}] Found {len(rows)} place-country mismatches to fix:")
        for row in rows:
            print(f"  imprint_id={row['imprint_id']}  mms_id={row['mms_id']}  "
                  f"{row['place_norm']}: {row['country_code_old']} -> {row['country_code_new']}  "
                  f"({row['explanation']})")

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
