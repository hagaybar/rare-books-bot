# Metadata Co-pilot Workbench — Architecture & Usage Guide

> For librarians using the system and AI agents improving it.

## 1. What This System Does

The Metadata Co-pilot Workbench improves the quality of a rare books bibliographic database (MARC-based) through an agent-driven, Human-In-The-Loop (HITL) workflow. Specialist AI agents analyze normalization gaps in the database, cluster related issues, propose evidence-grounded fixes, and present them to a librarian for approval. Approved corrections flow back into the database incrementally — no full pipeline rebuild required.

**The core insight**: Normalization rules are solid but coverage is incomplete. 2,740 publishers lack alias maps, 1,185 places are unmapped, 69 dates are unparsed. The system closes these gaps systematically rather than manually.

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    React Frontend (frontend/)                    │
│  Dashboard │ Workbench │ Agent Chat │ Review                     │
└──────────────────────────┬───────────────────────────────────────┘
                           │ REST API (11 endpoints)
┌──────────────────────────┴───────────────────────────────────────┐
│              FastAPI Backend (app/api/metadata.py)                │
│  /metadata/coverage │ /metadata/issues │ /metadata/corrections   │
│  /metadata/clusters │ /metadata/agent/chat │ /metadata/primo-urls │
└──────────────────────────┬───────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────┴──────┐  ┌─────┴──────┐  ┌──────┴──────┐
   │  Grounding  │  │ Specialist │  │   Action    │
   │   Layer     │  │   Agents   │  │   Layer     │
   │             │  │            │  │             │
   │ M3 SQLite   │  │ PlaceAgent │  │ Alias Maps  │
   │ Alias Maps  │  │ DateAgent  │  │ Review Log  │
   │ Country     │  │ PublAgent  │  │ Re-normalize│
   │ Codes       │  │ NameAgent  │  │ Coverage    │
   │ Auth URIs   │  │            │  │ Refresh     │
   └─────────────┘  └────────────┘  └─────────────┘
```

### Layer Responsibilities

| Layer | Purpose | LLM? | Key Principle |
|-------|---------|------|---------------|
| **Grounding** | Query DB for gaps, load alias maps, cross-reference evidence | No | Deterministic, fast, no external calls |
| **Reasoning** | Propose canonical mappings, explain clusters, suggest strategies | Yes | Strict prompts, structured JSON, cached responses |
| **Action** | Write alias maps, update DB, log corrections | No | Atomic writes, incremental updates, audit trail |

## 3. File Map

### Backend Modules (~3,700 lines Python)

```
scripts/metadata/
├── __init__.py
├── audit.py              # 533 lines — CoverageReport, confidence band analysis
├── clustering.py          # 730 lines — Gap clustering by script/pattern/frequency
├── agent_harness.py       # 638 lines — GroundingLayer + ReasoningLayer + AgentHarness
├── feedback_loop.py       # 518 lines — Approve → alias map → re-normalize → log
├── review_log.py          # 218 lines — Append-only JSONL audit trail
└── agents/
    ├── __init__.py
    ├── place_agent.py     # 362 lines — Latin toponyms, Hebrew names, country codes
    ├── date_agent.py      # 365 lines — Hebrew calendar, partial centuries, Latin
    ├── publisher_agent.py # 325 lines — Printer dynasties, Latin variants, s.n. detection
    └── name_agent.py      # 554 lines — VIAF/NLI authority, name matching, validation
```

### API Layer (~1,700 lines Python)

```
app/api/
├── metadata.py            # 1,362 lines — 11 REST endpoints + agent chat
└── metadata_models.py     # 328 lines — 25 Pydantic response models
```

### Frontend (~15 files TypeScript/React)

```
frontend/src/
├── types/metadata.ts      # TypeScript interfaces matching backend models
├── api/metadata.ts        # Fetch functions for all /metadata/* endpoints
├── hooks/useMetadata.ts   # TanStack Query hooks with caching
├── components/
│   ├── Layout.tsx          # Sidebar + content layout
│   ├── Sidebar.tsx         # Navigation with active states
│   └── workbench/
│       ├── EditableCell.tsx    # Double-click inline editing
│       ├── BatchToolbar.tsx    # Batch corrections + CSV export
│       └── ClusterCard.tsx     # Expandable cluster display
└── pages/
    ├── Dashboard.tsx       # Coverage charts, gap cards, method distribution
    ├── Workbench.tsx       # TanStack Table with filtering, sorting, pagination
    ├── AgentChat.tsx       # Chat UI with proposal approve/reject/edit
    └── Review.tsx          # Correction history timeline with filters + export
