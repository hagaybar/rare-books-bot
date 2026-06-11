"""Tests for network table build script."""
import json
import sqlite3
import pytest
from scripts.network.build_network_tables import (
    title_case_agent_norm,
    resolve_display_name,
    build_network_edges,
    build_network_agents,
)


@pytest.fixture
def db():
    """In-memory SQLite with minimal schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_norm TEXT,
            agent_raw TEXT, authority_uri TEXT, role_norm TEXT
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, place_norm TEXT,
            date_start INTEGER
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE, label TEXT,
            person_info TEXT, wikidata_id TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER, alias_form_lower TEXT
        );
        CREATE TABLE wikipedia_connections (
            id INTEGER PRIMARY KEY, source_agent_norm TEXT, target_agent_norm TEXT,
            source_type TEXT, confidence REAL, relationship TEXT,
            bidirectional INTEGER DEFAULT 0, evidence TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT,
            wikipedia_title TEXT
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER, title_type TEXT, value TEXT
        );
    """)

    # Insert test data
    conn.executescript("""
        INSERT INTO agents VALUES (1, 100, 'smith, john', 'John Smith', 'uri:smith', 'author');
        INSERT INTO agents VALUES (2, 100, 'jones, mary', 'Mary Jones', 'uri:jones', 'printer');
        INSERT INTO agents VALUES (3, 101, 'smith, john', 'John Smith', 'uri:smith', 'author');
        INSERT INTO agents VALUES (4, 101, 'jones, mary', 'Mary Jones', 'uri:jones', 'printer');
        INSERT INTO agents VALUES (5, 102, 'doe, jane', 'Jane Doe', 'uri:doe', 'author');

        INSERT INTO imprints VALUES (1, 100, 'amsterdam', 1550);
        INSERT INTO imprints VALUES (2, 101, 'amsterdam', 1560);
        INSERT INTO imprints VALUES (3, 102, 'venice', 1570);

        INSERT INTO authority_enrichment VALUES
            (1, 'uri:smith', 'John Smith', '{"birth_year":1500,"death_year":1570,"occupations":["author"],"teachers":["Jones, Mary"],"students":[]}', 'Q111');
        INSERT INTO authority_enrichment VALUES
            (2, 'uri:jones', 'Mary Jones', '{"birth_year":1480,"death_year":1550,"occupations":["printer"],"teachers":[],"students":[]}', 'Q222');

        INSERT INTO wikipedia_connections VALUES
            (1, 'smith, john', 'doe, jane', 'wikilink', 0.75, NULL, 0, 'linked');
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.', 'John Smith');
    """)
    yield conn
    conn.close()


def test_title_case_agent_norm():
    assert title_case_agent_norm("maimonides, moses") == "Maimonides, Moses"
    assert title_case_agent_norm("smith, john") == "Smith, John"


def test_resolve_display_name_fallback(db):
    # No authority match, has enrichment label
    name = resolve_display_name(db, "smith, john")
    assert name == "John Smith"


def test_resolve_display_name_title_case(db):
    # No authority, no enrichment
    name = resolve_display_name(db, "unknown, agent")
    assert name == "Unknown, Agent"


def test_build_network_edges(db):
    count = build_network_edges(db)
    assert count >= 1  # At least the wikipedia_connection
    # Check wikilink was imported
    row = db.execute(
        "SELECT * FROM network_edges WHERE connection_type='wikilink'"
    ).fetchone()
    assert row is not None
    # Check co-publication (smith+jones share 2 records)
    copub = db.execute(
        "SELECT * FROM network_edges WHERE connection_type='co_publication'"
    ).fetchall()
    assert len(copub) >= 1


def test_build_network_agents(db):
    geocodes = {
        "amsterdam": {"lat": 52.37, "lon": 4.90, "display_name": "Amsterdam"},
        "venice": {"lat": 45.44, "lon": 12.32, "display_name": "Venice"},
    }
    build_network_edges(db)
    count = build_network_agents(db, geocodes)
    assert count >= 2  # smith and jones at least

    # Check smith is in amsterdam (2 imprints there)
    row = db.execute(
        "SELECT place_norm, lat, has_wikipedia FROM network_agents WHERE agent_norm='smith, john'"
    ).fetchone()
    assert row[0] == "amsterdam"
    assert row[1] == pytest.approx(52.37)
    assert row[2] == 1  # has wikipedia cache entry


