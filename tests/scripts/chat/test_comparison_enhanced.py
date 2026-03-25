"""Unit tests for E3 enhanced comparison (multi-faceted analysis).

Tests execute_comparison_enhanced() which returns ComparisonResult with
counts, date_ranges, language_distribution, top_agents, top_subjects,
shared_agents, and subject_overlap populated. Also verifies backward
compatibility of the existing execute_comparison() function.

All tests use in-memory SQLite fixtures with production-like schema.
Tests are written TDD-style: they MUST fail initially (ImportError or
AttributeError) until execute_comparison_enhanced() is implemented in
scripts/chat/aggregation.py.

Spec reference: reports/historian-enhancement-plan.md lines 430-565 (E3).
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from scripts.chat.aggregation import execute_comparison
from scripts.chat.models import ComparisonFacets, ComparisonResult


# =============================================================================
# Fixtures: in-memory SQLite with production-like schema
# =============================================================================


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal tables matching m3_schema.sql for comparison tests."""
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL UNIQUE,
            source_file TEXT NOT NULL,
            created_at TEXT NOT NULL,
            jsonl_line_number INTEGER
        );

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
    """Insert a record and return its id."""
    cur = conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        (mms_id, "test.xml", _now_iso()),
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
    """Insert an imprint row and return its id."""
    cur = conn.execute(
        """INSERT INTO imprints
           (record_id, imprint_index, place_raw, place_norm, place_confidence,
            place_method, publisher_norm, date_start, country_name, provenance_json)
           VALUES (?, 0, ?, ?, 0.95, 'place_alias_map', ?, ?, ?, '[]')""",
        (record_id, place_norm, place_norm, publisher_norm, date_start, country_name),
    )
    return cur.lastrowid


def _insert_agent(
    conn: sqlite3.Connection,
    record_id: int,
    agent_norm: str,
    role_norm: str = "author",
    agent_index: int = 0,
) -> int:
    """Insert an agent row and return its id."""
    cur = conn.execute(
        """INSERT INTO agents
           (record_id, agent_index, agent_raw, agent_type,
            agent_norm, agent_confidence, agent_method, role_norm,
            role_confidence, role_method, provenance_json)
           VALUES (?, ?, ?, 'personal', ?, 0.95, 'base_clean', ?, 0.95,
                   'relator_code', '[]')""",
        (record_id, agent_index, agent_norm, agent_norm, role_norm),
    )
    return cur.lastrowid


def _insert_language(conn: sqlite3.Connection, record_id: int, code: str) -> int:
    """Insert a language row and return its id."""
    cur = conn.execute(
        "INSERT INTO languages (record_id, code) VALUES (?, ?)",
        (record_id, code),
    )
    return cur.lastrowid


def _insert_subject(conn: sqlite3.Connection, record_id: int, value: str) -> int:
    """Insert a subject row and return its id."""
    cur = conn.execute(
        "INSERT INTO subjects (record_id, tag, value, source) VALUES (?, '650', ?, 'lcsh')",
        (record_id, value),
    )
    return cur.lastrowid


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite database with the schema."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    return conn


@pytest.fixture
def comparison_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database with Venice and Amsterdam records for comparison testing.

    Venice records (3):
      990001001 - Latin, 1550, agent: manutius, subject: theology
      990001002 - Latin, 1560, agent: manutius, subject: philosophy
      990001003 - Hebrew, 1570, agent: bomberg, subject: theology

    Amsterdam records (2):
      990002001 - Hebrew, 1640, agent: menasseh, subject: theology
      990002002 - Latin, 1650, agent: elzevir, subject: philosophy
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


@pytest.fixture
def all_record_ids() -> list[str]:
    """All MMS IDs in the comparison fixture."""
    return ["990001001", "990001002", "990001003", "990002001", "990002002"]


# =============================================================================
# Fixture with shared agents
# =============================================================================

