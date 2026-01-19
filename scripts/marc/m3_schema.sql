-- M3 Bibliographic Index Schema
-- SQLite schema for querying M1 canonical records with M2 normalization
-- Design principle: Support fielded queries with evidence/provenance

-- ==============================================================================
-- CORE TABLES
-- ==============================================================================

-- Records table (one row per MMS ID)
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,  -- ISO 8601 timestamp
    jsonl_line_number INTEGER   -- Line number in source JSONL for fast lookup
);

CREATE INDEX idx_records_mms_id ON records(mms_id);

-- Titles table (main title per record, denormalized for fast access)
CREATE TABLE titles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    title_type TEXT NOT NULL,  -- 'main', 'uniform', 'variant'
    value TEXT NOT NULL,
    source TEXT NOT NULL,  -- JSON array of MARC sources
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_titles_record_id ON titles(record_id);
CREATE INDEX idx_titles_type ON titles(title_type);
CREATE INDEX idx_titles_value ON titles(value);

-- ==============================================================================
-- IMPRINT TABLES (M1 + M2)
-- ==============================================================================

-- Imprints table (raw M1 data + M2 normalization)
CREATE TABLE imprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,  -- 0-indexed position in imprints array

    -- M1 raw values
    date_raw TEXT,
    place_raw TEXT,
    publisher_raw TEXT,
    manufacturer_raw TEXT,
    source_tags TEXT NOT NULL,  -- JSON array of MARC tags used

    -- M2 normalized date
    date_start INTEGER,  -- Year (null if unparsed)
    date_end INTEGER,    -- Year (null if unparsed)
    date_label TEXT,
    date_confidence REAL,
    date_method TEXT,

    -- M2 normalized place
    place_norm TEXT,  -- Normalized key (casefolded, cleaned)
    place_display TEXT,
    place_confidence REAL,
    place_method TEXT,

    -- M2 normalized publisher
    publisher_norm TEXT,  -- Normalized key (casefolded, cleaned)
    publisher_display TEXT,
    publisher_confidence REAL,
    publisher_method TEXT,

    -- M1 country from 008/15-17
    country_code TEXT,  -- MARC country code (e.g., 'it', 'fr', 'gw')
    country_name TEXT,  -- Normalized country name (e.g., 'italy', 'france', 'germany')

    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_imprints_record_id ON imprints(record_id);
CREATE INDEX idx_imprints_date_range ON imprints(date_start, date_end);
CREATE INDEX idx_imprints_place_norm ON imprints(place_norm);
CREATE INDEX idx_imprints_publisher_norm ON imprints(publisher_norm);
CREATE INDEX idx_imprints_date_confidence ON imprints(date_confidence);
CREATE INDEX idx_imprints_country_code ON imprints(country_code);
CREATE INDEX idx_imprints_country_name ON imprints(country_name);

-- ==============================================================================
-- SUBJECT TABLES
-- ==============================================================================

-- Subjects table
CREATE TABLE subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    value TEXT NOT NULL,  -- Display string
    source_tag TEXT NOT NULL,  -- MARC tag (650, 651, etc.)
    scheme TEXT,  -- Subject scheme from $2 (e.g., 'nli', 'lcsh')
    heading_lang TEXT,  -- Heading language from $9
    authority_uri TEXT,  -- Authority URI from $0 (e.g., NLI/VIAF/LC authority link)
    parts TEXT NOT NULL,  -- JSON object of structured parts
    source TEXT NOT NULL,  -- JSON array of MARC sources with occurrence
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_subjects_record_id ON subjects(record_id);
CREATE INDEX idx_subjects_value ON subjects(value);
CREATE INDEX idx_subjects_tag ON subjects(source_tag);
CREATE INDEX idx_subjects_scheme ON subjects(scheme);
CREATE INDEX idx_subjects_authority_uri ON subjects(authority_uri);

-- ==============================================================================
-- AGENT TABLES (Authors, Contributors, etc.)
-- ==============================================================================

-- Enhanced agents table with M1 raw + M2 normalized fields (Stage 4)
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    agent_index INTEGER NOT NULL,  -- Stable ordering within record

    -- M1 raw fields
    agent_raw TEXT NOT NULL,  -- Original agent name from MARC
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    role_raw TEXT,  -- Raw role from MARC (may be NULL)
    role_source TEXT,  -- 'relator_code', 'relator_term', 'inferred_from_tag', 'unknown'
    authority_uri TEXT,  -- Authority URI from $0 (e.g., NLI/VIAF/LC authority link)

    -- M2 normalized fields
    agent_norm TEXT NOT NULL,  -- Canonical normalized name
    agent_confidence REAL NOT NULL CHECK(agent_confidence BETWEEN 0 AND 1),
    agent_method TEXT NOT NULL,  -- 'base_clean', 'alias_map', 'ambiguous'
    agent_notes TEXT,  -- Warnings or ambiguity flags

    role_norm TEXT NOT NULL,  -- Normalized role from controlled vocabulary
    role_confidence REAL NOT NULL CHECK(role_confidence BETWEEN 0 AND 1),
    role_method TEXT NOT NULL,  -- 'relator_code', 'relator_term', 'inferred', 'manual_map', etc.

    -- Provenance (JSON array of SourceMetadata)
    provenance_json TEXT NOT NULL,

    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX idx_agents_record_id ON agents(record_id);
