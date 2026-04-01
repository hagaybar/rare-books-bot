# Project Audit Report: Rare Books Bot
**Date**: 2026-03-22
**Focus**: Full project status review and next-step identification

---

## Inferred Project Model

### Core Responsibilities
1. **MARC XML Ingestion** - Parse bibliographic MARC XML into structured canonical records
2. **Deterministic Normalization** - Dates, places, publishers, agents with confidence scoring and raw preservation
3. **Fielded Query Pipeline** - Natural language → QueryPlan (LLM) → SQL → CandidateSet + Evidence
4. **Conversational API** - HTTP + WebSocket chatbot with session management, clarification, streaming
5. **Metadata Quality Workbench** - Agent-driven HITL system for coverage improvement (place/date/publisher/name)
6. **Publisher Authority System** - Canonical publisher identity management with variant matching

### Primary Workflows
- **Ingestion**: MARC XML → M1 CanonicalRecord → M2 Normalization → M3 SQLite Index
- **Query**: NL Query → LLM Compile → SQL Execute → CandidateSet + Evidence → Formatted Response
- **Metadata Improvement**: Coverage Audit → Gap Detection → Agent-Assisted Proposals → Human Review → Feedback Loop

### Key Non-Goals
- No embedding-based retrieval (SQLite fielded queries first)
- No general-purpose RAG
- LLM is planner/explainer, not authority

---

## Architecture Map

```
                    MARC XML files
                         │
                    ┌────┴────┐
                    │ M1 Parse │  scripts/marc/parse.py + models.py
                    └────┬────┘
                         │ CanonicalRecord JSONL
                    ┌────┴────────┐
                    │ M2 Normalize │  scripts/marc/m2_normalize.py
                    └────┬────────┘
                         │ NormalizedRecord JSONL
                    ┌────┴──────┐
                    │ M3 Index   │  scripts/marc/m3_index.py
                    └────┬──────┘
                         │ bibliographic.db (SQLite)
                ┌────────┼────────────┐
                │        │            │
        ┌───────┴──┐  ┌──┴──────┐  ┌──┴──────────┐
        │ M4 Query  │  │ M6 Chat │  │ M7 Metadata  │
        │ Pipeline  │  │ API     │  │ Workbench    │
        └───────┬──┘  └──┬──────┘  └──┬──────────┘
                │        │            │
                └────────┴────────────┘
                         │
                    React Frontend (M7)
                    Streamlit QA UI (M4)
```

### Data Store Summary
| Artifact | Location | Records |
|----------|----------|---------|
| Canonical JSONL | `data/canonical/records.jsonl` | 2,796 |
| SQLite Index | `data/index/bibliographic.db` | 2,796 records, 2,773 imprints |
| QA Database | `data/qa/qa.db` | Gold sets for regression |
| Sessions DB | `data/chat/sessions.db` | Conversation state |
| Place Aliases | `data/normalization/place_aliases/place_alias_map.json` | 196 mappings |
| Publisher Authorities | In bibliographic.db | 228 authorities, 266 variants |

---

## Milestone Status

| Milestone | Status | Coverage/Quality |
|-----------|--------|------------------|
| **M1** MARC Parse | **Complete** | 2,796 records, deterministic, fully tested |
| **M2** Normalization | **Complete** | Place: 99.3% high-conf, Publisher: 98.8%, Date: 68.2% |
| **M3** SQLite Index | **Complete** | Full schema with FTS5, provenance tracking |
| **M4** Query Pipeline | **Complete** | LLM compile + SQL execute + evidence extraction |
| **M5** Enrichment | **Complete** | NLI + Wikidata + VIAF with caching |
| **M6** Chatbot API | **Complete** | HTTP + WebSocket, sessions, clarification |
| **M7** Metadata Workbench | **Complete** | 4 specialist agents, React frontend, feedback loop |

**All 7 milestones are implemented.**

### Normalization Confidence Breakdown (2,773 imprints)
| Field | High (>=0.90) | Low (<0.90) | % High |
|-------|---------------|-------------|--------|
| Place | 2,754 | 0 | **99.3%** |
| Publisher | 2,740 | 33 | **98.8%** |
| Date | 1,892 | 881 | **68.2%** |

Date normalization is the weakest area. 881 imprints (31.8%) have date confidence below 0.90.

---

## Alignment Analysis

| Responsibility | Alignment | Notes |
|----------------|-----------|-------|
| MARC XML is source of truth | **Aligned** | Raw values always preserved alongside normalized |
| QueryPlan → CandidateSet → Evidence | **Partially Aligned** | Pipeline works but Evidence completeness not enforced |
| Deterministic outputs | **Aligned** | All normalization is rule-based with method tags |
| Reversible normalization | **Aligned** | Raw + norm + method + confidence stored |
| No narrative before CandidateSet | **Partially Aligned** | Chat layer can return clarification before execution |
| LLM as planner only | **Aligned** | LLM compiles queries; structured output validated |

---

## Contract & Boundary Analysis

| Boundary | Enforcement | Risk |
|----------|-------------|------|
| QueryPlan schema | **Schema-enforced** (Pydantic + OpenAI Responses API) | Low |
| Filter validation | **Schema-enforced** (model_validator) | Low |
| CandidateSet schema | **Type hints only** | **High** - incomplete evidence not caught |
| Evidence completeness | **None** | **High** - extraction failures silently swallowed |
| M3 schema constants | **Convention only** (m3_contract.py) | Medium - silent breakage if schema drifts |
| Answer Contract | **Documentation only** | High - not code-enforced |
| Chat response model | **Schema-enforced** (Pydantic) | Low |

