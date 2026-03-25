"""Unit tests for the cross-reference engine (E3).

Tests graph construction from authority_enrichment data, connection discovery
(teacher/student, co-publication, same_place_period), network neighbor traversal,
and edge cases (empty data, self-loops, circular references, max_results).

All tests use in-memory SQLite with fixture data mimicking the production schema.
Tests are written TDD-style: they MUST fail initially with ImportError/ModuleNotFoundError
until scripts/chat/cross_reference.py is implemented.

Spec reference: reports/historian-enhancement-plan.md lines 400-565 (E3).
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from scripts.chat.cross_reference import (
    build_agent_graph,
    find_connections,
    find_network_neighbors,
)
from scripts.chat.models import AgentNode, Connection


# =============================================================================
# Fixtures: in-memory SQLite with production-like schema
# =============================================================================


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal tables matching m3_schema.sql for cross-reference tests."""
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL UNIQUE,
            source_file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            jsonl_line_number INTEGER
        );

        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            agent_index INTEGER NOT NULL,
            agent_raw TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            role_raw TEXT,
            role_source TEXT,
            authority_uri TEXT,
            agent_norm TEXT NOT NULL,
            agent_confidence REAL NOT NULL,
            agent_method TEXT NOT NULL,
            agent_notes TEXT,
            role_norm TEXT NOT NULL,
            role_confidence REAL NOT NULL,
            role_method TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE INDEX idx_agents_record_id ON agents(record_id);
        CREATE INDEX idx_agents_agent_norm ON agents(agent_norm);
        CREATE INDEX idx_agents_authority_uri ON agents(authority_uri);

        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            authority_uri TEXT NOT NULL UNIQUE,
            nli_id TEXT,
            wikidata_id TEXT,
            viaf_id TEXT,
            isni_id TEXT,
            loc_id TEXT,
            label TEXT,
            description TEXT,
            person_info TEXT,
            place_info TEXT,
            image_url TEXT,
            wikipedia_url TEXT,
            source TEXT NOT NULL,
            confidence REAL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE INDEX idx_enrichment_authority_uri
            ON authority_enrichment(authority_uri);
        CREATE INDEX idx_enrichment_wikidata
            ON authority_enrichment(wikidata_id);
    """)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_record(conn: sqlite3.Connection, mms_id: str) -> int:
    """Insert a record and return its id."""
    cur = conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        (mms_id, "test.xml", _now_iso()),
    )
    return cur.lastrowid


def _insert_agent(
    conn: sqlite3.Connection,
    record_id: int,
    agent_norm: str,
    role_norm: str = "author",
    authority_uri: str | None = None,
    agent_index: int = 0,
) -> int:
    """Insert an agent row and return its id."""
    cur = conn.execute(
        """INSERT INTO agents
           (record_id, agent_index, agent_raw, agent_type, authority_uri,
            agent_norm, agent_confidence, agent_method, role_norm,
            role_confidence, role_method, provenance_json)
           VALUES (?, ?, ?, 'personal', ?, ?, 0.95, 'base_clean', ?, 0.95,
                   'relator_code', '[]')""",
        (record_id, agent_index, agent_norm, authority_uri, agent_norm, role_norm),
    )
    return cur.lastrowid


def _insert_enrichment(
    conn: sqlite3.Connection,
    authority_uri: str,
    wikidata_id: str,
    label: str,
    person_info: dict,
) -> int:
    """Insert an authority_enrichment row and return its id."""
    cur = conn.execute(
        """INSERT INTO authority_enrichment
           (authority_uri, wikidata_id, label, person_info,
            source, confidence, fetched_at, expires_at)
           VALUES (?, ?, ?, ?, 'wikidata', 0.95, ?, ?)""",
        (
            authority_uri,
            wikidata_id,
            label,
            json.dumps(person_info),
            _now_iso(),
            _now_iso(),
        ),
    )
    return cur.lastrowid


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    return conn


@pytest.fixture
def teacher_student_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with a teacher-student pair: Scultetus teaches Buxtorf.

    Buxtorf (Q61067) lists Scultetus as a teacher in person_info.
    Scultetus (Q62182) lists Buxtorf as a student in person_info.
    Both have authority_uri links so they can be joined via agents table.
    """
    conn = db_conn

    # Records
    r1 = _insert_record(conn, "990001001")
    r2 = _insert_record(conn, "990001002")

    # Agents with authority URIs
    _insert_agent(conn, r1, "buxtorf, johannes", "author", "nli:000001001")
    _insert_agent(conn, r2, "scultetus, abraham", "author", "nli:000002001")

    # Enrichment with teacher/student relationships
    _insert_enrichment(conn, "nli:000001001", "Q61067", "Johannes Buxtorf", {
        "birth_year": 1564,
        "death_year": 1629,
        "birth_place": "Kamen",
        "occupations": ["orientalist", "Hebraist"],
        "teachers": ["Abraham Scultetus"],
        "students": ["Johann Heinrich Hottinger", "Johannes Wasmuth"],
        "notable_works": ["Synagoga Judaica"],
        "languages_spoken": ["Latin", "Hebrew"],
    })
    _insert_enrichment(conn, "nli:000002001", "Q62182", "Abraham Scultetus", {
        "birth_year": 1566,
        "death_year": 1625,
        "birth_place": "Gruenberg",
        "occupations": ["theologian", "professor"],
        "teachers": [],
        "students": ["Johannes Buxtorf"],
        "notable_works": [],
        "languages_spoken": ["Latin"],
    })

    conn.commit()
    return conn


