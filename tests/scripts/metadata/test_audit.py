"""Tests for normalization coverage audit module.

Uses in-memory SQLite databases with controlled test data to verify
confidence distributions, method breakdowns, and flagged item detection.
"""

import sqlite3

import pytest

from scripts.metadata.audit import (
    CoverageReport,
    FieldCoverage,
    _assign_band,
    _build_confidence_distribution,
    build_date_coverage,
    build_place_coverage,
    build_publisher_coverage,
    build_agent_name_coverage,
    build_agent_role_coverage,
    generate_coverage_report,
    generate_coverage_report_from_conn,
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

IMPRINTS_SCHEMA = """
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
    occurrence INTEGER NOT NULL,
    date_raw TEXT,
    place_raw TEXT,
    publisher_raw TEXT,
    manufacturer_raw TEXT,
    source_tags TEXT NOT NULL,
    date_start INTEGER,
    date_end INTEGER,
    date_label TEXT,
    date_confidence REAL,
    date_method TEXT,
    place_norm TEXT,
    place_display TEXT,
    place_confidence REAL,
    place_method TEXT,
    publisher_norm TEXT,
    publisher_display TEXT,
    publisher_confidence REAL,
    publisher_method TEXT,
    country_code TEXT,
    country_name TEXT,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
"""

AGENTS_SCHEMA = """
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    agent_index INTEGER NOT NULL,
    agent_raw TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    role_raw TEXT,
    role_source TEXT,
    authority_uri TEXT,
    agent_norm TEXT NOT NULL,
    agent_confidence REAL NOT NULL CHECK(agent_confidence BETWEEN 0 AND 1),
    agent_method TEXT NOT NULL,
    agent_notes TEXT,
    role_norm TEXT NOT NULL,
    role_confidence REAL NOT NULL CHECK(role_confidence BETWEEN 0 AND 1),
    role_method TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
"""


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create both imprints and agents tables (plus records)."""
    conn.executescript(IMPRINTS_SCHEMA)
    conn.executescript(AGENTS_SCHEMA)


def _insert_record(conn: sqlite3.Connection, mms_id: str = "990001") -> int:
    """Insert a minimal record and return its id."""
    conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        (mms_id, "test.xml", "2025-01-01T00:00:00"),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_imprint(
    conn: sqlite3.Connection,
    record_id: int,
    occurrence: int = 0,
    date_raw: str = "1680",
    date_confidence: float = 0.99,
    date_method: str = "year_exact",
    place_raw: str = "Paris",
    place_norm: str = "paris",
    place_confidence: float = 0.95,
    place_method: str = "place_alias_map",
    publisher_raw: str = "Fosset",
    publisher_norm: str = "fosset",
    publisher_confidence: float = 0.80,
    publisher_method: str = "publisher_casefold_strip",
) -> None:
    """Insert a single imprint row with defaults."""
    conn.execute(
        """INSERT INTO imprints
           (record_id, occurrence, date_raw, source_tags,
            date_start, date_end, date_label, date_confidence, date_method,
            place_raw, place_norm, place_display, place_confidence, place_method,
            publisher_raw, publisher_norm, publisher_display,
            publisher_confidence, publisher_method)
           VALUES (?, ?, ?, '[]',
                   1680, 1680, '1680', ?, ?,
                   ?, ?, ?, ?, ?,
                   ?, ?, ?, ?, ?)""",
        (
            record_id, occurrence, date_raw,
            date_confidence, date_method,
            place_raw, place_norm, place_raw, place_confidence, place_method,
            publisher_raw, publisher_norm, publisher_raw,
            publisher_confidence, publisher_method,
        ),
    )


def _insert_agent(
    conn: sqlite3.Connection,
    record_id: int,
    agent_index: int = 0,
    agent_raw: str = "Smith, John",
    agent_norm: str = "smith, john",
    agent_confidence: float = 0.80,
    agent_method: str = "base_clean",
    role_raw: str = "author",
    role_norm: str = "author",
    role_confidence: float = 0.95,
    role_method: str = "relator_term",
) -> None:
    """Insert a single agent row with defaults."""
    conn.execute(
        """INSERT INTO agents
           (record_id, agent_index, agent_raw, agent_type,
            role_raw, role_source, agent_norm, agent_confidence,
            agent_method, role_norm, role_confidence, role_method,
            provenance_json)
           VALUES (?, ?, ?, 'personal', ?, 'relator_term',
                   ?, ?, ?, ?, ?, ?, '[]')""",
        (
            record_id, agent_index, agent_raw, role_raw,
            agent_norm, agent_confidence, agent_method,
            role_norm, role_confidence, role_method,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_db() -> sqlite3.Connection:
    """In-memory database with schema but no data."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def populated_db() -> sqlite3.Connection:
    """In-memory database with a variety of imprint and agent rows."""
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)

    rid = _insert_record(conn, "990001")
    # High-confidence date, alias-mapped place, base publisher
    _insert_imprint(conn, rid, 0,
                    date_raw="1680", date_confidence=0.99, date_method="year_exact",
                    place_raw="Paris", place_norm="paris",
                    place_confidence=0.95, place_method="place_alias_map",
                    publisher_raw="Fosset", publisher_norm="fosset",
                    publisher_confidence=0.80, publisher_method="publisher_casefold_strip")

    rid2 = _insert_record(conn, "990002")
    # Unparsed date, missing place, missing publisher
    _insert_imprint(conn, rid2, 0,
                    date_raw="unknown", date_confidence=0.0, date_method="unparsed",
                    place_raw=None, place_norm=None,
                    place_confidence=None, place_method=None,
                    publisher_raw=None, publisher_norm=None,
                    publisher_confidence=None, publisher_method=None)

    rid3 = _insert_record(conn, "990003")
    # Circa date, base-cleaned place, alias-mapped publisher
    _insert_imprint(conn, rid3, 0,
                    date_raw="c. 1650", date_confidence=0.80, date_method="year_circa_pm5",
                    place_raw="Amsterdam", place_norm="amsterdam",
                    place_confidence=0.80, place_method="place_casefold_strip",
                    publisher_raw="Elsevier", publisher_norm="elsevier",
                    publisher_confidence=0.95, publisher_method="publisher_alias_map")

    rid4 = _insert_record(conn, "990004")
    # Bracketed date, alias-mapped place, base publisher
    _insert_imprint(conn, rid4, 0,
                    date_raw="[1700]", date_confidence=0.95, date_method="year_bracketed",
                    place_raw="London", place_norm="london",
                    place_confidence=0.95, place_method="place_alias_map",
                    publisher_raw="Oxford Press", publisher_norm="oxford press",
                    publisher_confidence=0.80, publisher_method="publisher_casefold_strip")

    # Agents
    _insert_agent(conn, rid, 0,
                  agent_raw="Smith, John", agent_norm="smith, john",
                  agent_confidence=0.80, agent_method="base_clean",
                  role_raw="author", role_norm="author",
                  role_confidence=0.95, role_method="relator_term")

    _insert_agent(conn, rid2, 0,
                  agent_raw="Anonymous", agent_norm="anonymous",
                  agent_confidence=0.50, agent_method="ambiguous",
                  role_raw=None, role_norm="unknown",
                  role_confidence=0.50, role_method="inferred")

    _insert_agent(conn, rid3, 0,
                  agent_raw="Doe, Jane", agent_norm="doe, jane",
                  agent_confidence=0.95, agent_method="alias_map",
                  role_raw="prt", role_norm="printer",
                  role_confidence=0.99, role_method="relator_code")

    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Unit tests: band assignment
