# Wikipedia Enrichment Summary

**Date**: 2026-03-25
**Branch**: beta-bot-ui
**Rollback tag**: `pre-wikipedia-enrichment`

---

## What Was Done

Three-pass Wikipedia enrichment of the rare books agent collection, adding connection discovery, scholarly context for the narrator, and a foundation for future name variant extraction.

### Pass 1: Link-Based Connection Discovery (Complete)

Fetched wikilinks and categories for all agents with English Wikipedia articles via the MediaWiki API.

| Metric | Value |
|--------|-------|
| Agents with Wikidata IDs | 2,665 |
| Agents with English Wikipedia articles | 1,959 (73.6%) |
| Agents with no English Wikipedia article | 706 |
| Wikilinks cached | ~500K+ link titles across 1,959 articles |
| Categories cached | ~15K+ category entries |

### Pass 2: Wikipedia Summaries (Complete)

Fetched 2-3 paragraph summaries for all 1,959 agents via the Wikipedia REST API. Extracted name variants (Hebrew/Arabic) from opening paragraphs.

| Metric | Value |
|--------|-------|
| Summaries fetched | 1,959 |
| Name variants extracted | 10 (conservative regex; see Future Steps) |
| Average summary length | ~300-800 chars |

### Pass 3: LLM Relationship Extraction (In Progress)

Using gpt-4.1-nano to extract structured relationships from Wikipedia summaries for the top 500 most-connected agents.

| Metric | Value (so far) |
|--------|----------------|
| Agents processed | ~350 of 500 |
| Relationships extracted | 4,220+ |
| Cost | ~$0.08 (estimated final: ~$0.12) |

---

## Data Created

### New Tables in `bibliographic.db`

**`wikipedia_cache`** — Wikipedia data for 1,959 agents
- `wikidata_id`, `wikipedia_title`, `summary_extract`, `categories` (JSON), `article_wikilinks` (JSON), `see_also_titles` (JSON), `name_variants` (JSON), `page_id`, `revision_id`
- TTL: 90 days

**`wikipedia_connections`** — Discovered agent relationships

| Source Type | Count | Avg Confidence | Bidirectional |
|-------------|-------|---------------|---------------|
| `category` (shared Wikipedia categories) | 26,140 | 0.65 | 0 |
| `wikilink` (article cross-references) | 7,011 | 0.80 | 2,248 |
| `llm_extraction` (gpt-4.1-nano) | 4,220+ | 0.62 | 0 |
| **Total** | **37,371+** | | |
| **Unique agent pairs** | **30,687+** | | |

### Reports

- `reports/candidate_linkages.csv` — 2,044 candidate matches between Wikipedia wikilinks and un-enriched agents (~1,170 agents without Wikidata IDs). For future manual curation.

---

## Effects on the Live System

### 1. Narrator Gets Richer Context (Immediate)

The executor's `_handle_enrich()` now queries `wikipedia_cache` for each agent. When a Wikipedia summary exists, it replaces the terse Wikidata one-liner (e.g., "Dutch printer") with a multi-paragraph biographical extract. The narrator uses this to produce significantly richer scholarly responses.

**Before**: "Joseph Karo was a rabbi and author."
**After**: Full paragraph about Karo's role in codifying Jewish law, the Shulchan Aruch, his time in Safed, etc.

### 2. Connection Discovery (Immediate)

`find_connections()` in the cross-reference engine now has a 4th connection type: `wikipedia_mention`. When a user asks about an agent, the system surfaces connections discovered through Wikipedia — intellectual networks, shared categories, and LLM-extracted relationships.

**Before**: ~500 connections (teacher/student, co-publication, same-place-period)
**After**: ~37,000+ connections (adding Wikipedia link-based + category + LLM-extracted)

### 3. Grounding UI Shows More Connections (Immediate)

The `GroundingSources` component in the frontend displays connections from all sources, including Wikipedia-derived ones. Users see a richer network of related agents.

### 4. No Changes to Existing Data

All Wikipedia data lives in new tables (`wikipedia_cache`, `wikipedia_connections`). No existing tables were modified. Rollback is clean: drop the two tables and revert to tag `pre-wikipedia-enrichment`.

---

## New Modules Created

| File | Purpose |
|------|---------|
| `scripts/enrichment/wikipedia_client.py` | Async Wikipedia/MediaWiki API client (httpx, rate-limited, batched) |
| `scripts/enrichment/wikipedia_connections.py` | Connection discovery engine + LLM extraction + candidate linkage report |
| `scripts/enrichment/batch_wikipedia.py` | CLI for all 3 passes with `--pass` and `--limit` flags |
| `scripts/enrichment/wikipedia_schema.sql` | DDL for wikipedia_cache + wikipedia_connections tables |
| `tests/scripts/enrichment/test_wikipedia_client.py` | 15 tests (mocked HTTP) |
| `tests/scripts/enrichment/test_wikipedia_connections.py` | 20 tests (in-memory SQLite) |

