# Architecture
> Last verified: 2026-04-12
> Source of truth for: Project structure, core modules, data model index, and key architectural patterns

## Project Structure

```
app/                          # CLI interface (Typer) and FastAPI backend
  api/                        # FastAPI endpoints
    main.py                   # Core app: /chat, /chat/compare, /chat/history, /health, /sessions, WebSocket
    compare.py                # Model A/B comparison endpoint
    metadata.py               # Metadata workbench endpoints (12 routes)
    diagnostics.py            # QA/diagnostics endpoints
    models.py                 # API request/response models
    auth_models.py            # Authentication models
    metadata_models.py        # Metadata quality models (25 Pydantic models)
  cli.py                      # Typer CLI: parse, index, query, regression, chat-*

scripts/                      # Core library organized by function
  marc/                       # MARC XML parsing and normalization
    models.py                 # M1 canonical record models
    m2_models.py              # M2 normalization models
    normalize.py              # Date, place, publisher normalization
    m2_normalize.py           # M1->M2 enrichment CLI
  chat/                       # Chatbot session and scholar pipeline
    models.py                 # ChatSession, Message, ChatResponse
    session_store.py          # SQLite session persistence
    interpreter.py            # NL query → InterpretationPlan (via litellm)
    executor.py               # InterpretationPlan → ExecutionResult (SQL)
    narrator.py               # ExecutionResult → narrative response (via litellm)
    plan_models.py            # Execution pipeline models (28 models)
  query/                      # Query compilation and execution
    llm_compiler.py           # NL -> QueryPlan via litellm (legacy; see chat/interpreter.py)
    compile.py                # Query compilation entry point
    models.py                 # QueryResult, FacetCounts, QueryOptions
  schemas/                    # Shared Pydantic schemas
    query_plan.py             # QueryPlan, Filter, FilterField, FilterOp
    candidate_set.py          # CandidateSet, Candidate, Evidence
  metadata/                   # Metadata workbench agents and tools
    audit.py                  # Coverage audit
    clustering.py             # Gap clustering
    agent_harness.py          # Grounding + Reasoning layers
    feedback_loop.py          # Correction application
    review_log.py             # JSONL audit trail
    agents/                   # 4 specialist agents
  enrichment/                 # Wikidata/Wikipedia enrichment
    models.py                 # Enrichment data models
  normalization/              # Alias map generation
    generate_place_alias_map.py
  qa/                         # QA database operations
    db.py
  core/                       # Project management
    project_manager.py        # Config, paths, logging
  utils/                      # Utilities
    task_paths.py             # Per-run artifact paths
    logger.py                 # Structured JSON logging
  shared_models.py            # Cross-module models (ExternalLink)
  models/                     # LLM model configuration
    config.py                 # JSON-driven model selection per pipeline stage
    llm_client.py             # Thin litellm wrapper for structured/streaming completions
  eval/                       # Batch evaluation framework
    run_eval.py               # CLI entry point for model comparison runs
    judge.py                  # Response quality judging
    query_set.py              # Benchmark query loading
    report.py                 # Evaluation report generation

frontend/                     # Unified React SPA
  src/
    pages/                    # 9 screens across 4 tiers
      Chat.tsx                # Primary: conversational query
      Coverage.tsx            # Operator: metadata coverage dashboard
      Workbench.tsx           # Operator: metadata correction workbench
      AgentChat.tsx           # Operator: specialist agent conversations
      Review.tsx              # Operator: correction history
      QueryDebugger.tsx       # Diagnostics: QA query testing
      DbExplorer.tsx          # Diagnostics: table browser
      Publishers.tsx          # Diagnostics: publisher authorities
      Health.tsx              # Admin: system health
    api/                      # Fetch functions for all API endpoints
    hooks/                    # TanStack Query hooks with caching
    types/                    # TypeScript interfaces
    components/               # Shared UI components

tests/                        # Pytest suite
  scripts/                    # Unit tests per module
    marc/
    metadata/
    chat/
    query/
  app/                        # API endpoint tests
  integration/                # End-to-end tests

data/                         # Runtime data (mostly gitignored)
  marc_source/                # Raw MARC XML files (tracked in git)
  canonical/                  # Canonical JSONL (one record per line)
  index/                      # SQLite database (bibliographic.db)
  m2/                         # M2-enriched JSONL
  normalization/              # Alias maps (place_alias_map.json tracked)
  chat/                       # Session database
  qa/                         # QA database and gold sets
  runs/<run_id>/              # Per-run artifacts: plan, SQL, candidate set, logs
  eval/                       # Model config, benchmark queries, evaluation runs

archive/                      # Reference materials (retired UIs, template docs)
```

