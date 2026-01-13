# Session Management Usage Guide

## Overview

The session management system enables multi-turn conversations with persistent state. Sessions store conversation history, query results, and context for continuity across interactions.

## Data Storage

Sessions are stored in SQLite database: `data/chat/sessions.db`

**Tables:**
- `chat_sessions`: Session metadata (session_id, user_id, timestamps, context)
- `chat_messages`: Message history with QueryPlan and CandidateSet results

## CLI Usage

### Create a Session

```bash
# Anonymous session
python -m app.cli chat-init

# User-associated session
python -m app.cli chat-init --user-id "user123"
```

Output:
```
Created session: 550e8400-e29b-41d4-a716-446655440000
User: user123
Database: data/chat/sessions.db
```

### Run Query with Session Tracking

```bash
python -m app.cli query "books by Oxford" \
  --session-id 550e8400-e29b-41d4-a716-446655440000
```

### View Session History

```bash
python -m app.cli chat-history 550e8400-e29b-41d4-a716-446655440000
```

### Cleanup Old Sessions

```bash
# Expire sessions inactive for 24+ hours
python -m app.cli chat-cleanup --max-age-hours 24
```

## Python API Usage

### Initialize SessionStore

```python
from pathlib import Path
from scripts.chat.session_store import SessionStore

store = SessionStore(Path("data/chat/sessions.db"))
```

### Create Session

```python
session = store.create_session(user_id="user123")
print(f"Session ID: {session.session_id}")
```

### Add Messages

```python
from scripts.chat.models import Message

# User message
user_msg = Message(role="user", content="Find books by Oxford")
store.add_message(session.session_id, user_msg)

# Assistant response
assistant_msg = Message(
    role="assistant",
    content="Found 15 books by Oxford University Press",
    candidate_set=candidate_set  # From query execution
)
store.add_message(session.session_id, assistant_msg)
```

### Retrieve Session

```python
session = store.get_session(session_id)
if session:
    print(f"Messages: {len(session.messages)}")
    for msg in session.messages:
        print(f"[{msg.role}] {msg.content}")
```

### Update Context

```python
# Store carry-forward state
store.update_context(session.session_id, {
    "last_publisher": "Oxford",
    "last_result_count": 15
})
```

### Session Lifecycle

```python
# List user's sessions
sessions = store.list_user_sessions("user123")

# Expire session
store.expire_session(session_id)

# Cleanup old sessions (cron job)
expired_count = store.expire_old_sessions(max_age_hours=24)
```

## FastAPI Integration (Future)

Session management will be integrated into the chatbot API:

```python
from fastapi import FastAPI
from scripts.chat.session_store import SessionStore
from scripts.chat.models import ChatResponse

app = FastAPI()
store = SessionStore(Path("data/chat/sessions.db"))

@app.post("/chat")
async def chat(session_id: str, message: str) -> ChatResponse:
    # Get or create session
    session = store.get_session(session_id)
    if not session:
        session = store.create_session()

    # Execute query
    plan = compile_query(message)
    results = execute_plan(plan, db_path)

    # Save to session
    store.add_message(session_id, Message(role="user", content=message))
    store.add_message(session_id, Message(role="assistant", content=..., candidate_set=results))

    return ChatResponse(
        message="...",
        candidate_set=results,
        session_id=session.session_id
    )
```

## Performance Considerations

- **Session retrieval**: Sub-100ms for sessions with <100 messages
- **Concurrent users**: SQLite supports 100+ concurrent read sessions
- **Database size**: ~10KB per session + ~2KB per message
- **Indexing**: session_id and user_id indexed for fast lookups

## Maintenance

### Database Cleanup

Run nightly cron job to expire old sessions:

```bash
0 2 * * * cd /path/to/project && python -m app.cli chat-cleanup --max-age-hours 24
```

### Backup

```bash
cp data/chat/sessions.db data/chat/sessions_backup_$(date +%Y%m%d).db
```

### Monitoring

Check active session count:

```sql
SELECT COUNT(*) FROM chat_sessions WHERE expired_at IS NULL;
```

Check total messages:

```sql
SELECT COUNT(*) FROM chat_messages;
```

## Security

- **User isolation**: Sessions filtered by user_id
- **Data retention**: Expired sessions remain in database (soft delete)
- **No encryption**: Sensitive data should not be stored in sessions
- **Access control**: Application-level (JWT in M6)

## Troubleshooting

### Session Not Found

```python
session = store.get_session(session_id)
if not session:
    # Session expired or doesn't exist
    session = store.create_session(user_id=user_id)
```

### Database Locked

SQLite write lock - ensure only one writer at a time:

```python
# Use connection pooling or retry logic
import time
for attempt in range(3):
    try:
        store.add_message(session_id, message)
        break
    except sqlite3.OperationalError:
        time.sleep(0.1 * (2 ** attempt))
```

### Large Message History

Limit message retrieval:

```python
recent_messages = session.get_recent_messages(n=10)
```