def test_same_record_edges_are_role_typed_and_evidenced(db):
    """Issue #26: agents on the same record get an evidenced, role-typed edge."""
    from scripts.network.build_network_tables import build_same_record_edges
    conn = db
    conn.row_factory = sqlite3.Row
    # records/titles + a network_agents table so the join can fire
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, mms_id TEXT);
        CREATE TABLE IF NOT EXISTS network_agents (agent_norm TEXT PRIMARY KEY, display_name TEXT);
        CREATE TABLE IF NOT EXISTS network_edges (
            source_agent_norm TEXT, target_agent_norm TEXT, connection_type TEXT,
            confidence REAL, relationship TEXT, bidirectional INTEGER DEFAULT 0, evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type));
        INSERT INTO records VALUES (200, '990077788890104146');
        INSERT INTO titles VALUES (50, 200, 'main', 'De Revolutionibus');
        INSERT INTO agents VALUES (90, 200, 'copernicus, nicolaus', 'C', 'uri:c', 'author');
        INSERT INTO agents VALUES (91, 200, 'rheticus, georg', 'R', 'uri:r', 'editor');
        INSERT INTO network_agents VALUES ('copernicus, nicolaus', 'Nicolaus Copernicus');
        INSERT INTO network_agents VALUES ('rheticus, georg', 'Georg Rheticus');
    """)
    added = build_same_record_edges(conn)
    assert added == 1
    e = conn.execute("SELECT * FROM network_edges WHERE connection_type='same_record'").fetchone()
    assert e["relationship"] == "edited"
    assert "990077788890104146" in e["evidence"]
    assert "De Revolutionibus" in e["evidence"]


def test_same_record_skips_non_network_agents(db):
    """An agent without a network node never produces a rendered edge."""
    from scripts.network.build_network_tables import build_same_record_edges
    conn = db
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, mms_id TEXT);
        CREATE TABLE IF NOT EXISTS network_agents (agent_norm TEXT PRIMARY KEY, display_name TEXT);
        CREATE TABLE IF NOT EXISTS network_edges (
            source_agent_norm TEXT, target_agent_norm TEXT, connection_type TEXT,
            confidence REAL, relationship TEXT, bidirectional INTEGER DEFAULT 0, evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type));
        INSERT INTO records VALUES (201, '990000000000000001');
        INSERT INTO agents VALUES (92, 201, 'in_network, a', 'A', 'u:a', 'author');
        INSERT INTO agents VALUES (93, 201, 'not_in_network, b', 'B', 'u:b', 'author');
        INSERT INTO network_agents VALUES ('in_network, a', 'A');
    """)
    assert build_same_record_edges(conn) == 0


def test_publisher_nodes_and_printed_by(db):
    """Issue #27: printing houses become nodes; authors link via printed_by."""
    from scripts.network.build_network_tables import (
        build_publisher_nodes, build_printed_by_edges, PUBLISHER_PREFIX,
    )
    conn = db
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, mms_id TEXT);
        CREATE TABLE IF NOT EXISTS network_agents (
            agent_norm TEXT PRIMARY KEY, display_name TEXT, place_norm TEXT,
            lat REAL, lon REAL, birth_year INTEGER, death_year INTEGER,
            occupations TEXT, primary_role TEXT, has_wikipedia INTEGER DEFAULT 0,
            record_count INTEGER DEFAULT 0, connection_count INTEGER DEFAULT 0,
            node_type TEXT DEFAULT 'person');
        CREATE TABLE IF NOT EXISTS network_edges (
            source_agent_norm TEXT, target_agent_norm TEXT, connection_type TEXT,
            confidence REAL, relationship TEXT, bidirectional INTEGER DEFAULT 0, evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type));
        CREATE TABLE publisher_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT,
            type TEXT, date_start INTEGER, date_end INTEGER, location TEXT);
        CREATE TABLE publisher_variants (
            id INTEGER PRIMARY KEY, authority_id INTEGER, variant_form_lower TEXT);

        ALTER TABLE imprints ADD COLUMN publisher_norm TEXT;
        INSERT INTO publisher_authorities VALUES
            (1, 'Daniel Bomberg, Venice', 'daniel bomberg, venice', 'printing_house', 1516, 1549, 'Venice, Italy');
        INSERT INTO records VALUES (300, '990012345678900146');
        INSERT INTO imprints VALUES (10, 300, 'venice', 1520, 'daniel bomberg, venice');
        INSERT INTO agents VALUES (90, 300, 'pirke, avot', 'P', 'u:p', 'author');
        INSERT INTO network_agents (agent_norm, display_name, node_type) VALUES ('pirke, avot', 'Pirke Avot author', 'person');
    """)

    geocodes = {"venice": {"lat": 45.44, "lon": 12.32, "display_name": "Venice"}}
    n = build_publisher_nodes(conn, geocodes)
    assert n == 1
    pub = conn.execute("SELECT * FROM network_agents WHERE node_type='publisher'").fetchone()
    assert pub["agent_norm"] == PUBLISHER_PREFIX + "daniel bomberg, venice"
    assert pub["display_name"] == "Daniel Bomberg, Venice"
    assert pub["record_count"] == 1
    assert pub["lat"] == 45.44

    e = build_printed_by_edges(conn)
    assert e == 1
    edge = conn.execute("SELECT * FROM network_edges WHERE connection_type='printed_by'").fetchone()
    assert edge["source_agent_norm"] == "pirke, avot"
    assert edge["target_agent_norm"] == PUBLISHER_PREFIX + "daniel bomberg, venice"
    assert "990012345678900146" in edge["evidence"]
