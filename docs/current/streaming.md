# Streaming Responses
> Last verified: 2026-04-01
> Source of truth for: WebSocket streaming protocol, message types, batch structure, client integration, and chatbot testing procedures

## Overview

The WebSocket endpoint provides real-time streaming for progressive query results and better UX. Instead of waiting for a complete response, clients receive progress updates and result batches as they become available.

**Location**: `app/api/main.py` (`@app.websocket("/ws/chat")`)

---

## WebSocket Protocol

### Connection Flow

1. Client connects to `ws://localhost:8000/ws/chat`
2. Client sends JSON: `{"message": "query text", "session_id": "optional-id"}`
3. Server streams messages in sequence:
   - `session_created` (if new session)
   - `progress` (status updates during processing)
   - `batch` (result batches, up to 10 candidates each)
   - `complete` (final response with full ChatResponse)
4. Connection closes after the complete message

### Message Types

| Type | When Sent | Payload |
|------|-----------|---------|
| `session_created` | New session created | `{ session_id: string }` |
| `progress` | During query processing | `{ message: string }` |
| `batch` | Result batch ready | `{ candidates, batch_num, total_batches, start_idx, end_idx }` |
| `complete` | Processing finished | `{ response: ChatResponse }` |
| `error` | Error occurred | `{ message: string }` (connection closes after) |

### Progress Messages

The server sends progress updates at each processing stage:

1. `"Compiling query..."`
2. `"Executing query with N filters..."`
3. `"Found X results. Formatting response..."`

### Batch Structure

Results are streamed in batches of up to 10 candidates:

```json
{
  "type": "batch",
  "candidates": [...],
  "batch_num": 1,
  "total_batches": 3,
  "start_idx": 0,
  "end_idx": 10
}
```

| Field | Type | Description |
|-------|------|-------------|
| `candidates` | Array | Up to 10 Candidate objects |
| `batch_num` | int | Current batch number (1-indexed) |
| `total_batches` | int | Total number of batches |
| `start_idx` | int | Start index in full result set |
| `end_idx` | int | End index in full result set |

---

## Features

- **Progressive result streaming**: Batches of 10 candidates
- **Real-time progress updates**: Status messages during each processing stage
- **Session creation and reuse**: Creates session if not provided, reuses existing
- **Clarification detection**: Same ambiguity detection as the HTTP `/chat` endpoint
- **Error handling**: Graceful connection closure on errors

---

## Comparison with HTTP /chat

| Feature | HTTP POST /chat | WebSocket /ws/chat |
|---------|-----------------|-------------------|
| Protocol | Single request/response | Persistent connection |
| Streaming | No | Yes (progress + batches) |
| Client complexity | Simple | Moderate |
| Best for | Quick queries, simple clients | Long-running queries, interactive UIs |
| Session handling | Same | Same |
| Clarification flow | Same | Same |

---

## Client Integration

### JavaScript Example

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: "books published by Oxford",
    session_id: existingSessionId  // optional
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'session_created':
      console.log('Session:', data.session_id);
      break;
    case 'progress':
      console.log('Progress:', data.message);
      break;
    case 'batch':
      console.log(`Batch ${data.batch_num}/${data.total_batches}:`, data.candidates);
      // Render candidates incrementally
      break;
    case 'complete':
      console.log('Complete:', data.response);
      // Final response with full ChatResponse
      break;
    case 'error':
      console.error('Error:', data.message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Connection closed');
};
```

---

## Testing the Chatbot (M6)

### Prerequisites

1. Dependencies installed: `poetry install`
2. OpenAI API key set: `export OPENAI_API_KEY="sk-..."`
3. Bibliographic database exists at `data/index/bibliographic.db`

### Starting the Server

```bash
# Development mode (auto-reload on code changes)
uvicorn app.api.main:app --reload

# Server starts at http://localhost:8000
# API docs available at http://localhost:8000/docs
```

### Test 1: Health Check

```bash
curl http://localhost:8000/health

# Expected:
# { "status": "healthy", "database_connected": true, "session_store_ok": true }
```

### Test 2: HTTP Chat Endpoint

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books published by Oxford between 1500 and 1599"}'

# Response includes: session_id, message, candidate_set, followup_questions
```

### Test 3: Multi-Turn Conversation

```bash
# First query creates session
RESPONSE=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books about History"}')

SESSION_ID=$(echo $RESPONSE | jq -r '.response.session_id')

# Second query uses same session
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"only from Paris\", \"session_id\": \"$SESSION_ID\"}"
```

### Test 4: WebSocket Streaming

```bash
# Install wscat: npm install -g wscat
wscat -c ws://localhost:8000/ws/chat

# Send query:
> {"message": "books by Oxford"}

# Watch streaming messages:
# - session_created (with session_id)
# - progress messages ("Compiling query...", "Executing...", "Found X results...")
# - batch messages (groups of 10 candidates)
# - complete message (final response)
```

### Test 5: Ambiguity Detection

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "books"}'

# Response includes: clarification_needed: true, guidance message
```

### Interactive API Documentation

Navigate to `http://localhost:8000/docs` for Swagger UI with:
- Interactive endpoint testing
- Request/response schemas
- Rate limiting info (10 requests/minute per IP)

---

## Automated Tests

```bash
# Run WebSocket tests (4 tests, all passing)
pytest tests/app/test_api.py -k websocket -v

# Run all API tests
pytest tests/app/test_api.py -v
```

---

## What's Working

- Natural language query compilation (via OpenAI)
- SQL query execution against bibliographic database
- Evidence-based responses with MARC field citations
- Formatted responses with follow-up suggestions
- Session-based conversation history
- Real-time streaming with progress updates
- Clarification prompts for ambiguous queries
- Basic rate limiting (10 req/min per IP for /chat)
