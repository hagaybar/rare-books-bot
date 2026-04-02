"""
Fix 16: Investigate Subjectless Records

Analysis/documentation script (no DB modifications). Examines the 349 records
with no subjects to understand patterns and identify records that could benefit
from subject enrichment.

Outputs:
- data/qa/subjectless-records-analysis.csv (detailed per-record data)
- Console summary with categorization
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
OUTPUT_CSV = Path("data/qa/subjectless-records-analysis.csv")
FIX_ID = "fix_16_investigate_subjectless_records"


def get_subjectless_records(conn: sqlite3.Connection) -> list[int]:
    """Get record IDs that have no subjects."""
    cur = conn.execute(
        """
        SELECT r.id
        FROM records r
        WHERE r.id NOT IN (SELECT DISTINCT record_id FROM subjects)
        ORDER BY r.id
        """
    )
    return [row[0] for row in cur.fetchall()]


def collect_record_details(conn: sqlite3.Connection, record_ids: list[int]) -> list[dict]:
    """Collect detailed information for each subjectless record."""
    results = []
    for rid in record_ids:
        # Basic record info
        cur = conn.execute(
            "SELECT mms_id, source_file FROM records WHERE id = ?", (rid,)
        )
        rec = cur.fetchone()
        if not rec:
            continue
        mms_id = rec[0]

        # Title
        cur = conn.execute(
            "SELECT value FROM titles WHERE record_id = ? AND title_type = 'main' LIMIT 1",
            (rid,),
        )
        title_row = cur.fetchone()
        title = title_row[0] if title_row else ""
        if len(title) > 120:
            title = title[:117] + "..."

        # Date
        cur = conn.execute(
            "SELECT date_start, date_end, place_norm FROM imprints WHERE record_id = ? LIMIT 1",
            (rid,),
        )
        imp = cur.fetchone()
        date_start = imp[0] if imp else None
        date_end = imp[1] if imp else None
        place_norm = imp[2] if imp else None

        # Languages
        cur = conn.execute(
            "SELECT code FROM languages WHERE record_id = ? ORDER BY code",
            (rid,),
        )
        lang_codes = [row[0] for row in cur.fetchall()]

        # Agent names
        cur = conn.execute(
            "SELECT DISTINCT agent_norm FROM agents WHERE record_id = ? ORDER BY agent_index LIMIT 5",
            (rid,),
        )
        agent_names = [row[0] for row in cur.fetchall()]

        # Notes: get tag names present
        cur = conn.execute(
            "SELECT DISTINCT tag FROM notes WHERE record_id = ? ORDER BY tag",
            (rid,),
        )
        note_tags = [row[0] for row in cur.fetchall()]

        # Full note texts (for content analysis, truncated)
        cur = conn.execute(
            "SELECT tag, value FROM notes WHERE record_id = ? ORDER BY tag LIMIT 10",
            (rid,),
        )
        note_texts = []
        for nrow in cur.fetchall():
            text = nrow[1]
            if len(text) > 200:
                text = text[:197] + "..."
            note_texts.append(f"[{nrow[0]}] {text}")

        results.append({
            "record_id": rid,
            "mms_id": mms_id,
            "title": title,
            "date_start": date_start,
            "date_end": date_end,
            "place_norm": place_norm,
            "languages": "; ".join(lang_codes),
            "agent_names": "; ".join(agent_names),
            "note_tags": "; ".join(note_tags),
            "note_texts_preview": " | ".join(note_texts[:3]),
            "lang_codes": lang_codes,
            "has_notes": len(note_tags) > 0,
        })
    return results


def categorize(records: list[dict]) -> dict:
    """Categorize records by various dimensions."""
    # By language
    by_language: dict[str, int] = {}
    for rec in records:
        for code in rec["lang_codes"]:
            by_language[code] = by_language.get(code, 0) + 1

    # By date period
    by_period: dict[str, int] = {
        "before_1500": 0,
        "1500_1700": 0,
        "1700_1900": 0,
        "1900_1950": 0,
        "after_1950": 0,
        "no_date": 0,
    }
    for rec in records:
        ds = rec["date_start"]
        if ds is None:
            by_period["no_date"] += 1
        elif ds < 1500:
            by_period["before_1500"] += 1
        elif ds < 1700:
            by_period["1500_1700"] += 1
        elif ds < 1900:
            by_period["1700_1900"] += 1
        elif ds <= 1950:
            by_period["1900_1950"] += 1
        else:
            by_period["after_1950"] += 1

    # Hebrew records (potential liturgical texts)
    hebrew_records = [
        r for r in records if "heb" in r["lang_codes"]
    ]

    # Hebrew with liturgical keywords in title
    liturgical_keywords = [
        "siddur", "machzor", "mahzor", "haggadah", "hagadah",
        "selichot", "kinot", "tehilim", "psalms", "prayer",
        "סדור", "סידור", "מחזור", "הגדה", "סליחות", "קינות",
        "תהלים", "תפלה", "תפילה",
    ]
    liturgical = []
    for r in hebrew_records:
        title_lower = r["title"].lower()
        if any(kw in title_lower for kw in liturgical_keywords):
            liturgical.append(r)

    # Modern reprints (date > 1950)
    modern = [r for r in records if r["date_start"] and r["date_start"] > 1950]

    # Records with rich notes that might suggest subjects
    with_notes = [r for r in records if r["has_notes"]]

    # Records with content-bearing note tags (500, 505, 520)
    content_note_tags = {"500", "505", "520", "546", "590"}
    with_content_notes = []
    for r in records:
        tags = set(r["note_tags"].split("; ")) if r["note_tags"] else set()
        if tags & content_note_tags:
            with_content_notes.append(r)

    return {
        "by_language": by_language,
        "by_period": by_period,
        "hebrew_total": len(hebrew_records),
        "hebrew_liturgical": len(liturgical),
        "modern_reprints": len(modern),
        "with_notes": len(with_notes),
        "with_content_notes": len(with_content_notes),
        "liturgical_sample": liturgical[:5],
        "modern_sample": modern[:5],
    }


def write_csv(records: list[dict], output_path: Path) -> None:
    """Write detailed analysis to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "record_id", "mms_id", "title", "date_start", "date_end",
        "place_norm", "languages", "agent_names", "note_tags",
        "note_texts_preview",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(records)


