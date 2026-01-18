# Ground-Up System Audit Report

**Date:** 2026-01-18
**Audit Type:** Assumption-Free Reconstruction
**Auditor:** Claude Opus 4.5

---

## 1. Executive Summary

**Current System Maturity:** A functional conversational chatbot over bibliographic records with complete backend pipeline (M1-M4), two-phase conversation architecture, and enrichment capabilities—but with 21 failing tests and a critical mismatch between FTS5 query behavior and unit test expectations.

### 3 Most Critical Blockers

| # | Blocker | Impact | Evidence |
|---|---------|--------|----------|
| 1 | **FTS5 quoting breaks EQUALS path** | 21 query tests failing; title/subject EQUALS queries wrap values in quotes meant for FTS5 CONTAINS | `scripts/query/db_adapter.py:58-67` |
| 2 | **Database schema not rebuilt** | Country code columns added but DB has unmapped codes; tests assume old schema | `data/index/bibliographic.db` has `aa`, `ag`, `bl` codes with NULL names |
| 3 | **datetime.utcnow() deprecation** | 211 deprecation warnings; will break in Python 3.14 | `scripts/chat/session_store.py` multiple locations |

### 3 Most Promising Strengths

| # | Strength | Evidence |
|---|----------|----------|
| 1 | **Complete end-to-end system** | Streamlit chat UI (`app/ui_chat/main.py`, 279 lines) + FastAPI backend + SQLite storage |
| 2 | **Well-structured evidence system** | Every query result includes `Evidence` objects with field, value, operator, source, confidence |
| 3 | **LLM query caching** | JSONL cache at `data/query_plan_cache.jsonl` prevents redundant API calls |

---

## 2. Observed System Map (Inferred)

### 2.1 Directory Structure

```
rare-books-bot/
├── app/                          # Entry points
│   ├── cli.py                    # Typer CLI (parse_marc, query, chat-*)
│   ├── qa.py                     # Regression runner
│   ├── api/                      # FastAPI chatbot API
│   │   └── main.py               # REST + WebSocket endpoints
│   ├── ui_qa/                    # Streamlit QA tool (5 pages)
│   └── ui_chat/                  # Streamlit chat UI (279 lines)
│
├── scripts/                      # Core library
│   ├── marc/                     # M1-M3: Parse → Normalize → Index
│   │   ├── parse.py              # MARC XML → Canonical JSONL
│   │   ├── normalize.py          # Date/Place/Publisher normalization
│   │   ├── m3_index.py           # JSONL → SQLite
│   │   └── models.py             # Pydantic models
│   │
│   ├── query/                    # M4: NL → SQL → Results
│   │   ├── llm_compiler.py       # OpenAI GPT-4o query compilation
│   │   ├── db_adapter.py         # SQL generation
│   │   └── execute.py            # Query execution + evidence
│   │
│   ├── chat/                     # Conversation management
│   │   ├── intent_agent.py       # Query interpretation with confidence
│   │   ├── exploration_agent.py  # Phase 2 corpus exploration
│   │   ├── aggregation.py        # Count/group queries + overview
│   │   ├── session_store.py      # SQLite session persistence
│   │   └── models.py             # ChatSession, Message, etc.
│   │
│   ├── enrichment/               # External data integration
│   │   ├── enrichment_service.py # Orchestrator
│   │   ├── wikidata_client.py    # Wikidata API
│   │   └── nli_client.py         # NLI API
│   │
│   └── schemas/                  # Cross-module contracts
│       ├── query_plan.py         # QueryPlan, Filter, FilterField
│       └── candidate_set.py      # CandidateSet, Candidate, Evidence
│
├── data/                         # Artifacts (mostly gitignored)
│   ├── canonical/records.jsonl   # 2,796 M1 records
│   ├── m2/records_m1m2.jsonl     # Normalized records
│   ├── index/bibliographic.db    # 7.5MB SQLite (19 tables incl. FTS5)
│   ├── chat/sessions.db          # Session storage
│   ├── query_plan_cache.jsonl    # LLM query cache
│   └── intent_cache.jsonl        # Intent interpretation cache
│
└── tests/                        # 349 tests (328 passing, 21 failing)
```

### 2.2 Data Flow

