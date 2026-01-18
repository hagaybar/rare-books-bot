"""Tests for QueryService - Unified Query Pipeline.

Validates that QueryService provides consistent query execution
across all interfaces (CLI, API, Streamlit, QA).
"""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp, CandidateSet
from scripts.query.models import (
    QueryResult,
    QueryOptions,
    QueryWarning,
    FacetCounts,
)
from scripts.query.service import (
    QueryService,
    WARNING_LOW_CONFIDENCE,
    WARNING_EMPTY_FILTERS,
    WARNING_BROAD_DATE_RANGE,
    WARNING_VAGUE_QUERY,
    WARNING_ZERO_RESULTS,
)


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


class TestQueryServiceInit:
    """Tests for QueryService initialization."""

    def test_init_with_path(self, test_db):
        """Should initialize with database path."""
        service = QueryService(test_db)
        assert service.db_path == test_db
        # api_key is either from env or None, test just validates path is set

    def test_init_with_api_key(self, test_db):
        """Should initialize with explicit API key."""
        service = QueryService(test_db, api_key="test-key")
        assert service.api_key == "test-key"

    def test_init_without_env_api_key(self, test_db, monkeypatch):
        """Should have None api_key when not in environment."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        service = QueryService(test_db)
        assert service.api_key is None


class TestQueryServiceExecutePlan:
    """Tests for QueryService.execute_plan with pre-compiled plans."""

    def test_execute_plan_basic(self, test_db):
        """Should execute a basic query plan."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by Oxford",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.CONTAINS,
                    value="oxford"
                )
            ]
        )

        result = service.execute_plan(plan)

        assert isinstance(result, QueryResult)
        assert result.query_plan == plan
        assert result.sql  # SQL should be generated
        assert result.candidate_set is not None
        assert len(result.candidate_set.candidates) == 1  # Only record 1 matches
        assert result.candidate_set.candidates[0].record_id == "990001"

    def test_execute_plan_with_date_range(self, test_db):
        """Should execute a query with date range filter."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books between 1500 and 1560",
            filters=[
                Filter(
                    field=FilterField.YEAR,
                    op=FilterOp.RANGE,
                    start=1500,
                    end=1560
                )
            ]
        )

        result = service.execute_plan(plan)

        assert len(result.candidate_set.candidates) == 2  # Records 1 and 3
        record_ids = {c.record_id for c in result.candidate_set.candidates}
        assert "990001" in record_ids  # 1550
        assert "990003" in record_ids  # 1520

    def test_execute_plan_with_options(self, test_db):
        """Should respect QueryOptions."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="all books",
            filters=[]
        )

        options = QueryOptions(
            compute_facets=False,
            include_warnings=True,
        )

        result = service.execute_plan(plan, options=options)

        # All 3 records should be returned (no filters)
        assert len(result.candidate_set.candidates) == 3
        # No facets computed
        assert result.facets is None


class TestQueryServiceWarnings:
    """Tests for warning extraction."""

    def test_empty_filters_warning(self, test_db):
        """Should warn about empty filter set."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books",
            filters=[]
        )

        result = service.execute_plan(plan, options=QueryOptions(include_warnings=True))

        assert len(result.warnings) >= 1
        warning_codes = {w.code for w in result.warnings}
        assert WARNING_EMPTY_FILTERS in warning_codes

    def test_low_confidence_warning(self, test_db):
        """Should warn about low confidence filters."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by someone",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.CONTAINS,
                    value="unknown",
                    confidence=0.4  # Low confidence
                )
            ]
        )

        result = service.execute_plan(plan, options=QueryOptions(include_warnings=True))

        warning_codes = {w.code for w in result.warnings}
        assert WARNING_LOW_CONFIDENCE in warning_codes

    def test_broad_date_range_warning(self, test_db):
        """Should warn about broad date ranges (>200 years)."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books from 1400 to 1700",
            filters=[
                Filter(
                    field=FilterField.YEAR,
                    op=FilterOp.RANGE,
                    start=1400,
                    end=1700  # 300 years
                )
            ]
        )

        result = service.execute_plan(plan, options=QueryOptions(include_warnings=True))

        warning_codes = {w.code for w in result.warnings}
        assert WARNING_BROAD_DATE_RANGE in warning_codes

    def test_zero_results_warning(self, test_db):
        """Should warn when no results found."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by nonexistent publisher",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.EQUALS,
                    value="nonexistent"
                )
            ]
        )

        result = service.execute_plan(plan, options=QueryOptions(include_warnings=True))

        assert len(result.candidate_set.candidates) == 0
        warning_codes = {w.code for w in result.warnings}
        assert WARNING_ZERO_RESULTS in warning_codes

    def test_no_warnings_when_disabled(self, test_db):
        """Should not generate warnings when disabled."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books",
            filters=[]
        )

        result = service.execute_plan(plan, options=QueryOptions(include_warnings=False))

        assert len(result.warnings) == 0


class TestQueryServiceFacets:
    """Tests for facet computation."""

    def test_compute_facets_when_enabled(self, test_db):
        """Should compute facets when requested."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="all books",
            filters=[]
        )

        result = service.execute_plan(plan, options=QueryOptions(compute_facets=True))

        assert result.facets is not None
        assert isinstance(result.facets, FacetCounts)

    def test_facets_by_place(self, test_db):
        """Should compute place facets correctly."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="all books",
            filters=[]
        )

        result = service.execute_plan(plan, options=QueryOptions(compute_facets=True))

        # Check place facets
        assert "london" in result.facets.by_place
        assert "cambridge" in result.facets.by_place
        assert "venice" in result.facets.by_place

    def test_no_facets_when_disabled(self, test_db):
        """Should not compute facets when disabled."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="all books",
            filters=[]
        )

        result = service.execute_plan(plan, options=QueryOptions(compute_facets=False))

        assert result.facets is None