# ---------------------------------------------------------------------------

class TestBandAssignment:
    """Test confidence band assignment logic."""

    def test_zero_confidence(self):
        assert _assign_band(0.0) == "0.00"

    def test_low_confidence(self):
        assert _assign_band(0.3) == "0.00"

    def test_medium_confidence(self):
        assert _assign_band(0.5) == "0.50"
        assert _assign_band(0.79) == "0.50"

    def test_high_confidence(self):
        assert _assign_band(0.80) == "0.80"
        assert _assign_band(0.94) == "0.80"

    def test_very_high_confidence(self):
        assert _assign_band(0.95) == "0.95"
        assert _assign_band(0.98) == "0.95"

    def test_exact_confidence(self):
        assert _assign_band(0.99) == "0.99"
        assert _assign_band(1.0) == "0.99"

    def test_boundary_at_half(self):
        """0.5 is included in the 0.50 band, not 0.00."""
        assert _assign_band(0.5) == "0.50"

    def test_boundary_at_point_eight(self):
        """0.8 is included in the 0.80 band, not 0.50."""
        assert _assign_band(0.8) == "0.80"


# ---------------------------------------------------------------------------
# Unit tests: confidence distribution
# ---------------------------------------------------------------------------

class TestConfidenceDistribution:
    """Test building confidence distribution from raw values."""

    def test_empty_input(self):
        result = _build_confidence_distribution([])
        assert len(result) == 5
        assert all(b.count == 0 for b in result)

    def test_single_high_confidence(self):
        result = _build_confidence_distribution([(0.99,)])
        band_map = {b.band_label: b.count for b in result}
        assert band_map["0.99"] == 1
        assert band_map["0.00"] == 0

    def test_none_treated_as_zero(self):
        result = _build_confidence_distribution([(None,)])
        band_map = {b.band_label: b.count for b in result}
        assert band_map["0.00"] == 1

    def test_mixed_values(self):
        rows = [(0.0,), (0.5,), (0.80,), (0.95,), (0.99,)]
        result = _build_confidence_distribution(rows)
        band_map = {b.band_label: b.count for b in result}
        assert band_map["0.00"] == 1
        assert band_map["0.50"] == 1
        assert band_map["0.80"] == 1
        assert band_map["0.95"] == 1
        assert band_map["0.99"] == 1

    def test_multiple_in_same_band(self):
        rows = [(0.99,), (1.0,), (0.99,)]
        result = _build_confidence_distribution(rows)
        band_map = {b.band_label: b.count for b in result}
        assert band_map["0.99"] == 3


