# Metadata Workbench
> Last verified: 2026-04-01
> Source of truth for: Metadata co-pilot workbench architecture, specialist agents, publisher authorities, feedback loop, and HITL correction workflow

## Overview

The Metadata Co-pilot Workbench is an agent-driven Human-In-The-Loop (HITL) system for improving bibliographic metadata quality in the rare books collection. It combines automated analysis with specialist AI agents and librarian expertise to systematically find and fix normalization gaps in MARC-derived metadata.

**Why it exists**: The M2 normalization pipeline handles common cases well, but rare books contain unusual place names (Latin toponyms, Hebrew transliterations), ambiguous dates (Hebrew calendar, approximate ranges), and variant publisher forms that require domain expertise. The Workbench surfaces these gaps, lets librarians collaborate with specialist agents to resolve them, and feeds corrections back into the normalization pipeline -- permanently improving coverage.

**Key principle**: Every correction is grounded in evidence. Raw MARC values are never destroyed. Corrections create new alias mappings that augment the existing normalization rules.

**Current gaps**: 2,740 publishers lack alias maps, 1,185 places are unmapped, 69 dates are unparsed.

---

## Architecture

```
React Frontend (frontend/)
  Dashboard | Workbench | Agent Chat | Review
       |
       | REST API (12 endpoints)
       v
FastAPI Backend (app/api/metadata.py)
  /metadata/coverage | /metadata/issues | /metadata/corrections
  /metadata/clusters | /metadata/agent/chat | /metadata/primo-urls
       |
       +-- Grounding Layer (deterministic, no LLM)
       |     M3 SQLite, Alias Maps, Country Codes, Auth URIs
       |
       +-- Specialist Agents (LLM-assisted, strict prompts)
       |     PlaceAgent, DateAgent, PublisherAgent, NameAgent
       |
       +-- Action Layer (deterministic, no LLM)
             Alias Maps, Review Log, Re-normalize, Coverage Refresh
```

### Layer Responsibilities

| Layer | Purpose | Uses LLM? | Key Principle |
|-------|---------|-----------|---------------|
| **Grounding** | Query DB for gaps, load alias maps, cross-reference evidence | No | Deterministic, fast, no external calls |
| **Reasoning** | Propose canonical mappings, explain clusters, suggest strategies | Yes | Strict prompts, structured JSON, cached responses |
| **Action** | Write alias maps, update DB, log corrections | No | Atomic writes, incremental updates, audit trail |

---

## Librarian Workflow

### Step 1: Review Dashboard

Open the Dashboard to see coverage statistics across all normalized fields (place, date, publisher):
- Coverage percentage per field
- Total unmapped values and their frequency
- Method distribution (alias map, base cleaning, unparsed)

### Step 2: Drill Into Gaps

Click a field to open the Workbench showing:
- Unmapped values sorted by frequency (highest-impact gaps first)
- Low-confidence records below threshold
- Gap clusters grouping similar unmapped values

### Step 3: Chat with Specialist Agent

Select an unmapped value and open Agent Chat. The system routes to the appropriate specialist. The agent provides grounded suggestions with evidence (historical context, authority references, confidence score). Follow-up questions, alternatives, and challenges are supported.

### Step 4: Approve Corrections

Click **Approve** to submit. The system records the correction with full audit trail. Use **Batch Corrections** for clusters of related values.

### Step 5: Verify Improvement

The feedback loop: updates alias map -> re-normalizes affected records -> refreshes coverage statistics. Return to Dashboard to confirm improvement.

---

## Specialist Agents

### Agent Roster

| Agent | File | Domain Knowledge |
|-------|------|-----------------|
| **PlaceAgent** | `scripts/metadata/agents/place_agent.py` | Latin toponyms (genitive/nominative/ablative), Hebrew/Arabic script detection, MARC country code cross-referencing |
| **DateAgent** | `scripts/metadata/agents/date_agent.py` | Hebrew Gematria (e.g., tav-kuf-ayin = 1810), partial centuries, Latin date conventions (Anno, MDCCC) |
| **PublisherAgent** | `scripts/metadata/agents/publisher_agent.py` | Printer dynasties, "ex officina/typis/apud" Latin formulae, s.n./sine nomine detection |
| **NameAgent** | `scripts/metadata/agents/name_agent.py` | VIAF/NLI/LCNAF authority matching, "Last, First" / "First Last" normalization, authority URI validation |

### How Agents Work

Each agent follows the same two-layer pattern:

**Grounding (deterministic, no LLM)**:
1. Query DB for gaps in its field (confidence <= threshold)
2. Load alias map for vocabulary context
3. Cross-reference evidence (country codes, authority URIs)
4. Cluster values by pattern/script/frequency

**Reasoning (LLM-assisted, strict prompts)**:
1. Build system prompt with: role, existing vocabulary, evidence, raw value
2. Call OpenAI API (gpt-4o default) with structured JSON response
3. Parse response into ProposedMapping
4. Cache in `data/metadata/agent_llm_cache.jsonl`
5. Check review log -- never re-propose rejected mappings

### Agent Interaction Examples

