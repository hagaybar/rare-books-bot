"""Batch Wikipedia enrichment for agent collection.

Usage:
    # Pass 1: Fetch links + categories (fast, ~1 min)
    poetry run python -m scripts.enrichment.batch_wikipedia \
        --pass 1 --db data/index/bibliographic.db

    # Pass 2: Fetch summaries (slower, ~45 min, ordered by connectivity)
    poetry run python -m scripts.enrichment.batch_wikipedia \
        --pass 2 --db data/index/bibliographic.db

    # Pass 3: LLM extraction (top N agents, ~$0.12 for 500)
    poetry run python -m scripts.enrichment.batch_wikipedia \
        --pass 3 --db data/index/bibliographic.db --limit 500

    # All passes:
    poetry run python -m scripts.enrichment.batch_wikipedia \
        --pass all --db data/index/bibliographic.db --limit 500
"""

import argparse
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.enrichment.wikipedia_client import (
    fetch_links_batch,
    resolve_titles_batch,
)

CACHE_TTL_DAYS = 90


def run_pass_1(db_path: Path, limit: int | None = None) -> dict:
    """Pass 1: Resolve titles, fetch wikilinks + categories for all agents.

    Args:
        db_path: Path to the bibliographic SQLite database.
        limit: Optional limit on number of agents to process (for testing).

    Returns:
        Dict with stats: {"resolved": int, "cached": int}
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get all agents with Wikidata IDs
    rows = conn.execute(
        "SELECT DISTINCT wikidata_id FROM authority_enrichment WHERE wikidata_id IS NOT NULL"
    ).fetchall()
    qids = [r["wikidata_id"] for r in rows]
    if limit:
        qids = qids[:limit]

    print(f"Pass 1: Processing {len(qids)} agents with Wikidata IDs")

    # Step 1: Resolve QIDs -> Wikipedia titles
    print("  Step 1/3: Resolving Wikidata QIDs to Wikipedia titles...")
    qid_to_title = asyncio.run(resolve_titles_batch(qids))
    resolved = {q: t for q, t in qid_to_title.items() if t}
    print(f"  Resolved: {len(resolved)}/{len(qids)} have English Wikipedia articles")

    # Cache title resolutions
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=CACHE_TTL_DAYS)).isoformat()
    for qid, title in resolved.items():
        conn.execute(
            """INSERT OR REPLACE INTO wikipedia_cache
               (wikidata_id, wikipedia_title, language, fetched_at, expires_at)
               VALUES (?, ?, 'en', ?, ?)""",
            (qid, title, now, expires),
        )
    conn.commit()
    print(f"  Cached {len(resolved)} title resolutions")

    # Step 2: Fetch links + categories
    # Fetch one article at a time to avoid pllimit starvation (MediaWiki
    # distributes the pllimit quota across all titles in a single request,
    # so large articles consume the entire allowance for the batch).
    titles = list(resolved.values())
    total = len(titles)
    print(f"  Step 2/3: Fetching links + categories for {total} articles...")

    # Process one article at a time so each gets the full pllimit=500 quota.
    # The MediaWiki API distributes pllimit across all titles in a request,
    # so batching titles causes large articles to starve smaller ones.
    updated = 0
    for i, title in enumerate(titles):
        batch_links = asyncio.run(fetch_links_batch([title]))

        for art_title, links in batch_links.items():
            conn.execute(
                """UPDATE wikipedia_cache
                   SET article_wikilinks = ?, categories = ?, see_also_titles = ?
                   WHERE wikipedia_title = ? AND language = 'en'""",
                (
                    json.dumps(links.article_links, ensure_ascii=False),
                    json.dumps(links.categories, ensure_ascii=False),
                    json.dumps(links.see_also, ensure_ascii=False),
                    art_title,
                ),
            )
            updated += 1

        # Commit periodically and show progress
        if (i + 1) % 20 == 0:
            conn.commit()
        if (i + 1) % 100 == 0 or (i + 1) == total:
            print(f"    Progress: {i + 1}/{total} articles processed ({updated} with data)")

    conn.commit()

    print("  Step 3/3: Pass 1 complete.")
    print(f"    Resolved titles: {len(resolved)}")
    print(f"    Articles with links/categories cached: {updated}")

    conn.close()
    return {"resolved": len(resolved), "cached": updated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Wikipedia enrichment")
    parser.add_argument(
        "--pass",
        dest="pass_num",
        choices=["1", "2", "3", "all"],
        required=True,
        help="Which enrichment pass to run",
    )
    parser.add_argument(
        "--db",
        default="data/index/bibliographic.db",
        help="Path to bibliographic database (default: data/index/bibliographic.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of agents to process (for testing)",
    )
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"Error: Database not found at {db}")
        raise SystemExit(1)

    if args.pass_num in ("1", "all"):
        stats = run_pass_1(db, args.limit)
        print(f"\nPass 1 stats: {json.dumps(stats)}")
    # Pass 2 and 3 added in Tasks 5 and 7
