"""Fix 17: Enrich publisher authority records from web research.

Updates publisher_authorities rows from 'unresearched' to their researched
type, dates, location, notes, and sources for publishers with confidence >= 0.90.

Input: data/qa/publisher-research-results.json
Target: publisher_authorities table in data/index/bibliographic.db
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "index" / "bibliographic.db"
RESEARCH_PATH = Path(__file__).resolve().parents[3] / "data" / "qa" / "publisher-research-results.json"
MIN_CONFIDENCE = 0.90


def run(*, dry_run: bool = False) -> dict:
    with open(RESEARCH_PATH) as f:
        data = json.load(f)

    publishers = [p for p in data["publishers"] if p["confidence"] >= MIN_CONFIDENCE]
    print(f"Publishers with confidence >= {MIN_CONFIDENCE}: {len(publishers)}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    updated = 0
    skipped = 0
    not_found = 0
    details = []

    try:
        for pub in publishers:
            raw_name = pub["raw_name"]
            # Find matching row by canonical_name_lower
            row = conn.execute(
                "SELECT id, canonical_name, type FROM publisher_authorities WHERE canonical_name_lower = ?",
                (raw_name.lower(),),
            ).fetchone()

            if not row:
                # Try matching by canonical_name (case-insensitive)
                row = conn.execute(
                    "SELECT id, canonical_name, type FROM publisher_authorities WHERE lower(canonical_name) = ?",
                    (raw_name.lower(),),
                ).fetchone()

            if not row:
                print(f"  NOT FOUND in DB: {raw_name}")
                not_found += 1
                continue

            if row["type"] != "unresearched":
                print(f"  SKIP (already researched): {raw_name} -> {row['type']}")
                skipped += 1
                continue

            sources_json = json.dumps(pub.get("sources", []))
            if not dry_run:
                conn.execute(
                    """UPDATE publisher_authorities SET
                        type = ?,
                        dates_active = ?,
                        date_start = ?,
                        date_end = ?,
                        location = ?,
                        notes = ?,
                        sources = ?,
                        confidence = ?
                    WHERE id = ?""",
                    (
                        pub["type"],
                        pub.get("dates_active"),
                        pub.get("date_start"),
                        pub.get("date_end"),
                        pub.get("location"),
                        pub.get("notes"),
                        sources_json,
                        pub["confidence"],
                        row["id"],
                    ),
                )

            updated += 1
            details.append(f"  {raw_name} -> {pub['type']} ({pub.get('location', '?')})")

            # Also update variant raw names if present
            for variant in pub.get("variant_raw_names", []):
                vrow = conn.execute(
                    "SELECT id, type FROM publisher_authorities WHERE canonical_name_lower = ?",
                    (variant.lower(),),
                ).fetchone()
                if vrow and vrow["type"] == "unresearched":
                    if not dry_run:
                        conn.execute(
                            """UPDATE publisher_authorities SET
                                type = ?,
                                dates_active = ?,
                                date_start = ?,
                                date_end = ?,
                                location = ?,
                                notes = ?,
                                sources = ?,
                                confidence = ?
                            WHERE id = ?""",
                            (
                                pub["type"],
                                pub.get("dates_active"),
                                pub.get("date_start"),
                                pub.get("date_end"),
                                pub.get("location"),
                                pub.get("notes", "") + f" (Variant of {raw_name})",
                                sources_json,
                                pub["confidence"],
                                vrow["id"],
                            ),
                        )
                    updated += 1
                    details.append(f"  {variant} -> {pub['type']} (variant of {raw_name})")

        if not dry_run:
            conn.commit()

        for d in details:
            print(d)

        result = {
            "updated": updated,
            "skipped": skipped,
            "not_found": not_found,
            "dry_run": dry_run,
        }
        print(f"\nResult: {result}")
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
