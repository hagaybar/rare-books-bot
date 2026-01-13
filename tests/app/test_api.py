"""Integration tests for FastAPI chat endpoint.

These tests verify:
- Session creation and retrieval
- Query compilation and execution through /chat endpoint
- Error handling for invalid queries
- Health check endpoint
"""

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app, session_store, db_path


@pytest.fixture(scope="function")
def test_db_path():
    """Provide path to test bibliographic database.

    Returns:
        Path to bibliographic.db in data/index/
    """
    db = Path("data/index/bibliographic.db")
    if not db.exists():
        pytest.skip(f"Test database not found at {db}")
    return db


@pytest.fixture(scope="function")
def test_sessions_db():
    """Create temporary sessions database for testing.

    Yields:
        Path to temporary sessions.db
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    yield tmp_path

    # Cleanup
    if tmp_path.exists():
        tmp_path.unlink()


@pytest.fixture(scope="function")
def client(test_sessions_db, test_db_path, monkeypatch):
    """Create FastAPI test client with isolated session store.

    Args:
        test_sessions_db: Temporary sessions database
        test_db_path: Path to bibliographic database
        monkeypatch: Pytest monkeypatch fixture

    Yields:
        TestClient instance
    """
    # Set environment variables for test databases
    monkeypatch.setenv("SESSIONS_DB_PATH", str(test_sessions_db))
    monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(test_db_path))

    # Reset global state
    import app.api.main as main_module

    main_module.session_store = None
    main_module.db_path = None

    # Create test client (triggers startup event)
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    """Test /health endpoint returns healthy status."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert "database_connected" in data
    assert "session_store_ok" in data


