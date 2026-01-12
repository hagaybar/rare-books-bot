"""Tests for database adapter.

Validates SQL generation, filter value normalization, and JOIN logic.
"""

import pytest
import sqlite3
from pathlib import Path

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.db_adapter import (
    normalize_filter_value,
    build_where_clause,
    build_select_columns,
    build_join_clauses,
    build_full_query,
)


class TestNormalizeFilterValue:
    """Tests for filter value normalization."""

    def test_publisher_normalization(self):
        """Publisher values should be normalized (casefold, strip punctuation)."""
        assert normalize_filter_value(FilterField.PUBLISHER, "Oxford University Press") == "oxford university press"
        assert normalize_filter_value(FilterField.PUBLISHER, "[Amsterdam]") == "amsterdam"
        assert normalize_filter_value(FilterField.PUBLISHER, "Müller & Sons") == "müller sons"

    def test_place_normalization(self):
        """Place values should be normalized (casefold, strip punctuation)."""
        assert normalize_filter_value(FilterField.IMPRINT_PLACE, "Paris") == "paris"
        assert normalize_filter_value(FilterField.IMPRINT_PLACE, "[London]") == "london"
        assert normalize_filter_value(FilterField.IMPRINT_PLACE, "New York") == "new york"

    def test_language_normalization(self):
        """Language codes should be lowercased."""
        assert normalize_filter_value(FilterField.LANGUAGE, "LAT") == "lat"
        assert normalize_filter_value(FilterField.LANGUAGE, "Heb") == "heb"

    def test_title_normalization(self):
        """Titles should be lowercased for FTS."""
        assert normalize_filter_value(FilterField.TITLE, "Historia Mundi") == "historia mundi"

    def test_subject_normalization(self):
        """Subjects should be lowercased for FTS."""
        assert normalize_filter_value(FilterField.SUBJECT, "Philosophy") == "philosophy"

    def test_agent_normalization(self):
        """Agent names should be casefolded."""
        assert normalize_filter_value(FilterField.AGENT, "Dante Alighieri") == "dante alighieri"


class TestBuildWhereClause:
    """Tests for WHERE clause generation."""

    def test_empty_filters(self):
        """Empty filter list should return default WHERE."""
        plan = QueryPlan(query_text="test")
        where, params, joins = build_where_clause(plan)
        assert where == "1=1"
        assert params == {}
        assert joins == []

    def test_publisher_equals(self):
        """Publisher EQUALS filter should generate correct SQL."""
        plan = QueryPlan(
            query_text="books by oxford",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="Oxford")]
        )
        where, params, joins = build_where_clause(plan)
        assert "LOWER(i.publisher_norm) = LOWER(" in where
        assert "imprints" in joins
        assert "oxford" in params.values()

    def test_publisher_contains(self):
        """Publisher CONTAINS filter should use LIKE."""
        plan = QueryPlan(
            query_text="books by university press",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.CONTAINS, value="university")]
        )
        where, params, joins = build_where_clause(plan)
        assert "LIKE" in where
        assert "imprints" in joins
        # Value should be wrapped with %
        assert any("university" in str(v) and "%" in str(v) for v in params.values())

    def test_year_range(self):
        """Year RANGE filter should generate overlap condition."""
        plan = QueryPlan(
            query_text="books 1500-1599",
            filters=[Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)]
        )
        where, params, joins = build_where_clause(plan)
        assert "i.date_end >=" in where
        assert "i.date_start <=" in where
        assert "imprints" in joins
        assert 1500 in params.values()
        assert 1599 in params.values()

    def test_place_equals(self):
        """Place EQUALS filter should generate correct SQL."""
        plan = QueryPlan(
            query_text="printed in paris",
            filters=[Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="Paris")]
        )
        where, params, joins = build_where_clause(plan)
        assert "LOWER(i.place_norm) = LOWER(" in where
        assert "imprints" in joins
        assert "paris" in params.values()

    def test_language_equals(self):
        """Language EQUALS filter should generate correct SQL."""
        plan = QueryPlan(
            query_text="books in latin",
            filters=[Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat")]
        )
        where, params, joins = build_where_clause(plan)
        assert "l.code =" in where
        assert "languages" in joins
        assert "lat" in params.values()

    def test_language_in(self):
        """Language IN filter should generate IN clause."""
        plan = QueryPlan(
            query_text="books in latin or hebrew",
            filters=[Filter(field=FilterField.LANGUAGE, op=FilterOp.IN, value=["lat", "heb"])]
        )
        where, params, joins = build_where_clause(plan)
        assert "l.code IN" in where
        assert "languages" in joins
        assert "lat" in params.values()
        assert "heb" in params.values()

    def test_title_contains(self):
        """Title CONTAINS filter should use FTS5."""
        plan = QueryPlan(
            query_text="books with 'historia' in title",
            filters=[Filter(field=FilterField.TITLE, op=FilterOp.CONTAINS, value="historia")]
        )
        where, params, joins = build_where_clause(plan)
        assert "titles_fts MATCH" in where
        assert "titles" in joins
        assert "historia" in params.values()

    def test_subject_contains(self):
        """Subject CONTAINS filter should use FTS5."""
        plan = QueryPlan(
            query_text="books about philosophy",
            filters=[Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="philosophy")]
        )
        where, params, joins = build_where_clause(plan)
        assert "subjects_fts MATCH" in where
        assert "subjects" in joins
        assert "philosophy" in params.values()

    def test_agent_contains(self):
        """Agent CONTAINS filter should use LIKE."""
        plan = QueryPlan(
            query_text="books by dante",
            filters=[Filter(field=FilterField.AGENT, op=FilterOp.CONTAINS, value="Dante")]
        )
        where, params, joins = build_where_clause(plan)
        assert "LOWER(a.agent_raw) LIKE LOWER(" in where
        assert "agents" in joins
        assert any("dante" in str(v) for v in params.values())

    def test_multiple_filters(self):
        """Multiple filters should be AND-ed together."""
        plan = QueryPlan(
            query_text="books by oxford 1500-1599",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )
        where, params, joins = build_where_clause(plan)
        assert " AND " in where
        assert "imprints" in joins
        assert "oxford" in params.values()
        assert 1500 in params.values()
        assert 1599 in params.values()

    def test_filter_with_negate(self):
        """Filter with negate=True should be wrapped in NOT."""
        plan = QueryPlan(
            query_text="books not by oxford",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford", negate=True)]
        )
        where, params, joins = build_where_clause(plan)
        assert "NOT (" in where
        assert "oxford" in params.values()


