-- Chat session database schema
--
-- Design decisions:
-- - TEXT for datetime: SQLite has limited datetime types; store as ISO strings
-- - JSON for complex objects: QueryPlan/CandidateSet stored as JSON TEXT
-- - CASCADE DELETE: Deleting session deletes all messages
-- - Indexes: Optimize for session retrieval and user queries
-- - expired_at NULL: Active sessions have NULL, expired have timestamp

-- Chat sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL,  -- ISO datetime
    updated_at TEXT NOT NULL,  -- ISO datetime
    context TEXT,              -- JSON-serialized dict
    metadata TEXT,             -- JSON-serialized dict
    expired_at TEXT,           -- NULL if active, ISO datetime if expired
    UNIQUE(session_id)
);

-- Index for user_id lookups (multi-user support)
CREATE INDEX IF NOT EXISTS idx_sessions_user_id
ON chat_sessions(user_id);

-- Index for expiration queries
CREATE INDEX IF NOT EXISTS idx_sessions_expired
ON chat_sessions(expired_at);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    query_plan TEXT,          -- JSON-serialized QueryPlan
    candidate_set TEXT,        -- JSON-serialized CandidateSet
    timestamp TEXT NOT NULL,   -- ISO datetime
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

-- Index for session message retrieval
CREATE INDEX IF NOT EXISTS idx_messages_session
ON chat_messages(session_id, timestamp);

-- Index for timestamp-based queries
CREATE INDEX IF NOT EXISTS idx_messages_timestamp
ON chat_messages(timestamp DESC);
