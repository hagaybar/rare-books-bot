# Full Ingestion Pipeline — Process Description

**Process ID**: `full-ingestion-pipeline`
**Purpose**: Rebuild `bibliographic.db` from MARC XML through all enrichment stages, including methodical QA audit and correction.
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

## How to Run

```bash
# Interactive (with breakpoints for QA review and enrichment approval)
/babysitter:call Execute .a5c/processes/full-ingestion-pipeline.js with default inputs

# Non-interactive (auto-approve all fixes and enrichment)
/babysitter:yolo Execute .a5c/processes/full-ingestion-pipeline.js with default inputs

# Fast core-only (skip QA fixes and enrichment)
# Set skipEnrichment: true in inputs
```

---

## Pipeline Phases (7 total)

### Phase 1: Backup + Core Rebuild (~2 min)
- Auto-backup existing DB via `scripts/utils/db_backup.py`
- **M1**: Parse MARC XML → `data/canonical/records.jsonl`
  - Extracts all MARC fields including `$0` authority URIs
- **M2**: Normalize using alias maps:
  - Dates: 12 patterns + Hebrew calendar (Gematria, bracketed Gregorian)
  - Places: 196+ aliases in `place_alias_map.json` (99.3% coverage)
  - Publishers: 2,152 aliases in `publisher_alias_map.json` (98.8% coverage)
  - Agents: name normalization with `$0` URI preservation
- **M3**: Build SQLite index with 8 core tables + FTS5 indexes
- **Output**: `bibliographic.db` with records, agents, imprints, subjects, titles

### Phase 2: Normalization QA Audit & Corrections (~5-15 min)
Methodical review of normalization gaps. For each field (date, place, publisher):

1. **Audit** — Scan DB for low-confidence, unparsed, and unmapped values
2. **Categorize** — Group issues by type:
   - Dates: `hebrew_unparsed`, `complex_range`, `circa_variant`, `embedded_noise`, `no_date`
   - Places: `latin_toponym`, `hebrew_place`, `historical_rename`, `bracket_variant`, `sine_loco_variant`
   - Publishers: `sine_nomine_variant`, `latin_form`, `punctuation_issue`
3. **Propose fixes** — Write to `data/qa/*_fixes_proposed.json`:
   - New patterns for `normalize.py` (recurring patterns)
   - New entries for alias maps (one-off mappings)
   - Direct DB updates (one-off corrections)
4. **[BREAKPOINT]** User reviews proposed fixes
5. **Apply** — Update alias maps, add new patterns, re-run M2+M3
6. **Re-verify** — Confirm coverage improved

**Outputs**: `data/qa/norm_audit.json`, `data/qa/*_fixes_proposed.json`, updated alias maps

### Phase 3: Authority Systems (~1 min)
- Seed `agent_authorities` + `agent_aliases` (primary, variant_spelling, cross_script, word_reorder)
- Populate `publisher_authorities` + `publisher_variants` (if research data exists)

### Phase 4: Wikidata Enrichment (~10-60 min)
- **[BREAKPOINT]** User confirms before starting
- **If `$0` authority URIs exist**: NLI → Wikidata lookup (high confidence, ~2,600 agents)
- **If no `$0` URIs**: Name-based Wikidata search (lower confidence, ~200-400 agents)
- Populate `authority_enrichment`: wikidata_id, viaf_id, person_info
- Re-enrich with relationships: teachers, students, notable_works, hebrew_labels

### Phase 5: Wikipedia Enrichment (~1-4 hours)
- Pass 1: Fetch wikilinks + categories (~1 min)
- Pass 2: Fetch article summaries (~45 min)
- Pass 3: LLM relationship extraction via gpt-4.1-nano (~$0.50)
- Connection discovery: cross-reference wikilinks, score by type

### Phase 6: Network Tables (~1 min)
- Materialize `network_edges` (5 connection types unified)
- Materialize `network_agents` (geocoded, display names, connection counts)

### Phase 7: Final Verification
- Comprehensive report: table counts, coverage metrics, DB size

---

## Expected Output (with `$0` authority URIs)

| Metric | Expected |
|--------|----------|
| Records | ~2,800 |
| Agents | ~3,100 |
| Authority URIs | ~2,600+ |
| Date coverage (>=0.9) | ~96-99% |
| Place coverage (>=0.9) | ~99% |
| Publisher coverage (>=0.8) | ~98% |
| Wikidata enriched | ~2,600 |
| Wikipedia cache | ~1,900 |
| Wikipedia connections | ~35,000+ |
| Network edges | ~45,000+ |

## Safety

- Auto-backup before overwriting existing DB
- `seed_test_db.py` refuses production DB path
- All steps idempotent (safe to re-run)
- MARC XML committed to git
- QA fixes are proposed and reviewed before applying
