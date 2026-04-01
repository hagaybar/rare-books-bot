# Metadata Co-pilot Workbench

## Overview

The Metadata Co-pilot Workbench is an agent-driven Human-In-The-Loop (HITL) system for improving bibliographic metadata quality in the rare books collection. It combines automated analysis with specialist AI agents and librarian expertise to systematically find and fix normalization gaps in MARC-derived metadata.

**Why it exists:** The M2 normalization pipeline handles common cases well, but rare books contain unusual place names (Latin toponyms, Hebrew transliterations), ambiguous dates (Hebrew calendar, approximate ranges), and variant publisher forms that require domain expertise. The Workbench surfaces these gaps, lets librarians collaborate with specialist agents to resolve them, and feeds corrections back into the normalization pipeline -- permanently improving coverage.

**Key principle:** Every correction is grounded in evidence. Raw MARC values are never destroyed. Corrections create new alias mappings that augment the existing normalization rules.

## Getting Started

### Prerequisites

- Python 3.10+ with dependencies installed (`poetry install`)
- Node.js 18+ and npm (for the React frontend)
- OpenAI API key for agent conversations
- Bibliographic database at `data/index/bibliographic.db` (built via `python -m app.cli index`)

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OPENAI_API_KEY` | Yes (for agents) | -- | Powers specialist agent conversations |
| `BIBLIOGRAPHIC_DB_PATH` | No | `data/index/bibliographic.db` | Path to the SQLite bibliographic index |
| `PRIMO_BASE_URL` | No | -- | Base URL for Primo catalog links (e.g., `https://primo.nli.org.il`) |
| `SESSIONS_DB_PATH` | No | `data/chat/sessions.db` | Path to the chat sessions database |

### Starting the System

**Terminal 1 -- API server:**
```bash
export OPENAI_API_KEY="sk-..."
uvicorn app.api.main:app --reload
# Server starts at http://localhost:8000
# API docs at http://localhost:8000/docs
```

**Terminal 2 -- React frontend:**
```bash
cd frontend
npm install    # first time only
npm run dev
# Frontend starts at http://localhost:5173
```

## Librarian Workflow

The Workbench follows a structured workflow from discovery to resolution:

### Step 1: Review the Dashboard

Open the Dashboard page to see coverage statistics across all normalized fields (place, date, publisher). The dashboard shows:

- **Coverage percentage** per field (e.g., "place_norm: 87% mapped")
- **Total unmapped values** and their frequency
- **Method distribution** (how values were normalized: alias map, base cleaning, unparsed)

Focus on fields with the lowest coverage or highest number of unmapped values.

### Step 2: Drill Into Gaps

Click on a field to open the Workbench page showing:

- **Unmapped values** sorted by frequency (highest-impact gaps first)
- **Low-confidence records** where normalization confidence is below threshold
- **Gap clusters** grouping similar unmapped values that likely share a resolution

For example, you might see that "Lugduni Batavorum" appears 15 times unmapped -- resolving this single value improves 15 records.

### Step 3: Chat with a Specialist Agent

Select an unmapped value and open the Agent Chat. The system routes you to the appropriate specialist:

- **PlaceAgent** for place normalization gaps
- **DateAgent** for date parsing issues
- **PublisherAgent** for publisher/printer variants
- **NameAgent** for author/contributor authority matching

The agent provides a grounded suggestion with evidence (historical context, authority references, confidence score). You can ask follow-up questions, request alternatives, or challenge the suggestion.

### Step 4: Approve Corrections

When you agree with a suggestion:

1. Click **Approve** to submit the correction
2. The system records the correction with full audit trail (who, when, what, why)
3. Use **Batch Corrections** for clusters of related values

Each correction creates or updates an entry in the alias map (`data/normalization/place_aliases/place_alias_map.json` for places).

### Step 5: Verify Improvement

After corrections are applied, the feedback loop:

1. Updates the alias map with the new mapping
2. Re-normalizes affected records in the bibliographic database
3. Refreshes coverage statistics

Return to the Dashboard to confirm coverage has improved. The correction history page provides a full audit trail.

## Agent Interaction Examples

### PlaceAgent Conversation

```
Librarian: What is "Lugduni Batavorum"?

PlaceAgent: "Lugduni Batavorum" is the Latin name for Leiden, Netherlands.
This was a major printing center in the 16th-17th centuries, home to
the Elzevir family press and the University of Leiden press.

Suggested mapping:
  raw: "Lugduni Batavorum"
  canonical: "leiden"
  confidence: 0.97
  evidence: Standard Latin toponym, well-attested in bibliographic literature

Librarian: Could it be confused with Lyon (Lugdunum)?

PlaceAgent: Good question. "Lugdunum" alone typically refers to Lyon, France.
The suffix "Batavorum" (of the Batavians) disambiguates this as Leiden.
If you see just "Lugduni" without "Batavorum", that would map to Lyon.

  "Lugduni Batavorum" -> leiden (confidence: 0.97)
  "Lugduni" -> lyon (confidence: 0.90)

Shall I submit "leiden" as the canonical form?
```