**PlaceAgent**:
```
Librarian: What is "Lugduni Batavorum"?

PlaceAgent: "Lugduni Batavorum" is the Latin name for Leiden, Netherlands.
This was a major printing center in the 16th-17th centuries, home to
the Elzevir family press and the University of Leiden press.

Suggested mapping:
  raw: "Lugduni Batavorum"  ->  canonical: "leiden"
  confidence: 0.97
  evidence: Standard Latin toponym, well-attested in bibliographic literature
```

**DateAgent**:
```
Librarian: How should I interpret the date "[5765]"?

DateAgent: This appears to be a Hebrew calendar year. Converting:
  Hebrew year 5765 = Gregorian year 2004/2005
  raw: "[5765]"  ->  date_start: 2004, date_end: 2005
  method: "hebrew_calendar", confidence: 0.95
```

---

## API Endpoints

### Coverage and Analysis

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/metadata/coverage` | Full CoverageReport (all fields, confidence bands, methods, flagged items) |
| GET | `/metadata/issues` | Paginated low-confidence records (params: field, max_confidence, limit, offset) |
| GET | `/metadata/unmapped` | Frequency-sorted unmapped values (params: field, min_freq) |
| GET | `/metadata/clusters` | Gap clusters sorted by priority_score (params: field) |
| GET | `/metadata/methods` | Method distribution by count and percentage (params: field) |

### Corrections

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/metadata/corrections` | Submit single correction: field, raw_value, canonical_value, evidence, source |
| POST | `/metadata/corrections/batch` | Batch corrections with per-item results and totals |
| GET | `/metadata/corrections/history` | Paginated correction audit trail (params: field, limit, offset) |

### Agent and Discovery

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/metadata/agent/chat` | Agent conversation: field, message, optional session_id |
| POST | `/metadata/primo-urls` | Batch Primo discovery URLs from MMS IDs |
| GET | `/metadata/records/{mms_id}/primo` | Single Primo URL for a record |
| GET | `/metadata/publishers` | Publisher authority records (params: type filter) |

---

## Publisher Authority Records

Internal publisher identification system for the rare books collection.

### Database Tables

- **`publisher_authorities`**: Canonical publisher identities (227 records: 202 unresearched, 18 printing houses, 3 bibliophile societies, 2 unknown markers, 1 modern publisher, 1 private press)
- **`publisher_variants`**: Name forms linking to authorities (265 variants across Latin, Hebrew, and other scripts)

### Key Properties

- Every authority has at least one variant; every variant references a valid authority
- Confidence scores are always set (never null), range 0.0-1.0
- Missing-marker records (e.g., "publisher unknown", "privatdruck") flagged with `is_missing_marker = 1`
- 834 imprints currently matchable via variant forms

### Usage

```python
from scripts.metadata.publisher_authority import PublisherAuthorityStore
store = PublisherAuthorityStore(Path("data/index/bibliographic.db"))
authority = store.search_by_variant("ex officina elzeviriana")
```

### API

`GET /metadata/publishers` -- list all publisher authorities with variant counts and imprint counts. Optional query parameter: `type` (e.g., `printing_house`, `unresearched`).

---

## Data Flow: The Correction Lifecycle

```
1. AUDIT     -> audit.py queries M3 DB -> CoverageReport
2. CLUSTER   -> clustering.py groups flagged items -> Clusters
3. PROPOSE   -> specialist agent + LLM -> ProposedMapping
4. REVIEW    -> librarian via UI -> Approve / Reject / Edit
5. APPLY     -> feedback_loop.py:
                  -> writes alias map atomically (.tmp + os.replace)
                  -> UPDATE imprints/agents SET *_norm=?, *_confidence=0.95
                  -> appends to review_log.jsonl
6. VERIFY    -> re-run audit -> coverage improved
                rejected proposals logged -> agents won't re-propose
```

### Database Tables Touched

| Table | Read By | Written By |
|-------|---------|------------|
| `imprints` | Audit, GroundingLayer, API | FeedbackLoop (UPDATE *_norm, *_confidence) |
| `agents` | Audit, GroundingLayer, NameAgent | FeedbackLoop (UPDATE agent_norm, agent_confidence) |
| `authority_enrichment` | NameAgent (validate_against_authority) | Not written by workbench |
| `records` | GroundingLayer (mms_id lookups) | Not written by workbench |
| `publisher_authorities` | PublisherAuthorityStore, API | PublisherAuthorityStore.create/update |
| `publisher_variants` | PublisherAuthorityStore | PublisherAuthorityStore.create/add_variant |

### Alias Map Files

| File | Used By | Written By |
|------|---------|------------|
| `data/normalization/place_aliases/place_alias_map.json` | PlaceAgent, normalize.py | FeedbackLoop, corrections API |
| `data/normalization/publisher_aliases/publisher_alias_map.json` | PublisherAgent | FeedbackLoop, corrections API |
| `data/normalization/agent_aliases/agent_alias_map.json` | NameAgent | FeedbackLoop, corrections API |

---

## Key Files

### Backend (~3,700 lines Python)

| Path | Purpose |
|------|---------|
| `scripts/metadata/audit.py` | Coverage audit and gap detection (533 lines) |
| `scripts/metadata/clustering.py` | Gap clustering by script/pattern/frequency (730 lines) |
| `scripts/metadata/agent_harness.py` | GroundingLayer + ReasoningLayer + AgentHarness (638 lines) |
| `scripts/metadata/feedback_loop.py` | Correction application and re-normalization (518 lines) |
| `scripts/metadata/review_log.py` | Append-only JSONL audit trail (218 lines) |
| `scripts/metadata/agents/place_agent.py` | Place normalization specialist (362 lines) |
| `scripts/metadata/agents/date_agent.py` | Date normalization specialist (365 lines) |
| `scripts/metadata/agents/publisher_agent.py` | Publisher normalization specialist (325 lines) |
| `scripts/metadata/agents/name_agent.py` | Name authority specialist (554 lines) |

### API Layer (~1,700 lines Python)

| Path | Purpose |
|------|---------|
| `app/api/metadata.py` | 12 REST endpoints + agent chat (1,362 lines) |
| `app/api/metadata_models.py` | 25 Pydantic response models (328 lines) |

### Frontend (~15 files TypeScript/React)

Key pages: Dashboard, Workbench, AgentChat, Review, Publishers.

---

## Testing

### Unit Tests

```bash
# All metadata tests
poetry run python -m pytest tests/scripts/metadata/ -v

