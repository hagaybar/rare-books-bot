# Wikipedia Enrichment Design: Connection Discovery & Agent Knowledge

**Date**: 2026-03-25
**Status**: Approved design, pending implementation plan

## Problem

The rare books scholar pipeline has 2,665 agents with Wikidata IDs, but:
- Agent descriptions are one-line Wikidata text ("Dutch printer") — too thin for scholarly narration
- Only ~10% of agents have relationship data (teacher/student) from Wikidata
- The connection graph misses relationships described in Wikipedia prose but not encoded in Wikidata's structured properties
- ~1,170 unique agents (38% of ~3,100 unique names) have no Wikidata ID — we don't know if some could be matched

Wikipedia articles contain rich biographical text, intellectual network descriptions, alternate name forms, and editorial links that address all four gaps.

## Design Principle

> Connection discovery first. Enrichment ordered by value, but nobody abandoned.

All 2,665 enriched agents get full Wikipedia data eventually. Work happens in value order (most-connected first for summaries), but there's no permanent cutoff. The architecture is English Wikipedia first, designed so Hebrew Wikipedia is a parameter change away.

## Architecture: Three-Pass Layered Enrichment

```
Pass 1: Links + Categories (batched, ~1 min, free)
  │  MediaWiki API — 50 titles/request, ~54 calls
  │  Output: wikilinks, see_also, categories per agent
  │
  ├──> Connection Discovery Engine
  │      Cross-reference wikilinks against 1,971 unique agent names
  │      Match by wikidata_id (not name) via wikipedia_cache → authority_enrichment
  │      Score: see_also=0.85, body_link=0.75, shared_categories=0.65, bidirectional=0.90
  │      Store in wikipedia_connections table
  │
  └──> Candidate Linkage Report
         Wikilinks that fuzzy-match un-enriched agents (~1,170 unique names)
         Output: reports/candidate_linkages.csv

Pass 2: Summaries (all 2,665, ordered by connectivity, ~45 min, free)
  │  Wikipedia REST API — page/summary endpoint
  │  Output: multi-paragraph extract, name variants, targeted sections
  │  Feed into executor _handle_enrich → richer AgentSummary

Pass 3: LLM Relationship Extraction (top ~500, ~$0.12)
  │  gpt-4.1-nano on Wikipedia text
  │  Context: pre-populated with known linked agents + QIDs from Pass 1
  │  Output: structured relationships with free-text + pre-tagged labels
  │  Matching: by Wikidata QID (identifier-first, name as last resort)
```

Each pass is independently valuable. You can stop after any pass.

## Pass 1: Link-Based Connection Discovery

### Data Fetching

**API**: MediaWiki Action API with batch support

```
GET https://en.wikipedia.org/w/api.php
  ?action=query
  &titles=Joseph_Karo|Moses_Isserles|Maimonides|...  (50 per request)
  &prop=links|categories|extlinks
  &pllimit=500
  &cllimit=50
  &format=json
```

2,665 agents ÷ 50 per request = ~54 API calls. At 1 req/s = ~1 minute.

### Title Resolution

Before fetching, resolve Wikidata QIDs to Wikipedia article titles:

```
GET https://www.wikidata.org/w/api.php
  ?action=wbgetentities
  &ids=Q193460|Q440285|...  (50 per request)
  &props=sitelinks
  &sitefilter=enwiki
```

