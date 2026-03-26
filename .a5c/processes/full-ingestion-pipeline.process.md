# Full Ingestion Pipeline — Process Description

**Process ID**: `full-ingestion-pipeline`
**Purpose**: Rebuild `bibliographic.db` from MARC XML through all enrichment stages.
**Reusable**: Yes — run whenever new MARC XML is exported from the catalog.

---

## When to Use

- Fresh MARC XML export from Alma (with or without `$0` authority URIs)
- After data corruption or accidental DB deletion
- When normalization alias maps have been updated
- When re-ingestion is needed after schema changes

## Inputs

| Parameter | Default | Description |
|-----------|---------|-------------|
| `marcXml` | `data/marc_source/rare_book_bibs.xml` | Path to MARC XML file |
| `dbPath` | `data/index/bibliographic.db` | Output SQLite database |
| `skipEnrichment` | `false` | Skip Wikidata/Wikipedia (fast core-only rebuild) |

## Pipeline Phases

### Phase 1: Backup + Core Rebuild (~2 min)
- Auto-backup existing DB via `scripts/utils/db_backup.py`
- M1: Parse MARC XML → `data/canonical/records.jsonl`
  - Extracts all MARC fields including `$0` authority URIs
- M2: Normalize dates (12 patterns + Hebrew calendar), places (196+ aliases), publishers (2,152 aliases), agents
- M3: Build SQLite index with 8 core tables + FTS5 indexes
- **Output**: `bibliographic.db` with records, agents, imprints, subjects, titles

### Phase 2: Authority Systems (~1 min)
- Seed `agent_authorities` + `agent_aliases` (primary, variant_spelling, cross_script, word_reorder)
- Populate `publisher_authorities` + `publisher_variants` (if research data exists)
- **Output**: 3,000+ authorities, 7,000+ aliases

### Phase 3: Wikidata Enrichment (~10-60 min)
- **If `$0` authority URIs exist**: NLI → Wikidata lookup (high confidence, ~2,600 agents)
- **If no `$0` URIs**: Name-based Wikidata search (lower confidence, ~200-400 agents)
- Populate `authority_enrichment` with: wikidata_id, viaf_id, person_info (birth/death, occupations, teachers, students)
- **Breakpoint**: User confirms before starting (can skip)

### Phase 4: Wikipedia Enrichment (~1-4 hours)
- Pass 1: Fetch wikilinks + categories for all agents with Wikipedia articles (~1 min)
- Pass 2: Fetch article summaries (~45 min for ~2,000 agents)
- Pass 3: LLM relationship extraction via gpt-4.1-nano (~$0.50)
- Connection discovery: cross-reference wikilinks, score by type (see_also=0.85, body=0.75, category=0.65)
- **Output**: `wikipedia_cache` + `wikipedia_connections` (30,000+ connections with authority URIs; ~600 without)

### Phase 5: Network Tables (~1 min)
- Materialize `network_edges` (all 5 connection types unified)
- Materialize `network_agents` (geocoded, with display names and connection counts)
- **Output**: Ready for Network Map Explorer UI

### Phase 6: Final Verification
- Comprehensive report of all table counts, coverage metrics, and DB size

## Expected Output (with `$0` authority URIs)

| Metric | Expected |
|--------|----------|
| Records | ~2,800 |
| Agents | ~3,100 |
| Authority URIs | ~2,600+ |
| Date coverage (>=0.9) | ~90% |
| Place coverage (>=0.9) | ~99% |
| Publisher coverage (>=0.8) | ~98% |
| Wikidata enriched | ~2,600 |
| Wikipedia cache | ~1,900 |
| Wikipedia connections | ~35,000+ |
| Network edges | ~45,000+ |
| DB size | ~50+ MB |

## Running

```bash
# Interactive (with breakpoints)
/babysitter:call full-ingestion-pipeline

# Non-interactive (YOLO mode)
/babysitter:yolo full-ingestion-pipeline

# Fast core-only (skip enrichment)
# Set skipEnrichment: true in inputs
```

## Safety

- Auto-backup before overwriting existing DB
- `seed_test_db.py` refuses production DB path
- All steps idempotent (safe to re-run)
- MARC XML committed to git (never lose source data)