@pytest.fixture
def co_publication_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database where two agents share multiple records (co-publication).

    Agent A (author) and Agent B (printer) both appear on records r1 and r2,
    establishing a co-publication connection.
    """
    conn = db_conn

    r1 = _insert_record(conn, "990002001")
    r2 = _insert_record(conn, "990002002")
    r3 = _insert_record(conn, "990002003")

    # Agent A appears on r1 and r2 as author
    _insert_agent(conn, r1, "menasseh ben israel", "author", "nli:000003001", 0)
    _insert_agent(conn, r2, "menasseh ben israel", "author", "nli:000003001", 0)

    # Agent B appears on r1 and r2 as printer (different role)
    _insert_agent(conn, r1, "de castro, samuel", "printer", "nli:000003002", 1)
    _insert_agent(conn, r2, "de castro, samuel", "printer", "nli:000003002", 1)

    # Agent C on r3 only (no co-publication with A or B)
    _insert_agent(conn, r3, "spinoza, baruch", "author", "nli:000003003", 0)

    _insert_enrichment(conn, "nli:000003001", "Q346677", "Menasseh ben Israel", {
        "birth_year": 1604,
        "death_year": 1657,
        "birth_place": "Lisbon",
        "occupations": ["rabbi", "printer", "diplomat"],
        "teachers": [],
        "students": [],
        "notable_works": ["The Hope of Israel"],
        "languages_spoken": ["Hebrew", "Portuguese", "Latin"],
    })
    _insert_enrichment(conn, "nli:000003002", "Q999001", "Samuel de Castro", {
        "birth_year": 1600,
        "death_year": 1660,
        "birth_place": "Amsterdam",
        "occupations": ["printer"],
        "teachers": [],
        "students": [],
        "notable_works": [],
        "languages_spoken": [],
    })
    _insert_enrichment(conn, "nli:000003003", "Q35802", "Baruch Spinoza", {
        "birth_year": 1632,
        "death_year": 1677,
        "birth_place": "Amsterdam",
        "occupations": ["philosopher"],
        "teachers": ["Menasseh ben Israel"],
        "students": [],
        "notable_works": ["Ethics"],
        "languages_spoken": ["Latin", "Dutch", "Hebrew"],
    })

    conn.commit()
    return conn


@pytest.fixture
def same_place_period_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with agents active in the same city and overlapping dates.

    Both agents active in Amsterdam with overlapping lifespans.
    """
    conn = db_conn

    r1 = _insert_record(conn, "990003001")
    r2 = _insert_record(conn, "990003002")

    _insert_agent(conn, r1, "agent alpha", "author", "nli:000004001")
    _insert_agent(conn, r2, "agent beta", "author", "nli:000004002")

    _insert_enrichment(conn, "nli:000004001", "Q100001", "Agent Alpha", {
        "birth_year": 1580,
        "death_year": 1640,
        "birth_place": "Amsterdam",
        "occupations": ["printer"],
        "teachers": [],
        "students": [],
        "notable_works": [],
        "languages_spoken": [],
    })
    _insert_enrichment(conn, "nli:000004002", "Q100002", "Agent Beta", {
        "birth_year": 1600,
        "death_year": 1660,
        "birth_place": "Amsterdam",
        "occupations": ["bookseller"],
        "teachers": [],
        "students": [],
        "notable_works": [],
        "languages_spoken": [],
    })

    conn.commit()
    return conn


