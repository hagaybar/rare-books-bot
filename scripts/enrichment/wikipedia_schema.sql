CREATE TABLE IF NOT EXISTS wikipedia_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wikidata_id TEXT NOT NULL,
    wikipedia_title TEXT,
    summary_extract TEXT,
    categories TEXT,
    see_also_titles TEXT,
    article_wikilinks TEXT,
    sections_json TEXT,
    name_variants TEXT,
    page_id INTEGER,
    revision_id INTEGER,
    language TEXT DEFAULT 'en',
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    UNIQUE(wikidata_id, language)
);
CREATE INDEX IF NOT EXISTS idx_wiki_wikidata ON wikipedia_cache(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_wiki_title ON wikipedia_cache(wikipedia_title, language);

CREATE TABLE IF NOT EXISTS wikipedia_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_agent_norm TEXT NOT NULL,
    target_agent_norm TEXT NOT NULL,
    source_wikidata_id TEXT,
    target_wikidata_id TEXT,
    relationship TEXT,
    tags TEXT,
    confidence REAL NOT NULL,
    source_type TEXT NOT NULL,
    evidence TEXT,
    bidirectional INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(source_agent_norm, target_agent_norm, source_type)
);
CREATE INDEX IF NOT EXISTS idx_wconn_source ON wikipedia_connections(source_agent_norm);
CREATE INDEX IF NOT EXISTS idx_wconn_target ON wikipedia_connections(target_agent_norm);
