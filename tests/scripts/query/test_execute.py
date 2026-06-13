"""Tests for query executor.

Validates SQL execution, evidence extraction, and CandidateSet generation.
"""

import logging
import pytest
import sqlite3
import json
from unittest.mock import patch

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp, CandidateSet, Evidence
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


class TestEvidenceExtractionFailure:
    """Tests that evidence extraction failures are logged and marked, not silently swallowed."""

    def test_extraction_error_logged_and_marked(self, test_db, caplog):
        """When extract_evidence_for_filter raises, should log warning and include error evidence."""
        plan = QueryPlan(
            query_text="books by oxford university press",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford university press")
            ]
        )

        # Patch extract_evidence_for_filter to raise an exception
        with patch(
            "scripts.query.execute.extract_evidence_for_filter",
            side_effect=ValueError("simulated extraction failure"),
        ), caplog.at_level(logging.WARNING, logger="scripts.query.execute"):
            candidate_set = execute_plan(plan, test_db)

        # Should still return candidates (fail-visible, not fail-closed)
        assert candidate_set.total_count >= 1

        # Each candidate should have an evidence entry marking the failure
        for candidate in candidate_set.candidates:
            assert len(candidate.evidence) >= 1
            error_evidence = [e for e in candidate.evidence if e.extraction_error is not None]
            assert len(error_evidence) == 1, "Expected exactly one error evidence entry per failed filter"
            assert "simulated extraction failure" in error_evidence[0].extraction_error
            assert error_evidence[0].source == "extraction_failed"
            assert error_evidence[0].operator == "UNKNOWN"

        # Should have logged a warning
        assert any("simulated extraction failure" in rec.message for rec in caplog.records)
        assert any(rec.levelno == logging.WARNING for rec in caplog.records)

    def test_partial_evidence_on_mixed_success(self, test_db, caplog):
        """When one filter succeeds and another fails, should have both evidence entries."""
        plan = QueryPlan(
            query_text="latin books 1500-1599",
            filters=[
                Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599),
            ]
        )

        original_fn = extract_evidence_for_filter

        def selective_fail(filter_obj, row, field_prefix="", conn=None):
            """Fail only on YEAR filters, succeed on others."""
            if filter_obj.field == FilterField.YEAR:
                raise RuntimeError("date extraction broke")
            return original_fn(filter_obj, row, field_prefix, conn=conn)

        with patch(
            "scripts.query.execute.extract_evidence_for_filter",
            side_effect=selective_fail,
        ), caplog.at_level(logging.WARNING, logger="scripts.query.execute"):
            candidate_set = execute_plan(plan, test_db)

        assert candidate_set.total_count >= 1

        for candidate in candidate_set.candidates:
            # Should have 2 evidence entries: 1 success + 1 failure
            assert len(candidate.evidence) == 2

            good = [e for e in candidate.evidence if e.extraction_error is None]
            bad = [e for e in candidate.evidence if e.extraction_error is not None]
            assert len(good) == 1, "Expected one successful evidence entry"
            assert len(bad) == 1, "Expected one error evidence entry"
            assert good[0].field == "language_code"
            assert "date extraction broke" in bad[0].extraction_error

    def test_extraction_error_field_on_evidence_model(self):
        """Evidence model should accept extraction_error field."""
        # Normal evidence (no error)
        normal = Evidence(
            field="test", value="val", operator="=",
            matched_against="val", source="db.test",
        )
        assert normal.extraction_error is None

        # Error evidence
        error_ev = Evidence(
            field="test", value=None, operator="UNKNOWN",
            matched_against=None, source="extraction_failed",
            extraction_error="something went wrong",
        )
        assert error_ev.extraction_error == "something went wrong"


