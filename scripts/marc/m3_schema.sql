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

    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_imprints_record_id ON imprints(record_id);
CREATE INDEX idx_imprints_date_range ON imprints(date_start, date_end);
CREATE INDEX idx_imprints_place_norm ON imprints(place_norm);
CREATE INDEX idx_imprints_publisher_norm ON imprints(publisher_norm);
CREATE INDEX idx_imprints_date_confidence ON imprints(date_confidence);

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
    parts TEXT NOT NULL,  -- JSON object of structured parts
    source TEXT NOT NULL,  -- JSON array of MARC sources with occurrence
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_subjects_record_id ON subjects(record_id);
CREATE INDEX idx_subjects_value ON subjects(value);
CREATE INDEX idx_subjects_tag ON subjects(source_tag);
CREATE INDEX idx_subjects_scheme ON subjects(scheme);

-- ==============================================================================
-- AGENT TABLES (Authors, Contributors, etc.)
-- ==============================================================================

-- Agents table
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    value TEXT NOT NULL,  -- Display name
    role TEXT NOT NULL,  -- 'author', 'contributor', etc.
    relator_code TEXT,  -- MARC relator code (e.g., 'aut', 'pbl')
    source TEXT NOT NULL,  -- JSON array of MARC sources with occurrence
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);

CREATE INDEX idx_agents_record_id ON agents(record_id);
CREATE INDEX idx_agents_value ON agents(value);
CREATE INDEX idx_agents_role ON agents(role);

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