### Critical Gap: Evidence Extraction Failures
In `scripts/query/execute.py`, evidence extraction wraps errors in a `print()` statement rather than raising. This means a query can return candidates with missing or incomplete evidence, violating the Answer Contract.

---

## Code Health & Structural Risk

### Test Suite
- **1,076 tests collected**, 1,063 passing, **13 failing**
- **Pass rate: 98.8%**

### Failing Tests (3 Root Causes)

| Group | Count | Root Cause | Severity |
|-------|-------|------------|----------|
| `TestGetIssues` (metadata API) | 11 | Test fixture missing `record_id` column; schema mismatch with implementation | **P1** - Tests broken, not production |
| `test_mixed_latin_majority` (clustering) | 1 | `detect_script()` tie-breaking prefers Hebrew even when Latin dominates | **P2** - Logic bug |
| `test_subject_contains` (db_adapter) | 1 | FTS5 subjects table incorrectly added to outer JOIN set | **P2** - Correctness |

### Lint Issues
- **590 ruff errors** (176 auto-fixable)
- Mostly unused imports and unused variables
- No security-critical findings

### Deprecation Warnings
1. **FastAPI `on_event`** - Should migrate to lifespan event handlers (`app/api/main.py:260`)
2. **Pydantic class-based `Config`** - Should migrate to `ConfigDict` (`scripts/marc/models.py:86,232`)

### Large Files (Complexity Risk)
| File | Lines | Risk |
|------|-------|------|
| `app/api/metadata.py` | 1,484 | High - monolithic endpoint file |
| `app/api/main.py` | 1,288 | High - monolithic API file |
| `scripts/marc/parse.py` | 869 | Medium - complex but stable |
| `scripts/marc/m3_index.py` | 670 | Medium - index builder |
| `scripts/query/execute.py` | 664 | Medium - query execution |
| `scripts/metadata/agents/name_agent.py` | 600 | Medium - specialist agent |

### Frontend
- React 19 + TypeScript + Vite + Tailwind CSS
- 4 pages: Dashboard, Workbench, AgentChat, Review
- No test suite detected for frontend
- Dependencies are modern and well-chosen

---

## Test & QA Effectiveness

### Strengths
- High test count (1,076) relative to codebase size
- Good coverage of core pipeline (M1-M4)
- Gold set regression framework for query quality
- QA Streamlit tool for manual labeling

### Weaknesses
- **13 failing tests** indicate test maintenance debt
- **No frontend tests**
- **No integration test** that validates the full Answer Contract end-to-end
- Evidence extraction failures are not tested (silent failure path)

---

## Key Findings Summary

### P0 (Correctness / Data Integrity)
None identified. Core pipeline is sound.

### P1 (Architectural / Blocking)
1. **FINDING-01**: 11 metadata API tests failing due to schema mismatch in test fixtures
2. **FINDING-02**: Evidence extraction failures silently swallowed - violates Answer Contract
3. **FINDING-03**: Date normalization at 68.2% high-confidence (881 imprints below threshold)

### P2 (Maintainability / Quality)
4. **FINDING-04**: 590 ruff lint errors (code hygiene debt)
5. **FINDING-05**: `detect_script()` logic bug - Hebrew preferred over dominant Latin
6. **FINDING-06**: FTS5 subject query adds unnecessary JOIN
7. **FINDING-07**: `app/api/metadata.py` (1,484 lines) and `app/api/main.py` (1,288 lines) are oversized
8. **FINDING-08**: Pydantic v1-style `Config` classes need migration to `ConfigDict`
9. **FINDING-09**: FastAPI `on_event` deprecation - migrate to lifespan handlers

### P3 (Clarity / Ergonomics)
10. **FINDING-10**: No frontend test coverage
11. **FINDING-11**: CandidateSet model lacks validators for evidence completeness

---

## Recommendations for Next Steps

### Immediate (Fix Broken State)
1. **Fix 13 failing tests** - align test fixtures with implementation schema, fix `detect_script()` logic, fix FTS5 JOIN tracking
2. **Run `ruff check --fix .`** to auto-fix 176 lint errors; manually address remaining ~414

### Short-Term (Strengthen Contracts)
3. **Add CandidateSet validators** - enforce non-empty evidence list, evidence-filter mapping
4. **Make evidence extraction fail-closed** - raise on extraction failure instead of print()
5. **Add M3 schema runtime validation** - verify DB columns match `m3_contract.py` constants on connection

### Medium-Term (Improve Coverage)
6. **Date normalization improvement** - 881 imprints (31.8%) below 0.90 confidence. This is the biggest metadata quality gap. Consider:
   - Expanding date pattern rules (Hebrew calendar dates, ambiguous ranges)
   - Using DateAgent proposals to create a date alias/correction system
   - Manual review of most frequent unparsed date patterns
7. **Split large API files** - extract `metadata.py` endpoints into route modules

### Longer-Term (Production Readiness)
8. **Frontend testing** - add at least smoke tests for React pages
9. **End-to-end Answer Contract test** - integration test that validates QueryPlan → CandidateSet → Evidence → normalized mapping for known queries
10. **Migrate deprecated APIs** - Pydantic ConfigDict, FastAPI lifespan handlers
