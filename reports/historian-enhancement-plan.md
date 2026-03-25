# Implementation Plan: Historian Evaluation Enhancements

## 1. Executive Summary

### Current State

The historian evaluation tested 20 research questions against the bibliographic chatbot system. The results reveal significant gaps:

| Metric | Value |
|--------|-------|
| Overall Score | 7.55 / 25 (30.2%) |
| FAIL (0/25) | 7 queries |
| POOR (1-7/25) | 3 queries |
| FAIR (8-14/25) | 10 queries |
| GOOD (15+/25) | 0 queries |

**Grade Distribution**: No query achieved GOOD. The 7 FAILs are complete retrieval failures where the system returned zero results or silent non-responses.

### Root Causes

| Code | Count | Queries Affected | Impact |
|------|-------|-----------------|--------|
| NAME_FORM_MISMATCH | 6 | Q3, Q6, Q7, Q8, Q12, Q19 | 4 total failures + 2 partial. Word-order mismatch (MARC surname-first vs query given-name-first), cross-script gaps (Hebrew/Latin), publisher synonym mismatch. |
| MISSING_CROSS_REF | 5 | Q2, Q9, Q10, Q13, Q17 | Results found but connections between agents unexplored; no intellectual network context. |
| THIN_NARRATIVE | 5 | Q1, Q4, Q11, Q16, Q18 | Narrative exists but lacks scholarly depth -- no thematic context, printing history, or pedagogical framing. |
| NO_AGGREGATION | 3 | Q11, Q14, Q15 | Analytical questions (distribution, breakdown) treated as retrieval queries; aggregation engine exists but is not routed correctly. |
| NO_COMPARISON | 3 | Q1, Q4, Q5 | Cannot juxtapose two result sets (e.g., Venice vs Amsterdam printing). |
| LARGE_SET_SILENT | 3 | Q14, Q15, Q20 | Narrative agent threshold (_MAX_RESULT_SET=100) silently drops output for large sets. |
| NO_CURATION | 1 | Q20 | No selection/recommendation capability for exhibit curation. |

### Proposed Enhancements

Five enhancements address all root causes. Combined, they project the score from 30.2% to 62.8% and eliminate all FAILs.

| # | Enhancement | Priority | Effort | Root Causes Addressed | Score Impact | Queries Improved |
|---|------------|----------|--------|----------------------|-------------|-----------------|
| E1 | Agent Name Resolution Layer | CRITICAL | 3.5d | NAME_FORM_MISMATCH | +70 pts | Q3, Q6, Q7, Q8, Q12, Q19 |
| E2 | Auto-Aggregation for Analytical Questions | CRITICAL | 3.0d | NO_AGGREGATION, LARGE_SET_SILENT | +33 pts | Q14, Q15, Q20 |
| E3 | Entity Cross-Reference and Set Comparison | HIGH | 4.5d | MISSING_CROSS_REF, NO_COMPARISON | +24 pts | Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17 |
| E4 | Contextual Narrative Depth Layer | HIGH | 4.0d | THIN_NARRATIVE | +21 pts | Q1, Q2, Q4, Q5, Q11, Q16, Q18 |
| E5 | Intelligent Selection and Exhibit Curation | MEDIUM | 3.5d | NO_CURATION | +15 pts | Q4, Q11, Q14, Q15, Q20 |

### Score Projections

| Stage | Avg Score | Pct | FAILs | Cumulative Effort |
|-------|-----------|-----|-------|-------------------|
| Baseline | 7.55 | 30.2% | 7 | 0d |
| After E1 | 11.05 | 44.2% | 3 | 3.5d |
| After E1+E2 | 12.70 | 50.8% | 0 | 6.5d |
| After E1+E2+E3 | ~13.90 | 55.6% | 0 | 11.0d |
| After E1+E2+E3+E4 | ~14.95 | 59.8% | 0 | 15.0d |
| After All (E1-E5) | 15.70 | 62.8% | 0 | 18.5d |

### Highest ROI

E1 + E2 together require 6.5 developer-days and lift the score from 30% to 51%, eliminating all 7 FAILs. This combination delivers the highest return on investment and should be prioritized.

### Total Effort

~18.5 developer-days / ~100 hours across 30 tasks.

---

## 2. Enhancement Plans

---

### 2.1 Enhancement E1: Agent Name Resolution Layer

**Priority**: CRITICAL | **Effort**: 3.5 days | **Dependencies**: None

#### Goal

Create an agent name alias table (`agent_authorities` + `agent_aliases`) that enables order-insensitive, cross-script matching for bibliographic agent queries. This mirrors the existing `publisher_authorities`/`publisher_variants` pattern and leverages the 2,434 authority URIs and 1,937 Wikidata-linked enrichment records already in the database. By seeding aliases from `authority_enrichment` labels and Hebrew labels, queries like "Johann Buxtorf", "Moses Mendelssohn", "Joseph Karo", and "Maimonides" will resolve to all matching `agent_norm` values regardless of name order or script. The query adapter's `AGENT_NORM` handler (`scripts/query/db_adapter.py` lines 293-312) will be extended to JOIN through `agent_aliases`.

#### Report Failures Addressed

| Query | Current Behavior | Root Cause | Expected Fix |
|-------|-----------------|------------|-------------|
| Q6 (Buxtorf) | `AGENT_NORM CONTAINS 'johann buxtorf'` returns 0 results. DB has `'buxtorf, johann'` (surname-first). Word order differs. | `normalize_filter_value()` (db_adapter.py:95-110) removes commas and casefolds, but SQL comparison is positional. | Create `agent_aliases` entry linking `'buxtorf, johann'` to authority. Seed alias `'johann buxtorf'` as word-reordered variant. Query resolves via alias to all records. |
| Q7 (Mendelssohn) | Returns 0 results. DB has `'mendelssohn, moses'` (Latin) and `'מנדלסון, משה'` (Hebrew). Word order + cross-script gap. | Word-order mismatch plus no alias linkage between Latin query and Hebrew `agent_norm`. | Seed aliases: `'mendelssohn, moses'`, `'מנדלסון, משה'`, `'Moses Mendelssohn'`, `'משה מנדלסון'`. Query resolves via any alias. |
| Q8 (Maimonides) | Finds 7 records via `'maimonides, moses'` but misses 15+ under `'משה בן מימון'` (Hebrew patronymic). Both share authority_uri `987007265654005171`. | CONTAINS match on `agent_norm` cannot bridge across scripts. Enrichment has `label='Moshe ben Maimon'` and `hebrew_label='רמב"ם'` but unused. | Seed aliases from all sources. Query 'Maimonides' matches alias, finds all 22+ records. |
| Q19 (Karo) | Returns 0. DB only has Hebrew form `'קארו, יוסף בן אפרים'`. | No Latin `agent_norm` exists. Enrichment has `label='Joseph ben Ephraim Karo'` but unused. | Seed Latin aliases from enrichment. Query resolves to Hebrew records. |
| Q3 (Aldine Press) | Returns 0. Publisher forms are Latin (`'in aedibus aldi'`, `'apud aldum'`). Agent form is `'manuzio, aldo'`. | EQUALS on `'aldine'` fails against Latin forms. | Create agent authority for Aldus Manutius. Handles the agent/printer dimension. |
| Q12 (Ethiopia) | Returns 9 results (partial). Agent name mismatch for Ethiopian scholars. | Some Ethiopian agent names exist only in non-Latin script variants. | Agent alias resolution improves recall for cross-script agent names. |

#### Affected Components

| File | Functions / Changes | Type |
|------|-------------------|------|
| `scripts/metadata/agent_authority.py` | `AgentAuthorityStore`, `AgentAuthority`, `AgentAlias`, `init_schema`, `create`, `search_by_alias`, `resolve_agent_norm_to_authority_ids` | NEW |
| `scripts/metadata/seed_agent_authorities.py` | `seed_from_enrichment`, `generate_word_reorder_aliases`, `generate_cross_script_aliases`, `seed_all` | NEW |
| `scripts/query/db_adapter.py` | `build_where_clause` (AGENT_NORM branch, lines 293-312), `build_join_clauses`, `normalize_filter_value` (lines 95-110) | MODIFY |
| `scripts/marc/m3_contract.py` | `M3Tables`, `M3Columns`, `M3Aliases`, `EXPECTED_SCHEMA` -- add AGENT_AUTHORITIES, AGENT_ALIASES entries | MODIFY |
| `scripts/marc/m3_schema.sql` | `agent_authorities CREATE TABLE`, `agent_aliases CREATE TABLE`, indexes | MODIFY |
| `app/cli.py` | `seed-agent-authorities` command with `--db`, `--dry-run`, `--verbose` flags | MODIFY |
| `tests/scripts/metadata/test_agent_authority.py` | 10+ unit tests for CRUD, alias search, cross-script, word-reorder | NEW |
| `tests/scripts/query/test_db_adapter_agent_alias.py` | 6 integration tests for alias-aware query execution | NEW |
| `tests/scripts/metadata/test_seed_agent_authorities.py` | Tests for seeding, word-reorder generation, deduplication | NEW |

#### Implementation Steps

