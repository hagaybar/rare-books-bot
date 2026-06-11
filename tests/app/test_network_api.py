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
            primary_role TEXT,
            has_wikipedia INTEGER DEFAULT 0, record_count INTEGER DEFAULT 0,
            connection_count INTEGER DEFAULT 0,
            node_type TEXT DEFAULT 'person', community TEXT
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
            date_start INTEGER, date_label TEXT, place_display TEXT,
            publisher_display TEXT
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT, wikidata_id TEXT,
            wikipedia_url TEXT, viaf_id TEXT, person_info TEXT, label TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, summary_extract TEXT
        );
        CREATE TABLE records (
            id INTEGER PRIMARY KEY, mms_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER, title_type TEXT, value TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT,
            authority_uri TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER, alias_form TEXT,
            alias_form_lower TEXT, alias_type TEXT, script TEXT, language TEXT
        );

        INSERT INTO records VALUES (100, '990001112220304146');
        INSERT INTO titles VALUES (1, 100, 'main', 'A Treatise on Optics');

        INSERT INTO network_agents VALUES
            ('smith, john', 'John Smith', 'amsterdam', 52.37, 4.90,
             1500, 1570, '["author"]', 'author', 1, 5, 10, 'person', 'Kabbalists');
        INSERT INTO network_agents VALUES
            ('jones, mary', 'Mary Jones', 'venice', 45.44, 12.32,
             1480, 1550, '["printer"]', 'printer', 0, 3, 5, 'person', NULL);
        INSERT INTO network_edges VALUES
            ('smith, john', 'jones, mary', 'teacher_student', 0.85,
             'teacher of', 0, 'documented in authority record');
        INSERT INTO agents VALUES (1, 100, 'smith, john', 'uri:smith', 'author');
        INSERT INTO imprints VALUES (1, 100, 'amsterdam', 1550, '1550', 'Amsterdam', 'Elzevir');
        INSERT INTO authority_enrichment VALUES
            (1, 'uri:smith', 'Q111', 'https://en.wikipedia.org/wiki/John_Smith',
             'V123', '{"birth_year":1500}', 'John Smith');
        INSERT INTO wikipedia_cache VALUES (1, 'Q111', 'John Smith was a scholar.');

        -- Cross-script case (issue #30): a Hebrew-normed node whose only Latin
        -- handle lives in agent_aliases, so a Latin query must reach it.
        INSERT INTO network_agents VALUES
            ('משה בן מימון', 'Moshe ben Maimon', 'cordoba', 37.88, -4.78,
             1138, 1204, '["philosopher"]', 'author', 1, 2, 7, 'person', NULL);
        INSERT INTO agents VALUES (2, 100, 'משה בן מימון', 'uri:rambam', 'author');
        INSERT INTO agent_authorities VALUES (2, 'Moses Maimonides', 'moses maimonides', 'uri:rambam');
        INSERT INTO agent_aliases VALUES
            (1, 2, 'משה בן מימון', 'משה בן מימון', 'primary', 'Hebr', 'he'),
            (2, 2, 'Maimonides', 'maimonides', 'cross_script', 'Latn', 'en'),
            (3, 2, 'Rambam', 'rambam', 'variant_spelling', 'Latn', 'en');
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(mock_db):
    """Create test client with mocked DB path and auth token."""
    import app.api.network as network_mod
    from app.api.main import app
    from tests.app.conftest import make_test_token

    original_path = network_mod.DB_PATH
    network_mod.DB_PATH = mock_db
    client = TestClient(app, cookies={"access_token": make_test_token()})
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


def test_category_is_not_a_valid_arc_type(client):
    """Issue #28: category retired from arcs; requesting it is a 400."""
    resp = client.get("/network/map?connection_types=category")
    assert resp.status_code == 400


def test_search_resolves_cross_script_via_alias(client):
    """Issue #30: a Latin query finds a Hebrew-normed node through agent_aliases."""
    resp = client.get("/network/search?q=maimonides")
    assert resp.status_code == 200
    results = resp.json()["results"]
    hit = next((r for r in results if r["agent_norm"] == "משה בן מימון"), None)
    assert hit is not None, "cross-script alias did not resolve the Hebrew node"
    assert hit["matched_alias"] and "maimonides" in hit["matched_alias"].lower()


def test_agent_detail_includes_alt_script_name(client):
    """Issue #30: a Latin-labeled Hebrew node exposes its Hebrew form as name_alt."""
    resp = client.get("/network/agent/משה בן מימון")
    assert resp.status_code == 200
    assert resp.json()["name_alt"] == "משה בן מימון"


def test_agent_detail_no_alt_when_single_script(client):
    """A node with no opposite-script alias reports name_alt=None."""
    resp = client.get("/network/agent/smith, john")
    assert resp.status_code == 200
    assert resp.json()["name_alt"] is None


def test_search_direct_match_reports_no_alias(client):
    """A plain name match carries no matched_alias (nothing to disambiguate)."""
    resp = client.get("/network/search?q=smith")
    results = resp.json()["results"]
    hit = next(r for r in results if r["agent_norm"] == "smith, john")
    assert hit["matched_alias"] is None


def test_map_nodes_and_meta_carry_community(client):
    """Issue #28: nodes expose their community and meta lists the palette order."""
    resp = client.get("/network/map")
    assert resp.status_code == 200
    data = resp.json()
    smith = next(n for n in data["nodes"] if n["agent_norm"] == "smith, john")
    assert smith["community"] == "Kabbalists"
    assert data["meta"]["communities"] == ["Kabbalists"]


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


# --- Network committee Tier 1 (issues #18/#19/#20/#25/#29) ---


def test_agent_detail_includes_works_with_primo_mms_id(client):
    """#18/#19: clicking an agent lists the collection's own books with a
    Primo URL built from the MMS ID (not the internal rowid)."""
    resp = client.get("/network/agent/smith, john")
    assert resp.status_code == 200
    data = resp.json()
    assert data["works"], "agent detail must list the agent's records"
    w = data["works"][0]
    assert w["mms_id"] == "990001112220304146"
    assert w["title"] == "A Treatise on Optics"
    assert "990001112220304146" in w["primo_url"]  # MMS ID, never the rowid (100)
    assert "query=100&" not in w["primo_url"]


def test_map_edges_carry_evidence(client):
    """#20: every edge ships its evidence string so the UI can explain why."""
    resp = client.get("/network/map?connection_types=teacher_student")
    assert resp.status_code == 200
    edges = resp.json()["edges"]
    assert edges and edges[0]["evidence"] == "documented in authority record"


def test_map_nodes_carry_record_count_and_filtered_count(client):
    """#25: node size can reflect catalog presence and the active filter."""
    resp = client.get("/network/map?connection_types=teacher_student")
    nodes = {n["agent_norm"]: n for n in resp.json()["nodes"]}
    assert nodes["smith, john"]["record_count"] == 5
    assert nodes["smith, john"]["filtered_count"] >= 1


def test_place_endpoint_lists_books_printed_there(client):
    """#29: clicking a place shows the collection's imprints from there."""
    resp = client.get("/network/place/amsterdam")
    assert resp.status_code == 200
    works = resp.json()["works"]
    assert any(w["mms_id"] == "990001112220304146" for w in works)
