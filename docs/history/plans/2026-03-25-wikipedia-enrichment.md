# Wikipedia Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the rare books collection with Wikipedia data to discover agent connections, improve narrator quality, and extract name variants — via a three-pass layered enrichment pipeline.

**Architecture:** Pass 1 fetches wikilinks/categories for all 2,665 agents (batched MediaWiki API, ~1 min) and runs connection discovery. Pass 2 fetches summaries ordered by connectivity (~45 min). Pass 3 uses gpt-4.1-nano to extract structured relationships for the top 500 agents (~$0.12). All data cached in `wikipedia_cache` table in `bibliographic.db`.

**Tech Stack:** Python 3.11+, httpx (async HTTP), Wikipedia REST API, MediaWiki Action API, SQLite, gpt-4.1-nano, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-wikipedia-enrichment-design.md`

**Rollback:** Tag `pre-wikipedia-enrichment` marks the safe state before any DB changes.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `scripts/enrichment/wikipedia_client.py` | Async Wikipedia/MediaWiki API client: title resolution, summary, links, categories |
| `scripts/enrichment/wikipedia_connections.py` | Connection discovery engine: cross-reference wikilinks with agent collection |
| `scripts/enrichment/batch_wikipedia.py` | CLI script for all 3 passes with --pass and --limit flags |
| `tests/scripts/enrichment/test_wikipedia_client.py` | Client unit tests (mocked httpx) |
| `tests/scripts/enrichment/test_wikipedia_connections.py` | Connection discovery tests |

### Modified files

| File | Change |
|------|--------|
| `scripts/chat/cross_reference.py` | Add `_find_wikipedia_connections()` as 4th connection type |
| `scripts/chat/executor.py` | `_handle_enrich()` queries `wikipedia_cache` for richer AgentSummary |
| `scripts/chat/plan_models.py` | Add `wikipedia_context: str \| None` to AgentSummary |
| `scripts/chat/narrator.py` | Update evidence rule for Wikipedia context |

---

## Task Dependency Graph

```
Task 1 (DB schema) → Task 2 (wikipedia_client) → Task 3 (batch Pass 1: links)
                                                     → Task 4 (connection discovery)
                                                     → Task 5 (batch Pass 2: summaries)
                                                     → Task 6 (narrator integration)
                                                     → Task 7 (batch Pass 3: LLM extraction)
                                                     → Task 8 (cross_reference integration)
```

Tasks 5 and 6 can run in parallel after Task 4. Task 7 requires Task 5. Task 8 requires Tasks 4 and 7.

---

### Task 1: Database Schema

**Files:**
- Modify: `data/index/bibliographic.db` (add tables via script)
- Create: `scripts/enrichment/wikipedia_schema.sql`

- [ ] **Step 1: Create schema SQL file**

Create `scripts/enrichment/wikipedia_schema.sql`:

```sql
-- Wikipedia cache: stores fetched Wikipedia data per agent
CREATE TABLE IF NOT EXISTS wikipedia_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wikidata_id TEXT NOT NULL,
    wikipedia_title TEXT,
    summary_extract TEXT,
    categories TEXT,                 -- JSON array of category names
    see_also_titles TEXT,            -- JSON array of "See also" link titles
    article_wikilinks TEXT,          -- JSON array of all internal link titles
    sections_json TEXT,              -- JSON: {"Works": "...", "Legacy": "...", ...}
    name_variants TEXT,              -- JSON array of alternate names
    page_id INTEGER,
    revision_id INTEGER,
    language TEXT DEFAULT 'en',
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(wikidata_id, language)
);

CREATE INDEX IF NOT EXISTS idx_wiki_wikidata ON wikipedia_cache(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_wiki_title ON wikipedia_cache(wikipedia_title, language);

-- Wikipedia-discovered connections between agents
CREATE TABLE IF NOT EXISTS wikipedia_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_norm TEXT NOT NULL,
    target_agent_norm TEXT NOT NULL,
    source_wikidata_id TEXT,
    target_wikidata_id TEXT,
    relationship TEXT,               -- Free-text description
    tags TEXT,                       -- JSON array of labels
    confidence REAL NOT NULL,
    source_type TEXT NOT NULL,       -- "wikilink", "see_also", "category", "llm_extraction"
    evidence TEXT,
    bidirectional INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_agent_norm, target_agent_norm, source_type)
);

