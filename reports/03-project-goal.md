# Project Goal Analysis

**Date:** 2026-03-23
**Scope:** Strategic analysis of project purpose, users, core value, and noise
**Method:** Codebase-first analysis grounded in actual implementation, not aspirational documentation

---

## 1. What the Project Is Fundamentally Trying to Achieve

**Rare Books Bot is a conversational discovery system that lets scholars and librarians query a rare book collection using natural language and receive deterministic, evidence-backed answers traceable to specific MARC XML fields.**

The system solves a real problem: rare book collections are cataloged in MARC XML, a format that is opaque to end users and difficult to query without specialized knowledge of bibliographic standards. The project makes these records discoverable through natural conversation while maintaining the rigor and provenance that bibliographic work demands.

The distinguishing insight is that this is NOT a search engine or a RAG system. It is an **evidence-first query engine with a conversational surface**. The contract is: every answer must show exactly which MARC fields caused each record to appear. This makes it fundamentally different from keyword search (no provenance) and from LLM-based RAG (non-deterministic, hallucinates).

---

## 2. Primary Users

### User 1: Bibliographic Researcher / Scholar (Primary)

The person who types "books printed in Venice in the 16th century" and needs to trust the answer. They care about:
- Complete recall (finding all matching records)
- Evidence (why each record was included)
- Ability to explore a result set (aggregation, drilling down)
- Links back to catalog records (Primo URLs)

The two-phase conversation model (Phase 1: define query, Phase 2: explore corpus) is designed for this user. The confidence threshold (0.85) and clarification flow exist because this user needs to trust that the system understood their intent before showing results.

### User 2: Metadata Librarian / Cataloger (Secondary)

The person who maintains data quality. They care about:
- Normalization coverage (what percentage of records have high-confidence metadata)
- Identifying and fixing low-confidence records
- Building authority files (publisher authorities, place aliases)
- Auditing corrections

This user is served by the Metadata Co-pilot Workbench (React frontend).

### User 3: Developer / QA Tester (Internal)

The person who validates that the query pipeline works correctly. They care about:
- Labeling query results as true/false positives and negatives
- Regression testing against gold sets
- Inspecting query plans and SQL

This user is served by the QA Tool (Streamlit) and CLI.

---

## 3. Most Important Use Cases

### Tier 1: Core Discovery (defines the product)

1. **Natural language bibliographic query** -- "Hebrew books about philosophy printed in Amsterdam before 1700" -- returns a deterministic set of matching records with evidence showing which MARC fields caused inclusion.

2. **Two-phase exploration** -- First define a result set with confidence scoring, then explore it: "how many are in Latin?", "show by century", "top publishers". This is the core workflow that makes the chatbot more than a search box.

3. **Multi-turn refinement** -- Narrow or redirect within a conversation: "now only from Paris", "let me search for something different". Session persistence makes this possible.

### Tier 2: Data Quality (enables Tier 1)

4. **Normalization quality improvement** -- Review low-confidence records, propose corrections via specialist agents, apply fixes to alias maps, and watch coverage scores improve. Without this, queries return incomplete or inaccurate results.

5. **Publisher/place/date authority maintenance** -- Build and maintain the mapping tables that make normalization work. 228 publisher authorities, 196 place aliases, 6 date patterns.

### Tier 3: Pipeline Validation (ensures correctness)

6. **Query pipeline QA** -- Label results, build gold sets, run regression tests. This is infrastructure that prevents quality regressions.

---

## 4. What Must Sit at the Center of the Future Product Experience

**The conversational discovery bot is the center.**

Evidence:
- `plan.mf` explicitly states: "M6 Chatbot -- P0 - HIGHEST - This is the primary user-facing product"
- The entire M1-M4 backend pipeline exists to serve this surface
- The two-phase conversation model (intent interpretation with confidence scoring -> corpus exploration with aggregation) is the most architecturally sophisticated part of the system
- The API layer (`app/api/main.py`, 1,300 lines) is dominated by conversation handling logic: intent agent routing, phase transitions, aggregation, refinement, enrichment integration

The bot should be the unified entry point for researchers. Everything else either feeds data into it (the MARC pipeline, the normalization layer) or maintains the quality of data it uses (the metadata co-pilot).

### What "centerpiece" means concretely

The centerpiece is the **two-phase conversational query engine** consisting of:

1. **Intent Agent** (`scripts/chat/intent_agent.py`) -- Interprets natural language with confidence scoring, decides whether to execute or ask for clarification
2. **Query Pipeline** (`scripts/query/`) -- Compiles QueryPlan via LLM, generates SQL, extracts evidence
3. **Exploration Agent** (`scripts/chat/exploration_agent.py`) -- Classifies follow-up intents (aggregation, refinement, comparison, enrichment, new query)
4. **Aggregation Engine** (`scripts/chat/aggregation.py`) -- Deterministic SQL aggregations over result sets
5. **Session Management** (`scripts/chat/session_store.py`) -- Multi-turn state with phase tracking and active subgroup persistence
6. **FastAPI endpoints** (`app/api/main.py`) -- `/chat` with two-phase routing, `/ws/chat` for streaming

