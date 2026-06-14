# Chatbot API
> Last verified: 2026-06-13
> Source of truth for: HTTP chat endpoints, model comparison, session management, Hebrew/bilingual support, clarification flow, and API configuration

## Overview

The FastAPI application in `app/api/` provides the HTTP interface for the conversational chatbot. It integrates session management, query compilation (M4), response formatting, and ambiguity detection into a unified conversational experience.

---

## API Endpoints

### POST /chat

Send a natural language query, get results.

**Request**:
```json
{
  "message": "books published by Oxford between 1500 and 1599",
  "session_id": "optional-uuid",
  "context": {}
}
```

**Response**:
```json
{
  "success": true,
  "response": {
    "session_id": "uuid",
    "message": "Found 2 books matching your query...",
    "candidate_set": { ... },
    "suggested_followups": [],
    "clarification_needed": null
  },
  "error": null
}
```

- Creates new session if `session_id` not provided
- Automatically routes through M4 query pipeline (compile + execute)
- Returns clarification prompt if query is ambiguous (see Clarification Flow below)
- `response.metadata.message_db_id` carries the backend `chat_messages.id` of the persisted assistant message (also on clarification responses); the frontend uses it to report a specific message via `POST /feedback`. The WebSocket `complete` event carries the same value as a top-level `message_db_id` field (see docs/current/streaming.md)

### POST /chat/compare

Run the same query through multiple interpreter+narrator model configurations side-by-side for evaluation.

**File**: `app/api/compare.py`

**Request**:
```json
{
  "message": "Hebrew books printed in Venice",
  "configs": [
    {"interpreter": "gpt-4.1-mini", "narrator": "gpt-4.1-mini"},
    {"interpreter": "gpt-4.1", "narrator": "gpt-4.1"}
  ],
  "token_saving": true
}
```

**Response**:
```json
{
  "comparisons": [
    {
      "config": {"interpreter": "gpt-4.1-mini", "narrator": "gpt-4.1-mini"},
      "response": { "message": "...", "candidate_set": {...}, ... },
      "metrics": {"latency_ms": 2340, "cost_usd": 0.0012, "tokens": {"input": 850, "output": 420}},
      "error": null
    }
  ]
}
```

- Up to 3 model configurations per request
- Runs pipelines sequentially for accurate per-config metrics
- Rate limited to 10 req/min (requires 'full' role authentication)

### GET /chat/history

Get chat history for the authenticated user.

### GET /health

Health check for monitoring.

```json
{
  "status": "healthy",
  "database_connected": true,
  "session_store_ok": true
}
```

### GET /sessions/{session_id}

Get session details and message history.

### DELETE /sessions/{session_id}

Expire a session.

### POST /feedback

Report a problematic chat message or general feedback ("mark as problematic"). Reports become slim GitHub issues in the public feedback repo; the full debug payload (every session turn with its `query_plan` + `candidate_set`) stays server-side at `data/feedback/<report_id>.json`.

**File**: `app/api/feedback_routes.py` (store: `scripts/feedback/report_store.py`, GitHub: `scripts/feedback/github_client.py`)

**Request**:
```json
{
  "kind": "message",
  "session_id": "uuid",
  "message_id": 42,
  "comment": "optional tester comment"
}
```

**Kind rules**:
- `kind: "message"` -- `session_id` + `message_id` (the backend `chat_messages.id`, exposed as `metadata.message_db_id`) required; comment optional
- `kind: "general"` -- comment required; `session_id` optional (attached for context when present)
- Violations are rejected with 422 (Pydantic model validation)

**Response**:
```json
{
  "report_id": "fb_20260612T101500Z_a1b2c3",
  "github_issue_url": "https://github.com/hagaybar/rare-books-bot/issues/17"
}
```

**Save-first semantics**: the report row (`feedback_reports` in sessions.db) and payload JSON are persisted *before* any GitHub call. Issue creation is best-effort: if `GITHUB_TOKEN` is unset or the API call fails, the report stays `sync_status='pending'` and `github_issue_url` is `null`. Each successful POST also piggybacks a retry of up to 3 oldest pending reports.

- Requires `limited` role or higher (same gate as POST /chat)
- Ownership: non-admin users may only report their own sessions (403 otherwise; 404 for unknown sessions)
- Rate limited to 5 reports/min/user (429 when exceeded)
- Every report is audit-logged (`feedback_report` action)
- Payload assembly failure never loses the report: the row + comment are saved and the error is noted in the payload JSON

