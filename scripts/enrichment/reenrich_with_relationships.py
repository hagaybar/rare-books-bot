"""
Re-enrich all cached agents with extended Wikidata data (relationships).

Fetches teachers, students, notable works, languages, Hebrew labels,
and described-by sources for all agents that already have Wikidata IDs.

Usage:
    poetry run python -m scripts.enrichment.reenrich_with_relationships
"""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.enrichment.wikidata_client import enrich_agent_by_id


CACHE_DB = Path("data/enrichment/cache.db")
BIB_DB = Path("data/index/bibliographic.db")
BATCH_SIZE = 10
DELAY_BETWEEN_BATCHES = 1.5  # seconds


async def reenrich_all():
    """Re-fetch all cached agents with extended SPARQL query."""
    if not CACHE_DB.exists():
        print(f"Cache DB not found: {CACHE_DB}")
        return

    conn = sqlite3.connect(str(CACHE_DB))
    conn.row_factory = sqlite3.Row

    # Get all agents with wikidata IDs
    rows = conn.execute(
        "SELECT id, wikidata_id, entity_value, label FROM enrichment_cache "
        "WHERE entity_type = 'agent' AND wikidata_id IS NOT NULL "
        "ORDER BY id"
    ).fetchall()

    total = len(rows)
    print(f"Re-enriching {total} agents with relationships...")
    print(f"Estimated time: ~{total * DELAY_BETWEEN_BATCHES / BATCH_SIZE / 60:.0f} minutes")
    print()

    updated = 0
    errors = 0
    skipped = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]

        for row in batch:
            wikidata_id = row["wikidata_id"]
            try:
                result = await enrich_agent_by_id(wikidata_id)
                if result and result.person_info:
                    pi = result.person_info
                    person_info_dict = pi.model_dump()

                    # Update the cache
                    conn.execute(
                        "UPDATE enrichment_cache SET "
                        "person_info = ?, label = ?, description = ?, "
                        "image_url = ? "
                        "WHERE wikidata_id = ? AND entity_type = 'agent'",
                        (
                            json.dumps(person_info_dict),
                            result.label,
                            result.description,
                            result.image_url,
                            wikidata_id,
                        )
                    )
                    updated += 1

                    # Show progress for interesting ones
                    if pi.teachers or pi.students or pi.notable_works:
                        teachers = len(pi.teachers)
                        students = len(pi.students)
                        works = len(pi.notable_works)
                        he = pi.hebrew_label or ""
                        print(f"  [{i + batch.index(row) + 1}/{total}] {result.label}"
                              f" {he} — {teachers}T {students}S {works}W")
                else:
                    skipped += 1

            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  ERROR [{wikidata_id}]: {e}")
                elif errors == 6:
                    print("  (suppressing further errors...)")

        conn.commit()

        # Progress report every 100
        processed = min(i + BATCH_SIZE, total)
        if processed % 100 == 0 or processed == total:
            print(f"Progress: {processed}/{total} ({updated} updated, {errors} errors, {skipped} skipped)")

        # Rate limit
        if i + BATCH_SIZE < total:
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    conn.commit()
    conn.close()

    print("\nRe-enrichment complete:")
    print(f"  Updated: {updated}")
    print(f"  Errors:  {errors}")
    print(f"  Skipped: {skipped}")
    print(f"  Total:   {total}")

    # Now repopulate bibliographic.db
    print("\nRepopulating authority_enrichment table...")
    from scripts.enrichment.populate_authority_enrichment import populate
    stats = populate(str(BIB_DB), str(CACHE_DB))
    print(f"  Inserted: {stats['inserted']}")
    print(f"  Updated:  {stats['updated']}")
    print(f"  Total:    {stats['total_in_db']}")


if __name__ == "__main__":
    asyncio.run(reenrich_all())