1. **Define `agent_authorities` and `agent_aliases` schema** -- Create two new tables mirroring the `publisher_authorities`/`publisher_variants` pattern with `IF NOT EXISTS`. Add to `m3_schema.sql`. Do NOT modify existing `agents` table. (`scripts/marc/m3_schema.sql`)
2. **Update M3 contract** -- Add `AGENT_AUTHORITIES` and `AGENT_ALIASES` to `M3Tables`, `M3Columns`, `M3Aliases`, and `EXPECTED_SCHEMA` so schema validation covers them. (`scripts/marc/m3_contract.py`)
3. **Implement AgentAuthorityStore CRUD module** -- Create `scripts/metadata/agent_authority.py` mirroring `publisher_authority.py`. Dataclasses, CRUD, `search_by_alias()`, `resolve_agent_norm_to_authority_ids()`. (~300 lines)
4. **Implement alias seeding script** -- Create `scripts/metadata/seed_agent_authorities.py`. Group agents by `authority_uri`, gather `agent_norm` values as primary aliases, add enrichment labels and Hebrew labels as cross-script aliases, generate word-reorder variants. Idempotent. (~250 lines)
5. **Modify AGENT_NORM query path for alias resolution** -- Change `build_where_clause()` AGENT_NORM handler (lines 293-312). Add EXISTS subquery: alias lookup -> authority -> agents via `authority_uri`. OR with existing direct match for backward compatibility. (~30 lines modified)
6. **Add graceful fallback** -- `_agent_alias_tables_exist(conn)` checks `sqlite_master`. Cache result per process. Fall back to current behavior if tables absent.
7. **Add CLI command** -- `seed-agent-authorities` with `--db`, `--dry-run`, `--verbose`. Init schema, run `seed_all()`, print statistics. (~30 lines)
8. **Write unit tests for AgentAuthorityStore** -- `tests/scripts/metadata/test_agent_authority.py`. In-memory SQLite. Key scenarios: Maimonides, Karo, Buxtorf, Mendelssohn. (~200 lines)
9. **Write integration tests for alias-aware queries** -- `tests/scripts/query/test_db_adapter_agent_alias.py`. Complete mini-database with full pipeline. 6 test cases. (~250 lines)
10. **Write seeding script tests** -- `tests/scripts/metadata/test_seed_agent_authorities.py`. (~150 lines)
11. **Run seeding on production database and validate** -- Execute CLI, verify statistics (~2,400+ authorities, 3,000+ primary aliases, 1,000+ cross-script). Run historian queries Q6, Q7, Q8, Q19 to verify.

#### Schema / Data-Model Changes

**`agent_authorities` table:**

```sql
CREATE TABLE IF NOT EXISTS agent_authorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    canonical_name_lower TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    dates_active TEXT,
    date_start INTEGER,
    date_end INTEGER,
    notes TEXT,
    sources TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    authority_uri TEXT,
    wikidata_id TEXT,
    viaf_id TEXT,
    nli_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_auth_canonical_lower
    ON agent_authorities(canonical_name_lower);
CREATE INDEX IF NOT EXISTS idx_agent_auth_type
    ON agent_authorities(agent_type);
CREATE INDEX IF NOT EXISTS idx_agent_auth_authority_uri
    ON agent_authorities(authority_uri);
CREATE INDEX IF NOT EXISTS idx_agent_auth_wikidata
    ON agent_authorities(wikidata_id);
```

**`agent_aliases` table:**

```sql
CREATE TABLE IF NOT EXISTS agent_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_id INTEGER NOT NULL REFERENCES agent_authorities(id) ON DELETE CASCADE,
    alias_form TEXT NOT NULL,
    alias_form_lower TEXT NOT NULL,
    alias_type TEXT NOT NULL CHECK(alias_type IN (
        'primary', 'variant_spelling', 'cross_script',
        'patronymic', 'acronym', 'word_reorder', 'historical'
    )),
    script TEXT DEFAULT 'latin',
    language TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_alias_authority
    ON agent_aliases(authority_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_alias_form_lower
    ON agent_aliases(alias_form_lower);
CREATE INDEX IF NOT EXISTS idx_agent_alias_type
    ON agent_aliases(alias_type);
CREATE INDEX IF NOT EXISTS idx_agent_alias_script
    ON agent_aliases(script);
```

Seed data sources: Primary aliases from `agents.agent_norm`. Variant aliases from `authority_enrichment.label`. Cross-script aliases from `authority_enrichment.person_info->hebrew_label`. Word-reorder aliases generated by splitting `'Last, First'` -> `'First Last'`.

#### Retrieval / Orchestration Changes

- **Query Compilation**: No changes to `scripts/query/llm_compiler.py`. The alias resolution happens at the SQL execution layer, transparent to query planning.
- **Filter Normalization**: Minimal changes to `normalize_filter_value()` (db_adapter.py:95-110). Existing casefold/strip logic already correct for alias lookup.
- **SQL Generation**: Major change to AGENT_NORM branch of `build_where_clause()` (lines 293-312). New pattern: `(existing direct match) OR EXISTS(SELECT 1 FROM agent_aliases al JOIN agent_authorities aa ON al.authority_id = aa.id WHERE LOWER(REPLACE(al.alias_form_lower, ',', '')) LIKE :param AND aa.authority_uri = a.authority_uri)`.

#### Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Alias collision: two people share same name form (e.g., Buxtorf I/II) | Medium | UNIQUE index on `alias_form_lower`. Father/son get single authority with notes. Precision refinement is a separate enhancement. |
| Performance: EXISTS subquery on large alias table | Low | UNIQUE index ensures O(1) lookup. Expected ~8K-10K rows, trivial for SQLite. Benchmark with EXPLAIN QUERY PLAN. |
| Agents without `authority_uri` (~700) cannot use authority_uri join path | Medium | OR condition preserves existing direct match. Standalone authorities created with `authority_uri=NULL`. Fallback path via `agent_norm` comparison. |
| Hebrew text normalization: `casefold()` behavior | Low | Hebrew chars stable under casefold (no case distinction). Test with actual Hebrew strings from DB. |
| Seeding idempotency | Low | `INSERT OR IGNORE` for aliases (UNIQUE index). Check existence before creating authorities. |
| Schema migration on existing production DB | Low | All DDL uses `IF NOT EXISTS`. Fallback mechanism means queries work before tables exist. |
| Word-reorder for complex names (`'de la Cruz, Juan'`, Hebrew patronymics) | Medium | Only apply to simple `'Last, First'` pattern (one comma, Latin script). Skip complex names. |
| UNIQUE alias constraint prevents same form for two authorities | Medium | Minimum length threshold (>3 chars). Skip single-word common names. First authority to claim wins; log warnings. |

#### TDD Plan

**Test file**: `tests/scripts/metadata/test_agent_authority.py`

**Key unit tests**:
- `test_create_authority_and_retrieve` -- Create with 2 aliases, verify all fields
- `test_search_by_alias_case_insensitive` -- Search 'moshe ben maimon', match Maimonides
- `test_search_by_alias_cross_script` -- Search Hebrew `'רמב"ם'`, match Maimonides
- `test_search_by_alias_word_reorder` -- Search 'johann buxtorf', match authority
- `test_unique_alias_constraint` -- Duplicate alias raises IntegrityError
- `test_delete_cascades_aliases` -- FK cascade verified
- `test_detect_script_hebrew/latin` -- Script detection
- `test_list_all_with_type_filter` -- Filter by agent_type
- `test_add_alias_to_existing_authority` -- Dynamic alias addition

**Key integration tests** (`tests/scripts/query/test_db_adapter_agent_alias.py`):
- `test_query_buxtorf_word_reorder` -- 'Johann Buxtorf' finds records
- `test_query_mendelssohn_cross_script` -- Latin query finds Hebrew records
- `test_query_maimonides_all_forms` -- All forms unified
- `test_query_karo_latin_to_hebrew` -- Latin query finds Hebrew-only records
- `test_query_aldus_manutius` -- Agent alias for printer
- `test_query_fallback_no_alias_tables` -- Graceful degradation

#### Quality Gates

| Gate | Criterion | Command |
|------|----------|---------|
| Schema creation | Tables created with correct columns/indexes | `pytest tests/scripts/metadata/test_agent_authority.py -k test_create -v` |
| CRUD unit tests | 10+ unit tests pass | `pytest tests/scripts/metadata/test_agent_authority.py -v` |
| Seeding counts | 2,400+ authorities, 3,000+ primary, 1,000+ cross-script aliases | `python -m app.cli seed-agent-authorities --dry-run` |
| Alias query integration | 6 tests pass (word-reorder, cross-script, fallback) | `pytest tests/scripts/query/test_db_adapter_agent_alias.py -v` |
| Backward compatibility | Existing db_adapter tests unchanged | `pytest tests/scripts/query/test_db_adapter.py -v` |
| M3 contract | New tables pass schema validation | `validate_schema('data/index/bibliographic.db')` |
| Q6 Buxtorf | >=5 results (was 0) | curl test via `/chat` endpoint |
| Q7 Mendelssohn | >=5 results from Latin+Hebrew (was 0) | curl test via `/chat` endpoint |
| Q8 Maimonides | >=15 results (was 7) | curl test via `/chat` endpoint |
| Q19 Karo | >=3 results (was 0) | curl test via `/chat` endpoint |

#### Deliverables

| File | Description | Est. Lines |
|------|------------|-----------|
| `scripts/metadata/agent_authority.py` | AgentAuthorityStore module with CRUD, alias search, authority resolution | ~300 |
| `scripts/metadata/seed_agent_authorities.py` | Seeding script from agents + authority_enrichment | ~250 |
| `scripts/query/db_adapter.py` (modified) | AGENT_NORM alias resolution + `_agent_alias_tables_exist()` | ~30 added |
| `scripts/marc/m3_contract.py` (modified) | New table constants in M3Tables/M3Columns/M3Aliases | ~40 added |
| `scripts/marc/m3_schema.sql` (modified) | CREATE TABLE statements for agent_authorities/agent_aliases | ~50 added |
| `app/cli.py` (modified) | `seed-agent-authorities` command | ~30 added |
| `tests/scripts/metadata/test_agent_authority.py` | Unit tests for AgentAuthorityStore | ~200 |
| `tests/scripts/query/test_db_adapter_agent_alias.py` | Integration tests for alias-aware queries | ~250 |
| `tests/scripts/metadata/test_seed_agent_authorities.py` | Seeding script tests | ~150 |

#### Acceptance Criteria

1. **Q6 (Buxtorf)**: Query 'Johann Buxtorf' returns all records currently found by 'buxtorf, johann'. Expected: 5+ results.
2. **Q7 (Mendelssohn)**: Query 'Moses Mendelssohn' returns records from both Latin and Hebrew `agent_norm` forms.
3. **Q8 (Maimonides)**: Query 'Maimonides' returns 20+ results from both `'maimonides, moses'` and `'משה בן מימון'` forms (was 7).
4. **Q19 (Joseph Karo)**: Query 'Joseph Karo' returns records previously only findable via Hebrew form. Expected: 3+ results (was 0).
5. **Backward compatibility**: All existing `test_db_adapter.py` tests pass without modification.
6. **Schema is additive**: No existing tables modified. `PRAGMA table_info` on `agents` table identical before/after.
7. **Raw MARC values preserved**: No UPDATE statements on existing tables. `agents.agent_raw` unchanged.
8. **Graceful degradation**: System works correctly if alias tables don't exist or are empty.

---

