"""
Fix 11: Document Unresearched Publishers

Generate a CSV at data/qa/publisher-research-priorities.csv listing
publisher_authorities entries where type='unresearched', joined with
record counts and sample titles for prioritization.

This is analysis/documentation only -- no DB modifications.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path("data/index/bibliographic.db")
FIX_LOG = Path("data/qa/fix-log.jsonl")
OUTPUT_CSV = Path("data/qa/publisher-research-priorities.csv")
FIX_ID = "fix_11_document_unresearched_publishers"

MAX_SAMPLE_IDS = 5
MAX_SAMPLE_TITLES = 3


def query_unresearched(conn: sqlite3.Connection) -> list[dict]:
    """Query unresearched publishers with record counts and samples."""
    # Step 1: Get all unresearched publishers
    cur = conn.execute(
        """
        SELECT pa.id, pa.canonical_name, pa.type
        FROM publisher_authorities pa
        WHERE pa.type = 'unresearched'
        ORDER BY pa.canonical_name
        """
    )
    publishers = []
    for row in cur.fetchall():
        publishers.append({
            "authority_id": row[0],
            "canonical_name": row[1],
            "type": row[2],
        })

    results = []
    for pub in publishers:
        # Step 2: Get record IDs via publisher_variants -> imprints join
        cur = conn.execute(
            """
            SELECT DISTINCT i.record_id, r.mms_id
            FROM publisher_variants pv
            JOIN imprints i ON LOWER(i.publisher_norm) = pv.variant_form_lower
            JOIN records r ON r.id = i.record_id
            WHERE pv.authority_id = ?
            ORDER BY r.mms_id
            """,
            (pub["authority_id"],),
        )
        record_rows = cur.fetchall()
        record_ids = [r[0] for r in record_rows]
        mms_ids = [r[1] for r in record_rows]

        # Step 3: Get sample titles
        sample_titles = []
        for rid in record_ids[:MAX_SAMPLE_TITLES]:
            tcur = conn.execute(
                "SELECT value FROM titles WHERE record_id = ? AND title_type = 'main' LIMIT 1",
                (rid,),
            )
            trow = tcur.fetchone()
            if trow:
                title = trow[0]
                # Truncate long titles
                if len(title) > 80:
                    title = title[:77] + "..."
                sample_titles.append(title)

        results.append({
            "canonical_name": pub["canonical_name"],
            "record_count": len(record_ids),
            "type": pub["type"],
            "sample_mms_ids": "; ".join(mms_ids[:MAX_SAMPLE_IDS]),
            "sample_titles": " | ".join(sample_titles),
        })

    # Sort by record count descending
    results.sort(key=lambda x: -x["record_count"])
    return results


def write_csv(results: list[dict], output_path: Path) -> None:
    """Write results to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "canonical_name", "record_count", "type",
        "sample_mms_ids", "sample_titles",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def append_fix_log(results: list[dict]) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    total_records = sum(r["record_count"] for r in results)
    with_records = sum(1 for r in results if r["record_count"] > 0)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Generated publisher research priority CSV (analysis only, no DB changes)",
        "publishers_total": len(results),
        "publishers_with_records": with_records,
        "total_linked_records": total_records,
        "output_file": str(OUTPUT_CSV),
        "tables_changed": [],
        "method": "documentation_only",
    }
    with open(FIX_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only, do not write CSV or fix log")
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV,
                        help="Output CSV path")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db_path))
    try:
        results = query_unresearched(conn)
        if not results:
            print(f"[{FIX_ID}] No unresearched publishers found.")
            return

        total_records = sum(r["record_count"] for r in results)
        with_records = sum(1 for r in results if r["record_count"] > 0)
        without_records = len(results) - with_records

        print(f"[{FIX_ID}] Found {len(results)} unresearched publishers.")
        print(f"  With linked records: {with_records} ({total_records} total records)")
        print(f"  Without linked records: {without_records}")

        print(f"\n[{FIX_ID}] Top 15 by record count:")
        for r in results[:15]:
            print(f"  {r['record_count']:>4d} records  {r['canonical_name']}")
            if r["sample_titles"]:
                print(f"              sample: {r['sample_titles'][:80]}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no CSV or fix log written.")
            return

        output_path = args.output
        write_csv(results, output_path)
        print(f"\n[{FIX_ID}] Wrote {len(results)} rows to {output_path}")

        append_fix_log(results)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
