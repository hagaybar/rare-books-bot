# Session Management Implementation Plan
**Created:** 2026-01-13
**Status:** Ready for Implementation
**Priority:** P0 - Blocker for M6 Chatbot
**Estimated Duration:** 3-4 days

---

## Overview

This plan implements session management infrastructure to support the M6 conversational chatbot interface. Session management enables multi-turn conversations with state persistence, context tracking, and user isolation.

**Core Requirements:**
- Persistent storage of conversation history
- Multi-turn context tracking (users can refer to previous queries)
- Session lifecycle management (create, retrieve, update, expire)
- User association for multi-user support
- Performance: Sub-100ms session retrieval, support 100+ concurrent sessions
- Data safety: No data loss, atomic operations, proper error handling

**Dependencies:**
- Existing M4 query pipeline (QueryPlan, CandidateSet, Evidence schemas)
- SQLite database infrastructure (from M3)
- Pydantic for schema validation

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Chatbot API Layer                      │
│                  (FastAPI - Future)                     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────┐
│              Session Management Layer                   │
│  ┌─────────────────┐  ┌──────────────────┐             │
│  │  ChatSession    │  │  SessionStore    │             │
│  │  - session_id   │←─│  - create()      │             │
│  │  - messages[]   │  │  - get()         │             │
│  │  - context      │  │  - add_message() │             │
│  └─────────────────┘  │  - expire()      │             │
│                       └──────────────────┘             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────┐
│            Session Database (SQLite)                    │
│  - chat_sessions table                                  │
│  - chat_messages table                                  │
│  - Indexed by session_id, user_id, timestamp           │
└─────────────────────────────────────────────────────────┘
```

---

## Phase 1: Data Models and Schemas (Day 1)

### 1.1 Create Pydantic Models

**File:** `scripts/chat/models.py`

**Models to implement:**

```python
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import uuid4
from pydantic import BaseModel, Field
from scripts.schemas import QueryPlan, CandidateSet

