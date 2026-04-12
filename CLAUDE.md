# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tool Safety & Bounded Output

1. When inspecting files, never read large files in full. Always use bounded operations:
2. search first (rg/grep), then view small excerpts (offset/limit, sed -n, head, tail).
3. Any command that may return large output must include a hard cap (e.g., | head -n 50).
4. If a tool returns an error about size/limits, do not retry the same approach. Switch strategy (search -> narrow excerpt -> proceed).

## ⚠ Hard Rules (read first)

- Never read large files in full — always bound with `rg`/`head`/`sed -n`
- Hard-cap any command that may return large output (`| head -n 50`)
- On empty CandidateSet: report it explicitly with the query that produced it — do not narrate around it
- On MARC parse failure: log the error to `data/runs/`, surface it clearly, and stop — do not proceed with partial data
- On low normalization confidence: store `null` + explicit reason — never invent or guess values

## Project Mission

Build a bibliographic discovery system for rare books where **MARC XML is the source of truth**.

**Primary success criterion**: Given an inventory query, deterministically produce the correct CandidateSet (record IDs) with evidence showing which MARC fields/values caused inclusion.

## Answer Contract (Non-Negotiable)

Every response--even internal ones--must be grounded in:
1. **QueryPlan** (structured JSON)
2. **CandidateSet** (record IDs that match)
3. **Evidence** (which MARC fields/subfields caused inclusion)
4. **Normalized mapping** (raw -> normalized) with confidence scores

**No narrative or interpretation is allowed before CandidateSet exists.**

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

| Skill | Description | When to invoke |
|-------|-------------|----------------|
| python-dev-expert | Python best practices | Pure Python implementation questions |
| git-expert | Git/GitHub workflow | Branch, PR, and commit workflow |
| marc-ingest | Full MARC XML ingestion pipeline rebuild (7 phases) | Rebuilding or repairing the ingestion pipeline |
| babysitter | Orchestrate complex multi-step workflows | Any multi-step workflow requiring quality gates or process management |
| superpowers | Brainstorming, planning, TDD, debugging, verification, code review | Planning new features, debugging, or reviewing code |

## Directory Conventions

```
data/              # marc_source/, canonical/, index/, runs/, qa/, chat/
data/eval/          # model config, benchmark queries, evaluation runs
docs/current/      # 11 topic files -- single source of truth per area
docs/history/      # Historical journal -- audits, reports, plans, specs
docs/superpowers/  # Skill output targets (specs/, plans/)
docs/testing/      # Manual testing guide
audits/            # Project-audit skill output target
scripts/           # Core library
scripts/models/     # LLM client wrapper and model config
scripts/eval/       # Batch evaluation framework
frontend/          # React SPA
app/               # CLI + FastAPI
.a5c/              # Babysitter processes and runs
```

## Common Commands

```bash
poetry install                    # dependencies
pytest                            # all tests
pytest -k "test_name"             # specific test
ruff check . && ruff format .     # lint + format
uvicorn app.api.main:app --reload # dev server
cd frontend && npm run dev        # frontend dev
./deploy.sh                       # deploy to production
python -m app.cli query "..."     # run a query
# Run model comparison across stages; use when evaluating a new model or prompt change
python3 scripts/eval/run_eval.py --models gpt-4.1,gpt-4.1-mini --stages interpreter,narrator --queries data/eval/queries.json --judge-model gpt-4.1
```

## Topic Registry

Detailed documentation lives in `docs/current/`. Consult these files for implementation details.

| Topic | File | Covers |
|-------|------|--------|
| Normalization | docs/current/normalization-pipeline.md | M2 dates/places/publishers, alias maps |
| Query Engine | docs/current/query-engine.md | M4 LLM compiler, SQL execution, stable interfaces |
| Chatbot API | docs/current/chatbot-api.md | /chat endpoint, sessions, formatting, clarification |
| Streaming | docs/current/streaming.md | WebSocket protocol, message types, testing |
| QA Framework | docs/current/qa-framework.md | Diagnostics, gold sets, regression testing |
| Metadata | docs/current/metadata-workbench.md | Agents, corrections, publisher authorities |
| Deployment | docs/current/deployment.md | Docker, nginx, deploy.sh, SSH access |
| Ingestion | docs/current/ingestion-pipeline.md | MARC XML -> bibliographic.db pipeline |
| Architecture | docs/current/architecture.md | Project structure, key classes, model index |
| Data Model | docs/current/data-model.md | End-to-end data flow, schemas, strengths/weaknesses |
| Data Quality | docs/current/data-quality.md | Quality checks, fix scripts, sampling protocol, remediation |

## Documentation Maintenance Protocol

### On Every Code Change
When you modify code that affects behavior documented in `docs/current/`:
1. Update the relevant topic file in `docs/current/`
2. Set `Last verified: YYYY-MM-DD` in the file header
3. If no topic file exists for the area changed, create one and add it to the Topic Registry table above

### On Every New Feature or Architectural Change
1. Update `docs/current/architecture.md` if project structure changed
2. Update the Topic Registry in this file if a new topic was added
3. Update `Common Commands` in this file if new CLI commands were added

### After Superpowers Brainstorming/Planning
- New specs land in `docs/superpowers/specs/` (skill default)
- New plans land in `docs/superpowers/plans/` (skill default)
- After implementation is complete: move the spec/plan to `docs/history/specs/` or `docs/history/plans/` and add a line to `docs/history/INDEX.md`

### After Project Audits
- New audits land in `audits/YYYY-MM-DD-<name>/` (skill default)
- After action items are resolved: move the audit directory to `docs/history/audits/` and add a line to `docs/history/INDEX.md`

### Staleness Rule
If you read a `docs/current/` file and notice it contradicts the code, fix the doc immediately -- don't proceed with stale information.

## What's Different from the Template

This is **NOT** a general RAG platform. Key differences:
- Source of truth is **MARC XML**, not arbitrary documents
- No embedding-based retrieval (use SQLite fielded queries first)
- Answers require **deterministic evidence** from MARC fields
- Normalization must be **reversible** and **confident**
- Query execution must produce **CandidateSet before narrative**
