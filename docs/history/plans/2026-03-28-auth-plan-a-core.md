# Auth Plan A: Core Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure the backend with JWT auth, 4-tier roles, login/guest/refresh endpoints, and role-based route protection. After this plan, the API is fully secured and testable with curl.

**Architecture:** Separate `auth.db` for user data. PyJWT for token encoding, passlib[bcrypt] for passwords. FastAPI dependency injection (`Depends(require_role(...))`) on each router for role enforcement. httpOnly cookies for JWT transport.

**Tech Stack:** Python 3.11+, FastAPI, PyJWT, passlib[bcrypt], SQLite

**Spec:** `docs/superpowers/specs/2026-03-28-auth-security-design.md`
**Branch:** `feature/auth-security`

**This is Plan A of 3:**
- **Plan A (this):** Auth core — DB, endpoints, middleware, CLI
- **Plan B:** Frontend — login page, auth store, route guards, sidebar filtering
- **Plan C:** Security hardening — rate limiting, quotas, moderation, PII, admin panel

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `app/api/auth_db.py` | Create | Auth database init, connection, schema |
| `app/api/auth_models.py` | Create | Pydantic models for auth requests/responses |
| `app/api/auth_service.py` | Create | Business logic: password hashing, JWT create/validate, user CRUD |
| `app/api/auth_routes.py` | Create | FastAPI router: login, guest, refresh, me, user CRUD |
| `app/api/auth_deps.py` | Create | FastAPI dependencies: get_current_user, require_role |
| `app/api/main.py` | Modify | Mount auth router, update CORS, add cookie config |
| `app/cli.py` | Modify | Add create-user command |
| `tests/app/test_auth.py` | Create | Auth endpoint tests |

---

### Task 1: Dependencies + Auth Database

**Files:**
- Modify: `pyproject.toml`
- Create: `app/api/auth_db.py`

- [ ] **Step 1: Add dependencies**

```bash
poetry add PyJWT passlib[bcrypt]
```

- [ ] **Step 2: Create auth database module**

Create `app/api/auth_db.py`:

```python
"""Auth database initialization and connection management."""
import sqlite3
from pathlib import Path

AUTH_DB_PATH = Path("data/auth/auth.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'full', 'limited', 'guest')),
    token_limit INTEGER DEFAULT 50000,
    is_active BOOLEAN DEFAULT 1,
    locked_until TEXT,
    failed_login_attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by INTEGER REFERENCES users(id),
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    month TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    UNIQUE(user_id, month)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    user_id INTEGER,
    username TEXT,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
"""

INITIAL_SETTINGS = {
    "chat_enabled": "true",
    "monthly_cost_cap_usd": "50",
}


def init_auth_db() -> None:
    """Initialize auth database with schema and default settings."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.executescript(SCHEMA)
    for key, value in INITIAL_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


def get_auth_db() -> sqlite3.Connection:
    """Get a connection to the auth database."""
    if not AUTH_DB_PATH.exists():
        init_auth_db()
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

- [ ] **Step 3: Verify**

```bash
poetry run python -c "from app.api.auth_db import init_auth_db, get_auth_db; init_auth_db(); conn = get_auth_db(); print(conn.execute('SELECT count(*) FROM settings').fetchone()[0], 'settings'); conn.close()"
```

Expected: `2 settings`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml poetry.lock app/api/auth_db.py
git commit -m "feat: add auth database schema and connection management"
```

---

### Task 2: Auth Service (Password Hashing + JWT)

**Files:**
- Create: `app/api/auth_models.py`
- Create: `app/api/auth_service.py`

- [ ] **Step 1: Create Pydantic models**

Create `app/api/auth_models.py`:

```python
"""Pydantic models for auth requests and responses."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    message: str = "Login successful"
    username: str
    role: str


class UserInfo(BaseModel):
    user_id: int
    username: str
    role: str
    is_active: bool = True
    token_limit: int | None = None
    tokens_used_this_month: int | None = None


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: str = Field(..., pattern="^(admin|full|limited|guest)$")
    token_limit: int = 50000


class UpdateUserRequest(BaseModel):
    role: str | None = Field(None, pattern="^(admin|full|limited|guest)$")
    is_active: bool | None = None
    token_limit: int | None = None
    new_password: str | None = Field(None, min_length=8)


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    last_login: str | None
    tokens_used_this_month: int = 0
    token_limit: int = 50000
```

- [ ] **Step 2: Create auth service**

Create `app/api/auth_service.py`:

```python
"""Auth business logic: password hashing, JWT creation/validation, user CRUD."""
import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from passlib.hash import bcrypt

from app.api.auth_db import get_auth_db

# JWT configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_SECRET_PREVIOUS = os.environ.get("JWT_SECRET_PREVIOUS", "")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Validate JWT secret at import time
if not JWT_SECRET:
    # Auto-generate for development — print warning
    import secrets
    JWT_SECRET = secrets.token_hex(32)
    print("WARNING: JWT_SECRET not set. Using auto-generated secret (sessions won't survive restart).")
elif len(JWT_SECRET) < 32:
    raise ValueError("JWT_SECRET must be at least 32 characters long.")


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.verify(password, password_hash)


def create_access_token(user_id: int, username: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_guest_token() -> str:
    payload = {
        "user_id": f"guest-{uuid.uuid4().hex[:8]}",
        "username": "guest",
        "role": "guest",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    token = uuid.uuid4().hex
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    conn = get_auth_db()
    try:
        conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, token_hash, expires_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return token


def validate_access_token(token: str) -> dict | None:
    """Validate JWT and return payload, or None if invalid."""
    for secret in [JWT_SECRET, JWT_SECRET_PREVIOUS]:
        if not secret:
            continue
        try:
            return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            continue
    return None


def validate_refresh_token(token: str) -> dict | None:
    """Validate refresh token against DB. Returns user row or None."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_auth_db()
    try:
        row = conn.execute(
            """SELECT rt.user_id, u.username, u.role, u.is_active
               FROM refresh_tokens rt
               JOIN users u ON u.id = rt.user_id
               WHERE rt.token_hash = ? AND rt.expires_at > datetime('now')""",
            (token_hash,),
        ).fetchone()
        if row and row["is_active"]:
            return dict(row)
        return None
    finally:
        conn.close()


def revoke_refresh_tokens(user_id: int) -> None:
    conn = get_auth_db()
    try:
        conn.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict | None:
    """Validate username/password. Returns user dict or None."""
    conn = get_auth_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not user:
            return None
        if not user["is_active"]:
            return None
        # Check lockout
        if user["locked_until"]:
            locked = datetime.fromisoformat(user["locked_until"])
            if datetime.now(timezone.utc) < locked:
                return None  # Still locked
            # Lock expired, reset
            conn.execute(
                "UPDATE users SET locked_until = NULL, failed_login_attempts = 0 WHERE id = ?",
                (user["id"],),
            )
            conn.commit()

        if not verify_password(password, user["password_hash"]):
            # Increment failed attempts
            attempts = user["failed_login_attempts"] + 1
            if attempts >= 5:
                lock_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                conn.execute(
                    "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                    (attempts, lock_until.isoformat(), user["id"]),
                )
            else:
                conn.execute(
                    "UPDATE users SET failed_login_attempts = ? WHERE id = ?",
                    (attempts, user["id"]),
                )
            conn.commit()
            return None

        # Success — reset attempts, update last_login
        conn.execute(
            "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login = datetime('now') WHERE id = ?",
            (user["id"],),
        )
        conn.commit()
        return dict(user)
    finally:
        conn.close()


def create_user(username: str, password: str, role: str, token_limit: int = 50000, created_by: int | None = None) -> int:
    conn = get_auth_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role, token_limit, created_by) VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(password), role, token_limit, created_by),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def audit_log(action: str, user_id: int | None = None, username: str | None = None,
              details: str | None = None, ip_address: str | None = None) -> None:
    conn = get_auth_db()
    try:
        conn.execute(
            "INSERT INTO audit_log (user_id, username, action, details, ip_address) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, action, details, ip_address),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 3: Verify imports**

```bash
poetry run python -c "from app.api.auth_service import hash_password, verify_password, create_access_token, validate_access_token; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add app/api/auth_models.py app/api/auth_service.py
git commit -m "feat: add auth service — password hashing, JWT, user CRUD"
```

---

### Task 3: Auth Dependencies (Role Enforcement)

**Files:**
- Create: `app/api/auth_deps.py`

- [ ] **Step 1: Create FastAPI dependencies**

Create `app/api/auth_deps.py`:

```python
"""FastAPI dependencies for authentication and authorization."""
from fastapi import Request, HTTPException, status

from app.api.auth_service import validate_access_token

ROLE_HIERARCHY = {"admin": 4, "full": 3, "limited": 2, "guest": 1}