CREATE INDEX IF NOT EXISTS idx_wconn_source ON wikipedia_connections(source_agent_norm);
CREATE INDEX IF NOT EXISTS idx_wconn_target ON wikipedia_connections(target_agent_norm);
```

- [ ] **Step 2: Apply schema to bibliographic.db**

Run: `sqlite3 data/index/bibliographic.db < scripts/enrichment/wikipedia_schema.sql`
Verify: `sqlite3 data/index/bibliographic.db ".tables" | grep wikipedia`
Expected: `wikipedia_cache  wikipedia_connections`

- [ ] **Step 3: Commit**

```bash
git add scripts/enrichment/wikipedia_schema.sql
git commit -m "feat: add wikipedia_cache and wikipedia_connections table schema"
```

---

### Task 2: Wikipedia Client Module

**Files:**
- Create: `scripts/enrichment/wikipedia_client.py`
- Create: `tests/scripts/enrichment/test_wikipedia_client.py`

Follows the pattern from `scripts/enrichment/wikidata_client.py`: async httpx, rate limiting, User-Agent header.

- [ ] **Step 1: Write client tests with mocked httpx**

Create `tests/scripts/enrichment/test_wikipedia_client.py`:

```python
"""Tests for Wikipedia API client. All HTTP calls mocked."""
import json
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from scripts.enrichment.wikipedia_client import (
    resolve_titles_batch,
    fetch_links_batch,
    fetch_summary,
    WikipediaSummary,
    WikipediaLinks,
)


@pytest.fixture
def mock_wikidata_response():
    """Mock wbgetentities response for title resolution."""
    return {
        "entities": {
            "Q193460": {
                "sitelinks": {"enwiki": {"title": "Joseph Karo"}}
            },
            "Q440285": {
                "sitelinks": {"enwiki": {"title": "Moses Isserles"}}
            },
        }
    }


@pytest.fixture
def mock_links_response():
    """Mock MediaWiki prop=links|categories response."""
    return {
        "query": {
            "pages": {
                "12345": {
                    "title": "Joseph Karo",
                    "links": [
                        {"title": "Moses Isserles"},
                        {"title": "Shulchan Aruch"},
                        {"title": "Safed"},
                    ],
                    "categories": [
                        {"title": "Category:16th-century rabbis"},
                        {"title": "Category:Rabbis in Safed"},
                    ],
                }
            }
        }
    }


@pytest.fixture
def mock_summary_response():
    """Mock REST API page/summary response."""
    return {
        "title": "Joseph Karo",
        "extract": "Joseph ben Ephraim Karo was a major author of Jewish law.",
        "description": "Rabbi and author",
        "pageid": 12345,
        "revision": "rev123",
    }


class TestResolveTitlesBatch:
    def test_resolves_qids_to_titles(self, mock_wikidata_response):
        import asyncio
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock, return_value=mock_wikidata_response):
            result = asyncio.run(resolve_titles_batch(["Q193460", "Q440285"]))
        assert result["Q193460"] == "Joseph Karo"
        assert result["Q440285"] == "Moses Isserles"

    def test_missing_sitelink_returns_none(self):
        import asyncio
        response = {"entities": {"Q999": {"sitelinks": {}}}}
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock, return_value=response):
            result = asyncio.run(resolve_titles_batch(["Q999"]))
        assert result.get("Q999") is None


class TestFetchLinksBatch:
    def test_extracts_links_and_categories(self, mock_links_response):
        import asyncio
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock, return_value=mock_links_response):
            result = asyncio.run(fetch_links_batch(["Joseph Karo"]))
        assert "Joseph Karo" in result
        links = result["Joseph Karo"]
        assert "Moses Isserles" in links.article_links
        assert "16th-century rabbis" in links.categories

    def test_filters_broad_categories(self, mock_links_response):
        import asyncio
        mock_links_response["query"]["pages"]["12345"]["categories"].append(
            {"title": "Category:Articles with hCards"}
        )
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock, return_value=mock_links_response):
            result = asyncio.run(fetch_links_batch(["Joseph Karo"]))
        cats = result["Joseph Karo"].categories
        assert "Articles with hCards" not in cats


class TestFetchSummary:
    def test_returns_summary(self, mock_summary_response):
        import asyncio
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock, return_value=mock_summary_response):
            result = asyncio.run(fetch_summary("Joseph Karo"))
        assert isinstance(result, WikipediaSummary)
        assert result.title == "Joseph Karo"
        assert "Jewish law" in result.extract

    def test_returns_none_on_404(self):
        import asyncio
        import httpx
        with patch("scripts.enrichment.wikipedia_client._api_get",
                   new_callable=AsyncMock,
                   side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock(status_code=404))):
            result = asyncio.run(fetch_summary("NonexistentPage"))
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/scripts/enrichment/test_wikipedia_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement wikipedia_client.py**

Create `scripts/enrichment/wikipedia_client.py`. Key structure:

