# Rare Books Bot - MARC XML Bibliographic Discovery System

A deterministic, evidence-based bibliographic discovery system for rare books where MARC XML is the source of truth.

## Overview

This project processes MARC XML records through a multi-stage pipeline (M1 → M2 → M3 → M4 → M6) to enable fielded queries and conversational discovery of rare book collections. All normalization is reversible, confidence-scored, and traceable back to source MARC fields.

**Primary Success Criterion:** Given an inventory query, deterministically produce the correct CandidateSet (record IDs) with evidence showing which MARC fields/values caused inclusion.

**Pipeline Stages:**
- **M1:** MARC XML parsing → canonical JSONL
- **M2:** Normalization & enrichment (dates, places, publishers)
- **M3:** SQLite indexing with FTS
- **M4:** Query planning & execution (LLM-based)
- **M6:** Chatbot API with conversational interface

## Quick Start

```bash
# Install dependencies
poetry install

# Set up OpenAI API key (REQUIRED for query compilation)
export OPENAI_API_KEY="sk-..."

# Parse MARC XML to canonical format (M1)
python -m scripts.marc.parse_xml \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/canonical/records.jsonl

# Build place frequency table (for normalization)
python -m scripts.marc.build_place_freq \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/frequency/places_freq.csv \
  data/frequency/places_examples.json

# Generate place alias map (one-time, LLM-assisted)
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json

# Enrich with M2 normalization
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json

# Build M3 SQLite index
python -m scripts.marc.m3_index \
  data/m2/records_m1m2.jsonl \
  data/index/bibliographic.db \
  scripts/marc/m3_schema.sql

# Query the index (M4)
python -m app.cli query "Books printed in Paris in the 17th century"

# Start the Chatbot API (M6)
uvicorn app.api.main:app --reload

# Start the Chat UI
poetry run streamlit run app/ui_chat/main.py
```

## Project Structure

```
rare-books-bot/
├── CLAUDE.md                    # Claude Code guidance
├── README.md                    # This file
├── plan.mf                      # Milestone roadmap
│
├── docs/                        # Documentation
│   ├── specs/                   # Completed specifications
│   ├── pipelines/               # Pipeline documentation
│   ├── utilities/               # Utility documentation
│   ├── session_management_usage.md
│   ├── PROJECT_DESCRIPTION.md   # Comprehensive reference
│   └── testing/
│       └── MANUAL_TESTING_GUIDE.md
│
├── app/                         # Application layer
│   ├── cli.py                   # CLI interface (Typer)
│   ├── qa.py                    # QA regression runner
│   ├── api/                     # FastAPI chatbot API
│   │   ├── main.py              # HTTP + WebSocket endpoints
│   │   └── models.py            # API request/response models
│   ├── ui_chat/                 # Streamlit chat UI
│   │   └── main.py
│   └── ui_qa/                   # Streamlit QA tool
│
├── scripts/                     # Source code
│   ├── marc/                    # MARC XML processing (M1-M3)
│   │   ├── parse.py             # M1: MARC XML → canonical JSONL
│   │   ├── models.py            # M1 data models
│   │   ├── normalize.py         # M2: Normalization functions
│   │   ├── m2_normalize.py      # M2: Enrichment CLI
│   │   ├── m3_schema.sql        # M3: SQLite schema
│   │   ├── m3_index.py          # M3: Indexing script
│   │   └── m3_query.py          # M3: Query functions
│   │
│   ├── query/                   # Query planning & execution (M4)
│   │   ├── llm_compiler.py      # LLM-based query compilation
│   │   ├── execute.py           # Query execution
│   │   ├── service.py           # Query service
│   │   ├── db_adapter.py        # Database adapter
│   │   └── models.py            # Query models
│   │
│   ├── chat/                    # Chatbot components (M6)
│   │   ├── session_store.py     # Session management
│   │   ├── formatter.py         # Response formatting
│   │   ├── clarification.py     # Ambiguity detection
│   │   ├── intent_agent.py      # Intent interpretation
│   │   ├── exploration_agent.py # Corpus exploration
│   │   ├── aggregation.py       # Result aggregation
│   │   └── models.py            # Chat models
│   │
│   ├── enrichment/              # External data enrichment
│   │   ├── wikidata_client.py   # Wikidata API client
│   │   ├── nli_client.py        # National Library of Israel client
│   │   ├── enrichment_service.py
│   │   └── models.py
│   │
│   ├── normalization/           # Normalization utilities
│   └── utils/                   # Shared utilities
│
├── tests/                       # Test suite (32+ test files)
│   ├── scripts/                 # Mirrors scripts/ structure
│   ├── app/                     # API and CLI tests
│   └── ...
│
├── data/                        # Data artifacts (gitignored)
│   ├── marc_source/             # Raw MARC XML files
│   ├── canonical/               # M1: Canonical JSONL records
│   ├── m2/                      # M2: Enriched records
│   ├── index/                   # M3: SQLite database
│   ├── chat/                    # Session database
│   │   └── sessions.db
│   ├── qa/                      # QA tool database
│   │   └── qa.db
│   └── runs/                    # M4: Query artifacts (per run_id)
│
└── configs/                     # Configuration files
```