This is approximately 5,000+ lines of well-structured Python implementing a genuine conversational research assistant, not just a chatbot wrapper around search.

---

## 5. Secondary Capabilities

### 5A. Metadata Co-pilot Workbench (React Frontend)

**Role:** Data quality administration tool
**Relationship to center:** It improves the data that the bot queries. Higher normalization confidence means better query recall and precision.
**Status:** The most polished UI in the project (high UX, high maintainability, high architectural coherence per report 02).
**Strategic note:** This is genuinely valuable but serves a different persona (cataloger vs. researcher). It should remain a separate tool, not be merged into the chatbot.

### 5B. QA Tool (Streamlit)

**Role:** Pipeline validation and regression testing
**Relationship to center:** It validates that the query engine produces correct results.
**Status:** Medium quality, development-only, appropriate for its purpose.
**Strategic note:** Should remain a development tool. Its key value is the gold set / regression testing loop, which should eventually run in CI, not in a UI.

### 5C. Enrichment Pipeline

**Role:** External data augmentation (Wikidata, NLI authorities)
**Relationship to center:** It enriches agent and entity data that the bot can surface during corpus exploration.
**Status:** Infrastructure is built (Wikidata SPARQL, NLI client, caching), but not deeply integrated into the conversational flow yet. The exploration agent has an `ENRICHMENT_REQUEST` intent type but the implementation is minimal.
**Strategic note:** This is a future differentiator. When a user asks "tell me about this printer," being able to pull birth/death dates and biographical info from Wikidata makes the bot significantly more useful.

### 5D. CLI

**Role:** Developer/testing interface
**Relationship to center:** Provides direct access to the M1-M4 pipeline without the API layer.
**Status:** Small (520 lines), focused, appropriate.
**Strategic note:** Keep as a development tool.

---

## 6. Historical Noise and Accidental Complexity

### 6A. RAG Template Remnants

The project was scaffolded from a "MultiSourceRAG" platform template. Surviving artifacts:

- `configs/chunk_rules.yaml` -- Chunking rules for email (eml, msg, mbox) formats. Completely irrelevant to MARC bibliographic records. This file defines strategies for email block chunking with min/max tokens and overlap -- concepts from document RAG that do not apply here.
- `configs/outlook_helper.yaml` -- Windows COM server configuration for Outlook email processing. References `C:/MultiSourceRAG/tools/win_com_server.py` and pywin32. Has nothing to do with rare books.
- `configs/outlook_helper.yaml.template` -- Template version of the above.
- `scripts/api_clients/openai/completer.py` -- Generic OpenAI completion wrapper from the template. The project uses OpenAI's Responses API directly through intent_agent.py and llm_compiler.py, making this wrapper orphaned.
- `scripts/utils/task_paths.py`, `scripts/utils/config_loader.py` -- Generic utilities from the template. TaskPaths handles per-run artifact paths (still referenced but could be simplified). ConfigLoader may be vestigial.
- CLAUDE.md references "ProjectManager" in `scripts/core/project_manager.py` but this file does not exist. This is a ghost reference from the template.

### 6B. Dual Primo URL Configuration

