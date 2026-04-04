"""Fix 18: Apply proposed subject headings to subjectless records.

Inserts proposed subject headings from data/qa/proposed-subjects.json
into the subjects table for records that currently have no subjects.

Input: data/qa/proposed-subjects.json
Target: subjects table in data/index/bibliographic.db
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "index" / "bibliographic.db"
PROPOSALS_PATH = Path(__file__).resolve().parents[3] / "data" / "qa" / "proposed-subjects.json"


def run(*, dry_run: bool = False) -> dict:
    with open(PROPOSALS_PATH) as f:
        proposals = json.load(f)

    print(f"Total records with proposals: {len(proposals)}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    inserted = 0
    skipped_records = 0
    skipped_existing = 0
    not_found = 0
    details = []

    try:
        for rec in proposals:
            record_id = rec["record_id"]
            mms_id = rec["mms_id"]

            # Verify record exists
            row = conn.execute(
                "SELECT id FROM records WHERE id = ?", (record_id,)
            ).fetchone()
            if not row:
                # Try by mms_id
                row = conn.execute(
                    "SELECT id FROM records WHERE mms_id = ?", (mms_id,)
                ).fetchone()
                if not row:
                    not_found += 1
                    continue
                record_id = row["id"]

            # Check if record already has subjects (idempotency)
            existing = conn.execute(
                "SELECT count(*) FROM subjects WHERE record_id = ?", (record_id,)
            ).fetchone()[0]
            if existing > 0:
                skipped_records += 1
                continue

            for subj in rec.get("proposed_subjects", []):
                # Check for duplicate subject value on this record
                dup = conn.execute(
                    "SELECT count(*) FROM subjects WHERE record_id = ? AND value = ?",
                    (record_id, subj["value"]),
                ).fetchone()[0]
                if dup > 0:
                    skipped_existing += 1
                    continue

                # Build parts JSON (simple: just the main heading)
                parts = json.dumps({"a": subj["value"]})
                # Build source JSON (mark as auto-proposed)
                source = json.dumps([{
                    "method": "auto_proposed",
                    "confidence": subj["confidence"],
                    "reasoning": subj.get("reasoning", ""),
                }])

                if not dry_run:
                    conn.execute(
                        """INSERT INTO subjects
                            (record_id, value, source_tag, scheme, heading_lang, authority_uri, parts, source)
                        VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)""",
                        (
                            record_id,
                            subj["value"],
                            subj["source_tag"],
                            subj.get("scheme", "lcsh"),
                            parts,
                            source,
                        ),
                    )
                inserted += 1

            if rec.get("proposed_subjects"):
                details.append(
                    f"  record {record_id}: +{len(rec['proposed_subjects'])} subjects"
                )

        if not dry_run:
            conn.commit()

        # Print summary (limit output)
        for d in details[:20]:
            print(d)
        if len(details) > 20:
            print(f"  ... and {len(details) - 20} more records")

        result = {
            "inserted": inserted,
            "skipped_records_with_existing_subjects": skipped_records,
            "skipped_duplicate_subjects": skipped_existing,
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