```
┌─────────────────┐
│  MARC XML       │  (Source of Truth)
│  2,796 records  │
└────────┬────────┘
         │ CLI: parse_marc
         ▼
┌─────────────────┐
│  Canonical JSONL│  (M1: parse.py)
│  records.jsonl  │  - SourcedValue provenance
└────────┬────────┘  - Subfield-level tracking
         │ m2_normalize.py
         ▼
┌─────────────────┐
│  Normalized JSONL│  (M2: normalize.py)
│  records_m1m2   │  - Date ranges + confidence
└────────┬────────┘  - Place/Publisher normalization
         │ m3_index.py
         ▼
┌─────────────────┐
│  SQLite DB      │  (M3: 19 tables)
│  bibliographic  │  - records, titles, subjects, agents
│  .db            │  - imprints, languages, notes
└────────┬────────┘  - titles_fts, subjects_fts (FTS5)
         │
         ▼
┌─────────────────────────────────────────┐
│  Query Pipeline (M4)                     │
│  ┌──────────────┐  ┌──────────────┐     │
│  │ LLM Compiler │→ │ DB Adapter   │     │
│  │ (GPT-4o)     │  │ (SQL Gen)    │     │
│  └──────────────┘  └──────┬───────┘     │
│                           │             │
│                    ┌──────▼───────┐     │
│                    │  Execute     │     │
│                    │  (Evidence)  │     │
│                    └──────────────┘     │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Chat API (M6)                           │
│  - Phase 1: Query Definition             │
│  - Phase 2: Corpus Exploration           │
│  - Session management                    │
│  - Enrichment (Wikidata, NLI)           │
└─────────────────────────────────────────┘
```

### 2.3 Entry Points

| Entry Point | Type | Location | Purpose |
|-------------|------|----------|---------|
| `parse_marc` | CLI | `app/cli.py:19` | MARC XML → Canonical JSONL |
| `query` | CLI | `app/cli.py:165` | NL query → CandidateSet |
| `chat-init/history/cleanup` | CLI | `app/cli.py:81-162` | Session management |
| `/chat` | HTTP POST | `app/api/main.py:214` | Chatbot endpoint |
| `/ws/chat` | WebSocket | `app/api/main.py` | Streaming responses |
| `/health` | HTTP GET | `app/api/main.py:176` | Health check |
| Streamlit Chat | Web | `app/ui_chat/main.py` | User-facing chat UI |
| Streamlit QA | Web | `app/ui_qa/` | Query labeling tool |

### 2.4 Persistent State

| Artifact | Path | Size | Purpose |
|----------|------|------|---------|
| Canonical JSONL | `data/canonical/records.jsonl` | 6.2MB | M1 output |
| Normalized JSONL | `data/m2/records_m1m2.jsonl` | 10.5MB | M2 output |
| Bibliographic DB | `data/index/bibliographic.db` | 7.9MB | M3 queryable index |
| Session DB | `data/chat/sessions.db` | Variable | Conversation state |
| Enrichment Cache | `data/enrichment/cache.db` | Variable | Wikidata/NLI cache |
| Query Plan Cache | `data/query_plan_cache.jsonl` | 20KB | LLM response cache |
| Intent Cache | `data/intent_cache.jsonl` | 11KB | Intent interpretation cache |

---

## 3. What the System Actually Does Today

### 3.1 Supported Operations

| Operation | How | Evidence |
|-----------|-----|----------|
| Parse MARC XML → JSONL | `app/cli.py parse_marc` | 2,796 records extracted |
| Normalize dates/places/publishers | `scripts/marc/normalize.py` | Confidence-scored rules |
| Index to SQLite with FTS5 | `scripts/marc/m3_index.py` | 19 tables created |
| NL query → SQL via LLM | `scripts/query/llm_compiler.py` | GPT-4o with caching |
| Execute query with evidence | `scripts/query/execute.py` | Evidence objects attached |
| Two-phase conversation | `app/api/main.py` | Phase 1 + Phase 2 routing |
| Session persistence | `scripts/chat/session_store.py` | SQLite-based |
| Collection overview | `scripts/chat/aggregation.py:get_collection_overview` | Statistics response |
| Enrichment (Wikidata/NLI) | `scripts/enrichment/` | External data integration |

### 3.2 Unsupported But Implied

| Feature | Implied By | Actual Status |
|---------|------------|---------------|
| JWT authentication | `plan.mf:68` mentions "JWT (planned)" | Not implemented |
| Multi-user isolation | API has sessions but no user auth | Single-user mode |
| Country filtering in queries | Country code columns added | Schema migration needed |

### 3.3 Accidental Behaviors

