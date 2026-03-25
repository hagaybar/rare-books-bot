"""Integration tests for E3 cross-reference engine and enhanced comparison.

Tests end-to-end flows using in-memory SQLite fixtures with production-like
data, verifying network discovery, connection types, comparison facets,
graceful degradation, and performance.

Spec reference: reports/historian-enhancement-plan.md lines 519-534 (E3 phase 6).
"""

import json
import sqlite3
import time
from datetime import datetime, timezone

import pytest

from scripts.chat.cross_reference import (
    find_connections,
    find_network_neighbors,
)
from scripts.chat.models import Connection


# =============================================================================
# Fixtures: in-memory SQLite with production-like schema
# =============================================================================


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal tables matching m3_schema.sql for integration tests."""
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

        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            imprint_index INTEGER NOT NULL DEFAULT 0,
            place_raw TEXT,
            place_norm TEXT,
            place_confidence REAL,
            place_method TEXT,
            publisher_raw TEXT,
            publisher_norm TEXT,
            publisher_confidence REAL,
            publisher_method TEXT,
            date_raw TEXT,
            date_start INTEGER,
            date_end INTEGER,
            date_confidence REAL,
            date_method TEXT,
            country_code TEXT,
            country_name TEXT,
            provenance_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE INDEX idx_imprints_record_id ON imprints(record_id);
        CREATE INDEX idx_imprints_place_norm ON imprints(place_norm);

        CREATE TABLE languages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE INDEX idx_languages_record_id ON languages(record_id);

        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            tag TEXT,
            value TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE INDEX idx_subjects_record_id ON subjects(record_id);
    """)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_record(conn: sqlite3.Connection, mms_id: str) -> int:
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


def _insert_imprint(
    conn: sqlite3.Connection,
    record_id: int,
    place_norm: str,
    date_start: int,
    publisher_norm: str = "",
    country_name: str = "",
) -> int:
    cur = conn.execute(
        """INSERT INTO imprints
           (record_id, imprint_index, place_raw, place_norm, place_confidence,
            place_method, publisher_norm, date_start, country_name, provenance_json)
           VALUES (?, 0, ?, ?, 0.95, 'place_alias_map', ?, ?, ?, '[]')""",
        (record_id, place_norm, place_norm, publisher_norm, date_start, country_name),
    )
    return cur.lastrowid


def _insert_language(conn: sqlite3.Connection, record_id: int, code: str) -> int:
    cur = conn.execute(
        "INSERT INTO languages (record_id, code) VALUES (?, ?)",
        (record_id, code),
    )
    return cur.lastrowid


def _insert_subject(conn: sqlite3.Connection, record_id: int, value: str) -> int:
    cur = conn.execute(
        "INSERT INTO subjects (record_id, tag, value, source) VALUES (?, '650', ?, 'lcsh')",
        (record_id, value),
    )
    return cur.lastrowid


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the schema."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    return conn


@pytest.fixture
def buxtorf_network_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with Buxtorf and his teacher/student chain.

    Buxtorf (Q61067): teacher of Cocceius
    Cocceius (Q12345): student of Buxtorf, teacher of Witsius
    Witsius (Q23456): student of Cocceius
    """
    conn = db_conn

    r1 = _insert_record(conn, "990001001")
    r2 = _insert_record(conn, "990001002")
    r3 = _insert_record(conn, "990001003")

    _insert_agent(conn, r1, "buxtorf, johannes", "author", "nli:000001001")
    _insert_agent(conn, r2, "cocceius, johannes", "author", "nli:000002001")
    _insert_agent(conn, r3, "witsius, herman", "author", "nli:000003001")

    _insert_enrichment(conn, "nli:000001001", "Q61067", "Johannes Buxtorf", {
        "birth_year": 1564,
        "death_year": 1629,
        "birth_place": "Basel",
        "occupations": ["orientalist", "Hebraist"],
        "teachers": [],
        "students": ["Johannes Cocceius"],
    })

    _insert_enrichment(conn, "nli:000002001", "Q12345", "Johannes Cocceius", {
        "birth_year": 1603,
        "death_year": 1669,
        "birth_place": "Bremen",
        "occupations": ["theologian"],
        "teachers": ["Johannes Buxtorf"],
        "students": ["Herman Witsius"],
    })

    _insert_enrichment(conn, "nli:000003001", "Q23456", "Herman Witsius", {
        "birth_year": 1636,
        "death_year": 1708,
        "birth_place": "Enkhuizen",
        "occupations": ["theologian"],
        "teachers": ["Johannes Cocceius"],
        "students": [],
    })

    conn.commit()
    return conn


@pytest.fixture
def venice_printer_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with Venice printers who share records.

    Bomberg and Manutius both appear on records together (co-publication).
    """
    conn = db_conn

    # Record 1: Bomberg as printer, Manutius as publisher
    r1 = _insert_record(conn, "990010001")
    _insert_agent(conn, r1, "bomberg, daniel", "printer", "nli:000010001", 0)
    _insert_agent(conn, r1, "manutius, aldus", "publisher", "nli:000020001", 1)

    # Record 2: same pair, different record
    r2 = _insert_record(conn, "990010002")
    _insert_agent(conn, r2, "bomberg, daniel", "printer", "nli:000010001", 0)
    _insert_agent(conn, r2, "manutius, aldus", "publisher", "nli:000020001", 1)

    # Record 3: Bomberg alone
    r3 = _insert_record(conn, "990010003")
    _insert_agent(conn, r3, "bomberg, daniel", "printer", "nli:000010001", 0)

    _insert_enrichment(conn, "nli:000010001", "Q101010", "Daniel Bomberg", {
        "birth_year": 1483,
        "death_year": 1549,
        "birth_place": "Antwerp",
        "occupations": ["printer"],
        "teachers": [],
        "students": [],
    })

    _insert_enrichment(conn, "nli:000020001", "Q202020", "Aldus Manutius", {
        "birth_year": 1449,
        "death_year": 1515,
        "birth_place": "Bassiano",
        "occupations": ["printer", "publisher"],
        "teachers": [],
        "students": [],
    })

    conn.commit()
    return conn