class TestAgentEvidenceProvenance:
    """Agent evidence must carry the real MARC source from provenance_json (issue #43).

    The M3 agents table stores provenance as ``[{"source": "100[0]$a"}]`` —
    the ``source`` value is a STRING. The extractor previously assumed a dict
    shape ({"tag": ..., "occurrence": ...}), hit AttributeError, and silently
    collapsed every agent evidence source to marc:unknown.
    """

    class FakeRow:
        def __init__(self, data):
            self.data = data
        def __getitem__(self, key):
            return self.data[key]
        def keys(self):
            return self.data.keys()
        def get(self, key, default=None):
            return self.data.get(key, default)

    def test_agent_norm_source_from_string_provenance(self):
        """String-shaped provenance (the real DB shape) must yield the MARC tag."""
        filter_obj = Filter(field=FilterField.AGENT_NORM, op=FilterOp.CONTAINS, value="maimonides")
        row = self.FakeRow({
            "agent_norm": "maimonides, moses",
            "agent_confidence": 0.8,
            "agent_provenance": '[{"source": "100[0]$a"}]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.agent_norm (marc:100[0]$a)"
        assert evidence.value == "maimonides, moses"
        assert evidence.confidence == 0.8

    def test_agent_norm_source_from_dict_provenance(self):
        """Legacy dict-shaped provenance must keep working (tag[occurrence])."""
        filter_obj = Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="x")
        row = self.FakeRow({
            "agent_norm": "x",
            "agent_confidence": 0.8,
            "agent_provenance": '[{"source": {"tag": "700", "occurrence": 1}}]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.agent_norm (marc:700[1])"

    def test_agent_norm_source_unknown_when_provenance_missing(self):
        """No provenance at all must still degrade to marc:unknown, not crash."""
        filter_obj = Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="x")
        row = self.FakeRow({"agent_norm": "x", "agent_confidence": 0.8})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.agent_norm (marc:unknown)"

    def test_agent_role_source_from_string_provenance(self):
        filter_obj = Filter(field=FilterField.AGENT_ROLE, op=FilterOp.EQUALS, value="printer")
        row = self.FakeRow({
            "agent_role_norm": "printer",
            "agent_role_confidence": 0.9,
            "agent_provenance": '[{"source": "700[1]$e"}]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.role_norm (marc:700[1]$e)"

    def test_agent_type_source_from_string_provenance(self):
        filter_obj = Filter(field=FilterField.AGENT_TYPE, op=FilterOp.EQUALS, value="corporate")
        row = self.FakeRow({
            "agent_type": "corporate",
            "agent_provenance": '[{"source": "710[0]$a"}]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.agent_type (marc:710[0]$a)"

    def test_deprecated_agent_field_source_from_string_provenance(self):
        filter_obj = Filter(field=FilterField.AGENT, op=FilterOp.CONTAINS, value="buxtorf")
        row = self.FakeRow({
            "agent_raw": "Buxtorf, Johann,",
            "agent_confidence": 0.8,
            "agent_provenance": '[{"source": "100[0]$a"}]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.agents.agent_raw (marc:100[0]$a)"


class TestEvidenceQualityCluster:
    """Issue #51: evidence-layer quality fixes for extract_evidence_for_filter.

    (a) imprint sources must cite the actual subfield+tag from source_tags
    (b) language source must be a clean string, never a serialized JSON list
    (c) country + physical_desc must have real extractor branches
    (d) FTS matches must not yield Evidence.value=None on a real match
    """

    class FakeRow:
        def __init__(self, data):
            self.data = data
        def __getitem__(self, key):
            return self.data[key]
        def keys(self):
            return self.data.keys()
        def get(self, key, default=None):
            return self.data.get(key, default)

    # --- (a) imprint subfield precision -----------------------------------

    def test_publisher_source_cites_264b_from_source_tags(self):
        """Publisher derived from a 264 row must cite marc:264$b, not marc:260."""
        filter_obj = Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="aldine")
        row = self.FakeRow({
            "publisher_norm": "aldine press",
            "publisher_confidence": 0.9,
            "source_tags": '["264"]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.imprints.publisher_norm (marc:264$b)"

    def test_place_source_cites_264a_from_source_tags(self):
        """Imprint place from a 264 row must cite marc:264$a."""
        filter_obj = Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")
        row = self.FakeRow({
            "place_norm": "venice",
            "place_confidence": 0.9,
            "source_tags": '["264"]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.imprints.place_norm (marc:264$a)"

    def test_year_source_cites_264c_from_source_tags(self):
        """Date from a 264 row must cite marc:264$c."""
        filter_obj = Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
        row = self.FakeRow({
            "date_start": 1520,
            "date_end": 1520,
            "date_confidence": 0.99,
            "source_tags": '["264"]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.imprints.date_start/date_end (marc:264$c)"

    def test_imprint_source_falls_back_to_260_when_source_tags_absent(self):
        """No source_tags -> sensible default tag (260) with the subfield."""
        filter_obj = Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="x")
        row = self.FakeRow({"publisher_norm": "x", "publisher_confidence": 0.5})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.imprints.publisher_norm (marc:260$b)"

    def test_imprint_source_preserves_explicit_subfield_in_source_tags(self):
        """If source_tags already encodes a subfield, keep it verbatim."""
        filter_obj = Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="x")
        row = self.FakeRow({
            "publisher_norm": "x",
            "publisher_confidence": 0.5,
            "source_tags": '["260$b"]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.imprints.publisher_norm (marc:260$b)"

    # --- (b) clean language source ----------------------------------------

    def test_language_source_no_json_list_leakage(self):
        """language_source stored as JSON-list string must not leak the list."""
        filter_obj = Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat")
        row = self.FakeRow({
            "language_code": "lat",
            "language_source": '["041$a"]',
        })
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.languages.code (marc:041$a)"
        assert "[" not in evidence.source
        assert '"' not in evidence.source

    def test_language_source_plain_string(self):
        """A plain (non-JSON) source string is used as-is."""
        filter_obj = Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat")
        row = self.FakeRow({"language_code": "lat", "language_source": "041$a"})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.languages.code (marc:041$a)"

    def test_language_source_defaults_to_008_when_missing(self):
        """No language_source -> default to marc:008 (language is in 008)."""
        filter_obj = Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat")
        row = self.FakeRow({"language_code": "lat"})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.source == "db.languages.code (marc:008)"

    # --- (c) country + physical_desc branches -----------------------------

    def test_country_branch_returns_real_source(self):
        """COUNTRY must have a real branch (marc:008), not the unknown fallback."""
        filter_obj = Filter(field=FilterField.COUNTRY, op=FilterOp.EQUALS, value="england")
        row = self.FakeRow({"country_name": "england", "country_code": "enk"})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.value == "england"
        assert evidence.source != "unknown"
        assert evidence.source == "db.imprints.country_name (marc:008)"

    def test_physical_desc_branch_returns_real_source(self):
        """PHYSICAL_DESC must have a real branch (marc:300), not unknown."""
        filter_obj = Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="plates")
        row = self.FakeRow({"physical_desc_value": "24 plates : ill."})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.value == "24 plates : ill."
        assert evidence.source != "unknown"
        assert evidence.source == "db.physical_descriptions.value (marc:300)"

    def test_physical_desc_value_falls_back_to_matched_term(self):
        """When the row carries no phys value, fall back to the matched term."""
        filter_obj = Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="maps")
        row = self.FakeRow({})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.value == "maps"
        assert evidence.source == "db.physical_descriptions.value (marc:300)"

    # --- (d) FTS match must not yield null value --------------------------

    def test_title_fts_value_reread_from_base_table(self, test_db):
        """TITLE FTS match with no title_value column -> re-read from base table."""
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "INSERT INTO titles (record_id, value, source) VALUES (1, ?, ?)",
                ("Cosmographia universalis", '["245$a"]'),
            )
            conn.commit()
            filter_obj = Filter(
                field=FilterField.TITLE, op=FilterOp.CONTAINS, value="cosmographia"
            )
            # Row from an EXISTS-style query: mms_id present, title_value absent.
            cur = conn.execute("SELECT mms_id FROM records WHERE id = 1")
            row = cur.fetchone()
            evidence = extract_evidence_for_filter(filter_obj, row, conn=conn)
            assert evidence.value == "Cosmographia universalis"
            assert evidence.value is not None
        finally:
            conn.close()

    def test_subject_fts_value_reread_from_base_table(self, test_db):
        """SUBJECT FTS match with null subject_value -> re-read from base table."""
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                "INSERT INTO subjects (record_id, value, source) VALUES (2, ?, ?)",
                ("Astronomy -- Early works", '["650[0]$a"]'),
            )
            conn.commit()
            filter_obj = Filter(
                field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="astronomy"
            )
            cur = conn.execute("SELECT mms_id FROM records WHERE id = 2")
            row = cur.fetchone()
            evidence = extract_evidence_for_filter(filter_obj, row, conn=conn)
            assert evidence.value == "Astronomy -- Early works"
            assert evidence.value is not None
        finally:
            conn.close()

    def test_title_fts_value_present_in_row_is_used(self):
        """When title_value is already in the row, no re-read is needed."""
        filter_obj = Filter(
            field=FilterField.TITLE, op=FilterOp.CONTAINS, value="cosmographia"
        )
        row = self.FakeRow({"title_value": "Cosmographia"})
        evidence = extract_evidence_for_filter(filter_obj, row)
        assert evidence.value == "Cosmographia"