def test_chat_creates_new_session(client):
    """Test /chat endpoint creates new session if session_id not provided."""
    response = client.post(
        "/chat", json={"message": "books published by Oxford between 1500 and 1599"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["response"] is not None
    assert "session_id" in data["response"]
    assert data["response"]["message"] is not None


@pytest.mark.integration
def test_chat_with_valid_query(client):
    """Test /chat endpoint with valid query returns results.

    Requires OPENAI_API_KEY environment variable.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    response = client.post(
        "/chat", json={"message": "books published by Oxford between 1500 and 1599"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["response"] is not None
    assert data["response"]["message"] is not None
    assert "candidate_set" in data["response"]
    assert "session_id" in data["response"]


@pytest.mark.integration
def test_chat_with_existing_session(client):
    """Test /chat endpoint uses existing session for multi-turn conversation.

    Requires OPENAI_API_KEY environment variable.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    # First query creates session
    response1 = client.post("/chat", json={"message": "books about History"})
    assert response1.status_code == 200
    data1 = response1.json()
    session_id = data1["response"]["session_id"]

    # Second query uses same session
    response2 = client.post(
        "/chat", json={"message": "only from Paris", "session_id": session_id}
    )
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["response"]["session_id"] == session_id


def test_chat_with_invalid_session(client):
    """Test /chat endpoint returns 404 for non-existent session."""
    response = client.post(
        "/chat",
        json={"message": "books about History", "session_id": "nonexistent-session-id"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_chat_with_empty_message(client):
    """Test /chat endpoint rejects empty message."""
    response = client.post("/chat", json={"message": ""})

    assert response.status_code == 422  # Validation error


def test_get_session(client):
    """Test GET /sessions/{session_id} returns session details."""
    # Create a session first
    response1 = client.post("/chat", json={"message": "test query"})
    session_id = response1.json()["response"]["session_id"]

    # Get session details
    response2 = client.get(f"/sessions/{session_id}")

    assert response2.status_code == 200
    data = response2.json()
    assert data["session_id"] == session_id
    assert "messages" in data
    assert len(data["messages"]) >= 2  # user + assistant


def test_get_nonexistent_session(client):
    """Test GET /sessions/{session_id} returns 404 for non-existent session."""
    response = client.get("/sessions/nonexistent-session-id")

    assert response.status_code == 404


def test_expire_session(client):
    """Test DELETE /sessions/{session_id} expires session."""
    # Create a session first
    response1 = client.post("/chat", json={"message": "test query"})
    session_id = response1.json()["response"]["session_id"]

    # Expire the session
    response2 = client.delete(f"/sessions/{session_id}")

    assert response2.status_code == 200
    data = response2.json()
    assert data["status"] == "success"

    # Verify session is expired (GET should return 404)
    response3 = client.get(f"/sessions/{session_id}")
    assert response3.status_code == 404


def test_expire_nonexistent_session(client):
    """Test DELETE /sessions/{session_id} returns 404 for non-existent session."""
    response = client.delete("/sessions/nonexistent-session-id")

    assert response.status_code == 404


def test_chat_with_context(client):
    """Test /chat endpoint accepts and stores context."""
    response = client.post(
        "/chat",
        json={
            "message": "books about History",
            "context": {"user_preference": "concise_results"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    session_id = data["response"]["session_id"]

    # Get session and verify context was stored
    session_response = client.get(f"/sessions/{session_id}")
    session_data = session_response.json()
    assert "user_preference" in session_data["context"]
    assert session_data["context"]["user_preference"] == "concise_results"


def test_websocket_creates_session(client):
    """Test WebSocket endpoint creates new session."""
    with client.websocket_connect("/ws/chat") as websocket:
        # Send message without session_id
        websocket.send_json({"message": "books"})

        # Should receive session_created message
        msg1 = websocket.receive_json()
        assert msg1["type"] == "session_created"
        assert "session_id" in msg1

        # Should receive progress messages
        messages = []
        while True:
            msg = websocket.receive_json()
            messages.append(msg)
            if msg["type"] == "complete":
                break

        # Verify we got progress messages
        progress_msgs = [m for m in messages if m["type"] == "progress"]
        assert len(progress_msgs) > 0
        assert any("Compiling query" in m["message"] for m in progress_msgs)


def test_websocket_with_existing_session(client):
    """Test WebSocket endpoint uses existing session."""
    # Create session via HTTP first
    response = client.post("/chat", json={"message": "test"})
    session_id = response.json()["response"]["session_id"]

    # Connect via WebSocket with session_id
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "message": "books",
            "session_id": session_id
        })

        # Should not create new session
        messages = []
        while True:
            msg = websocket.receive_json()
            messages.append(msg)
            if msg["type"] == "complete":
                break

        # Should not have session_created message
        assert not any(m["type"] == "session_created" for m in messages)

        # Should have complete response
        complete_msg = [m for m in messages if m["type"] == "complete"][0]
        assert complete_msg["response"]["session_id"] == session_id


def test_websocket_empty_message(client):
    """Test WebSocket endpoint rejects empty message."""
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"message": ""})

        # Should receive error
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "required" in msg["message"].lower()


def test_websocket_invalid_session(client):
    """Test WebSocket endpoint rejects invalid session_id."""
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "message": "books",
            "session_id": "nonexistent-session"
        })

        # Should receive error
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["message"].lower()


@pytest.mark.integration
def test_websocket_streaming_batches(client):
    """Test WebSocket streams results in batches.

    Requires OPENAI_API_KEY environment variable.
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "message": "books published by Oxford"
        })

        # Collect all messages
        messages = []
        while True:
            msg = websocket.receive_json()
            messages.append(msg)
            if msg["type"] == "complete":
                break

        # Should have session_created
        assert any(m["type"] == "session_created" for m in messages)

        # Should have progress messages
        progress_msgs = [m for m in messages if m["type"] == "progress"]
        assert len(progress_msgs) >= 2  # At least compiling and executing

        # Should have complete message
        complete_msgs = [m for m in messages if m["type"] == "complete"]
        assert len(complete_msgs) == 1

        # If results found, should have batch messages
        batch_msgs = [m for m in messages if m["type"] == "batch"]
        if batch_msgs:
            # Verify batch structure
            for batch in batch_msgs:
                assert "candidates" in batch
                assert "batch_num" in batch
                assert "total_batches" in batch
                assert len(batch["candidates"]) <= 10  # Batch size limit