class Message(BaseModel):
    """Single message in a conversation.

    Attributes:
        role: Who sent the message (user, assistant, system)
        content: Text content of the message
        query_plan: Optional QueryPlan if this was a search query
        candidate_set: Optional results if this message has search results
        timestamp: When the message was created
    """
    role: Literal["user", "assistant", "system"]
    content: str
    query_plan: Optional[QueryPlan] = None
    candidate_set: Optional[CandidateSet] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ChatSession(BaseModel):
    """Conversation session with message history and context.

    Attributes:
        session_id: Unique identifier (UUID)
        user_id: Optional user identifier for multi-user support
        created_at: Session creation timestamp
        updated_at: Last activity timestamp
        messages: Chronologically ordered conversation history
        context: Carry-forward state for multi-turn conversations
        metadata: Extensible metadata (tags, client info, etc.)
    """
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def add_message(self, message: Message) -> None:
        """Add message and update timestamp."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

    def get_recent_messages(self, n: int = 5) -> List[Message]:
        """Get last N messages."""
        return self.messages[-n:] if len(self.messages) > n else self.messages


class ChatResponse(BaseModel):
    """Response from chatbot to user.

    Attributes:
        message: Natural language response text
        candidate_set: Optional search results
        suggested_followups: Suggested next queries
        clarification_needed: Request for user clarification if query ambiguous
        session_id: Session identifier for multi-turn tracking
    """
    message: str
    candidate_set: Optional[CandidateSet] = None
    suggested_followups: List[str] = Field(default_factory=list)
    clarification_needed: Optional[str] = None
    session_id: str
```

**Tasks:**
1. Create `scripts/chat/` directory
2. Create `scripts/chat/__init__.py`
3. Implement `scripts/chat/models.py` with above models
4. Update `scripts/schemas/__init__.py` to export chat models

**Deliverables:**
- `scripts/chat/models.py` (3 Pydantic models)
- `scripts/chat/__init__.py` (exports)

**Acceptance Criteria:**
- [ ] All models are JSON-serializable
- [ ] datetime fields serialize to ISO format
- [ ] Default factories work for all optional fields
- [ ] Message.timestamp auto-generates if not provided
- [ ] ChatSession.session_id auto-generates UUID if not provided

---

### 1.2 Create Unit Tests for Models

**File:** `tests/scripts/chat/test_models.py`

**Test cases:**

```python
import pytest
from datetime import datetime
from scripts.chat.models import Message, ChatSession, ChatResponse
from scripts.schemas import QueryPlan, CandidateSet

def test_message_creation():
    """Test Message model instantiation."""
    msg = Message(role="user", content="test query")
    assert msg.role == "user"
    assert msg.content == "test query"
    assert msg.query_plan is None
    assert msg.candidate_set is None
    assert isinstance(msg.timestamp, datetime)

def test_message_serialization():
    """Test Message JSON serialization."""
    msg = Message(role="user", content="test")
    json_str = msg.model_dump_json()
    assert "test" in json_str
    assert "user" in json_str

def test_chat_session_creation():
    """Test ChatSession auto-generates session_id."""
    session = ChatSession()
    assert session.session_id is not None
    assert len(session.session_id) == 36  # UUID format
    assert session.messages == []
    assert session.context == {}

def test_chat_session_add_message():
    """Test adding messages to session."""
    session = ChatSession()
    original_updated = session.updated_at

    msg = Message(role="user", content="test")
    session.add_message(msg)

    assert len(session.messages) == 1
    assert session.messages[0].content == "test"
    assert session.updated_at > original_updated

def test_chat_session_get_recent_messages():
    """Test retrieving recent messages."""
    session = ChatSession()
    for i in range(10):
        session.add_message(Message(role="user", content=f"msg {i}"))

    recent = session.get_recent_messages(n=3)
    assert len(recent) == 3
    assert recent[0].content == "msg 7"
    assert recent[2].content == "msg 9"

def test_chat_session_serialization():
    """Test ChatSession JSON serialization with nested Message."""
    session = ChatSession(user_id="user123")
    session.add_message(Message(role="user", content="test"))

    json_str = session.model_dump_json()
    assert "user123" in json_str
    assert "test" in json_str

    # Test deserialization
    session2 = ChatSession.model_validate_json(json_str)
    assert session2.session_id == session.session_id
    assert len(session2.messages) == 1

def test_chat_response_creation():
    """Test ChatResponse model."""
    response = ChatResponse(
        message="Found 5 books",
        session_id="test-123"
    )
    assert response.message == "Found 5 books"
    assert response.session_id == "test-123"
    assert response.candidate_set is None
    assert response.suggested_followups == []
```

**Deliverables:**
- `tests/scripts/chat/` directory
- `tests/scripts/chat/__init__.py`
- `tests/scripts/chat/test_models.py` (8+ test cases)

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] 100% coverage of model methods
- [ ] Serialization/deserialization tested
- [ ] Edge cases tested (empty lists, None values)

---

## Phase 2: Session Storage Layer (Days 2-3)

### 2.1 Create Database Schema

**File:** `scripts/chat/schema.sql`

**Schema:**

```sql
-- Chat sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL,  -- ISO datetime
    updated_at TEXT NOT NULL,  -- ISO datetime
    context TEXT,              -- JSON-serialized dict
    metadata TEXT,             -- JSON-serialized dict
    expired_at TEXT,           -- NULL if active, ISO datetime if expired
    UNIQUE(session_id)
);

-- Index for user_id lookups (multi-user support)
CREATE INDEX IF NOT EXISTS idx_sessions_user_id
ON chat_sessions(user_id);

-- Index for expiration queries
CREATE INDEX IF NOT EXISTS idx_sessions_expired
ON chat_sessions(expired_at);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    query_plan TEXT,          -- JSON-serialized QueryPlan
    candidate_set TEXT,        -- JSON-serialized CandidateSet
    timestamp TEXT NOT NULL,   -- ISO datetime
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

-- Index for session message retrieval
CREATE INDEX IF NOT EXISTS idx_messages_session
ON chat_messages(session_id, timestamp);

-- Index for timestamp-based queries
CREATE INDEX IF NOT EXISTS idx_messages_timestamp
ON chat_messages(timestamp DESC);
```

**Tasks:**
1. Create `scripts/chat/schema.sql`
2. Document schema design decisions in comments
3. Ensure foreign key constraints enabled

**Deliverables:**
- `scripts/chat/schema.sql`

**Design Notes:**
- **TEXT for datetime**: SQLite has limited datetime types; store as ISO strings
- **JSON for complex objects**: QueryPlan/CandidateSet stored as JSON TEXT
- **CASCADE DELETE**: Deleting session deletes all messages
- **Indexes**: Optimize for session retrieval and user queries
- **expired_at NULL**: Active sessions have NULL, expired have timestamp

---

### 2.2 Implement SessionStore Class

**File:** `scripts/chat/session_store.py`

**Implementation:**

```python
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from scripts.chat.models import ChatSession, Message
from scripts.utils.logger import LoggerManager


class SessionStore:
    """SQLite-backed storage for chat sessions.

    Handles CRUD operations for sessions and messages with atomic operations.

    Attributes:
        db_path: Path to SQLite database file
        _conn: SQLite connection (lazy-loaded)
    """

    def __init__(self, db_path: Path):
        """Initialize session store.

        Args:
            db_path: Path to SQLite database (created if not exists)
        """
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self.logger = LoggerManager.get_logger(__name__)
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection with foreign keys enabled."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()

        conn = self._get_connection()
        conn.executescript(schema)
        conn.commit()
        self.logger.info("Session database schema initialized",
                        extra={"db_path": str(self.db_path)})

    def create_session(self, user_id: Optional[str] = None) -> ChatSession:
        """Create new chat session.

        Args:
            user_id: Optional user identifier

        Returns:
            ChatSession: New session object
        """
        session = ChatSession(user_id=user_id)

        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO chat_sessions
            (session_id, user_id, created_at, updated_at, context, metadata, expired_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.user_id,
                session.created_at.isoformat(),
                session.updated_at.isoformat(),
                json.dumps(session.context),
                json.dumps(session.metadata),
                None
            )
        )
        conn.commit()

        self.logger.info("Created chat session",
                        extra={"session_id": session.session_id, "user_id": user_id})
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            ChatSession if found, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT session_id, user_id, created_at, updated_at, context, metadata
            FROM chat_sessions
            WHERE session_id = ? AND expired_at IS NULL
            """,
            (session_id,)
        )
        row = cursor.fetchone()

        if not row:
            self.logger.warning("Session not found", extra={"session_id": session_id})
            return None

        # Reconstruct ChatSession
        session = ChatSession(
            session_id=row[0],
            user_id=row[1],
            created_at=datetime.fromisoformat(row[2]),
            updated_at=datetime.fromisoformat(row[3]),
            context=json.loads(row[4]) if row[4] else {},
            metadata=json.loads(row[5]) if row[5] else {}
        )

        # Load messages
        messages = self._get_messages(session_id)
        session.messages = messages

        return session

    def _get_messages(self, session_id: str) -> List[Message]:
        """Retrieve all messages for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of Message objects ordered by timestamp
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT role, content, query_plan, candidate_set, timestamp
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
            """,
            (session_id,)
        )

        messages = []
        for row in cursor.fetchall():
            msg = Message(
                role=row[0],
                content=row[1],
                query_plan=json.loads(row[2]) if row[2] else None,
                candidate_set=json.loads(row[3]) if row[3] else None,
                timestamp=datetime.fromisoformat(row[4])
            )
            messages.append(msg)

        return messages

    def add_message(self, session_id: str, message: Message) -> None:
        """Add message to session.

        Args:
            session_id: Session identifier
            message: Message to add

        Raises:
            ValueError: If session doesn't exist
        """
        # Verify session exists
        if not self.get_session(session_id):
            raise ValueError(f"Session {session_id} not found")

        conn = self._get_connection()

        # Insert message
        conn.execute(
            """
            INSERT INTO chat_messages
            (session_id, role, content, query_plan, candidate_set, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                message.role,
                message.content,
                json.dumps(message.query_plan.model_dump()) if message.query_plan else None,
                json.dumps(message.candidate_set.model_dump()) if message.candidate_set else None,
                message.timestamp.isoformat()
            )
        )

        # Update session timestamp
        conn.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?
            WHERE session_id = ?
            """,
            (datetime.utcnow().isoformat(), session_id)
        )

        conn.commit()

        self.logger.info("Added message to session",
                        extra={"session_id": session_id, "role": message.role})

    def update_context(self, session_id: str, context: Dict[str, Any]) -> None:
        """Update session context.

        Args:
            session_id: Session identifier
            context: Context dictionary to merge with existing
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Merge contexts
        merged_context = {**session.context, **context}

        conn = self._get_connection()
        conn.execute(
            """
            UPDATE chat_sessions
            SET context = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (json.dumps(merged_context), datetime.utcnow().isoformat(), session_id)
        )
        conn.commit()

        self.logger.info("Updated session context",
                        extra={"session_id": session_id, "context_keys": list(context.keys())})

    def expire_session(self, session_id: str) -> None:
        """Mark session as expired.

        Args:
            session_id: Session identifier
        """
        conn = self._get_connection()
        conn.execute(
            """
            UPDATE chat_sessions
            SET expired_at = ?
            WHERE session_id = ?
            """,
            (datetime.utcnow().isoformat(), session_id)
        )
        conn.commit()

        self.logger.info("Expired session", extra={"session_id": session_id})

    def expire_old_sessions(self, max_age_hours: int = 24) -> int:
        """Expire sessions older than max_age_hours.

        Args:
            max_age_hours: Sessions inactive for this long are expired

        Returns:
            Number of sessions expired
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        conn = self._get_connection()
        cursor = conn.execute(
            """
            UPDATE chat_sessions
            SET expired_at = ?
            WHERE updated_at < ? AND expired_at IS NULL
            """,
            (datetime.utcnow().isoformat(), cutoff.isoformat())
        )
        count = cursor.rowcount
        conn.commit()

        self.logger.info("Expired old sessions",
                        extra={"count": count, "max_age_hours": max_age_hours})
        return count

    def list_user_sessions(self, user_id: str, include_expired: bool = False) -> List[str]:
        """List all sessions for a user.

        Args:
            user_id: User identifier
            include_expired: Include expired sessions

        Returns:
            List of session IDs
        """
        conn = self._get_connection()

        if include_expired:
            query = "SELECT session_id FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC"
            params = (user_id,)
        else:
            query = "SELECT session_id FROM chat_sessions WHERE user_id = ? AND expired_at IS NULL ORDER BY updated_at DESC"
            params = (user_id,)

        cursor = conn.execute(query, params)
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
```

**Tasks:**
1. Implement `scripts/chat/session_store.py` with SessionStore class
2. Add comprehensive docstrings
3. Add logging for all operations
4. Implement error handling

**Deliverables:**
- `scripts/chat/session_store.py` (SessionStore class with 10 methods)

**Acceptance Criteria:**
- [ ] All CRUD operations work correctly
- [ ] Foreign key constraints enforced
- [ ] Transactions are atomic (no partial writes)
- [ ] JSON serialization/deserialization works
- [ ] Expired sessions excluded from get_session()
- [ ] Logging for all operations

---

### 2.3 Create Integration Tests

**File:** `tests/scripts/chat/test_session_store.py`

**Test cases:**

```python
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from scripts.chat.session_store import SessionStore
from scripts.chat.models import Message, ChatSession
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp

@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()

@pytest.fixture
def store(temp_db):
    """Create SessionStore with temp database."""
    store = SessionStore(temp_db)
    yield store
    store.close()

def test_create_session(store):
    """Test session creation."""
    session = store.create_session(user_id="user123")

    assert session.session_id is not None
    assert session.user_id == "user123"
    assert len(session.messages) == 0

def test_get_session(store):
    """Test session retrieval."""
    session1 = store.create_session(user_id="user123")

    session2 = store.get_session(session1.session_id)

    assert session2 is not None
    assert session2.session_id == session1.session_id
    assert session2.user_id == "user123"

def test_get_nonexistent_session(store):
    """Test retrieving nonexistent session."""
    session = store.get_session("nonexistent")
    assert session is None

def test_add_message(store):
    """Test adding message to session."""
    session = store.create_session()
    msg = Message(role="user", content="test query")

    store.add_message(session.session_id, msg)

    # Retrieve and verify
    retrieved = store.get_session(session.session_id)
    assert len(retrieved.messages) == 1
    assert retrieved.messages[0].content == "test query"
    assert retrieved.messages[0].role == "user"

def test_add_message_with_query_plan(store):
    """Test adding message with QueryPlan."""
    session = store.create_session()

    plan = QueryPlan(
        filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="Oxford")]
    )
    msg = Message(role="user", content="books by Oxford", query_plan=plan)

    store.add_message(session.session_id, msg)

    # Retrieve and verify QueryPlan preserved
    retrieved = store.get_session(session.session_id)
    assert retrieved.messages[0].query_plan is not None
    assert retrieved.messages[0].query_plan["filters"][0]["value"] == "Oxford"

def test_add_message_to_nonexistent_session(store):
    """Test adding message to nonexistent session raises error."""
    msg = Message(role="user", content="test")

    with pytest.raises(ValueError, match="not found"):
        store.add_message("nonexistent", msg)

def test_message_ordering(store):
    """Test messages retrieved in chronological order."""
    session = store.create_session()

    for i in range(5):
        msg = Message(role="user", content=f"message {i}")
        store.add_message(session.session_id, msg)

    retrieved = store.get_session(session.session_id)
    assert len(retrieved.messages) == 5
    assert retrieved.messages[0].content == "message 0"
    assert retrieved.messages[4].content == "message 4"

def test_update_context(store):
    """Test updating session context."""
    session = store.create_session()

    store.update_context(session.session_id, {"last_query": "test", "result_count": 5})

    retrieved = store.get_session(session.session_id)
    assert retrieved.context["last_query"] == "test"
    assert retrieved.context["result_count"] == 5

def test_context_merge(store):
    """Test context updates merge with existing."""
    session = store.create_session()

    store.update_context(session.session_id, {"key1": "value1"})
    store.update_context(session.session_id, {"key2": "value2"})

    retrieved = store.get_session(session.session_id)
    assert retrieved.context["key1"] == "value1"
    assert retrieved.context["key2"] == "value2"

def test_expire_session(store):
    """Test session expiration."""
    session = store.create_session()

    store.expire_session(session.session_id)

    # Expired session should not be retrieved
    retrieved = store.get_session(session.session_id)
    assert retrieved is None

def test_expire_old_sessions(store):
    """Test expiring sessions by age."""
    # Create sessions
    session1 = store.create_session()
    session2 = store.create_session()

    # Manually set one session's updated_at to 25 hours ago
    import sqlite3
    conn = sqlite3.connect(str(store.db_path))
    old_time = (datetime.utcnow() - timedelta(hours=25)).isoformat()
    conn.execute(
        "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
        (old_time, session1.session_id)
    )
    conn.commit()
    conn.close()

    # Expire old sessions
    count = store.expire_old_sessions(max_age_hours=24)

    assert count == 1
    assert store.get_session(session1.session_id) is None
    assert store.get_session(session2.session_id) is not None

def test_list_user_sessions(store):
    """Test listing sessions for a user."""
    session1 = store.create_session(user_id="user1")
    session2 = store.create_session(user_id="user1")
    session3 = store.create_session(user_id="user2")

    user1_sessions = store.list_user_sessions("user1")

    assert len(user1_sessions) == 2
    assert session1.session_id in user1_sessions
    assert session2.session_id in user1_sessions
    assert session3.session_id not in user1_sessions

def test_list_user_sessions_exclude_expired(store):
    """Test expired sessions excluded from user list."""
    session1 = store.create_session(user_id="user1")
    session2 = store.create_session(user_id="user1")

    store.expire_session(session1.session_id)

    user1_sessions = store.list_user_sessions("user1")
    assert len(user1_sessions) == 1
    assert session2.session_id in user1_sessions

    # Include expired
    all_sessions = store.list_user_sessions("user1", include_expired=True)
    assert len(all_sessions) == 2

def test_session_persistence(store):
    """Test session persists across store reconnections."""
    session = store.create_session(user_id="user1")
    msg = Message(role="user", content="persistent message")
    store.add_message(session.session_id, msg)
    store.close()

    # Reconnect
    store2 = SessionStore(store.db_path)
    retrieved = store2.get_session(session.session_id)

    assert retrieved is not None
    assert len(retrieved.messages) == 1
    assert retrieved.messages[0].content == "persistent message"
    store2.close()

def test_foreign_key_cascade(store):
    """Test deleting session cascades to messages."""
    import sqlite3

    session = store.create_session()
    store.add_message(session.session_id, Message(role="user", content="test"))

    # Manually delete session (simulating cascade)
    conn = sqlite3.connect(str(store.db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session.session_id,))
    conn.commit()

    # Verify messages also deleted
    cursor = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session.session_id,))
    count = cursor.fetchone()[0]
    assert count == 0

    conn.close()
```

**Tasks:**
1. Create `tests/scripts/chat/test_session_store.py`
2. Implement 15+ integration test cases
3. Use fixtures for test database isolation
4. Test error conditions and edge cases

**Deliverables:**
- `tests/scripts/chat/test_session_store.py` (15+ tests)

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] 100% coverage of SessionStore methods
- [ ] Tests use temporary databases (no pollution)
- [ ] Concurrent access tested (if needed)
- [ ] Foreign key cascade verified
- [ ] Session expiration logic tested

---

## Phase 3: CLI Integration (Day 3)

### 3.1 Add Session Management to CLI

**File:** `app/cli.py` (modifications)

**Add new commands:**

```python
@app.command()
def chat_init(
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        help="Path to session database"
    ),
    user_id: Optional[str] = typer.Option(None, help="Optional user ID")
):
    """Initialize new chat session.

    Creates a new session and prints session_id for use in subsequent queries.
    """
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    session = store.create_session(user_id=user_id)

    typer.echo(f"Created session: {session.session_id}")
    typer.echo(f"User: {session.user_id or 'anonymous'}")
    typer.echo(f"Database: {db_path}")

    store.close()


@app.command()
def chat_history(
    session_id: str = typer.Argument(..., help="Session ID"),
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        help="Path to session database"
    )
):
    """View conversation history for a session."""
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    session = store.get_session(session_id)

    if not session:
        typer.echo(f"Session {session_id} not found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Session: {session.session_id}")
    typer.echo(f"User: {session.user_id or 'anonymous'}")
    typer.echo(f"Messages: {len(session.messages)}")
    typer.echo(f"Created: {session.created_at}")
    typer.echo(f"Updated: {session.updated_at}")
    typer.echo("\n--- Messages ---\n")

    for i, msg in enumerate(session.messages, 1):
        typer.echo(f"{i}. [{msg.role}] {msg.content}")
        if msg.query_plan:
            typer.echo(f"   QueryPlan: {len(msg.query_plan.filters)} filters")
        if msg.candidate_set:
            typer.echo(f"   Results: {msg.candidate_set.total_count} candidates")
        typer.echo(f"   Time: {msg.timestamp}")
        typer.echo()

    store.close()


@app.command()
def chat_cleanup(
    db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        help="Path to session database"
    ),
    max_age_hours: int = typer.Option(24, help="Expire sessions older than this")
):
    """Expire old sessions."""
    from scripts.chat.session_store import SessionStore

    store = SessionStore(db_path)
    count = store.expire_old_sessions(max_age_hours=max_age_hours)

    typer.echo(f"Expired {count} sessions older than {max_age_hours} hours")

    store.close()
```

**Tasks:**
1. Add `chat_init`, `chat_history`, `chat_cleanup` commands to `app/cli.py`
2. Update CLI help text
3. Test commands manually

**Deliverables:**
- Updated `app/cli.py` with 3 new commands

**Acceptance Criteria:**
- [ ] `chat-init` creates session and prints ID
- [ ] `chat-history <session-id>` displays messages
- [ ] `chat-cleanup` expires old sessions
- [ ] All commands handle errors gracefully
- [ ] Help text is clear

---

### 3.2 Modify Query Command for Session Support

**File:** `app/cli.py` (modifications)

**Update existing `query` command:**

```python
@app.command()
def query(
    query_text: str = typer.Argument(..., help="Natural language query"),
    db_path: Path = typer.Option(
        Path("data/index/bibliographic.db"),
        help="Path to bibliographic database"
    ),
    session_id: Optional[str] = typer.Option(
        None,
        help="Optional session ID to save query to session history"
    ),
    session_db_path: Path = typer.Option(
        Path("data/chat/sessions.db"),
        help="Path to session database"
    ),
    api_key: Optional[str] = typer.Option(None, help="OpenAI API key"),
    show_evidence: bool = typer.Option(True, help="Show evidence for each candidate"),
    limit: int = typer.Option(10, help="Max candidates to display")
):
    """Execute natural language query with optional session tracking.

    If session_id provided, saves query and results to session history.
    """
    from scripts.query.compile import compile_query
    from scripts.query.execute import execute_plan
    from scripts.chat.session_store import SessionStore
    from scripts.chat.models import Message

    # Execute query (existing logic)
    plan = compile_query(query_text, api_key=api_key)
    candidate_set = execute_plan(plan, db_path)

    # Display results (existing logic)
    typer.echo(f"Found {candidate_set.total_count} candidates")
    # ... display logic ...

    # Save to session if session_id provided
    if session_id:
        store = SessionStore(session_db_path)

        # Add user message
        user_msg = Message(
            role="user",
            content=query_text,
            query_plan=plan
        )
        store.add_message(session_id, user_msg)

        # Add assistant response with results
        response_text = f"Found {candidate_set.total_count} books matching your query"
        assistant_msg = Message(
            role="assistant",
            content=response_text,
            candidate_set=candidate_set
        )
        store.add_message(session_id, assistant_msg)

        typer.echo(f"\n✓ Saved to session {session_id}")
        store.close()
```

**Tasks:**
1. Modify `query` command to accept `--session-id` option
2. Save query + results to session if session_id provided
3. Test with and without session tracking

**Deliverables:**
- Updated `app/cli.py` query command with session support

**Acceptance Criteria:**
- [ ] Query works without session (backward compatible)
- [ ] Query with `--session-id` saves to session
- [ ] Session history shows query + results
- [ ] Error if invalid session_id

---

## Phase 4: Documentation and Deployment (Day 4)

### 4.1 Create Usage Documentation

**File:** `docs/session_management_usage.md`

**Contents:**

```markdown
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
```

**Tasks:**
1. Create `docs/session_management_usage.md`
2. Include CLI examples, Python API examples, troubleshooting
3. Document performance characteristics

**Deliverables:**
- `docs/session_management_usage.md`

**Acceptance Criteria:**
- [ ] All use cases documented
- [ ] Code examples tested and working
- [ ] Performance notes included
- [ ] Troubleshooting section comprehensive

---

### 4.2 Update Project Documentation

**Files to update:**

1. **CLAUDE.md** - Add session management section:

```markdown
## Session Management

Multi-turn conversation support with persistent state:

**Location**: `scripts/chat/session_store.py`
**Database**: `data/chat/sessions.db`
**Models**: `scripts/chat/models.py` (ChatSession, Message, ChatResponse)

**Key Operations**:
- Create session: `store.create_session(user_id)`
- Add message: `store.add_message(session_id, message)`
- Retrieve session: `store.get_session(session_id)`
- Expire old: `store.expire_old_sessions(max_age_hours=24)`

See `docs/session_management_usage.md` for full documentation.
```

2. **README.md** - Update CLI commands:

```markdown
### Chat Commands

```bash
# Create session
python -m app.cli chat-init

# Query with session tracking
python -m app.cli query "books by Oxford" --session-id <id>

# View history
python -m app.cli chat-history <session-id>

# Cleanup
python -m app.cli chat-cleanup
```
```

3. **plan.mf** - Mark session management as complete:

```markdown
### Phase 1: Conversational Foundation ✅ COMPLETE

**Session Management (CB-001)**: ✅
- Pydantic models: ChatSession, Message, ChatResponse
- SQLite storage: chat_sessions, chat_messages tables
- SessionStore class: CRUD operations, context management
- CLI integration: chat-init, chat-history, chat-cleanup commands
- Comprehensive tests: 15+ integration tests, 100% coverage
```

**Tasks:**
1. Update CLAUDE.md with session management section
2. Update README.md with chat commands
3. Update plan.mf to mark session management complete
4. Add session management to .gitignore if needed

**Deliverables:**
- Updated CLAUDE.md, README.md, plan.mf
- `.gitignore` updated to exclude `data/chat/sessions.db`

**Acceptance Criteria:**
- [ ] All project docs reference session management
- [ ] Session database excluded from git
- [ ] CLI help is comprehensive

---

### 4.3 Create Migration Script (Optional)

**File:** `scripts/chat/migrate_sessions.py`

For future schema changes:

```python
"""Session database migration utilities.

