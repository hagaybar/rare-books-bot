"""Tests for query executor.

Validates SQL execution, evidence extraction, and CandidateSet generation.
"""

import pytest
import sqlite3
import json
import tempfile
from pathlib import Path
from datetime import datetime

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp, CandidateSet
from scripts.query.execute import (
    load_plan_from_file,
    extract_evidence_for_filter,
    build_match_rationale,
    execute_plan,
    write_sql_to_file,
    write_candidates_to_file,
    execute_plan_from_file,
)
from scripts.query.compile import write_plan_to_file


@pytest.fixture
def test_db(tmp_path):
    """Create a minimal test database with sample records."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))

    # Create minimal schema
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            mms_id TEXT UNIQUE NOT NULL
        );

        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL,
            publisher_norm TEXT,
            publisher_raw TEXT,
            publisher_confidence REAL,
            place_norm TEXT,
            place_raw TEXT,
            place_confidence REAL,
            date_start INTEGER,
            date_end INTEGER,
            date_confidence REAL,
            source_tags TEXT,
            country_code TEXT,
            country_name TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE TABLE languages (
            id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE TABLE titles (
            id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL,
            value TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL,
            value TEXT NOT NULL,
            source TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            record_id INTEGER NOT NULL,
            agent_raw TEXT NOT NULL,
            agent_norm TEXT NOT NULL,
            agent_confidence REAL NOT NULL,
            agent_type TEXT NOT NULL,
            role_norm TEXT,
            role_confidence REAL,
            provenance_json TEXT,
            FOREIGN KEY (record_id) REFERENCES records(id)
        );

        -- Insert test records
        INSERT INTO records (id, mms_id) VALUES
            (1, '990001'),
            (2, '990002'),
            (3, '990003');

        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name) VALUES
            (1, 'oxford university press', 'Oxford University Press', 0.95,
             'london', 'London', 0.95, 1550, 1550, 0.99, '["260$b"]', 'enk', 'england'),
            (2, 'cambridge press', 'Cambridge Press', 0.90,
             'cambridge', 'Cambridge', 0.90, 1575, 1575, 0.99, '["264$b"]', 'enk', 'england'),
            (3, 'venetian press', 'Venetian Press', 0.85,
             'venice', 'Venice', 0.85, 1520, 1520, 0.99, '["260$b"]', 'it', 'italy');

        INSERT INTO languages (record_id, code, source) VALUES
            (1, 'lat', '041$a'),
            (2, 'eng', '041$a'),
            (3, 'lat', '041$a');
    """)

    conn.commit()
    conn.close()

    return db_path


