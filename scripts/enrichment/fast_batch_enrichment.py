#!/usr/bin/env python3
"""Fast batch enrichment using batched SPARQL queries.

Instead of querying Wikidata one NLI ID at a time, this script:
1. Batches NLI ID -> Wikidata ID lookups (50 IDs per SPARQL query)
2. Then batches Wikidata enrichment (5 agents at a time, parallel)
3. Stores results in the enrichment cache

This is ~10x faster than the serial approach.

Usage:
    python -m scripts.enrichment.fast_batch_enrichment [--limit N] [--dry-run]
"""

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).parents[2]))

import httpx

from scripts.enrichment.enrichment_service import (
    cache_put,
    init_cache_db,
    normalize_key,
)
from scripts.enrichment.models import (
    EnrichmentResult,
    EnrichmentSource,
    EntityType,
)
from scripts.enrichment.nli_client import extract_nli_id_from_uri
from scripts.enrichment.wikidata_client import enrich_agent_by_id


WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"


def get_all_agents_with_uris(biblio_db: Path) -> List[Tuple[str, str, str]]:
    """Get all agents with authority URIs.

    Returns:
        List of (agent_norm, authority_uri, nli_id) tuples
    """
    conn = sqlite3.connect(str(biblio_db))
    rows = conn.execute("""
        SELECT DISTINCT agent_norm, authority_uri
        FROM agents
        WHERE authority_uri IS NOT NULL
    """).fetchall()
    conn.close()

    results = []
    for agent_norm, uri in rows:
        nli_id = extract_nli_id_from_uri(uri)
        if nli_id:
            results.append((agent_norm, uri, nli_id))
    return results


def get_already_cached_nli_ids(cache_db: Path) -> Set[str]:
    """Get NLI IDs already in cache."""
    conn = sqlite3.connect(str(cache_db))
    conn.row_factory = sqlite3.Row

    cached = set()

    # Check enrichment_cache for entities where we stored the NLI ID
    rows = conn.execute(
        "SELECT nli_id FROM enrichment_cache WHERE nli_id IS NOT NULL"
    ).fetchall()
    cached.update(r["nli_id"] for r in rows)

    # Also check nli_identifiers table
    rows = conn.execute("SELECT nli_id FROM nli_identifiers").fetchall()
    cached.update(r["nli_id"] for r in rows)

    # Check by entity_value pattern (some cached entries use name as entity_value)
    # We need to check if the normalized key matches any agents
    conn.close()
    return cached


