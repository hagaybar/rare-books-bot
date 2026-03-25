# Wikipedia Enrichment Plan: Agent Knowledge & Connection Discovery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the rare books scholar pipeline with Wikipedia data to improve narrator quality, discover agent connections, and extract name variants — all cached and provenance-tracked.

**Architecture:** Hybrid batch + on-the-fly Wikipedia enrichment feeding into the existing Interpret → Execute → Narrate pipeline. Wikipedia data is cached in `wikipedia_cache` table (90-day TTL), cross-referenced against 2,665 collection agents, and surfaced through the executor's `_handle_enrich` step.

**Tech Stack:** Python 3.11+, httpx (async HTTP), Wikipedia REST API, MediaWiki Action API, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-scholar-pipeline-design.md`

---

## Current State

| Metric | Value |
|--------|-------|
| Total agents with authority URIs | 5,667 |
| Agents with Wikidata IDs | 2,665 (47%) |
| Agents with Wikipedia URLs | 2,665 (47%) |
| Agents with person_info populated | 2,665 (47%) |
| Agents with teacher/student relationships | 277 / 250 (~10%) |
| Agents with birth/death years | 1,920 (72% of enriched) |

**Problem:** Wikidata provides structured facts (birth/death, occupations, identifiers) but not prose context. The narrator gets one-line descriptions like "Dutch printer" when it could have multi-paragraph scholarly context. Relationship fields are sparsely populated (~10%) because Wikidata coverage for Judaica scholars is limited.

**Opportunity:** Wikipedia articles contain rich biographical text, intellectual network descriptions, alternate name forms (Hebrew, Latin), and editorial "See also" links. Cross-referencing Wikipedia mentions against our 2,665 agents can discover relationships invisible to both Wikidata and MARC data.

---

## Data Sources & APIs

### Wikipedia REST API (official, permitted by ToS)

| Endpoint | Data | Use |
|----------|------|-----|
| `GET /api/rest_v1/page/summary/{title}` | Extract (1-3 paragraphs), description, thumbnail, page_id | Agent bio context for narrator |
| MediaWiki `action=query&prop=categories` | Category names (e.g., "16th-century Italian printers") | Thematic grouping, analytical queries |
| MediaWiki `action=query&prop=links` | All internal wikilinks + "See also" links | Connection discovery |
| MediaWiki `action=query&prop=revisions&rvprop=ids` | Revision ID | Cache freshness check |
| `GET /api/rest_v1/page/mobile-sections/{title}` | Structured sections | "Works", "Legacy", "Influence" extraction |

### Wikidata API (for title resolution)

| Endpoint | Purpose |
|----------|---------|
| `wbgetentities?ids={QID}&props=sitelinks&sitefilter=enwiki` | Resolve Wikidata QID → actual Wikipedia article title |

Rate limit: Wikipedia allows 200 req/s with User-Agent header. We'll use 1 req/s (conservative, matching existing `wikidata_client.py` pattern).

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `scripts/enrichment/wikipedia_client.py` | Async Wikipedia REST API client: summary, categories, links, sections, title resolution |
| `scripts/enrichment/batch_wikipedia_enrichment.py` | Batch script to populate wikipedia_cache for all 2,665 agents |
| `scripts/enrichment/wikipedia_connections.py` | Cross-reference Wikipedia wikilinks with collection agents → discover relationships |
| `scripts/enrichment/wikipedia_alias_discovery.py` | Extract name variants from Wikipedia first paragraphs → propose new agent aliases |
| `tests/scripts/enrichment/test_wikipedia_client.py` | Unit tests (mocked HTTP) |
| `tests/scripts/enrichment/test_wikipedia_connections.py` | Connection discovery tests |
| `tests/scripts/enrichment/test_wikipedia_alias_discovery.py` | Alias extraction tests |

### Modified files

| File | Change |
|------|--------|
| `scripts/chat/executor.py` | `_handle_enrich()` — look up wikipedia_cache, populate richer AgentSummary |
| `scripts/chat/plan_models.py` | Add `wikipedia_context: str \| None` to AgentSummary |
| `scripts/chat/narrator.py` | `_build_narrator_prompt()` — render Wikipedia context; update evidence rules |
| `scripts/chat/cross_reference.py` | Add `_find_wikipedia_mention_connections()` as 4th connection type |

---

## Phase 1: Wikipedia Client & Cache (Foundation)

### Task 1.1: Wikipedia Cache Table

**Files:** Create schema in `scripts/enrichment/wikipedia_schema.sql`

```sql
CREATE TABLE IF NOT EXISTS wikipedia_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wikidata_id TEXT NOT NULL,
    wikipedia_title TEXT,
    summary_extract TEXT,           -- First 2-3 paragraphs (plain text, ~500 words)
    categories TEXT,                -- JSON array of category names
    see_also_titles TEXT,           -- JSON array of "See also" link titles
    article_wikilinks TEXT,         -- JSON array of all internal link titles
    sections_json TEXT,             -- JSON: {"Works": "...", "Legacy": "...", ...}
    name_variants TEXT,             -- JSON array of alternate names found in text
    page_id INTEGER,
    revision_id INTEGER,            -- For cache freshness check
    language TEXT DEFAULT 'en',
    fetched_at TEXT NOT NULL,        -- ISO 8601
    expires_at TEXT NOT NULL,        -- ISO 8601 (fetched_at + 90 days)
    UNIQUE(wikidata_id, language)
);

