# Rare Books Bot - Project Description (Updated January 2026)

## Executive Summary

**Rare Books Bot** is a deterministic, evidence-based bibliographic discovery system for rare book collections where MARC XML serves as the single source of truth. The system processes historical bibliographic records through a multi-stage pipeline (M1→M2→M3→M4) that enables precise, fielded queries while maintaining full traceability to original MARC fields.

**Core Philosophy:** Every query response must include:
1. **QueryPlan** - Structured JSON representation of the query
2. **CandidateSet** - Record IDs that match the criteria
3. **Evidence** - Specific MARC fields/values that caused each record's inclusion
4. **Normalized Mappings** - Raw→Normalized transformations with confidence scores

**Current Status:** Production-ready through M3 (indexing), with M4 (query execution) operational and actively being refined through comprehensive QA workflows.

---

## Project Purpose

### Primary Goal
Enable librarians, researchers, and archivists to perform precise inventory queries over rare book collections with **deterministic results** and **complete provenance tracking** back to source MARC records.

### Success Criteria
Given a natural language query like:
- *"All books published by Oxford between 1500 and 1599"*
- *"Books printed in Paris in the 16th century"*
- *"Hebrew texts on philosophy"*

The system must:
1. Parse the query into a validated QueryPlan
2. Generate SQL that queries normalized bibliographic fields
3. Return a CandidateSet with record IDs
4. Provide Evidence showing which MARC fields caused each match
5. Allow verification that raw values were correctly normalized

### Key Differentiators
- **MARC-first:** Unlike general RAG systems, preserves bibliographic standards
- **Deterministic:** Same query → same results (no LLM randomness in core pipeline)
- **Reversible normalization:** Can always trace normalized values back to raw MARC
- **Evidence-based:** Every match includes field-level provenance
- **Confidence-scored:** All normalizations include explicit confidence levels (0.0-1.0)

---

## Architecture Overview

### Data Pipeline Stages

```
MARC XML Files
    ↓
[M1: Canonical Extraction]
    ↓
Canonical JSONL (2,796 records)
    ↓
[M2: Normalization & Enrichment]
    ↓
M1+M2 JSONL (enriched)
    ↓
[M3: SQLite Indexing]
    ↓
bibliographic.db (7 tables, FTS5)
    ↓
[M4: Query Planning & Execution] ← ✅ CURRENT FOCUS
    ↓
QueryPlan → SQL → CandidateSet + Evidence
    ↓
[M5: Complex Q&A] ← 🚧 PLANNED
    ↓
Narrative Answers with Citations
```

---

## Implemented Features

### ✅ M1: MARC XML Canonical Extraction

**Purpose:** Parse MARC XML into structured, occurrence-indexed JSON records

**Status:** Production-ready (100% test coverage on core parsing)

**Key Features:**
- Occurrence indexing: `260[0]$a`, `260[1]$a` (preserves field repetition order)
- Extracts: titles, imprints, agents, subjects, languages, notes
- Provenance tracking: records which MARC tags/subfields were used
- Handles complex cases: bracketed dates, Hebrew text, uncertain publisher data

**Output:**
- `data/canonical/records.jsonl` (2,796 records × ~50 fields each)
- `data/canonical/extraction_report.json` (statistics on coverage)

**Files:**
- `scripts/marc/parse.py` - Main parser
- `scripts/marc/models.py` - Pydantic data models
- `tests/scripts/marc/test_parse.py` - 20+ tests

**Example Record Structure:**
```json
{
  "mms_id": "990011964120204146",
  "title": "Avicennae Arabum medicorum principis...",
  "imprints": [
    {
      "place": "Venetiis",
      "publisher": "apud Iuntas",
      "date": "1555",
      "raw_260": ["$a Venetiis : $b apud Iuntas, $c 1555."]
    }
  ],
  "subjects": [...],
  "agents": [...],
  "languages": ["lat"],
  "provenance": {...}
}
```

---

### ✅ M2: Deterministic Normalization

**Purpose:** Add queryable normalized fields without modifying M1 data

**Status:** Production-ready (deterministic, 20+ tests)

**Normalization Types:**

#### 1. **Date Normalization** (6 rules)
- **Exact year:** `1555` → `[1555, 1555]` (confidence: 0.99)
- **Bracketed:** `[1680]` → `[1680, 1680]` (confidence: 0.95, uncertain)
- **Circa:** `c. 1650` → `[1645, 1655]` (confidence: 0.85, ±5 year range)
- **Range:** `1500-1599` → `[1500, 1599]` (confidence: 0.99)
- **Embedded:** extracts year from complex strings (confidence: 0.90)
- **Unparsed:** → `null` with explicit reason (confidence: 0.0)

