# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tool Safety & Bounded Output

1. When inspecting files, never read large files in full. Always use bounded operations:
2. search first (rg/grep), then view small excerpts (offset/limit, sed -n, head, tail).
3. Any command that may return large output must include a hard cap (e.g., | head -n 50).
4. If a tool returns an error about size/limits, do not retry the same approach. Switch strategy (search → narrow excerpt → proceed).

## Project Mission

Build a bibliographic discovery system for rare books where **MARC XML is the source of truth**.

**Primary success criterion**: Given an inventory query, deterministically produce the correct CandidateSet (record IDs) with evidence showing which MARC fields/values caused inclusion.

## Answer Contract (Non-Negotiable)

Every response—even internal ones—must be grounded in:
1. **QueryPlan** (structured JSON)
2. **CandidateSet** (record IDs that match)
3. **Evidence** (which MARC fields/subfields caused inclusion)
4. **Normalized mapping** (raw → normalized) with confidence scores

**No narrative or interpretation is allowed before CandidateSet exists.**

## Development Priorities (POC)

1. Parse MARC XML → CanonicalRecord JSONL (raw values always preserved)
2. Build SQLite index for fielded queries (not embeddings-first)
3. Implement normalization v1:
   - Dates → `date_start`/`date_end` (+ normalization method, confidence)
   - Place/publisher/agent string normalization (rule-based, reversible)
4. Implement QueryPlan compiler:
   - Natural language query → JSON plan (LLM-assisted is acceptable)
   - Plan → SQL → CandidateSet + explain output
5. "Complex questions" run ONLY over CandidateSet + evidence
   - Web enrichment is optional; must be cached with citations + confidence

## Data Model Rules

- **Preserve raw MARC values always** (no destructive normalization)
- Normalized fields must be **reversible**: store raw alongside normalized
- If uncertain: store `null`/range + **explicit reason**; never invent data

## Data Normalization Pipeline

The M2 normalization layer enriches M1 canonical records with normalized fields for querying and analysis:

### Place Normalization
- **Input:** Raw place strings from M1 imprints (e.g., "Paris :", "אמשטרדם", "[Berlin]")
- **Mapping:** `data/normalization/place_aliases/place_alias_map.json` (production, version-controlled)
- **Process:** Basic cleaning (casefold, strip punctuation, remove brackets) + optional alias map lookup
- **Output:** Canonical English keys (e.g., "paris", "amsterdam", "berlin") with confidence scores
- **Confidence:** 0.80 (base cleaning) or 0.95 (with alias map)
- **Documentation:** `docs/pipelines/place_normalization.md`

### Publisher Normalization
- **Input:** Raw publisher strings from M1 imprints (e.g., "C. Fosset,", "Elsevier:")
- **Process:** Same cleaning pipeline as place normalization
- **Output:** Canonical keys with confidence scores
- **Confidence:** 0.80 (base) or 0.95 (with optional alias map)

### Date Normalization
- **Input:** Raw date strings from M1 imprints (e.g., "[1680]", "c. 1650", "1500-1599")
- **Rules:** 6 deterministic patterns (exact, bracketed, circa ±5 years, range, embedded, unparsed)
- **Output:** Start/end years with method tag and confidence
- **Confidence:** 0.95-0.99 (high certainty), 0.80-0.85 (medium), 0.0 (unparsed)
- **Specification:** `docs/specs/m2_normalization_spec.md`

### Key Files
```
data/normalization/place_aliases/
├── place_alias_map.json         # Production mapping (tracked in git)
├── place_alias_cache.jsonl      # LLM cache (gitignored)
└── place_alias_proposed.csv     # Human review file (gitignored)
```

### Usage Example
```bash
# Generate place alias map (one-time, LLM-assisted)
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json

# Enrich M1 records with M2 normalization
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json
```

## Code Style