async def batch_resolve_nli_to_wikidata(
    nli_ids: List[str],
    batch_size: int = 50,
    delay: float = 2.0,
) -> Dict[str, str]:
    """Resolve NLI IDs to Wikidata IDs in batches.

    Uses VALUES clause to query multiple IDs per SPARQL request.

    Args:
        nli_ids: List of NLI authority IDs
        batch_size: IDs per SPARQL query
        delay: Delay between queries in seconds

    Returns:
        Dict mapping nli_id -> wikidata_id
    """
    mapping: Dict[str, str] = {}
    total_batches = (len(nli_ids) + batch_size - 1) // batch_size

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(nli_ids), batch_size):
            batch = nli_ids[i:i + batch_size]
            batch_num = i // batch_size + 1

            # Build VALUES clause
            values = " ".join(f'"{nid}"' for nid in batch)
            query = f"""
            SELECT ?nliId ?item WHERE {{
              VALUES ?nliId {{ {values} }}
              ?item wdt:P8189 ?nliId .
            }}
            """

            try:
                response = await client.get(
                    WIKIDATA_SPARQL_ENDPOINT,
                    params={"query": query, "format": "json"},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                bindings = data.get("results", {}).get("bindings", [])
                for b in bindings:
                    nli_id = b.get("nliId", {}).get("value")
                    item_uri = b.get("item", {}).get("value", "")
                    qid_match = re.search(r"(Q\d+)$", item_uri)
                    if nli_id and qid_match:
                        mapping[nli_id] = qid_match.group(1)

                found = len([b for b in batch if b in mapping])
                print(
                    f"  Batch {batch_num}/{total_batches}: "
                    f"{found}/{len(batch)} resolved "
                    f"(total: {len(mapping)})",
                    flush=True,
                )

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print(f"  Rate limited, waiting 30s...", flush=True)
                    await asyncio.sleep(30)
                    # Retry this batch
                    try:
                        response = await client.get(
                            WIKIDATA_SPARQL_ENDPOINT,
                            params={"query": query, "format": "json"},
                            headers=headers,
                        )
                        response.raise_for_status()
                        data = response.json()
                        bindings = data.get("results", {}).get("bindings", [])
                        for b in bindings:
                            nli_id = b.get("nliId", {}).get("value")
                            item_uri = b.get("item", {}).get("value", "")
                            qid_match = re.search(r"(Q\d+)$", item_uri)
                            if nli_id and qid_match:
                                mapping[nli_id] = qid_match.group(1)
                    except Exception as retry_e:
                        print(f"  Retry failed: {retry_e}", flush=True)
                else:
                    print(f"  SPARQL error: {e}", flush=True)
            except Exception as e:
                print(f"  Error in batch {batch_num}: {e}", flush=True)

            if i + batch_size < len(nli_ids):
                await asyncio.sleep(delay)

    return mapping


async def batch_enrich_agents(
    agents_to_enrich: List[Tuple[str, str, str, str]],
    cache_db: Path,
    parallel: int = 5,
    delay: float = 1.5,
) -> Tuple[int, int]:
    """Enrich agents from Wikidata by ID.

    Args:
        agents_to_enrich: List of (agent_norm, authority_uri, nli_id, wikidata_id)
        cache_db: Path to cache database
        parallel: Number of parallel enrichment requests
        delay: Delay between batches

    Returns:
        (successful, failed) counts
    """
    conn = init_cache_db(cache_db)
    successful = 0
    failed = 0
    total = len(agents_to_enrich)

    for i in range(0, total, parallel):
        batch = agents_to_enrich[i:i + parallel]

        # Create enrichment tasks
        tasks = []
        for agent_norm, authority_uri, nli_id, wikidata_id in batch:
            norm_key = normalize_key(EntityType.AGENT, agent_norm)
            tasks.append(enrich_agent_by_id(wikidata_id, norm_key))

        # Execute in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(results):
            agent_norm, authority_uri, nli_id, wikidata_id = batch[j]
            norm_key = normalize_key(EntityType.AGENT, agent_norm)

            if isinstance(result, Exception):
                failed += 1
                continue

            if result and result.wikidata_id:
                result.entity_value = agent_norm
                result.normalized_key = norm_key
                result.nli_id = nli_id
                try:
                    cache_put(conn, result)
                    successful += 1
                except Exception as e:
                    failed += 1
                    if failed <= 5:
                        print(f"  Cache error for {agent_norm}: {e}", flush=True)
            else:
                failed += 1

        # Also store NLI identifier mappings
        for agent_norm, authority_uri, nli_id, wikidata_id in batch:
            try:
                now = datetime.now(timezone.utc).isoformat()
                expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                conn.execute("""
                    INSERT OR IGNORE INTO nli_identifiers
                    (nli_id, nli_uri, wikidata_id, fetch_method, fetched_at, expires_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    nli_id,
                    authority_uri,
                    wikidata_id,
                    "batch_sparql",
                    now,
                    expires,
                    "success",
                ))
            except Exception:
                pass
        conn.commit()

        processed = min(i + parallel, total)
        if processed % 50 == 0 or processed == total or processed <= parallel:
            print(
                f"  Enrichment: {processed}/{total} "
                f"({successful} OK, {failed} failed)",
                flush=True,
            )

        if i + parallel < total:
            await asyncio.sleep(delay)

    conn.close()
    return successful, failed


async def store_no_wikidata_agents(
    agents_without_wikidata: List[Tuple[str, str, str]],
    cache_db: Path,
) -> int:
    """Store NLI identifier entries for agents without Wikidata matches.

    This prevents re-querying them in future runs.

    Args:
        agents_without_wikidata: List of (agent_norm, authority_uri, nli_id)
        cache_db: Path to cache database

    Returns:
        Number stored
    """
    conn = sqlite3.connect(str(cache_db))
    stored = 0
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    for agent_norm, authority_uri, nli_id in agents_without_wikidata:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO nli_identifiers
                (nli_id, nli_uri, wikidata_id, fetch_method, fetched_at, expires_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nli_id,
                authority_uri,
                None,  # No Wikidata ID
                "batch_sparql_no_match",
                now,
                expires,
                "not_found",
            ))
            stored += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    return stored


async def main_async(args):
    """Main async entry point."""
    biblio_db = Path("data/index/bibliographic.db")
    cache_db = Path("data/enrichment/cache.db")

    if not biblio_db.exists():
        print(f"Error: {biblio_db} not found")
        return

    if not cache_db.exists():
        print(f"Error: {cache_db} not found")
        return

    # Step 1: Get all agents with authority URIs
    print("Step 1: Loading agents with authority URIs...", flush=True)
    all_agents = get_all_agents_with_uris(biblio_db)
    print(f"  Found {len(all_agents)} agents with parseable NLI IDs", flush=True)

    # Step 2: Filter out already cached
    print("\nStep 2: Checking cache...", flush=True)
    cached_nli_ids = get_already_cached_nli_ids(cache_db)
    print(f"  Already cached: {len(cached_nli_ids)} NLI IDs", flush=True)

    agents_needed = [
        (norm, uri, nli_id)
        for norm, uri, nli_id in all_agents
        if nli_id not in cached_nli_ids
    ]

    if args.limit:
        agents_needed = agents_needed[:args.limit]

    print(f"  Need to enrich: {len(agents_needed)} agents", flush=True)

    if not agents_needed:
        print("\nAll agents already cached!")
        return

    if args.dry_run:
        print("\nDry run - would enrich these agents:")
        for norm, uri, nli_id in agents_needed[:20]:
            print(f"  - {norm} (NLI: {nli_id})")
        if len(agents_needed) > 20:
            print(f"  ... and {len(agents_needed) - 20} more")
        return

    # Step 3: Batch resolve NLI IDs to Wikidata IDs
    nli_ids = [nli_id for _, _, nli_id in agents_needed]
    print(f"\nStep 3: Batch resolving {len(nli_ids)} NLI IDs to Wikidata IDs...", flush=True)
    start_time = time.time()

    nli_to_wikidata = await batch_resolve_nli_to_wikidata(
        nli_ids, batch_size=50, delay=2.0
    )

    resolve_time = time.time() - start_time
    print(
        f"\n  Resolved {len(nli_to_wikidata)}/{len(nli_ids)} NLI IDs "
        f"to Wikidata in {resolve_time:.1f}s",
        flush=True,
    )

    # Step 4: Enrich agents with Wikidata data
    agents_with_wikidata = [
        (norm, uri, nli_id, nli_to_wikidata[nli_id])
        for norm, uri, nli_id in agents_needed
        if nli_id in nli_to_wikidata
    ]

    agents_without_wikidata = [
        (norm, uri, nli_id)
        for norm, uri, nli_id in agents_needed
        if nli_id not in nli_to_wikidata
    ]

    print(
        f"\nStep 4: Enriching {len(agents_with_wikidata)} agents from Wikidata...",
        flush=True,
    )
    print(
        f"  ({len(agents_without_wikidata)} agents have no Wikidata entry)",
        flush=True,
    )

    if agents_with_wikidata:
        start_time = time.time()
        successful, failed = await batch_enrich_agents(
            agents_with_wikidata,
            cache_db,
            parallel=5,
            delay=1.5,
        )
        enrich_time = time.time() - start_time

        print(f"\n  Enrichment complete in {enrich_time:.1f}s:", flush=True)
        print(f"    Successful: {successful}", flush=True)
        print(f"    Failed:     {failed}", flush=True)
    else:
        successful = 0
        failed = 0

    # Step 5: Store "not found" entries to avoid re-querying
    if agents_without_wikidata:
        print(f"\nStep 5: Caching {len(agents_without_wikidata)} 'not found' entries...", flush=True)
        stored = await store_no_wikidata_agents(agents_without_wikidata, cache_db)
        print(f"  Stored: {stored}", flush=True)

    # Final summary
    print(f"\n{'='*60}", flush=True)
    print("ENRICHMENT SUMMARY", flush=True)
    print(f"  Total agents processed: {len(agents_needed)}", flush=True)
    print(f"  Resolved to Wikidata:   {len(nli_to_wikidata)}", flush=True)
    print(f"  Successfully enriched:  {successful}", flush=True)
    print(f"  No Wikidata entry:      {len(agents_without_wikidata)}", flush=True)
    print(f"  Enrichment failures:    {failed}", flush=True)
    print(f"{'='*60}", flush=True)

    return successful


def main():
    parser = argparse.ArgumentParser(
        description="Fast batch enrich agents with Wikidata data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without doing it",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of agents to process",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