### GET /feedback

Admin only. List all feedback reports (newest first, limit 100) including `sync_status` (`pending`/`synced`) and GitHub issue URL/number.

### POST /feedback/sync

Admin only. Retry GitHub issue creation for all pending reports.

**Response**: `{"synced": 2, "remaining": 0}`

---

## Configuration

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `SESSIONS_DB_PATH` | `data/chat/sessions.db` | Path to sessions database |
| `BIBLIOGRAPHIC_DB_PATH` | `data/index/bibliographic.db` | Path to bibliographic database |
| `OPENAI_API_KEY` | (required) | Required for LLM calls (used by litellm) |
| `GITHUB_TOKEN` | (unset) | Optional -- enables /feedback GitHub issue sync; without it reports stay `pending` |
| `FEEDBACK_REPO` | `hagaybar/rare-books-bot` | Target repo for feedback issues |
| `FEEDBACK_DIR` | `data/feedback` | Directory for full report payload JSON files |

---

## Session Management

Multi-turn conversation support with persistent state.

### Implementation

| File | Purpose |
|------|---------|
| `scripts/chat/session_store.py` | SessionStore class -- CRUD for sessions and messages |
| `scripts/chat/models.py` | Data models: ChatSession, Message, ChatResponse |
| `data/chat/sessions.db` | SQLite database with `chat_sessions` and `chat_messages` tables |

### Database Schema

- **`chat_sessions`**: session_id, user_id, created_at, updated_at, expired_at, context (JSON)
- **`chat_messages`**: message_id, session_id, role, content, query_plan (JSON), candidate_set (JSON), created_at

### Python API

```python
from pathlib import Path
from scripts.chat.session_store import SessionStore
from scripts.chat.models import Message

store = SessionStore(Path("data/chat/sessions.db"))

# Create session
session = store.create_session(user_id="user123")

# Add messages
user_msg = Message(role="user", content="Find books by Oxford")
store.add_message(session.session_id, user_msg)

assistant_msg = Message(
    role="assistant",
    content="Found 15 books by Oxford University Press",
    candidate_set=candidate_set
)
store.add_message(session.session_id, assistant_msg)

# Retrieve session
session = store.get_session(session_id)
for msg in session.messages:
    print(f"[{msg.role}] {msg.content}")

# Update context (carry-forward state)
store.update_context(session.session_id, {
    "last_publisher": "Oxford",
    "last_result_count": 15
})

# Session lifecycle
sessions = store.list_user_sessions("user123")
store.expire_session(session_id)
expired_count = store.expire_old_sessions(max_age_hours=24)
```

### CLI Commands

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

### Performance

- Session retrieval: sub-100ms for sessions with <100 messages
- Concurrent users: SQLite supports 100+ concurrent read sessions
- Database size: ~10KB per session + ~2KB per message
- Indexed on session_id and user_id for fast lookups

### Maintenance

```bash
# Nightly cron to expire old sessions
0 2 * * * cd /path/to/project && python -m app.cli chat-cleanup --max-age-hours 24

# Backup
cp data/chat/sessions.db data/chat/sessions_backup_$(date +%Y%m%d).db
```

### Security

- User isolation: sessions filtered by user_id
- Data retention: expired sessions remain (soft delete)
- Access control: application-level (JWT authentication)

---

## Scholar Pipeline (Interpret → Execute → Narrate)

The chat endpoint uses a three-stage scholar pipeline instead of direct query compilation:

### Pipeline Stages

| Stage | File | Purpose |
|-------|------|---------|
| **Interpret** | `scripts/chat/interpreter.py` | NL query → `InterpretationPlan` (via litellm, default model: gpt-4.1-mini) |
| **Execute** | `scripts/chat/executor.py` | `InterpretationPlan` → `ExecutionResult` (SQL against bibliographic.db) |
| **Narrate** | `scripts/chat/narrator.py` | `ExecutionResult` → natural language narrative (via litellm) |

### Model Configuration

Models are configurable per pipeline stage via `scripts/models/config.py`:
- **Config file**: `data/eval/model-config.json` maps stage names to model IDs
- **Default**: gpt-4.1-mini for interpreter (switched from gpt-4.1 based on benchmark: 5x cheaper, +31% accuracy)
- **Override**: The `/chat/compare` endpoint allows per-request model selection