- Prefer small, pure functions with unit tests
- All parsing/normalization must be **testable without the LLM**
- Use type hints, Pydantic/dataclasses, and deterministic outputs
- Write logs/artifacts per run to support debugging

## Available Skills

This project has specialized skills in `.claude/skills/` that extend Claude's capabilities:

### python-dev-expert
Python development best practices aligned with this project's requirements:
- Single-purpose functions (<50 lines, one responsibility)
- Deterministic, testable code with dependency injection
- Type hints and comprehensive docstrings
- Composition over inheritance
- Extract logic after 3rd duplication (DRY principle)

**Use for**: Writing new Python code, refactoring, architectural decisions, code reviews

### git-expert
Git and GitHub workflow management:
- Granular commits with clear messages
- Safe operations (never destructive without explicit request)
- Branch management and PR creation

**Use for**: Committing changes, creating PRs, managing git workflow

**Note**: Claude should proactively use these skills when relevant rather than waiting for explicit invocation.

## Directory Conventions

```
data/
  marc_source/                # raw MARC XML files
  canonical/                  # canonical JSONL (one record per line)
  index/                      # SQLite database for fielded queries
  runs/<run_id>/              # per-run artifacts: plan, SQL, candidate set, logs
```

## Stable Interfaces (Contracts)

```python
parse_marc_xml(path: Path) -> Iterable[CanonicalRecord]
normalize_record(record: CanonicalRecord) -> NormalizedRecord  # raw + norm + confidence
compile_query(nl_query: str) -> QueryPlan  # JSON schema validated
execute_plan(plan: QueryPlan, sqlite_db: Path) -> CandidateSet + Evidence
```

## LLM Usage Rules

- LLM is a **planner/explainer**, not the authority
- LLM output must be validated against a JSON schema (using OpenAI Responses API for structured output)
- If schema validation fails: return empty plan with error in debug, don't retry (fail-closed pattern)

### Query Planning (M4/M5)

The query compiler now uses **LLM-based parsing** via OpenAI's Responses API:

- **Implementation**: `scripts/query/llm_compiler.py`
- **Model**: gpt-4o (default, configurable)
- **Schema enforcement**: Pydantic models via OpenAI Responses API (`client.responses.parse()`)
- **Caching**: JSONL cache at `data/query_plan_cache.jsonl` (query_text → QueryPlan)
- **API key**: Set `OPENAI_API_KEY` environment variable

**Pattern**:
```python
from scripts.query.compile import compile_query

# With API key in environment
plan = compile_query("books published by Oxford between 1500 and 1599")

# Or pass explicitly
plan = compile_query("...", api_key="sk-...", model="gpt-4o")
```

**Cache behavior**:
- Cache hits return immediately (no API call)
- Cache misses call LLM and write to cache
- Cache is append-only JSONL for inspection and debugging

## Acceptance Tests (POC)

Must support queries like:
- "All books published by X between 1500 and 1599"
- "All books printed in Paris in the 16th century"
- "Books on topic X" (subject headings / 6XX fields)

Output must include CandidateSet + evidence fields used.

## QA Tool Architecture

**Status**: Development tool maintained as part of core repository

**Purpose**: Quality assurance infrastructure for M4 query pipeline development, providing systematic labeling, issue tracking, and regression testing capabilities.

### Components

**Streamlit UI** (`app/ui_qa/`):
- 5-page interactive application for query testing and labeling
- Session management for organizing QA work
- Visual query builder and result inspection
- Issue tagging with predefined categories (parser errors, normalization issues, etc.)

**QA Database** (`data/qa/qa.db`):
- Separate SQLite database (isolated from production `bibliographic.db`)
- Tables: `qa_queries`, `qa_candidate_labels`, `qa_query_gold`
- Stores query runs, candidate labels (TP/FP/FN/UNK), and gold set metadata

