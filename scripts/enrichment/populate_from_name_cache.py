"""
Populate authority_enrichment table from name-based enrichment cache.

When agents don't have NLI authority URIs, we enrich by name search.
This script transfers those results into the authority_enrichment table,
using the agent_norm value as the linking key instead of authority_uri.

Usage:
    poetry run python -m scripts.enrichment.populate_from_name_cache
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def populate(
    bib_db_path: str = "data/index/bibliographic.db",
    cache_db_path: str = "data/enrichment/cache.db",
) -> dict:
    """Copy name-based enrichment cache into authority_enrichment table."""

    bib_db = Path(bib_db_path)
    cache_db = Path(cache_db_path)

    if not bib_db.exists():
        raise FileNotFoundError(f"Bibliographic DB not found: {bib_db}")
    if not cache_db.exists():
        raise FileNotFoundError(f"Enrichment cache not found: {cache_db}")

    bib_conn = sqlite3.connect(str(bib_db))
    bib_conn.execute("PRAGMA journal_mode=WAL")

    cache_conn = sqlite3.connect(str(cache_db))
    cache_conn.row_factory = sqlite3.Row

    now = datetime.utcnow().isoformat()
    expires = (datetime.utcnow() + timedelta(days=365)).isoformat()

    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    try:
        # Get all agent enrichment results from cache
        rows = cache_conn.execute("""
            SELECT
                entity_value,
                normalized_key,
                nli_id,
                wikidata_id,
                viaf_id,
                isni_id,
                loc_id,
                label,
                description,
                person_info,
                place_info,
                image_url,
                wikipedia_url,
                source,
                confidence,
                fetched_at
            FROM enrichment_cache
            WHERE entity_type = 'agent'
        """).fetchall()

        for row in rows:
            # Use normalized agent name as the authority_uri key
            # (since we don't have actual NLI URIs)
            entity_value = row["entity_value"]
            norm_key = row["normalized_key"]

            # Create a synthetic authority_uri based on agent name
            authority_uri = f"name:{norm_key}"

            # Check if record already exists
            existing = bib_conn.execute(
                "SELECT id FROM authority_enrichment WHERE authority_uri = ?",
                (authority_uri,)
            ).fetchone()

            if existing:
                bib_conn.execute("""
                    UPDATE authority_enrichment SET
                        nli_id = ?, wikidata_id = ?, viaf_id = ?,
                        isni_id = ?, loc_id = ?, label = ?,
                        description = ?, person_info = ?, place_info = ?,
                        image_url = ?, wikipedia_url = ?,
                        source = ?, confidence = ?,
                        fetched_at = ?, expires_at = ?
                    WHERE authority_uri = ?
                """, (
                    row["nli_id"], row["wikidata_id"], row["viaf_id"],
                    row["isni_id"], row["loc_id"], row["label"],
                    row["description"], row["person_info"], row["place_info"],
                    row["image_url"], row["wikipedia_url"],
                    row["source"] or "wikidata", row["confidence"] or 0.7,
                    row["fetched_at"] or now, expires,
                    authority_uri,
                ))
                stats["updated"] += 1
            else:
                bib_conn.execute("""
                    INSERT INTO authority_enrichment (
                        authority_uri, nli_id, wikidata_id, viaf_id,
                        isni_id, loc_id, label, description,
                        person_info, place_info, image_url, wikipedia_url,
                        source, confidence, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    authority_uri, row["nli_id"], row["wikidata_id"],
                    row["viaf_id"], row["isni_id"], row["loc_id"],
                    row["label"], row["description"], row["person_info"],
                    row["place_info"], row["image_url"], row["wikipedia_url"],
                    row["source"] or "wikidata", row["confidence"] or 0.7,
                    row["fetched_at"] or now, expires,
                ))
                stats["inserted"] += 1

        bib_conn.commit()

        # Verify
        total = bib_conn.execute("SELECT count(*) FROM authority_enrichment").fetchone()[0]
        with_wikidata = bib_conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE wikidata_id IS NOT NULL"
        ).fetchone()[0]
        with_person = bib_conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE person_info IS NOT NULL"
        ).fetchone()[0]

        stats["total_in_db"] = total
        stats["with_wikidata_id"] = with_wikidata
        stats["with_person_info"] = with_person

    finally:
        bib_conn.close()
        cache_conn.close()

    return stats


if __name__ == "__main__":
    stats = populate()
    print("Authority enrichment population complete:")
    print(f"  Inserted:         {stats['inserted']}")
    print(f"  Updated:          {stats['updated']}")
    print(f"  Skipped:          {stats['skipped']}")
    print("  ---")
    print(f"  Total in DB:      {stats['total_in_db']}")
    print(f"  With Wikidata ID: {stats['with_wikidata_id']}")
    print(f"  With person info: {stats['with_person_info']}")