@pytest.fixture
def shared_agent_db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Database where an agent appears in both Venice and Amsterdam records.

    Shared agent 'spinoza, baruch' appears in records from both cities.
    """
    conn = db_conn

    # Venice record with shared agent
    r1 = _insert_record(conn, "990003001")
    _insert_imprint(conn, r1, "venice", 1555, "manutius", "Italy")
    _insert_agent(conn, r1, "spinoza, baruch")
    _insert_language(conn, r1, "lat")
    _insert_subject(conn, r1, "Philosophy")

    # Amsterdam record with shared agent
    r2 = _insert_record(conn, "990003002")
    _insert_imprint(conn, r2, "amsterdam", 1665, "rieuwertsz", "Netherlands")
    _insert_agent(conn, r2, "spinoza, baruch")
    _insert_language(conn, r2, "lat")
    _insert_subject(conn, r2, "Ethics")

    # Additional Venice record (no shared agent)
    r3 = _insert_record(conn, "990003003")
    _insert_imprint(conn, r3, "venice", 1560, "manutius", "Italy")
    _insert_agent(conn, r3, "manutius, aldus")
    _insert_language(conn, r3, "lat")
    _insert_subject(conn, r3, "Rhetoric")

    conn.commit()
    return conn


# =============================================================================
# Tests: Enhanced Comparison
# =============================================================================


class TestComparisonEnhanced:
    """Tests for execute_comparison_enhanced() multi-faceted analysis."""

    def test_comparison_facets_populated(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """execute_comparison_enhanced returns ComparisonResult with all facet
        types populated: counts, date_ranges, language_distribution,
        top_agents, and top_subjects."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        # Write the in-memory DB to a temp file so Path-based API works
        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        assert isinstance(result, ComparisonResult)
        assert result.field == "place"
        assert set(result.values) == {"venice", "amsterdam"}

        facets = result.facets
        # counts populated
        assert "venice" in facets.counts
        assert "amsterdam" in facets.counts
        assert facets.counts["venice"] == 3
        assert facets.counts["amsterdam"] == 2

        # date_ranges populated
        assert "venice" in facets.date_ranges
        assert "amsterdam" in facets.date_ranges

        # language_distribution populated
        assert "venice" in facets.language_distribution
        assert "amsterdam" in facets.language_distribution

        # top_agents populated
        assert "venice" in facets.top_agents
        assert "amsterdam" in facets.top_agents

        # top_subjects populated
        assert "venice" in facets.top_subjects
        assert "amsterdam" in facets.top_subjects

    def test_shared_agents_discovered(
        self, shared_agent_db: sqlite3.Connection, tmp_path
    ):
        """Agents appearing in both compared value sets are in shared_agents."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        shared_agent_db.backup(backup)
        backup.close()

        record_ids = ["990003001", "990003002", "990003003"]
        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        assert "spinoza, baruch" in result.facets.shared_agents

    def test_subject_overlap(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """Common subjects between compared values are found in subject_overlap."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        # 'Theology' appears in both Venice and Amsterdam
        assert "Theology" in result.facets.subject_overlap
        # 'Philosophy' also appears in both
        assert "Philosophy" in result.facets.subject_overlap

    def test_backward_compatible(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """Old execute_comparison() still works and returns Dict[str, int]."""
        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        assert isinstance(result, dict)
        assert result["venice"] == 3
        assert result["amsterdam"] == 2

    def test_empty_comparison(self, db_conn: sqlite3.Connection, tmp_path):
        """Empty values list handled gracefully."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        db_conn.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=["990001001"],
            field="place",
            values=[],
        )

        assert isinstance(result, ComparisonResult)
        assert result.facets.counts == {}
        assert result.facets.shared_agents == []
        assert result.facets.subject_overlap == []

    def test_single_value(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """Comparison with single value returns valid result (no shared/overlap)."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice"],
        )

        assert isinstance(result, ComparisonResult)
        assert result.facets.counts["venice"] == 3
        # Single value means no shared agents or subject overlap
        assert result.facets.shared_agents == []
        assert result.facets.subject_overlap == []

    def test_date_ranges_correct(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """Min/max dates per compared value are correct."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        venice_range = result.facets.date_ranges["venice"]
        amsterdam_range = result.facets.date_ranges["amsterdam"]

        # Venice: 1550, 1560, 1570 -> min=1550, max=1570
        assert venice_range[0] == 1550
        assert venice_range[1] == 1570

        # Amsterdam: 1640, 1650 -> min=1640, max=1650
        assert amsterdam_range[0] == 1640
        assert amsterdam_range[1] == 1650

    def test_language_distribution(
        self, comparison_db: sqlite3.Connection, all_record_ids: list[str], tmp_path
    ):
        """Language counts per compared value are correct."""
        from scripts.chat.aggregation import execute_comparison_enhanced

        db_path = tmp_path / "test.db"
        backup = sqlite3.connect(str(db_path))
        comparison_db.backup(backup)
        backup.close()

        result = execute_comparison_enhanced(
            db_path=db_path,
            record_ids=all_record_ids,
            field="place",
            values=["venice", "amsterdam"],
        )

        venice_langs = result.facets.language_distribution["venice"]
        amsterdam_langs = result.facets.language_distribution["amsterdam"]

        # Venice: 2 Latin, 1 Hebrew
        assert venice_langs["lat"] == 2
        assert venice_langs["heb"] == 1

        # Amsterdam: 1 Hebrew, 1 Latin
        assert amsterdam_langs["heb"] == 1
        assert amsterdam_langs["lat"] == 1