# ---------------------------------------------------------------------------
# Integration tests: per-field coverage on populated DB
# ---------------------------------------------------------------------------

class TestDateCoverage:
    """Test date coverage on populated database."""

    def test_total_records(self, populated_db):
        cov = build_date_coverage(populated_db)
        assert cov.total_records == 4

    def test_non_null_count(self, populated_db):
        cov = build_date_coverage(populated_db)
        # All 4 imprints have date_confidence set (including 0.0)
        assert cov.non_null_count == 4

    def test_method_distribution_includes_unparsed(self, populated_db):
        cov = build_date_coverage(populated_db)
        methods = {m.method: m.count for m in cov.method_distribution}
        assert "unparsed" in methods
        assert methods["unparsed"] == 1

    def test_method_distribution_includes_year_exact(self, populated_db):
        cov = build_date_coverage(populated_db)
        methods = {m.method: m.count for m in cov.method_distribution}
        assert "year_exact" in methods
        assert methods["year_exact"] == 1

    def test_flagged_items_contain_unparsed(self, populated_db):
        cov = build_date_coverage(populated_db)
        flagged_raws = [item.raw_value for item in cov.flagged_items]
        assert "unknown" in flagged_raws

    def test_confidence_distribution_sums_to_total(self, populated_db):
        cov = build_date_coverage(populated_db)
        total_from_bands = sum(b.count for b in cov.confidence_distribution)
        assert total_from_bands == cov.total_records


class TestPlaceCoverage:
    """Test place coverage on populated database."""

    def test_total_records(self, populated_db):
        cov = build_place_coverage(populated_db)
        assert cov.total_records == 4

    def test_null_count(self, populated_db):
        cov = build_place_coverage(populated_db)
        # One imprint has NULL place_confidence
        assert cov.null_count == 1

    def test_flagged_includes_null_place(self, populated_db):
        cov = build_place_coverage(populated_db)
        # NULL place and base-cleaned (0.80) place should both be flagged
        assert len(cov.flagged_items) >= 1

    def test_flagged_includes_low_confidence_place(self, populated_db):
        """Places with confidence <= 0.80 are flagged."""
        cov = build_place_coverage(populated_db)
        flagged_confs = [item.confidence for item in cov.flagged_items]
        # Amsterdam has 0.80 which is <= 0.80 threshold
        assert any(c <= 0.80 for c in flagged_confs)


class TestPublisherCoverage:
    """Test publisher coverage on populated database."""

    def test_total_records(self, populated_db):
        cov = build_publisher_coverage(populated_db)
        assert cov.total_records == 4

    def test_null_count(self, populated_db):
        cov = build_publisher_coverage(populated_db)
        assert cov.null_count == 1

    def test_method_distribution(self, populated_db):
        cov = build_publisher_coverage(populated_db)
        methods = {m.method: m.count for m in cov.method_distribution}
        assert "publisher_casefold_strip" in methods
        assert "publisher_alias_map" in methods


class TestAgentNameCoverage:
    """Test agent name coverage on populated database."""

    def test_total_records(self, populated_db):
        cov = build_agent_name_coverage(populated_db)
        assert cov.total_records == 3

    def test_null_count_always_zero(self, populated_db):
        """Agent confidence is NOT NULL in schema, so null_count is always 0."""
        cov = build_agent_name_coverage(populated_db)
        assert cov.null_count == 0

    def test_ambiguous_agents_flagged(self, populated_db):
        cov = build_agent_name_coverage(populated_db)
        flagged_methods = [item.method for item in cov.flagged_items]
        assert "ambiguous" in flagged_methods

    def test_flagged_agent_has_raw_value(self, populated_db):
        cov = build_agent_name_coverage(populated_db)
        flagged_raws = [item.raw_value for item in cov.flagged_items]
        assert "Anonymous" in flagged_raws


class TestAgentRoleCoverage:
    """Test agent role coverage on populated database."""

    def test_total_records(self, populated_db):
        cov = build_agent_role_coverage(populated_db)
        assert cov.total_records == 3

    def test_low_confidence_roles_flagged(self, populated_db):
        cov = build_agent_role_coverage(populated_db)
        # Agent with role_confidence=0.50 should be flagged
        flagged_confs = [item.confidence for item in cov.flagged_items]
        assert any(c < 0.80 for c in flagged_confs)


