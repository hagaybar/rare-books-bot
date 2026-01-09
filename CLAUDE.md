# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
- LLM output must be validated against a JSON schema
- If schema validation fails: retry once with a repair prompt, else **fail fast**

## Acceptance Tests (POC)

Must support queries like:
- "All books published by X between 1500 and 1599"
- "All books printed in Paris in the 16th century"
- "Books on topic X" (subject headings / 6XX fields)

Output must include CandidateSet + evidence fields used.

## Project Structure (Inherited Shell)

This project started from a multi-source RAG platform template. The core structure includes:

- **`app/`**: CLI interface (using Typer)
- **`scripts/`**: Core library organized by function (ingestion, chunking, embeddings, retrieval, etc.)
- **`configs/`**: YAML configurations (currently chunk_rules.yaml from template)
- **`tests/`**: Pytest suite
- **`archive/`**: Reference materials and documentation from the RAG template (kept for reference only, not active code)

**Current state**: The repo is largely a shell template. Development will focus on MARC-specific components while leveraging the modular architecture (e.g., using the utils, logging, and project management patterns).

**Transformation status**: Actively removing RAG-specific components and building MARC XML functionality. See `plan.mf` for milestone roadmap.

## Common Commands

```bash
# Install dependencies
poetry install

# Run tests
pytest                          # all tests
pytest tests/path/to/test.py    # specific test file
pytest -k "test_name"           # specific test by name
pytest -m "not legacy_chunker"  # skip legacy chunker tests

# Code quality
ruff check .                    # linting
ruff format .                   # formatting
pylint scripts/                 # additional linting

# Once MARC parsing is implemented:
python -m app.cli parse <marc_xml_path>      # parse MARC XML to JSONL
python -m app.cli index <canonical_dir>      # build SQLite index
python -m app.cli query "<nl_query>"         # execute query
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
