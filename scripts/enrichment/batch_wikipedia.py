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
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.enrichment.wikipedia_client import (
    fetch_links_batch,
    fetch_summary,
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


def _extract_name_variants(extract: str) -> list[str]:
    """Extract alternate names from Wikipedia first paragraph.

    Looks for parenthetical names containing Hebrew/Arabic text
    or "known as" patterns.

    Args:
        extract: Wikipedia summary extract text.

    Returns:
        List of extracted name variant strings.
    """
    variants: list[str] = []
    # In REST API extract, bold is not preserved, but parenthetical names are
    paren_matches = re.findall(r"\(([^)]+)\)", extract[:500])
    for match in paren_matches:
        # Look for Hebrew/Arabic text
        if re.search(r"[\u0590-\u05FF\u0600-\u06FF]", match):
            variants.append(match.strip())
        # Look for "also known as X" or "commonly known as X"
        elif "known as" in match.lower():
            name = re.sub(
                r"(?:also |commonly )?known as\s+",
                "",
                match,
                flags=re.IGNORECASE,
            )
            variants.append(name.strip())
    return variants


def run_pass_2(db_path: Path, limit: int | None = None) -> dict:
    """Pass 2: Fetch Wikipedia summaries ordered by connectivity.

    Fetches summary extracts for all agents that have a Wikipedia title
    but no summary yet. Orders by connectivity (most wikipedia_connections
    first) so the most important agents are enriched first.

    Args:
        db_path: Path to the bibliographic SQLite database.
        limit: Optional limit on number of agents to process (for testing).

    Returns:
        Dict with stats: {"fetched": int, "failed": int, "skipped": int}
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Order by connectivity: agents with more wikipedia_connections first
    rows = conn.execute(
        """
        SELECT wc.wikidata_id, wc.wikipedia_title
        FROM wikipedia_cache wc
        WHERE wc.wikipedia_title IS NOT NULL
          AND (wc.summary_extract IS NULL OR wc.summary_extract = '')
        ORDER BY (
            SELECT COUNT(*) FROM wikipedia_connections wconn
            WHERE wconn.source_agent_norm IN (
                SELECT a.agent_norm FROM agents a
                JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
                WHERE ae.wikidata_id = wc.wikidata_id
            )
        ) DESC
        """
    ).fetchall()
    if limit:
        rows = rows[:limit]

    total = len(rows)
    print(f"Pass 2: Fetching summaries for {total} agents")

    fetched = 0
    failed = 0
    for i, row in enumerate(rows):
        title = row["wikipedia_title"]
        summary = asyncio.run(fetch_summary(title))
        if summary and summary.extract:
            variants = _extract_name_variants(summary.extract)
            conn.execute(
                """UPDATE wikipedia_cache
                   SET summary_extract = ?, name_variants = ?,
                       page_id = ?, revision_id = ?
                   WHERE wikidata_id = ? AND language = 'en'""",
                (
                    summary.extract,
                    json.dumps(variants, ensure_ascii=False),
                    summary.page_id,
                    summary.revision_id,
                    row["wikidata_id"],
                ),
            )
            fetched += 1
        else:
            failed += 1

        # Commit every 50 agents
        if (i + 1) % 50 == 0:
            conn.commit()
        # Print progress every 100
        if (i + 1) % 100 == 0 or (i + 1) == total:
            print(
                f"  Progress: {i + 1}/{total} "
                f"(fetched={fetched}, failed={failed})"
            )

    conn.commit()
    print(f"  Pass 2 complete. {fetched} summaries fetched, {failed} failed.")
    conn.close()
    return {"fetched": fetched, "failed": failed, "skipped": 0}


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

    if args.pass_num in ("2", "all"):
        stats = run_pass_2(db, args.limit)
        print(f"\nPass 2 stats: {json.dumps(stats)}")
    # Pass 3 added in Task 7