class TestBuildSelectColumns:
    """Tests for SELECT column list generation."""

    def test_minimal_columns(self):
        """With no joins, should include only record ID."""
        columns = build_select_columns([])
        assert "DISTINCT r.mms_id" in columns

    def test_imprints_columns(self):
        """With imprints join, should include imprint columns."""
        columns = build_select_columns(["imprints"])
        assert "r.mms_id" in columns
        assert "i.publisher_norm" in columns
        assert "i.place_norm" in columns
        assert "i.date_start" in columns
        assert "i.date_end" in columns
        assert "i.source_tags" in columns

    def test_languages_columns(self):
        """With languages join, should include language columns."""
        columns = build_select_columns(["languages"])
        assert "l.code" in columns
        assert "l.source" in columns

    def test_titles_columns(self):
        """With titles join, should include title columns."""
        columns = build_select_columns(["titles"])
        assert "t.value" in columns
        assert "t.source" in columns

    def test_multiple_joins_columns(self):
        """With multiple joins, should include all columns."""
        columns = build_select_columns(["imprints", "languages"])
        assert "r.mms_id" in columns
        assert "i.publisher_norm" in columns
        assert "l.code" in columns


class TestBuildJoinClauses:
    """Tests for JOIN clause generation."""

    def test_no_joins(self):
        """With no needed joins, should return empty string."""
        joins = build_join_clauses([])
        assert joins == ""

    def test_imprints_join(self):
        """Should generate JOIN for imprints."""
        joins = build_join_clauses(["imprints"])
        assert "JOIN imprints i ON r.id = i.record_id" in joins

    def test_languages_join(self):
        """Should generate LEFT JOIN for languages."""
        joins = build_join_clauses(["languages"])
        assert "LEFT JOIN languages l ON r.id = l.record_id" in joins

    def test_multiple_joins(self):
        """Should generate all needed JOINs."""
        joins = build_join_clauses(["imprints", "languages", "titles"])
        assert "JOIN imprints i" in joins
        assert "LEFT JOIN languages l" in joins
        assert "LEFT JOIN titles t" in joins


class TestBuildFullQuery:
    """Tests for complete SQL query generation."""

    def test_minimal_query(self):
        """Minimal query should work."""
        plan = QueryPlan(query_text="test")
        sql, params = build_full_query(plan)
        assert "SELECT DISTINCT r.mms_id" in sql
        assert "FROM records r" in sql
        assert "WHERE 1=1" in sql
        assert "ORDER BY r.mms_id" in sql

    def test_publisher_year_query(self):
        """Query with publisher and year should generate correct SQL."""
        plan = QueryPlan(
            query_text="books by oxford 1500-1599",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
            ]
        )
        sql, params = build_full_query(plan)
        assert "SELECT DISTINCT r.mms_id" in sql
        assert "i.publisher_norm" in sql
        assert "i.date_start" in sql
        assert "JOIN imprints i" in sql
        assert "WHERE" in sql
        assert "AND" in sql
        assert "ORDER BY r.mms_id" in sql

    def test_query_with_limit(self):
        """Query with limit should include LIMIT clause."""
        plan = QueryPlan(
            query_text="test",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")],
            limit=100
        )
        sql, params = build_full_query(plan)
        assert "LIMIT 100" in sql

    def test_query_deterministic_ordering(self):
        """Query should always include ORDER BY for determinism."""
        plan = QueryPlan(
            query_text="books by oxford",
            filters=[Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")]
        )
        sql, params = build_full_query(plan)
        assert "ORDER BY r.mms_id" in sql

    def test_complex_query(self):
        """Complex query with multiple filters should work."""
        plan = QueryPlan(
            query_text="latin books about philosophy by oxford 1500-1599",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599),
                Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="lat"),
                Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="philosophy")
            ]
        )
        sql, params = build_full_query(plan)
        # Should include all necessary joins
        assert "JOIN imprints i" in sql
        assert "LEFT JOIN languages l" in sql
        # Should have all filter conditions
        assert "i.publisher_norm" in sql
        assert "i.date_start" in sql
        assert "l.code" in sql
        assert "subjects_fts MATCH" in sql
        # Should have proper number of AND conditions (3, since we have 4 filters)
        assert sql.count(" AND ") >= 2