```

### Tests (~534 tests)

```
tests/scripts/metadata/
├── test_audit.py              # 41 tests
├── test_clustering.py         # 71 tests
├── test_agent_harness.py      # 46 tests
├── test_feedback_loop.py      # 30 tests
├── test_review_log.py         # 28 tests
└── agents/
    ├── test_place_agent.py    # 40 tests
    ├── test_date_agent.py     # 45 tests
    ├── test_publisher_agent.py # 59 tests
    └── test_name_agent.py     # 61 tests
tests/app/
├── test_metadata_api.py       # 53 tests
├── test_metadata_corrections.py # 25 tests
└── test_agent_chat.py         # 18 tests
tests/integration/
└── test_metadata_workbench.py # 17 tests (full workflow smoke)
```

## 4. Data Flow

### The Correction Lifecycle

```
1. AUDIT
   audit.py queries M3 DB → CoverageReport (per-field confidence distributions)

2. CLUSTER
   clustering.py groups flagged items → Clusters (by script, pattern, frequency)

3. PROPOSE (Agent)
   specialist agent + LLM → ProposedMapping (canonical_value, confidence, reasoning)

4. REVIEW (Human via UI)
   librarian sees proposals → Approve / Reject / Edit

5. APPLY (Feedback Loop)
   feedback_loop.py:
     → writes alias map atomically (.tmp + os.replace)
     → UPDATE imprints/agents SET *_norm=?, *_confidence=0.95
     → appends to review_log.jsonl

6. VERIFY
   re-run audit → coverage improved
   rejected proposals logged → agents won't re-propose
```

### Database Tables Touched

| Table | Read By | Written By |
|-------|---------|------------|
| `imprints` | Audit, GroundingLayer, API issues endpoint | FeedbackLoop (UPDATE *_norm, *_confidence) |
| `agents` | Audit, GroundingLayer, NameAgent | FeedbackLoop (UPDATE agent_norm, agent_confidence) |
| `authority_enrichment` | NameAgent (validate_against_authority) | Not written by workbench |
| `records` | GroundingLayer (mms_id lookups) | Not written by workbench |

### Alias Map Files

| File | Used By | Written By |
|------|---------|------------|
| `data/normalization/place_aliases/place_alias_map.json` | PlaceAgent, normalize.py | FeedbackLoop, corrections API |
| `data/normalization/publisher_aliases/publisher_alias_map.json` | PublisherAgent | FeedbackLoop, corrections API |
| `data/normalization/agent_aliases/agent_alias_map.json` | NameAgent | FeedbackLoop, corrections API |

## 5. Specialist Agents — How They Work

Each agent follows the same two-layer pattern:

### Grounding (deterministic, no LLM)
1. Query DB for gaps in its field (confidence <= threshold)
2. Load alias map for vocabulary context
3. Cross-reference evidence (country codes, authority URIs)
4. Cluster values by pattern/script/frequency

### Reasoning (LLM-assisted, strict prompts)
1. Build system prompt with: role, existing vocabulary, evidence, raw value
2. Call OpenAI API (gpt-4o default) with structured JSON response
3. Parse response into ProposedMapping
4. Cache in `data/metadata/agent_llm_cache.jsonl`
5. Check review log — never re-propose rejected mappings

### Agent-Specific Knowledge

| Agent | Domain Knowledge | Example |
|-------|-----------------|---------|
| **PlaceAgent** | Latin toponyms (genitive/nominative/ablative), Hebrew/Arabic script detection, MARC country code cross-referencing | "Lugduni Batavorum" + country=ne → "leiden" |
| **DateAgent** | Hebrew Gematria (תק"ע→1810), partial centuries ([17--?]), Latin date conventions (Anno, MDCCC) | "[17--?]" → partial_century pattern, needs LLM |
| **PublisherAgent** | Printer dynasties, "ex officina/typis/apud" Latin formulae, s.n./sine nomine detection | "typis Elzevirianis" → "elzevir" |
| **NameAgent** | VIAF/NLI/LCNAF authority matching, "Last, First" ↔ "First Last" normalization, authority URI validation | Compares agent_norm against authority_enrichment.label |

## 6. API Endpoints Reference

### Coverage & Analysis
| Endpoint | Params | Returns |
|----------|--------|---------|
| `GET /metadata/coverage` | — | Full CoverageReport (all fields, confidence bands, methods, flagged items) |
| `GET /metadata/issues` | `field` (required), `max_confidence`, `limit`, `offset` | Paginated low-confidence records with mms_id |
| `GET /metadata/unmapped` | `field` (required) | Frequency-sorted unmapped values |
| `GET /metadata/methods` | `field` (required) | Method distribution (count + percentage) |
| `GET /metadata/clusters` | `field` (optional) | Gap clusters sorted by priority_score |

### Corrections
| Endpoint | Body/Params | Returns |
|----------|-------------|---------|
| `POST /metadata/corrections` | `{field, raw_value, canonical_value, evidence, source}` | `{success, alias_map_updated, records_affected}` |
| `POST /metadata/corrections/batch` | `{corrections: [...]}` | Per-item results + totals |
| `GET /metadata/corrections/history` | `field`, `limit`, `offset` | Paginated correction timeline |

### Agent & Primo
| Endpoint | Body/Params | Returns |
|----------|-------------|---------|
| `POST /metadata/agent/chat` | `{field, message}` | `{response, proposals[], clusters[], action}` |
| `POST /metadata/primo-urls` | `{mms_ids: [...]}` | Batch Primo discovery URLs |
| `GET /metadata/records/{mms_id}/primo` | — | Single Primo URL |

## 7. Usage Guide

### For Librarians

**Starting the system:**
```bash
# Terminal 1: Backend
uvicorn app.api.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev
# Opens at http://localhost:5173
```

**Workflow:**
1. **Dashboard** — See coverage gaps at a glance. Click a gap card to drill in.
2. **Workbench** — Browse low-confidence records in a filterable table. Double-click to edit inline. Select rows for batch corrections.
3. **Agent Chat** — Select a field (Place/Date/Publisher/Agent). Click "Analyze" to have the agent find clusters. Click "Investigate" on a cluster. Approve/reject/edit proposals.
4. **Review** — See correction history. Filter by field/source. Export as CSV/JSON.

### For Developers / AI Agents

**Running tests:**
```bash
# Unit tests (fast, no DB needed)
poetry run python -m pytest tests/scripts/metadata/ -v