The Chat UI generates Primo URLs for Tel Aviv University (`tau.primo.exlibrisgroup.com`), while the Metadata Workbench generates them for the National Library of Israel (`primo.nli.org.il`). This is not noise per se, but it is an unresolved configuration issue that signals the system serves a specific institutional collection (likely Tel Aviv University's rare books) but has not cleanly externalized this institutional binding.

### 6C. Duplicate Regression Runner

The gold set regression test exists in three places:
1. `app/qa.py` -- CLI regression runner (canonical)
2. QA Tool gold set page -- Streamlit UI wrapper
3. Inline in `plan.mf` documentation

The QA Tool version duplicates the CLI version's logic.

### 6D. Archive Directory

`archive/` exists but is empty. CLAUDE.md mentions it should contain "Reference materials and documentation from the RAG template (kept for reference only, not active code)" but it has been cleaned out.

### 6E. Documentation Sprawl

The project has accumulated planning documents that are no longer actionable:
- `TODO_CONVERSATIONAL_AGENT.md` -- Stage 1-4 implementation checklist, all marked complete. This is a completed TODO list.
- `docs/salvaged_disscussion.txt` -- Preserved discussion, unclear origin.
- `project_basseline.txt` -- Misspelled baseline file at project root.

---

## 7. Code Size Summary (Implementation Weight)

| Component | Lines of Python/TS | Role |
|-----------|-------------------|------|
| MARC Pipeline (scripts/marc/) | ~4,200 | Data foundation |
| Query Pipeline (scripts/query/) | ~2,350 | Core engine |
| Chat/Conversation (scripts/chat/) | ~3,400 | Conversational layer |
| Enrichment (scripts/enrichment/) | ~2,270 | External data |
| Metadata Admin (scripts/metadata/) | ~3,900 | Data quality |
| API Layer (app/api/) | ~3,220 | HTTP/WS interface |
| React Frontend (frontend/src/) | ~3,160 (TS) | Metadata UI |
| Chat UI (app/ui_chat/) | ~450 | Discovery UI |
| QA Tool (app/ui_qa/) | ~3,530 | Dev/QA UI |
| CLI (app/cli.py) | ~520 | Dev interface |
| Tests | ~52 files | Validation |
| **Total active code** | **~27,000+** | |

The largest code investment is in the backend pipeline + conversation engine (~13,000+ lines across marc, query, chat, and API). This is appropriate -- the backend is the product's brain.

---

## 8. Strategic Assessment

### What is working

1. The M1-M4 pipeline is mature, well-tested, and production-ready. It is the strongest part of the codebase.
2. The two-phase conversation model is architecturally sound and genuinely novel for bibliographic systems.
3. The metadata co-pilot provides a real HITL workflow for data quality improvement.
4. The normalization pipeline achieves high coverage (99.3% places, 98.8% publishers).
5. Evidence-based answers with MARC field provenance is a genuine differentiator.

### What needs attention

1. The **chat UI is a thin Streamlit wrapper** (~450 lines) while the conversational backend is sophisticated (~6,600+ lines across chat + API). The frontend does not surface the backend's full capabilities (no streaming, no aggregation visualization, no exploration phase UI, no enrichment display).
2. **Two separate institutional Primo URLs** suggest the system's institutional binding is not cleanly configured.
3. **RAG template artifacts** should be cleaned up -- they create confusion about what the project actually is.
4. **The enrichment pipeline** is built but underutilized in the conversational flow.

### The fundamental tension

The project has invested heavily in two parallel tracks:
- **Track A:** Conversational discovery for researchers (the bot)
- **Track B:** Metadata quality tooling for catalogers (the workbench)

These tracks share the same database and normalization infrastructure but serve different users through different UIs with different architectures (React vs. Streamlit). This is not necessarily a problem -- they are genuinely different products for different users -- but the project documentation sometimes conflates them, and the chat UI (Track A) is significantly less mature than the workbench (Track B).

The strategic priority should be clear: **the bot is the product, the workbench is the tool that maintains the data the product uses.**

---

## 9. JSON Summary

```json
{
  "projectGoal": "Enable scholars and librarians to discover rare books through natural language conversation, backed by a deterministic, evidence-based query engine over MARC XML bibliographic records with full provenance tracking.",
  "primaryUsers": [
    "Bibliographic researchers and scholars who need to query rare book collections in natural language and trust the results",
    "Metadata librarians who maintain normalization quality and authority records",
    "Developers who validate query pipeline correctness"
  ],
  "coreUseCases": [
    "Natural language bibliographic query with evidence-based results traceable to MARC fields",
    "Two-phase conversational exploration: define a result set with confidence scoring, then aggregate and analyze it",
    "Multi-turn refinement and follow-up within a session",
    "Normalization quality improvement via HITL metadata co-pilot",
    "Query pipeline regression testing via gold sets"
  ],
  "centerpiece": "The two-phase conversational query engine: intent interpretation with confidence scoring (Phase 1) -> corpus exploration with aggregation, refinement, and enrichment (Phase 2), delivered through the FastAPI backend and surfaced via the chatbot UI",
  "secondary": [
    "Metadata Co-pilot Workbench (React) -- data quality administration for catalogers",
    "QA Tool (Streamlit) -- query pipeline validation and regression testing",
    "Enrichment pipeline (Wikidata/NLI) -- external data augmentation, partially integrated",
    "CLI -- developer access to the M1-M4 pipeline",
    "Publisher authority record system -- canonical publisher identification"
  ],
  "noise": [
    "configs/chunk_rules.yaml -- RAG template email chunking rules, irrelevant to MARC",
    "configs/outlook_helper.yaml -- Windows COM server for Outlook, from RAG template",
    "scripts/api_clients/openai/completer.py -- orphaned generic OpenAI wrapper from template",
    "Ghost reference to ProjectManager in scripts/core/ (file does not exist)",
    "TODO_CONVERSATIONAL_AGENT.md -- completed TODO list with no remaining action items",
    "project_basseline.txt -- misspelled baseline file at project root",
    "docs/salvaged_disscussion.txt -- preserved discussion of unclear origin",
    "Duplicate regression runner logic in QA Tool gold set page (duplicates app/qa.py)",
    "Empty archive/ directory"
  ]
}
```