| Behavior | Location | Impact |
|----------|----------|--------|
| Title EQUALS gets FTS5 quotes | `db_adapter.py:58-67` | Returns `"term"` instead of `term` |
| Hebrew calendar dates (5000+) filtered in overview | `aggregation.py:545` | `date_start <= 2100` filter |
| Unmapped country codes return NULL name | `m3_index.py:181` | `aa`, `ag`, `bl` have no country_name |

---

## 4. Determinism & Reliability Findings

### 4.1 LLM Usage Points (Non-Deterministic)

| Location | Purpose | Mitigation |
|----------|---------|------------|
| `scripts/query/llm_compiler.py:229` | Query plan generation | JSONL cache |
| `scripts/chat/intent_agent.py` | Intent interpretation | JSONL cache |
| `scripts/chat/exploration_agent.py` | Phase 2 requests | No cache observed |
| `scripts/normalization/generate_place_alias_map.py` | Place alias generation | One-time script |

### 4.2 Detailed Findings

#### P0: FTS5 Quoting Breaks EQUALS Path

- **Severity:** P0 (Correctness)
- **Evidence:** `scripts/query/db_adapter.py:58-67`
- **Concrete Failure:**
  ```python
  # Test expects:
  normalize_filter_value(FilterField.TITLE, "Historia Mundi") == "historia mundi"
  # Actual returns:
  '"historia mundi"'  # Wrapped in quotes for FTS5
  ```
- **Why It Matters:** Title EQUALS queries use direct string comparison but receive FTS5-quoted values, causing 0 matches.

#### P1: Database Schema Drift

- **Severity:** P1 (Data Integrity)
- **Evidence:** `data/index/bibliographic.db` query shows:
  ```
  aa -> None: 1 records
  ag -> None: 3 records
  bl -> None: 1 records
  ```
- **Concrete Failure:** Country codes exist in DB but mapping incomplete (41 codes mapped, dozens unmapped)
- **Why It Matters:** Country filtering will miss records with unmapped codes.

#### P1: datetime.utcnow() Deprecation

- **Severity:** P1 (Future Compatibility)
- **Evidence:** `scripts/chat/session_store.py:230, 264, 286, 301, 310`
- **Concrete Failure:** 211 deprecation warnings in test output
- **Why It Matters:** Python 3.12+ deprecates `utcnow()`, will break in Python 3.14+

#### P2: No Test for Overview Query Detection

- **Severity:** P2 (Coverage Gap)
- **Evidence:** `scripts/chat/aggregation.py:is_overview_query()` (80 lines)
- **Concrete Failure:** No unit tests for `is_overview_query()` function
- **Why It Matters:** Complex logic with many edge cases untested.

---

## 5. Architectural Gaps & Drift

### 5.1 Conceptual Gaps

| Gap | Stated Intent | Reality |
|-----|---------------|---------|
| Web UI | "M6 Chatbot (Web + API)" | API complete, no UI |
| Authentication | "JWT (planned)" | Not implemented |
| Country filtering | Column added to schema | DB not rebuilt with full mapping |

### 5.2 Dead or Misleading Code Paths

| Path | Issue | Evidence |
|------|-------|----------|
| `app/ui_chat/` | Directory exists but incomplete | Only 1 file observed |
| `scripts/marc/m3_query.py` | 16KB file, appears superseded | `db_adapter.py` handles queries |
| `FilterField.AGENT` | Marked "Legacy - kept for backward compatibility" | `query_plan.py:21` |

### 5.3 Intent vs Reality Mismatches

| Intent (plan.mf) | Reality |
|------------------|---------|
| "Backend Complete (M1-M4)" | 21 tests failing |
| "All backend components tested and audited" | Test suite has regressions |
| "2,796 records indexed" | Country codes partially mapped |

---

## 6. Tactical Fixes (Low Effort, High Impact)

### Fix 1: Separate FTS5 and EQUALS Normalization

**Location:** `scripts/query/db_adapter.py:58-67`

**Change:**
```python
elif field == FilterField.TITLE or field == FilterField.SUBJECT:
    value = raw_value.lower()
    # Only wrap in quotes for FTS5 CONTAINS, not EQUALS
    # This function is called for both, so we need operation context
    return value  # Let caller handle FTS5 quoting
```

**Verification:** `pytest tests/scripts/query/test_db_adapter.py -v`

### Fix 2: Expand Country Code Mapping

**Location:** `data/normalization/marc_country_codes.json`

**Change:** Add missing codes from https://www.loc.gov/marc/countries/countries_code.html

**Verification:**
```python
# After rebuild:
SELECT country_code, country_name FROM imprints WHERE country_name IS NULL;
# Should return 0 rows
```