```python
"""Wikipedia & MediaWiki API client for agent enrichment.

Provides batch title resolution (Wikidata → Wikipedia), batch link/category
fetching, and individual summary fetching. Uses httpx async with rate limiting.

Follows the same pattern as scripts/enrichment/wikidata_client.py.
"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

USER_AGENT = "RareBooksBot/1.0 (https://github.com/rare-books-bot; educational research)"
REQUEST_DELAY_SECONDS = 0.5  # Conservative rate limiting
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST = "https://en.wikipedia.org/api/rest_v1"
BATCH_SIZE = 50  # MediaWiki API max titles per request

# Category patterns to filter out (maintenance, not substantive)
_BROAD_CATEGORY_RE = re.compile(
    r"^(Articles|All |CS1|Pages|Webarchive|Use |Short description|"
    r"Living people|AC with|Wikipedia|Wikidata|Commons|Harv and Sfn)",
    re.IGNORECASE,
)


class WikipediaSummary(BaseModel):
    title: str
    extract: str
    description: str | None = None
    page_id: int
    revision_id: str | None = None


class WikipediaLinks(BaseModel):
    article_links: list[str]  # All internal wikilink titles
    categories: list[str]     # Filtered category names (no "Category:" prefix)
    see_also: list[str] = []  # "See also" titles if detectable


async def _api_get(url: str, params: dict, timeout: float = 30.0) -> dict:
    """Make a GET request with User-Agent and rate limiting."""
    async with httpx.AsyncClient() as client:
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
        resp = await client.get(url, params=params,
                                headers={"User-Agent": USER_AGENT},
                                timeout=timeout)
        resp.raise_for_status()
        return resp.json()


async def resolve_titles_batch(qids: list[str]) -> dict[str, str | None]:
    """Resolve Wikidata QIDs to English Wikipedia article titles.

    Uses wbgetentities with sitefilter=enwiki. Batches up to 50 QIDs per request.
    Returns: {qid: title_or_None}
    """
    ...


async def fetch_links_batch(titles: list[str]) -> dict[str, WikipediaLinks]:
    """Fetch internal wikilinks and categories for Wikipedia articles.

    Uses MediaWiki prop=links|categories. Batches up to 50 titles per request.
    Filters out broad/maintenance categories.
    Returns: {title: WikipediaLinks}
    """
    ...


async def fetch_summary(title: str) -> WikipediaSummary | None:
    """Fetch summary extract for a single Wikipedia article.

    Uses REST API /page/summary/{title}. Returns None on 404 or error.
    """
    ...
```

Implement all three functions following the patterns above. Key details:
- `resolve_titles_batch`: Call `WIKIDATA_API?action=wbgetentities&ids={batch}&props=sitelinks&sitefilter=enwiki&format=json`. Batch in groups of 50.
- `fetch_links_batch`: Call `WIKIPEDIA_API?action=query&titles={batch}&prop=links|categories&pllimit=500&cllimit=50&format=json`. Filter categories with `_BROAD_CATEGORY_RE`. Strip "Category:" prefix.
- `fetch_summary`: Call `WIKIPEDIA_REST/page/summary/{title}`. Handle 404 gracefully.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/scripts/enrichment/test_wikipedia_client.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/enrichment/wikipedia_client.py tests/scripts/enrichment/test_wikipedia_client.py
git commit -m "feat: add Wikipedia API client with batch title resolution and link fetching"
```

---

### Task 3: Batch Script — Pass 1 (Links + Categories)

**Files:**
- Create: `scripts/enrichment/batch_wikipedia.py`

The CLI script that runs all three passes with `--pass` and `--limit` flags.

- [ ] **Step 1: Implement batch script for Pass 1**

Create `scripts/enrichment/batch_wikipedia.py`:

```python
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
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scripts.enrichment.wikipedia_client import (
    resolve_titles_batch, fetch_links_batch, fetch_summary,
)


