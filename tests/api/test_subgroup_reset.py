"""Reset endpoint tests for DELETE /sessions/{id}/subgroup (issue #60 part 2).

Deterministic, LLM-free: exercises only the held-set reset route against the
live SessionStore the app wires at startup. Reuses the app-test suite's JWT
auth pattern (admin cookie via tests.app.conftest.make_test_token), which the
authenticated session routes (get_session / expire_session) accept.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.chat.session_store import SessionStore
from tests.app.conftest import make_test_token

# The admin test token carries user_id=1; the route's ownership check is
# bypassed for the admin role, so this is the user the held set is owned by.
AUTHED_USER_ID = "1"


@pytest.fixture(scope="function")
def sessions_db_path():
    """Temp sessions DB file shared by the app store and the test store."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        path = Path(tmp.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture(scope="function")
def authed_client(sessions_db_path, monkeypatch):
    """TestClient with an admin JWT cookie and an isolated sessions DB.

    Mirrors the `client` fixture in tests/app/test_api.py: points
    SESSIONS_DB_PATH at a temp file and resets the module-global session store
    so startup rebuilds it against the temp DB.
    """
    monkeypatch.setenv("SESSIONS_DB_PATH", str(sessions_db_path))

    import app.api.main as main_module

    main_module.session_store = None
    main_module.db_path = None

    with TestClient(app, cookies={"access_token": make_test_token()}) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def store(sessions_db_path):
    """A SessionStore on the same temp DB the app uses.

    A separate connection (own thread) avoids SQLite's single-thread-per-
    connection restriction: the TestClient drives the route on its own thread
    via its own store; this fixture writes/reads the held set from the test
    thread. Both connections commit to the same on-disk file.
    """
    return SessionStore(sessions_db_path)


def test_reset_subgroup_clears_held_set(authed_client, store):
    """DELETE /sessions/{id}/subgroup clears the held set; next get is None."""
    from scripts.chat.models import ActiveSubgroup

    session = store.create_session(user_id=AUTHED_USER_ID)
    store.set_active_subgroup(
        session.session_id,
        ActiveSubgroup(defining_query="q", filter_summary="", record_ids=["1", "2"]),
    )

    resp = authed_client.delete(f"/sessions/{session.session_id}/subgroup")
    assert resp.status_code == 200
    assert store.get_active_subgroup(session.session_id) is None


def test_reset_subgroup_noop_when_none(authed_client, store):
    """Reset on a session with no held set is a 200 no-op."""
    session = store.create_session(user_id=AUTHED_USER_ID)
    resp = authed_client.delete(f"/sessions/{session.session_id}/subgroup")
    assert resp.status_code == 200


def test_reset_subgroup_404_for_missing_session(authed_client):
    """Unknown session id returns 404."""
    resp = authed_client.delete("/sessions/does-not-exist/subgroup")
    assert resp.status_code == 404
