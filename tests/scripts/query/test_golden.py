"""Golden test for M4 end-to-end pipeline.

Tests the complete M4 flow: NL query → QueryPlan → SQL → CandidateSet
with the reference query from M4 specifications.
"""

import pytest
import sqlite3
import json
import tempfile
from pathlib import Path

from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.schemas import FilterField


@pytest.fixture
def golden_db(tmp_path):
    """Create golden test database with known records.

    This database contains carefully crafted test records to verify
    the M4 pipeline produces correct results for the reference query.
    """
    db_path = tmp_path / "golden.db"
    conn = sqlite3.connect(str(db_path))

    # Create schema (minimal version for testing)
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
    """)

    # Insert test data
    # Record 1: Matches publisher "x" and year range 1500-1599
    conn.execute("INSERT INTO records (id, mms_id) VALUES (1, '990001')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (1, 'x', 'X', 0.80, 'london', 'London', 0.90, 1510, 1510, 0.99, '["260$b"]', 'enk', 'england')
    """)

    # Record 2: Matches publisher "x" but year is outside range
    conn.execute("INSERT INTO records (id, mms_id) VALUES (2, '990002')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (2, 'x', 'X', 0.80, 'paris', 'Paris', 0.90, 1650, 1650, 0.99, '["260$b"]', 'fr', 'france')
    """)

    # Record 3: Matches year range but different publisher
    conn.execute("INSERT INTO records (id, mms_id) VALUES (3, '990003')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (3, 'cambridge press', 'Cambridge Press', 0.90, 'cambridge', 'Cambridge', 0.95, 1550, 1550, 0.99, '["260$b"]', 'enk', 'england')
    """)

    # Record 4: Another match for publisher "x" and year range
    conn.execute("INSERT INTO records (id, mms_id) VALUES (4, '990004')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (4, 'x', 'X', 0.80, 'venice', 'Venice', 0.85, 1590, 1590, 0.99, '["264$b"]', 'it', 'italy')
    """)

    # Record 5: Edge case - year range boundary (1599)
    conn.execute("INSERT INTO records (id, mms_id) VALUES (5, '990005')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (5, 'x', 'X', 0.80, 'oxford', 'Oxford', 0.90, 1599, 1599, 0.99, '["260$b"]', 'enk', 'england')
    """)

    # Record 6: Edge case - year range boundary (1500)
    conn.execute("INSERT INTO records (id, mms_id) VALUES (6, '990006')")
    conn.execute("""
        INSERT INTO imprints (record_id, publisher_norm, publisher_raw, publisher_confidence,
                             place_norm, place_raw, place_confidence,
                             date_start, date_end, date_confidence, source_tags,
                             country_code, country_name)
        VALUES (6, 'x', 'X', 0.80, 'amsterdam', 'Amsterdam', 0.95, 1500, 1500, 0.99, '["260$c"]', 'ne', 'netherlands')
    """)

    conn.commit()
    conn.close()

    return db_path


