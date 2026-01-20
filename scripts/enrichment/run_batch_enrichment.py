#!/usr/bin/env python3
"""Batch enrichment script for agents with NLI authority URIs.

Fetches Wikidata enrichment data for all agents that have authority URIs
but aren't yet in the enrichment cache.

Usage:
    python -m scripts.enrichment.run_batch_enrichment [--dry-run] [--limit N]
"""

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.enrichment.enrichment_service import EnrichmentService
from scripts.enrichment.models import EnrichmentRequest, EntityType
from scripts.enrichment.nli_client import extract_nli_id_from_uri


def get_agents_needing_enrichment(
    biblio_db: Path,
    cache_db: Path,
    limit: int | None = None
) -> List[Tuple[str, str]]:
    """Get agents with authority URIs not yet in cache.

    Args:
        biblio_db: Path to bibliographic.db
        cache_db: Path to cache.db
        limit: Optional limit on number of agents

    Returns:
        List of (agent_norm, authority_uri) tuples
    """
    # Get all agents with authority URIs
    biblio_conn = sqlite3.connect(biblio_db)
    cursor = biblio_conn.execute("""
        SELECT DISTINCT agent_norm, authority_uri
        FROM agents
        WHERE authority_uri IS NOT NULL
    """)
    all_agents = cursor.fetchall()
    biblio_conn.close()

    # Get cached NLI IDs
    cache_conn = sqlite3.connect(cache_db)
    cursor = cache_conn.execute("""
        SELECT nli_id FROM enrichment_cache WHERE nli_id IS NOT NULL
    """)
    cached_nli_ids = {row[0] for row in cursor.fetchall()}
    cache_conn.close()

    # Filter to agents not in cache
    agents_needed = []
    for agent_norm, authority_uri in all_agents:
        nli_id = extract_nli_id_from_uri(authority_uri)
        if nli_id and nli_id not in cached_nli_ids:
            agents_needed.append((agent_norm, authority_uri))

    if limit:
        agents_needed = agents_needed[:limit]

    return agents_needed


async def run_batch_enrichment(
    agents: List[Tuple[str, str]],
    cache_db: Path,
    batch_size: int = 10,
    rate_limit_delay: float = 1.0
) -> Tuple[int, int]:
    """Run batch enrichment for agents.

    Args:
        agents: List of (agent_norm, authority_uri) tuples
        cache_db: Path to cache.db
        batch_size: Number of agents per batch
        rate_limit_delay: Delay between batches in seconds

    Returns:
        Tuple of (successful_count, failed_count)
    """
    service = EnrichmentService(cache_db_path=cache_db)

    successful = 0
    failed = 0
    total = len(agents)

    # Process in batches
    for i in range(0, total, batch_size):
        batch = agents[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({i+1}-{min(i+batch_size, total)} of {total})")

        # Create enrichment requests
        requests = [
            EnrichmentRequest(
                entity_type=EntityType.AGENT,
                entity_value=agent_norm,
                nli_authority_uri=authority_uri
            )
            for agent_norm, authority_uri in batch
        ]

        # Run enrichment
        results = await service.enrich_batch(
            requests,
            parallel=3,
            rate_limit_delay=rate_limit_delay
        )

        # Count results
        for j, result in enumerate(results):
            agent_norm = batch[j][0]
            if result:
                successful += 1
                desc = result.description or "No description"
                print(f"  [OK] {agent_norm[:40]}: {desc[:50]}")
            else:
                failed += 1
                print(f"  [--] {agent_norm[:40]}: Not found in Wikidata")

        # Progress summary
        print(f"  Progress: {successful} enriched, {failed} not found")

        # Rate limit between batches
        if i + batch_size < total:
            await asyncio.sleep(rate_limit_delay)

    return successful, failed


def main():
    parser = argparse.ArgumentParser(
        description="Batch enrich agents with Wikidata data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be enriched without actually doing it"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of agents to enrich"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of agents per batch (default: 10)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between batches in seconds (default: 1.0)"
    )
    args = parser.parse_args()

    # Paths
    biblio_db = Path("data/index/bibliographic.db")
    cache_db = Path("data/enrichment/cache.db")

    if not biblio_db.exists():
        print(f"Error: {biblio_db} not found")
        sys.exit(1)

    if not cache_db.exists():
        print(f"Error: {cache_db} not found")
        sys.exit(1)

    # Get agents needing enrichment
    print("Scanning for agents needing enrichment...")
    agents = get_agents_needing_enrichment(biblio_db, cache_db, args.limit)

    print(f"\nFound {len(agents)} agents with authority URIs not yet cached")

    if not agents:
        print("All agents already enriched!")
        return

    if args.dry_run:
        print("\nDry run - would enrich these agents:")
        for agent_norm, uri in agents[:20]:
            print(f"  - {agent_norm}")
        if len(agents) > 20:
            print(f"  ... and {len(agents) - 20} more")
        return

    # Run enrichment
    print(f"\nStarting batch enrichment...")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Rate limit delay: {args.delay}s")
    estimated_time = len(agents) / args.batch_size * (args.delay + 2)
    print(f"  Estimated time: {estimated_time/60:.1f} minutes")

    successful, failed = asyncio.run(
        run_batch_enrichment(
            agents,
            cache_db,
            batch_size=args.batch_size,
            rate_limit_delay=args.delay
        )
    )

    print(f"\n{'='*60}")
    print(f"Enrichment complete!")
    print(f"  Successful: {successful}")
    print(f"  Not found:  {failed}")
    print(f"  Total:      {successful + failed}")


if __name__ == "__main__":
    main()
