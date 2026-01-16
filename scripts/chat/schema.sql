-- Chat session database schema
--
-- Design decisions:
-- - TEXT for datetime: SQLite has limited datetime types; store as ISO strings
-- - JSON for complex objects: QueryPlan/CandidateSet stored as JSON TEXT
-- - CASCADE DELETE: Deleting session deletes all messages
-- - Indexes: Optimize for session retrieval and user queries
-- - expired_at NULL: Active sessions have NULL, expired have timestamp
--
-- Two-Phase Conversation Support:
-- - phase column: Tracks query_definition or corpus_exploration
-- - active_subgroups table: Stores the currently defined CandidateSet
-- - user_goals table: Stores elicited user goals

-- Chat sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL,  -- ISO datetime
    updated_at TEXT NOT NULL,  -- ISO datetime
    context TEXT,              -- JSON-serialized dict
    metadata TEXT,             -- JSON-serialized dict
    expired_at TEXT,           -- NULL if active, ISO datetime if expired
    phase TEXT DEFAULT 'query_definition',  -- 'query_definition' or 'corpus_exploration'
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

-- =============================================================================
-- Two-Phase Conversation Support Tables
-- =============================================================================

-- Active subgroups table (stores the current CandidateSet being explored)
CREATE TABLE IF NOT EXISTS active_subgroups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,  -- One active subgroup per session
    defining_query TEXT NOT NULL,      -- Original query that created this subgroup
    filter_summary TEXT NOT NULL,      -- Natural language summary of filters
    record_ids TEXT NOT NULL,          -- JSON array of MMS IDs in subgroup
    candidate_count INTEGER NOT NULL,  -- Number of records in subgroup
    candidate_set TEXT,                -- JSON-serialized full CandidateSet (optional, may be large)
    created_at TEXT NOT NULL,          -- ISO datetime
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

-- Index for session lookups
CREATE INDEX IF NOT EXISTS idx_subgroups_session
ON active_subgroups(session_id);

-- User goals table (stores elicited user goals for exploration)
CREATE TABLE IF NOT EXISTS user_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    goal_type TEXT NOT NULL,           -- 'find_specific', 'analyze_corpus', 'compare', 'discover'
    description TEXT NOT NULL,         -- Natural language goal description
    elicited_at TEXT NOT NULL,         -- ISO datetime
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
);

-- Index for session goal lookups
CREATE INDEX IF NOT EXISTS idx_goals_session
ON user_goals(session_id);

-- Index for phase lookups
CREATE INDEX IF NOT EXISTS idx_sessions_phase
ON chat_sessions(phase);