CREATE INDEX idx_agents_agent_norm ON agents(agent_norm);
CREATE INDEX idx_agents_role_norm ON agents(role_norm);
CREATE INDEX idx_agents_agent_role ON agents(agent_norm, role_norm);  -- Composite for "printer X" queries
CREATE INDEX idx_agents_type ON agents(agent_type);
CREATE INDEX idx_agents_authority_uri ON agents(authority_uri);

-- ==============================================================================
-- LANGUAGE TABLE
-- ==============================================================================

-- Languages table
CREATE TABLE languages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    code TEXT NOT NULL,  -- ISO 639-2 language code
    source TEXT NOT NULL,  -- MARC source (e.g., '041[0]$a' or '008/35-37')
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_languages_record_id ON languages(record_id);
CREATE INDEX idx_languages_code ON languages(code);

-- ==============================================================================
-- NOTES TABLE
-- ==============================================================================

-- Notes table
CREATE TABLE notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    tag TEXT NOT NULL,  -- MARC tag (500, 502, 505, etc.)
    value TEXT NOT NULL,
    source TEXT NOT NULL,  -- JSON array of MARC sources with occurrence
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_notes_record_id ON notes(record_id);
CREATE INDEX idx_notes_tag ON notes(tag);

-- ==============================================================================
-- PHYSICAL DESCRIPTION TABLE
-- ==============================================================================

-- Physical descriptions table
CREATE TABLE physical_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    value TEXT NOT NULL,
    source TEXT NOT NULL,  -- JSON array of MARC sources
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_physical_descriptions_record_id ON physical_descriptions(record_id);

-- ==============================================================================
-- FULL-TEXT SEARCH (FTS5 virtual table for titles and subjects)
-- ==============================================================================

-- Full-text search on titles
CREATE VIRTUAL TABLE titles_fts USING fts5(
    mms_id UNINDEXED,
    title_type UNINDEXED,
    value,
    content=titles,
    content_rowid=id
);

-- Triggers to keep FTS table in sync
CREATE TRIGGER titles_fts_insert AFTER INSERT ON titles BEGIN
    INSERT INTO titles_fts(rowid, mms_id, title_type, value)
    SELECT NEW.id, r.mms_id, NEW.title_type, NEW.value
    FROM records r WHERE r.id = NEW.record_id;
END;

CREATE TRIGGER titles_fts_delete AFTER DELETE ON titles BEGIN
    DELETE FROM titles_fts WHERE rowid = OLD.id;
END;

CREATE TRIGGER titles_fts_update AFTER UPDATE ON titles BEGIN
    DELETE FROM titles_fts WHERE rowid = OLD.id;
    INSERT INTO titles_fts(rowid, mms_id, title_type, value)
    SELECT NEW.id, r.mms_id, NEW.title_type, NEW.value
    FROM records r WHERE r.id = NEW.record_id;
END;

-- Full-text search on subjects
CREATE VIRTUAL TABLE subjects_fts USING fts5(
    mms_id UNINDEXED,
    value,
    content=subjects,
    content_rowid=id
);

-- Triggers for subjects FTS
CREATE TRIGGER subjects_fts_insert AFTER INSERT ON subjects BEGIN
    INSERT INTO subjects_fts(rowid, mms_id, value)
    SELECT NEW.id, r.mms_id, NEW.value
    FROM records r WHERE r.id = NEW.record_id;
END;

CREATE TRIGGER subjects_fts_delete AFTER DELETE ON subjects BEGIN
    DELETE FROM subjects_fts WHERE rowid = OLD.id;
END;

CREATE TRIGGER subjects_fts_update AFTER UPDATE ON subjects BEGIN
    DELETE FROM subjects_fts WHERE rowid = OLD.id;
    INSERT INTO subjects_fts(rowid, mms_id, value)
    SELECT NEW.id, r.mms_id, NEW.value
    FROM records r WHERE r.id = NEW.record_id;
END;

-- ==============================================================================
-- AUTHORITY ENRICHMENT TABLE (Wikidata/VIAF/NLI)
-- ==============================================================================

-- Authority enrichment data from external sources
CREATE TABLE authority_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_uri TEXT NOT NULL UNIQUE,  -- Original authority URI from $0
    nli_id TEXT,  -- NLI authority ID (extracted from URI)
    wikidata_id TEXT,  -- Wikidata QID (e.g., Q123456)
    viaf_id TEXT,  -- VIAF ID
    isni_id TEXT,  -- ISNI
    loc_id TEXT,  -- Library of Congress ID
    label TEXT,  -- Display label from Wikidata
    description TEXT,  -- Description from Wikidata
    person_info TEXT,  -- JSON: birth/death years, occupations, nationality
    place_info TEXT,  -- JSON: coordinates, country
    image_url TEXT,  -- Wikidata image URL
    wikipedia_url TEXT,  -- Wikipedia article URL
    source TEXT NOT NULL,  -- Primary source: 'wikidata', 'viaf', 'nli'
    confidence REAL,  -- Confidence score (0-1)
    fetched_at TEXT NOT NULL,  -- ISO 8601 timestamp when fetched
    expires_at TEXT NOT NULL  -- ISO 8601 timestamp when cache expires
);

-- Indexes for efficient lookups
CREATE INDEX idx_enrichment_authority_uri ON authority_enrichment(authority_uri);
CREATE INDEX idx_enrichment_wikidata ON authority_enrichment(wikidata_id);
CREATE INDEX idx_enrichment_nli ON authority_enrichment(nli_id);
CREATE INDEX idx_enrichment_viaf ON authority_enrichment(viaf_id);