### Frontend Tiers

| Tier | Screens | Audience |
|------|---------|----------|
| **Primary** | Chat | End users |
| **Operator** | Coverage, Workbench, Agent Chat, Review | Librarians |
| **Diagnostics** | Query Debugger, DB Explorer, Publishers | Developers/QA |
| **Admin** | Health | System administrators |

---

## Core Modules

### ProjectManager (`scripts/core/project_manager.py`)

Central class for managing project configuration, paths, and logging. Provides:
- Project root path resolution
- Configuration loading
- Logging setup

### TaskPaths (`scripts/utils/task_paths.py`)

Handles per-run artifact paths. Each run gets a unique directory under `data/runs/<run_id>/` containing:
- Query plan JSON
- SQL query text
- Candidate set results
- Execution logs

### LoggerManager (`scripts/utils/logger.py`)

Structured JSON logging per project/task/run. Supports:
- Per-task log files
- Structured fields for debugging
- Configurable log levels

### Modular Design

Each component (ingestion, normalization, query, metadata) has a base interface and pluggable implementations. Key design patterns:
- **Composition over inheritance**
- **Dependency injection** for testability
- **Single-purpose functions** (<50 lines, one responsibility)
- **Deterministic outputs** for all non-LLM operations

---

## Pydantic Model Index

The project uses 123 Pydantic models (7 Enums + 116 BaseModels) across 12 files. This section provides a complete reference.

### Cross-Module (`scripts/shared_models.py`)

| Model | Description |
|-------|-------------|
| `ExternalLink` | Unified external reference link (Primo, Wikipedia, Wikidata, VIAF, NLI, ISNI, LoC) |

### Chat Domain (`scripts/chat/models.py`, `scripts/chat/plan_models.py`)

**Session and Messages** (11 models):

| Model | Description |
|-------|-------------|
| `ConversationPhase` | Enum: QUERY_DEFINITION or CORPUS_EXPLORATION |
| `ExplorationIntent` | Enum: 9 intent values (METADATA_QUESTION, AGGREGATION, etc.) |
| `ActiveSubgroup` | Currently defined CandidateSet being explored |
| `UserGoal` | Elicited user goal for corpus exploration |
| `Message` | Single conversation message with role, content, optional QueryPlan/CandidateSet |
| `ChatSession` | Conversation session with message history and context |
| `ChatResponse` | Response: message, candidate_set, followups, clarification, phase, confidence |
| `Connection` | Relationship between two agents with evidence and confidence |
| `AgentNode` | Node in agent relationship graph |
| `ComparisonFacets` | Multi-faceted comparison data |
| `ComparisonResult` | Result of comparing field values |

**Execution Pipeline** (27 models):

Step actions: `RESOLVE_AGENT`, `RESOLVE_PUBLISHER`, `RETRIEVE`, `AGGREGATE`, `FIND_CONNECTIONS`, `ENRICH`, `SAMPLE`

Key models: `ExecutionStep`, `InterpretationPlan`, `StepResult`, `RecordSummary`, `GroundingData`, `ExecutionResult`, `ScholarResponse`

LLM-facing variants: `ExecutionStepLLM`, `ScholarlyDirectiveLLM`, `InterpretationPlanLLM` (simplified for litellm structured output compatibility)

### Query Domain (`scripts/schemas/`, `scripts/query/models.py`)

| Model | Description |
|-------|-------------|
| `FilterField` | Enum: 12 supported filter fields |
| `FilterOp` | Enum: EQUALS, CONTAINS, RANGE, IN |
| `Filter` | Single filter condition |
| `QueryPlan` | Structured query plan (intermediate NL-to-SQL representation) |
| `Evidence` | Why a record matched |
| `Candidate` | Single matched record with evidence |
| `CandidateSet` | Complete query result |
| `QueryWarning` | Warning from execution |
| `FacetCounts` | Facet aggregations |
| `QueryOptions` | Execution options |
| `QueryResult` | Unified execution result |

### MARC Domain (`scripts/marc/models.py`, `scripts/marc/m2_models.py`)

**M1 Canonical Records** (8 models):

