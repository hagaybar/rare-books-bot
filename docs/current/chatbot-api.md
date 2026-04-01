# Chatbot API
> Last verified: 2026-04-01
> Source of truth for: HTTP chat endpoints, session management, response formatting, clarification flow, and API configuration

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
| `OPENAI_API_KEY` | (required) | Required for query compilation |

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

## Response Formatting

Natural language response formatting for conversational interfaces.

### Implementation

**File**: `scripts/chat/formatter.py`

### Key Functions

| Function | Purpose |
|----------|---------|
| `format_for_chat(candidate_set) -> str` | Main formatting: CandidateSet to conversational response with evidence |
| `format_summary(candidate_set) -> str` | Brief one-line summary |
| `generate_followups(candidate_set, query_text) -> List[str]` | Context-aware follow-up suggestions |
| `format_evidence(evidence_list) -> str` | Evidence as readable bullet points |

### Features

- Natural language summaries: "Found X books matching your query"
- Evidence formatted as bullet points with confidence scores
- Context-aware follow-up question suggestions
- Zero-results handling with broadening suggestions
- Multi-result formatting with configurable detail limits

### Integration

- Used by API layer (`app/api/main.py`) to format responses
- Automatically generates `suggested_followups` for ChatResponse
- Provides evidence citations in readable format

### Example Output

```
Found 2 books matching your query.
Query: "books published by Oxford between 1500 and 1599"

Showing details for 2 of 2 results:

1. Record: 990001234
   Match: publisher_norm='oxford' AND year_range overlaps 1500-1599
   Evidence:
     - publisher_norm matches 'oxford' (confidence: 95%) [marc:264$b[0]]
     - date_start is 1550 (matches range) (confidence: 99%) [marc:264$c[0]]

2. Record: 990005678
   ...
```

---

## Clarification Flow

Ambiguity detection and clarification prompts for improved query success.

### Implementation

**File**: `scripts/chat/clarification.py`

### Key Functions

| Function | Purpose |
|----------|---------|
| `detect_ambiguous_query(plan, result_count) -> (bool, reason)` | Detect ambiguity |
| `generate_clarification_message(plan, reason) -> str` | Create helpful prompt |
| `suggest_refinements(plan) -> List[str]` | Specific refinement suggestions |
| `should_ask_for_clarification(plan, result_count) -> bool` | Main entry point |

### Ambiguity Detection Criteria

| Criterion | Condition | Reason Code |
|-----------|-----------|-------------|
| Empty filters | Query has no specific filters | `empty_filters` |
| Low confidence | Filters have confidence < 0.7 | `low_confidence` |
| Broad date range | Date range > 200 years | `broad_date_range` |
| Vague queries | Single-word subject/title | `vague_query` |
| Zero results | No matches found | `zero_results` |

### Integration with API

The `/chat` endpoint checks for ambiguity at two points:

1. **After query compilation** (before execution): If the QueryPlan has empty filters or low confidence, return early with a clarification prompt.
2. **After execution** (for zero results): If no matches are found, suggest broadening the query.

The `clarification_needed` field in ChatResponse is set when clarification is needed.

### Example Flow

```
User: "books"

Compile query -> QueryPlan: { filters: [] }  (empty filters)
Detect ambiguity -> reason: "empty_filters"
Generate clarification ->

Response: {
  "message": "I need some clarification to search effectively.",
  "clarification_needed": "I need more details to search effectively. Could you specify:
    - What topic or subject are you interested in?
    - A specific publisher, author, or printer?
    - A time period or date range?
    - A place of publication?"
}
```

### Features

- Detects 5 types of ambiguity
- Context-aware suggestions (suggests missing filter types)
- Prioritizes specificity (narrow date ranges, specific terms)
- Graceful zero-results handling (broadening suggestions)
- Context-specific guidance based on reason code

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
