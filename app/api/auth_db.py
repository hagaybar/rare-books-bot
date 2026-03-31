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
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    model TEXT DEFAULT '',
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


def _migrate_token_usage(conn: sqlite3.Connection) -> None:
    """Add input/output/cost columns to token_usage if missing.

    For existing rows, split tokens_used evenly between input and output.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(token_usage)").fetchall()}
    if "input_tokens" in cols:
        return  # Already migrated
    conn.execute("ALTER TABLE token_usage ADD COLUMN input_tokens INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE token_usage ADD COLUMN output_tokens INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE token_usage ADD COLUMN cost_usd REAL DEFAULT 0.0")
    conn.execute("ALTER TABLE token_usage ADD COLUMN model TEXT DEFAULT ''")
    # Backfill existing data: split total evenly
    conn.execute(
        "UPDATE token_usage SET input_tokens = tokens_used / 2, "
        "output_tokens = tokens_used - tokens_used / 2"
    )
    conn.commit()


def init_auth_db() -> None:
    """Initialize auth database with schema and default settings."""
    AUTH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(AUTH_DB_PATH))
    conn.executescript(SCHEMA)
    _migrate_token_usage(conn)
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


def purge_audit_log(days: int = 90) -> int:
    """Delete audit log entries older than N days. Returns count of deleted rows."""
    conn = get_auth_db()
    try:
        cursor = conn.execute(
            "DELETE FROM audit_log WHERE timestamp < datetime('now', ?)",
            (f'-{days} days',),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()