def append_fix_log(records: list[dict], categories: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Analysis of records without subjects (no DB modifications)",
        "subjectless_count": len(records),
        "by_language": categories["by_language"],
        "by_period": categories["by_period"],
        "hebrew_total": categories["hebrew_total"],
        "hebrew_liturgical": categories["hebrew_liturgical"],
        "modern_reprints": categories["modern_reprints"],
        "with_notes": categories["with_notes"],
        "with_content_notes": categories["with_content_notes"],
        "output_file": str(OUTPUT_CSV),
        "tables_changed": [],
        "method": "analysis_only",
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
        record_ids = get_subjectless_records(conn)
        if not record_ids:
            print(f"[{FIX_ID}] No subjectless records found.")
            return

        print(f"[{FIX_ID}] Found {len(record_ids)} records without subjects")

        records = collect_record_details(conn, record_ids)
        categories = categorize(records)

        # Print summary
        print(f"\n{'=' * 60}")
        print("  SUBJECTLESS RECORDS ANALYSIS")
        print(f"{'=' * 60}")

        print("\n  By language:")
        for lang, cnt in sorted(
            categories["by_language"].items(), key=lambda x: -x[1]
        ):
            print(f"    {lang:<6s} {cnt:>4d}")

        print("\n  By date period:")
        for period, cnt in categories["by_period"].items():
            if cnt > 0:
                print(f"    {period:<15s} {cnt:>4d}")

        print("\n  Hebrew analysis:")
        print(f"    Total Hebrew records: {categories['hebrew_total']}")
        print(f"    Likely liturgical texts: {categories['hebrew_liturgical']}")
        if categories["liturgical_sample"]:
            print("    Sample liturgical:")
            for r in categories["liturgical_sample"]:
                print(f"      {r['mms_id']}  {r['title'][:60]}")

        print(f"\n  Modern reprints (date > 1950): {categories['modern_reprints']}")
        if categories["modern_sample"]:
            for r in categories["modern_sample"][:3]:
                print(f"    {r['mms_id']}  date={r['date_start']}  {r['title'][:50]}")

        print("\n  Notes analysis:")
        print(f"    Records with any notes: {categories['with_notes']}")
        print(f"    Records with content notes (500/505/520/546/590): "
              f"{categories['with_content_notes']}")

        print(f"\n{'=' * 60}")

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- no CSV or fix log written.")
            return

        output_path = args.output
        write_csv(records, output_path)
        print(f"\n[{FIX_ID}] Wrote {len(records)} rows to {output_path}")

        append_fix_log(records, categories)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