#### 2. **Place Normalization** (2-stage)
- **Stage 1 (base):** Casefold, strip punctuation, remove brackets
  - `"Venetiis :"` → `"venetiis"` (confidence: 0.80)
- **Stage 2 (alias map):** Optional LLM-assisted canonical mapping
  - `"venetiis"` → `"venice"` (confidence: 0.95)
  - `"אמשטרדם"` → `"amsterdam"` (confidence: 0.95)

#### 3. **Publisher Normalization**
- Same pipeline as places
- Handles common variants: `"C. Fosset,"` → `"fosset"`

**Key Principle:** M1 raw values are **always preserved** alongside M2 normalized values.

**Output:**
- `data/m2/records_m1m2.jsonl` (M1 + `m2` object appended)
- `data/normalization/place_aliases/place_alias_map.json` (tracked in git)

**Files:**
- `scripts/marc/normalize.py` - Normalization functions
- `scripts/marc/m2_normalize.py` - CLI enrichment script
- `scripts/marc/m2_models.py` - M2 data models
- `scripts/normalization/generate_place_alias_map.py` - LLM-assisted alias generation
- `tests/scripts/marc/test_m2_normalize.py` - 20+ tests

**Specifications:**
- `docs/specs/m2_normalization_spec.md` - Complete normalization rules
- `docs/pipelines/place_normalization.md` - Place normalization workflow
- `docs/utilities/place_alias_mapping.md` - Alias generation guide

---

### ✅ M3: SQLite Bibliographic Index

**Purpose:** Build queryable relational database with FTS for fielded searches

**Status:** Production-ready (15 tests, deployed database)

**Database Schema:**

```sql
-- Core tables
records          (id, mms_id, title_1xx, provenance_json)
titles           (id, record_id, marc_tag, title_text, title_index)
imprints         (id, record_id, place_raw, place_norm, place_confidence,
                  publisher_raw, publisher_norm, date_start, date_end, ...)
subjects         (id, record_id, heading_text, heading_index)
agents           (id, record_id, agent_name, agent_role, agent_index)
languages        (id, record_id, language_code)
notes            (id, record_id, note_type, note_text)

-- FTS5 virtual tables
titles_fts       (title_text) -- Full-text search
subjects_fts     (heading_text) -- Full-text search
```

**Indexes:**
- `imprints.date_start`, `imprints.date_end` (range queries)
- `imprints.place_norm`, `imprints.publisher_norm` (exact/prefix matches)
- `languages.language_code` (filtering)
- FTS5 tokenization on titles and subjects

**Statistics (production database):**
- 2,796 records
- 4,791 titles
- 2,773 imprints (with M2 normalization)
- 5,415 subjects
- 4,708 agents
- Database size: ~15 MB

**Output:**
- `data/index/bibliographic.db` (SQLite 3.x)

**Files:**
- `scripts/marc/m3_schema.sql` - Complete schema definition
- `scripts/marc/m3_index.py` - Indexing script
- `scripts/marc/m3_query.py` - Query helper functions
- `tests/scripts/marc/test_m3_index.py` - 15 tests

---

### ✅ M4: Query Planning & Execution (Active Development)

**Purpose:** Natural language → QueryPlan → SQL → CandidateSet with Evidence

**Status:** Operational (heuristic parser, being refined through QA)

#### Query Compiler (`scripts/query/compile.py`)

**Approach:** Heuristic regex-based pattern matching (deterministic, fast)

**Supported Query Types:**
1. **Date ranges:**
   - `"between 1500 and 1599"` → filters on `date_start`/`date_end`
   - `"in the 16th century"` → extracts century, converts to year range
   - `"from 1520"` → single year match

2. **Places:**
   - `"printed in Paris"` → filters on `place_norm`
   - `"books from Venice"` → same logic
   - Handles multi-word places: `"printed in New York"`

3. **Publishers:**
   - `"published by Oxford"` → filters on `publisher_norm`
   - `"books by Aldus Manutius"` → same
   - Prioritizes specificity in extraction

4. **Languages:**
   - `"books in Latin"` → filters on `language_code = 'lat'`
   - Supports: Latin, Hebrew, English, French, German, Italian, Spanish, Greek, Arabic

**Output Schema:**
```python
QueryPlan {
  query_text: str           # Original query
  filters: List[Filter]     # Extracted filters
  limit: int                # Result limit
  debug: dict               # Parser debug info
  plan_hash: str            # Reproducibility hash
}

Filter {
  field: FilterField        # IMPRINT_PLACE_NORM, DATE_RANGE, etc.
  op: FilterOp              # CONTAINS, BETWEEN, EQUALS
  value: Any                # Filter value(s)
}
```