### Hebrew and Bilingual Support

The interpreter includes dedicated handling for Hebrew queries:
- Subject headings are searchable in both English and Hebrew (3,094+ bilingual headings)
- Hebrew terms are used directly in SUBJECT and TITLE filters
- Collection/provenance queries use corporate agents (e.g., "the Faitlovitch collection" → `agent_norm CONTAINS` + `agent_type EQUALS corporate`)
- The narrator answers in the language of the user's query (Hebrew question → Hebrew answer, both REST and streaming paths); bibliographic titles, imprints, and names stay in their original language/script
- The narrator uses ONLY links present in the grounding data and never constructs, guesses, or completes a URL (e.g. Primo search links, Wikidata/Wikipedia URLs). This guardrail was added 2026-06-14 after the narrator gold eval found URL fabrication to be the dominant fabrication mode (see `qa-framework.md`).
- **Active narrator model: `gpt-5-mini`** (since 2026-06-14, selected via the narrator gold-standard eval — highest grounded quality at ~75% lower cost than gpt-4.1). It is a reasoning model, called with `reasoning_effort="low"`.

### Enriched Narrator Context

The executor provides the narrator with rich grounding data beyond basic record fields:

- **Confidence scores**: Date, place, and publisher confidence on each record. The narrator qualifies uncertain attributions (e.g., "circa", "possibly printed in").
- **Publisher details**: Type, dates active, location, and external IDs from `publisher_authorities`. Enables descriptions like "printed by Aldine Press (Venice, active 1495-1515)".
- **Hebrew subjects**: Bilingual subject headings (`subjects_he`). The narrator includes Hebrew equivalents alongside English terms.
- **Agent images and aliases**: Wikipedia portrait URLs and Hebrew name variants from `agent_aliases`.
- **Auto-discovered connections**: When 2-10 agents appear in results and no explicit `find_connections` step was planned, the executor auto-queries `cross_reference.find_connections()` and passes relationship hints to the narrator.
- **Title variants**: Uniform and variant titles shown as "Also known as: ..."
- **Expanded notes**: Notes from MARC tags 504 (bibliography), 505 (contents), and 590 (shelf marks) in addition to 500/520.
- **Truncation feedback**: When results are truncated, the narrator is told "Showing N of M total records" and instructed to acknowledge this to the user.
- **Aggregation honesty** (issue #42): every `aggregate` step computes a companion `COUNT(DISTINCT)` so `AggregationResult` carries `distinct_values` and `facets_truncated` alongside the top-K facets. `GroundingData.aggregation_meta` forwards these per field, and both narrator prompt builders render "N distinct values total — showing top K" on every aggregation block. Evidence rule 12 instructs the narrator to answer "how many X?" from N (never by counting visible facets) and to treat bracketed values like `[sine nomine]` as unattributed-record counts, not real entities.
- **Unsupported aggregation field** (issue #57, seam audit B9): `_handle_aggregate` raises a `PlanValidationError` when the requested field is not in the supported `field_map` (after alias normalization). `_execute_step` converts this into a `StepResult` with `status="error"` and an explicit `error_message` ("Unsupported aggregation field: ... Supported fields: ..."). This replaces the prior silent-empty `AggregationResult`, which was indistinguishable from a genuine "0 records" result and violated the answer contract's evidence requirement. Supported fields are unchanged.
- **Concept fan-out transparency** (issue #47): when the Interpreter expands one user concept (e.g. "cartography") into several topical retrieve steps on *different* terms (subject `geography`, physical_desc `maps`, title `atlas`), each step strict-matches so its per-`RecordSet.relaxations` stays empty — the broadening is invisible at the executor's relaxation-ladder level. `execute_plan` now detects this fan-out (`_concept_fanout_note`: 2+ `retrieve` steps, each carrying exactly one topical CONTAINS filter, across ≥2 distinct terms) and appends a note to `GroundingData.broadening_notes` ("explored related topics: geography, maps, atlas"). Both narrator prompt builders render a "SEARCH BROADENING (disclose to the user)" block from it. Single-topic queries (and repeated-same-term retrieves) produce no note and are unchanged.
- **Semantic concept-count (`resolve_subject_concept`)** (semantic subject search, Phase 1): fixes the held-set concept-count defect where "how many in philosophy?" answered `0` because no literal subject heading equals the word "philosophy". The Interpreter routes a topical "how many in ‹concept›?" over a held set to a `resolve_subject_concept(concept)` step followed by a `retrieve(subject IN $step)` scoped to `$previous_results` (intent `explore-in-set`, so the held set is unchanged). `_handle_resolve_subject_concept` calls the model-backed resolver (see Architecture: `subject_concept_resolver` + `onnx_embedder`), which maps the concept to the collection's **real** catalogued `subjects.value` headings via cosine similarity (≥ 0.84, top-K 40) over precomputed embeddings — then attaches a transparent per-heading `record_count` (COUNT of records carrying that exact heading, *within the held set* when one is in scope) and returns a `ResolvedHeadings` step output. **Embeddings only expand the concept into headings; records still match exactly on those headings, so the count stays evidential.** The matched headings (+ counts) are pushed to `GroundingData.broadening_notes` via `_matched_headings_note`, and the narrator MUST cite them ("counted via: *Jewish philosophy* (8), *Philosophy and religion* (2)…") and MUST NOT fabricate a zero: when the resolver is unavailable (missing model dir or empty `subject_embeddings`, which `get_subject_resolver`/`load_subject_resolver` fail loud on per the loud-failure rule) or nothing clears the threshold, `ResolvedHeadings` is empty and the narrator discloses "no subject headings matched ‹concept› above the confidence threshold" rather than asserting "there are none".

### Features

- LLM-generated narrative summaries with evidence citations
- Confidence-qualified assertions for uncertain dates, places, publishers
- Streaming narrative via WebSocket (see `docs/current/streaming.md`)
- Zero-results handling with broadening suggestions
- Bilingual Hebrew/English subject search

---

## Clarification Flow

Ambiguity detection and clarification prompts are now handled by the interpreter stage.

### Implementation

**File**: `scripts/chat/interpreter.py` (clarification is part of the `InterpretationPlan`)

When the interpreter's confidence is low (<= 0.7) and it sets a `clarification` field, the API short-circuits before execution and returns the clarification directly.

Clarification triggers include garbled/typo terms (e.g. "פילוסופיה חד" → "did you mean פילוסופיה ודת?"); the interpreter is forbidden from silently substituting a different concept for an unreadable term.

**Transparency backstop** (deterministic, `narrator.low_confidence_notice`): when the pipeline *proceeds* at confidence < 0.7 without a clarification, the response opens by stating how the query was interpreted (in the user's language), on both REST and WebSocket paths.

### Integration with API

The `/chat` endpoint checks for clarification after interpretation:

1. **After interpretation** (before execution): If `plan.clarification` is set and `plan.confidence <= 0.7`, return early with a clarification prompt.
2. The `clarification_needed` field in ChatResponse is set when clarification is needed.

### Example Flow

```
User: "books"

Interpret query -> InterpretationPlan: { confidence: 0.3, clarification: "..." }
Short-circuit (confidence < 0.7) ->

Response: {
  "message": "I need some clarification to search effectively...",
  "clarification_needed": "Could you specify a subject, author, date range, or place?"
}
```

---

## Held result set (active subgroup)

After a search, the chat keeps the result the user is looking at as a **held result set** (the session's "active subgroup", issue #60). Follow-up turns can stay scoped to exactly those records instead of searching the whole collection again. This is wired end to end; the lifecycle decision is deterministic and LLM-free (`scripts/chat/subgroup_policy.py`).

### Three-intent model

The interpreter classifies each turn, when a held set is present, into exactly one of three intents and sets step scope accordingly:

| Intent | Example | Scope | Effect on held set |
|--------|---------|-------|--------------------|
| **New search** | "books printed in Venice" | `full_collection` | Replaced by this turn's result |
| **Explore-in-set** | "how many are in Hebrew?", "who printed them?" | `$previous_results` (aggregate / find_connections) | Left unchanged |
| **Refine-in-set** | "only the Hebrew ones", "just those after 1550" | `$previous_results` (retrieve) | Replaced by the narrowed result (progressive drilling) |

Anaphora ("them", "those", "the Hebrew ones") signal explore/refine, not a new search. The interpreter prompt teaches this vocabulary (`scripts/chat/interpreter.py`, FOLLOW-UP section); the held set's size + IDs are rendered into the user-prompt context.

### Scoping reuses `$previous_results`

No new scope keyword was introduced. Scoping reuses the pre-existing reserved keyword **`$previous_results`**, which `executor._resolve_scope` already resolves to `SessionContext.previous_record_ids` (degrading to the full collection when empty). The held set flows into that context on each turn via the load path documented in `architecture.md`.

### Lifecycle (deterministic)

`build_subgroup_update(plan, execution_result, query_text)` decides replace-vs-unchanged from the resulting step shape:
- A turn **redefines** the held set iff it has a `retrieve` step **and** produced a non-empty result (new search or refine-in-set).
- `aggregate`/`find_connections`-only turns (explore-in-set), empty results, and clarification turns leave the held set unchanged.

The held set's `record_ids` are the **full** match set — the deduped union of every `retrieve` step's `mms_ids` (its length equals `total_record_count`), sourced via `held_record_ids(execution_result)`. It is **not** the displayed/truncated subset (the display grounding is capped at 30). This fixes the defect where a counting follow-up over a 74-record search explored only the 30 shown records and answered circularly ("9 of 9").

**Explore vs refine** — the distinction governs both the count and the held set:
- **Explore-in-set** (a counting/facet question like "how many are in Hebrew?") emits a single `aggregate` scoped to `$previous_results`. It aggregates over the **full** held set and leaves it **unchanged** — never a preceding `retrieve` that narrows first (that would count within the narrowed subset and wrongly replace the set).
- **Refine-in-set** ("only the Hebrew ones") emits a `retrieve` scoped to `$previous_results`. It **replaces** the held set with the narrowed match set (progressive drilling).

### Surfacing in the response

- **`ChatResponse.metadata.active_subgroup`** carries a compact summary `{ "defining_query": str, "count": int }` when a set is held, or `null` when none is. Built by `subgroup_summary(...)`; present on both narrative and clarification responses, on REST and WebSocket paths. Drives the frontend "held set" chip.
- **`phase = corpus_exploration`** when the turn was scoped to the held set (`was_scoped_to_held_set(plan)` true). Otherwise the phase stays `query_definition`.
- **Disclosure phrasing** — when the turn is scoped to a held set, the narrator (both `build_lean_narrator_prompt` and `_build_narrator_prompt`) discloses the held-set size and the answer count as **distinct** numbers, phrasing a count/facet as "Of the N you're exploring, X are …". This prevents conflating the two into one figure (the "among the 9, all 9 are Hebrew" circular answer).

### DELETE /sessions/{session_id}/subgroup

Clears the held set for a session — the frontend "Search all" reset calls this.

- Requires `limited` role or higher (same gate as POST /chat); non-admin users may only reset their own sessions (403 otherwise).
- **200** on success, and a **200 no-op** when the session holds no set (clearing is idempotent; `set_active_subgroup(session_id, None)` deletes the row, no separate clear method).
- **404** for an unknown session.

**Response**: `{"status": "success", "message": "Active subgroup cleared"}`

---

## Implementation Status

| Component | Status |
|-----------|--------|
| Session Management (CB-001) | Complete |
| API Layer (CB-002) | Complete |
| Response Formatting (CB-003) | Complete |
| Clarification Flow (CB-004) | Complete |
| Streaming Responses (CB-005) | Complete (see `docs/current/streaming.md`) |
| Basic Rate Limiting (CB-006) | Complete (10 req/min for /chat) |
| Authentication (CB-007) | Postponed |
| Performance Metrics (CB-008) | Postponed |
| Multi-User Isolation (CB-009) | Postponed |

---

## Testing

```bash
# Run API tests (unit tests, no API key needed)
pytest tests/app/test_api.py -v

# Run integration tests (requires OPENAI_API_KEY)
pytest tests/app/test_api.py -v --run-integration
```

### Manual Testing

```bash
# Health check
curl http://localhost:8000/health

# Simple query
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}'

# Multi-turn conversation
RESPONSE=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books about History"}')

SESSION_ID=$(echo $RESPONSE | jq -r '.response.session_id')

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"only from Paris\", \"session_id\": \"$SESSION_ID\"}"

# Ambiguity detection
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books"}'
```

### Troubleshooting

**Session not found**: Session may have expired. Create a new session or omit `session_id`.

**Database locked**: SQLite write lock -- use connection pooling or retry logic with exponential backoff.

**Large message history**: Use `session.get_recent_messages(n=10)` to limit retrieval.