### 2.2 Enhancement E2: Auto-Aggregation for Analytical Questions

**Priority**: CRITICAL | **Effort**: 3.0 days | **Dependencies**: None

#### Goal

Add analytical query routing so that questions requesting aggregation, distribution analysis, or curation are detected at Phase 1 (query definition) and routed directly to the existing aggregation engine rather than treated as standard retrieval queries. This eliminates three 1/25-scoring failures (Q14 chronological shape, Q15 printing centers, Q20 curated exhibit) by detecting analytical intent before the intent agent is invoked, running the appropriate aggregation/summary pipeline, and formatting results as structured breakdowns (histograms, ranked lists) instead of dumping thousands of raw records. The narrative agent's `_MAX_RESULT_SET=100` ceiling is bypassed entirely because analytical queries produce aggregation tables, not CandidateSets.

#### Report Failures Addressed

| Query | Current Behavior | Root Cause | Expected Fix |
|-------|-----------------|------------|-------------|
| Q14 (Chronological distribution) | Returns all 2,796 records. Intent agent classifies as retrieval. Narrative agent skips (>100). Score: 1/25. | `is_overview_query()` at aggregation.py:688 doesn't match 'chronological', 'distribution'. No ANALYTICAL intent type. | `detect_analytical_query()` intercepts before `interpret_query()`. Runs `execute_aggregation()` with `field='date_decade'` over full collection. Returns decade-by-decade breakdown. |
| Q15 (Hebrew printing centers) | Returns 806 Hebrew records with no geographic aggregation. Narrative agent skips. Score: 1/25. | Same routing gap. 'Printing centers' is analytical needing filter+aggregate. | Detects GEOGRAPHIC_DISTRIBUTION with `implied_filter=[language=heb]`. Filters to Hebrew, aggregates by place, returns ranked center list. |
| Q20 (Curated exhibit) | Returns 120 records with no curation. Narrative agent skips (>100). Score: 1/25. | No CURATION intent in Phase 1. RECOMMENDATION handler returns static stub. | Detects CURATION intent. Applies multi-criteria scoring heuristic. Returns top-N diverse items with rationale. |

#### Affected Components

| File | Functions / Changes | Type |
|------|-------------------|------|
| `scripts/chat/analytical_router.py` | `detect_analytical_query`, `classify_analytical_intent`, `AnalyticalIntent`, `AnalyticalQueryResult` | NEW |
| `scripts/chat/curation_engine.py` | `score_for_curation`, `select_curated_items`, `format_curation_response`, `CurationScorer` | NEW |
| `app/api/main.py` | `handle_query_definition_phase`, `handle_analytical_query`, `websocket_chat` | MODIFY |
| `scripts/chat/aggregation.py` | `execute_aggregation_full_collection`, `get_all_record_ids` | MODIFY |
| `scripts/chat/exploration_agent.py` | `ExplorationRequestLLM`, `EXPLORATION_AGENT_SYSTEM_PROMPT` | MODIFY |
| `scripts/chat/models.py` | `ConversationPhase` -- add CURATION to ExplorationIntent enum | MODIFY |
| `scripts/chat/narrative_agent.py` | `generate_agent_narrative`, `generate_analytical_narrative` | MODIFY |
| `tests/scripts/chat/test_analytical_router.py` | 25 unit tests for analytical detection | NEW |
| `tests/scripts/chat/test_curation_engine.py` | 8-10 unit tests for curation scoring | NEW |
| `tests/app/test_api_analytical.py` | 8 integration tests for E2E routing | NEW |

#### Implementation Steps

1. **Define AnalyticalIntent enum and AnalyticalQueryResult model** -- `scripts/chat/analytical_router.py`. Enum: TEMPORAL/GEOGRAPHIC/PUBLISHER/LANGUAGE/SUBJECT/GENERAL/CURATION/NOT_ANALYTICAL. Pydantic model with `is_analytical`, `intent`, `aggregation_field`, `implied_filters`, `confidence`.
2. **Implement `detect_analytical_query()`** -- Two-layer approach: (1) signal detection with multi-word phrases by category, (2) anti-signals for retrieval patterns. Implied filters extracted from query text using lightweight pattern matcher.
3. **Add `execute_aggregation_full_collection()` to aggregation.py** -- New SQL templates without `WHERE record_id IN (...)` clause. Also `get_all_record_ids()` utility for filtered-then-aggregate flows.
4. **Implement `handle_analytical_query()` in main.py** -- Routes analytical results: implied filters -> compile -> execute -> aggregate subset; or no filters -> full collection aggregate. Creates ChatResponse with `phase=CORPUS_EXPLORATION`, `visualization_hint`, structured data.
5. **Wire `detect_analytical_query()` into `handle_query_definition_phase()`** -- Insert after `is_overview_query()` check but BEFORE `interpret_query()`. Deterministic (no LLM call), saves latency.
6. **Wire into WebSocket handler** -- Add analytical detection to `websocket_chat()` with 'Analyzing collection...' progress message.
7. **Implement curation engine** -- `scripts/chat/curation_engine.py`. Deterministic heuristic: temporal_score (0.3), enrichment_score (0.3), diversity_bonus (0.2), subject_richness (0.2). Returns top-N with rationale strings.
8. **Add analytical summary path to narrative_agent.py** -- New `generate_analytical_narrative()` for statistical summaries of large sets. Optional `analytical_mode` parameter.
9. **Extend ExplorationIntent for follow-ups** -- Add CURATION to enum. Update exploration agent prompt with curation examples.
10. **End-to-end testing with Q14, Q15, Q20** -- `tests/app/test_api_analytical.py`. Simulate exact failing queries, verify aggregation data, visualization_hint, session transitions.

#### Schema / Data-Model Changes

```python
# scripts/chat/models.py (line ~48)
class ExplorationIntent(str, Enum):
    ...
    CURATION = 'curation'  # NEW
```

No database schema changes. No API response schema changes -- `ChatResponse.metadata` dict already supports arbitrary keys.

#### Retrieval / Orchestration Changes

- **Query Compilation**: No changes to LLM compiler or intent agent. Analytical queries intercepted BEFORE the intent agent.
- **Filter Normalization**: Implied filter extraction reuses existing normalization logic (language name -> ISO 639-2, place -> lowercase, century -> year range).
- **SQL Generation**: `execute_aggregation_full_collection()` introduces new SQL templates omitting the `WHERE record_id IN (...)` clause. GROUP BY, ORDER BY, LIMIT identical to existing.

#### Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|-----------|
| False positive: retrieval query misclassified as analytical | Medium | Multi-word signals (not single words). Anti-signals: 'books about', 'find', 'search for'. Confidence threshold for weak matches. 20+ borderline test cases. |
| False negative: novel analytical phrasing not covered | Low | Start conservative with known failing queries. Monitor missed detections. Expand keyword lists iteratively. |
| Full-collection aggregation performance | Low | GROUP BY on indexed columns. 3K records in <100ms. Add timing logs. |
| Curation scoring may not align with scholarly judgment | Medium | Heuristic is documented and transparent. Rationale strings explain each selection. Weights configurable. Caveat in response. |
| Implied filter extraction misparses terms | Low | Best-effort extraction. Missing filter produces broader aggregation, not error. Log unrecognized terms. |
| WebSocket/HTTP routing divergence | Low | Extract into shared `handle_analytical_query()` called by both paths. Test both with same inputs. |

#### TDD Plan

**Test file**: `tests/scripts/chat/test_analytical_router.py` (25 unit tests)

Key tests:
- `test_detect_q14_chronological_distribution` -- Returns TEMPORAL_DISTRIBUTION, field='date_decade'
- `test_detect_q15_printing_centers` -- Returns GEOGRAPHIC_DISTRIBUTION, field='place', implied language filter
- `test_detect_q20_curated_exhibit` -- Returns CURATION
- `test_not_analytical_specific_search` -- 'books printed in Paris' returns NOT_ANALYTICAL
- `test_not_analytical_comparison` -- 'compare Venice and Amsterdam' returns NOT_ANALYTICAL
- `test_implied_filter_hebrew` -- Extracts language=heb from 'Hebrew'
- `test_borderline_about_chronological_history` -- 'books about chronological development' returns NOT_ANALYTICAL (anti-signal)
- `test_case_insensitive` -- 'CHRONOLOGICAL DISTRIBUTION' still detected

**Integration tests** (`tests/app/test_api_analytical.py`, 8 tests): E2E for Q14/Q15/Q20, WebSocket routing, follow-ups.

#### Quality Gates

| Gate | Criterion | Command |
|------|----------|---------|
| Router unit tests | 25 tests pass | `pytest tests/scripts/chat/test_analytical_router.py -v` |
| Curation engine tests | All pass | `pytest tests/scripts/chat/test_curation_engine.py -v` |
| API integration | 8 tests pass | `pytest tests/app/test_api_analytical.py -v` |
| No LLM dependency | Works without OPENAI_API_KEY | `unset OPENAI_API_KEY && pytest tests/scripts/chat/test_analytical_router.py -v` |
| Q14 aggregation | Decade breakdown, not raw records | Response `metadata.data.field == 'date_decade'` |
| Q15 place breakdown | Place-by-count for Hebrew books | Response `metadata.data.field == 'place'` |
| Q20 curation | Curated items, not 120 raw | Response contains curation language |
| No regression | Full suite passes | `pytest tests/ -v --timeout=60` |
| Linting | No new errors | `ruff check scripts/chat/analytical_router.py scripts/chat/curation_engine.py` |

#### Deliverables

| File | Description | Est. Lines |
|------|------------|-----------|
| `scripts/chat/analytical_router.py` | AnalyticalIntent enum, detect function, implied filter extraction | ~150-200 |
| `scripts/chat/curation_engine.py` | CurationScorer, scoring heuristic, diverse selection, formatting | ~200-250 |
| `app/api/main.py` (modified) | `handle_analytical_query()`, wiring into Phase 1 and WebSocket | ~95 added |
| `scripts/chat/aggregation.py` (modified) | Full-collection aggregation queries, `get_all_record_ids()` | ~105 added |
| `scripts/chat/models.py` (modified) | CURATION added to ExplorationIntent | ~1 added |
| `scripts/chat/narrative_agent.py` (modified) | `generate_analytical_narrative()`, `analytical_mode` parameter | ~40 added |
| `tests/scripts/chat/test_analytical_router.py` | 25 unit tests | NEW |
| `tests/scripts/chat/test_curation_engine.py` | 8-10 unit tests | NEW |
| `tests/app/test_api_analytical.py` | 8 integration tests | NEW |