# Specific agent tests
poetry run python -m pytest tests/scripts/metadata/test_place_agent.py -v
poetry run python -m pytest tests/scripts/metadata/test_date_agent.py -v
poetry run python -m pytest tests/scripts/metadata/test_publisher_agent.py -v
```

### Integration Tests

```bash
# Full workflow tests (requires OPENAI_API_KEY for agent tests)
poetry run python -m pytest tests/integration/ -v

# API endpoint tests
poetry run python -m pytest tests/app/test_api.py -k metadata -v
```

### Publisher Authority Tests

```bash
# Unit tests (in-memory DB)
poetry run python -m pytest tests/scripts/metadata/test_publisher_authority.py -v

# Integration tests (real DB)
poetry run python -m pytest tests/integration/test_publisher_authority.py -v
```

### Test Coverage (~534 tests)

- audit.py: 41 tests
- clustering.py: 71 tests
- agent_harness.py: 46 tests
- feedback_loop.py: 30 tests
- review_log.py: 28 tests
- place_agent.py: 40 tests
- date_agent.py: 45 tests
- publisher_agent.py: 59 tests
- name_agent.py: 61 tests
- metadata_api.py: 53 tests
- metadata_corrections.py: 25 tests
- agent_chat.py: 18 tests
- integration/metadata_workbench.py: 17 tests

---

## Quick Start

```bash
# Terminal 1: API server
export OPENAI_API_KEY="sk-..."
uvicorn app.api.main:app --reload

# Terminal 2: React frontend
cd frontend && npm install && npm run dev
# Opens at http://localhost:5173

# Run coverage audit
poetry run python -m scripts.metadata.audit data/index/bibliographic.db \
  --output data/metadata/baseline_audit.json

# Apply a correction via CLI
poetry run python -m scripts.metadata.feedback_loop \
  --field place --raw "Lugduni Batavorum" --canonical leiden \
  --db data/index/bibliographic.db

# Check coverage delta
poetry run python -m scripts.metadata.feedback_loop \
  --coverage-delta place --db data/index/bibliographic.db

# Test API endpoints directly
curl http://localhost:8000/metadata/coverage
curl "http://localhost:8000/metadata/issues?field=place_norm&limit=10"
curl "http://localhost:8000/metadata/unmapped?field=place_norm&min_freq=5"
```

---

## Key Invariants (Do Not Break)

- **Raw values are never destroyed** -- alias maps add mappings, they don't modify originals
- **Alias map writes are atomic** -- always `.tmp` + `os.replace()`
- **Rejected proposals are never re-proposed** -- check `review_log.is_rejected()` before proposing
- **Confidence scores have meaning** -- 0.95 = alias map match, 0.80 = base cleaning, <0.50 = unreliable
- **LLM is reasoning layer, not authority** -- grounding layer provides evidence, LLM proposes, human decides
- **Tests must pass** -- run the full test suite before any change

---

## Extension Guide

### Adding a New Specialist Agent

1. Create `scripts/metadata/agents/<field>_agent.py`
2. Follow the pattern in `place_agent.py`: accept `AgentHarness`, implement `analyze()`, `get_clusters()`, `propose_mappings(cluster)`
3. Add to the factory in `app/api/metadata.py` (`_create_specialist_agent`)
4. Add tests at `tests/scripts/metadata/agents/test_<field>_agent.py`
5. Update the frontend field selector tabs

### Improving Normalization Coverage

1. Run audit: `python -m scripts.metadata.audit <db_path> --output audit.json`
2. Identify highest-impact gaps (sort by frequency)
3. For places/publishers: add entries to alias map JSON files
4. For dates: improve patterns in `scripts/marc/normalize.py`
5. For agents: add authority URI enrichment via `scripts/enrichment/`
6. Apply via feedback loop or re-run pipeline