CREATE INDEX IF NOT EXISTS idx_wiki_wikidata ON wikipedia_cache(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_wiki_title ON wikipedia_cache(wikipedia_title);
```

- [ ] Create schema file
- [ ] Add table creation to enrichment initialization code
- [ ] Test: verify table creates in test DB

### Task 1.2: Wikipedia Client Module

**Files:** Create `scripts/enrichment/wikipedia_client.py`, `tests/scripts/enrichment/test_wikipedia_client.py`

Follow the pattern from `scripts/enrichment/wikidata_client.py` (async HTTP, rate limiting, User-Agent header, structured output models).

```python
# Core functions
async def resolve_wikidata_to_title(wikidata_id: str) -> Optional[str]
    """Resolve Q123456 → 'Joseph Karo' via Wikidata sitelinks API."""

async def fetch_summary(title: str) -> Optional[WikipediaSummary]
    """GET /api/rest_v1/page/summary/{title} → extract + description."""

async def fetch_categories(title: str) -> List[str]
    """MediaWiki action=query&prop=categories → category names."""

async def fetch_links(title: str) -> WikipediaLinks
    """MediaWiki action=query&prop=links → see_also + article wikilinks."""

async def fetch_sections(title: str, targets: List[str]) -> Dict[str, str]
    """GET /api/rest_v1/page/mobile-sections/{title} → targeted section text."""

async def enrich_agent(wikidata_id: str, cache_db_path: Path) -> Optional[WikipediaEnrichment]
    """Full enrichment: resolve title → fetch all data → cache → return."""
```

Models:
```python
class WikipediaSummary(BaseModel):
    title: str
    extract: str              # Plain text, 2-3 paragraphs
    description: str | None   # Short description
    page_id: int
    revision_id: int

class WikipediaLinks(BaseModel):
    see_also: list[str]       # "See also" section titles
    article_links: list[str]  # All internal wikilinks in article body

class WikipediaEnrichment(BaseModel):
    """Complete Wikipedia data for one agent."""
    wikidata_id: str
    title: str
    summary: str
    categories: list[str]
    see_also: list[str]
    article_links: list[str]
    sections: dict[str, str]  # Only targeted sections
    name_variants: list[str]
    page_id: int
    revision_id: int
```

- [ ] Write tests first (mocked HTTP responses)
- [ ] Implement wikipedia_client.py
- [ ] Verify tests pass
- [ ] Manual smoke test: resolve Q467148 (Joseph Karo) → fetch summary
- [ ] Commit

### Task 1.3: Batch Enrichment Script

**Files:** Create `scripts/enrichment/batch_wikipedia_enrichment.py`

```python
"""Batch-populate wikipedia_cache for all agents with Wikidata IDs.

Usage:
    poetry run python -m scripts.enrichment.batch_wikipedia_enrichment \
        --bib-db data/index/bibliographic.db \
        --cache-db data/enrichment/cache.db \
        --limit 10  # for testing
"""
```

Flow:
1. Query `authority_enrichment` for all rows with `wikidata_id IS NOT NULL`
2. For each, check `wikipedia_cache` — skip if fresh (not expired)
3. Call `enrich_agent(wikidata_id, cache_db_path)`
4. Insert/update `wikipedia_cache` row
5. Optionally update `person_info` JSON with `wikipedia_summary` and `wikipedia_categories`
6. Log progress: `{done}/{total}, {skipped} cached, {failed} errors`

Rate limiting: 1 request/second (configurable). For 2,665 agents, ~45 minutes.

- [ ] Implement batch script with --limit flag for testing
- [ ] Test with --limit 10
- [ ] Run full batch (2,665 agents)
- [ ] Verify cache populated: `SELECT COUNT(*) FROM wikipedia_cache;`
- [ ] Commit

### Task 1.4: Extend person_info with Wikipedia Data

**Files:** Modify `scripts/enrichment/populate_authority_enrichment.py`

After Wikidata population, also populate Wikipedia fields in `person_info`:
- `wikipedia_summary`: First paragraph only (~200 words)
- `wikipedia_categories`: List of category strings

`PersonInfo` uses `extra='allow'` — no model changes needed, just write the new keys.

- [ ] Modify populate script to read from wikipedia_cache and merge into person_info
- [ ] Test with sample agents
- [ ] Commit

---

## Phase 2: Connection Discovery via Wikipedia Mentions

### Task 2.1: Wikipedia Connection Discovery Engine

**Files:** Create `scripts/enrichment/wikipedia_connections.py`, `tests/scripts/enrichment/test_wikipedia_connections.py`

Algorithm:
1. **Build title→agent_norm lookup**: For each of the 2,665 agents with Wikipedia data, map their Wikipedia article title (lowercase) → agent_norm. Also include Wikidata IDs as keys.

2. **For each agent's Wikipedia article**: Read `article_wikilinks` and `see_also_titles` from `wikipedia_cache`. Check each link title against the lookup.

3. **Score discovered connections**:

| Source | Confidence | Rationale |
|--------|-----------|-----------|
| See also link match | 0.85 | Deliberate editorial connection |
| Article body wikilink match | 0.75 | Mentioned in scholarly context |
| Shared Wikipedia categories | 0.65 | Same movement/school/era |
| Bidirectional mention | 0.90 (boost) | Both articles link to each other |

4. **Output**: List of `{agent_a, agent_b, relationship_type: "wikipedia_mention", confidence, evidence}` tuples.

```python
def discover_wikipedia_connections(
    cache_db: Path,
    bib_db: Path,
) -> List[DiscoveredConnection]
```

- [ ] Write tests with mock wikipedia_cache data
- [ ] Implement discovery engine
- [ ] Run on real data, report: "Found N new connections between M agent pairs"
- [ ] Commit

### Task 2.2: Integrate into Cross-Reference Engine

**Files:** Modify `scripts/chat/cross_reference.py`

Add `_find_wikipedia_mention_connections()` as 4th connection type alongside:
- `_find_teacher_student_connections()` (confidence 0.90)
- `_find_co_publication_connections()` (confidence 0.85)
- `_find_same_place_period_connections()` (confidence 0.70)
- **NEW:** `_find_wikipedia_mention_connections()` (confidence 0.75-0.90)

The function queries `wikipedia_cache` for agents in the current graph and returns connections where one agent's Wikipedia article links to another.

- [ ] Add function to cross_reference.py
- [ ] Integrate into `find_connections()` flow
- [ ] Test: query "Who was Joseph Karo?" → verify Wikipedia-derived connections appear
- [ ] Commit

---

## Phase 3: Narrator Enhancement

### Task 3.1: Richer AgentSummary from Wikipedia

**Files:** Modify `scripts/chat/executor.py`, `scripts/chat/plan_models.py`

In `plan_models.py`:
```python
class AgentSummary(BaseModel):
    # ... existing fields ...
    wikipedia_context: str | None = None  # Extended bio from Wikipedia for narrator
```

In `executor.py` `_handle_enrich()`:
- After building `AgentSummary` from `authority_enrichment`, check `wikipedia_cache` for the agent's `wikidata_id`
- If found: set `description` to Wikipedia summary (richer than Wikidata one-liner), set `wikipedia_context` to extended extract

- [ ] Add field to AgentSummary
- [ ] Modify _handle_enrich to query wikipedia_cache
- [ ] Test: enrich step produces richer description
- [ ] Commit

### Task 3.2: Narrator Prompt Enhancement

**Files:** Modify `scripts/chat/narrator.py`

In `_build_narrator_prompt()`:
- When `agent.wikipedia_context` is present, add a "Wikipedia Context" section under the agent profile
- Keep it clearly labeled so the narrator knows it's external knowledge (not collection data)

In `NARRATOR_SYSTEM_PROMPT`:
- Add evidence rule: "When Wikipedia context is provided for an agent, you may use it as scholarly background. Cite it as general knowledge, not as collection evidence."

- [ ] Extend prompt builder
- [ ] Update system prompt
- [ ] Test: "Who was Maimonides?" produces richer narrative with Wikipedia context
- [ ] Commit

---

## Phase 4: Name Variant Discovery

### Task 4.1: Extract Name Variants from Wikipedia

**Files:** Create `scripts/enrichment/wikipedia_alias_discovery.py`, tests

Wikipedia opening paragraphs often contain alternate names in bold or parentheses:
> **Moses ben Maimon** (Hebrew: **משה בן מימון**), commonly known as **Maimonides** (/maɪˈmɒnɪdiːz/) and also referred to by the acronym **Rambam** (רמב"ם)

Extract these and propose as new agent aliases:
```python
def extract_name_variants(summary_text: str) -> List[NameVariant]
    """Parse bolded names and parenthetical variants from Wikipedia first paragraph."""

def propose_new_aliases(
    variants: List[NameVariant],
    existing_aliases: List[str],
    agent_authority_id: int,
) -> List[ProposedAlias]
    """Filter to variants not already in agent_aliases table."""
```

- [ ] Implement variant extraction (regex + heuristics for bold text, parentheticals, Hebrew text)
- [ ] Cross-reference with existing `agent_aliases` table
- [ ] Generate report: "Found N new variants for M agents"
- [ ] Add to aliases with `alias_type='wikipedia'`, confidence 0.80
- [ ] Test: verify "Rambam" alias discovered for Maimonides
- [ ] Commit

---

## Storage & Provenance

### Cache Strategy

| Data | Storage | TTL | Refresh |
|------|---------|-----|---------|
| Wikipedia summary + categories + links | `wikipedia_cache` in cache.db | 90 days | Compare revision_id, skip if unchanged |
| Summary excerpt for narrator | `person_info.wikipedia_summary` in bibliographic.db | Updated with batch | Overwritten on refresh |
| Discovered connections | `cross_reference.py` in-memory graph | Per-query | Rebuilt from wikipedia_cache on each query |
| Discovered aliases | `agent_aliases` table | Permanent | alias_type='wikipedia' for provenance |

### Provenance Tracking

- `wikipedia_cache.fetched_at` + `revision_id` — when and which version
- `person_info.wikipedia_summary` — clearly named, narrator knows source
- Connection `evidence` strings include "(source: Wikipedia article on {title})"
- Aliases tagged `alias_type='wikipedia'` with confidence 0.80

---

## On-the-Fly Fallback

When the executor's `_handle_enrich()` encounters an agent without cached Wikipedia data:
1. Check `wikipedia_cache` for `wikidata_id` — if fresh, use cached
2. If expired or missing: trigger `enrich_agent()` async call (single agent, <2s)
3. Cache result for future queries
4. If API fails: gracefully degrade to existing Wikidata-only enrichment

This handles agents added after the last batch run without requiring re-batching.

---

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Agent descriptions | 1-line Wikidata text | 2-3 paragraph Wikipedia extract |
| Agent connections discovered | ~500 (teacher/student/co-pub) | ~1,500+ (adding Wikipedia mentions) |
| Agent alias coverage | 6,418 aliases | ~7,000+ (Wikipedia variant discovery) |
| Narrator scholarly depth | Limited by Wikidata facts | Rich biographical + intellectual context |
| Hebrew query resolution | Depends on manual aliases | Auto-discovered Hebrew variants from Wikipedia |

## Verification

1. `poetry run python -m scripts.enrichment.batch_wikipedia_enrichment --limit 10` → 10 agents enriched
2. `sqlite3 data/enrichment/cache.db "SELECT COUNT(*) FROM wikipedia_cache;"` → populated
3. `poetry run python -m scripts.enrichment.wikipedia_connections` → "Found N connections"
4. Chat query "Who was Joseph Karo?" → narrator uses Wikipedia context
5. Chat query "מה לגבי הרמב״ם?" → Rambam alias discovered, richer response
6. `poetry run pytest tests/scripts/enrichment/ -v` → all pass