class TestQueryServiceExecutionTime:
    """Tests for execution time tracking."""

    def test_execution_time_tracked(self, test_db):
        """Should track execution time in milliseconds."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by Oxford",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.CONTAINS,
                    value="oxford"
                )
            ]
        )

        result = service.execute_plan(plan)

        assert result.execution_time_ms > 0


class TestQueryServiceEvidence:
    """Tests for evidence extraction in results."""

    def test_candidates_have_evidence(self, test_db):
        """Should include evidence for each candidate."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by Oxford",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.CONTAINS,
                    value="oxford"
                )
            ]
        )

        result = service.execute_plan(plan)

        for candidate in result.candidate_set.candidates:
            assert len(candidate.evidence) > 0
            assert candidate.match_rationale  # Should have rationale

    def test_evidence_includes_field_info(self, test_db):
        """Should include field information in evidence."""
        service = QueryService(test_db)

        plan = QueryPlan(
            query_text="books by Oxford",
            filters=[
                Filter(
                    field=FilterField.PUBLISHER,
                    op=FilterOp.CONTAINS,
                    value="oxford"
                )
            ]
        )

        result = service.execute_plan(plan)

        candidate = result.candidate_set.candidates[0]
        evidence = candidate.evidence[0]

        assert evidence.field  # e.g., "publisher_norm"
        assert evidence.value  # e.g., "oxford university press"
        assert evidence.operator  # e.g., "LIKE"


class TestQueryOptions:
    """Tests for QueryOptions model."""

    def test_default_options(self):
        """Should have sensible defaults."""
        options = QueryOptions()

        assert options.compute_facets is False
        assert options.facet_limit == 10
        assert options.include_warnings is True
        assert options.limit is None

    def test_custom_options(self):
        """Should accept custom values."""
        options = QueryOptions(
            compute_facets=True,
            facet_limit=20,
            include_warnings=False,
            limit=100
        )

        assert options.compute_facets is True
        assert options.facet_limit == 20
        assert options.include_warnings is False
        assert options.limit == 100


class TestQueryWarning:
    """Tests for QueryWarning model."""

    def test_basic_warning(self):
        """Should create warning with code and message."""
        warning = QueryWarning(
            code="TEST_CODE",
            message="Test message"
        )

        assert warning.code == "TEST_CODE"
        assert warning.message == "Test message"
        assert warning.field is None
        assert warning.confidence is None

    def test_warning_with_field(self):
        """Should include field information."""
        warning = QueryWarning(
            code="LOW_CONFIDENCE",
            message="Low confidence on publisher",
            field="publisher",
            confidence=0.5
        )

        assert warning.field == "publisher"
        assert warning.confidence == 0.5


class TestFacetCounts:
    """Tests for FacetCounts model."""

    def test_default_facets(self):
        """Should have empty defaults."""
        facets = FacetCounts()

        assert facets.by_place == {}
        assert facets.by_year == {}
        assert facets.by_language == {}
        assert facets.by_publisher == {}
        assert facets.by_century == {}

    def test_custom_facets(self):
        """Should accept custom values."""
        facets = FacetCounts(
            by_place={"london": 5, "paris": 3},
            by_language={"lat": 10}
        )

        assert facets.by_place == {"london": 5, "paris": 3}
        assert facets.by_language == {"lat": 10}