## Data Pipeline

### M1: MARC XML Parsing

**Purpose:** Extract bibliographic records from MARC XML into canonical JSON format

**Input:** Raw MARC XML files

**Output:** `data/canonical/records.jsonl` (one JSON record per line)

**Key features:**
- Preserves all raw MARC values
- Occurrence-indexed provenance (e.g., `500[0]$a`, `500[1]$a`)
- Extracts: title, imprints, agents, subjects, languages, notes

```bash
python -m scripts.marc.parse_xml \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/canonical/records.jsonl
```

### M2: Normalization & Enrichment

**Purpose:** Add normalized fields for querying without modifying M1 data

**Input:** M1 canonical records

**Output:** `data/m2/records_m1m2.jsonl` (M1 + `m2` object appended)

**Normalization types:**
- **Dates:** 6 deterministic rules (exact, bracketed, circa, range, embedded, unparsed)
- **Places:** Cleaning + optional alias map lookup (0.80-0.95 confidence)
- **Publishers:** Same as places

**Key features:**
- Deterministic (same input → same output)
- Reversible (M1 preserved)
- Confidence-scored (0.0-1.0)
- Method-tagged (e.g., `year_bracketed`, `place_alias_map`)

```bash
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json
```

### M3: SQLite Indexing

**Purpose:** Build queryable database with M1 raw + M2 normalized fields

**Input:** M2 enriched records

**Output:** `data/index/bibliographic.db` (SQLite database)

**Schema:**
- Tables: records, titles, imprints, subjects, agents, languages, notes
- FTS5 full-text search on titles and subjects
- Indexes on date ranges, places, publishers

```bash
python -m scripts.marc.m3_index \
  data/m2/records_m1m2.jsonl \
  data/index/bibliographic.db \
  scripts/marc/m3_schema.sql
```

### M4: Query Planning & Execution

**Purpose:** Convert natural language queries to SQL with CandidateSet + Evidence

**Input:** Natural language query

**Output:**
- QueryPlan (structured JSON)
- SQL query
- CandidateSet (matching record IDs)
- Evidence (MARC fields that caused inclusion)

**Example queries:**
- "All books published by X between 1500 and 1599"
- "All books printed in Paris in the 16th century"
- "Books on topic X" (subject headings)

```bash
python -m app.cli query "Books printed in Paris in the 17th century"
```

## M6: Chatbot API

The chatbot layer provides a conversational interface for bibliographic discovery.

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Send query, receive results with evidence |
| `/health` | GET | Health check (database, session store) |
| `/sessions/{id}` | GET | Get session details and history |
| `/sessions/{id}` | DELETE | Expire a session |

**Example chat request:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}'
```

**Response includes:**
- `session_id` - for multi-turn conversations
- `message` - natural language response
- `candidate_set` - matched records with evidence
- `followup_questions` - suggested refinements

### WebSocket Streaming

Connect to `ws://localhost:8000/ws/chat` for real-time streaming:
- Progress updates during query execution
- Batch results (groups of 10 candidates)
- Final response with full ChatResponse

### Two-Phase Conversation

1. **Query Definition Phase:** Intent interpretation, ambiguity detection, clarification prompts
2. **Corpus Exploration Phase:** Query execution, evidence collection, result formatting

### Features

- **Session Management:** Multi-turn conversations with persistent state
- **Response Formatting:** Natural language responses with evidence citations
- **Clarification Flow:** Detects vague queries and guides users to specificity
- **Streaming:** Real-time progress and batch results via WebSocket
- **Rate Limiting:** 10 requests/minute per IP on `/chat` endpoint

### Starting the API

```bash
# Development mode (auto-reload)
uvicorn app.api.main:app --reload

# API docs at http://localhost:8000/docs
```

## Chat UI

A Streamlit-based chat interface for interactive bibliographic discovery.

```bash
poetry run streamlit run app/ui_chat/main.py
```