**Files:**
- `scripts/query/compile.py` - Query parser
- `scripts/schemas/query_plan.py` - QueryPlan Pydantic models

#### Query Executor (`scripts/query/execute.py`)

**Purpose:** Execute QueryPlan against SQLite database, return CandidateSet

**Output Schema:**
```python
CandidateSet {
  query_text: str
  sql: str                   # Generated SQL
  total_count: int
  candidates: List[Candidate]
}

Candidate {
  record_id: str             # MMS ID
  match_rationale: str       # Human-readable explanation
  evidence: List[Evidence]   # Field-level proof
}

Evidence {
  field: str                 # MARC field (e.g., "260$a")
  value: Any                 # Raw or normalized value
  operator: str              # Comparison used
  matched_against: Any       # What was matched
}
```

**Evidence Example:**
```json
{
  "record_id": "990011964120204146",
  "match_rationale": "Place 'venetiis' (→ venice) matches filter 'venice'",
  "evidence": [
    {
      "field": "imprints.place_norm",
      "value": "venice",
      "operator": "CONTAINS",
      "matched_against": "venice"
    },
    {
      "field": "imprints.date_start",
      "value": 1555,
      "operator": "BETWEEN",
      "matched_against": [1500, 1599]
    }
  ]
}
```

**Files:**
- `scripts/query/execute.py` - Executor
- `scripts/query/db_adapter.py` - Database utilities
- `scripts/schemas/candidate_set.py` - CandidateSet models

---

### ✅ M4 QA Tool (Streamlit UI)

**Purpose:** Interactive tool for query testing, result labeling, and regression test building

**Status:** Production-ready (7 pages, full CRUD operations)

#### Page 0: QA Sessions (NEW - Wizard System)

**Purpose:** Guided testing workflows for systematic query validation

**Features:**
- **Session Types:**
  - **SMOKE (Precision Test):** Label 10+ candidates, verify evidence quality
  - **RECALL (False Negative Hunt):** Find missing records, label 5+ candidates
- **Session Management:**
  - Create new sessions with canonical or custom queries
  - Continue interrupted sessions (resume capability)
  - Abort sessions (marks as ABORTED, keeps data)
  - Delete sessions (permanent removal with confirmation)
- **5-Step Wizard:**
  1. Setup Query (select canonical or enter custom)
  2. Run + Plan Check (execute and verify plan)
  3. Label Candidates (TP/FP with bulk actions)
  4. Evidence/Missing Check (SMOKE: spot-check, RECALL: find FN)
  5. Session Summary (verdict + notes)
