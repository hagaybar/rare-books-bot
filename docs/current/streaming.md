# Streaming Responses
> Last verified: 2026-04-12
> Source of truth for: WebSocket streaming protocol, message types, narrative streaming, client integration, and chatbot testing procedures

## Overview

The WebSocket endpoint provides real-time streaming for progressive query results and better UX. Instead of waiting for a complete response, clients receive thinking updates during each pipeline stage and streamed narrative text as it's generated.

**Location**: `app/api/main.py` (`@app.websocket("/ws/chat")`)

---

## WebSocket Protocol

### Connection Flow

1. Client connects to `ws://localhost:8000/ws/chat`
2. Client sends JSON: `{"message": "query text", "session_id": "optional-id"}`
3. Server streams messages in sequence:
   - `session_created` (if new session)
   - `thinking` (status updates during interpret/execute stages)
   - `stream_start` (signals narrative streaming is about to begin)
   - `stream_chunk` (repeated: real-time narrative text from the narrator)
   - `complete` (final response with full ChatResponse)
4. Connection closes after the complete message

### Message Types

| Type | When Sent | Payload |
|------|-----------|---------|
| `session_created` | New session created | `{ session_id: string }` |
| `thinking` | During interpret/execute stages | `{ text: string }` |
| `stream_start` | Before narrative streaming begins | `{}` |
| `stream_chunk` | Each narrative text chunk | `{ text: string }` |
| `complete` | Processing finished | `{ response: ChatResponse }` |
| `error` | Error occurred | `{ message: string }` (connection closes after) |

### Thinking Messages

The server sends thinking updates at each pipeline stage:

1. `"Interpreting your query..."` (Stage 1: interpreter)
2. `"Searching for {filter description}..."` (Stage 2: executor)
3. `"Found N matching records"` (after execution)

### Narrative Streaming

After execution, the narrator generates a natural language response. This is streamed in real time:

1. `stream_start` signals that narrative chunks are about to arrive
2. Multiple `stream_chunk` messages deliver the narrative text incrementally
3. `complete` carries the final `ChatResponse` with the full narrative, candidate set, and metadata

```json
{"type": "stream_start"}
{"type": "stream_chunk", "text": "I found 15 books matching"}
{"type": "stream_chunk", "text": " your query about Oxford..."}
{"type": "complete", "response": { ... }}
```

---

## Features

- **Narrative streaming**: Real-time text chunks from the narrator via `stream_chunk`
- **Thinking updates**: Status messages during interpret and execute stages
- **Session creation and reuse**: Creates session if not provided, reuses existing
- **Clarification detection**: Same ambiguity detection as the HTTP `/chat` endpoint
- **Error handling**: Graceful connection closure on errors

---

## Comparison with HTTP /chat

| Feature | HTTP POST /chat | WebSocket /ws/chat |
|---------|-----------------|-------------------|
| Protocol | Single request/response | Persistent connection |
| Streaming | No | Yes (thinking + narrative chunks) |
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
    case 'thinking':
      console.log('Thinking:', data.text);
      break;
    case 'stream_start':
      console.log('Narrative streaming started');
      break;
    case 'stream_chunk':
      // Append text chunk to UI incrementally
      process.stdout.write(data.text);
      break;
    case 'complete':
      console.log('\nComplete:', data.response);
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
2. LLM API key set: `export OPENAI_API_KEY="sk-..."` (used by litellm)
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
# - thinking messages ("Interpreting your query...", "Searching for...", "Found N matching records")
# - stream_start (narrative about to begin)
# - stream_chunk messages (real-time narrative text)
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

- Natural language query interpretation (via litellm)
- SQL query execution against bibliographic database
- Evidence-based responses with MARC field citations
- Streamed narrative responses with follow-up suggestions
- Session-based conversation history
- Real-time streaming with thinking updates and narrative chunks
- Clarification prompts for ambiguous queries
- Basic rate limiting (10 req/min per IP for /chat)