~54 calls, cached permanently (titles don't change).

### Connection Discovery Algorithm

1. **Build lookup**: `wikidata_id → agent_norm` and `wikipedia_title_lower → wikidata_id` from existing `authority_enrichment`

2. **For each agent's wikilinks**: Normalize link title → look up in title→QID map → match against our agents by QID

3. **Score connections**:

| Source | Confidence | Rationale |
|--------|-----------|-----------|
| "See also" link match | 0.85 | Deliberate editorial connection |
| Article body wikilink | 0.75 | Mentioned in scholarly context |
| Shared Wikipedia categories | 0.65 | Same movement/school/era |
| Bidirectional mention | 0.90 (boost) | Both articles link to each other |

4. **Filter broad categories**: Exclude categories matching patterns like "Articles with...", "All stub articles", "Living people", "CS1 errors", etc. Keep only substantive categories (e.g., "16th-century rabbis in Safed", "Italian printers").

5. **Store** in `wikipedia_connections` table.

### Candidate Linkage Report

During connection discovery, for each wikilink that does NOT match an enriched agent:
- Fuzzy-match the Wikipedia title against all ~3,100 unique agent names (including ~1,170 un-enriched 3,002)
- If fuzzy score > 0.80 → record as candidate linkage
- Output: `reports/candidate_linkages.csv`

Columns: `wikipedia_title, mentioned_in_agent, possible_agent_norm, match_score, wikidata_qid_if_known`

This is a passive report — no automatic matching. Enables future manual or batch enrichment of the 3,002 un-matched agents.

## Pass 2: Wikipedia Summaries

### Data Fetching

**API**: Wikipedia REST API

```
GET https://en.wikipedia.org/api/rest_v1/page/summary/{title}
```

Returns: extract (first 2-3 paragraphs), description, page_id, revision_id, thumbnail.

2,665 calls at 1 req/s = ~45 minutes. **Ordered by connectivity** (most-connected agents from Pass 1 first). If interrupted, the most valuable agents are already cached.

### Name Variant Extraction

Wikipedia opening paragraphs often contain alternate names:
> **Moses ben Maimon** (Hebrew: **משה בן מימון**), commonly known as **Maimonides**, also referred to by the acronym **Rambam** (רמב"ם)

Parse bolded text and parenthetical variants from the extract. Store as `name_variants` JSON array in cache.

### Section Extraction (targeted)

For agents with long articles, optionally fetch structured sections via:
```
GET https://en.wikipedia.org/api/rest_v1/page/mobile-sections/{title}
```

Target sections: "Works", "Legacy", "Influence", "Career", "Publications", "Bibliography". Store in `sections_json`.

### Narrator Integration

In `executor.py` `_handle_enrich()`:
- Look up `wikipedia_cache` for the agent's `wikidata_id`
- If found: use `summary_extract` as `AgentSummary.description` (replaces Wikidata one-liner)
- Set `AgentSummary.wikipedia_context` to extended extract for deeper context
- Fallback: Wikidata description if no Wikipedia data

Narrator prompt addition: "When Wikipedia context is provided for an agent, use it to inform your narrative. Do not quote it verbatim."

## Pass 3: LLM Relationship Extraction

### Input

For each of the top ~500 most-connected agents (configurable via `--limit`):
- Wikipedia summary text (from Pass 2 cache)
- Known linked agents with QIDs (from Pass 1 — pre-resolved, provided as context)

### LLM Prompt

```
Extract all relationships between {agent_name} and other historical figures
mentioned in the following Wikipedia text.

Known agents in our collection that are linked from this article:
- Moses Isserles (Q440285)
- Solomon Alkabetz (Q2305889)
- Jacob Berab (Q1070233)
...

For each relationship, provide:
- target_name: the other person's name as written in the text
- target_wikidata_id: QID if known from the list above, otherwise null
- relationship: free-text description of how they are connected
- tags: applicable labels from [teacher_of, student_of, collaborator,
  commentator, co_publication, patron, rival, translator, publisher_of,
  same_school, family, influenced_by]. Add new tags if none fit.
- confidence: 0.0-1.0 based on how explicitly the text states the relationship

Text:
{wikipedia_summary}
```

**Model**: gpt-4.1-nano (~$0.10/M input, $0.40/M output)
**Cost**: 500 agents × ~1,700 tokens = ~$0.12 total

### Matching

```
LLM returns target_wikidata_id?
  ├─ Yes → match authority_enrichment.wikidata_id (exact)
  ├─ No  → look up target_name in wikipedia_cache.wikipedia_title
  │        └─ Found? → get wikidata_id → match authority_enrichment
  └─ Still no match? → fuzzy name match → candidate linkage report only
```

Identifier-first. Name matching only for the candidate report.

### Output

Stored in `wikipedia_connections` table with `source_type="llm_extraction"`. Both free-text `relationship` and structured `tags` preserved.

## Storage

### `wikipedia_cache` table (in `data/index/bibliographic.db`)

Stored in `bibliographic.db` alongside `authority_enrichment` and `wikipedia_connections` to avoid cross-database queries. The executor takes a single `db_path` — all Wikipedia data is accessible through it.

```sql
CREATE TABLE IF NOT EXISTS wikipedia_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wikidata_id TEXT NOT NULL,
    wikipedia_title TEXT,
    summary_extract TEXT,
    categories TEXT,                 -- JSON array
    see_also_titles TEXT,            -- JSON array
    article_wikilinks TEXT,          -- JSON array
    sections_json TEXT,              -- JSON: {"Works": "...", ...}
    name_variants TEXT,              -- JSON array
    page_id INTEGER,
    revision_id INTEGER,
    language TEXT DEFAULT 'en',
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,        -- fetched_at + 90 days
    UNIQUE(wikidata_id, language)
);
```

### `wikipedia_connections` table (in `data/index/bibliographic.db`)

```sql
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
    evidence TEXT,                   -- Quote or context
    bidirectional INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_agent_norm, target_agent_norm, source_type)
);
```

### `AgentSummary` extension (in `plan_models.py`)

```python
class AgentSummary(BaseModel):
    # ... existing fields ...
    wikipedia_context: str | None = None
```

### No `person_info` extension needed

`wikipedia_cache` is the single source for Wikipedia data. The executor queries it directly when building `AgentSummary`. No redundant copy in `person_info` JSON.

## Integration with Existing Systems

### Cross-Reference Engine

`scripts/chat/cross_reference.py` gains a 4th connection type:

```python
def _find_wikipedia_connections(agent_names, db_path):
    """Query wikipedia_connections table for agents in the current graph."""
```

Returns connections alongside existing teacher_of, co_publication, same_place_period. The confidence scoring is calibrated so Wikipedia connections sit between co_publication (0.85) and same_place_period (0.70).

### Executor

`_handle_enrich()` in `executor.py`:
1. Existing: query `authority_enrichment` → build `AgentSummary`
2. New: query `wikipedia_cache` for `wikidata_id` → enrich `description` and `wikipedia_context`
3. New: query `wikipedia_connections` for agent → include in `ConnectionGraph`

### Narrator

No prompt structure changes. The narrator already handles:
- `AgentSummary.description` (now richer from Wikipedia)
- `ConnectionGraph` connections (now includes Wikipedia-derived ones)
- Evidence rules already distinguish collection data from general knowledge

One addition: "When Wikipedia context is provided for an agent, use it to inform your narrative. Do not quote it verbatim."

## Bidirectional Connection Storage

For each agent pair, store a single canonical row with `source_agent_norm < target_agent_norm` (alphabetically). Set `bidirectional=1` when both agents' articles link to each other. This avoids duplicate connections and matches the sorted-pair deduplication pattern in `cross_reference.py`.

## Error Handling

| Failure | Behavior |
|---------|----------|
| Wikidata QID has no enwiki sitelink | Skip agent, set `wikipedia_title=NULL` in cache |
| Wikipedia returns disambiguation page | Detect via categories containing "disambiguation", skip |
| HTTP 429 (rate limit) | Exponential backoff, max 3 retries |
| Article redirected | Follow redirect, store resolved title |
| API timeout | Skip agent, retry in next batch run |
| LLM extraction returns invalid JSON | Skip agent, log error |

## Pass 1 Bootstrapping

The title→QID lookup map requires `wikipedia_cache` to be populated. Pass 1 runs in two sub-steps:
1. **Title resolution**: Call `wbgetentities` for all 2,665 QIDs → populate `wikipedia_cache.wikipedia_title`. Build `title_lower → wikidata_id` map.
2. **Link fetching**: Call MediaWiki `prop=links|categories` for all resolved titles → populate `article_wikilinks`, `see_also_titles`, `categories`.
3. **Connection matching**: Scan each agent's `article_wikilinks` against the title→QID map.

The `wikipedia_cache` table has an additional index: `CREATE INDEX idx_wiki_title ON wikipedia_cache(wikipedia_title, language)`.

## Connection Refresh

When `wikipedia_cache` entries are refreshed (90-day TTL):
1. Compare `revision_id` — if unchanged, skip
2. If article changed: re-fetch links/categories, delete existing `wikipedia_connections` rows for this agent, re-run connection discovery for this agent only
3. LLM-extracted connections (`source_type='llm_extraction'`) are only refreshed when Pass 3 is explicitly re-run

## Modules

### New

| File | Purpose |
|------|---------|
| `scripts/enrichment/wikipedia_client.py` | Async Wikipedia/MediaWiki API client |
| `scripts/enrichment/wikipedia_connections.py` | Connection discovery: cross-reference wikilinks + LLM extraction |
| `scripts/enrichment/batch_wikipedia_enrichment.py` | Batch population script (all 3 passes) |
| `tests/scripts/enrichment/test_wikipedia_client.py` | Client tests (mocked HTTP) |
| `tests/scripts/enrichment/test_wikipedia_connections.py` | Connection discovery tests |

### Modified

| File | Change |
|------|--------|
| `scripts/chat/cross_reference.py` | Add `_find_wikipedia_connections()` 4th connection type |
| `scripts/chat/executor.py` | `_handle_enrich()` queries wikipedia_cache for richer AgentSummary |
| `scripts/chat/plan_models.py` | Add `wikipedia_context` to AgentSummary |
| `scripts/chat/narrator.py` | Update evidence rule for Wikipedia context |

## Cost & Performance

| Pass | API Calls | Time | Cost |
|------|-----------|------|------|
| 1. Links + categories | ~54 batch | ~1 min | Free |
| 2. Summaries (all 2,665) | 2,665 | ~45 min | Free |
| 3. LLM extraction (500) | 500 | ~2 min | ~$0.12 |
| **Total** | **~3,219** | **~48 min** | **~$0.12** |

Refresh: 90-day TTL. On refresh, compare `revision_id` — skip unchanged articles.

## Expected Impact

| Metric | Before | After |
|--------|--------|-------|
| Agent descriptions | 1-line Wikidata text | 2-3 paragraph Wikipedia extract |
| Connections discovered | ~500 (teacher/student/co-pub/same-place) | ~1,500+ (adding Wikipedia link-based + LLM-extracted) |
| Connection types | 3 fixed types | 3 fixed + open-ended from LLM |
| Un-enriched agent candidates | Unknown | Report identifying matchable agents |
| Hebrew name variant coverage | Manual aliases only | Auto-discovered from Wikipedia |
| Narrator scholarly depth | Limited by Wikidata facts | Rich biographical + network context |