# ---------------------------------------------------------------------------
# Integration tests: full report
# ---------------------------------------------------------------------------

class TestCoverageReport:
    """Test full coverage report generation."""

    def test_from_conn(self, populated_db):
        report = generate_coverage_report_from_conn(populated_db)
        assert isinstance(report, CoverageReport)
        assert report.total_imprint_rows == 4
        assert report.total_agent_rows == 3

    def test_to_dict(self, populated_db):
        report = generate_coverage_report_from_conn(populated_db)
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "date_coverage" in d
        assert "place_coverage" in d
        assert "publisher_coverage" in d
        assert "agent_name_coverage" in d
        assert "agent_role_coverage" in d
        assert d["total_imprint_rows"] == 4
        assert d["total_agent_rows"] == 3

    def test_field_coverage_structure(self, populated_db):
        report = generate_coverage_report_from_conn(populated_db)
        for field_name in ["date_coverage", "place_coverage", "publisher_coverage",
                           "agent_name_coverage", "agent_role_coverage"]:
            fc = getattr(report, field_name)
            assert isinstance(fc, FieldCoverage)
            assert isinstance(fc.confidence_distribution, list)
            assert isinstance(fc.method_distribution, list)
            assert isinstance(fc.flagged_items, list)
            assert len(fc.confidence_distribution) == 5

    def test_from_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_coverage_report(tmp_path / "nonexistent.db")

    def test_from_file(self, tmp_path, populated_db):
        """Test generate_coverage_report from a file path."""
        db_path = tmp_path / "test.db"
        # Create a real file-based database with test data
        file_conn = sqlite3.connect(str(db_path))
        _create_schema(file_conn)
        rid = _insert_record(file_conn, "990001")
        _insert_imprint(file_conn, rid)
        _insert_agent(file_conn, rid)
        file_conn.commit()
        file_conn.close()

        report = generate_coverage_report(db_path)
        assert report.total_imprint_rows == 1
        assert report.total_agent_rows == 1


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

class TestEmptyDatabase:
    """Test report on empty database (schema exists but no rows)."""

    def test_empty_report(self, empty_db):
        report = generate_coverage_report_from_conn(empty_db)
        assert report.total_imprint_rows == 0
        assert report.total_agent_rows == 0
        assert report.date_coverage.total_records == 0
        assert report.date_coverage.non_null_count == 0
        assert all(b.count == 0 for b in report.date_coverage.confidence_distribution)

    def test_empty_flagged(self, empty_db):
        report = generate_coverage_report_from_conn(empty_db)
        assert len(report.date_coverage.flagged_items) == 0
        assert len(report.place_coverage.flagged_items) == 0


class TestFlaggedItemOrdering:
    """Test that flagged items are sorted by frequency descending."""

    def test_high_frequency_first(self):
        """Verify items are sorted by frequency (highest first)."""
        conn = sqlite3.connect(":memory:")
        _create_schema(conn)

        # Insert 5 records with same unparsed date raw value
        for i in range(5):
            rid = _insert_record(conn, f"99000{i}")
            _insert_imprint(conn, rid, date_raw="???",
                            date_confidence=0.0, date_method="unparsed")

        # Insert 1 record with a different unparsed date
        rid_single = _insert_record(conn, "990100")
        _insert_imprint(conn, rid_single, date_raw="n.d.",
                        date_confidence=0.0, date_method="unparsed")

        conn.commit()
        cov = build_date_coverage(conn)
        conn.close()

        assert len(cov.flagged_items) >= 2
        # First flagged item should have frequency 5, second should have 1
        assert cov.flagged_items[0].frequency >= cov.flagged_items[1].frequency
        assert cov.flagged_items[0].raw_value == "???"
        assert cov.flagged_items[0].frequency == 5

    def test_place_frequency_ordering(self):
        """Low-confidence places appearing more often rank higher."""
        conn = sqlite3.connect(":memory:")
        _create_schema(conn)

        # 3 records with unmapped place "S.l."
        for i in range(3):
            rid = _insert_record(conn, f"99100{i}")
            _insert_imprint(conn, rid,
                            place_raw="S.l.", place_norm="s.l.",
                            place_confidence=0.0, place_method="missing")

        # 1 record with unmapped place "Obscure Town"
        rid_single = _insert_record(conn, "991100")
        _insert_imprint(conn, rid_single,
                        place_raw="Obscure Town", place_norm="obscure town",
                        place_confidence=0.80, place_method="place_casefold_strip")

        conn.commit()
        cov = build_place_coverage(conn)
        conn.close()

        assert len(cov.flagged_items) >= 2
        assert cov.flagged_items[0].frequency >= cov.flagged_items[1].frequency
        assert cov.flagged_items[0].raw_value == "S.l."
