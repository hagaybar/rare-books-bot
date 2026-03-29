"""Tests for auth endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def setup_auth_db(tmp_path, monkeypatch):
    """Use temp auth DB for all tests."""
    import app.api.auth_db as auth_db_mod

    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_db_mod, "AUTH_DB_PATH", db_path)
    auth_db_mod.init_auth_db()

    # Create test users
    from app.api.auth_service import create_user

    create_user("admin", "adminpass123", "admin")
    create_user("limited_user", "limitedpass1", "limited")


@pytest.fixture
def client():
    from app.api.main import app

    return TestClient(app)


def test_login_success(client):
    resp = client.post("/auth/login", json={"username": "admin", "password": "adminpass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert resp.json()["role"] == "admin"


def test_login_wrong_password(client):
    resp = client.post("/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_guest_session(client):
    resp = client.post("/auth/guest")
    assert resp.status_code == 200
    assert "access_token" in resp.cookies
    assert resp.json()["role"] == "guest"


def test_me_endpoint(client):
    # Login first
    client.post("/auth/login", json={"username": "admin", "password": "adminpass123"})
    # Use the cookie (TestClient persists cookies across requests)
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    assert resp.json()["role"] == "admin"


def test_me_without_auth(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_admin_list_users(client):
    client.post("/auth/login", json={"username": "admin", "password": "adminpass123"})
    resp = client.get("/auth/users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) >= 2


def test_non_admin_cannot_list_users(client):
    client.post("/auth/login", json={"username": "limited_user", "password": "limitedpass1"})
    resp = client.get("/auth/users")
    assert resp.status_code == 403
