# API Layer (CB-002) - Chatbot HTTP Interface

This directory contains the FastAPI application that provides the HTTP interface for the conversational chatbot (M6 milestone).

## Overview

The API layer bridges external clients (web UIs, mobile apps) with the backend query pipeline:

1. Receives natural language queries via HTTP
2. Manages multi-turn conversation sessions
3. Routes queries through M4 query pipeline (compile + execute)
4. Returns structured responses with evidence

## Architecture

```
Client → POST /chat → FastAPI → SessionStore → M4 Pipeline → Response
                                                    ↓
                                             (compile_query + execute_plan)
```

## Files

- `main.py` - FastAPI application with endpoints
- `models.py` - Request/response Pydantic models
- `__init__.py` - Module initialization

## Endpoints

### POST /chat

Send natural language query and get results.

**Request:**
```json
{
  "message": "books published by Oxford between 1500 and 1599",
  "session_id": "optional-session-id",
  "context": {
    "optional": "context data"
  }
}
```

**Response:**
```json
{
  "success": true,
  "response": {
    "message": "Found 15 books matching your query.",
    "candidate_set": {
      "query_text": "books published by Oxford between 1500 and 1599",
      "candidates": [
        {
          "record_id": "990001234",
          "title": "...",
          "match_rationale": "...",
          "evidence": [...]
        }
      ]
    },
    "suggested_followups": ["..."],
    "clarification_needed": null,
    "session_id": "abc-123-def"
  },
  "error": null
}
```

### GET /health

Health check for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "database_connected": true,
  "session_store_ok": true
}
```

### GET /sessions/{session_id}

Get session details and message history.

**Response:**
```json
{
  "session_id": "abc-123-def",
  "user_id": null,
  "created_at": "2026-01-13T10:00:00",
  "updated_at": "2026-01-13T10:05:00",
  "messages": [
    {
      "role": "user",
      "content": "books by Oxford",
      "query_plan": {...},
      "candidate_set": null,
      "timestamp": "2026-01-13T10:00:00"
    },
    {
      "role": "assistant",
      "content": "Found 15 books...",
      "query_plan": {...},
      "candidate_set": {...},
      "timestamp": "2026-01-13T10:00:05"
    }
  ],
  "context": {},
  "metadata": {}
}
```

### DELETE /sessions/{session_id}

Expire a session.

**Response:**
```json
{
  "status": "success",
  "message": "Session abc-123-def expired"
}
```

## Configuration

Environment variables:

- `SESSIONS_DB_PATH` - Path to sessions.db (default: `data/chat/sessions.db`)
- `BIBLIOGRAPHIC_DB_PATH` - Path to bibliographic.db (default: `data/index/bibliographic.db`)
- `OPENAI_API_KEY` - Required for query compilation

## Running the Server

**Development (with auto-reload):**
```bash
uvicorn app.api.main:app --reload
```

**Production:**
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

**Access:**
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- OpenAPI spec: http://localhost:8000/openapi.json

## Testing

**Unit tests (no API key needed):**
```bash
pytest tests/app/test_api.py -v -k "not integration"
```

**Integration tests (requires OPENAI_API_KEY):**
```bash
export OPENAI_API_KEY="sk-..."
pytest tests/app/test_api.py -v --run-integration
```

**Manual testing with curl:**
```bash
# Health check
curl http://localhost:8000/health

# Chat query (creates new session)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}'

# Chat with existing session
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "only from Paris", "session_id": "SESSION_ID_FROM_PREVIOUS_RESPONSE"}'

# Get session details
curl http://localhost:8000/sessions/SESSION_ID

# Expire session
curl -X DELETE http://localhost:8000/sessions/SESSION_ID
```

## Error Handling

The API handles errors gracefully:

- **400 Bad Request** - Invalid query format or validation errors
- **404 Not Found** - Session not found
- **422 Unprocessable Entity** - Pydantic validation errors (e.g., empty message)
- **500 Internal Server Error** - Unexpected errors (logged)
- **503 Service Unavailable** - Database or session store not initialized

## Session Management

Sessions are automatically created if `session_id` not provided. Each session:

- Has unique UUID identifier
- Stores message history (user + assistant messages)
- Tracks context for multi-turn conversations
- Persists to SQLite (`data/chat/sessions.db`)
- Can be expired manually or automatically after 24 hours

## Query Processing Flow

1. **Receive request** - Validate message, get/create session
2. **Compile query** - Use M4 LLM compiler to generate QueryPlan
3. **Execute query** - Run SQL against bibliographic.db, extract evidence
4. **Format response** - Generate natural language message (simple for now, will enhance in CB-003)
5. **Save to session** - Store user message and assistant response
6. **Return** - Send ChatResponse to client

## Next Steps (Phase 1)

After CB-002 (API Layer), the next component is:

**CB-003: Response Formatting** - Convert CandidateSet to natural language responses
- `scripts/chat/formatter.py` module
- More sophisticated response generation
- Evidence citations in readable format
- Zero-results handling
- Suggested follow-up questions

## Dependencies

- FastAPI 0.115.x - Web framework
- Uvicorn 0.34.x - ASGI server
- Pydantic 2.x - Request/response validation
- SQLite - Session persistence and bibliographic database

## Status

✅ **Completed** (2026-01-13)

All Phase 1 deliverables for CB-002 implemented:
- FastAPI application with /chat endpoint
- Session management integration
- M4 query pipeline integration
- Error handling
- Health check endpoint
- Comprehensive tests (9 passing)
