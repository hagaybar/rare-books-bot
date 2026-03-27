#!/usr/bin/env python3
"""Batch enrichment for agents by name search (no authority URIs needed).

Since agents in the database don't have authority URIs (NLI $0 subfield),
this script enriches them using Wikidata name search as a fallback.

It uses the EnrichmentService which:
1. Checks cache first
2. Falls back to Wikidata API name search
3. Gets full SPARQL data for matched entities
4. Caches results for reuse

Usage:
    python -m scripts.enrichment.run_name_enrichment [--limit N] [--dry-run]
"""

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parents[2]))

from scripts.enrichment.enrichment_service import EnrichmentService
from scripts.enrichment.models import EntityType


def get_agents_for_enrichment(
    biblio_db: Path,
    cache_db: Path,
    limit: int | None = None,
) -> List[Tuple[str, str]]:
    """Get distinct personal agents not yet in cache.

    Args:
        biblio_db: Path to bibliographic.db
        cache_db: Path to cache.db
        limit: Optional limit

    Returns:
        List of (agent_norm, agent_raw) tuples, ordered by frequency
    """
    biblio_conn = sqlite3.connect(str(biblio_db))
    agents = biblio_conn.execute("""
        SELECT agent_norm, agent_raw, COUNT(*) as cnt
        FROM agents
        WHERE agent_type = 'personal'
          AND agent_norm IS NOT NULL
          AND agent_norm != ''
        GROUP BY agent_norm
        ORDER BY cnt DESC
    """).fetchall()
    biblio_conn.close()

    # Filter out agents already in cache
    cache_conn = sqlite3.connect(str(cache_db))
    try:
        cached_keys = set()
        rows = cache_conn.execute(
            "SELECT normalized_key FROM enrichment_cache WHERE entity_type = 'agent'"
        ).fetchall()
        cached_keys = {r[0] for r in rows}
    except Exception:
        cached_keys = set()
    cache_conn.close()

    # Normalize and filter
    result = []
    for agent_norm, agent_raw, cnt in agents:
        # Create same normalized key as EnrichmentService
        key = agent_norm.lower().strip()
        for char in ".,;:!?()[]{}":
            key = key.replace(char, "")
        if key not in cached_keys:
            result.append((agent_norm, agent_raw))

    if limit:
        result = result[:limit]

    return result


def is_latin_script(text: str) -> bool:
    """Check if text is primarily Latin script (better for Wikidata search)."""
    latin_count = sum(1 for c in text if c.isascii() and c.isalpha())
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return False
    return latin_count / total_alpha > 0.5


def format_name_for_search(agent_raw: str) -> str:
    """Convert 'Last, First' MARC format to 'First Last' for search.

    Example: 'Manutius, Aldus,' -> 'Aldus Manutius'
    """
    # Remove trailing punctuation
    name = agent_raw.rstrip(".,;: ")

    if "," in name:
        parts = name.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip().rstrip(".,;: ") if len(parts) > 1 else ""
        if first:
            return f"{first} {last}"
        return last

    return name


async def run_name_enrichment(
    agents: List[Tuple[str, str]],
    cache_db: Path,
    batch_size: int = 5,
    rate_limit_delay: float = 2.0,
) -> Tuple[int, int, int]:
    """Run batch enrichment by name search.

    Args:
        agents: List of (agent_norm, agent_raw) tuples
        cache_db: Path to cache.db
        batch_size: Agents per batch
        rate_limit_delay: Delay between batches

    Returns:
        (successful, not_found, errors) counts
    """
    service = EnrichmentService(cache_db_path=cache_db)

    successful = 0
    not_found = 0
    errors = 0
    total = len(agents)

    for i in range(0, total, batch_size):
        batch = agents[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"\nBatch {batch_num}/{total_batches} ({i+1}-{min(i+batch_size, total)} of {total})")

        for j, (agent_norm, agent_raw) in enumerate(batch):
            search_name = format_name_for_search(agent_raw)

            try:
                result = await service.enrich_entity(
                    entity_type=EntityType.AGENT,
                    entity_value=agent_norm,
                )

                if result and result.wikidata_id:
                    successful += 1
                    desc = result.description or "No description"
                    print(f"  [OK] {agent_raw[:40]:40s} -> {result.label or 'N/A'} ({desc[:40]})")
                else:
                    not_found += 1
                    print(f"  [--] {agent_raw[:40]:40s} -> Not found")

            except Exception as e:
                errors += 1
                print(f"  [!!] {agent_raw[:40]:40s} -> Error: {e}")

            # Rate limit between individual requests
            await asyncio.sleep(rate_limit_delay)

        # Progress summary
        processed = min(i + batch_size, total)
        print(f"  Progress: {processed}/{total} "
              f"(found: {successful}, not found: {not_found}, errors: {errors})")

    service.close()
    return successful, not_found, errors


def main():
    parser = argparse.ArgumentParser(
        description="Enrich agents via Wikidata name search"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be enriched"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of agents"
    )
    parser.add_argument(
        "--batch-size", type=int, default=5,
        help="Agents per batch (default: 5)"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Delay between requests in seconds (default: 2.0)"
    )
    parser.add_argument(
        "--latin-only", action="store_true",
        help="Only enrich Latin-script names (more reliable)"
    )
    args = parser.parse_args()

    biblio_db = Path("data/index/bibliographic.db")
    cache_db = Path("data/enrichment/cache.db")

    if not biblio_db.exists():
        print(f"Error: {biblio_db} not found")
        sys.exit(1)

    if not cache_db.exists():
        print(f"Error: {cache_db} not found")
        sys.exit(1)

    print("Scanning for agents needing enrichment...")
    agents = get_agents_for_enrichment(biblio_db, cache_db, args.limit)

    if args.latin_only:
        original = len(agents)
        agents = [(n, r) for n, r in agents if is_latin_script(r)]
        print(f"Filtered to Latin-script names: {len(agents)} of {original}")

    print(f"Found {len(agents)} agents not yet in cache")

    if not agents:
        print("All agents already enriched!")
        return

    if args.dry_run:
        print("\nDry run - would enrich:")
        for norm, raw in agents[:30]:
            search = format_name_for_search(raw)
            latin = "Latin" if is_latin_script(raw) else "Non-Latin"
            print(f"  - {raw[:50]} -> search: '{search}' [{latin}]")
        if len(agents) > 30:
            print(f"  ... and {len(agents) - 30} more")
        return

    print(f"\nStarting name-based enrichment...")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Delay: {args.delay}s between requests")
    estimated_min = len(agents) * args.delay / 60
    print(f"  Estimated time: {estimated_min:.1f} minutes")

    successful, not_found, errors = asyncio.run(
        run_name_enrichment(
            agents, cache_db,
            batch_size=args.batch_size,
            rate_limit_delay=args.delay,
        )
    )

    print(f"\n{'='*60}")
    print("Name-based enrichment complete!")
    print(f"  Found in Wikidata: {successful}")
    print(f"  Not found:         {not_found}")
    print(f"  Errors:            {errors}")
    print(f"  Total processed:   {successful + not_found + errors}")


if __name__ == "__main__":
    main()
