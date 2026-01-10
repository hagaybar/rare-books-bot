"""Tests for query compiler.

Validates heuristic parsing patterns and QueryPlan generation.
"""

import pytest
import json
import tempfile
from pathlib import Path

from scripts.query.compile import (
    parse_publisher,
    parse_year_range,
    parse_place,
    parse_language,
    language_name_to_code,
    compile_query,
    write_plan_to_file,
    compute_plan_hash,
)
from scripts.schemas import QueryPlan, FilterField, FilterOp


class TestParsePublisher:
    """Tests for publisher parsing."""

    def test_published_by_pattern(self):
        """Should parse 'published by X' pattern."""
        assert parse_publisher("books published by Oxford") == "Oxford"
        assert parse_publisher("All books published by Cambridge Press") == "Cambridge Press"

    def test_publisher_by_pattern(self):
        """Should parse 'by X' pattern."""
        assert parse_publisher("books by Oxford") == "Oxford"
        assert parse_publisher("items by Venice Press") == "Venice Press"

    def test_by_between_pattern(self):
        """Should parse 'by X between' pattern."""
        assert parse_publisher("books by Oxford between 1500 and 1599") == "Oxford"

    def test_by_in_the_pattern(self):
        """Should parse 'by X in the' pattern."""
        assert parse_publisher("books by Cambridge in the 16th century") == "Cambridge"

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert parse_publisher("PUBLISHED BY OXFORD") == "OXFORD"

    def test_no_match(self):
        """Should return None when no pattern matches."""
        assert parse_publisher("random query with no publisher") is None


class TestParseYearRange:
    """Tests for year range parsing."""

    def test_between_and_pattern(self):
        """Should parse 'between YYYY and YYYY' pattern."""
        assert parse_year_range("books between 1500 and 1599") == (1500, 1599)
        assert parse_year_range("items between 1600 and 1700") == (1600, 1700)

    def test_from_to_pattern(self):
        """Should parse 'from YYYY to YYYY' pattern."""
        assert parse_year_range("books from 1500 to 1599") == (1500, 1599)

    def test_hyphen_pattern(self):
        """Should parse 'YYYY-YYYY' pattern."""
        assert parse_year_range("books 1500-1599") == (1500, 1599)
        assert parse_year_range("published 1600-1650") == (1600, 1650)

    def test_century_pattern(self):
        """Should parse '16th century' pattern."""
        assert parse_year_range("books in the 16th century") == (1501, 1600)
        assert parse_year_range("printed in the 17th century") == (1601, 1700)
        assert parse_year_range("from the 15th century") == (1401, 1500)

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert parse_year_range("BETWEEN 1500 AND 1599") == (1500, 1599)

    def test_no_match(self):
        """Should return None when no pattern matches."""
        assert parse_year_range("random query with no years") is None


class TestParsePlace:
    """Tests for place parsing."""

    def test_printed_in_pattern(self):
        """Should parse 'printed in X' pattern."""
        assert parse_place("books printed in Paris") == "Paris"
        assert parse_place("items printed in London") == "London"

    def test_published_in_pattern(self):
        """Should parse 'published in X' pattern."""
        assert parse_place("books published in Venice") == "Venice"

    def test_from_between_pattern(self):
        """Should parse 'from X between' pattern."""
        assert parse_place("books from Paris between 1500 and 1599") == "Paris"

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert parse_place("PRINTED IN PARIS") == "PARIS"

    def test_no_match(self):
        """Should return None when no pattern matches."""
        assert parse_place("random query with no place") is None


class TestParseLanguage:
    """Tests for language parsing."""

    def test_in_language_pattern(self):
        """Should parse 'in Language' pattern."""
        assert parse_language("books in Latin") == "Latin"
        assert parse_language("texts in Hebrew") == "Hebrew"
        assert parse_language("documents in Greek") == "Greek"

    def test_language_books_pattern(self):
        """Should parse 'Language books' pattern."""
        assert parse_language("Latin books") == "Latin"
        assert parse_language("French texts") == "French"

    def test_supported_languages(self):
        """Should recognize common languages."""
        assert parse_language("in English") == "English"
        assert parse_language("in French") == "French"
        assert parse_language("in German") == "German"
        assert parse_language("in Italian") == "Italian"
        assert parse_language("in Spanish") == "Spanish"
        assert parse_language("in Arabic") == "Arabic"

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert parse_language("IN LATIN") == "LATIN"

    def test_no_match(self):
        """Should return None when no pattern matches."""
        assert parse_language("random query with no language") is None


class TestLanguageNameToCode:
    """Tests for language code conversion."""

    def test_common_languages(self):
        """Should convert common language names to codes."""
        assert language_name_to_code("Latin") == "lat"
        assert language_name_to_code("Hebrew") == "heb"
        assert language_name_to_code("English") == "eng"
        assert language_name_to_code("French") == "fre"
        assert language_name_to_code("German") == "ger"

    def test_case_insensitive(self):
        """Should be case-insensitive."""
        assert language_name_to_code("LATIN") == "lat"
        assert language_name_to_code("latin") == "lat"

    def test_unknown_language(self):
        """Should return lowercased input for unknown languages."""
        assert language_name_to_code("Klingon") == "klingon"