class TestLoadPlanFromFile:
    """Tests for plan loading."""

    def test_load_valid_plan(self, tmp_path):
        """Should load valid plan from file."""
        plan = QueryPlan(
            query_text="test query",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")]
        )
        plan_path = tmp_path / "plan.json"
        write_plan_to_file(plan, plan_path)

        loaded_plan = load_plan_from_file(plan_path)
        assert loaded_plan.query_text == "test query"
        assert len(loaded_plan.filters) == 1

    def test_load_nonexistent_file_fails(self, tmp_path):
        """Should fail when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_plan_from_file(tmp_path / "nonexistent.json")


class TestExtractEvidenceForFilter:
    """Tests for evidence extraction."""

    def test_publisher_evidence(self):
        """Should extract publisher evidence."""
        filter_obj = Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
        row = {
            "publisher_norm": "oxford university press",
            "publisher_confidence": 0.95,
            "source_tags": '["260$b"]'
        }
        # Convert dict to sqlite3.Row-like object
        class FakeRow:
            def __init__(self, data):
                self.data = data
            def __getitem__(self, key):
                return self.data[key]
            def keys(self):
                return self.data.keys()
            def get(self, key, default=None):
                return self.data.get(key, default)

        evidence = extract_evidence_for_filter(filter_obj, FakeRow(row))
        assert evidence.field == "publisher_norm"
        assert evidence.value == "oxford university press"
        assert evidence.operator == "="
        assert evidence.matched_against == "oxford"
        assert evidence.confidence == 0.95

    def test_year_evidence(self):
        """Should extract year range evidence."""
        filter_obj = Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
        row = {
            "date_start": 1550,
            "date_end": 1550,
            "date_confidence": 0.99,
            "source_tags": '["260$c"]'
        }

        class FakeRow:
            def __init__(self, data):
                self.data = data
            def __getitem__(self, key):
                return self.data[key]
            def keys(self):
                return self.data.keys()
            def get(self, key, default=None):
                return self.data.get(key, default)

        evidence = extract_evidence_for_filter(filter_obj, FakeRow(row))
        assert evidence.field == "date_range"
        assert evidence.value == "1550-1550"
        assert evidence.operator == "OVERLAPS"
        assert evidence.matched_against == "1500-1599"
        assert evidence.confidence == 0.99


class TestBuildMatchRationale:
    """Tests for match rationale generation."""

    def test_publisher_rationale(self):
        """Should build rationale for publisher filter."""
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")]
        )
        row = {"publisher_norm": "oxford university press"}

        class FakeRow:
            def __init__(self, data):
                self.data = data
            def __getitem__(self, key):
                return self.data[key]
            def keys(self):
                return self.data.keys()

        rationale = build_match_rationale(plan, FakeRow(row))
        assert "publisher_norm='oxford university press'" in rationale

    def test_multiple_filters_rationale(self):
        """Should build rationale for multiple filters."""
        plan = QueryPlan(
            query_text="test",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )
        row = {
            "publisher_norm": "oxford",
            "date_start": 1550,
            "date_end": 1550
        }

        class FakeRow:
            def __init__(self, data):
                self.data = data
            def __getitem__(self, key):
                return self.data[key]
            def keys(self):
                return self.data.keys()

        rationale = build_match_rationale(plan, FakeRow(row))
        assert "publisher_norm='oxford'" in rationale
        assert "year_range=" in rationale
        assert " AND " in rationale

    def test_deterministic_rationale(self):
        """Rationale should be deterministic (same input = same output)."""
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")]
        )
        row = {"publisher_norm": "oxford"}

        class FakeRow:
            def __init__(self, data):
                self.data = data
            def __getitem__(self, key):
                return self.data[key]
            def keys(self):
                return self.data.keys()

        rationale1 = build_match_rationale(plan, FakeRow(row))
        rationale2 = build_match_rationale(plan, FakeRow(row))
        assert rationale1 == rationale2


class TestExecutePlan:
    """Tests for plan execution."""

    def test_execute_simple_query(self, test_db):
        """Should execute simple query and return candidates."""
        plan = QueryPlan(
            query_text="books by oxford university press",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford university press")]
        )

        candidate_set = execute_plan(plan, test_db)

        # Should find at least one matching record
        assert candidate_set.total_count >= 1
        assert len(candidate_set.candidates) >= 1

        # Should have correct structure
        assert candidate_set.query_text == "books by oxford university press"
        assert candidate_set.sql is not None
        assert len(candidate_set.plan_hash) == 64  # SHA256

    def test_execute_with_year_range(self, test_db):
        """Should execute query with year range."""
        plan = QueryPlan(
            query_text="books 1500-1599",
            filters=[Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)]
        )

        candidate_set = execute_plan(plan, test_db)

        # Should find records in date range
        assert candidate_set.total_count >= 1

        # Check that evidence is present
        for candidate in candidate_set.candidates:
            assert len(candidate.evidence) > 0
            assert candidate.match_rationale != ""

    def test_execute_with_multiple_filters(self, test_db):
        """Should execute query with multiple filters."""
        plan = QueryPlan(
            query_text="latin books 1500-1599",
            filters=[
                Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )

        candidate_set = execute_plan(plan, test_db)

        # Should have results with both filters applied
        assert candidate_set.total_count >= 1

        # Each candidate should have evidence for both filters
        for candidate in candidate_set.candidates:
            assert len(candidate.evidence) == 2

    def test_candidates_have_evidence(self, test_db):
        """Candidates should have evidence for each filter."""
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford university press")]
        )

        candidate_set = execute_plan(plan, test_db)

        for candidate in candidate_set.candidates:
            assert len(candidate.evidence) == 1
            assert candidate.evidence[0].field == "publisher_norm"
            assert candidate.evidence[0].confidence is not None

    def test_candidates_ordered_by_mms_id(self, test_db):
        """Candidates should be ordered by mms_id for determinism."""
        plan = QueryPlan(
            query_text="all books",
            filters=[Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1600)]
        )

        candidate_set = execute_plan(plan, test_db)

        if len(candidate_set.candidates) > 1:
            # Check ordering
            mms_ids = [c.record_id for c in candidate_set.candidates]
            assert mms_ids == sorted(mms_ids)


class TestWriteOutputFiles:
    """Tests for output file writing."""

    def test_write_sql_to_file(self, tmp_path):
        """Should write SQL to file."""
        sql = "SELECT * FROM records WHERE publisher='oxford'"
        output_path = tmp_path / "sql.txt"

        write_sql_to_file(sql, output_path)

        assert output_path.exists()
        assert output_path.read_text() == sql

    def test_write_candidates_to_file(self, tmp_path):
        """Should write candidates to JSON file."""
        candidate_set = CandidateSet(
            query_text="test",
            plan_hash="abc123",
            sql="SELECT * FROM records",
            candidates=[],
            total_count=0
        )
        output_path = tmp_path / "candidates.json"

        write_candidates_to_file(candidate_set, output_path)

        assert output_path.exists()
        # Verify JSON is valid
        with open(output_path, 'r') as f:
            data = json.load(f)
            assert data["query_text"] == "test"

    def test_create_output_directories(self, tmp_path):
        """Should create parent directories if needed."""
        sql = "SELECT * FROM records"
        output_path = tmp_path / "subdir" / "sql.txt"

        write_sql_to_file(sql, output_path)

        assert output_path.exists()


class TestExecutePlanFromFile:
    """Tests for complete execution from file."""

    def test_execute_from_file(self, tmp_path, test_db):
        """Should execute plan from file and write all outputs."""
        # Create plan file
        plan = QueryPlan(
            query_text="books by oxford university press",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford university press")]
        )
        plan_path = tmp_path / "plan.json"
        write_plan_to_file(plan, plan_path)

        # Execute
        output_dir = tmp_path / "output"
        candidate_set = execute_plan_from_file(plan_path, test_db, output_dir)

        # Verify outputs
        assert (output_dir / "sql.txt").exists()
        assert (output_dir / "candidates.json").exists()

        # Verify candidate set
        assert candidate_set.total_count >= 0
        assert len(candidate_set.sql) > 0
