# Chatbot API
> Last verified: 2026-04-12
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
    "suggested_followups": ["..."],
    "clarification_needed": null
  },
  "error": null
}
```

- Creates new session if `session_id` not provided
- Automatically routes through M4 query pipeline (compile + execute)
- Returns clarification prompt if query is ambiguous (see Clarification Flow below)

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

---

## Configuration

| Environment Variable | Default | Purpose |
|---------------------|---------|---------|
| `SESSIONS_DB_PATH` | `data/chat/sessions.db` | Path to sessions database |
| `BIBLIOGRAPHIC_DB_PATH` | `data/index/bibliographic.db` | Path to bibliographic database |
| `OPENAI_API_KEY` | (required) | Required for LLM calls (used by litellm) |

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

### Enriched Narrator Context

The executor provides the narrator with rich grounding data beyond basic record fields:

- **Confidence scores**: Date, place, and publisher confidence on each record. The narrator qualifies uncertain attributions (e.g., "circa", "possibly printed in").
- **Publisher details**: Type, dates active, location, and external IDs from `publisher_authorities`. Enables descriptions like "printed by Aldine Press (Venice, active 1495-1515)".
- **Hebrew subjects**: Bilingual subject headings (`subjects_he`). The narrator includes Hebrew equivalents alongside English terms.
- **Agent images and aliases**: Wikipedia portrait URLs and Hebrew name variants from `agent_aliases`.
- **Auto-discovered connections**: When 2-10 agents appear in results and no explicit `find_connections` step was planned, the executor auto-queries `cross_reference.find_connections()` and passes relationship hints to the narrator.
- **Title variants**: Uniform and variant titles shown as "Also known as: ..."
- **Expanded notes**: Notes from MARC tags 504 (bibliography), 505 (contents), and 590 (shelf marks) in addition to 500/520.
- **Entity-aware follow-ups**: The narrator receives deterministic hint data (top agents, agents with connections, top subjects) to generate data-driven follow-up suggestions.
- **Truncation feedback**: When results are truncated, the narrator is told "Showing N of M total records" and instructed to acknowledge this to the user.

### Features

- LLM-generated narrative summaries with evidence citations
- Confidence-qualified assertions for uncertain dates, places, publishers
- Entity-aware follow-up suggestions leveraging available connections and subjects
- Streaming narrative via WebSocket (see `docs/current/streaming.md`)
- Zero-results handling with broadening suggestions
- Bilingual Hebrew/English subject search

---

## Clarification Flow

Ambiguity detection and clarification prompts are now handled by the interpreter stage.

### Implementation

**File**: `scripts/chat/interpreter.py` (clarification is part of the `InterpretationPlan`)

When the interpreter's confidence is low (< 0.7) and it sets a `clarification` field, the API short-circuits before execution and returns the clarification directly.

### Integration with API

The `/chat` endpoint checks for clarification after interpretation:

1. **After interpretation** (before execution): If `plan.clarification` is set and `plan.confidence < 0.7`, return early with a clarification prompt.
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
