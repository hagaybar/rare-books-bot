"""
Populate the authority_enrichment table in bibliographic.db from enrichment cache.

Moves cached Wikidata enrichment data into the main bibliographic database
so the UI can display it.

Strategy:
1. For enrichment_cache entries WITH nli_id: look up the authority_uri from agents table
2. For enrichment_cache entries WITHOUT nli_id (name-based): match by agent_norm
3. For nli_identifiers entries not already in enrichment_cache: add as NLI-only

Usage:
    poetry run python -m scripts.enrichment.populate_authority_enrichment

This is idempotent -- running it again will update existing records.
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
    bib_conn.row_factory = sqlite3.Row

    cache_conn = sqlite3.connect(str(cache_db))
    cache_conn.row_factory = sqlite3.Row

    now = datetime.utcnow().isoformat()
    expires = (datetime.utcnow() + timedelta(days=365)).isoformat()

    stats = {"inserted": 0, "updated": 0, "skipped": 0, "nli_only": 0}

    try:
        # Build a mapping of nli_id -> authority_uri from agents table
        nli_to_uri = {}
        agent_norm_to_uri = {}
        agent_rows = bib_conn.execute("""
            SELECT DISTINCT agent_norm, authority_uri
            FROM agents
            WHERE authority_uri IS NOT NULL
        """).fetchall()
        for row in agent_rows:
            agent_norm = row["agent_norm"]
            authority_uri = row["authority_uri"]
            agent_norm_to_uri[agent_norm] = authority_uri

            # Extract NLI ID from URI
            if authority_uri and "authorities/" in authority_uri:
                nli_id = authority_uri.split("authorities/")[-1].replace(".jsonld", "")
                nli_to_uri[nli_id] = authority_uri

        print(f"  Agent mappings: {len(agent_norm_to_uri)} by name, {len(nli_to_uri)} by NLI ID")

        # Phase 1: Insert fully enriched records from enrichment_cache
        cache_rows = cache_conn.execute("""
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

        for row in cache_rows:
            entity_value = row["entity_value"]
            nli_id = row["nli_id"]

            # Determine authority_uri: prefer NLI ID match, then name match
            authority_uri = None
            if nli_id and nli_id in nli_to_uri:
                authority_uri = nli_to_uri[nli_id]
            elif entity_value in agent_norm_to_uri:
                authority_uri = agent_norm_to_uri[entity_value]

            if not authority_uri:
                # If we have nli_id but no match in agents, construct the URI
                if nli_id:
                    authority_uri = (
                        f"https://open-eu.hosted.exlibrisgroup.com/alma/"
                        f"972NNL_INST/authorities/{nli_id}.jsonld"
                    )
                else:
                    # Can't determine authority_uri, use entity_value as fallback
                    authority_uri = entity_value

            # Extract NLI ID from authority_uri if not already set
            if not nli_id and authority_uri and "authorities/" in authority_uri:
                nli_id = authority_uri.split("authorities/")[-1].replace(".jsonld", "")

            # Upsert into authority_enrichment
            existing = bib_conn.execute(
                "SELECT id FROM authority_enrichment WHERE authority_uri = ?",
                (authority_uri,)
            ).fetchone()

            values = (
                nli_id, row["wikidata_id"], row["viaf_id"],
                row["isni_id"], row["loc_id"], row["label"],
                row["description"], row["person_info"], row["place_info"],
                row["image_url"], row["wikipedia_url"],
                row["source"] or "wikidata", row["confidence"] or 0.95,
                row["fetched_at"] or now, expires,
            )

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
                """, values + (authority_uri,))
                stats["updated"] += 1
            else:
                bib_conn.execute("""
                    INSERT INTO authority_enrichment (
                        authority_uri, nli_id, wikidata_id, viaf_id,
                        isni_id, loc_id, label, description,
                        person_info, place_info, image_url, wikipedia_url,
                        source, confidence, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (authority_uri,) + values)
                stats["inserted"] += 1

        # Phase 2: Add NLI-only records (have NLI mapping but no full enrichment)
        # These are agents where we know the Wikidata ID from NLI but didn't
        # successfully fetch the full Wikidata profile
        enriched_nli_ids = set()
        for row in cache_rows:
            if row["nli_id"]:
                enriched_nli_ids.add(row["nli_id"])

        nli_rows = cache_conn.execute("""
            SELECT
                nli_id,
                wikidata_id,
                viaf_id,
                isni_id,
                loc_id,
                fetch_method
            FROM nli_identifiers
            WHERE status = 'success'
        """).fetchall()

        for row in nli_rows:
            nli_id = row["nli_id"]

            # Skip if already enriched in Phase 1
            if nli_id in enriched_nli_ids:
                stats["skipped"] += 1
                continue

            # Get authority_uri from agents table
            authority_uri = nli_to_uri.get(nli_id)
            if not authority_uri:
                authority_uri = (
                    f"https://open-eu.hosted.exlibrisgroup.com/alma/"
                    f"972NNL_INST/authorities/{nli_id}.jsonld"
                )

            existing = bib_conn.execute(
                "SELECT id FROM authority_enrichment WHERE authority_uri = ?",
                (authority_uri,)
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

        # Fix Wikipedia URLs: replace Wikidata fallback URLs with real Wikipedia article URLs
        # from wikipedia_cache where available
        try:
            fixed_urls = bib_conn.execute("""
                UPDATE authority_enrichment
                SET wikipedia_url = 'https://en.wikipedia.org/wiki/' || REPLACE(wc.wikipedia_title, ' ', '_')
                FROM wikipedia_cache wc
                WHERE authority_enrichment.wikidata_id = wc.wikidata_id
                  AND wc.wikipedia_title IS NOT NULL
            """).rowcount
            bib_conn.commit()
            stats["wikipedia_urls_fixed"] = fixed_urls
        except Exception:
            stats["wikipedia_urls_fixed"] = 0

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