**Regression Framework**:
- Gold set export to `data/qa/gold.json` (expected includes/excludes per query)
- CLI regression runner: `python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db`
- Exit codes for CI integration (0 = pass, 1 = fail)

### Scope and Boundaries

**In Scope**:
- Query labeling and issue tracking for M4 development
- Gold set creation and management
- Regression testing for query pipeline
- Statistical analysis of query quality (precision, recall, issue patterns)

**Out of Scope**:
- Production query execution (use `app/cli.py query` for production)
- M1-M3 pipeline testing (covered by unit tests in `tests/`)
- General-purpose data exploration (not a database browser)

### Usage

**Launch QA UI**:
```bash
poetry run streamlit run app/ui_qa/main.py
```

**Run regression tests** (for CI or manual validation):
```bash
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db
```

**Workflow**:
1. Run query in UI → review results
2. Label candidates as TP/FP/FN → tag issues
3. Find missing records (FN) via database search
4. Export gold set when queries are validated
5. Run regression tests to prevent quality regressions

**Documentation**: See `app/ui_qa/README.md` for detailed usage guide

**Decision rationale**: QA tool is maintained in-repo (not extracted) because:
- Tightly coupled to M4 query pipeline evolution
- Uses same dependencies (Pydantic models, query compiler, evidence extraction)
- Facilitates rapid iteration during M4 development
- Small codebase (~1000 lines) doesn't justify separate package overhead

## Project Structure (Inherited Shell)

This project started from a multi-source RAG platform template. The core structure includes:

- **`app/`**: CLI interface (using Typer)
- **`scripts/`**: Core library organized by function (ingestion, chunking, embeddings, retrieval, etc.)
- **`configs/`**: YAML configurations (currently chunk_rules.yaml from template)
- **`tests/`**: Pytest suite
- **`archive/`**: Reference materials and documentation from the RAG template (kept for reference only, not active code)

**Current state**: The repo is largely a shell template. Development will focus on MARC-specific components while leveraging the modular architecture (e.g., using the utils, logging, and project management patterns).

**Transformation status**: Actively removing RAG-specific components and building MARC XML functionality. See `plan.mf` for milestone roadmap.

## Session Management

Multi-turn conversation support with persistent state:

**Location**: `scripts/chat/session_store.py`
**Database**: `data/chat/sessions.db`
**Models**: `scripts/chat/models.py` (ChatSession, Message, ChatResponse)

**Key Operations**:
- Create session: `store.create_session(user_id)`
- Add message: `store.add_message(session_id, message)`
- Retrieve session: `store.get_session(session_id)`
- Expire old: `store.expire_old_sessions(max_age_hours=24)`

**CLI Commands**:
```bash
# Create new session
python -m app.cli chat-init [--user-id USER_ID]

# Query with session tracking
python -m app.cli query "books by Oxford" --session-id <SESSION_ID>

# View session history
python -m app.cli chat-history <SESSION_ID>

# Cleanup old sessions
python -m app.cli chat-cleanup [--max-age-hours 24]
```

See `docs/session_management_usage.md` for full documentation.

## Response Formatting (Chatbot)

Natural language response formatting for conversational interfaces:

**Location**: `scripts/chat/formatter.py`
**Purpose**: Transform CandidateSet results into natural language chat responses

**Key Functions**:
- `format_for_chat(candidate_set) -> str` - Main formatting function
  - Converts CandidateSet to conversational response with evidence
  - Handles zero results with helpful suggestions
  - Supports max_candidates limit and evidence toggle
- `format_summary(candidate_set) -> str` - Brief one-line summary
- `generate_followups(candidate_set, query_text) -> List[str]` - Context-aware suggestions
- `format_evidence(evidence_list) -> str` - Evidence as readable bullet points

**Features**:
- Natural language summaries: "Found X books matching your query"
- Evidence formatted as bullet points with confidence scores
- Context-aware follow-up question suggestions
- Zero-results handling with broadening suggestions
- Multi-result formatting with detail limits