def get_current_user(request: Request) -> dict:
    """Extract and validate JWT from cookie. Returns user payload."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = validate_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


def require_role(minimum_role: str):
    """Factory that returns a dependency requiring a minimum role level."""
    min_level = ROLE_HIERARCHY.get(minimum_role, 0)

    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        user_level = ROLE_HIERARCHY.get(user.get("role", ""), 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role} role or higher",
            )
        return user

    return dependency
```

- [ ] **Step 2: Verify**

```bash
poetry run python -c "from app.api.auth_deps import require_role, get_current_user; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/auth_deps.py
git commit -m "feat: add auth dependencies — get_current_user, require_role"
```

---

### Task 4: Auth Routes (Login, Guest, Refresh, Me, User CRUD)

**Files:**
- Create: `app/api/auth_routes.py`

- [ ] **Step 1: Create auth router**

Create `app/api/auth_routes.py`:

```python
"""Auth API routes: login, guest, refresh, me, user CRUD."""
from fastapi import APIRouter, HTTPException, Request, Response, Depends, status

from app.api.auth_models import (
    LoginRequest, TokenResponse, UserInfo, CreateUserRequest,
    UpdateUserRequest, UserListItem,
)
from app.api.auth_service import (
    authenticate_user, create_access_token, create_guest_token,
    create_refresh_token, validate_refresh_token, revoke_refresh_tokens,
    create_user, audit_log, hash_password,
)
from app.api.auth_deps import require_role, get_current_user
from app.api.auth_db import get_auth_db

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_KWARGS = {
    "httponly": True,
    "samesite": "lax",
    "path": "/",
}


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None = None):
    response.set_cookie("access_token", access_token, max_age=900, **COOKIE_KWARGS)  # 15 min
    if refresh_token:
        response.set_cookie("refresh_token", refresh_token, max_age=604800, **COOKIE_KWARGS)  # 7 days


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, response: Response):
    ip = request.client.host if request.client else "unknown"
    user = authenticate_user(body.username, body.password)
    if not user:
        audit_log("login_failed", username=body.username, ip_address=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user["id"], user["username"], user["role"])
    refresh_token = create_refresh_token(user["id"])
    _set_auth_cookies(response, access_token, refresh_token)

    audit_log("login", user_id=user["id"], username=user["username"], ip_address=ip)
    return TokenResponse(username=user["username"], role=user["role"])


@router.post("/guest")
async def guest_session(response: Response):
    token = create_guest_token()
    response.set_cookie("access_token", token, max_age=86400, **COOKIE_KWARGS)  # 24h
    return {"message": "Guest session created", "role": "guest"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    user = validate_refresh_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    access_token = create_access_token(user["user_id"], user["username"], user["role"])
    response.set_cookie("access_token", access_token, max_age=900, **COOKIE_KWARGS)
    return {"message": "Token refreshed", "role": user["role"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    user = get_current_user(request)
    if isinstance(user.get("user_id"), int):
        revoke_refresh_tokens(user["user_id"])
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserInfo)
async def get_me(user=Depends(get_current_user)):
    user_id = user.get("user_id")
    if isinstance(user_id, str) and user_id.startswith("guest"):
        return UserInfo(user_id=0, username="guest", role="guest")

    conn = get_auth_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        # Get token usage for this month
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        usage = conn.execute(
            "SELECT tokens_used FROM token_usage WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchone()
        return UserInfo(
            user_id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            token_limit=row["token_limit"],
            tokens_used_this_month=usage["tokens_used"] if usage else 0,
        )
    finally:
        conn.close()


# --- Admin user management ---

@router.get("/users", response_model=list[UserListItem])
async def list_users(admin=Depends(require_role("admin"))):
    conn = get_auth_db()
    try:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        rows = conn.execute(
            """SELECT u.*, COALESCE(tu.tokens_used, 0) as tokens_used_this_month
               FROM users u
               LEFT JOIN token_usage tu ON tu.user_id = u.id AND tu.month = ?
               ORDER BY u.id""",
            (month,),
        ).fetchall()
        return [UserListItem(
            id=r["id"], username=r["username"], role=r["role"],
            is_active=bool(r["is_active"]), last_login=r["last_login"],
            tokens_used_this_month=r["tokens_used_this_month"],
            token_limit=r["token_limit"],
        ) for r in rows]
    finally:
        conn.close()


@router.post("/users", status_code=201)
async def create_user_endpoint(body: CreateUserRequest, admin=Depends(require_role("admin"))):
    try:
        user_id = create_user(body.username, body.password, body.role, body.token_limit, admin["user_id"])
        audit_log("user_created", user_id=admin["user_id"], username=admin["username"],
                  details=f"Created user '{body.username}' with role '{body.role}'")
        return {"id": user_id, "username": body.username, "role": body.role}
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(400, f"Username '{body.username}' already exists")
        raise


@router.put("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest, admin=Depends(require_role("admin"))):
    conn = get_auth_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        updates = []
        params = []
        if body.role is not None:
            updates.append("role = ?")
            params.append(body.role)
        if body.is_active is not None:
            updates.append("is_active = ?")
            params.append(int(body.is_active))
        if body.token_limit is not None:
            updates.append("token_limit = ?")
            params.append(body.token_limit)
        if body.new_password:
            updates.append("password_hash = ?")
            params.append(hash_password(body.new_password))

        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        audit_log("user_updated", user_id=admin["user_id"], username=admin["username"],
                  details=f"Updated user {user_id}: {body.model_dump(exclude_none=True)}")
        return {"message": "User updated"}
    finally:
        conn.close()
```

- [ ] **Step 2: Verify import**

```bash
poetry run python -c "from app.api.auth_routes import router; print(f'Routes: {len(router.routes)}')"
```

- [ ] **Step 3: Commit**

```bash
git add app/api/auth_routes.py
git commit -m "feat: add auth routes — login, guest, refresh, me, user CRUD"
```

---

### Task 5: Mount Auth + Protect Existing Routes

**Files:**
- Modify: `app/api/main.py`

- [ ] **Step 1: Mount auth router and init DB**

In `app/api/main.py`:
- Import and mount auth router: `from app.api.auth_routes import router as auth_router` + `app.include_router(auth_router)`
- Call `init_auth_db()` on startup
- Update CORS: change `allow_origins=["*"]` to read from `CORS_ORIGIN` env var with `["*"]` as default

- [ ] **Step 2: Add role dependencies to existing routers**

Add `Depends(require_role(...))` to each existing router's endpoints:
- `/chat` endpoint: `Depends(require_role("limited"))`
- `/ws/chat` WebSocket: validate JWT from cookies at connection time
- `/network/*`: `Depends(require_role("guest"))` (accessible to all)
- `/metadata/enrichment/agents`, `/metadata/enrichment/facets`, `/metadata/enrichment/agent-records`: `Depends(require_role("guest"))`
- `/metadata/coverage`, `/metadata/issues`, `/metadata/corrections/*`, etc.: `Depends(require_role("full"))`
- `/diagnostics/*`: `Depends(require_role("full"))`
- `/health`: No auth (public basic health check)
- `/health/extended`: `Depends(require_role("full"))`

IMPORTANT: Don't modify every single endpoint individually — instead, add the dependency at the router level where possible, or create a simple middleware/dependency that checks the path prefix.

- [ ] **Step 3: Commit**

```bash
git add app/api/main.py
git commit -m "feat: mount auth router, protect existing endpoints with role deps"
```

---

### Task 6: CLI Create-User Command

**Files:**
- Modify: `app/cli.py`

- [ ] **Step 1: Add create-user command**

Add to `app/cli.py`:

```python
@app.command()
def create_user(
    username: str = typer.Argument(..., help="Username"),
    password: str = typer.Argument(..., help="Password (min 8 chars)"),
    role: str = typer.Option("admin", help="Role: admin, full, limited, guest"),
):
    """Create a new user (for bootstrapping the first admin)."""
    from app.api.auth_db import init_auth_db
    from app.api.auth_service import create_user as _create_user
    init_auth_db()
    try:
        user_id = _create_user(username, password, role)
        print(f"Created user '{username}' (id={user_id}, role={role})")
    except Exception as e:
        print(f"Error: {e}")
        raise typer.Exit(1)
```

- [ ] **Step 2: Test**

```bash
poetry run python -m app.cli create-user testadmin testpassword123 --role admin
poetry run python -c "from app.api.auth_db import get_auth_db; c=get_auth_db(); print(c.execute('SELECT username, role FROM users').fetchall())"
```

- [ ] **Step 3: Commit**

```bash
git add app/cli.py
git commit -m "feat: add create-user CLI command for admin bootstrapping"
```

---

### Task 7: Auth Tests

**Files:**
- Create: `tests/app/test_auth.py`

- [ ] **Step 1: Write tests**

Create `tests/app/test_auth.py`:

```python
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
    # Create a test admin
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
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "adminpass123"})
    # Use the cookie
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
```

- [ ] **Step 2: Run tests**

```bash
poetry run pytest tests/app/test_auth.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit and push**

```bash
git add tests/app/test_auth.py
git commit -m "feat: add auth endpoint tests"
git push origin feature/auth-security
```