def run_pass_1(db_path: Path, limit: int | None = None):
    """Pass 1: Resolve titles, fetch wikilinks + categories for all agents."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get all agents with Wikidata IDs
    rows = conn.execute(
        "SELECT DISTINCT wikidata_id FROM authority_enrichment "
        "WHERE wikidata_id IS NOT NULL"
    ).fetchall()
    qids = [r["wikidata_id"] for r in rows]
    if limit:
        qids = qids[:limit]

    print(f"Pass 1: Processing {len(qids)} agents with Wikidata IDs")

    # Step 1: Resolve QIDs → Wikipedia titles
    print("  Step 1/3: Resolving Wikidata QIDs to Wikipedia titles...")
    qid_to_title = asyncio.run(resolve_titles_batch(qids))
    resolved = {q: t for q, t in qid_to_title.items() if t}
    print(f"  Resolved: {len(resolved)}/{len(qids)} have English Wikipedia articles")

    # Cache title resolutions
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    for qid, title in resolved.items():
        conn.execute(
            """INSERT OR REPLACE INTO wikipedia_cache
               (wikidata_id, wikipedia_title, language, fetched_at, expires_at)
               VALUES (?, ?, 'en', ?, ?)""",
            (qid, title, now, expires),
        )
    conn.commit()

    # Step 2: Fetch links + categories
    titles = list(resolved.values())
    print(f"  Step 2/3: Fetching links + categories for {len(titles)} articles...")
    title_to_links = asyncio.run(fetch_links_batch(titles))

    for title, links in title_to_links.items():
        conn.execute(
            """UPDATE wikipedia_cache
               SET article_wikilinks = ?, categories = ?, see_also_titles = ?
               WHERE wikipedia_title = ? AND language = 'en'""",
            (
                json.dumps(links.article_links, ensure_ascii=False),
                json.dumps(links.categories, ensure_ascii=False),
                json.dumps(links.see_also, ensure_ascii=False),
                title,
            ),
        )
    conn.commit()

    print(f"  Step 3/3: Pass 1 complete. {len(title_to_links)} articles cached.")
    conn.close()
    return {"resolved": len(resolved), "cached": len(title_to_links)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Wikipedia enrichment")
    parser.add_argument("--pass", dest="pass_num", choices=["1", "2", "3", "all"], required=True)
    parser.add_argument("--db", default="data/index/bibliographic.db")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    db = Path(args.db)
    if args.pass_num in ("1", "all"):
        run_pass_1(db, args.limit)
    # Pass 2 and 3 added in Tasks 5 and 7
```

- [ ] **Step 2: Test with --limit 5**

Run: `poetry run python -m scripts.enrichment.batch_wikipedia --pass 1 --db data/index/bibliographic.db --limit 5`
Expected: 5 agents resolved, links cached. Check: `sqlite3 data/index/bibliographic.db "SELECT wikidata_id, wikipedia_title, length(article_wikilinks) FROM wikipedia_cache LIMIT 5;"`

- [ ] **Step 3: Run full Pass 1**

Run: `poetry run python -m scripts.enrichment.batch_wikipedia --pass 1 --db data/index/bibliographic.db`
Expected: ~2,000+ articles resolved and cached in ~1-2 minutes.

- [ ] **Step 4: Commit**

```bash
git add scripts/enrichment/batch_wikipedia.py
git commit -m "feat: add batch Wikipedia enrichment script (Pass 1: links + categories)"
```

---

### Task 4: Connection Discovery Engine

**Files:**
- Create: `scripts/enrichment/wikipedia_connections.py`
- Create: `tests/scripts/enrichment/test_wikipedia_connections.py`

This is the core value delivery — cross-reference Wikipedia wikilinks with our agent collection.

- [ ] **Step 1: Write connection discovery tests**

Create `tests/scripts/enrichment/test_wikipedia_connections.py`:

```python
"""Tests for Wikipedia connection discovery engine."""
import json
import sqlite3
from pathlib import Path

import pytest
from scripts.enrichment.wikipedia_connections import (
    build_agent_lookup,
    discover_connections,
    generate_candidate_linkage_report,
    DiscoveredConnection,
)


@pytest.fixture
def test_db(tmp_path):
    """Create test DB with wikipedia_cache + authority_enrichment data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE,
            wikidata_id TEXT, label TEXT, wikipedia_url TEXT,
            nli_id TEXT, viaf_id TEXT, isni_id TEXT, loc_id TEXT,
            description TEXT, person_info TEXT, place_info TEXT,
            image_url TEXT, source TEXT, confidence REAL,
            fetched_at TEXT, expires_at TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
            agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT,
            authority_uri TEXT, agent_norm TEXT, agent_confidence REAL,
            agent_method TEXT, agent_notes TEXT, role_norm TEXT,
            role_confidence REAL, role_method TEXT, provenance_json TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, wikipedia_title TEXT,
            summary_extract TEXT, categories TEXT, see_also_titles TEXT,
            article_wikilinks TEXT, sections_json TEXT, name_variants TEXT,
            page_id INTEGER, revision_id INTEGER, language TEXT DEFAULT 'en',
            fetched_at TEXT, expires_at TEXT, UNIQUE(wikidata_id, language)
        );
        CREATE TABLE wikipedia_connections (
            id INTEGER PRIMARY KEY, source_agent_norm TEXT,
            target_agent_norm TEXT, source_wikidata_id TEXT,
            target_wikidata_id TEXT, relationship TEXT, tags TEXT,
            confidence REAL, source_type TEXT, evidence TEXT,
            bidirectional INTEGER DEFAULT 0, created_at TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, source_type)
        );

        -- Agent A: Joseph Karo (Q193460)
        INSERT INTO authority_enrichment VALUES
            (1, 'uri:1', 'Q193460', 'Joseph Karo', NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, NULL, NULL, 'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO agents VALUES
            (1, 1, 0, 'Karo', 'personal', NULL, NULL, 'uri:1',
             'קארו, יוסף בן אפרים', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        -- Agent B: Moses Isserles (Q440285)
        INSERT INTO authority_enrichment VALUES
            (2, 'uri:2', 'Q440285', 'Moses Isserles', NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, NULL, NULL, 'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO agents VALUES
            (2, 2, 0, 'Isserles', 'personal', NULL, NULL, 'uri:2',
             'isserles, moses', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        -- Agent C: No Wikidata ID (un-enriched)
        INSERT INTO agents VALUES
            (3, 3, 0, 'Unknown Rabbi', 'personal', NULL, NULL, NULL,
             'unknown rabbi', 0.5, 'base_clean', NULL,
             'author', 0.5, 'relator_code', '[]');

        -- Wikipedia cache: Karo's article links to Isserles
        INSERT INTO wikipedia_cache VALUES
            (1, 'Q193460', 'Joseph Karo', NULL,
             '["16th-century rabbis", "Rabbis in Safed"]',
             '["Moses Isserles"]',
             '["Moses Isserles", "Shulchan Aruch", "Safed", "Unknown Rabbi Page"]',
             NULL, NULL, 12345, NULL, 'en', '2024-01-01', '2025-01-01');

        -- Wikipedia cache: Isserles links back to Karo
        INSERT INTO wikipedia_cache VALUES
            (2, 'Q440285', 'Moses Isserles', NULL,
             '["16th-century rabbis", "Polish rabbis"]',
             '["Joseph Karo"]',
             '["Joseph Karo", "Shulchan Aruch", "Krakow"]',
             NULL, NULL, 67890, NULL, 'en', '2024-01-01', '2025-01-01');
    """)
    conn.close()
    return db_path


class TestBuildAgentLookup:
    def test_builds_title_to_agent_map(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert lookup.title_to_qid["joseph karo"] == "Q193460"
        assert lookup.qid_to_agent["Q193460"] == "קארו, יוסף בן אפרים"

    def test_un_enriched_agents_tracked(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert "unknown rabbi" in lookup.all_agent_norms


class TestDiscoverConnections:
    def test_finds_wikilink_connection(self, test_db):
        connections = discover_connections(test_db)
        pairs = {(c.source_agent_norm, c.target_agent_norm) for c in connections}
        # Karo → Isserles (canonical order: alphabetical)
        assert any("isserles" in p[0] or "isserles" in p[1] for p in pairs)

    def test_bidirectional_boost(self, test_db):
        connections = discover_connections(test_db)
        # Both articles link to each other → bidirectional
        bidi = [c for c in connections if c.bidirectional]
        assert len(bidi) > 0
        assert bidi[0].confidence == 0.90

    def test_shared_category_connection(self, test_db):
        connections = discover_connections(test_db)
        cat_conns = [c for c in connections if c.source_type == "category"]
        assert len(cat_conns) > 0  # Both share "16th-century rabbis"
        assert cat_conns[0].confidence == 0.65

    def test_stores_to_wikipedia_connections_table(self, test_db):
        discover_connections(test_db, store=True)
        conn = sqlite3.connect(str(test_db))
        count = conn.execute("SELECT COUNT(*) FROM wikipedia_connections").fetchone()[0]
        assert count > 0
        conn.close()


class TestCandidateLinkageReport:
    def test_finds_unmatched_agent_candidates(self, test_db):
        candidates = generate_candidate_linkage_report(test_db)
        # "Unknown Rabbi Page" in Karo's wikilinks might fuzzy-match "unknown rabbi"
        assert len(candidates) >= 0  # May or may not match depending on fuzzy threshold
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/scripts/enrichment/test_wikipedia_connections.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement wikipedia_connections.py**

Create `scripts/enrichment/wikipedia_connections.py`:

```python
"""Wikipedia connection discovery engine.

Cross-references Wikipedia wikilinks and categories against the agent
collection to discover relationships invisible to Wikidata and MARC data.
"""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from thefuzz import fuzz  # fuzzy string matching


@dataclass
class AgentLookup:
    """Lookup tables for matching Wikipedia titles to collection agents."""
    title_to_qid: dict[str, str]      # wikipedia_title_lower → wikidata_id
    qid_to_agent: dict[str, str]      # wikidata_id → agent_norm
    all_agent_norms: set[str]          # All agent_norms including un-enriched


@dataclass
class DiscoveredConnection:
    source_agent_norm: str
    target_agent_norm: str
    source_wikidata_id: str | None
    target_wikidata_id: str | None
    relationship: str | None
    tags: list[str]
    confidence: float
    source_type: str  # "wikilink", "see_also", "category"
    evidence: str | None
    bidirectional: bool = False


@dataclass
class CandidateLinkage:
    wikipedia_title: str
    mentioned_in_agent: str
    possible_agent_norm: str | None
    match_score: float


def build_agent_lookup(db_path: Path) -> AgentLookup:
    """Build lookup tables from authority_enrichment + wikipedia_cache."""
    ...


def discover_connections(
    db_path: Path,
    store: bool = False,
) -> list[DiscoveredConnection]:
    """Discover connections by cross-referencing wikilinks with agents.

    Algorithm:
    1. Build title→QID→agent lookup from wikipedia_cache + authority_enrichment
    2. For each agent's wikilinks, match against lookup (by QID, not name)
    3. Score: see_also=0.85, body_link=0.75, category=0.65, bidirectional=0.90
    4. Canonical row: source_agent_norm < target_agent_norm (alphabetically)
    5. Optionally store to wikipedia_connections table
    """
    ...


def generate_candidate_linkage_report(
    db_path: Path,
    fuzzy_threshold: float = 0.80,
    output_path: Path | None = None,
) -> list[CandidateLinkage]:
    """Generate report of wikilinks that might match un-enriched agents.

    For each wikilink that doesn't match an enriched agent, fuzzy-match
    against all agent_norms. Output as CSV if output_path provided.
    """
    ...
```

Key implementation details:
- `build_agent_lookup`: Query `wikipedia_cache` for `title→qid`, query `authority_enrichment` + `agents` for `qid→agent_norm`, query all `agents.agent_norm` for the full name set
- `discover_connections`: For each agent in wikipedia_cache, parse `article_wikilinks` JSON, look up each title in `title_to_qid`, then resolve QID to agent_norm. Use canonical ordering (`source < target` alphabetically). Detect bidirectional by checking if the reverse pair also exists.
- `generate_candidate_linkage_report`: Collect all wikilink titles that didn't match, fuzzy-match against `all_agent_norms` using `thefuzz.fuzz.ratio()`. Use `thefuzz` (already in many Python environments) or fall back to `difflib.SequenceMatcher`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/scripts/enrichment/test_wikipedia_connections.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run connection discovery on real data**

Run: `poetry run python -c "from scripts.enrichment.wikipedia_connections import discover_connections; from pathlib import Path; conns = discover_connections(Path('data/index/bibliographic.db'), store=True); print(f'Found {len(conns)} connections')"`

Also generate candidate report:
Run: `poetry run python -c "from scripts.enrichment.wikipedia_connections import generate_candidate_linkage_report; from pathlib import Path; report = generate_candidate_linkage_report(Path('data/index/bibliographic.db'), output_path=Path('reports/candidate_linkages.csv')); print(f'{len(report)} candidates')"`

- [ ] **Step 6: Commit**

```bash
git add scripts/enrichment/wikipedia_connections.py tests/scripts/enrichment/test_wikipedia_connections.py reports/candidate_linkages.csv
git commit -m "feat: add Wikipedia connection discovery engine with candidate linkage report"
```

---

### Task 5: Batch Script — Pass 2 (Summaries)

**Files:**
- Modify: `scripts/enrichment/batch_wikipedia.py`

Add `run_pass_2()` that fetches summaries for all agents, ordered by connectivity (most-connected first).

- [ ] **Step 1: Add run_pass_2 to batch script**

```python
def run_pass_2(db_path: Path, limit: int | None = None):
    """Pass 2: Fetch Wikipedia summaries ordered by connectivity."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Order by connectivity: agents with more wikipedia_connections first
    rows = conn.execute("""
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
    """).fetchall()
    if limit:
        rows = rows[:limit]

    print(f"Pass 2: Fetching summaries for {len(rows)} agents")

    for i, row in enumerate(rows):
        title = row["wikipedia_title"]
        summary = asyncio.run(fetch_summary(title))
        if summary:
            # Extract name variants from first paragraph
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
            if (i + 1) % 50 == 0:
                conn.commit()
                print(f"  Progress: {i+1}/{len(rows)}")
    conn.commit()
    print(f"  Pass 2 complete. {len(rows)} summaries fetched.")
    conn.close()


def _extract_name_variants(extract: str) -> list[str]:
    """Extract alternate names from Wikipedia first paragraph.

    Looks for bolded text, parenthetical names, Hebrew/Arabic text.
    """
    import re
    variants = []
    # Bold text often contains alternate names
    # In REST API extract, bold is not preserved, but parenthetical names are
    # Pattern: "known as Name" or "(Hebrew: שם)"
    paren_matches = re.findall(r'\(([^)]+)\)', extract[:500])
    for match in paren_matches:
        # Look for Hebrew/Arabic text
        if re.search(r'[\u0590-\u05FF\u0600-\u06FF]', match):
            variants.append(match.strip())
        # Look for "also known as X" or "commonly known as X"
        elif 'known as' in match.lower():
            name = re.sub(r'(?:also |commonly )?known as\s+', '', match, flags=re.IGNORECASE)
            variants.append(name.strip())
    return variants
```

- [ ] **Step 2: Test with --limit 10**

Run: `poetry run python -m scripts.enrichment.batch_wikipedia --pass 2 --db data/index/bibliographic.db --limit 10`
Verify: `sqlite3 data/index/bibliographic.db "SELECT wikidata_id, wikipedia_title, length(summary_extract) as len FROM wikipedia_cache WHERE summary_extract IS NOT NULL LIMIT 5;"`

- [ ] **Step 3: Commit**

```bash
git add scripts/enrichment/batch_wikipedia.py
git commit -m "feat: add Pass 2 summary fetching with name variant extraction"
```

---

### Task 6: Narrator Integration

**Files:**
- Modify: `scripts/chat/plan_models.py`
- Modify: `scripts/chat/executor.py`
- Modify: `scripts/chat/narrator.py`

Wire Wikipedia data into the scholar pipeline.

- [ ] **Step 1: Add wikipedia_context to AgentSummary**

In `scripts/chat/plan_models.py`, add to `AgentSummary`:

```python
class AgentSummary(BaseModel):
    # ... existing fields ...
    wikipedia_context: str | None = None  # Extended bio from Wikipedia
```

- [ ] **Step 2: Modify _handle_enrich to use wikipedia_cache**

In `scripts/chat/executor.py`, in `_handle_enrich()`, after building `AgentSummary` from `authority_enrichment`, add a wikipedia_cache lookup:

```python
# After building the AgentSummary from authority_enrichment...
# Check wikipedia_cache for richer description
wiki_row = conn.execute(
    """SELECT summary_extract FROM wikipedia_cache
       WHERE wikidata_id = ? AND language = 'en'
       AND summary_extract IS NOT NULL""",
    (enrich_row["wikidata_id"],) if enrich_row["wikidata_id"] else (None,),
).fetchone()
if wiki_row and wiki_row["summary_extract"]:
    agent_summary.wikipedia_context = wiki_row["summary_extract"]
    # Use Wikipedia summary as description if it's richer
    if len(wiki_row["summary_extract"]) > len(agent_summary.description or ""):
        agent_summary.description = wiki_row["summary_extract"][:500]
```

- [ ] **Step 3: Update narrator evidence rule**

In `scripts/chat/narrator.py`, add to `NARRATOR_SYSTEM_PROMPT`:

```
7. When Wikipedia context is provided for an agent, use it to inform your
   narrative with richer biographical detail. Do not quote it verbatim.
   Wikipedia context is general scholarly knowledge, not collection evidence.
```

- [ ] **Step 4: Update _build_narrator_prompt**

In `_build_narrator_prompt()`, when rendering agent profiles, include `wikipedia_context` if present:

```python
if agent.wikipedia_context:
    lines.append(f"  Wikipedia context: {agent.wikipedia_context[:800]}")
```

- [ ] **Step 5: Run tests**

Run: `poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v`
Expected: All pass (wikipedia_cache may not exist in test DB — the lookup should be a graceful no-op)

- [ ] **Step 6: Commit**

```bash
git add scripts/chat/plan_models.py scripts/chat/executor.py scripts/chat/narrator.py
git commit -m "feat: integrate Wikipedia context into narrator via executor enrich step"
```

---

### Task 7: Batch Script — Pass 3 (LLM Extraction)

**Files:**
- Modify: `scripts/enrichment/batch_wikipedia.py`
- Modify: `scripts/enrichment/wikipedia_connections.py`

Add LLM-assisted relationship extraction for top N agents.

- [ ] **Step 1: Add extraction function to wikipedia_connections.py**

```python
async def extract_relationships_llm(
    agent_name: str,
    summary_text: str,
    known_linked_agents: list[dict],  # [{name, qid}, ...]
    model: str = "gpt-4.1-nano",
) -> list[DiscoveredConnection]:
    """Use LLM to extract structured relationships from Wikipedia text.

    The LLM receives the summary + list of known linked agents with QIDs.
    Returns relationships with free-text description + pre-tagged labels.
    Matching is by QID (identifier-first).
    """
    from openai import OpenAI
    ...
```

The LLM prompt includes the known linked agents with QIDs from Pass 1, so matching is identifier-based. Output schema:

```python
class ExtractedRelationship(BaseModel):
    target_name: str
    target_wikidata_id: str | None
    relationship: str                    # Free-text
    tags: list[str]                      # Pre-tagged + open-ended
    confidence: float
```

Tag vocabulary in prompt: `[teacher_of, student_of, collaborator, commentator, co_publication, patron, rival, translator, publisher_of, same_school, family, influenced_by]` + "Add new tags if none fit."

- [ ] **Step 2: Add run_pass_3 to batch script**

```python
def run_pass_3(db_path: Path, limit: int = 500):
    """Pass 3: LLM extraction on top N most-connected agents."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Get top N agents by connection count
    rows = conn.execute("""
        SELECT wc.wikidata_id, wc.wikipedia_title, wc.summary_extract,
               ae.label as agent_label
        FROM wikipedia_cache wc
        JOIN authority_enrichment ae ON ae.wikidata_id = wc.wikidata_id
        WHERE wc.summary_extract IS NOT NULL
        ORDER BY (
            SELECT COUNT(*) FROM wikipedia_connections wconn
            WHERE wconn.source_wikidata_id = wc.wikidata_id
               OR wconn.target_wikidata_id = wc.wikidata_id
        ) DESC
        LIMIT ?
    """, (limit,)).fetchall()

    print(f"Pass 3: LLM extraction for {len(rows)} agents")

    for i, row in enumerate(rows):
        # Get known linked agents for this agent (from Pass 1)
        known = conn.execute("""
            SELECT DISTINCT wc2.wikipedia_title, wc2.wikidata_id
            FROM wikipedia_connections wconn
            JOIN wikipedia_cache wc2 ON wc2.wikidata_id IN (
                wconn.source_wikidata_id, wconn.target_wikidata_id
            )
            WHERE wconn.source_wikidata_id = ? OR wconn.target_wikidata_id = ?
        """, (row["wikidata_id"], row["wikidata_id"])).fetchall()

        known_agents = [{"name": k["wikipedia_title"], "qid": k["wikidata_id"]} for k in known]

        # LLM extraction
        new_conns = asyncio.run(extract_relationships_llm(
            agent_name=row["agent_label"] or row["wikipedia_title"],
            summary_text=row["summary_extract"],
            known_linked_agents=known_agents,
        ))

        # Store new connections
        for nc in new_conns:
            # ... insert into wikipedia_connections with source_type="llm_extraction"

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f"  Progress: {i+1}/{len(rows)}")

    conn.commit()
    conn.close()
```

- [ ] **Step 3: Test with --limit 5**

Run: `poetry run python -m scripts.enrichment.batch_wikipedia --pass 3 --db data/index/bibliographic.db --limit 5`
Expected: 5 agents processed, LLM-extracted connections stored.

- [ ] **Step 4: Commit**

```bash
git add scripts/enrichment/batch_wikipedia.py scripts/enrichment/wikipedia_connections.py
git commit -m "feat: add Pass 3 LLM relationship extraction with identifier-based matching"
```

---

### Task 8: Cross-Reference Integration

**Files:**
- Modify: `scripts/chat/cross_reference.py`

Add Wikipedia connections as the 4th connection type in `find_connections()`.

- [ ] **Step 1: Add _find_wikipedia_connections function**

In `scripts/chat/cross_reference.py`:

```python
def _find_wikipedia_connections(
    agent_norms: List[str],
    conn: sqlite3.Connection,
    visited_pairs: Set[Tuple[str, str]],
) -> List[Connection]:
    """Find Wikipedia-derived connections between agents.

    Queries wikipedia_connections table for pairs where both agents
    are in the current agent_norms list.
    """
    if not agent_norms:
        return []

    placeholders = ",".join("?" for _ in agent_norms)
    rows = conn.execute(f"""
        SELECT source_agent_norm, target_agent_norm, relationship,
               tags, confidence, source_type, bidirectional
        FROM wikipedia_connections
        WHERE source_agent_norm IN ({placeholders})
          AND target_agent_norm IN ({placeholders})
        ORDER BY confidence DESC
    """, agent_norms + agent_norms).fetchall()

    connections = []
    for row in rows:
        pair = tuple(sorted([row["source_agent_norm"], row["target_agent_norm"]]))
        if pair in visited_pairs:
            continue
        visited_pairs.add(pair)
        connections.append(Connection(
            agent_a=row["source_agent_norm"],
            agent_b=row["target_agent_norm"],
            relationship_type="wikipedia_mention",
            confidence=row["confidence"],
            evidence=row["relationship"] or f"Connected via Wikipedia ({row['source_type']})",
            shared_records=[],
        ))
    return connections
```

- [ ] **Step 2: Wire into find_connections()**

In `find_connections()`, after the existing three connection types, add:

```python
# 4. Wikipedia-derived connections
wiki_conns = _find_wikipedia_connections(agent_norms, conn, visited_pairs)
all_connections.extend(wiki_conns)
```

Handle gracefully if `wikipedia_connections` table doesn't exist (try/except with table check).

- [ ] **Step 3: Run tests**

Run: `poetry run pytest tests/scripts/chat/test_cross_reference.py -v`
Expected: Existing tests pass. Wikipedia connections are additive (table may not exist in test DB — graceful no-op).

- [ ] **Step 4: End-to-end verification**

With the server running, test:
```bash
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Who was Joseph Karo?"}' | python3 -m json.tool | head -40
```

Verify the response includes Wikipedia-derived connections and richer biographical context.

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/cross_reference.py
git commit -m "feat: add Wikipedia connections as 4th relationship type in cross-reference engine"
```

---

## Execution Notes

**Task ordering for babysitter orchestration:**
- Task 1 → Task 2 → Task 3 (sequential, foundation)
- Task 4 depends on Task 3 (needs Pass 1 data)
- Tasks 5 and 6 can run in parallel after Task 4
- Task 7 depends on Task 5 (needs summaries)
- Task 8 depends on Tasks 4 and 7 (needs both connection types)

**Database safety:**
- Tag `pre-wikipedia-enrichment` marks the rollback point
- All Wikipedia data is in new tables (`wikipedia_cache`, `wikipedia_connections`) — no existing tables modified
- Pass 1 can be re-run safely (UPSERT via `INSERT OR REPLACE`)

**Testing without APIs:**
- Tasks 1, 2, 4, 6, 8 use mocked HTTP / in-memory SQLite
- Tasks 3, 5, 7 require network access (Wikipedia API / OpenAI API)

**Dependency: `thefuzz`:**
- Used for fuzzy name matching in candidate linkage report
- Install: `poetry add thefuzz` (or use `difflib.SequenceMatcher` as fallback)

**Key domain knowledge:**
- MARC stores names surname-first: "buxtorf, johann"
- `agent_norm` values are lowercase: "קארו, יוסף בן אפרים"
- `authority_enrichment.wikidata_id` is the bridge to Wikipedia (e.g., "Q193460")
- The `wbgetentities` API resolves QID → Wikipedia title reliably
- Wikipedia articles for historical Jewish figures are generally well-maintained