**Integration**:
- Used by API layer (`app/api/main.py`) to format responses
- Automatically generates suggested_followups for ChatResponse
- Provides evidence citations in readable format

**Example Output**:
```
Found 2 books matching your query.
Query: "books published by Oxford between 1500 and 1599"

Showing details for 2 of 2 results:

1. Record: 990001234
   Match: publisher_norm='oxford' AND year_range overlaps 1500-1599
   Evidence:
     • publisher_norm matches 'oxford' (confidence: 95%) [marc:264$b[0]]
     • date_start is 1550 (matches range) (confidence: 99%) [marc:264$c[0]]

2. Record: 990005678
   ...
```

## Common Commands

```bash
# Install dependencies
poetry install

# Set up environment (for LLM query planning)
export OPENAI_API_KEY="sk-..."  # Required for query compilation

# Run tests
pytest                          # all tests
pytest tests/path/to/test.py    # specific test file
pytest -k "test_name"           # specific test by name
pytest -m "not legacy_chunker"  # skip legacy chunker tests
pytest --run-integration        # run integration tests (requires OPENAI_API_KEY)

# Code quality
ruff check .                    # linting
ruff format .                   # formatting
pylint scripts/                 # additional linting

# MARC pipeline commands:
python -m app.cli parse <marc_xml_path>      # parse MARC XML to JSONL
python -m app.cli index <canonical_dir>      # build SQLite index
python -m app.cli query "<nl_query>"         # execute query (requires OPENAI_API_KEY)

# API server commands (M6 Chatbot API):
uvicorn app.api.main:app --reload           # start development server (http://localhost:8000)
uvicorn app.api.main:app --host 0.0.0.0 --port 8000  # production server

# Test API endpoints:
curl http://localhost:8000/health           # health check
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books by Oxford"}'       # chat query (creates new session)
```

## API Layer (M6 Chatbot)

The FastAPI application in `app/api/` provides the HTTP interface for the conversational chatbot:

**Endpoints:**
- `POST /chat` - Send natural language query, get results
  - Request: `{message: str, session_id?: str, context?: dict}`
  - Response: `{success: bool, response: ChatResponse, error?: str}`
  - Creates new session if `session_id` not provided
  - Automatically routes through M4 query pipeline (compile + execute)

- `GET /health` - Health check for monitoring
  - Returns: `{status: str, database_connected: bool, session_store_ok: bool}`

- `GET /sessions/{session_id}` - Get session details and message history
- `DELETE /sessions/{session_id}` - Expire a session

**Configuration (environment variables):**
- `SESSIONS_DB_PATH` - Path to sessions.db (default: `data/chat/sessions.db`)
- `BIBLIOGRAPHIC_DB_PATH` - Path to bibliographic.db (default: `data/index/bibliographic.db`)
- `OPENAI_API_KEY` - Required for query compilation

**Testing:**
```bash
# Run API tests (unit tests, no API key needed)
pytest tests/app/test_api.py -v

# Run integration tests (requires OPENAI_API_KEY)
pytest tests/app/test_api.py -v --run-integration
```

## Key Architecture Notes

- **ProjectManager** (`scripts/core/project_manager.py`): Central class for managing project config, paths, and logging
- **TaskPaths** (`scripts/utils/task_paths.py`): Handles per-run artifact paths
- **LoggerManager** (`scripts/utils/logger.py`): Structured JSON logging per project/task/run
- **Modular design**: Each component (ingestion, chunking, embeddings, etc.) has a base interface and pluggable implementations

## What's Different from the Template

This is **NOT** a general RAG platform. Key differences:
- Source of truth is **MARC XML**, not arbitrary documents
- No embedding-based retrieval (use SQLite fielded queries first)
- Answers require **deterministic evidence** from MARC fields
- Normalization must be **reversible** and **confident**
- Query execution must produce **CandidateSet before narrative**