#### Acceptance Criteria

1. **Q14**: 'chronological distribution of the collection' returns decade-by-decade breakdown with counts, NOT 2,796 raw records. `metadata.data.field == 'date_decade'`.
2. **Q15**: 'major Hebrew printing centers represented' returns place-by-count ranking filtered to Hebrew-language records.
3. **Q20**: 'curated selection for Hebrew printing exhibit' returns 10-15 selected items with per-item rationale, not 120 raw records.
4. **Deterministic**: Analytical detection works without OPENAI_API_KEY. No LLM calls in `detect_analytical_query()`.
5. **No interference**: Standard retrieval queries unaffected. 'books printed in Paris' still routes to retrieval.
6. **Follow-ups work**: After analytical response, 'show me the publisher breakdown' produces publisher aggregation.
7. **Both endpoints**: HTTP `/chat` and WebSocket `/ws/chat` both support analytical routing.
8. **Narrative threshold bypassed**: Q14/Q15 responses include analytical narrative summary instead of silence.

---

### 2.3 Enhancement E3: Entity Cross-Reference and Set Comparison

**Priority**: HIGH | **Effort**: 4.5 days | **Dependencies**: E1

#### Goal

Build an Entity Cross-Reference and Set Comparison Engine that discovers and surfaces relationships between agents (authors, printers, translators) across query result sets, and enriches comparison operations with multi-faceted side-by-side analysis. Addresses 8 queries (Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17) currently scoring 108/200 (54%) where 160/200 (80%) is achievable.

#### Report Failures Addressed

| Query | Current Score | Gap | How E3 Fixes |
|-------|-------------|-----|-------------|
| Q1 (Bragadin Venice) | 12/25 | No comparison with rival Venetian printers. Flat list, no network context. | Cross-reference discovers co-publication links. Enhanced comparison: Bragadin vs rival printers side-by-side. Follow-up: 'Compare with di Gara'. |
| Q2 (Amsterdam Hebrew 1620-1650) | 15/25 | Found Menasseh ben Israel but no network connections. | Graph reveals teacher-student network, co-publication partners, contemporaries. Narrative appends Connections section. |
| Q4 (Incunabula) | 14/25 | Good results but no cross-center comparison. | Side-by-side facet breakdown across printing centers. Shared agents highlighted. |
| Q5 (Constantinople) | 12/25 | Found Ottoman printing but no Venice comparison. | Discovers agents in both cities (e.g., Soncino). Comparison with shared agents. |
| Q9 (Josephus) | 14/25 | Unexplored connections between translators/editors. | Surfaces translator networks, co-publication chains across editions. |
| Q10 (Jewish philosophy) | 14/25 | No intellectual network mapping. | Teacher/student chains (Nahmanides -> Shlomo ben Aderet -> Bahya ben Asher). Graph visualization data. |
| Q13 (Book collecting) | 12/25 | No cross-referencing between collectors/printers. | Collector-printer relationships via co-occurrence. |
| Q17 (Hebrew grammar) | 15/25 | Buxtorf network unused. Enrichment data (teachers: Scultetus, Pareus; students: Wasmuth) completely ignored. | Discovers teacher chain. Surfaces related grammarians. |

#### Affected Components

| File | Status | Description |
|------|--------|------------|
| `scripts/chat/cross_reference.py` | NEW | Core engine. In-memory graph from `authority_enrichment.person_info`. `find_connections()`, `build_agent_graph()`, `find_network_neighbors()`. ~280 lines. |
| `scripts/chat/narrative_agent.py` | MODIFY | Append Connections section after bios. `_format_connections()` helper. ~60 new lines. |
| `scripts/chat/aggregation.py` | MODIFY | Replace `execute_comparison()` (line 782) with multi-faceted version returning ComparisonResult. ~180 new lines. |
| `scripts/chat/exploration_agent.py` | MODIFY | Add CROSS_REFERENCE intent. `cross_reference_entity` field. Updated system prompt. ~50 new lines. |
| `scripts/chat/models.py` | MODIFY | Connection, AgentNode, ComparisonFacets, ComparisonResult models. CROSS_REFERENCE enum value. ~85 new lines. |
| `scripts/chat/formatter.py` | MODIFY | Cross-reference and comparison follow-up suggestions. ~55 new lines. |
| `app/api/main.py` | MODIFY | Enhanced COMPARISON handler, new CROSS_REFERENCE handler, connection data in Phase 1 metadata. ~80 new lines. |
| `tests/scripts/chat/test_cross_reference.py` | NEW | 13 unit tests. ~320 lines. |
| `tests/scripts/chat/test_comparison_enhanced.py` | NEW | 8 unit tests. ~250 lines. |
| `tests/scripts/chat/test_cross_reference_integration.py` | NEW | 6 integration tests against real DB. ~200 lines. |

#### Implementation Steps

1. **Define data models** -- Connection, AgentNode, ComparisonResult, ComparisonFacets in `scripts/chat/models.py`. Add CROSS_REFERENCE to ExplorationIntent enum.
2. **Build core cross-reference engine** -- `scripts/chat/cross_reference.py`. `build_agent_graph()` loads ~2,665 enriched records. `find_connections()` checks teacher/student, co-publication, same_place_period. `find_network_neighbors()` discovers 1-hop neighbors. Pure functions, no LLM.
3. **Write unit tests** -- 13 tests covering graph construction, connection types, edge cases (no enrichment, self-loops, max limits). In-memory SQLite fixtures.
4. **Integrate cross-references into narrative agent** -- After bios (line 253), call `find_connections()`. Append '**Connections found:**' section. Non-blocking (try/except). Performance guard: skip if >50 agents.
5. **Enhance comparison with multi-faceted analysis** -- Replace `execute_comparison()` with `execute_comparison_enhanced()` returning counts, date_ranges, language_distribution, top_agents, shared_agents, subject_overlap. Keep old function as backward-compatible wrapper.
6. **Write comparison tests** -- 8 tests for multi-faceted results, shared agents, empty values, backward compatibility.
7. **Add cross-reference intent to exploration agent** -- `cross_reference_entity`, `cross_reference_scope` fields. Updated system prompt with examples.
8. **Enhance follow-up suggestions** -- For multi-place results: 'Compare [A] vs [B]'. For multi-agent results: 'Show connections'. For single prominent agent: 'Show [agent] network'.
9. **Wire into API orchestrator** -- Phase 1: connection data in `response_metadata`. Phase 2: CROSS_REFERENCE handler, enhanced COMPARISON handler.
10. **Integration tests with real DB** -- Buxtorf network, Venice printer connections, teacher-student chains, Venice vs Amsterdam comparison.

#### Schema / Data-Model Changes

**New Pydantic models** (in `scripts/chat/models.py`):

```python
class Connection(BaseModel):
    agent_a: str           # display label
    agent_b: str           # display label
    relationship_type: str # teacher_of | student_of | co_publication |
                          # same_place_period | shared_occupation | network_neighbor
    evidence: str          # human-readable with source citation
    confidence: float      # teacher_of=0.90, co_publication=0.85, same_place=0.70
    agent_a_wikidata_id: Optional[str]
    agent_b_wikidata_id: Optional[str]

class AgentNode(BaseModel):
    label: str
    agent_norm: str
    authority_uri: Optional[str]
    wikidata_id: Optional[str]
    birth_year: Optional[int]
    death_year: Optional[int]
    birth_place: Optional[str]
    occupations: List[str]
    teachers: List[str]
    students: List[str]
    notable_works: List[str]
    record_count: int

class ComparisonFacets(BaseModel):
    counts: Dict[str, int]
    date_ranges: Dict[str, Tuple[Optional[int], Optional[int]]]
    language_distribution: Dict[str, Dict[str, int]]
    top_agents: Dict[str, List[Dict[str, Any]]]
    top_subjects: Dict[str, List[Dict[str, Any]]]
    shared_agents: List[str]
    subject_overlap: List[str]

class ComparisonResult(BaseModel):
    field: str
    values: List[str]
    facets: ComparisonFacets
    total_in_subgroup: int

# ExplorationIntent enum addition:
CROSS_REFERENCE = 'cross_reference'
```

No SQLite database schema changes. All relationship data from existing `authority_enrichment.person_info`.

#### Retrieval / Orchestration Changes

- **Cross-reference engine** (`scripts/chat/cross_reference.py`): New module. `build_agent_graph()` loads ~2,665 nodes from `authority_enrichment`. `find_connections()` checks pairwise relationships. Co-publication uses SQL GROUP BY on shared `record_id`.
- **Enhanced comparison** (`scripts/chat/aggregation.py`): `execute_comparison_enhanced()` runs 5 SQL queries per compared value plus 2 cross-value queries (shared agents, subject overlap).
- **Narrative agent**: After bio generation, calls `find_connections()`. Appends Connections section.
- **Follow-up suggestions**: Scans result evidence for distinct places/agents; suggests comparisons and network exploration.

#### Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Name matching ambiguity in teacher/student cross-referencing | Medium | Two-pass: exact match first, then normalized substring with constraints (same century, region). Confidence tracking. |
| Pairwise comparison O(N^2) for large agent sets | Medium | Cap at 30 agents (435 pairs max). Co-publication uses single SQL GROUP BY. Teacher/student uses pre-built graph. |
| Graph staleness after DB updates | Low | Lazy singleton with manual rebuild trigger. Enrichment runs are rare. |
| Sparse enrichment data (277/5,667 have teachers) | Medium | Fall back to co-publication and same_place_period. Return empty list gracefully, skip Connections section. |
| Enhanced comparison SQL performance | Low | IN-clause with indexed columns. <1s for 500 records. Fast-path fallback if >2s. |
| Circular teacher/student references | Low | Track visited nodes in set. Max hops=1 by default. |
| LLM misclassification COMPARISON vs CROSS_REFERENCE | Low | When COMPARISON uses field='agent', include cross-reference data alongside. Both intents produce useful results. |

#### TDD Plan