@pytest.fixture
def teacher_chain_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with a teacher-student chain: Nahmanides -> Shlomo ben Aderet.

    Nahmanides (Ramban) taught Shlomo ben Aderet (Rashba).
    """
    conn = db_conn

    r1 = _insert_record(conn, "990020001")
    r2 = _insert_record(conn, "990020002")

    _insert_agent(conn, r1, "nahmanides", "author", "nli:000030001")
    _insert_agent(conn, r2, "shlomo ben aderet", "author", "nli:000040001")

    _insert_enrichment(conn, "nli:000030001", "Q334517", "Nahmanides", {
        "birth_year": 1194,
        "death_year": 1270,
        "birth_place": "Girona",
        "occupations": ["rabbi", "philosopher"],
        "teachers": [],
        "students": ["Shlomo ben Aderet"],
    })

    _insert_enrichment(conn, "nli:000040001", "Q335789", "Shlomo ben Aderet", {
        "birth_year": 1235,
        "death_year": 1310,
        "birth_place": "Barcelona",
        "occupations": ["rabbi"],
        "teachers": ["Nahmanides"],
        "students": [],
    })

    conn.commit()
    return conn


@pytest.fixture
def comparison_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with Venice and Amsterdam records for comparison testing.

    Venice: 3 records, Amsterdam: 2 records.
    """
    conn = db_conn

    # Venice records
    r1 = _insert_record(conn, "990001001")
    _insert_imprint(conn, r1, "venice", 1550, "manutius", "Italy")
    _insert_agent(conn, r1, "manutius, aldus")
    _insert_language(conn, r1, "lat")
    _insert_subject(conn, r1, "Theology")

    r2 = _insert_record(conn, "990001002")
    _insert_imprint(conn, r2, "venice", 1560, "manutius", "Italy")
    _insert_agent(conn, r2, "manutius, aldus")
    _insert_language(conn, r2, "lat")
    _insert_subject(conn, r2, "Philosophy")

    r3 = _insert_record(conn, "990001003")
    _insert_imprint(conn, r3, "venice", 1570, "bomberg", "Italy")
    _insert_agent(conn, r3, "bomberg, daniel")
    _insert_language(conn, r3, "heb")
    _insert_subject(conn, r3, "Theology")

    # Amsterdam records
    r4 = _insert_record(conn, "990002001")
    _insert_imprint(conn, r4, "amsterdam", 1640, "menasseh", "Netherlands")
    _insert_agent(conn, r4, "menasseh ben israel")
    _insert_language(conn, r4, "heb")
    _insert_subject(conn, r4, "Theology")

    r5 = _insert_record(conn, "990002002")
    _insert_imprint(conn, r5, "amsterdam", 1650, "elzevir", "Netherlands")
    _insert_agent(conn, r5, "elzevir, louis")
    _insert_language(conn, r5, "lat")
    _insert_subject(conn, r5, "Philosophy")

    conn.commit()
    return conn


# =============================================================================
# Tests
# =============================================================================


