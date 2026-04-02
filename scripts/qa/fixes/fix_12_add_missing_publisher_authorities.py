"""
Fix 12: Add Missing Publisher Variant Links

Major historical publishers found in imprints (via publisher_norm) already have
publisher_authorities entries with rich metadata, but lack a publisher_variants
row mapping the normalized form back to the authority. This means the join from
imprints -> publisher_variants -> publisher_authorities fails for these publishers.

This script adds one publisher_variants row per publisher, linking the
publisher_norm value (e.g. "insel verlag") to its existing authority entry.

Where an authority entry already has correct research data (dates, location,
type, confidence >= 0.8), we leave it untouched. Where it is a stub or has
is_missing_marker=1, we update it with the researched data.

Raw values are preserved; this only adds linkage rows.
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
FIX_ID = "fix_12_add_missing_publisher_authorities"

# Research data for each publisher.
# Keys are the publisher_norm values (lowercase) found in imprints.
PUBLISHER_RESEARCH: list[dict] = [
    {
        "publisher_norm": "insel verlag",
        "canonical_name": "Insel Verlag",
        "type": "modern_publisher",
        "dates_active": "1901-present",
        "date_start": 1901,
        "date_end": None,
        "location": "Leipzig/Berlin, Germany",
    },
    {
        "publisher_norm": "bragadin press, venice",
        "canonical_name": "Bragadin Press, Venice",
        "type": "printing_house",
        "dates_active": "1550-1710",
        "date_start": 1550,
        "date_end": 1710,
        "location": "Venice, Italy",
    },
    {
        "publisher_norm": "a.a.m. stols",
        "canonical_name": "A.A.M. Stols",
        "type": "private_press",
        "dates_active": "1922-1942",
        "date_start": 1922,
        "date_end": 1942,
        "location": "Maastricht, Netherlands",
    },
    {
        "publisher_norm": "house of elzevir",
        "canonical_name": "House of Elzevir",
        "type": "printing_house",
        "dates_active": "1583-1712",
        "date_start": 1583,
        "date_end": 1712,
        "location": "Leiden/Amsterdam, Netherlands",
    },
    {
        "publisher_norm": "ferdinand dummler, berlin",
        "canonical_name": "Ferdinand Dummler, Berlin",
        "type": "printing_house",
        "dates_active": "1808-1870s",
        "date_start": 1808,
        "date_end": 1870,
        "location": "Berlin, Germany",
    },
    {
        "publisher_norm": "francke orphanage press, halle",
        "canonical_name": "Francke Orphanage Press, Halle",
        "type": "printing_house",
        "dates_active": "1698-1800s",
        "date_start": 1698,
        "date_end": 1800,
        "location": "Halle, Germany",
    },
    {
        "publisher_norm": "aldine press, venice",
        "canonical_name": "Aldine Press, Venice",
        "type": "printing_house",
        "dates_active": "1494-1597",
        "date_start": 1494,
        "date_end": 1597,
        "location": "Venice, Italy",
    },
    {
        "publisher_norm": "vendramin press, venice",
        "canonical_name": "Vendramin Press, Venice",
        "type": "printing_house",
        "dates_active": "1630-1750",
        "date_start": 1630,
        "date_end": 1750,
        "location": "Venice, Italy",
    },
    {
        "publisher_norm": "daniel bomberg, venice",
        "canonical_name": "Daniel Bomberg, Venice",
        "type": "printing_house",
        "dates_active": "1516-1549",
        "date_start": 1516,
        "date_end": 1549,
        "location": "Venice, Italy",
    },
    {
        "publisher_norm": "blaeu, amsterdam",
        "canonical_name": "Blaeu, Amsterdam",
        "type": "printing_house",
        "dates_active": "1596-1672",
        "date_start": 1596,
        "date_end": 1672,
        "location": "Amsterdam, Netherlands",
    },
    {
        "publisher_norm": "christophe plantin, antwerp",
        "canonical_name": "Christophe Plantin, Antwerp",
        "type": "printing_house",
        "dates_active": "1555-1589",
        "date_start": 1555,
        "date_end": 1589,
        "location": "Antwerp, Belgium",
    },
]


def find_gaps(conn: sqlite3.Connection) -> list[dict]:
    """Find publishers that need a variant row linking publisher_norm to authority."""
    gaps = []
    for pub in PUBLISHER_RESEARCH:
        pn = pub["publisher_norm"]
        # Check if authority exists
        cur = conn.execute(
            "SELECT id, canonical_name, type, confidence, is_missing_marker "
            "FROM publisher_authorities WHERE canonical_name_lower = ?",
            (pn,),
        )
        auth_row = cur.fetchone()

        # Check if variant already exists for this exact publisher_norm
        cur2 = conn.execute(
            "SELECT id FROM publisher_variants WHERE variant_form_lower = ?",
            (pn,),
        )
        variant_row = cur2.fetchone()

        # Count imprint records
        cur3 = conn.execute(
            "SELECT COUNT(DISTINCT record_id) FROM imprints WHERE LOWER(publisher_norm) = ?",
            (pn,),
        )
        record_count = cur3.fetchone()[0]

        gaps.append({
            "publisher_norm": pn,
            "canonical_name": pub["canonical_name"],
            "type": pub["type"],
            "dates_active": pub["dates_active"],
            "date_start": pub["date_start"],
            "date_end": pub["date_end"],
            "location": pub["location"],
            "authority_exists": auth_row is not None,
            "authority_id": auth_row[0] if auth_row else None,
            "authority_confidence": auth_row[3] if auth_row else None,
            "authority_is_missing": auth_row[4] if auth_row else None,
            "variant_exists": variant_row is not None,
            "record_count": record_count,
        })
    return gaps


def archive_state(gaps: list[dict], archive_dir: Path) -> Path:
    """Archive current state before modifications."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    path = archive_dir / f"{FIX_ID}_archive.json"
    payload = {
        "fix_id": FIX_ID,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "publisher_count": len(gaps),
        "publishers": gaps,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def apply_fixes(conn: sqlite3.Connection, gaps: list[dict]) -> dict:
    """Create authority entries (if missing) and variant rows. Returns counts."""
    now = datetime.now(timezone.utc).isoformat()
    authorities_created = 0
    authorities_updated = 0
    variants_created = 0

    for gap in gaps:
        authority_id = gap["authority_id"]

        # Step 1: Create authority if it doesn't exist
        if not gap["authority_exists"]:
            conn.execute(
                """
                INSERT INTO publisher_authorities
                    (canonical_name, canonical_name_lower, type, dates_active,
                     date_start, date_end, location, confidence,
                     is_missing_marker, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0.8, 0, ?, ?)
                """,
                (
                    gap["canonical_name"],
                    gap["publisher_norm"],
                    gap["type"],
                    gap["dates_active"],
                    gap["date_start"],
                    gap["date_end"],
                    gap["location"],
                    now, now,
                ),
            )
            authority_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            authorities_created += 1
        elif gap["authority_is_missing"] == 1:
            # Update stub authority with researched data
            conn.execute(
                """
                UPDATE publisher_authorities
                SET type = ?, dates_active = ?, date_start = ?, date_end = ?,
                    location = ?, confidence = 0.8, is_missing_marker = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    gap["type"],
                    gap["dates_active"],
                    gap["date_start"],
                    gap["date_end"],
                    gap["location"],
                    now,
                    authority_id,
                ),
            )
            authorities_updated += 1

        # Step 2: Create variant linking publisher_norm -> authority
        if not gap["variant_exists"] and authority_id is not None:
            conn.execute(
                """
                INSERT INTO publisher_variants
                    (authority_id, variant_form, variant_form_lower, script,
                     is_primary, priority, notes, created_at)
                VALUES (?, ?, ?, 'latin', 1, 0,
                        'fix_12: normalized form from imprints', ?)
                """,
                (
                    authority_id,
                    gap["canonical_name"],
                    gap["publisher_norm"],
                    now,
                ),
            )
            variants_created += 1

    conn.commit()
    return {
        "authorities_created": authorities_created,
        "authorities_updated": authorities_updated,
        "variants_created": variants_created,
    }


def append_fix_log(gaps: list[dict], counts: dict) -> None:
    """Append one JSONL entry to the fix log."""
    FIX_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fix_id": FIX_ID,
        "description": "Add publisher_variants rows linking publisher_norm to existing authorities",
        "publishers_processed": len(gaps),
        "authorities_created": counts["authorities_created"],
        "authorities_updated": counts["authorities_updated"],
        "variants_created": counts["variants_created"],
        "total_records_linked": sum(g["record_count"] for g in gaps),
        "tables_changed": ["publisher_authorities", "publisher_variants"],
        "method": "manual_research_variant_link",
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
    try:
        gaps = find_gaps(conn)

        needs_work = [g for g in gaps if not g["variant_exists"]]
        already_done = [g for g in gaps if g["variant_exists"]]

        print(f"[{FIX_ID}] Publisher variant linkage analysis:")
        print(f"  Total publishers checked: {len(gaps)}")
        print(f"  Need variant rows: {len(needs_work)}")
        print(f"  Already linked: {len(already_done)}")
        print()

        for g in gaps:
            status = "OK" if g["variant_exists"] else "MISSING"
            auth_status = "exists" if g["authority_exists"] else "CREATE"
            if g["authority_is_missing"] == 1:
                auth_status = "UPDATE (stub)"
            print(f"  [{status}] {g['canonical_name']:<35s} "
                  f"records={g['record_count']:>3d}  "
                  f"authority={auth_status}")

        if not needs_work:
            print(f"\n[{FIX_ID}] All publishers already linked. Nothing to do.")
            return

        if args.dry_run:
            print(f"\n[{FIX_ID}] DRY RUN -- would create {len(needs_work)} variant rows.")
            return

        archive_path = archive_state(gaps, ARCHIVE_DIR)
        print(f"\n[{FIX_ID}] Archived state to {archive_path}")

        counts = apply_fixes(conn, needs_work)
        print(f"[{FIX_ID}] Results:")
        print(f"  Authorities created: {counts['authorities_created']}")
        print(f"  Authorities updated (stubs): {counts['authorities_updated']}")
        print(f"  Variants created: {counts['variants_created']}")

        append_fix_log(gaps, counts)
        print(f"[{FIX_ID}] Appended to fix log: {FIX_LOG}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
