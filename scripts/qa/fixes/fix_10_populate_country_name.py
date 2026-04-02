"""
Fix 10: Populate country_name from country_code

The imprints table has a country_code column (MARC 008/15-17) but
country_name is unpopulated (0 of ~2,773 rows). This script fills
country_name using the MARC Code List for Countries.

Does NOT change country_code -- only populates the empty country_name column.
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
FIX_ID = "fix_10_populate_country_name"

# MARC Code List for Countries
# Full reference: https://www.loc.gov/marc/countries/
# This mapping covers all codes found in the database plus common extras.
MARC_COUNTRY_MAP: dict[str, str] = {
    # -- European countries --
    "gw": "Germany",
    "fr": "France",
    "ne": "Netherlands",
    "it": "Italy",
    "enk": "England",
    "sz": "Switzerland",
    "pl": "Poland",
    "au": "Austria",
    "be": "Belgium",
    "sp": "Spain",
    "po": "Portugal",
    "ru": "Russia",
    "tu": "Turkey",
    "hu": "Hungary",
    "dk": "Denmark",
    "sw": "Sweden",
    "xr": "Czech Republic",
    "gr": "Greece",
    "lv": "Latvia",
    "ie": "Ireland",
    "li": "Liechtenstein",
    "mc": "Monaco",
    "stk": "Scotland",
    "wlk": "Wales",
    "rm": "Romania",
    "ua": "Ukraine",
    "cy": "Cyprus",
    # -- Middle East / Africa --
    "is": "Israel",
    "eg": "Egypt",
    "et": "Ethiopia",
    "ea": "Indonesia",
    "sy": "Syria",
    "ye": "Yemen",
    "sa": "Saudi Arabia",
    "ti": "Tunisia",
    # -- Asia --
    "ii": "India",
    "ja": "Japan",
    "ko": "Korea",
    # -- Baltic / Eastern Europe --
    "aa": "Albania",  # MARC code; note: one record has place=Prague, possible data error
    "er": "Estonia",
    # -- Americas --
    "mx": "Mexico",
    "ag": "Argentina",
    "bl": "Brazil",
    "bw": "Belarus",
    # -- US states (MARC uses state-level codes) --
    "mau": "Massachusetts",
    "ilu": "Illinois",
    "nyu": "New York (State)",
    "pau": "Pennsylvania",
    "cau": "California",
    "nju": "New Jersey",
    "miu": "Michigan",
    "mou": "Missouri",
    "ohu": "Ohio",
    "ncu": "North Carolina",
    "lau": "Louisiana",
    "meu": "Maine",
    "vra": "Virginia",
    # -- Canadian provinces --
    "onc": "Ontario",
    # -- Special codes --
    "xx": "Unknown",
    "un": "Undetermined",
    # -- Pipe-separated junk (data quality issue) --
    "|||": None,  # Pipe characters = missing data
}


def find_affected(conn: sqlite3.Connection) -> list[dict]:
    """Find imprints where country_code is set but country_name is empty."""
    cur = conn.execute(
        """
        SELECT i.id, i.record_id, i.country_code, i.country_name, r.mms_id
        FROM imprints i
        JOIN records r ON r.id = i.record_id
        WHERE i.country_code IS NOT NULL
          AND i.country_code <> ''
          AND (i.country_name IS NULL OR i.country_name = '')
        ORDER BY i.id
        """
    )
    rows = []
    for row in cur.fetchall():
        code = row[2].strip() if row[2] else row[2]
        mapped_name = MARC_COUNTRY_MAP.get(code)
        rows.append({
            "imprint_id": row[0],
            "record_id": row[1],
            "country_code": code,
            "country_name_old": row[3],
            "country_name_new": mapped_name,
            "mms_id": row[4],
            "unmapped": mapped_name is None and code != "|||",
        })
    return rows


def archive(rows: list[dict], archive_dir: Path) -> Path:
    """Write original values to archive JSON."""
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


def apply_fixes(conn: sqlite3.Connection, rows: list[dict]) -> dict:
    """Update country_name for affected imprints. Returns counts."""
    updated = 0
    skipped_null = 0
    skipped_unmapped = 0

    for row in rows:
        new_name = row["country_name_new"]
        if new_name is None:
            if row["unmapped"]:
                skipped_unmapped += 1
            else:
                skipped_null += 1
            continue

        conn.execute(
            """
            UPDATE imprints
            SET country_name = ?
            WHERE id = ?
              AND (country_name IS NULL OR country_name = '')
            """,
            (new_name, row["imprint_id"]),
        )
        updated += 1

    conn.commit()
    return {
        "updated": updated,
        "skipped_null_code": skipped_null,
        "skipped_unmapped_code": skipped_unmapped,
    }


def append_fix_log(rows: list[dict], counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)

    unmapped_codes = sorted(set(
        r["country_code"] for r in rows if r["unmapped"]
    ))

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Populate country_name from MARC country codes",
        "records_affected": counts["updated"],
        "fields_changed": ["country_name"],
        "method": "marc_country_code_map",
        "counts": counts,
        "unmapped_codes": unmapped_codes,
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
            print(f"[{FIX_ID}] No imprints with empty country_name found (already fixed).")
            return

        # Summary by code
        code_counts: dict[str, int] = {}
        for r in rows:
            code_counts[r["country_code"]] = code_counts.get(r["country_code"], 0) + 1

        mappable = [r for r in rows if r["country_name_new"] is not None]
        unmapped = [r for r in rows if r["unmapped"]]

        print(f"[{FIX_ID}] Found {len(rows)} imprints with empty country_name.")
        print(f"  Mappable: {len(mappable)}")
        print(f"  Unmapped codes: {len(unmapped)}")

        print(f"\n[{FIX_ID}] Country code distribution (top 20):")
        for code, count in sorted(code_counts.items(), key=lambda x: -x[1])[:20]:
            name = MARC_COUNTRY_MAP.get(code, "??? UNMAPPED")
            print(f"  {code:>4s} -> {name:<25s} ({count} imprints)")

        if unmapped:
            unmapped_codes = sorted(set(r["country_code"] for r in unmapped))
            print(f"\n[{FIX_ID}] WARNING: Unmapped country codes: {unmapped_codes}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no changes made.")
            return

        archive_path = archive(rows, ARCHIVE_DIR)
        print(f"[{FIX_ID}] Archived {len(rows)} original values to {archive_path}")

        counts = apply_fixes(conn, rows)
        print(f"[{FIX_ID}] Updated {counts['updated']} imprints.")
        if counts["skipped_unmapped_code"]:
            print(f"[{FIX_ID}] Skipped {counts['skipped_unmapped_code']} with unmapped codes.")

        append_fix_log(rows, counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
