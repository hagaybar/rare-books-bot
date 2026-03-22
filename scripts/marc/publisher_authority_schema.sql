-- Publisher Authority Records
-- Internal authority system for publisher identification and normalization
-- Two-table normalized design for efficient variant searching and indexing

-- ==============================================================================
-- PUBLISHER AUTHORITIES (one row per canonical publisher identity)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS publisher_authorities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,          -- English canonical form (e.g., "House of Elzevir")
    canonical_name_lower TEXT NOT NULL,    -- Lowercase for matching (e.g., "house of elzevir")
    type TEXT NOT NULL CHECK(type IN (
        'printing_house', 'private_press', 'modern_publisher',
        'bibliophile_society', 'unknown_marker', 'unresearched'
    )),
    dates_active TEXT,                     -- e.g., "1583-1712"
    date_start INTEGER,                   -- Start year (nullable)
    date_end INTEGER,                     -- End year (nullable)
    location TEXT,                        -- e.g., "Venice, Italy"
    notes TEXT,                           -- Historical notes
    sources TEXT,                         -- JSON array of reference URLs
    confidence REAL NOT NULL DEFAULT 0.5, -- 0.0-1.0
    is_missing_marker INTEGER NOT NULL DEFAULT 0, -- 1 if this represents "publisher unknown"
    viaf_id TEXT,                         -- VIAF authority ID
    wikidata_id TEXT,                     -- Wikidata Q-number
    cerl_id TEXT,                         -- CERL Thesaurus ID
    branch TEXT,                         -- Branch for printing dynasties (e.g., "Leiden", "Amsterdam")
    primary_language TEXT,               -- Dominant language/script of the press (ISO 639: "lat", "heb", "deu")
    created_at TEXT NOT NULL,             -- ISO 8601
    updated_at TEXT NOT NULL              -- ISO 8601
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pub_auth_canonical_lower
    ON publisher_authorities(canonical_name_lower);
CREATE INDEX IF NOT EXISTS idx_pub_auth_type
    ON publisher_authorities(type);
CREATE INDEX IF NOT EXISTS idx_pub_auth_location
    ON publisher_authorities(location);
CREATE INDEX IF NOT EXISTS idx_pub_auth_branch
    ON publisher_authorities(branch);
CREATE INDEX IF NOT EXISTS idx_pub_auth_primary_language
    ON publisher_authorities(primary_language);

-- ==============================================================================
-- PUBLISHER VARIANTS (one row per name variant, FK to publisher_authorities)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS publisher_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_id INTEGER NOT NULL REFERENCES publisher_authorities(id) ON DELETE CASCADE,
    variant_form TEXT NOT NULL,            -- The name as it appears in records
    variant_form_lower TEXT NOT NULL,      -- Lowercase for matching
    script TEXT DEFAULT 'latin',          -- 'latin', 'hebrew', 'arabic', 'other'
    language TEXT,                         -- ISO 639 code if known
    is_primary INTEGER NOT NULL DEFAULT 0, -- 1 if this is the form used in publisher_norm
    priority INTEGER NOT NULL DEFAULT 0, -- Higher = preferred for display ordering
    notes TEXT,                           -- e.g., "Latin genitive form"
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pub_var_authority
    ON publisher_variants(authority_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pub_var_form_lower
    ON publisher_variants(variant_form_lower);
CREATE INDEX IF NOT EXISTS idx_pub_var_script
    ON publisher_variants(script);