class TestCompileQuery:
    """Tests for complete query compilation."""

    def test_publisher_only(self):
        """Should compile query with only publisher."""
        plan = compile_query("books published by Oxford")
        assert len(plan.filters) == 1
        assert plan.filters[0].field == FilterField.PUBLISHER
        assert plan.filters[0].op == FilterOp.EQUALS
        assert "oxford" in plan.filters[0].value  # Normalized

    def test_year_range_only(self):
        """Should compile query with only year range."""
        plan = compile_query("books between 1500 and 1599")
        assert len(plan.filters) == 1
        assert plan.filters[0].field == FilterField.YEAR
        assert plan.filters[0].op == FilterOp.RANGE
        assert plan.filters[0].start == 1500
        assert plan.filters[0].end == 1599

    def test_place_only(self):
        """Should compile query with only place."""
        plan = compile_query("books printed in Paris")
        assert len(plan.filters) == 1
        assert plan.filters[0].field == FilterField.IMPRINT_PLACE
        assert plan.filters[0].op == FilterOp.EQUALS
        assert "paris" in plan.filters[0].value  # Normalized

    def test_language_only(self):
        """Should compile query with only language."""
        plan = compile_query("books in Latin")
        assert len(plan.filters) == 1
        assert plan.filters[0].field == FilterField.LANGUAGE
        assert plan.filters[0].op == FilterOp.EQUALS
        assert plan.filters[0].value == "lat"  # Converted to code

    def test_publisher_and_year(self):
        """Should compile query with publisher and year range."""
        plan = compile_query("All books published by Oxford between 1500 and 1599")
        assert len(plan.filters) == 2
        # Find filters by field
        publisher_filter = next(f for f in plan.filters if f.field == FilterField.PUBLISHER)
        year_filter = next(f for f in plan.filters if f.field == FilterField.YEAR)
        assert "oxford" in publisher_filter.value
        assert year_filter.start == 1500
        assert year_filter.end == 1599

    def test_complex_query(self):
        """Should compile query with multiple filters."""
        # Use simpler query structure for heuristic parsing
        # Complex nested queries would be handled by LLM in M5
        plan = compile_query("Latin books printed in Paris between 1500 and 1599")
        assert len(plan.filters) >= 3
        # Verify main filter types are present
        fields = {f.field for f in plan.filters}
        assert FilterField.YEAR in fields
        assert FilterField.IMPRINT_PLACE in fields
        assert FilterField.LANGUAGE in fields

    def test_query_with_limit(self):
        """Should include limit if provided."""
        plan = compile_query("books by Oxford", limit=100)
        assert plan.limit == 100

    def test_debug_info_included(self):
        """Should include debug information."""
        plan = compile_query("books published by Oxford between 1500 and 1599")
        assert plan.debug is not None
        assert plan.debug["parser"] == "heuristic"
        assert "patterns_matched" in plan.debug
        assert plan.debug["filters_count"] == 2

    def test_normalization_applied(self):
        """Should normalize publisher and place values."""
        plan = compile_query("books published by [Oxford] printed in [Paris]")
        publisher_filter = next(f for f in plan.filters if f.field == FilterField.PUBLISHER)
        place_filter = next(f for f in plan.filters if f.field == FilterField.IMPRINT_PLACE)
        # Brackets should be removed
        assert "[" not in publisher_filter.value
        assert "[" not in place_filter.value

    def test_empty_query(self):
        """Should compile query with no recognized patterns."""
        plan = compile_query("random unrecognized query")
        assert len(plan.filters) == 0
        assert plan.debug["filters_count"] == 0

    def test_query_text_preserved(self):
        """Should preserve original query text."""
        query = "books by Oxford 1500-1599"
        plan = compile_query(query)
        assert plan.query_text == query


class TestWritePlanToFile:
    """Tests for plan file writing."""

    def test_write_plan(self):
        """Should write plan to JSON file."""
        plan = QueryPlan(
            query_text="test query",
            filters=[]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "plan.json"
            write_plan_to_file(plan, output_path)
            assert output_path.exists()
            # Verify JSON is valid
            with open(output_path, 'r') as f:
                data = json.load(f)
                assert data["query_text"] == "test query"

    def test_create_parent_directories(self):
        """Should create parent directories if they don't exist."""
        plan = QueryPlan(query_text="test", filters=[])
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "plan.json"
            write_plan_to_file(plan, output_path)
            assert output_path.exists()


class TestComputePlanHash:
    """Tests for plan hash computation."""

    def test_same_plan_same_hash(self):
        """Same plan should produce same hash."""
        plan1 = QueryPlan(query_text="test", filters=[])
        plan2 = QueryPlan(query_text="test", filters=[])
        hash1 = compute_plan_hash(plan1)
        hash2 = compute_plan_hash(plan2)
        assert hash1 == hash2

    def test_different_plan_different_hash(self):
        """Different plans should produce different hashes."""
        plan1 = QueryPlan(query_text="test1", filters=[])
        plan2 = QueryPlan(query_text="test2", filters=[])
        hash1 = compute_plan_hash(plan1)
        hash2 = compute_plan_hash(plan2)
        assert hash1 != hash2

    def test_hash_is_sha256(self):
        """Hash should be SHA256 (64 hex characters)."""
        plan = QueryPlan(query_text="test", filters=[])
        hash_value = compute_plan_hash(plan)
        assert len(hash_value) == 64
        assert all(c in '0123456789abcdef' for c in hash_value)