## Modified Modules

| File | Change |
|------|--------|
| `scripts/chat/cross_reference.py` | Added `_find_wikipedia_connections()` as 4th connection type |
| `scripts/chat/executor.py` | `_handle_enrich()` queries `wikipedia_cache` for richer AgentSummary |
| `scripts/chat/plan_models.py` | Added `wikipedia_context` field to AgentSummary |
| `scripts/chat/narrator.py` | Evidence rule 7 for Wikipedia context; renders in prompt |

---

## Future Steps (Planned, Not Yet Implemented)

### Step A: Agent Alias Integration (Phase 4 from spec)

**What**: Feed Wikipedia-extracted name variants into the `agent_aliases` table with `alias_type='wikipedia'`.

**Why**: Currently 10 Hebrew name variants were extracted (e.g., רש"י for Rashi, יהואש for Yehoash poet) but sit unused in `wikipedia_cache.name_variants`. Integrating them into `agent_aliases` would improve query resolution for Hebrew-script searches.

**Scope**:
- Improve the `_extract_name_variants()` regex to catch more patterns (bolded names, "also known as", multiple script variants)
- Cross-reference against existing `agent_aliases` to avoid duplicates
- Insert new aliases with `alias_type='wikipedia'`, confidence 0.80
- Re-run on all 1,959 summaries

**Estimated effort**: Small (1 task)

### Step B: Hebrew Wikipedia Pass

**What**: Run Passes 1-3 on Hebrew Wikipedia (`he.wikipedia.org`) for agents that have Hebrew articles.

**Why**: Some agents have Hebrew Wikipedia articles but no English one (706 agents had no English article). Hebrew articles also contain name variants and relationships specific to Jewish scholarship that English articles miss.

**Scope**: The `wikipedia_cache` table already has a `language` column with `UNIQUE(wikidata_id, language)` — designed for this. The Wikipedia client just needs a `language` parameter.

**Estimated effort**: Small (parameter change + batch run)

### Step C: Expand LLM Extraction to All Agents

**What**: Run Pass 3 on all 1,959 agents instead of just 500.

**Why**: Pass 3 extracted ~4,200 relationships from ~500 agents. Running on all 1,959 would likely yield ~15,000+ LLM-extracted relationships with nuanced free-text descriptions and pre-tagged labels.

**Cost**: ~$0.48 for remaining 1,459 agents (gpt-4.1-nano)

**Command**: `poetry run python -m scripts.enrichment.batch_wikipedia --pass 3 --db data/index/bibliographic.db --limit 2000`

### Step D: Periodic Refresh

**What**: Re-run the enrichment pipeline periodically to pick up Wikipedia updates.

**Why**: Wikipedia articles for historical figures change infrequently but do get improved. The 90-day TTL on `wikipedia_cache` enables selective refresh — only re-fetch articles whose `revision_id` has changed.

**Scope**: Add a `--refresh` flag to `batch_wikipedia.py` that checks revision IDs before fetching.

### Step E: Category-Based Analytical Queries

**What**: Use Wikipedia categories (e.g., "16th-century rabbis in Safed", "Italian printers") as a new dimension for analytical queries in the interpreter.

**Why**: Categories provide thematic grouping that MARC subject headings don't always capture. The interpreter could recognize queries like "rabbis from Safed" and use Wikipedia categories to find agents, even if their MARC records don't have a "Safed" subject heading.

**Scope**: Add a new executor step type `resolve_by_category` that queries `wikipedia_cache.categories`.

### Step F: Connection Graph Visualization

**What**: Add a visual network graph to the frontend showing agent connections.

**Why**: With 30,000+ unique agent pairs connected, the data is rich enough for meaningful network visualization. Users could explore intellectual networks interactively — "show me the network around Maimonides" would display a force-directed graph of connected scholars.

**Scope**: Frontend component using a graph library (e.g., vis-network, cytoscape.js). API endpoint to serve subgraph data.

### Step G: Candidate Linkage Curation

**What**: Review the 2,044 candidate linkages in `reports/candidate_linkages.csv` and manually confirm matches.

**Why**: These are un-enriched agents in our MARC data that might match Wikipedia articles referenced by enriched agents. Confirming matches would expand Wikidata coverage from 1,971 to potentially 2,100+ unique agents.

**Scope**: Manual review (or LLM-assisted review) of the CSV. For confirmed matches, add Wikidata IDs to `authority_enrichment` and re-run enrichment.
