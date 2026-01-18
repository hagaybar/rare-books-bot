"""Integration tests for SessionStore.

Tests SQLite-backed session storage with CRUD operations,
persistence, expiration, and foreign key constraints.
"""

import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.chat.models import Message
from scripts.chat.session_store import SessionStore
from scripts.schemas import CandidateSet, Filter, FilterField, FilterOp, QueryPlan


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
        query_text="books by Oxford",
        filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="Oxford")]
    )
    msg = Message(role="user", content="books by Oxford", query_plan=plan)

    store.add_message(session.session_id, msg)

    # Retrieve and verify QueryPlan preserved
    retrieved = store.get_session(session.session_id)
    assert retrieved.messages[0].query_plan is not None
    # Note: query_plan is deserialized as QueryPlan object by Pydantic
    assert retrieved.messages[0].query_plan.filters[0].value == "Oxford"


def test_add_message_with_candidate_set(store):
    """Test adding message with CandidateSet."""
    session = store.create_session()

    candidate_set = CandidateSet(
        query_text="books by Oxford",
        plan_hash="abc123",
        sql="SELECT * FROM records WHERE publisher = 'Oxford'",
        candidates=[],
        total_count=2,
    )
    msg = Message(
        role="assistant", content="Found 2 books", candidate_set=candidate_set
    )

    store.add_message(session.session_id, msg)

    # Retrieve and verify CandidateSet preserved
    retrieved = store.get_session(session.session_id)
    assert retrieved.messages[0].candidate_set is not None
    # Note: candidate_set is deserialized as CandidateSet object by Pydantic
    assert retrieved.messages[0].candidate_set.total_count == 2


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


def test_update_context_nonexistent_session(store):
    """Test updating context for nonexistent session raises error."""
    with pytest.raises(ValueError, match="not found"):
        store.update_context("nonexistent", {"key": "value"})


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
    conn = sqlite3.connect(str(store.db_path))
    old_time = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conn.execute(
        "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
        (old_time, session1.session_id),
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
    session = store.create_session()
    store.add_message(session.session_id, Message(role="user", content="test"))

    # Manually delete session (simulating cascade)
    conn = sqlite3.connect(str(store.db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM chat_sessions WHERE session_id = ?", (session.session_id,))
    conn.commit()

    # Verify messages also deleted
    cursor = conn.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE session_id = ?", (session.session_id,)
    )
    count = cursor.fetchone()[0]
    assert count == 0

    conn.close()


def test_multiple_messages_with_plans_and_results(store):
    """Test session with multiple messages containing QueryPlans and CandidateSets."""
    session = store.create_session(user_id="user1")

    # User query
    plan1 = QueryPlan(
        query_text="books by Oxford",
        filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="Oxford")]
    )
    msg1 = Message(role="user", content="books by Oxford", query_plan=plan1)
    store.add_message(session.session_id, msg1)

    # Assistant response
    candidate_set1 = CandidateSet(
        query_text="books by Oxford",
        plan_hash="abc123",
        sql="SELECT * FROM records WHERE publisher = 'Oxford'",
        candidates=[],
        total_count=2,
    )
    msg2 = Message(
        role="assistant", content="Found 2 books by Oxford", candidate_set=candidate_set1
    )
    store.add_message(session.session_id, msg2)

    # Follow-up query
    plan2 = QueryPlan(
        query_text="books by Oxford from 17th century",
        filters=[
            Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="Oxford"),
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1600, end=1700),
        ]
    )
    msg3 = Message(
        role="user", content="books by Oxford from 17th century", query_plan=plan2
    )
    store.add_message(session.session_id, msg3)

    # Retrieve and verify
    retrieved = store.get_session(session.session_id)
    assert len(retrieved.messages) == 3
    assert retrieved.messages[0].query_plan is not None
    assert retrieved.messages[1].candidate_set is not None
    assert retrieved.messages[2].query_plan is not None
    assert len(retrieved.messages[2].query_plan.filters) == 2


def test_anonymous_session(store):
    """Test session creation without user_id."""
    session = store.create_session()

    assert session.user_id is None
    assert session.session_id is not None


def test_session_metadata_persistence(store):
    """Test session metadata persists across retrieval."""
    session = store.create_session(user_id="user1")
    session.metadata = {"client": "web", "version": "1.0"}

    # Manually update metadata in database
    conn = sqlite3.connect(str(store.db_path))
    conn.execute(
        "UPDATE chat_sessions SET metadata = ? WHERE session_id = ?",
        ('{"client": "web", "version": "1.0"}', session.session_id),
    )
    conn.commit()
    conn.close()

    # Retrieve and verify
    retrieved = store.get_session(session.session_id)
    assert retrieved.metadata["client"] == "web"
    assert retrieved.metadata["version"] == "1.0"


def test_list_user_sessions_ordering(store):
    """Test user sessions ordered by updated_at (most recent first)."""
    import time

    session1 = store.create_session(user_id="user1")
    time.sleep(0.01)  # Ensure different timestamps
    session2 = store.create_session(user_id="user1")
    time.sleep(0.01)
    session3 = store.create_session(user_id="user1")

    sessions = store.list_user_sessions("user1")

    # Most recent first
    assert sessions[0] == session3.session_id
    assert sessions[1] == session2.session_id
    assert sessions[2] == session1.session_id
