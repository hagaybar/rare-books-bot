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
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT
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
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.');
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
