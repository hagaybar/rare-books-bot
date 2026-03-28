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