### Fix 3: Replace utcnow() with timezone-aware

**Location:** `scripts/chat/session_store.py`

**Change:**
```python
# Before:
datetime.utcnow().isoformat()
# After:
datetime.now(timezone.utc).isoformat()
```

**Verification:** `pytest tests/ -W error::DeprecationWarning`

### Fix 4: Add Missing Test for is_overview_query

**Location:** `tests/scripts/chat/test_aggregation.py` (create)

**Change:**
```python
def test_is_overview_query_returns_true_for_generic():
    assert is_overview_query("tell me about the collection") == True

def test_is_overview_query_returns_false_for_specific():
    assert is_overview_query("Hebrew books from Venice") == False
```

**Verification:** `pytest tests/scripts/chat/test_aggregation.py -v`

---

## 7. Strategic Recommendations

### Recommendation 1: Fix Test Suite Before Adding Features

**Rationale:** 21 failing tests mask future regressions.

**Action:**
1. Fix FTS5 quoting issue (root cause of ~15 failures)
2. Update test expectations OR fix code behavior
3. Target: 0 failing tests

**Success Metric:** `pytest tests/ -q` shows all tests passing.

### Recommendation 2: Rebuild Database with Full Country Mapping

**Rationale:** Country filtering feature incomplete without data.

**Action:**
1. Expand `marc_country_codes.json` to 100+ codes
2. Rerun indexing pipeline: `python -m app.cli index data/m2/`
3. Verify: `SELECT COUNT(*) FROM imprints WHERE country_name IS NULL` = 0

**Success Metric:** Country queries return expected results.

### Recommendation 3: Add Operation Context to normalize_filter_value

**Rationale:** Single function handles both EQUALS and CONTAINS but FTS5 quoting only needed for CONTAINS.

**Action:**
1. Add `op: FilterOp` parameter to `normalize_filter_value()`
2. Only apply FTS5 quoting when `op == FilterOp.CONTAINS`
3. Update all call sites

**Success Metric:** Title/Subject EQUALS queries work correctly.

### Recommendation 4: Add Integration Test for Full Query Path

**Rationale:** Unit tests pass but system integration untested.

**Action:**
1. Create test that:
   - Starts API server
   - Sends query via `/chat`
   - Verifies response structure
   - Checks evidence presence
2. Run with `pytest --run-integration`

**Success Metric:** Full path test passes without mocking.

---

## 8. Final Verdict

### System Classification

The system is primarily a **Conversational Search Engine** with:
- Strong bibliographic data pipeline (M1-M3)
- LLM-powered query understanding (M4)
- Two-phase conversation architecture (M6 API)
- Evidence-based provenance tracking

It is NOT:
- A general RAG system (no embeddings, no retrieval-augmented generation)
- A pure data pipeline (has interactive query capabilities)
- A chatbot with free-form generation (responses grounded in database evidence)

### Recommended Next Milestone

**Fix Test Suite and Rebuild Database**

**Why:** The system has solid architecture but is in a degraded state:
- 21 failing tests create uncertainty about correctness
- Country filtering feature is incomplete
- These are low-effort fixes that restore baseline quality

**Concrete Steps:**
1. Fix `normalize_filter_value()` to separate EQUALS/CONTAINS paths (2 hours)
2. Run test suite to identify remaining failures (30 min)
3. Expand country code mapping and rebuild DB (1 hour)
4. Verify all tests pass (30 min)

**After This:** Proceed to web UI implementation with confidence in backend stability.

---

## Appendix A: Test Failure Summary

```
21 failed, 328 passed, 211 warnings

Failures by category:
- FTS5 quoting issues: 15 tests
- Missing API key handling: 2 tests
- Relator code mapping: 1 test
- Schema mismatch: 3 tests
```

## Appendix B: LLM Call Points

| File | Line | Function | Cache |
|------|------|----------|-------|
| `llm_compiler.py` | 229 | `call_model()` | `query_plan_cache.jsonl` |
| `llm_compiler.py` | 307 | `compile_query_with_subject_hints()` | No cache |
| `intent_agent.py` | ~300 | `interpret_query()` | `intent_cache.jsonl` |
| `exploration_agent.py` | ~200 | `interpret_exploration_request()` | Unknown |

## Appendix C: Database Schema Summary

```
Tables (19 total):
- records (2,796 rows)
- titles, titles_fts, titles_fts_*
- subjects, subjects_fts, subjects_fts_*
- agents
- imprints (with country_code, country_name)
- languages
- notes
- physical_descriptions
```
