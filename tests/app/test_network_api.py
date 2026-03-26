"""Tests for network API endpoints."""
import json
import sqlite3
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db(tmp_path):
    """Create a temporary DB with network tables for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE network_agents (
            agent_norm TEXT PRIMARY KEY, display_name TEXT NOT NULL,
            place_norm TEXT, lat REAL, lon REAL,
            birth_year INTEGER, death_year INTEGER, occupations TEXT,
            has_wikipedia INTEGER DEFAULT 0, record_count INTEGER DEFAULT 0,
            connection_count INTEGER DEFAULT 0
        );
        CREATE TABLE network_edges (
            source_agent_norm TEXT, target_agent_norm TEXT,
            connection_type TEXT, confidence REAL, relationship TEXT,
            bidirectional INTEGER DEFAULT 0, evidence TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, connection_type)
        );
        CREATE INDEX idx_network_edges_source ON network_edges(source_agent_norm);
        CREATE INDEX idx_network_edges_target ON network_edges(target_agent_norm);
        CREATE INDEX idx_network_edges_type ON network_edges(connection_type);
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_norm TEXT,
            authority_uri TEXT, role_norm TEXT
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, place_norm TEXT,
            date_start INTEGER
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT, wikidata_id TEXT,
            wikipedia_url TEXT, viaf_id TEXT, person_info TEXT, label TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT
        );

        INSERT INTO network_agents VALUES
            ('smith, john', 'John Smith', 'amsterdam', 52.37, 4.90,
             1500, 1570, '["author"]', 1, 5, 10);
        INSERT INTO network_agents VALUES
            ('jones, mary', 'Mary Jones', 'venice', 45.44, 12.32,
             1480, 1550, '["printer"]', 0, 3, 5);
        INSERT INTO network_edges VALUES
            ('smith, john', 'jones, mary', 'teacher_student', 0.85,
             'teacher of', 0, NULL);
        INSERT INTO agents VALUES (1, 100, 'smith, john', 'uri:smith', 'author');
        INSERT INTO imprints VALUES (1, 100, 'amsterdam', 1550);
        INSERT INTO authority_enrichment VALUES
            (1, 'uri:smith', 'Q111', 'https://en.wikipedia.org/wiki/John_Smith',
             'V123', '{"birth_year":1500}', 'John Smith');
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.');
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(mock_db):
    """Create test client with mocked DB path."""
    import app.api.network as network_mod
    from app.api.main import app

    original_path = network_mod.DB_PATH
    network_mod.DB_PATH = mock_db
    client = TestClient(app)
    yield client
    network_mod.DB_PATH = original_path


def test_get_map_default(client):
    resp = client.get("/network/map")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
    assert "meta" in data
    assert len(data["nodes"]) <= 150


def test_get_map_with_types(client):
    resp = client.get("/network/map?connection_types=teacher_student")
    assert resp.status_code == 200
    data = resp.json()
    for edge in data["edges"]:
        assert edge["type"] == "teacher_student"


def test_get_map_invalid_type(client):
    resp = client.get("/network/map?connection_types=invalid_type")
    assert resp.status_code == 400


def test_get_agent_detail(client):
    resp = client.get("/network/agent/smith, john")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_norm"] == "smith, john"
    assert data["display_name"] == "John Smith"
    assert data["wikipedia_summary"] == "John Smith was a scholar."
    assert len(data["connections"]) >= 1
    assert "wikidata" in data["external_links"]


def test_get_agent_not_found(client):
    resp = client.get("/network/agent/nonexistent, agent")
    assert resp.status_code == 404
