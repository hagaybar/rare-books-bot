"""Tests for query compiler module.

After LLM migration, this file tests the compile module's public interface:
- compile_query (now delegated to llm_compiler)
- write_plan_to_file (utility function)
- compute_plan_hash (utility function)

Detailed LLM compiler tests are in test_llm_compiler.py.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from scripts.query.compile import (
    compile_query,
    write_plan_to_file,
    compute_plan_hash,
)
from scripts.query.exceptions import QueryCompilationError
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp


class TestCompileQuery:
    """Tests for compile_query function (now LLM-based)."""

    @patch('scripts.query.llm_compiler.OpenAI')
    @patch('scripts.query.llm_compiler.load_cache')
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_compile_query_basic(self, mock_write_cache, mock_load_cache, mock_openai_class, tmp_path):
        """Should compile query using LLM."""
        # Mock empty cache
        mock_load_cache.return_value = {}

        # Mock OpenAI client
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock LLM response with usage stats (required for llm_logger)
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_plan = QueryPlan(
            query_text="books published by Oxford",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
            ]
        )
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        # Call compile_query
        plan = compile_query("books published by Oxford", api_key="test-key")

        # Verify result
        assert plan.query_text == "books published by Oxford"
        assert len(plan.filters) == 1
        assert plan.filters[0].field == FilterField.PUBLISHER
        assert plan.filters[0].value == "oxford"

    @patch('scripts.query.llm_compiler.load_cache')
    def test_compile_query_with_cache(self, mock_load_cache):
        """Should use cached result when available."""
        # Mock cache with existing entry
        cached_plan_data = {
            "query_text": "cached query",
            "filters": [
                {"field": "publisher", "op": "EQUALS", "value": "oxford"}
            ],
            "version": "1.0"
        }

        mock_load_cache.return_value = {
            "cached query": {
                "query_text": "cached query",
                "plan": cached_plan_data,
                "model": "gpt-4o",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }

        plan = compile_query("cached query", api_key="test-key")

        assert plan.query_text == "cached query"
        assert len(plan.filters) == 1
        assert plan.debug.get("cache_hit") is True

    @patch('scripts.query.llm_compiler.load_cache')
    def test_compile_query_missing_api_key(self, mock_load_cache):
        """Should raise error if API key not provided."""
        mock_load_cache.return_value = {}  # Empty cache, no cache hit
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(QueryCompilationError, match="OpenAI API key"):
                compile_query("test query")

    @patch('scripts.query.llm_compiler.OpenAI')
    @patch('scripts.query.llm_compiler.load_cache')
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_compile_query_with_limit(self, mock_write_cache, mock_load_cache, mock_openai_class):
        """Should apply limit parameter to plan."""
        mock_load_cache.return_value = {}

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock LLM response with usage stats (required for llm_logger)
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_plan = QueryPlan(query_text="test", filters=[])
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        plan = compile_query("test", limit=50, api_key="test-key")

        assert plan.limit == 50


class TestWritePlanToFile:
    """Tests for plan file writing."""

    def test_write_plan(self):
        """Should write plan to JSON file."""
        plan = QueryPlan(
            query_text="test query",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "plan.json"
            write_plan_to_file(plan, output_path)

            assert output_path.exists()

            # Verify JSON is valid and contains expected data
            with open(output_path, 'r') as f:
                data = json.load(f)
                assert data["query_text"] == "test query"
                assert len(data["filters"]) == 1
                assert data["filters"][0]["field"] == "publisher"

    def test_create_parent_directories(self):
        """Should create parent directories if they don't exist."""
        plan = QueryPlan(query_text="test", filters=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "nested" / "plan.json"
            write_plan_to_file(plan, output_path)

            assert output_path.exists()

    def test_unicode_handling(self):
        """Should handle Unicode characters in plan."""
        plan = QueryPlan(
            query_text="ספרים עבריים",  # Hebrew text
            filters=[
                Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="heb", notes="Hebrew text")
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "plan.json"
            write_plan_to_file(plan, output_path)

            # Verify Unicode is preserved
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                assert "ספרים עבריים" in data["query_text"]


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

    def test_filter_order_matters(self):
        """Filter order should affect hash (since we sort keys in serialization)."""
        plan1 = QueryPlan(
            query_text="test",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="a"),
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1600)
            ]
        )

        plan2 = QueryPlan(
            query_text="test",
            filters=[
                Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1600),
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="a")
            ]
        )

        hash1 = compute_plan_hash(plan1)
        hash2 = compute_plan_hash(plan2)

        # Hashes should differ because filter order is part of the plan
        assert hash1 != hash2

    def test_hash_deterministic(self):
        """Multiple hash computations of same plan should be identical."""
        plan = QueryPlan(
            query_text="test query",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
            ]
        )

        hashes = [compute_plan_hash(plan) for _ in range(10)]

        # All hashes should be identical
        assert len(set(hashes)) == 1


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing code."""

    @patch('scripts.query.llm_compiler.load_cache')
    def test_imports_work(self, mock_load_cache):
        """Should be able to import functions from compile module."""
        # These imports should work
        from scripts.query.compile import compile_query, write_plan_to_file, compute_plan_hash

        assert callable(compile_query)
        assert callable(write_plan_to_file)
        assert callable(compute_plan_hash)

    @patch('scripts.query.llm_compiler.OpenAI')
    @patch('scripts.query.llm_compiler.load_cache')
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_compile_query_signature(self, mock_write_cache, mock_load_cache, mock_openai_class):
        """Should accept same parameters as before (with api_key added)."""
        mock_load_cache.return_value = {}

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock LLM response with usage stats (required for llm_logger)
        mock_response = Mock()
        mock_response.usage = Mock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_plan = QueryPlan(query_text="test query", filters=[])
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        # Should accept query_text and limit
        plan = compile_query("test query", limit=100, api_key="test-key")

        assert plan.query_text == "test query"
        assert plan.limit == 100


# Legacy tests are removed - they tested regex patterns that no longer exist
# New LLM-specific tests are in test_llm_compiler.py