- **Progress Tracking:**
  - Visual stepper showing current step
  - Gating logic (can't advance until requirements met)
  - Override option for queries with < threshold results
- **Session History:**
  - View all sessions (IN_PROGRESS, DONE, ABORTED)
  - Drill down to see config, summary, labels
  - Delete any session from history

**Database:**
- `qa_sessions` table with status tracking
- Foreign keys link sessions → queries → labels
- Resume works even after browser close

#### Page 1: Run + Review

**Purpose:** Ad-hoc query testing and candidate labeling

**Features:**
- Execute natural language queries
- View QueryPlan (JSON), generated SQL, and results
- Label candidates: **TP** (True Positive), **FP** (False Positive), **FN** (False Negative), **UNK** (Unknown)
- Add issue tags per label (parser errors, normalization bugs, etc.)
- Add free-text notes
- Bulk actions: Mark all as TP/FP, clear all labels
- Sidebar detail view for selected candidate with evidence table

#### Page 2: Find Missing

**Purpose:** False negative discovery (records that should match but don't)

**Features:**
- Search bibliographic.db by year range, place, publisher
- Cross-reference search results with query results
- Mark missing records as FN
- Add issue tags to explain why record was missed

#### Page 3: Dashboard

**Purpose:** Aggregate analytics and issue tracking

**Features:**
- Statistics: Total queries reviewed, TP/FP/FN counts
- Top issue tags with bar chart visualization
- "Worst queries" ranked by FP+FN count
- Query drill-down: view plan, SQL, labels, notes per query

#### Page 4: Gold Set & Regression

**Purpose:** Export labeled queries and run regression tests

**Features:**
- **Query Management:**
  - View all queries with labels
  - Delete queries (with 2-click confirmation)
  - Filters out unwanted queries before export
- **Gold Set Export:**
  - Export to `data/qa/gold.json`
  - Format: `expected_includes` (TP + FN), `expected_excludes` (FP)
  - Includes plan hash for version tracking
- **Regression Testing:**
  - Run all gold set queries from UI
  - Validate expected_includes/expected_excludes
  - Show pass/fail status with detailed diff
  - Drill down to see missing/unexpected records

#### Page 5: Database Explorer

**Purpose:** Read-only browser for bibliographic.db

**Features:**
- Select table (records, imprints, titles, subjects, agents, languages)
- View schema (column names, types)
- Apply filters (column selection, search text, row limit)
- CSV export
- View generated SQL query

**Database Schema:**
```sql
qa_sessions (
  id, created_at, updated_at,
  session_type,        -- 'SMOKE' or 'RECALL'
  status,              -- 'IN_PROGRESS', 'DONE', 'ABORTED'
  current_step,        -- 1-5 (wizard progress)
  query_id,            -- FK to qa_queries
  session_config_json, -- Query text, thresholds
  summary_json,        -- TP/FP/FN counts, issue tags
  verdict,             -- 'PASS', 'NEEDS_WORK', 'INCONCLUSIVE'
  note
)

qa_queries (
  id, created_at, query_text, db_path,
  plan_json, sql_text, parser_debug,
  status, error_message, total_candidates,
  session_id           -- FK to qa_sessions (optional)
)

qa_candidate_labels (
  id, query_id, record_id,
  label,               -- 'TP', 'FP', 'FN', 'UNK'
  issue_tags,          -- JSON array
  note,
  created_at, updated_at,
  session_id           -- FK to qa_sessions (optional)
)
```

**Issue Tags:**
- `PARSER_MISSED_FILTER` - Heuristic parser failed to extract filter
- `PARSER_WRONG_FILTER` - Parser extracted wrong value/field
- `NORM_PLACE_BAD` - Place normalization incorrect
- `NORM_PUBLISHER_BAD` - Publisher normalization incorrect
- `DATE_PARSE_BAD` - Date parsing error
- `SQL_LOGIC_BAD` - SQL query logic issue
- `EVIDENCE_INSUFFICIENT` - Evidence doesn't justify match
- `OTHER` - Custom issue

**Launch Command:**
```bash
poetry run streamlit run app/ui_qa/main.py
```

**Files:**
- `app/ui_qa/main.py` - Streamlit entry point
- `app/ui_qa/config.py` - Configuration (paths, tags, canonical queries)
- `app/ui_qa/db.py` - Database operations (20+ functions)
- `app/ui_qa/wizard_components.py` - Wizard utilities (gating, navigation, etc.)
- `app/ui_qa/pages/0_qa_sessions.py` - Sessions landing page
- `app/ui_qa/pages/1_run_review.py` - Query execution and labeling
- `app/ui_qa/pages/2_find_missing.py` - FN discovery
- `app/ui_qa/pages/3_dashboard.py` - Analytics
- `app/ui_qa/pages/4_gold_set.py` - Export and regression
- `app/ui_qa/pages/5_db_explorer.py` - Database browser
- `app/ui_qa/pages/_wizard.py` - Guided workflow (5 steps)
- `app/ui_qa/README.md` - Usage documentation
- `app/ui_qa/USAGE.md` - Quick reference

**Documentation:**
- `docs/qa_wizard_implementation.md` - Wizard design and testing checklist

---

### ✅ CLI Regression Runner

**Purpose:** Automated regression testing for CI/CD integration

**Status:** Production-ready

**Usage:**
```bash
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db \
  --verbose \
  --log-file test-results/regress.json
```

**Exit Codes:**
- `0` - All tests passed
- `1` - One or more tests failed

**Features:**
- Runs all queries from gold set
- Validates expected_includes/expected_excludes
- Reports missing and unexpected records
- JSON log output for CI parsing
- Summary metrics (passed/failed/errors)

**Files:**
- `app/qa.py` - CLI runner (Typer-based)

---

## Development Workflows

### Daily Development Cycle

1. **Make changes** to parser/normalization/query logic
2. **Run tests:** `pytest tests/scripts/marc/`
3. **Test queries in UI:** `streamlit run app/ui_qa/main.py`
4. **Label results** (mark FP/FN, add issue tags)
5. **Update gold set:** Export from UI
6. **Run regression:** `python -m app.qa regress --gold data/qa/gold.json`
7. **Commit** with test evidence

### Adding New Query Types

1. **Identify pattern** from failed queries in dashboard
2. **Add regex pattern** to `scripts/query/compile.py`
3. **Add unit test** to `tests/scripts/query/test_compile.py`
4. **Test in UI** with multiple examples
5. **Add to canonical queries** in `app/ui_qa/config.py`
6. **Run SMOKE session** in wizard
7. **Update gold set** if passing

### Fixing Normalization Issues

1. **Identify issue** from FP/FN labels in dashboard
2. **Add test case** to `tests/scripts/marc/test_m2_normalize.py`
3. **Fix normalization** in `scripts/marc/normalize.py`
4. **Regenerate M2 data:** `python -m scripts.marc.m2_normalize ...`
5. **Rebuild M3 index:** `python -m scripts.marc.m3_index ...`
6. **Re-run affected queries** in UI
7. **Verify FP/FN resolved**

---

## Testing Infrastructure

### Test Coverage

**Unit Tests:** 12 test files, 80+ tests
- `tests/scripts/marc/test_parse.py` - M1 parsing (20+ tests)
- `tests/scripts/marc/test_m2_normalize.py` - M2 normalization (20+ tests)
- `tests/scripts/marc/test_place_freq.py` - Frequency analysis (11 tests)
- `tests/scripts/marc/test_m3_index.py` - M3 indexing (15 tests)
- `tests/scripts/query/test_compile.py` - Query parsing
- `tests/scripts/query/test_execute.py` - Query execution

**Integration Tests:**
- QA tool manual testing workflows (wizard sessions)
- End-to-end query testing via Streamlit UI
- Regression testing via gold set

**Test Commands:**
```bash
# All tests
pytest

# Specific suite
pytest tests/scripts/marc/test_m2_normalize.py

# With coverage
pytest --cov=scripts --cov-report=html

# Fast tests only
pytest -m "not slow"
```

**Test Data:**
- Reference record: `990011964120204146` (Avicenna medical text, Venice 1555)
- Test fixtures in `tests/fixtures/`
- Test database subset in `tests/scripts/marc/fixtures/`

---

## Technology Stack

### Core Languages & Frameworks
- **Python 3.11-3.13** (type-hinted throughout)
- **Pydantic 2.x** - Data validation and serialization
- **SQLite 3.x** - Database engine
- **Streamlit 1.x** - Web UI framework
- **Typer** - CLI framework

### Data Processing
- **pymarc** - MARC record parsing
- **lxml** - XML processing
- **pandas** - Data manipulation (frequency analysis)

### LLM Integration (Utilities Only)
- **litellm** - LLM API client (used only in place alias generation, not core pipeline)

### Code Quality
- **pytest** - Testing framework
- **pytest-cov** - Coverage reporting
- **ruff** - Linting and formatting
- **black** - Code formatting
- **pylint** - Additional linting
- **mypy** (planned) - Static type checking

### Dependencies
See `pyproject.toml` for complete list (44 dependencies total, 15 direct)

---

## Project Statistics

### Codebase Size
- **Scripts:** 29 Python files (~4,500 lines)
- **App/UI:** 15 Python files (~2,500 lines)
- **Tests:** 12 test files (~2,000 lines)
- **Documentation:** 15+ markdown files (~8,000 lines)
- **Total:** ~17,000 lines of Python + documentation

### Data Volume (Production)
- **MARC XML:** 1 file, ~20 MB (2,796 records)
- **Canonical JSONL:** ~8 MB (M1 output)
- **M2 JSONL:** ~10 MB (M1 + M2 enrichment)
- **SQLite Database:** ~15 MB (indexed, queryable)
- **Place Alias Map:** 1,200+ place variants → ~300 canonical names

### Performance Benchmarks
- **M1 Parsing:** ~500 records/second
- **M2 Normalization:** ~800 records/second
- **M3 Indexing:** ~2,796 records in < 5 seconds
- **M4 Query:** < 100ms for typical query (10-50 results)
- **FTS Search:** < 50ms for full-text title/subject search

---

## Future Development

### 🚧 M4 Enhancements (Short-term)

**Query Parser Improvements:**
- Support compound filters: `"books by X OR Y"`
- Handle negation: `"not printed in Paris"`
- Subject/topic filtering: `"books on medicine"`
- Agent-based queries: `"books by author X"`
- Title search integration: `"books with 'philosophy' in title"`

**Evidence Improvements:**
- Show raw MARC field excerpts in evidence
- Highlight exact matched substrings
- Include confidence scores in evidence
- Link evidence to M1 provenance

**SQL Generation:**
- Query optimization (currently naive JOIN)
- Support for complex boolean logic
- Better handling of missing/null fields

**QA Tool Enhancements:**
- Batch labeling workflows
- Import gold sets from external sources
- Export labels to CSV for analysis
- Diff tool to compare plan versions
- Analytics: Parser accuracy over time

### 📋 M5: Complex Question Answering (Planned)

**Purpose:** Answer interpretive questions using CandidateSet + curated knowledge

**Example Questions:**
- *"What is the cultural significance of this text?"*
- *"How does this edition compare to the Amsterdam 1640 edition?"*
- *"Why would a collector be interested in this book?"*

**Architecture:**
```
User Question
    ↓
[M4: Get CandidateSet]
    ↓
[Load full MARC for candidates]
    ↓
[Optional: Web enrichment with caching]
    ↓
[LLM prompt with evidence constraint]
    ↓
Answer + Citations (MARC fields, web sources)
```

**Key Constraints:**
- Must operate over **CandidateSet only** (no hallucinated records)
- Citations required for all facts (MARC field or web URL)
- If insufficient evidence, explicitly say so
- Web enrichment is **opt-in** and **cached with provenance**

**Files (planned):**
- `scripts/qa/answer.py` - Answer generator
- `scripts/qa/enrichment.py` - Web data fetcher
- `scripts/qa/prompt_builder.py` - Constrained prompt construction

---

### 📋 Additional Normalization Types (Planned)

**Agent/Author Normalization:**
- Normalize name variants: `"Avicenna"` = `"Ibn Sina"` = `"Abū ʿAlī al-Ḥusayn ibn ʿAbd Allāh ibn Sīnā"`
- Extract dates: `"1473-1543"` → birth/death years
- Normalize roles: `"author"`, `"translator"`, `"editor"`, etc.

**Subject Normalization:**
- Map to controlled vocabularies (LCSH, FAST)
- Extract hierarchical relationships
- Detect language of subject heading

**Format/Genre Normalization:**
- Extract physical format (folio, quarto, octavo)
- Detect genre (incunabula, manuscript, printed book)

**Language Detection:**
- Infer language from title/imprint when missing
- Handle multilingual texts

---

### 📋 Publisher Alias Mapping (Planned)

**Purpose:** Canonical mapping for publisher name variants

**Approach:** Same as place alias mapping (LLM-assisted, version-controlled)

**Examples:**
- `"apud Iuntas"` → `"Giunti"` (Venice printing house)
- `"C. Fosset"` → `"Fosset"` (Paris publisher)
- `"Elsevier"` → `"Elsevier"` (Amsterdam publisher family)

**Files (planned):**
- `data/normalization/publisher_aliases/publisher_alias_map.json`
- `scripts/normalization/generate_publisher_alias_map.py`

---

### 📋 Web Enrichment (Planned)

**Purpose:** Augment MARC records with external data (opt-in, cached)

**Sources:**
- VIAF (Virtual International Authority File) for agents
- WorldCat for edition comparisons
- USTC (Universal Short Title Catalogue) for early printed books
- Library of Congress for controlled vocabularies

**Architecture:**
```
record_id
    ↓
[Check enrichment cache]
    ↓
    ├─ Hit: Return cached data
    │
    └─ Miss:
        ↓
        [Fetch from web API]
        ↓
        [Validate schema]
        ↓
        [Store with provenance + confidence]
        ↓
        Return enriched data
```

**Storage:**
- `data/enrichment/<source>/<record_id>.json` (cached responses)
- `data/enrichment/<source>/metadata.json` (fetch timestamps, versions)

**Constraints:**
- Must include source URL
- Must include confidence score
- Must respect rate limits
- Must handle failures gracefully (cache errors)

---

### 📋 CI/CD Integration (Planned)

**GitHub Actions Workflows:**

1. **Test & Lint** (on every push)
   - Run pytest with coverage
   - Run ruff/black checks
   - Report coverage to codecov

2. **M1-M3 Pipeline** (on data changes)
   - Trigger on `data/marc_source/` changes
   - Run M1 → M2 → M3 pipeline
   - Upload database artifacts

3. **M4 Regression** (on query logic changes)
   - Run gold set regression tests
   - Fail PR if regressions detected
   - Generate diff report

4. **QA Dashboard** (nightly)
   - Run all canonical queries
   - Generate metrics report
   - Alert on new failures

**Files (planned):**
- `.github/workflows/test.yml`
- `.github/workflows/pipeline.yml`
- `.github/workflows/regression.yml`
- `.github/workflows/qa_report.yml`

---

### 📋 Advanced Analytics (Planned)

**QA Metrics Dashboard:**
- Parser accuracy over time (% queries parsed correctly)
- Normalization coverage (% fields successfully normalized)
- False positive/negative trends
- Issue tag frequency (what breaks most often)

**Collection Insights:**
- Most common places (geographic distribution)
- Publication timeline (books per decade)
- Language distribution
- Subject taxonomy (hierarchical breakdown)
- Agent network (publisher/author relationships)

**Visualization:**
- Timeline charts (publications over time)
- Geographic maps (printing locations)
- Network graphs (agent relationships)
- Confidence distribution histograms

**Files (planned):**
- `scripts/analytics/collection_stats.py`
- `scripts/analytics/qa_metrics.py`
- `app/ui_qa/pages/6_analytics.py` (Streamlit page)

---

## Key Design Principles

### 1. MARC XML as Source of Truth
- All answers trace back to MARC fields
- No destructive transformations
- Full provenance at all times

### 2. Deterministic Processing
- Same input → same output (no randomness in core pipeline)
- Testable, reproducible, debuggable
- LLM use restricted to utilities (alias mapping, M5 Q&A)

### 3. Confidence-Scored Normalization
- Every normalized field has explicit confidence (0.0-1.0)
- Method tags explain how normalization was done
- Unparsed values preserved with reasons (never silently dropped)

### 4. Evidence-Based Answers
- Every match includes field-level evidence
- Users can verify system's reasoning
- No "black box" matches

### 5. Reversibility
- Can always trace normalized → raw
- M1 preserved alongside M2/M3
- Enables debugging and quality control

### 6. Code Quality
- Single-purpose functions (< 50 lines)
- Type hints everywhere
- Comprehensive docstrings
- Unit tests for all logic
- No global state

---

## Documentation Index

### Specifications
- `docs/specs/m2_normalization_spec.md` - Complete M2 normalization rules
- `docs/specs/place_frequency_spec.md` - Place frequency analysis specification

### Pipelines
- `docs/pipelines/place_normalization.md` - End-to-end place normalization workflow

### Utilities
- `docs/utilities/place_alias_mapping.md` - LLM-assisted alias generation guide

### Implementation Guides
- `docs/qa_wizard_implementation.md` - QA wizard design and workflows

### Developer Instructions
- `docs/dev_instructions/M4_phase_instructions.txt` - M4 development guidelines
- `docs/dev_instructions/ui_qa_tool_instructions.txt` - QA tool usage
- `docs/dev_instructions/ui_qa_tool_wizard_instructions.txt` - Wizard workflows

### Core Documentation
- `CLAUDE.md` - Claude Code guidance (development philosophy, contracts, rules)
- `README.md` - Quick start and architecture overview
- `plan.mf` - Milestone roadmap (M0-M5)
- `app/ui_qa/README.md` - QA tool user guide
- `app/ui_qa/USAGE.md` - Quick reference

---

## Getting Started for New Developers

### 1. Environment Setup
```bash
# Clone repository
git clone https://github.com/hagaybar/rare-books-bot.git
cd rare-books-bot

# Install dependencies
poetry install

# Verify installation
pytest
```

### 2. Understand the Pipeline
```bash
# Read core documentation
cat CLAUDE.md           # Development philosophy
cat README.md           # Quick start guide
cat plan.mf             # Milestone roadmap

# Examine data flow
ls -R data/             # See pipeline outputs
```

### 3. Run the Full Pipeline
```bash
# M1: Parse MARC XML
python -m scripts.marc.parse_xml \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/canonical/records.jsonl

# M2: Normalize
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json

# M3: Index
python -m scripts.marc.m3_index \
  data/m2/records_m1m2.jsonl \
  data/index/bibliographic.db \
  scripts/marc/m3_schema.sql
```

### 4. Launch QA Tool
```bash
# Start Streamlit UI
poetry run streamlit run app/ui_qa/main.py

# In browser:
# - Page 1: Run test queries
# - Page 0: Try wizard workflow (SMOKE session)
# - Page 3: View analytics
```

### 5. Read Key Source Files
```bash
# Core parsing
cat scripts/marc/parse.py          # M1 parser
cat scripts/marc/normalize.py      # M2 normalization

# Query system
cat scripts/query/compile.py       # Query parser
cat scripts/query/execute.py       # SQL executor

# QA tool
cat app/ui_qa/db.py                # Database operations
cat app/ui_qa/pages/_wizard.py     # Wizard workflow
```

### 6. Run Tests
```bash
# All tests
pytest

# Specific test suite
pytest tests/scripts/marc/test_m2_normalize.py -v

# With coverage
pytest --cov=scripts --cov-report=html
```

### 7. Make Your First Contribution
**Example:** Add support for a new query pattern

1. Find a failing query in the QA dashboard (Page 3)
2. Identify the missing pattern (e.g., "before 1500")
3. Add regex pattern to `scripts/query/compile.py`
4. Add test to `tests/scripts/query/test_compile.py`
5. Test in QA tool UI (Page 1)
6. Run regression: `python -m app.qa regress --gold data/qa/gold.json`
7. Commit with test evidence

---

## Contact & Contribution

**Project Lead:** Hagay Bar (hagay.bar@gmail.com)

**Repository:** https://github.com/hagaybar/rare-books-bot

**License:** [To be added]

**Contributing:** See `CLAUDE.md` for development guidelines and code standards.

---

## Appendix: File Structure

```
rare-books-bot/
├── CLAUDE.md                      # Claude Code guidance (8.5 KB)
├── README.md                      # Quick start guide (10.7 KB)
├── plan.mf                        # Milestone roadmap (2.3 KB)
├── pyproject.toml                 # Dependencies and build config
├── pytest.ini                     # Test configuration
│
├── docs/                          # Documentation (15+ files)
│   ├── specs/                     # Feature specifications
│   │   ├── m2_normalization_spec.md
│   │   └── place_frequency_spec.md
│   ├── pipelines/                 # Pipeline workflows
│   │   └── place_normalization.md
│   ├── utilities/                 # Utility guides
│   │   └── place_alias_mapping.md
│   ├── dev_instructions/          # Developer instructions
│   │   ├── M4_phase_instructions.txt
│   │   ├── ui_qa_tool_instructions.txt
│   │   └── ui_qa_tool_wizard_instructions.txt
│   └── qa_wizard_implementation.md
│
├── scripts/                       # Source code (29 Python files)
│   ├── marc/                      # MARC processing (M1-M3)
│   │   ├── parse.py              # M1: MARC XML parser
│   │   ├── models.py             # M1 data models
│   │   ├── normalize.py          # M2: Normalization functions
│   │   ├── m2_normalize.py       # M2: CLI enrichment
│   │   ├── m2_models.py          # M2 data models
│   │   ├── build_place_freq.py   # Place frequency analysis
│   │   ├── m3_schema.sql         # M3: SQLite schema
│   │   ├── m3_index.py           # M3: Indexing script
│   │   └── m3_query.py           # M3: Query helpers
│   ├── query/                     # Query system (M4)
│   │   ├── compile.py            # Natural language → QueryPlan
│   │   ├── execute.py            # QueryPlan → CandidateSet
│   │   └── db_adapter.py         # Database utilities
│   ├── schemas/                   # Pydantic data models
│   │   ├── query_plan.py         # QueryPlan schema
│   │   └── candidate_set.py      # CandidateSet schema
│   ├── normalization/             # Normalization utilities
│   │   └── generate_place_alias_map.py
│   └── utils/                     # Shared utilities
│       ├── logger.py
│       ├── config_loader.py
│       └── task_paths.py
│
├── app/                           # CLI and UI (15 Python files)
│   ├── cli.py                    # Main CLI interface
│   ├── qa.py                     # CLI regression runner
│   └── ui_qa/                    # Streamlit QA tool
│       ├── main.py               # Streamlit entry point
│       ├── config.py             # Configuration
│       ├── db.py                 # Database operations
│       ├── wizard_components.py  # Wizard utilities
│       ├── README.md             # User guide
│       ├── USAGE.md              # Quick reference
│       └── pages/
│           ├── 0_qa_sessions.py  # Sessions landing page
│           ├── 1_run_review.py   # Query execution & labeling
│           ├── 2_find_missing.py # FN discovery
│           ├── 3_dashboard.py    # Analytics
│           ├── 4_gold_set.py     # Export & regression
│           ├── 5_db_explorer.py  # Database browser
│           └── _wizard.py        # Guided workflow (5 steps)
│
├── tests/                         # Test suite (12 test files)
│   ├── fixtures/                  # Test data
│   └── scripts/
│       ├── marc/
│       │   ├── test_parse.py
│       │   ├── test_m2_normalize.py
│       │   ├── test_place_freq.py
│       │   └── test_m3_index.py
│       └── query/
│           ├── test_compile.py
│           └── test_execute.py
│
├── data/                          # Data artifacts (mostly gitignored)
│   ├── marc_source/               # Raw MARC XML (20 MB)
│   ├── canonical/                 # M1 output (8 MB, 2,796 records)
│   │   ├── records.jsonl
│   │   └── extraction_report.json
│   ├── frequency/                 # Frequency analysis
│   │   ├── places_freq.csv
│   │   └── places_examples.json
│   ├── normalization/             # Normalization artifacts
│   │   └── place_aliases/
│   │       ├── place_alias_map.json  # (tracked in git)
│   │       ├── place_alias_cache.jsonl # (gitignored)
│   │       └── place_alias_proposed.csv # (gitignored)
│   ├── m2/                        # M2 output (10 MB)
│   │   └── records_m1m2.jsonl
│   ├── index/                     # M3 output (15 MB)
│   │   └── bibliographic.db
│   ├── qa/                        # QA tool database
│   │   ├── qa.db
│   │   └── gold.json
│   └── runs/                      # M4 query artifacts (per run_id)
│
├── configs/                       # Configuration files
│   └── README.md
│
├── logs/                          # Execution logs
│   └── runs/
│
└── archive/                       # Reference materials
    └── backup_CLAUDE.md
```

---

**Last Updated:** January 11, 2026
**Document Version:** 1.0
**Project Status:** M4 Active Development, Production-Ready through M3