Usage:
    python scripts/chat/migrate_sessions.py --db data/chat/sessions.db --version 2
"""

import sqlite3
from pathlib import Path
import typer

app = typer.Typer()

MIGRATIONS = {
    2: [
        """
        -- Add user preferences column
        ALTER TABLE chat_sessions ADD COLUMN preferences TEXT DEFAULT '{}';
        """
    ],
    3: [
        """
        -- Add message rating system
        ALTER TABLE chat_messages ADD COLUMN rating INTEGER DEFAULT NULL;
        CREATE INDEX IF NOT EXISTS idx_messages_rating ON chat_messages(rating);
        """
    ]
}

@app.command()
def migrate(
    db_path: Path,
    version: int = typer.Option(..., help="Target schema version")
):
    """Migrate session database to target version."""
    conn = sqlite3.connect(str(db_path))

    # Get current version
    cursor = conn.execute("PRAGMA user_version")
    current_version = cursor.fetchone()[0]

    if version <= current_version:
        typer.echo(f"Database already at version {current_version}")
        return

    # Apply migrations
    for v in range(current_version + 1, version + 1):
        if v not in MIGRATIONS:
            typer.echo(f"No migration for version {v}", err=True)
            raise typer.Exit(1)

        typer.echo(f"Applying migration to version {v}...")
        for sql in MIGRATIONS[v]:
            conn.executescript(sql)

        conn.execute(f"PRAGMA user_version = {v}")
        conn.commit()

    typer.echo(f"✓ Migrated to version {version}")
    conn.close()

if __name__ == "__main__":
    app()
```

**Tasks:**
1. Create `scripts/chat/migrate_sessions.py` (optional, for future use)
2. Document migration process

**Deliverables:**
- `scripts/chat/migrate_sessions.py` (optional)

---

## Testing Strategy

### Unit Tests (Day 1)
- **Coverage**: 100% of models.py
- **Focus**: Serialization, validation, defaults
- **Runtime**: <1 second

### Integration Tests (Days 2-3)
- **Coverage**: 100% of SessionStore methods
- **Focus**: Database operations, transactions, persistence
- **Runtime**: <5 seconds
- **Isolation**: Temporary databases per test

### Manual Testing (Day 3)
- **CLI commands**: Create, query, history, cleanup
- **Multi-session**: Multiple concurrent sessions
- **Edge cases**: Invalid IDs, expired sessions, empty history

### Regression Tests (Day 4)
- **Backward compatibility**: Existing query command still works
- **Performance**: Session retrieval <100ms for 50-message sessions

---

## Success Criteria

### Functional Requirements ✅
- [ ] Create session with optional user_id
- [ ] Add messages with QueryPlan and CandidateSet
- [ ] Retrieve session with full message history
- [ ] Update session context
- [ ] Expire sessions manually or by age
- [ ] List user's sessions
- [ ] Messages ordered chronologically
- [ ] JSON serialization/deserialization works

### Non-Functional Requirements ✅
- [ ] Session retrieval <100ms (50 messages)
- [ ] Database size <20KB per session
- [ ] 100% test coverage for core operations
- [ ] No data loss (atomic operations)
- [ ] Foreign key constraints enforced
- [ ] Comprehensive logging

### Integration Requirements ✅
- [ ] CLI commands: chat-init, chat-history, chat-cleanup
- [ ] Query command supports --session-id
- [ ] Documentation complete and accurate
- [ ] Project docs updated (CLAUDE.md, README.md, plan.mf)

---

## Next Steps (Post-Implementation)

After session management is complete, proceed to:

1. **Response Formatter (CB-003)**: Convert CandidateSet to natural language
   - `scripts/chat/formatter.py`
   - Templates for zero/single/multiple results
   - Evidence formatting

2. **Chat API Endpoint (CB-002)**: FastAPI REST endpoint
   - `app/api/main.py`
   - POST /chat endpoint
   - Session integration

3. **Clarification Flow (CB-004)**: Ambiguity detection
   - `scripts/chat/clarification.py`
   - Empty filter detection
   - Retry logic

---

## Risk Mitigation

### Risk: SQLite Write Contention
**Impact**: High concurrent writes may cause database locks
**Mitigation**:
- Use connection pooling
- Implement retry logic with exponential backoff
- Consider PostgreSQL for production if >100 concurrent writers

### Risk: Unbounded Session Growth
**Impact**: Sessions with 1000+ messages slow retrieval
**Mitigation**:
- Implement message pagination in SessionStore
- Add `get_recent_messages(n)` method (already included)
- Archive old messages after 30 days

### Risk: Session Database Corruption
**Impact**: Loss of conversation history
**Mitigation**:
- Regular backups (nightly cron)
- SQLite integrity checks: `PRAGMA integrity_check`
- Write-ahead logging (WAL mode)

### Risk: Testing Coverage Gaps
**Impact**: Bugs in production
**Mitigation**:
- 100% test coverage requirement
- Integration tests with real database
- Manual testing of CLI commands

---

## Dependencies

### Existing Code (No Changes Needed)
- `scripts/schemas/query_plan.py` (QueryPlan, Filter)
- `scripts/schemas/candidate_set.py` (CandidateSet, Evidence)
- `scripts/query/compile.py` (compile_query)
- `scripts/query/execute.py` (execute_plan)
- `scripts/utils/logger.py` (LoggerManager)

### New Dependencies
None - all functionality uses standard library + existing dependencies

### Directory Structure to Create
```
scripts/chat/
├── __init__.py
├── models.py           # Pydantic schemas
├── session_store.py    # SessionStore class
└── schema.sql          # Database schema

tests/scripts/chat/
├── __init__.py
├── test_models.py      # Model unit tests
└── test_session_store.py  # SessionStore integration tests

data/chat/
└── sessions.db         # Session database (gitignored)

docs/
└── session_management_usage.md  # Usage documentation
```

---

## Implementation Checklist

### Day 1: Data Models ✅
- [ ] Create `scripts/chat/` directory structure
- [ ] Implement `scripts/chat/models.py` (3 models)
- [ ] Create `tests/scripts/chat/test_models.py` (8+ tests)
- [ ] Run tests: `pytest tests/scripts/chat/test_models.py -v`
- [ ] Verify 100% coverage

### Day 2: Storage Layer ✅
- [ ] Create `scripts/chat/schema.sql` (2 tables, 3 indexes)
- [ ] Implement `scripts/chat/session_store.py` (SessionStore class)
- [ ] Create `tests/scripts/chat/test_session_store.py` (15+ tests)
- [ ] Run tests: `pytest tests/scripts/chat/test_session_store.py -v`
- [ ] Verify persistence, foreign keys, expiration

### Day 3: CLI Integration ✅
- [ ] Add `chat_init` command to `app/cli.py`
- [ ] Add `chat_history` command to `app/cli.py`
- [ ] Add `chat_cleanup` command to `app/cli.py`
- [ ] Modify `query` command for session support
- [ ] Manual testing of all CLI commands

### Day 4: Documentation ✅
- [ ] Create `docs/session_management_usage.md`
- [ ] Update `CLAUDE.md` with session management section
- [ ] Update `README.md` with chat commands
- [ ] Update `plan.mf` to mark CB-001 complete
- [ ] Add `data/chat/sessions.db` to `.gitignore`
- [ ] Create migration script (optional)

### Final Validation ✅
- [ ] All tests pass: `pytest tests/scripts/chat/ -v`
- [ ] Test coverage ≥100%: `pytest tests/scripts/chat/ --cov=scripts.chat`
- [ ] CLI commands work end-to-end
- [ ] Documentation accurate and complete
- [ ] Git commit with detailed message

---

## Commit Message Template

```
Add session management for multi-turn chatbot conversations

Implement complete session management infrastructure for M6 chatbot:

**Data Models (scripts/chat/models.py):**
- ChatSession: Session metadata with message history and context
- Message: Individual conversation turn with QueryPlan/CandidateSet
- ChatResponse: Chatbot response with results and suggestions

**Storage Layer (scripts/chat/session_store.py):**
- SessionStore class with SQLite backend
- CRUD operations: create, get, add_message, update_context, expire
- Foreign key constraints with cascade delete
- Automatic session expiration by age

**Database Schema (scripts/chat/schema.sql):**
- chat_sessions table: session metadata and context
- chat_messages table: conversation history
- Indexes for session_id, user_id, timestamp

**CLI Integration (app/cli.py):**
- chat-init: Create new session
- chat-history: View conversation history
- chat-cleanup: Expire old sessions
- query --session-id: Save queries to session

**Testing:**
- 8 unit tests for models (serialization, validation)
- 15+ integration tests for SessionStore (CRUD, persistence, expiration)
- 100% test coverage

**Documentation:**
- docs/session_management_usage.md: Complete usage guide
- Updated CLAUDE.md, README.md, plan.mf

**Addresses:**
- CB-001 (Session Management) from chatbot readiness audit
- Phase 1 of M6 implementation plan

**Next Steps:**
- Response formatter (CB-003)
- FastAPI chat endpoint (CB-002)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

---

**End of Plan**