**Features:**
- Message history display
- API integration with session tracking
- Evidence visualization

## Enrichment Services

External data enrichment for bibliographic records:

| Service | Purpose |
|---------|---------|
| `wikidata_client.py` | Wikidata entity lookup and enrichment |
| `nli_client.py` | National Library of Israel integration |
| `enrichment_service.py` | Unified enrichment orchestration |

## QA Tool

Quality assurance infrastructure for query pipeline development:

```bash
# Launch QA UI
poetry run streamlit run app/ui_qa/main.py

# Run regression tests
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db
```

See `app/ui_qa/README.md` for detailed documentation.

## Documentation

### Specifications
- **[M2 Normalization](docs/specs/m2_normalization_spec.md)** - Date, place, publisher normalization rules
- **[Place Frequency Analysis](docs/specs/place_frequency_spec.md)** - Extract and count place name variants

### Guides
- **[Session Management](docs/session_management_usage.md)** - Multi-turn conversation support
- **[Manual Testing Guide](docs/testing/MANUAL_TESTING_GUIDE.md)** - API testing procedures
- **[Project Description](docs/PROJECT_DESCRIPTION.md)** - Comprehensive reference

### Pipeline Documentation
- **[Place Normalization](docs/pipelines/place_normalization.md)** - Complete normalization workflow

## Testing

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/scripts/marc/test_m2_normalize.py

# Run API tests
pytest tests/app/test_api.py -v

# Run integration tests (requires OPENAI_API_KEY)
pytest --run-integration

# Run with coverage
pytest --cov=scripts --cov-report=html
```

**Test Coverage:** 32+ test files covering M1-M4 pipelines, API endpoints, chat components, and query services.

## Common Commands

```bash
# Install dependencies
poetry install

# Set up environment
export OPENAI_API_KEY="sk-..."

# MARC pipeline
python -m app.cli parse <marc_xml_path>
python -m app.cli index <canonical_dir>
python -m app.cli query "<nl_query>"

# API server
uvicorn app.api.main:app --reload
curl http://localhost:8000/health
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books by Oxford"}'

# Chat UI
poetry run streamlit run app/ui_chat/main.py

# QA Tool
poetry run streamlit run app/ui_qa/main.py

# Session management
python -m app.cli chat-init [--user-id USER_ID]
python -m app.cli chat-history <SESSION_ID>
python -m app.cli chat-cleanup [--max-age-hours 24]

# Code quality
ruff check .
ruff format .
pytest
```

## Current Status

**Completed:**
- ✅ M1: MARC XML parsing with occurrence indexing
- ✅ M2: Deterministic normalization (date, place, publisher, agents)
- ✅ M3: SQLite indexing with FTS
- ✅ M4: LLM-based query planning and execution
- ✅ M6: Chatbot API (HTTP + WebSocket)
- ✅ Session management (multi-turn conversations)
- ✅ Response formatting (natural language with evidence)
- ✅ Clarification flow (ambiguity detection)
- ✅ Streaming responses (WebSocket progressive streaming)
- ✅ Rate limiting (10 req/min for /chat)
- ✅ QA Tool with regression testing
- ✅ Chat UI (Streamlit interface)
- ✅ Enrichment services (Wikidata, NLI clients)

**In Progress:**
- 🚧 Two-phase conversation refinement
- 🚧 Enrichment service integration

**Planned:**
- 📋 M5: Complex question answering over CandidateSet
- 📋 Authentication (postponed for initial testing)
- 📋 Performance metrics (postponed for initial testing)

## Key Principles

### Answer Contract (Non-Negotiable)

Every query response must include:
1. **QueryPlan** (structured JSON)
2. **CandidateSet** (record IDs)
3. **Evidence** (MARC fields that matched)
4. **Normalized mapping** (raw → normalized with confidence)

**No narrative before CandidateSet exists.**

### Data Model Rules

- **Preserve raw MARC values always** (no destructive normalization)
- **Normalized fields are reversible** (store raw alongside normalized)
- **If uncertain:** store `null`/range + explicit reason (never invent data)

### Deterministic Processing

- Same input file → identical output
- All normalization rules are explicit and testable
- No randomness (LLM only used for query compilation, not core pipeline)

## Development

See [CLAUDE.md](CLAUDE.md) for detailed guidance on working with this codebase.

### Skills Available

This project has specialized Claude Code skills:
- **python-dev-expert** - Best practices for Python development
- **git-expert** - Git workflow management

## License

[Add license information]

## Contact

[Add contact information]
