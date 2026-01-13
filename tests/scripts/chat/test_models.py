"""Unit tests for chat models.

Tests Message, ChatSession, and ChatResponse Pydantic models.
"""

from datetime import datetime

import pytest

from scripts.chat.models import ChatResponse, ChatSession, Message
from scripts.schemas import CandidateSet, Filter, FilterField, FilterOp, QueryPlan


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


def test_chat_session_get_recent_messages_fewer_than_n():
    """Test get_recent_messages when fewer than n messages exist."""
    session = ChatSession()
    session.add_message(Message(role="user", content="msg 0"))
    session.add_message(Message(role="user", content="msg 1"))

    recent = session.get_recent_messages(n=5)
    assert len(recent) == 2
    assert recent[0].content == "msg 0"
    assert recent[1].content == "msg 1"


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
    response = ChatResponse(message="Found 5 books", session_id="test-123")
    assert response.message == "Found 5 books"
    assert response.session_id == "test-123"
    assert response.candidate_set is None
    assert response.suggested_followups == []


def test_message_with_query_plan():
    """Test Message with QueryPlan attached."""
    plan = QueryPlan(
        query_text="books by Oxford",
        filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="Oxford")]
    )
    msg = Message(role="user", content="books by Oxford", query_plan=plan)

    assert msg.query_plan is not None
    assert msg.query_plan.filters[0].value == "Oxford"


def test_message_with_candidate_set():
    """Test Message with CandidateSet attached."""
    candidate_set = CandidateSet(
        query_text="books by Oxford",
        plan_hash="abc123",
        sql="SELECT * FROM records WHERE publisher = 'Oxford'",
        candidates=[],
        total_count=2,
    )
    msg = Message(role="assistant", content="Found 2 books", candidate_set=candidate_set)

    assert msg.candidate_set is not None
    assert msg.candidate_set.total_count == 2


def test_chat_session_metadata():
    """Test ChatSession with metadata."""
    session = ChatSession(
        user_id="user123", metadata={"client": "web", "version": "1.0"}
    )

    assert session.metadata["client"] == "web"
    assert session.metadata["version"] == "1.0"


def test_chat_session_context():
    """Test ChatSession with context."""
    session = ChatSession(context={"last_query": "test", "result_count": 5})

    assert session.context["last_query"] == "test"
    assert session.context["result_count"] == 5


def test_chat_response_with_clarification():
    """Test ChatResponse with clarification needed."""
    response = ChatResponse(
        message="I need more information",
        clarification_needed="Which century are you interested in?",
        session_id="test-123",
    )

    assert response.clarification_needed == "Which century are you interested in?"


def test_chat_response_with_followups():
    """Test ChatResponse with suggested followups."""
    response = ChatResponse(
        message="Found 10 books",
        suggested_followups=["Show more details", "Filter by date", "Export results"],
        session_id="test-123",
    )

    assert len(response.suggested_followups) == 3
    assert "Show more details" in response.suggested_followups