| Model | Description |
|-------|-------------|
| `SourcedValue` | Value with MARC source provenance |
| `ImprintData` | Raw imprint from MARC 260/264 |
| `AgentData` | Author/contributor with authority URI |
| `SubjectData` | Subject heading with scheme and authority |
| `NoteData` | Note with explicit MARC tag |
| `SourceMetadata` | Record-level source info |
| `CanonicalRecord` | Full canonical bibliographic record |
| `ExtractionReport` | MARC extraction summary |

**M2 Normalization** (7 models):

| Model | Description |
|-------|-------------|
| `DateNormalization` | Normalized date: start/end year, confidence, method |
| `PlaceNormalization` | Normalized place: canonical key, confidence, method |
| `PublisherNormalization` | Normalized publisher: canonical key, confidence, method |
| `ImprintNormalization` | Combines date/place/publisher normalization |
| `AgentNormalization` | Normalized agent name |
| `RoleNormalization` | Normalized role |
| `M2Enrichment` | M2 enrichment container |

### Enrichment Domain (`scripts/enrichment/models.py`)

9 models: `EntityType`, `EnrichmentSource`, `ExternalIdentifier`, `EnrichmentRequest`, `PersonInfo`, `PlaceInfo`, `EnrichmentResult`, `NLIAuthorityIdentifiers`, `CacheEntry`

### API Layer (`app/api/`)

**Core** (9 models): `ChatRequest`, `ChatResponseAPI`, `HealthResponse`, `HealthExtendedResponse`, `ModelPair`, `CompareRequest`, `ComparisonMetrics`, `ComparisonResult`, `CompareResponse`

**Authentication** (6 models): `LoginRequest`, `TokenResponse`, `UserInfo`, `CreateUserRequest`, `UpdateUserRequest`, `UserListItem`

**Metadata Quality** (33 models): Coverage, issues, unmapped values, clusters, corrections, Primo URLs, agent chat, publisher authorities.

### File Summary

| File | BaseModels | Enums | Total |
|------|-----------|-------|-------|
| `scripts/shared_models.py` | 1 | 0 | 1 |
| `scripts/chat/models.py` | 9 | 2 | 11 |
| `scripts/chat/plan_models.py` | 27 | 1 | 28 |
| `scripts/schemas/query_plan.py` | 2 | 2 | 4 |
| `scripts/schemas/candidate_set.py` | 3 | 0 | 3 |
| `scripts/enrichment/models.py` | 7 | 2 | 9 |
| `scripts/marc/models.py` | 8 | 0 | 8 |
| `scripts/marc/m2_models.py` | 7 | 0 | 7 |
| `scripts/query/models.py` | 4 | 0 | 4 |
| `app/api/models.py` | 9 | 0 | 9 |
| `app/api/auth_models.py` | 6 | 0 | 6 |
| `app/api/metadata_models.py` | 33 | 0 | 33 |
| **Total** | **116** | **7** | **123** |

---

## Model Configuration

The model config system decouples LLM model selection from pipeline code, allowing per-stage model assignment and batch evaluation.

| File | Purpose |
|------|---------|
| `scripts/models/config.py` | JSON-driven model selection per pipeline stage (interpreter, narrator, etc.) |
| `scripts/models/llm_client.py` | Thin litellm wrapper for structured and streaming completions |
| `data/eval/model-config.json` | Active model configuration (maps stage names to model IDs) |

The evaluation framework (`scripts/eval/`) supports batch comparison of models across pipeline stages using benchmark queries from `data/eval/queries.json`.

---

## Key Architectural Decisions

### What's Different from a General RAG Platform

This is **not** a general RAG platform. Key differences:

- Source of truth is **MARC XML**, not arbitrary documents
- No embedding-based retrieval -- use SQLite fielded queries first
- Answers require **deterministic evidence** from MARC fields
- Normalization must be **reversible** and **confident**
- Query execution must produce **CandidateSet before narrative**

### Data Model Rules

- **Preserve raw MARC values always** -- no destructive normalization
- Normalized fields must be **reversible**: store raw alongside normalized
- If uncertain: store `null`/range + **explicit reason**; never invent data

### Pipeline Stages

```
MARC XML -> M1 (CanonicalRecord JSONL)
         -> M2 (+ normalized fields)
         -> M3 (SQLite index)
         -> M4 (QueryPlan compilation)
         -> M5 (CandidateSet + Evidence)
```

Each stage has clear input/output contracts and is independently testable.
