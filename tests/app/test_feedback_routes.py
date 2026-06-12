"""POST /feedback: auth, ownership, save-first, best-effort GitHub sync.

Spec: docs/superpowers/specs/2026-06-12-mark-as-problematic-design.md
Fixtures follow the patterns in tests/app/test_api.py (TestClient with/without
make_test_token() cookie; sessions seeded via SessionStore against the test
sessions DB the app uses through the SESSIONS_DB_PATH env var).
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.chat.models import Message
from scripts.chat.session_store import SessionStore
from tests.app.conftest import make_test_token

TEST_USER_ID = 7
TEST_USERNAME = "tester"


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Clear the in-process rate-limit window between tests."""
    try:
        from app.api import feedback_routes

        feedback_routes._recent.clear()
    except ImportError:
        pass  # route module not implemented yet (TDD red phase)
    yield


@pytest.fixture(scope="function")
def test_sessions_db():
    """Temporary sessions database (same pattern as tests/app/test_api.py)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    yield tmp_path

    if tmp_path.exists():
        tmp_path.unlink()


@pytest.fixture(scope="function")
def _app_env(test_sessions_db, tmp_path, monkeypatch):
    """Point the app at the test sessions DB and a temp feedback payload dir."""
    monkeypatch.setenv("SESSIONS_DB_PATH", str(test_sessions_db))
    monkeypatch.setenv("FEEDBACK_DIR", str(tmp_path / "feedback"))

    # Reset global state so lifespan rebuilds the session store from env
    import app.api.main as main_module

    main_module.session_store = None
    main_module.db_path = None
    return test_sessions_db


@pytest.fixture(scope="function")
def client(_app_env):
    """Authenticated client with a non-admin ('limited') user."""
    token = make_test_token(role="limited", user_id=TEST_USER_ID, username=TEST_USERNAME)
    with TestClient(app, cookies={"access_token": token}) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def admin_client(_app_env):
    """Authenticated client with an admin user (token via tests/app/conftest.py)."""
    token = make_test_token(role="admin", user_id=1, username="testadmin")
    with TestClient(app, cookies={"access_token": token}) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def anon_client(_app_env):
    """Client with no auth cookie."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def own_session_with_message(test_sessions_db):
    """Session owned by the test user, with one user + one assistant message."""
    store = SessionStore(test_sessions_db)
    session = store.create_session(user_id=str(TEST_USER_ID))
    store.add_message(session.session_id, Message(role="user", content="who printed in Venice?"))
    message_id = store.add_message(
        session.session_id, Message(role="assistant", content="Aldus Manutius, among others.")
    )
    store.close()
    return session.session_id, message_id


@pytest.fixture(scope="function")
def other_user_session(test_sessions_db):
    """Session owned by a different user."""
    store = SessionStore(test_sessions_db)
    session = store.create_session(user_id="999")
    store.add_message(session.session_id, Message(role="user", content="hello"))
    store.close()
    return session.session_id


class TestPostFeedback:
    def test_requires_auth(self, anon_client):
        assert anon_client.post(
            "/feedback", json={"kind": "general", "comment": "x"}
        ).status_code in (401, 403)

    def test_general_requires_comment(self, client):
        resp = client.post("/feedback", json={"kind": "general"})
        assert resp.status_code == 422

    def test_message_kind_requires_session_and_message(self, client):
        assert client.post("/feedback", json={"kind": "message"}).status_code == 422

    def test_unknown_session_404(self, client):
        resp = client.post(
            "/feedback",
            json={"kind": "message", "session_id": "ghost", "message_id": 1},
        )
        assert resp.status_code == 404

    def test_other_users_session_403(self, client, other_user_session):
        resp = client.post(
            "/feedback",
            json={"kind": "message", "session_id": other_user_session, "message_id": 1},
        )
        assert resp.status_code == 403

    def test_saves_report_and_returns_pending_when_github_disabled(
        self, client, own_session_with_message, monkeypatch
    ):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        resp = client.post(
            "/feedback",
            json={"kind": "message", "session_id": sid, "message_id": mid, "comment": "broken"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["report_id"].startswith("fb_")
        assert body["github_issue_url"] is None

    def test_synced_when_github_succeeds(self, client, own_session_with_message, monkeypatch):
        import scripts.feedback.github_client as gc

        monkeypatch.setattr(
            gc, "create_issue", lambda *a, **k: ("https://github.com/o/r/issues/12", 12)
        )
        sid, mid = own_session_with_message
        resp = client.post(
            "/feedback", json={"kind": "message", "session_id": sid, "message_id": mid}
        )
        assert resp.json()["github_issue_url"].endswith("/12")


class TestAdminEndpoints:
    def test_list_requires_admin(self, client):  # client = limited role
        assert client.get("/feedback").status_code == 403

    def test_admin_lists_reports(self, admin_client, own_session_with_message, client, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        client.post("/feedback", json={"kind": "message", "session_id": sid, "message_id": mid})
        resp = admin_client.get("/feedback")
        assert resp.status_code == 200
        assert resp.json()[0]["sync_status"] == "pending"

    def test_admin_sync_retries_pending(self, admin_client, client,
                                        own_session_with_message, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        sid, mid = own_session_with_message
        client.post("/feedback", json={"kind": "message", "session_id": sid, "message_id": mid})
        import scripts.feedback.github_client as gc
        monkeypatch.setattr(gc, "create_issue",
                            lambda *a, **k: ("https://github.com/o/r/issues/1", 1))
        resp = admin_client.post("/feedback/sync")
        assert resp.json()["synced"] >= 1
