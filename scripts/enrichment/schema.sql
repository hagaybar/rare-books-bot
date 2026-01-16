-- Enrichment cache database schema
--
-- Stores cached enrichment data to avoid repeated external requests.
-- TTL-based expiration for freshness.
--
-- Design:
-- - enrichment_cache: Main cache table for all enrichment results
-- - nli_identifiers: Cached NLI authority → external ID mappings
-- - enrichment_queue: Background enrichment job queue

-- Main enrichment cache
CREATE TABLE IF NOT EXISTS enrichment_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Entity identification
    entity_type TEXT NOT NULL,  -- 'agent', 'place', 'publisher', 'subject', 'work'
    entity_value TEXT NOT NULL,  -- Original entity value
    normalized_key TEXT NOT NULL,  -- Normalized lookup key (casefolded, cleaned)

    -- External identifiers
    wikidata_id TEXT,  -- Q123456
    viaf_id TEXT,      -- 12345678
    isni_id TEXT,      -- 0000 0001 2345 6789
    loc_id TEXT,       -- n12345678
    nli_id TEXT,       -- 987007261327805171

    -- Enrichment data (JSON)
    person_info TEXT,   -- JSON: birth/death, nationality, occupations
    place_info TEXT,    -- JSON: coordinates, country, historical names
    label TEXT,         -- Display label
    description TEXT,   -- Short description
    image_url TEXT,     -- Image URL if available
    wikipedia_url TEXT, -- Wikipedia article URL
    external_links TEXT,-- JSON: additional external links

    -- Metadata
    source TEXT NOT NULL,  -- Primary source: 'wikidata', 'viaf', 'nli', etc.
    confidence REAL DEFAULT 0.0,
    raw_data TEXT,         -- Full JSON response for debugging
    fetched_at TEXT NOT NULL,  -- ISO datetime
    expires_at TEXT,       -- ISO datetime for TTL

    -- Constraints
    UNIQUE(entity_type, normalized_key, source)
);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_cache_entity
ON enrichment_cache(entity_type, normalized_key);

CREATE INDEX IF NOT EXISTS idx_cache_wikidata
ON enrichment_cache(wikidata_id);

CREATE INDEX IF NOT EXISTS idx_cache_viaf
ON enrichment_cache(viaf_id);

CREATE INDEX IF NOT EXISTS idx_cache_expiry
ON enrichment_cache(expires_at);


-- NLI authority to external ID mapping cache
-- Separate table because NLI page scraping is expensive
CREATE TABLE IF NOT EXISTS nli_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- NLI identifier
    nli_id TEXT NOT NULL UNIQUE,  -- 987007261327805171
    nli_uri TEXT,                  -- Full JSONLD URI

    -- External identifiers found on NLI page
    wikidata_id TEXT,
    viaf_id TEXT,
    isni_id TEXT,
    loc_id TEXT,

    -- Other identifiers (JSON)
    other_ids TEXT,  -- JSON: {"gnd": "123", "bnf": "456", ...}

    -- Metadata
    fetch_method TEXT NOT NULL,  -- 'playwright', 'requests', 'manual'
    fetched_at TEXT NOT NULL,
    expires_at TEXT,

    -- Status
    status TEXT DEFAULT 'success'  -- 'success', 'not_found', 'error', 'blocked'
);

CREATE INDEX IF NOT EXISTS idx_nli_wikidata
ON nli_identifiers(wikidata_id);

CREATE INDEX IF NOT EXISTS idx_nli_viaf
ON nli_identifiers(viaf_id);


-- Enrichment job queue for background processing
CREATE TABLE IF NOT EXISTS enrichment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Request
    entity_type TEXT NOT NULL,
    entity_value TEXT NOT NULL,
    nli_id TEXT,  -- If known

    -- Queue management
    priority INTEGER DEFAULT 0,  -- Higher = more urgent
    status TEXT DEFAULT 'pending',  -- 'pending', 'processing', 'completed', 'failed'
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Timestamps
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    next_retry_at TEXT,

    -- Error tracking
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_queue_status
ON enrichment_queue(status, priority DESC, created_at);

CREATE INDEX IF NOT EXISTS idx_queue_entity
ON enrichment_queue(entity_type, entity_value);


-- Statistics and rate limiting
CREATE TABLE IF NOT EXISTS enrichment_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,  -- 'wikidata', 'viaf', 'nli'
    date TEXT NOT NULL,    -- YYYY-MM-DD
    request_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    cache_hit_count INTEGER DEFAULT 0,
    avg_response_ms REAL,
    UNIQUE(source, date)
);