class TestGoldenQuery:
    """Golden test for reference M4 query."""

    def test_reference_query_execution(self, golden_db):
        """Test reference query: 'All books published by X between 1500 and 1599'.

        This is the primary success condition from M4 specifications.
        """
        query_text = "All books published by X between 1500 and 1599"

        # Step 1: Compile query
        plan = compile_query(query_text)

        # Verify plan structure
        assert plan.query_text == query_text
        assert len(plan.filters) == 2

        # Verify filters were extracted
        filter_fields = {f.field for f in plan.filters}
        assert FilterField.PUBLISHER in filter_fields
        assert FilterField.YEAR in filter_fields

        # Find specific filters
        publisher_filter = next(f for f in plan.filters if f.field == FilterField.PUBLISHER)
        year_filter = next(f for f in plan.filters if f.field == FilterField.YEAR)

        # Verify publisher filter
        assert publisher_filter.value == "x"  # Normalized from "X"

        # Verify year filter
        assert year_filter.start == 1500
        assert year_filter.end == 1599

        # Step 2: Execute plan
        candidate_set = execute_plan(plan, golden_db)

        # Verify CandidateSet structure
        assert candidate_set.query_text == query_text
        assert len(candidate_set.plan_hash) == 64  # SHA256
        assert candidate_set.sql is not None
        assert len(candidate_set.sql) > 0

        # Verify correct candidates returned
        # Should match records: 1, 4, 5, 6 (publisher='x' AND year in range)
        # Should NOT match: 2 (year outside), 3 (different publisher)
        expected_record_ids = {"990001", "990004", "990005", "990006"}
        actual_record_ids = {c.record_id for c in candidate_set.candidates}
        assert actual_record_ids == expected_record_ids, (
            f"Expected {expected_record_ids}, got {actual_record_ids}"
        )

        # Verify count matches
        assert candidate_set.total_count == 4
        assert len(candidate_set.candidates) == 4

    def test_candidates_have_evidence(self, golden_db):
        """Every candidate must have evidence for each filter."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        for candidate in candidate_set.candidates:
            # Should have evidence for both filters
            assert len(candidate.evidence) == 2

            # Check evidence fields
            evidence_fields = {e.field for e in candidate.evidence}
            assert "publisher_norm" in evidence_fields
            assert "date_range" in evidence_fields

            # Check evidence has required attributes
            for evidence in candidate.evidence:
                assert evidence.value is not None
                assert evidence.operator is not None
                assert evidence.matched_against is not None
                assert evidence.source is not None
                # Publisher and date should have confidence scores
                if evidence.field in ["publisher_norm", "date_range"]:
                    assert evidence.confidence is not None

    def test_match_rationale_present(self, golden_db):
        """Every candidate must have a match rationale."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        for candidate in candidate_set.candidates:
            assert candidate.match_rationale != ""
            assert "publisher_norm" in candidate.match_rationale
            assert "year_range" in candidate.match_rationale
            assert "overlaps" in candidate.match_rationale

    def test_deterministic_output(self, golden_db):
        """Re-running the same query should produce identical output."""
        query_text = "All books published by X between 1500 and 1599"

        # Run 1
        plan1 = compile_query(query_text)
        candidate_set1 = execute_plan(plan1, golden_db)

        # Run 2
        plan2 = compile_query(query_text)
        candidate_set2 = execute_plan(plan2, golden_db)

        # Plans should be identical
        assert plan1.model_dump() == plan2.model_dump()

        # Candidate sets should be identical
        assert candidate_set1.total_count == candidate_set2.total_count
        assert len(candidate_set1.candidates) == len(candidate_set2.candidates)

        # Record IDs should be in same order
        record_ids1 = [c.record_id for c in candidate_set1.candidates]
        record_ids2 = [c.record_id for c in candidate_set2.candidates]
        assert record_ids1 == record_ids2

        # Match rationales should be identical
        rationales1 = [c.match_rationale for c in candidate_set1.candidates]
        rationales2 = [c.match_rationale for c in candidate_set2.candidates]
        assert rationales1 == rationales2

    def test_ordering_deterministic(self, golden_db):
        """Results should be ordered by mms_id for determinism."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        record_ids = [c.record_id for c in candidate_set.candidates]
        assert record_ids == sorted(record_ids), "Results must be sorted by record_id"

    def test_edge_cases_included(self, golden_db):
        """Year range boundaries (1500 and 1599) should be included."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        record_ids = {c.record_id for c in candidate_set.candidates}

        # Record with year 1500 should be included
        assert "990006" in record_ids

        # Record with year 1599 should be included
        assert "990005" in record_ids

    def test_outside_range_excluded(self, golden_db):
        """Records outside year range should be excluded."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        record_ids = {c.record_id for c in candidate_set.candidates}

        # Record 990002 has year 1650 (outside range) - should NOT be included
        assert "990002" not in record_ids

    def test_different_publisher_excluded(self, golden_db):
        """Records with different publisher should be excluded."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        record_ids = {c.record_id for c in candidate_set.candidates}

        # Record 990003 has publisher 'cambridge press' - should NOT be included
        assert "990003" not in record_ids

    def test_plan_hash_computed(self, golden_db):
        """Plan hash should be SHA256 of canonicalized plan."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        # Hash should be 64 hex characters
        assert len(candidate_set.plan_hash) == 64
        assert all(c in '0123456789abcdef' for c in candidate_set.plan_hash)

    def test_sql_included_in_output(self, golden_db):
        """CandidateSet should include the exact SQL executed."""
        query_text = "All books published by X between 1500 and 1599"
        plan = compile_query(query_text)
        candidate_set = execute_plan(plan, golden_db)

        # SQL should be present and non-empty
        assert candidate_set.sql is not None
        assert len(candidate_set.sql) > 0

        # SQL should contain key elements
        assert "SELECT" in candidate_set.sql
        assert "FROM records" in candidate_set.sql
        assert "JOIN imprints" in candidate_set.sql
        assert "WHERE" in candidate_set.sql
        assert "ORDER BY r.mms_id" in candidate_set.sql
