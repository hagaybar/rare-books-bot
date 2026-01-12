"""Tests for LLM-based query compiler."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from scripts.query.llm_compiler import (
    build_user_prompt,
    load_cache,
    write_cache_entry,
    compile_query_llm,
    CACHE_PATH,
)
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.exceptions import QueryCompilationError


class TestBuildUserPrompt:
    """Tests for user prompt builder."""

    def test_simple_query(self):
        """Should format query text into prompt."""
        query = "books published by Oxford"
        prompt = build_user_prompt(query)
        assert "Parse this query" in prompt
        assert query in prompt


class TestCacheOperations:
    """Tests for cache read/write operations."""

    def test_load_empty_cache(self, tmp_path):
        """Should return empty dict if cache doesn't exist."""
        with patch('scripts.query.llm_compiler.CACHE_PATH', tmp_path / "nonexistent.jsonl"):
            cache = load_cache()
            assert cache == {}

    def test_load_valid_cache(self, tmp_path):
        """Should load cache entries from JSONL."""
        cache_file = tmp_path / "cache.jsonl"

        # Write test entries
        entries = [
            {
                "query_text": "test query 1",
                "plan": {"query_text": "test query 1", "filters": []},
                "model": "gpt-4o",
                "timestamp": "2024-01-01T00:00:00Z"
            },
            {
                "query_text": "test query 2",
                "plan": {"query_text": "test query 2", "filters": []},
                "model": "gpt-4o",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        ]

        with open(cache_file, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            cache = load_cache()
            assert len(cache) == 2
            assert "test query 1" in cache
            assert "test query 2" in cache

    def test_load_malformed_cache(self, tmp_path):
        """Should skip malformed entries."""
        cache_file = tmp_path / "cache.jsonl"

        with open(cache_file, 'w') as f:
            f.write('{"query_text": "valid", "plan": {}, "model": "gpt-4o"}\n')
            f.write('invalid json line\n')
            f.write('{"missing_query_text": true}\n')
            f.write('{"query_text": "valid2", "plan": {}, "model": "gpt-4o"}\n')

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            cache = load_cache()
            # Should only load valid entries
            assert len(cache) == 2
            assert "valid" in cache
            assert "valid2" in cache

    def test_write_cache_entry(self, tmp_path):
        """Should append entry to cache file."""
        cache_file = tmp_path / "data" / "cache.jsonl"

        plan = QueryPlan(query_text="test query", filters=[])

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            write_cache_entry("test query", plan, "gpt-4o")

            # Verify file exists and contains entry
            assert cache_file.exists()
            with open(cache_file, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 1
                entry = json.loads(lines[0])
                assert entry["query_text"] == "test query"
                assert entry["model"] == "gpt-4o"
                assert "timestamp" in entry

    def test_write_cache_creates_directory(self, tmp_path):
        """Should create parent directories if needed."""
        cache_file = tmp_path / "deep" / "nested" / "cache.jsonl"

        plan = QueryPlan(query_text="test", filters=[])

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            write_cache_entry("test", plan, "gpt-4o")
            assert cache_file.exists()


class TestCompileQueryLLM:
    """Tests for main compile_query_llm function."""

    def test_cache_hit(self, tmp_path):
        """Should return cached plan without calling LLM."""
        cache_file = tmp_path / "cache.jsonl"

        # Setup cache with existing entry
        cached_plan = {
            "query_text": "cached query",
            "filters": [
                {"field": "publisher", "op": "EQUALS", "value": "oxford"}
            ]
        }

        cache_entry = {
            "query_text": "cached query",
            "plan": cached_plan,
            "model": "gpt-4o",
            "timestamp": "2024-01-01T00:00:00Z"
        }

        with open(cache_file, 'w') as f:
            f.write(json.dumps(cache_entry) + '\n')

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            # Should not call OpenAI
            plan = compile_query_llm("cached query", api_key="fake-key")

            assert plan.query_text == "cached query"
            assert len(plan.filters) == 1
            assert plan.debug.get("cache_hit") is True

    def test_cache_hit_with_limit_override(self, tmp_path):
        """Should use cached plan but override limit."""
        cache_file = tmp_path / "cache.jsonl"

        cached_plan = {
            "query_text": "test",
            "filters": [],
            "limit": 10
        }

        cache_entry = {
            "query_text": "test",
            "plan": cached_plan,
            "model": "gpt-4o",
            "timestamp": "2024-01-01T00:00:00Z"
        }

        with open(cache_file, 'w') as f:
            f.write(json.dumps(cache_entry) + '\n')

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            plan = compile_query_llm("test", limit=50, api_key="fake-key")

            assert plan.limit == 50  # Should override cached limit

    def test_missing_api_key(self):
        """Should raise QueryCompilationError if API key not provided."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(QueryCompilationError, match="OpenAI API key not found"):
                compile_query_llm("test query")

    @patch('scripts.query.llm_compiler.OpenAI')
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_successful_llm_call(self, mock_write_cache, mock_openai_class, tmp_path):
        """Should call LLM and cache result on cache miss."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.touch()

        # Mock OpenAI client and response
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Mock successful parse response
        mock_response = Mock()
        mock_plan = QueryPlan(
            query_text="test query",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
            ]
        )
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            plan = compile_query_llm("test query", api_key="test-key", model="gpt-4o")

            # Verify LLM was called
            mock_client.responses.parse.assert_called_once()
            call_args = mock_client.responses.parse.call_args
            assert call_args.kwargs["model"] == "gpt-4o"

            # Verify plan structure
            assert plan.query_text == "test query"
            assert len(plan.filters) == 1
            assert plan.debug["parser"] == "llm"
            assert plan.debug["model"] == "gpt-4o"
            assert plan.debug["cache_hit"] is False

            # Verify cache was written
            mock_write_cache.assert_called_once()

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_llm_error_handling(self, mock_openai_class, tmp_path):
        """Should raise QueryCompilationError on unexpected LLM failure."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock OpenAI client that raises unexpected exception
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.responses.parse.side_effect = Exception("Unexpected API Error")

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError, match="OpenAI returned invalid response"):
                compile_query_llm("test query", api_key="test-key")

    @patch('scripts.query.llm_compiler.OpenAI')
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_cache_write_failure_doesnt_block(self, mock_write_cache, mock_openai_class, tmp_path):
        """Should not fail if cache write fails."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock successful LLM call
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_response = Mock()
        mock_plan = QueryPlan(query_text="test", filters=[])
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        # Mock cache write failure
        mock_write_cache.side_effect = IOError("Disk full")

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            # Should not raise exception
            plan = compile_query_llm("test", api_key="test-key")
            assert plan is not None

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_limit_parameter(self, mock_openai_class, tmp_path):
        """Should apply limit parameter to generated plan."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_response = Mock()
        mock_plan = QueryPlan(query_text="test", filters=[])
        mock_response.output_parsed = mock_plan
        mock_client.responses.parse.return_value = mock_response

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with patch('scripts.query.llm_compiler.write_cache_entry'):
                plan = compile_query_llm("test", limit=100, api_key="test-key")

                assert plan.limit == 100

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_authentication_error(self, mock_openai_class, tmp_path):
        """Should raise QueryCompilationError with helpful message on invalid API key."""
        from openai import AuthenticationError

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock OpenAI client that raises AuthenticationError
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.responses.parse.side_effect = AuthenticationError(
            message="Invalid API key",
            response=Mock(status_code=401),
            body=None
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="invalid-key")

            error_msg = str(exc_info.value)
            assert "OpenAI API error" in error_msg
            assert "AuthenticationError" in error_msg
            assert "Invalid or expired API key" in error_msg

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_rate_limit_error(self, mock_openai_class, tmp_path):
        """Should raise QueryCompilationError with helpful message on rate limiting."""
        from openai import RateLimitError

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock OpenAI client that raises RateLimitError
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.responses.parse.side_effect = RateLimitError(
            message="Rate limit exceeded",
            response=Mock(status_code=429),
            body=None
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "OpenAI API error" in error_msg
            assert "RateLimitError" in error_msg
            assert "Rate limiting" in error_msg

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_api_timeout_error(self, mock_openai_class, tmp_path):
        """Should raise QueryCompilationError with helpful message on timeout."""
        from openai import APITimeoutError

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock OpenAI client that raises APITimeoutError
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.responses.parse.side_effect = APITimeoutError(request=Mock())

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "OpenAI API error" in error_msg
            assert "APITimeoutError" in error_msg
            assert "Network timeout" in error_msg

    @patch('scripts.query.llm_compiler.OpenAI')
    def test_general_api_error(self, mock_openai_class, tmp_path):
        """Should raise QueryCompilationError on general API errors."""
        from openai import APIError

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock OpenAI client that raises APIError
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.responses.parse.side_effect = APIError(
            message="Service unavailable",
            request=Mock(),
            body=None
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "OpenAI API error" in error_msg
            assert "APIError" in error_msg


class TestIntegration:
    """Integration tests (require OPENAI_API_KEY to be set)."""

    @pytest.mark.integration
    def test_real_api_call(self):
        """Test with real OpenAI API (requires API key, run with pytest -m integration)."""
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        plan = compile_query_llm("books published by Oxford between 1500 and 1599")

        assert plan.query_text == "books published by Oxford between 1500 and 1599"
        assert len(plan.filters) >= 2  # Should have publisher and year filters
        assert plan.debug["parser"] == "llm"
        assert plan.debug["model"] == "gpt-4o"