**Phase 1**: Models (5 tests in `test_models_e3.py`)
**Phase 2**: Cross-reference core (13 tests in `test_cross_reference.py`)
**Phase 3**: Narrative integration (6 tests in `test_narrative_agent_e3.py`)
**Phase 4**: Enhanced comparison (8 tests in `test_comparison_enhanced.py`)
**Phase 5**: Follow-ups and exploration (6 tests in `test_formatter_e3.py`)
**Phase 6**: Integration tests (6 tests in `test_cross_reference_integration.py`)

Total: ~50 unit tests + 6 integration tests. All unit tests run without API keys.

#### Quality Gates

| Gate | Criterion | Verification |
|------|----------|-------------|
| Buxtorf network | >=1 teacher_of connection discovered | Integration test `test_buxtorf_network` |
| Venice-Amsterdam comparison | Non-empty facets for both values | Integration test `test_venice_amsterdam` |
| Teacher-student chain | Nahmanides -> Shlomo ben Aderet discovered | Integration test `test_teacher_student_chain` |
| Follow-up suggestions | Cross-reference options included for multi-agent results | Unit test `test_followups_with_multiple_places` |
| Graceful degradation | Narrative works when no connections exist | Unit test `test_narrative_no_connections` |
| Performance | `find_connections()` <500ms for 100 records | Integration timing test |
| Backward-compatible comparison | Old `execute_comparison()` returns Dict[str, int] | Unit test `test_backward_compatible` |
| No regression | Full suite passes | `pytest tests/ -v` |

#### Deliverables

| File | Type | Est. Lines |
|------|------|-----------|
| `scripts/chat/cross_reference.py` | NEW | ~280 |
| `scripts/chat/models.py` (updated) | MODIFY | ~85 new |
| `scripts/chat/narrative_agent.py` (updated) | MODIFY | ~60 new |
| `scripts/chat/aggregation.py` (updated) | MODIFY | ~180 new |
| `scripts/chat/exploration_agent.py` (updated) | MODIFY | ~50 new |
| `scripts/chat/formatter.py` (updated) | MODIFY | ~55 new |
| `app/api/main.py` (updated) | MODIFY | ~80 new |
| `tests/scripts/chat/test_cross_reference.py` | NEW | ~320 |
| `tests/scripts/chat/test_comparison_enhanced.py` | NEW | ~250 |
| `tests/scripts/chat/test_cross_reference_integration.py` | NEW | ~200 |
| `tests/scripts/chat/test_narrative_agent_e3.py` | NEW | ~150 |
| `tests/scripts/chat/test_formatter_e3.py` | NEW | ~100 |

#### Acceptance Criteria

1. **AC1**: `find_connections()` discovers teacher/student relationships with evidence citing Wikidata source.
2. **AC2**: `find_connections()` discovers co-publication relationships (agents sharing >1 record with different roles).
3. **AC3**: `find_network_neighbors()` discovers agents 1 hop away in the teacher/student graph.
4. **AC4**: `generate_agent_narrative()` includes '**Connections found:**' section when connections exist.
5. **AC5**: `execute_comparison_enhanced()` returns multi-faceted ComparisonResult with all facet types populated.
6. **AC6**: `generate_followups()` suggests cross-reference and comparison actions when warranted.
7. **AC7**: CROSS_REFERENCE exploration intent recognized and handled in API orchestrator.
8. **AC8**: All existing tests pass with no regressions.
9. **AC9**: Graceful edge case handling: no enrichment, single agent, >100 candidates, circular references.
10. **AC10**: Performance: `find_connections()` <500ms for 100 records; `execute_comparison_enhanced()` <1s for 500-record subgroup.

---

### 2.4 Enhancement E4: Contextual Narrative Depth Layer

**Priority**: HIGH | **Effort**: 4.0 days | **Dependencies**: E3

#### Goal

Add scholarly narrative depth to 7 queries (Q1, Q2, Q4, Q5, Q11, Q16, Q18) that currently score 9-15/25 due to THIN_NARRATIVE and missing pedagogical framing. Introduce a thematic context layer with pre-authored, cited historical paragraphs; a significance scoring function for highlighting notable items; and pedagogical framing for teaching-oriented queries. All thematic content is deterministic, human-authored prose with citations -- never LLM-generated.

#### Report Failures Addressed

| Query | Current Score | What Is Missing | What E4 Adds |
|-------|-------------|----------------|-------------|
| Q1 (Bragadin Venice) | 12 | No Council of Trent context, no censorship analysis, no rival printer comparison context. | Venetian Hebrew printing and censorship thematic paragraph. Significance scoring. Teaching note. |
| Q2 (Amsterdam Hebrew) | 15 | No 'Dutch Jerusalem' framing. No Sephardic exile context. | Amsterdam as Dutch Jerusalem context. Menasseh significance. Pedagogical note. |
| Q4 (Incunabula) | 14 | No framing of why incunabula are significant. No Gutenberg context. | Incunabula and spread of printing context. Earliest items highlighted. |
| Q5 (Constantinople) | 12 | No Ottoman tolerance context. No Sephardic diaspora framing. | Ottoman Hebrew printing context. Teaching note comparing centers. |
| Q11 (Napoleon era) | 9 | No emancipation context. No Sanhedrin/ghetto dissolution analysis. | Napoleonic emancipation context. Transitional works highlighted. |
| Q16 (Biblical commentaries) | 11 | No Mikraot Gedolot tradition. No Rashi/Ibn Ezra significance. | Biblical commentary tradition context. Teaching note. |
| Q18 (Talmud editions) | 12 | No Bomberg 1520-23. No 1553 burning. No Vilna Shas. | Talmud printing history context. Landmark editions highlighted. |

#### Affected Components

| File | Status | Purpose |
|------|--------|---------|
| `scripts/chat/thematic_context.py` | NEW | Core module. 8 pre-authored thematic entries, matching engine, significance scoring, notable items selector. ~400-500 lines. |
| `app/api/main.py` | MODIFY | Integrate into `handle_query_definition_phase()` after agent narrative. ~30 lines added. |
| `scripts/chat/formatter.py` | MODIFY | Pedagogical framing functions, theme-aware followups. ~60 lines added. |
| `scripts/chat/models.py` | MODIFY | Optional `thematic_context` field on ChatResponse. ~2 lines added. |
| `scripts/chat/narrative_agent.py` | MODIFY | Export `get_agent_enrichment_for_records()` for reuse. Module-level only. |
| `tests/scripts/chat/test_thematic_context.py` | NEW | 13 unit tests. |
| `tests/scripts/chat/test_formatter_pedagogical.py` | NEW | 3 unit tests. |
| `tests/integration/test_thematic_integration.py` | NEW | 2 integration tests. |

#### Implementation Steps

1. **Define data models** -- ThematicBlock, SignificanceResult, NotableItem, Reference, MatchRule, ThematicEntry, SignificanceFactor Pydantic models. (0.25d)
2. **Author 8 thematic context entries** -- THEMATIC_REGISTRY dict with pre-authored scholarly paragraphs. Themes: (1) venetian_hebrew_printing, (2) amsterdam_dutch_jerusalem, (3) christian_hebraism, (4) haskalah, (5) incunabula_spread, (6) talmud_printing, (7) napoleonic_emancipation, (8) ottoman_hebrew_printing. Each with citations (Heller 2004, Offenberg 1990, Fuks 1987, etc.). (1.5d)
3. **Implement theme matching logic** -- `get_thematic_context(filters, candidates, db_path)`. Match rules against filter dimensions. Score by matching dimensions. Return highest-scoring theme or None. (0.5d)
4. **Implement significance scoring** -- `significance_score(candidate, db_path)`. Factors: date_rarity (pre-1500: +5), enrichment_richness (max +3.5), place_rarity, first edition indicators, subject_richness. SHARED with E5. (0.75d)
5. **Implement `get_notable_items()`** -- Score all candidates (batched DB lookups), sort descending, return top-N with highlight_reasons. Respect _MAX_RESULT_SET=100. (0.5d)
6. **Add pedagogical framing to formatter** -- `format_teaching_note()`, citation formatting, theme-specific follow-up suggestions. (0.5d)
7. **Integrate into `handle_query_definition_phase()`** -- After agent narrative block (lines 588-601). Non-blocking. Append '**Historical Context**' section. Add notable items. Merge theme-specific followups. (0.5d)
8. **Add `thematic_context` field to ChatResponse** -- Optional[str] = None. Non-breaking. (0.25d)
9. **Write comprehensive tests** -- Theme matching, significance scoring, notable items, pedagogical formatting, edge cases. (0.75d)

#### Schema / Data-Model Changes

**New Pydantic models** (in `scripts/chat/thematic_context.py`):

| Model | Key Fields |
|-------|-----------|
| ThematicBlock | `theme_id`, `title`, `context_paragraph`, `citations: List[Reference]`, `teaching_note: Optional[str]`, `matched_by: List[str]` |
| Reference | `author`, `title`, `year`, `pages: Optional[str]` |
| MatchRule | `field: FilterField`, `values: Optional[List[str]]`, `date_start`, `date_end`, `require_all: bool` |
| ThematicEntry | `theme_id`, `match_rules: List[MatchRule]`, `min_match_score: int`, `block: ThematicBlock`, `followup_suggestions: List[str]` |
| SignificanceResult | `record_id`, `score: float`, `factors: List[SignificanceFactor]` |
| SignificanceFactor | `name`, `value: float`, `reason: str` |
| NotableItem | `record_id`, `title: Optional[str]`, `score: float`, `highlight_reasons: List[str]` |

**ChatResponse modification** (`scripts/chat/models.py`): Add `thematic_context: Optional[str] = None` after line 201. Non-breaking.

#### Retrieval / Orchestration Changes

E4 does NOT change the query compilation or execution pipeline. All changes are post-retrieval enrichment. The `query_plan.filters` are read (not modified) to determine which thematic context to attach.

**New DB queries for significance scoring:**

| Purpose | SQL | Performance |
|---------|-----|------------|
| Place frequency lookup | `SELECT place_norm, COUNT(*) FROM imprints WHERE place_norm IS NOT NULL GROUP BY place_norm` | ~3ms, cached per batch |
| Enrichment richness | `SELECT ae.* FROM agents a JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri WHERE a.record_id IN (...)` | ~5ms for 100 records |

#### Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Thematic paragraphs become stale | Low | Keyed to universal historical facts (Council of Trent, Bomberg 1520-23). Annual review sufficient. |
| Users confuse thematic context with catalog data | Medium | Clear '**Historical Context**' header, horizontal rule separator, scholarly citations. |
| Multiple themes match same query | Low | Return highest-scoring. Prefer more specific (more match_rules). |
| Significance scoring expensive for large sets | Low | Respect _MAX_RESULT_SET=100. Batched queries. <20ms for 100 records. |
| Thematic context adds latency | Low | Theme matching is pure dict lookup (~0.1ms). Total overhead <30ms worst case. |
| Only 8 themes initially | Low | By design. Gracefully returns None for unmatched queries. New themes are simple dict entries. |
| E5 dependency on `significance_score()` | Low | Pure function with clean interface. E5 can import and extend. |

#### TDD Plan

**Test file**: `tests/scripts/chat/test_thematic_context.py` (13 unit tests)

Key tests:
- `test_venetian_theme_matches_venice_16c_hebrew`
- `test_amsterdam_theme_matches_amsterdam_1620_1650`
- `test_talmud_theme_matches_subject_talmud`
- `test_napoleon_theme_matches_1795_1815`
- `test_no_theme_matches_unrelated_filters` (place=london, year=1900-1950)
- `test_highest_scoring_theme_wins`
- `test_thematic_block_has_citations` -- Every entry has >=1 Reference
- `test_significance_score_pre1500_higher`
- `test_notable_items_returns_top3`
- `test_notable_items_respects_max_result_set` (>150 candidates -> empty)

**Pedagogical tests** (`tests/scripts/chat/test_formatter_pedagogical.py`, 3 tests):
- `test_format_teaching_note_output`
- `test_format_citations_output`
- `test_followups_include_thematic_suggestions`

#### Quality Gates

| Gate | Criterion | When |
|------|----------|------|
| All 8 entries have citations | Every ThematicEntry has >=1 Reference | After step 2 |
| Deterministic matching | Same input = same output, 100 times | After step 3 |
| No false matches | 10 unrelated filter sets all return None | After step 3 |
| Significance scoring stable | Same candidate = same score. No API calls. | After step 4 |
| Context clearly labeled | Output has '**Historical Context**' header | After step 7 |
| Performance <30ms | Theme matching + scoring overhead | After step 7 |
| E5 importable | `from scripts.chat.thematic_context import significance_score` succeeds | After step 4 |
| No LLM content | THEMATIC_REGISTRY has only string literals | Code review |
| No regression | Full suite passes | After step 9 |

#### Deliverables

| File | Type | Est. Lines |
|------|------|-----------|
| `scripts/chat/thematic_context.py` | NEW | ~400-500 |
| `app/api/main.py` (modified) | MODIFY | ~30 added |
| `scripts/chat/formatter.py` (modified) | MODIFY | ~60 added |
| `scripts/chat/models.py` (modified) | MODIFY | ~2 added |
| `tests/scripts/chat/test_thematic_context.py` | NEW | 13 tests |
| `tests/scripts/chat/test_formatter_pedagogical.py` | NEW | 3 tests |
| `tests/integration/test_thematic_integration.py` | NEW | 2 tests |

#### Acceptance Criteria

| ID | Criterion | Verification |
|----|----------|-------------|
| AC-1 | Q1 (Bragadin) response mentions Council of Trent/censorship with citation | curl test |
| AC-2 | Q2 (Amsterdam) response includes 'Dutch Jerusalem' or Sephardic context | curl test |
| AC-3 | Q4 (Incunabula) response explains significance of pre-1500 printing | curl test |
| AC-4 | Q5 (Constantinople) response contextualizes Ottoman Hebrew printing | curl test |
| AC-5 | Q11 (Napoleon) response mentions emancipation/Sanhedrin | curl test |
| AC-6 | Q16 (Biblical commentaries) includes pedagogical framing | curl test |
| AC-7 | Q18 (Talmud) mentions Bomberg 1520-23 or papal censorship | curl test |
| AC-8 | Thematic context clearly labeled, never confused with catalog data | All responses show '**Historical Context**' header |
| AC-9 | `significance_score()` importable by E5 | Import test |
| AC-10 | No regression on existing test suite | `pytest` exit 0 |
| AC-11 | All paragraphs pre-authored with citations, no LLM generation | Code review |
| AC-12 | Performance overhead <30ms per query | Benchmark test |

---

### 2.5 Enhancement E5: Intelligent Selection and Exhibit Curation

**Priority**: MEDIUM | **Effort**: 3.5 days | **Dependencies**: E4, E2

#### Goal

Build a curation engine (`scripts/chat/curator.py`) that scores, diversely selects, and formats exhibit-quality subsets from large CandidateSets. Replace the static RECOMMENDATION stub in `main.py` (lines 1025-1038) with a working handler that parses curation requests, scores candidates on significance, selects a diverse subset across date/place/language/agent dimensions, and returns exhibit-formatted responses with significance notes.

#### Report Failures Addressed

| Query | Current Score | Target | How Fixed |
|-------|-------------|--------|-----------|
| Q20 (Curated exhibit) | 1/25 | 12/25 | Scores all 120 records, selects diverse top-N with significance notes. Exhibit formatting with item-level rationale. |
| Q4 (Incunabula) | 14/25 | 20/25 | `select_diverse()` provides representative sampling for large result sets. (indirect) |
| Q11 (Napoleon era) | 9/25 | 15/25 | Same diverse selection mechanism. (indirect) |
| Q14 (Chronological) | 1/25 | 14/25 | Representative items supplement aggregation data. (indirect) |
| Q15 (Printing centers) | 1/25 | 14/25 | Same mechanism. (indirect) |

#### Affected Components

| File | Status | Description |
|------|--------|------------|
| `scripts/chat/curator.py` | NEW | Core module: ScoredCandidate, CurationRequest, CurationResult, `fetch_record_metadata()`, `score_candidates()`, `select_diverse()`. ~230 lines. |
| `scripts/chat/exploration_agent.py` | MODIFY | `recommendation_count`, `recommendation_criteria` fields. Updated system prompt with 5 RECOMMENDATION examples. ~35 lines added. |
| `app/api/main.py` | MODIFY | Replace static RECOMMENDATION stub with working handler. ~40 lines. |
| `scripts/chat/formatter.py` | MODIFY | `format_exhibit_item()`, `format_exhibit_response()`. ~45 lines added. |
| `scripts/chat/thematic_context.py` | DEPENDENCY (E4) | Imports `significance_score()`. Fallback stub if E4 unavailable. |
| `tests/scripts/chat/test_curator.py` | NEW | 25 tests. ~150 lines. |

#### Implementation Steps

1. **Create ScoredCandidate model and curator.py skeleton** -- Pydantic models: ScoredCandidate (record_id, significance_score, reasons, metadata), CurationRequest (n, criteria, dimensions), CurationResult (selected, total_scored, selection_method, dimension_coverage). Import `significance_score` with try/except fallback.
2. **Implement `fetch_record_metadata()` helper** -- Single query joining records, imprints, languages, agents, subjects, authority_enrichment. Returns Dict[mms_id -> metadata]. Batches if >500 IDs.
3. **Implement `score_candidates()`** -- Calls `fetch_record_metadata()` then `significance_score()` (E4) or fallback. Returns sorted list of ScoredCandidate with human-readable reasons.
4. **Implement `select_diverse()`** -- Greedy diversity-aware selection. Default dimensions: date_decade, place_norm, language, agent. Diversity bonus: `0.15 * (new_dimension_values / total_dimensions)`. Edge cases: n >= total, empty input, identical dimensions.
5. **Add exhibit formatting to formatter.py** -- `format_exhibit_item()`: 'Item {n} ({date}, {place}): {title} -- {significance_note}'. `format_exhibit_response()`: header, dimension coverage summary, items, footer.
6. **Add recommendation fields to ExplorationRequestLLM** -- `recommendation_count: Optional[int]`, `recommendation_criteria: Optional[str]`. System prompt with 5 examples.
7. **Wire up RECOMMENDATION handler in main.py** -- Replace static stub. Extract count/criteria, call `score_candidates()`, `select_diverse()`, `format_exhibit_response()`. Context-aware follow-up suggestions.
8. **Write comprehensive tests** -- 25 tests covering models, scoring (with/without E4), diverse selection (basic, edge cases, improves coverage), formatting, handler integration.

#### Schema / Data-Model Changes

**New Pydantic models** (in `scripts/chat/curator.py`):

| Model | Key Fields |
|-------|-----------|
| ScoredCandidate | `record_id: str`, `significance_score: float (0.0-1.0)`, `reasons: List[str]`, `metadata: Dict[str, Any]` |
| CurationRequest | `n: int = 10`, `criteria: Optional[str]`, `dimensions: List[str] = ['date_decade', 'place_norm', 'language', 'agent']` |
| CurationResult | `selected: List[ScoredCandidate]`, `total_scored: int`, `selection_method: str`, `dimension_coverage: Dict[str, List[str]]` |

**ExplorationRequestLLM** (`exploration_agent.py`): Add `recommendation_count: Optional[int]`, `recommendation_criteria: Optional[str]`.

**ChatResponse.metadata**: No schema change. Curation populates `metadata['curation']` with total_scored, selected_count, dimension_coverage.

#### Retrieval / Orchestration Changes

- **New SQL query** (`fetch_record_metadata`): Batch fetch joining records, imprints, languages, agents, subjects, authority_enrichment. <100ms for 120 records with existing indexes.
- **RECOMMENDATION handler replacement**: Static stub at main.py:1025-1038 replaced with working logic calling `score_candidates()` + `select_diverse()`.

#### Risks and Edge Cases

| Risk | Severity | Mitigation |
|------|----------|-----------|
| E4 dependency not yet implemented | Medium | try/except ImportError fallback. Stub uses basic heuristics (date antiquity, enrichment presence). Logs warning. |
| Very small subgroups (1-3 records) | Low | Returns all sorted by score. selection_method='top_n'. Adjusted header. |
| Very large subgroups (1000+ records) | Medium | Batched SQL (groups of 500). Greedy selection is O(n*N) -- negligible for n=10, N=1000. Target <500ms. |
| Missing metadata (NULL fields) | Low | Factors degrade: NULL date_start = 0 date_rarity. All-NULL gets minimal score. reasons=['Limited metadata']. |
| Diversity algorithm degeneracy (all identical) | Low | Degrades to pure top-N-by-score. selection_method='top_n_fallback'. |
| LLM misclassifies curation as AGGREGATION | Medium | System prompt with 5 explicit examples. Distinguishes RECOMMENDATION (selects items) from AGGREGATION (counts/groups). |
| recommendation_count out of range | Low | Clamped to [1, 50]. None defaults to 10. |

