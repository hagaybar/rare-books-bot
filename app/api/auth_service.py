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