class TestCrossReferenceIntegration:
    """End-to-end integration tests for the cross-reference engine."""

    def test_buxtorf_network(self, buxtorf_network_db: sqlite3.Connection):
        """Find network neighbors for Buxtorf discovers Cocceius as student."""
        neighbors = find_network_neighbors(
            buxtorf_network_db, "buxtorf, johannes", max_hops=1,
        )

        assert len(neighbors) >= 1
        labels = [c.agent_b for c in neighbors]
        # Buxtorf's student Cocceius should be discovered
        assert any("Cocceius" in label for label in labels), (
            f"Expected Cocceius in neighbors, got: {labels}"
        )

    def test_venice_printer_connections(
        self, venice_printer_db: sqlite3.Connection
    ):
        """Connections between Venice printers discovered via co-publication."""
        connections = find_connections(
            venice_printer_db,
            ["bomberg, daniel", "manutius, aldus"],
        )

        assert len(connections) >= 1
        co_pub = [c for c in connections if c.relationship_type == "co_publication"]
        assert len(co_pub) >= 1, (
            f"Expected co_publication connections, got types: "
            f"{[c.relationship_type for c in connections]}"
        )
        # Evidence should mention the shared records
        assert any("2 records" in c.evidence for c in co_pub), (
            f"Expected evidence mentioning shared records, got: "
            f"{[c.evidence for c in co_pub]}"
        )

    def test_teacher_student_chain(
        self, teacher_chain_db: sqlite3.Connection
    ):
        """Teacher-student chain: Nahmanides -> Shlomo ben Aderet discovered."""
        connections = find_connections(
            teacher_chain_db,
            ["nahmanides", "shlomo ben aderet"],
        )

        assert len(connections) >= 1
        teacher_conns = [
            c for c in connections if c.relationship_type == "teacher_of"
        ]
        assert len(teacher_conns) >= 1, (
            f"Expected teacher_of connection, got: "
            f"{[c.relationship_type for c in connections]}"
        )

        # Verify directionality: Nahmanides is teacher of Shlomo ben Aderet
        conn = teacher_conns[0]
        assert "Nahmanides" in conn.agent_a
        assert "Shlomo ben Aderet" in conn.agent_b

    def test_venice_amsterdam_comparison(
        self, comparison_db: sqlite3.Connection, tmp_path
    ):
        """Enhanced comparison between Venice and Amsterdam produces facets."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        record_ids = [
            "990001001", "990001002", "990001003", "990002001", "990002002",
        ]
        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        assert result.facets.counts["venice"] == 3
        assert result.facets.counts["amsterdam"] == 2

        # Date ranges populated
        assert result.facets.date_ranges["venice"][0] == 1550
        assert result.facets.date_ranges["venice"][1] == 1570
        assert result.facets.date_ranges["amsterdam"][0] == 1640

        # Language distribution populated
        assert result.facets.language_distribution["venice"]["lat"] == 2
        assert result.facets.language_distribution["amsterdam"]["heb"] == 1

        # Subject overlap (both have Theology and Philosophy)
        assert "Theology" in result.facets.subject_overlap
        assert "Philosophy" in result.facets.subject_overlap

    def test_graceful_no_enrichment(self, db_conn: sqlite3.Connection):
        """find_connections returns empty list when no enrichment data exists."""
        conn = db_conn

        r1 = _insert_record(conn, "990050001")
        _insert_agent(conn, r1, "unknown, author")

        r2 = _insert_record(conn, "990050002")
        _insert_agent(conn, r2, "another, author")

        conn.commit()

        connections = find_connections(
            conn, ["unknown, author", "another, author"],
        )

        assert connections == []

    def test_performance_under_500ms(self, db_conn: sqlite3.Connection):
        """find_connections completes in <500ms for 30 agents."""
        conn = db_conn

        # Insert 30 agents with enrichment data
        for i in range(30):
            r = _insert_record(conn, f"99009{i:04d}")
            uri = f"nli:perf{i:04d}"
            _insert_agent(conn, r, f"agent_{i:03d}", "author", uri)
            _insert_enrichment(conn, uri, f"Q{90000 + i}", f"Agent {i}", {
                "birth_year": 1500 + i,
                "death_year": 1570 + i,
                "occupations": ["scholar"],
                "teachers": [],
                "students": [],
            })

        conn.commit()

        agent_norms = [f"agent_{i:03d}" for i in range(30)]

        start = time.perf_counter()
        find_connections(conn, agent_norms)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, (
            f"find_connections took {elapsed_ms:.1f}ms, expected <500ms"
        )