#### TDD Plan

**Test file**: `tests/scripts/chat/test_curator.py` (25 tests)

Test groups:
- **ScoredCandidate validation** (3 tests): valid, score bounds, empty reasons
- **fetch_record_metadata** (4 tests): all fields, missing record, NULL fields, batching
- **score_candidates** (4 tests): sorted descending, reasons populated, empty input, fallback scoring
- **select_diverse** (7 tests): basic, improves coverage, n exceeds total, empty, single item, dimension coverage, identical dimensions
- **exhibit formatting** (4 tests): item complete, missing date, response header, coverage summary
- **exploration agent schema** (2 tests): recommendation fields, defaults
- **integration** (3 tests): handler returns exhibit, metadata populated, followups non-empty

#### Quality Gates

| Gate | Criterion | Blocking |
|------|----------|---------|
| All unit tests pass | 25 tests in test_curator.py | Yes |
| No regressions | Full suite passes | Yes |
| Ruff linting | No errors in curator/formatter/exploration/main | Yes |
| Diversity works | Top-3-by-score same place; select_diverse picks >=2 places | Yes |
| Fallback without E4 | Scoring works when thematic_context unavailable | Yes |
| Exhibit format | Header, items, significance notes, coverage summary | Yes |
| RECOMMENDATION handler | Replaces static stub | Yes |
| Q20 scenario | >=5 curated exhibit items with notes | Yes |
| Performance | 200 records scored+selected <1s | No |

#### Deliverables

| File | Type | Est. Lines |
|------|------|-----------|
| `scripts/chat/curator.py` | NEW | ~230 |
| `scripts/chat/exploration_agent.py` (modified) | MODIFY | ~35 added |
| `app/api/main.py` (modified) | MODIFY | ~40 added |
| `scripts/chat/formatter.py` (modified) | MODIFY | ~45 added |
| `tests/scripts/chat/test_curator.py` | NEW | ~150 |

#### Acceptance Criteria

| ID | Criterion | Verification |
|----|----------|-------------|
| AC1 | 'select 10 for an exhibit' returns formatted list with significance notes (not 'not yet available') | Manual test via /chat |
| AC2 | Diverse: 120-record subgroup, 10 selected cover >=3 decades and >=3 places | Automated test |
| AC3 | Each item includes human-readable significance note | Automated test |
| AC4 | Works without E4 thematic_context (fallback scoring) | Automated test |
| AC5 | Exploration agent classifies curation requests correctly | System prompt + LLM test |
| AC6 | Response includes dimension coverage summary | Automated test |
| AC7 | User can specify count: 'pick 5', 'select 20', 'top 15'. Clamped to [1, 50]. | Schema + handler test |
| AC8 | All 25 new tests pass. No regressions. | `pytest tests/ -v` |
| AC9 | Q20 score improves from 1/25 to at least 12/25 | Manual evaluation |

---

## 3. Task Breakdown

### Task Table

| ID | Title | Enhancement | Complexity | Dependencies | Order | Deliverable | Hours |
|----|-------|------------|-----------|-------------|-------|------------|-------|
| E1-T1 | Tests: AgentAuthorityStore and schema | E1 | medium | -- | 1 | `tests/scripts/metadata/test_agent_authority.py` | 3 |
| E1-T2 | Schema and M3 contract updates | E1 | low | E1-T1 | 2 | `m3_contract.py`, `m3_schema.sql` | 2 |
| E1-T3 | Implement AgentAuthorityStore CRUD | E1 | medium | E1-T1, E1-T2 | 3 | `scripts/metadata/agent_authority.py` | 4 |
| E1-T4 | Tests: Seeding and alias-aware queries | E1 | medium | E1-T3 | 4 | `test_seed_agent_authorities.py`, `test_db_adapter_agent_alias.py` | 3 |
| E1-T5 | Implement seeding script and CLI | E1 | high | E1-T3, E1-T4 | 5 | `seed_agent_authorities.py`, `app/cli.py` | 5 |
| E1-T6 | Modify AGENT_NORM query path | E1 | medium | E1-T3, E1-T4 | 5 | `scripts/query/db_adapter.py` | 3 |
| E1-T7 | E1 integration verification | E1 | medium | E1-T5, E1-T6 | 6 | Passing tests, seeded DB | 2 |
| E2-T1 | Tests: Analytical router detection | E2 | medium | -- | 1 | `test_analytical_router.py` | 3 |
| E2-T2 | Implement analytical router | E2 | medium | E2-T1 | 2 | `scripts/chat/analytical_router.py` | 4 |
| E2-T3 | Tests: Curation engine | E2 | low | E2-T2 | 3 | `test_curation_engine.py` | 2 |
| E2-T4 | Implement curation engine and aggregation | E2 | high | E2-T2, E2-T3 | 4 | `curation_engine.py`, `aggregation.py`, `narrative_agent.py` | 5 |
| E2-T5 | Wire into API and WebSocket | E2 | high | E2-T4 | 5 | `app/api/main.py`, `models.py`, `exploration_agent.py` | 4 |
| E2-T6 | E2 integration verification | E2 | medium | E2-T5 | 6 | `test_api_analytical.py` | 3 |
| E3-T1 | Tests: Cross-reference models and engine | E3 | medium | E1-T7 | 7 | `test_cross_reference.py`, `conftest.py` | 3 |
| E3-T2 | Implement cross-reference engine | E3 | high | E3-T1 | 8 | `cross_reference.py`, `models.py` | 5 |
| E3-T3 | Tests: Enhanced comparison and narrative | E3 | medium | E3-T2 | 9 | `test_comparison_enhanced.py`, `test_narrative_agent_e3.py` | 3 |
| E3-T4 | Integrate into narrative, comparison, formatter | E3 | high | E3-T2, E3-T3 | 10 | `narrative_agent.py`, `aggregation.py`, `formatter.py` | 5 |
| E3-T5 | Wire into API and exploration agent | E3 | medium | E3-T4 | 11 | `main.py`, `exploration_agent.py` | 3 |
| E3-T6 | E3 integration verification | E3 | medium | E3-T5 | 12 | Integration tests, formatter tests | 3 |
| E4-T1 | Tests: Thematic context and scoring | E4 | medium | E3-T6 | 13 | `test_thematic_context.py` | 3 |
| E4-T2 | Implement thematic context module (8 entries) | E4 | high | E4-T1 | 14 | `scripts/chat/thematic_context.py` | 6 |
| E4-T3 | Tests: Pedagogical formatting | E4 | low | E4-T2 | 15 | `test_formatter_pedagogical.py` | 1 |
| E4-T4 | Add pedagogical framing and wire into API | E4 | medium | E4-T2, E4-T3 | 16 | `formatter.py`, `models.py`, `main.py` | 3 |
| E4-T5 | E4 integration verification | E4 | medium | E4-T4 | 17 | `test_thematic_integration.py` | 3 |
| E5-T1 | Tests: Curator scoring and diversity | E5 | medium | E4-T5, E2-T6 | 18 | `test_curator.py` | 3 |
| E5-T2 | Implement curator module | E5 | high | E5-T1 | 19 | `scripts/chat/curator.py` | 5 |
| E5-T3 | Add exhibit formatting and schema updates | E5 | medium | E5-T2 | 20 | `formatter.py`, `exploration_agent.py` | 3 |
| E5-T4 | Wire RECOMMENDATION handler in API | E5 | medium | E5-T2, E5-T3 | 21 | `app/api/main.py` | 3 |
| E5-T5 | E5 integration verification | E5 | medium | E5-T4 | 22 | Passing tests, verified output | 2 |
| FINAL-T1 | Full regression and cross-enhancement verification | ALL | medium | All T7/T6/T5 tasks | 23 | Full passing suite, regression report | 3 |

**Totals**: 30 tasks, 100 hours

### Task Distribution by Complexity

| Complexity | Count |
|-----------|-------|
| Low | 3 |
| Medium | 20 |
| High | 7 |

### Task Distribution by Type

| Type | Count |
|------|-------|
| Test (TDD, written first) | 9 |
| Implementation | 14 |
| Integration/Verification | 6 |
| Final Regression | 1 |

### Milestones

| ID | Milestone | Completion Task | Cumulative Hours |
|----|----------|----------------|-----------------|
| M-E1 | Agent Name Alias System Complete | E1-T7 | 22 |
| M-E2 | Analytical Query Routing Complete | E2-T6 | 21 |
| M-E3 | Cross-Reference Engine Complete | E3-T6 | 22 |
| M-E4 | Scholarly Narrative Depth Complete | E4-T5 | 16 |
| M-E5 | Curation Engine Complete | E5-T5 | 16 |
| M-FINAL | All Enhancements Integrated and Verified | FINAL-T1 | 3 (100 total) |

### Critical Path

```
E1-T1 -> E1-T2 -> E1-T3 -> E1-T4 -> E1-T5/T6 -> E1-T7
  -> E3-T1 -> E3-T2 -> E3-T3 -> E3-T4 -> E3-T5 -> E3-T6
    -> E4-T1 -> E4-T2 -> E4-T3 -> E4-T4 -> E4-T5
      -> E5-T1 -> E5-T2 -> E5-T3 -> E5-T4 -> E5-T5
        -> FINAL-T1
```

**Longest chain**: E1 -> E3 -> E4 -> E5 -> Final = 97 hours on the critical path.

**Bottleneck tasks**: E4-T2 (authoring 8 thematic entries, 6h) and E3-T4 (cross-reference integration across narrative/comparison/formatter, 5h).

### Parallel Opportunities

| Opportunity | Parallel Sets | Time Saving |
|------------|--------------|-------------|
| E1 and E2 fully parallel from day one | [E1-T1..T7] \|\| [E2-T1..T6] | 21 hours (full E2 in parallel) |
| Within E1: T5 and T6 parallel after T4 | [E1-T5] \|\| [E1-T6] | 3 hours |
| E3 can start as E2 finishes | [E2-T5, E2-T6] \|\| [E3-T1, E3-T2] | Up to 6 hours |
| Two-developer split | Dev A: E1->E3->E4 chain, Dev B: E2->E5 | 30-40% calendar time reduction |