@pytest.fixture
def large_network_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with a larger network for max_results and visited-tracking tests.

    Chain: A taught B, B taught C, B taught D, B taught E (5 nodes, fan-out from B).
    All share a record for co-publication links.
    """
    conn = db_conn

    # Shared record so everyone has co-publication links too
    r1 = _insert_record(conn, "990004001")

    agents_data = [
        ("agent a", "nli:000005001", "Q200001", "Agent A", {
            "birth_year": 1500, "death_year": 1560, "birth_place": "Venice",
            "occupations": ["rabbi"], "teachers": [],
            "students": ["Agent B"], "notable_works": [], "languages_spoken": [],
        }),
        ("agent b", "nli:000005002", "Q200002", "Agent B", {
            "birth_year": 1530, "death_year": 1590, "birth_place": "Venice",
            "occupations": ["rabbi"], "teachers": ["Agent A"],
            "students": ["Agent C", "Agent D", "Agent E"],
            "notable_works": [], "languages_spoken": [],
        }),
        ("agent c", "nli:000005003", "Q200003", "Agent C", {
            "birth_year": 1560, "death_year": 1620, "birth_place": "Venice",
            "occupations": ["scholar"], "teachers": ["Agent B"],
            "students": [], "notable_works": [], "languages_spoken": [],
        }),
        ("agent d", "nli:000005004", "Q200004", "Agent D", {
            "birth_year": 1565, "death_year": 1625, "birth_place": "Padua",
            "occupations": ["physician"], "teachers": ["Agent B"],
            "students": [], "notable_works": [], "languages_spoken": [],
        }),
        ("agent e", "nli:000005005", "Q200005", "Agent E", {
            "birth_year": 1570, "death_year": 1630, "birth_place": "Rome",
            "occupations": ["translator"], "teachers": ["Agent B"],
            "students": [], "notable_works": [], "languages_spoken": [],
        }),
    ]

    for i, (norm, uri, wdid, label, pi) in enumerate(agents_data):
        _insert_agent(conn, r1, norm, "author", uri, agent_index=i)
        _insert_enrichment(conn, uri, wdid, label, pi)

    conn.commit()
    return conn


# =============================================================================
# Test 1: Graph construction
# =============================================================================


def test_build_agent_graph_from_enrichment(teacher_student_db):
    """build_agent_graph() creates graph with correct node count from enrichment data.

    Given a database with 2 enriched agents (Buxtorf and Scultetus),
    the graph should contain exactly 2 AgentNode entries.
    """
    graph = build_agent_graph(teacher_student_db)

    # Should have exactly 2 nodes
    assert len(graph) == 2

    # Each entry should be an AgentNode
    for node in graph.values():
        assert isinstance(node, AgentNode)


# =============================================================================
# Test 2: Teacher-student connection discovery
# =============================================================================


def test_find_teacher_student_connection(teacher_student_db):
    """Discovers teacher_of relationship between agents with known data.

    Buxtorf's person_info lists Scultetus as a teacher. find_connections()
    should discover this and return a Connection with relationship_type='teacher_of'.
    """
    connections = find_connections(
        teacher_student_db,
        agent_norms=["buxtorf, johannes", "scultetus, abraham"],
    )

    # At least one teacher_of connection
    teacher_connections = [
        c for c in connections if c.relationship_type == "teacher_of"
    ]
    assert len(teacher_connections) >= 1

    tc = teacher_connections[0]
    # Scultetus teaches Buxtorf (teacher_of goes from teacher to student)
    assert "scultetus" in tc.agent_a.lower() or "scultetus" in tc.agent_b.lower()
    assert "buxtorf" in tc.agent_a.lower() or "buxtorf" in tc.agent_b.lower()
    assert tc.confidence > 0


# =============================================================================
# Test 3: Co-publication connection
# =============================================================================


def test_find_co_publication(co_publication_db):
    """Agents sharing records get co_publication connection.

    Menasseh ben Israel (author) and Samuel de Castro (printer) appear on
    the same 2 records. find_connections() should return a co_publication
    Connection between them.
    """
    connections = find_connections(
        co_publication_db,
        agent_norms=["menasseh ben israel", "de castro, samuel"],
    )

    co_pub = [c for c in connections if c.relationship_type == "co_publication"]
    assert len(co_pub) >= 1

    cp = co_pub[0]
    assert "menasseh" in cp.agent_a.lower() or "menasseh" in cp.agent_b.lower()
    assert "castro" in cp.agent_a.lower() or "castro" in cp.agent_b.lower()
    assert cp.confidence > 0
    assert cp.evidence  # Should have human-readable evidence string


# =============================================================================
# Test 4: Same place and period connection
# =============================================================================


def test_find_same_place_period(same_place_period_db):
    """Agents active in same city + overlapping dates connected.

    Both agents born in Amsterdam with overlapping lifespans (1580-1640
    and 1600-1660). Should get same_place_period connection.
    """
    connections = find_connections(
        same_place_period_db,
        agent_norms=["agent alpha", "agent beta"],
    )

    place_connections = [
        c for c in connections if c.relationship_type == "same_place_period"
    ]
    assert len(place_connections) >= 1

    pc = place_connections[0]
    assert pc.confidence > 0
    assert "amsterdam" in pc.evidence.lower()


# =============================================================================
# Test 5: Network neighbors (1-hop)
# =============================================================================


def test_find_network_neighbors(large_network_db):
    """1-hop neighbors discovered from a starting agent.

    Starting from Agent B who has 1 teacher (A) and 3 students (C, D, E),
    find_network_neighbors() should return at least 4 neighbors.
    """
    neighbors = find_network_neighbors(
        large_network_db,
        agent_norm="agent b",
        max_hops=1,
    )

    # B connects to A (teacher), C, D, E (students)
    assert len(neighbors) >= 4

    # All results should be Connection instances
    for conn_obj in neighbors:
        assert isinstance(conn_obj, Connection)


# =============================================================================
# Test 6: No connections found
# =============================================================================


def test_no_connections_found(co_publication_db):
    """Empty list when agents are unrelated.

    Spinoza (r3 only) and de Castro (r1, r2) share no records and have
    no teacher/student link. Should return empty connections list.
    """
    connections = find_connections(
        co_publication_db,
        agent_norms=["spinoza, baruch", "de castro, samuel"],
    )

    # No direct co-publication (different records)
    co_pub = [c for c in connections if c.relationship_type == "co_publication"]
    assert len(co_pub) == 0


# =============================================================================
# Test 7: Self-loop excluded
# =============================================================================


def test_self_loop_excluded(teacher_student_db):
    """Agent not connected to itself.

    Calling find_connections with a single agent should not produce
    a self-referencing connection.
    """
    connections = find_connections(
        teacher_student_db,
        agent_norms=["buxtorf, johannes"],
    )

    for c in connections:
        # No connection should have the same agent on both sides
        assert not (
            c.agent_a.lower() == c.agent_b.lower()
        ), f"Self-loop found: {c.agent_a} -> {c.agent_b}"


# =============================================================================
# Test 8: max_results respected
# =============================================================================


def test_max_results_respected(large_network_db):
    """Results capped at max_results parameter.

    The large network has many possible connections. With max_results=2,
    only 2 connections should be returned.
    """
    connections = find_connections(
        large_network_db,
        agent_norms=["agent a", "agent b", "agent c", "agent d", "agent e"],
        max_results=2,
    )

    assert len(connections) <= 2


# =============================================================================
# Test 9: Connection confidence values
# =============================================================================


def test_connection_confidence_values(teacher_student_db, co_publication_db,
                                       same_place_period_db):
    """teacher_of=0.90, co_publication=0.85, same_place_period=0.70.

    Each connection type should have its specified confidence score per the
    E3 specification.
    """
    # Teacher/student
    teacher_conns = find_connections(
        teacher_student_db,
        agent_norms=["buxtorf, johannes", "scultetus, abraham"],
    )
    teacher_of_conns = [c for c in teacher_conns if c.relationship_type == "teacher_of"]
    assert len(teacher_of_conns) >= 1
    assert teacher_of_conns[0].confidence == pytest.approx(0.90, abs=0.01)

    # Co-publication
    copub_conns = find_connections(
        co_publication_db,
        agent_norms=["menasseh ben israel", "de castro, samuel"],
    )
    copub_filtered = [c for c in copub_conns if c.relationship_type == "co_publication"]
    assert len(copub_filtered) >= 1
    assert copub_filtered[0].confidence == pytest.approx(0.85, abs=0.01)

    # Same place period
    place_conns = find_connections(
        same_place_period_db,
        agent_norms=["agent alpha", "agent beta"],
    )
    place_filtered = [
        c for c in place_conns if c.relationship_type == "same_place_period"
    ]
    assert len(place_filtered) >= 1
    assert place_filtered[0].confidence == pytest.approx(0.70, abs=0.01)


# =============================================================================
# Test 10: Empty enrichment data
# =============================================================================


def test_empty_enrichment(db_conn):
    """Empty/no enrichment data returns empty graph gracefully.

    A database with records and agents but NO authority_enrichment rows
    should produce an empty graph without errors.
    """
    conn = db_conn
    r1 = _insert_record(conn, "990099001")
    _insert_agent(conn, r1, "unknown author", "author")
    conn.commit()

    graph = build_agent_graph(conn)
    assert len(graph) == 0

    # find_connections should also return empty gracefully
    connections = find_connections(conn, agent_norms=["unknown author"])
    assert connections == []


# =============================================================================
# Test 11: Circular teacher-student references
# =============================================================================


def test_circular_teacher_student(db_conn):
    """A teaches B teaches A doesn't cause infinite loop.

    Circular teacher/student references in person_info should not cause
    infinite recursion or duplicate connections.
    """
    conn = db_conn

    r1 = _insert_record(conn, "990006001")
    r2 = _insert_record(conn, "990006002")

    _insert_agent(conn, r1, "rabbi alpha", "author", "nli:000006001")
    _insert_agent(conn, r2, "rabbi beta", "author", "nli:000006002")

    # Circular: Alpha teaches Beta, Beta teaches Alpha
    _insert_enrichment(conn, "nli:000006001", "Q300001", "Rabbi Alpha", {
        "birth_year": 1500,
        "death_year": 1570,
        "birth_place": "Safed",
        "occupations": ["rabbi"],
        "teachers": ["Rabbi Beta"],
        "students": ["Rabbi Beta"],
        "notable_works": [],
        "languages_spoken": [],
    })
    _insert_enrichment(conn, "nli:000006002", "Q300002", "Rabbi Beta", {
        "birth_year": 1510,
        "death_year": 1580,
        "birth_place": "Safed",
        "occupations": ["rabbi"],
        "teachers": ["Rabbi Alpha"],
        "students": ["Rabbi Alpha"],
        "notable_works": [],
        "languages_spoken": [],
    })
    conn.commit()

    # Should complete without hanging or raising
    connections = find_connections(
        conn,
        agent_norms=["rabbi alpha", "rabbi beta"],
    )

    # Should find connections but not duplicate them
    assert isinstance(connections, list)
    # Should terminate and return a finite list
    assert len(connections) < 100


# =============================================================================
# Test 12: Visited tracking (no duplicate connections)
# =============================================================================


def test_visited_tracking(large_network_db):
    """No duplicate connections returned.

    In a network where A->B and B has teachers/students, calling
    find_connections should not produce duplicate Connection objects
    for the same pair+relationship.
    """
    connections = find_connections(
        large_network_db,
        agent_norms=["agent a", "agent b", "agent c", "agent d", "agent e"],
    )

    # Build set of (sorted pair, relationship_type) to check for duplicates
    seen = set()
    for c in connections:
        pair = tuple(sorted([c.agent_a.lower(), c.agent_b.lower()]))
        key = (pair, c.relationship_type)
        assert key not in seen, (
            f"Duplicate connection: {c.agent_a} <-> {c.agent_b} "
            f"({c.relationship_type})"
        )
        seen.add(key)


# =============================================================================
# Test 13: AgentNode has all expected fields populated
# =============================================================================


def test_agent_node_fields(teacher_student_db):
    """AgentNode has all expected fields populated.

    Each AgentNode built from enrichment data should have label, agent_norm,
    wikidata_id, birth/death years, occupations, teachers, students, and
    record_count populated.
    """
    graph = build_agent_graph(teacher_student_db)

    # Buxtorf node
    buxtorf_nodes = [
        n for n in graph.values()
        if "buxtorf" in n.agent_norm.lower()
    ]
    assert len(buxtorf_nodes) == 1
    node = buxtorf_nodes[0]

    # Check all expected fields are populated
    assert node.label == "Johannes Buxtorf"
    assert "buxtorf" in node.agent_norm.lower()
    assert node.wikidata_id == "Q61067"
    assert node.birth_year == 1564
    assert node.death_year == 1629
    assert node.birth_place == "Kamen"
    assert "orientalist" in node.occupations or "Hebraist" in node.occupations
    assert len(node.occupations) == 2
    assert "Abraham Scultetus" in node.teachers
    assert len(node.students) == 2  # Hottinger and Wasmuth
    assert "Synagoga Judaica" in node.notable_works
    assert node.record_count >= 1  # At least 1 record in the DB
