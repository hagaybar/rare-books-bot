"""
Populate the authority_enrichment table in bibliographic.db from enrichment cache.

Moves cached Wikidata enrichment data (2,665 agent records + 5,584 NLI ID mappings)
into the main bibliographic database so the UI can display it.

Usage:
    poetry run python -m scripts.enrichment.populate_authority_enrichment

This is idempotent — running it again will update existing records.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def populate(
    bib_db_path: str = "data/index/bibliographic.db",
    cache_db_path: str = "data/enrichment/cache.db",
) -> dict:
    """Copy enrichment cache into authority_enrichment table."""

    bib_db = Path(bib_db_path)
    cache_db = Path(cache_db_path)

    if not bib_db.exists():
        raise FileNotFoundError(f"Bibliographic DB not found: {bib_db}")
    if not cache_db.exists():
        raise FileNotFoundError(f"Enrichment cache not found: {cache_db}")

    # Connect to both databases
    bib_conn = sqlite3.connect(str(bib_db))
    bib_conn.execute("PRAGMA journal_mode=WAL")

    cache_conn = sqlite3.connect(str(cache_db))
    cache_conn.row_factory = sqlite3.Row

    now = datetime.utcnow().isoformat()
    expires = (datetime.utcnow() + timedelta(days=365)).isoformat()

    stats = {"inserted": 0, "updated": 0, "skipped": 0, "nli_only": 0}

    try:
        # Phase 1: Insert fully enriched records (have Wikidata data)
        rows = cache_conn.execute("""
            SELECT
                entity_value as authority_uri,
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
            # Extract NLI ID from the authority URI
            uri = row["authority_uri"]
            nli_id = None
            if uri and "authorities/" in uri:
                nli_id = uri.split("authorities/")[-1].replace(".jsonld", "")

            # Check if record already exists
            existing = bib_conn.execute(
                "SELECT id FROM authority_enrichment WHERE authority_uri = ?",
                (uri,)
            ).fetchone()

            if existing:
                # Update
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
                    nli_id, row["wikidata_id"], row["viaf_id"],
                    row["isni_id"], row["loc_id"], row["label"],
                    row["description"], row["person_info"], row["place_info"],
                    row["image_url"], row["wikipedia_url"],
                    row["source"] or "wikidata", row["confidence"] or 0.95,
                    row["fetched_at"] or now, expires,
                    uri,
                ))
                stats["updated"] += 1
            else:
                # Insert
                bib_conn.execute("""
                    INSERT INTO authority_enrichment (
                        authority_uri, nli_id, wikidata_id, viaf_id,
                        isni_id, loc_id, label, description,
                        person_info, place_info, image_url, wikipedia_url,
                        source, confidence, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    uri, nli_id, row["wikidata_id"], row["viaf_id"],
                    row["isni_id"], row["loc_id"], row["label"],
                    row["description"], row["person_info"], row["place_info"],
                    row["image_url"], row["wikipedia_url"],
                    row["source"] or "wikidata", row["confidence"] or 0.95,
                    row["fetched_at"] or now, expires,
                ))
                stats["inserted"] += 1

        # Phase 2: Add NLI-only records (have NLI mapping but no full enrichment)
        # These are agents where we know the external IDs but haven't fetched
        # the full Wikidata profile yet
        nli_rows = cache_conn.execute("""
            SELECT
                ni.nli_id,
                ni.wikidata_id,
                ni.viaf_id,
                ni.isni_id,
                ni.loc_id,
                ni.fetch_method
            FROM nli_identifiers ni
            WHERE ni.status = 'success'
            AND ni.nli_id NOT IN (
                SELECT REPLACE(REPLACE(entity_value,
                    'https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/', ''),
                    '.jsonld', '')
                FROM enrichment_cache
                WHERE entity_type = 'agent' AND nli_id IS NOT NULL
            )
        """).fetchall()

        for row in nli_rows:
            nli_id = row["nli_id"]
            authority_uri = f"https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/{nli_id}.jsonld"

            existing = bib_conn.execute(
                "SELECT id FROM authority_enrichment WHERE nli_id = ?",
                (nli_id,)
            ).fetchone()

            if existing:
                stats["skipped"] += 1
                continue

            bib_conn.execute("""
                INSERT INTO authority_enrichment (
                    authority_uri, nli_id, wikidata_id, viaf_id,
                    isni_id, loc_id, label, description,
                    person_info, place_info, image_url, wikipedia_url,
                    source, confidence, fetched_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                authority_uri, nli_id, row["wikidata_id"], row["viaf_id"],
                row["isni_id"], row["loc_id"], None, None,
                None, None, None, None,
                "nli_identifiers", 0.80,
                now, expires,
            ))
            stats["nli_only"] += 1

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
    print("Enrichment population complete:")
    print(f"  Inserted:       {stats['inserted']}")
    print(f"  Updated:        {stats['updated']}")
    print(f"  NLI-only added: {stats['nli_only']}")
    print(f"  Skipped:        {stats['skipped']}")
    print("  ---")
    print(f"  Total in DB:    {stats['total_in_db']}")
    print(f"  With Wikidata:  {stats['with_wikidata_id']}")
    print(f"  With person info: {stats['with_person_info']}")