---

## 4. Validation Plan

### Score Projection Table (Per Enhancement, Cumulative)

| Query | Baseline | After E1 | After E2 | After E3 | After E4 | After E5 (Final) |
|-------|----------|----------|----------|----------|----------|-------------------|
| Q1 (Bragadin Venice) | 12 | 12 | 12 | 15 | 17 | 17 |
| Q2 (Amsterdam Hebrew) | 15 | 15 | 15 | 18 | 19 | 19 |
| Q3 (Aldine Press) | 0 | 10 | 10 | 10 | 10 | 10 |
| Q4 (Incunabula) | 14 | 14 | 14 | 17 | 19 | 20 |
| Q5 (Constantinople) | 12 | 12 | 12 | 15 | 16 | 16 |
| Q6 (Buxtorf) | 0 | 14 | 14 | 14 | 14 | 14 |
| Q7 (Mendelssohn) | 0 | 14 | 14 | 14 | 14 | 14 |
| Q8 (Maimonides) | 9 | 16 | 16 | 16 | 16 | 16 |
| Q9 (Josephus) | 14 | 14 | 14 | 17 | 17 | 17 |
| Q10 (Jewish philosophy) | 14 | 14 | 14 | 17 | 17 | 17 |
| Q11 (Napoleon era) | 9 | 9 | 9 | 9 | 14 | 15 |
| Q12 (Ethiopia) | 9 | 13 | 13 | 13 | 13 | 13 |
| Q13 (Book collecting) | 12 | 12 | 12 | 15 | 15 | 15 |
| Q14 (Chronological) | 1 | 1 | 12 | 12 | 12 | 14 |
| Q15 (Printing centers) | 1 | 1 | 12 | 12 | 12 | 14 |
| Q16 (Biblical commentaries) | 11 | 11 | 11 | 11 | 15 | 15 |
| Q17 (Hebrew grammar) | 15 | 15 | 15 | 18 | 18 | 18 |
| Q18 (Talmud editions) | 12 | 12 | 12 | 12 | 16 | 16 |
| Q19 (Joseph Karo) | 0 | 14 | 14 | 14 | 14 | 14 |
| Q20 (Curated exhibit) | 1 | 1 | 10 | 10 | 10 | 14 |
| **Average** | **7.55** | **11.05** | **12.70** | **~13.90** | **~14.95** | **15.70** |
| **FAIL count** | **7** | **3** | **0** | **0** | **0** | **0** |

### Affected Queries Per Enhancement

| Enhancement | Queries | Count |
|------------|---------|-------|
| E1 (Agent Aliases) | Q3, Q6, Q7, Q8, Q12, Q19 | 6 |
| E2 (Analytical Routing) | Q14, Q15, Q20 | 3 |
| E3 (Cross-Reference) | Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17 | 8 |
| E4 (Narrative Depth) | Q1, Q2, Q4, Q5, Q11, Q16, Q18 | 7 |
| E5 (Curation) | Q4, Q11, Q14, Q15, Q20 | 5 |

### Regression Tests

| Query | Baseline Score | Minimum Acceptable | Risk Factors |
|-------|---------------|-------------------|-------------|
| Q1 (Bragadin Venice) | 12 | 12 | E3 comparison changes must not break publisher+place filter; E4 must not displace existing narrative |
| Q2 (Amsterdam Hebrew) | 15 | 14 | E3 cross-reference could slow response; multi-filter query sensitive to adapter changes |
| Q4 (Incunabula) | 14 | 13 | E2 analytical routing must not misclassify; date RANGE filter must survive E1 changes |
| Q9 (Josephus) | 14 | 13 | Subject CONTAINS unaffected by E1; E3/E4 narrative changes could regress richness |
| Q10 (Jewish philosophy) | 14 | 13 | Subject filter stability; E3 narrative additions must not overflow |
| Q13 (Book collecting) | 12 | 11 | Subject filter unchanged; formatter changes in E3/E4 could affect output |
| Q16 (Biblical commentaries) | 11 | 11 | E4 pedagogical framing must enhance not replace |
| Q17 (Hebrew grammar) | 15 | 14 | Highest-scoring query; E3 must not slow it; E1 Buxtorf alias should help |
| Q18 (Talmud editions) | 12 | 11 | E4 thematic context must enhance not replace |

### Key Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|------------|
| Overall average score | 7.55 | 15.70 | Average of 20 Q scores (0-25) via historian rubric |
| FAIL count (0/25) | 7 | 0 | Count of queries scoring 0/25 |
| FAIR+ rate (>=8/25) | 50% (10/20) | 100% (20/20) | Fraction reaching FAIR grade |
| Name resolution recall | Q3=0, Q6=0, Q7=0, Q19=0 | Q3>=1, Q6>=5, Q7>=5, Q19>=3 | Record count per query after E1 |
| Maimonides cross-script recall | 7 results | 22+ results | Q8 record count after E1 |
| Analytical routing accuracy | 0% | 100% for Q14/Q15/Q20 | `detect_analytical_query()` returns is_analytical=True |
| Cross-reference connections | 0 | >=1 per E3 query | `find_connections()` non-empty for 8 queries |
| Thematic context hits | 0/7 | 7/7 | `get_thematic_context()` non-None for 7 queries |
| Curation diversity | N/A | >=3 places, >=3 decades in top-10 | `CurationResult.dimension_coverage` for Q20 |
| Backward compatibility | All pass | All pass | `pytest tests/` exit code 0 after each E |
| Latency overhead | <200ms | <500ms with all E | Wall-clock /chat endpoint timing |

### Release Quality Gates

| Gate | Criterion | Command | Pass Condition |
|------|----------|---------|---------------|
| All unit tests | Zero failures | `pytest tests/ -v --timeout=120` | Exit 0 |
| Zero FAIL queries | No query scores 0/25 | Run 20 queries via evaluation | Min score >= 1 |
| Overall score >= 15.0 | Average meets target | Calculate from evaluation | Average >= 15.0 |
| No regressions | Baseline queries maintain scores | Compare pre/post for 9 queries | All >= baseline-1 |
| Linting clean | No ruff errors | `ruff check scripts/ app/ --select E,W,F` | Exit 0 |
| API health | Server starts and responds | `curl http://localhost:8000/health` | status=='healthy' |
| WebSocket functional | Streaming works | `pytest tests/app/test_api.py -k websocket -v` | Exit 0 |
| CLI backward compat | Existing commands work | `python -m app.cli query 'books printed in Paris'` | Returns results |
| No secrets | No API keys in tracked files | `git diff --cached | grep 'sk-'` | clean |
| Integration tests | E2E with real DB pass | `pytest tests/ --run-integration -v --timeout=120` | Exit 0 |

### Evaluation Procedure Summary

**Prerequisites**:
1. Start API: `uvicorn app.api.main:app --reload`
2. Verify health: `curl http://localhost:8000/health`
3. Set `OPENAI_API_KEY` for query compilation

**Procedure**:
1. Run each of the 20 curl commands against the `/chat` endpoint
2. Score 5 dimensions per query (0-5 each): Accuracy, Richness, CrossRef, Narrative, Pedagogical
3. Record 20x5 matrix; sum per-query totals (max 25)
4. Calculate overall average (sum / 20, max 25)
5. Grade: GOOD >= 18, FAIR >= 8, POOR >= 1, FAIL = 0
6. Verify: 0 FAILs, overall >= 15.0/25
7. Flag regressions > 1 point vs baseline

---

## 5. Open Questions / Assumptions

### Technical Assumptions

| Assumption | Notes |
|-----------|-------|
| OpenAI API for query compilation | `OPENAI_API_KEY` required for LLM-based query planning. Analytical routing (E2) is deterministic and does not require it. |
| SQLite as primary store | All enhancements use SQLite. Full-collection aggregation on ~2,796 records is performant (<100ms). |
| Existing schema is stable | All DDL is additive (`IF NOT EXISTS`). No existing tables modified. |
| authority_enrichment data is sufficient | 2,665 enriched records, 277 with teachers, 250 with students. Cross-referencing viable but sparse for some result sets. |
| agents.authority_uri is the linking key | E1 depends on `authority_uri` joining agents to agent_authorities. ~700 agents without authority_uri handled via fallback. |
| publisher_authorities pattern is proven | E1 mirrors the existing publisher authority system (228 authorities, 266 variants). |

### Decisions Needed

| Decision | Context | Options |
|----------|---------|---------|
| E4 thematic templates authorship | 8 scholarly paragraphs require domain expertise. Must be factually verifiable. | (A) Domain expert writes all 8. (B) Collaborative: draft with LLM, expert reviews/corrects. (C) Iterative: start with 3-4 highest-impact themes, add rest later. |
| E1 alias table population strategy | Initial seeding is automated from enrichment data. Manual entries needed for known gaps. | (A) Fully automated seed + manual review. (B) Automated seed only, expand iteratively. (C) Curated seed list for top-100 agents + automated for rest. |
| E5 scoring weight calibration | Default weights (temporal=0.3, enrichment=0.3, diversity=0.2, subject=0.2) are heuristic. | (A) Use defaults, tune after evaluation. (B) Make weights configurable via API parameter. (C) A/B test different weight sets. |
| Cross-reference graph refresh strategy | In-memory graph built at startup. Could become stale after enrichment runs. | (A) Lazy singleton, rebuild on /admin endpoint. (B) Rebuild on every request (costly). (C) TTL-based cache (rebuild every N hours). |
| UNIQUE alias constraint handling | Same name form (e.g., 'Moses') could apply to multiple authorities. | (A) First authority wins, log duplicate. (B) Skip ambiguous short names. (C) Allow many-to-many with disambiguation logic. |

### Verification Results

All implementation assumptions have been verified against the live codebase and database:

- **27/27 claims confirmed** with zero discrepancies
- All 10 must-exist files present
- All 5 must-not-exist files (new modules) correctly absent
- All 8 function/constant lookups matched (correct names, line numbers, values)
- All 4 schema claims confirmed (tables, columns, indexes)
- **Overall verification accuracy: 100%**