### DateAgent Conversation

```
Librarian: How should I interpret the date "[5765]"?

DateAgent: This appears to be a Hebrew calendar year. Converting:
  Hebrew year 5765 = Gregorian year 2004/2005
  (Hebrew years span two Gregorian years since they start in September/October)

Suggested mapping:
  raw: "[5765]"
  date_start: 2004
  date_end: 2005
  method: "hebrew_calendar"
  confidence: 0.95
  note: Brackets indicate date not from title page

Librarian: What about "[תק"ל]"?

DateAgent: This is a Hebrew date in Hebrew numerals.
  תק"ל = 400 + 100 + 30 = 530 (in the current millennium = 5530)
  Hebrew year 5530 = Gregorian year 1769/1770

Suggested mapping:
  raw: "[תק\"ל]"
  date_start: 1769
  date_end: 1770
  method: "hebrew_calendar_numerals"
  confidence: 0.93
```

## Architecture

### Component Diagram

```
+------------------+       +-------------------+       +----------------------+
|  React Frontend  | REST  |  FastAPI Backend   |       |   Grounding Layer    |
|                  |------>|                    |------>|                      |
|  - Dashboard     |       |  app/api/          |       |  - Coverage audit    |
|  - Workbench     |       |    metadata.py     |       |  - Gap detection     |
|  - Agent Chat    |       |    main.py         |       |  - Cluster analysis  |
|  - Review        |       |                    |       |                      |
+------------------+       +--------+-----------+       +----------+-----------+
                                    |                              |
                           +--------v-----------+       +----------v-----------+
                           |  Specialist Agents  |       |    Action Layer      |
                           |                     |       |                      |
                           |  - PlaceAgent       |       |  - Alias map update  |
                           |  - DateAgent        |       |  - Re-normalization  |
                           |  - PublisherAgent   |       |  - Coverage refresh  |
                           |  - NameAgent        |       |  - Audit trail       |
                           +---------------------+       +----------------------+
```

### Data Flow

1. **Audit**: `scripts/metadata/audit.py` scans `bibliographic.db` and computes coverage, gaps, and clusters
2. **API**: `app/api/metadata.py` serves audit results and accepts corrections via REST endpoints
3. **Agents**: `scripts/metadata/agents/` provide domain-specific suggestions grounded in bibliographic knowledge
4. **Feedback Loop**: `scripts/metadata/feedback_loop.py` applies approved corrections:
   - Writes new entries to the alias map JSON
   - Runs M2 re-normalization on affected records
   - Updates coverage statistics in the database
5. **Frontend**: `frontend/` renders the dashboard and provides the interactive correction interface

### Key Files

| Path | Purpose |
|------|---------|
| `app/api/metadata.py` | REST API endpoints (11 routes) |
| `scripts/metadata/audit.py` | Coverage audit and gap detection |
| `scripts/metadata/feedback_loop.py` | Correction application and re-normalization |
| `scripts/metadata/agents/place_agent.py` | Place normalization specialist |
| `scripts/metadata/agents/date_agent.py` | Date normalization specialist |
| `scripts/metadata/agents/publisher_agent.py` | Publisher normalization specialist |
| `scripts/metadata/agents/name_agent.py` | Name authority specialist |
| `data/normalization/place_aliases/place_alias_map.json` | Production place alias map |
| `frontend/` | React SPA source |

## Testing

### Unit Tests

```bash
# Run all metadata-related tests
poetry run python -m pytest tests/scripts/metadata/ -v

# Run specific agent tests
poetry run python -m pytest tests/scripts/metadata/test_place_agent.py -v
poetry run python -m pytest tests/scripts/metadata/test_date_agent.py -v
```

### Integration Tests

```bash
# Run integration tests (requires OPENAI_API_KEY for agent tests)
poetry run python -m pytest tests/integration/ -v

# Run API endpoint tests
poetry run python -m pytest tests/app/test_api.py -k metadata -v
```

### What Tests Cover

- **Audit module**: Coverage calculation, gap detection, cluster grouping
- **Feedback loop**: Alias map updates, re-normalization triggers, audit trail recording
- **Agent responses**: Grounded suggestions, confidence scoring, evidence formatting
- **API endpoints**: Request/response validation, pagination, error handling
- **End-to-end**: Full workflow from gap detection through correction to coverage improvement

### Manual Testing

```bash
# Run a coverage audit against the database
poetry run python -m scripts.metadata.audit data/index/bibliographic.db \
  --output data/metadata/baseline_audit.json

# Test a single correction via the feedback loop
poetry run python -m scripts.metadata.feedback_loop \
  --field place \
  --raw "Lugduni Batavorum" \
  --canonical leiden \
  --db data/index/bibliographic.db

# Test API endpoints directly
curl http://localhost:8000/metadata/coverage
curl "http://localhost:8000/metadata/issues?field=place_norm&limit=10"
curl "http://localhost:8000/metadata/unmapped?field=place_norm&min_freq=5"
```