# API tests (uses test fixtures)
poetry run python -m pytest tests/app/test_metadata_api.py tests/app/test_metadata_corrections.py tests/app/test_agent_chat.py -v

# Integration tests (full workflow)
poetry run python -m pytest tests/integration/ -v

# All metadata tests
poetry run python -m pytest tests/scripts/metadata/ tests/app/test_metadata_api.py tests/app/test_metadata_corrections.py tests/app/test_agent_chat.py tests/integration/ -v
```

**CLI tools:**
```bash
# Run coverage audit
poetry run python -m scripts.metadata.audit data/index/bibliographic.db --output data/metadata/baseline_audit.json

# Apply a correction
poetry run python -m scripts.metadata.feedback_loop \
  --field place --raw "Lugduni Batavorum" --canonical leiden \
  --db data/index/bibliographic.db

# Check coverage delta
poetry run python -m scripts.metadata.feedback_loop \
  --coverage-delta place --db data/index/bibliographic.db
```

**Environment variables:**
| Variable | Purpose | Default |
|----------|---------|---------|
| `BIBLIOGRAPHIC_DB_PATH` | Path to M3 SQLite database | `data/index/bibliographic.db` |
| `OPENAI_API_KEY` | Required for agent LLM proposals | — |
| `PRIMO_BASE_URL` | Primo discovery base URL | TAU Primo URL |

## 8. Extension Guide (For AI Agents)

### Adding a New Specialist Agent

1. Create `scripts/metadata/agents/<field>_agent.py`
2. Follow the pattern in `place_agent.py`:
   - Accept `AgentHarness` in constructor
   - Implement `analyze()`, `get_clusters()`, `propose_mappings(cluster)`
   - Use `self.harness.grounding` for DB queries
   - Use `self.harness.reasoning.propose_mapping()` for LLM calls
3. Add the agent to the factory in `app/api/metadata.py` (`_create_specialist_agent`)
4. Add tests at `tests/scripts/metadata/agents/test_<field>_agent.py`
5. Update the frontend field selector tabs

### Adding a New API Endpoint

1. Add the route to `app/api/metadata.py`
2. Add Pydantic models to `app/api/metadata_models.py`
3. Add the fetch function to `frontend/src/api/metadata.ts`
4. Add the TypeScript type to `frontend/src/types/metadata.ts`
5. Add a TanStack Query hook to `frontend/src/hooks/useMetadata.ts`
6. Write tests in `tests/app/`

### Improving Normalization Coverage

1. Run audit: `python -m scripts.metadata.audit <db_path> --output audit.json`
2. Identify highest-impact gaps (sort by frequency)
3. For places/publishers: add entries to alias map JSON files
4. For dates: improve patterns in `scripts/marc/normalize.py`
5. For agents: add authority URI enrichment via `scripts/enrichment/`
6. Apply via feedback loop or re-run pipeline: `python -m scripts.marc.rebuild_pipeline`

### Key Invariants (Do Not Break)

- **Raw values are never destroyed** — alias maps add mappings, they don't modify originals
- **Alias map writes are atomic** — always `.tmp` + `os.replace()`
- **Rejected proposals are never re-proposed** — check `review_log.is_rejected()` before proposing
- **Confidence scores have meaning** — 0.95 = alias map match, 0.80 = base cleaning, <0.50 = unreliable
- **LLM is reasoning layer, not authority** — grounding layer provides evidence, LLM proposes, human decides
- **Tests must pass** — 534 tests cover the full stack; run them before any change
