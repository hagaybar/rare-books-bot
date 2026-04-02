"""Tests for LLM-based query compiler.

After litellm migration, tests mock structured_completion instead of OpenAI directly.
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock

from scripts.query.llm_compiler import (
    build_user_prompt,
    load_cache,
    write_cache_entry,
    compile_query_llm,
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


def _make_mock_llm_result(plan: QueryPlan):
    """Build a mock LLMResult returned by structured_completion."""
    from scripts.query.llm_compiler import QueryPlanLLM

    llm_plan = QueryPlanLLM(
        version=plan.version,
        query_text=plan.query_text,
        filters=plan.filters,
        soft_filters=plan.soft_filters,
        limit=plan.limit,
    )

    mock_result = Mock()
    mock_result.parsed = llm_plan
    mock_result.raw_content = plan.model_dump_json()
    mock_result.model = "gpt-4o"
    mock_result.input_tokens = 100
    mock_result.output_tokens = 50
    mock_result.cost_usd = 0.001
    mock_result.latency_ms = 500
    return mock_result


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
            # Should not call LLM
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

    @patch('scripts.query.llm_compiler.load_cache')
    def test_missing_api_key_no_longer_checked(self, mock_load_cache):
        """With litellm, API key is handled by the provider, not by us.

        The function should proceed to call the LLM (which will fail
        at the litellm level if no key is configured). We mock call_model
        to avoid an actual API call.
        """
        mock_load_cache.return_value = {}  # Empty cache, no cache hit
        # Mock call_model to simulate a litellm auth error
        with patch('scripts.query.llm_compiler.call_model', new_callable=AsyncMock) as mock_cm:
            import litellm
            mock_cm.side_effect = litellm.AuthenticationError(
                message="No API key",
                llm_provider="openai",
                model="gpt-4o",
            )
            with pytest.raises(QueryCompilationError):
                compile_query_llm("test query")

    @patch('scripts.query.llm_compiler.structured_completion', new_callable=AsyncMock)
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_successful_llm_call(self, mock_write_cache, mock_structured, tmp_path):
        """Should call LLM and cache result on cache miss."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.touch()

        # Build mock LLMResult
        plan_data = QueryPlan(
            query_text="test query",
            filters=[
                Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
            ]
        )
        mock_structured.return_value = _make_mock_llm_result(plan_data)

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            plan = compile_query_llm("test query", api_key="test-key", model="gpt-4o")

            # Verify LLM was called
            mock_structured.assert_called_once()
            call_kwargs = mock_structured.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"

            # Verify plan structure
            assert plan.query_text == "test query"
            assert len(plan.filters) == 1
            assert plan.debug["parser"] == "llm"
            assert plan.debug["model"] == "gpt-4o"
            assert plan.debug["cache_hit"] is False

            # Verify cache was written
            mock_write_cache.assert_called_once()

    @patch('scripts.query.llm_compiler.structured_completion', new_callable=AsyncMock)
    def test_llm_error_handling(self, mock_structured, tmp_path):
        """Should raise QueryCompilationError on unexpected LLM failure."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_structured.side_effect = Exception("Unexpected API Error")

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError, match="invalid response"):
                compile_query_llm("test query", api_key="test-key")

    @patch('scripts.query.llm_compiler.structured_completion', new_callable=AsyncMock)
    @patch('scripts.query.llm_compiler.write_cache_entry')
    def test_cache_write_failure_doesnt_block(self, mock_write_cache, mock_structured, tmp_path):
        """Should not fail if cache write fails."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        # Mock successful LLM call
        plan_data = QueryPlan(query_text="test", filters=[])
        mock_structured.return_value = _make_mock_llm_result(plan_data)

        # Mock cache write failure
        mock_write_cache.side_effect = IOError("Disk full")

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            # Should not raise exception
            plan = compile_query_llm("test", api_key="test-key")
            assert plan is not None

    @patch('scripts.query.llm_compiler.structured_completion', new_callable=AsyncMock)
    def test_limit_parameter(self, mock_structured, tmp_path):
        """Should apply limit parameter to generated plan."""
        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        plan_data = QueryPlan(query_text="test", filters=[])
        mock_structured.return_value = _make_mock_llm_result(plan_data)

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with patch('scripts.query.llm_compiler.write_cache_entry'):
                plan = compile_query_llm("test", limit=100, api_key="test-key")

                assert plan.limit == 100

    @patch('scripts.query.llm_compiler.call_model', new_callable=AsyncMock)
    def test_authentication_error(self, mock_call_model, tmp_path):
        """Should raise QueryCompilationError with helpful message on auth failure."""
        import litellm

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_call_model.side_effect = litellm.AuthenticationError(
            message="Invalid API key",
            llm_provider="openai",
            model="gpt-4o",
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="invalid-key")

            error_msg = str(exc_info.value)
            assert "API error" in error_msg

    @patch('scripts.query.llm_compiler.call_model', new_callable=AsyncMock)
    def test_rate_limit_error(self, mock_call_model, tmp_path):
        """Should raise QueryCompilationError with helpful message on rate limiting."""
        import litellm

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_call_model.side_effect = litellm.RateLimitError(
            message="Rate limit exceeded",
            llm_provider="openai",
            model="gpt-4o",
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "API error" in error_msg

    @patch('scripts.query.llm_compiler.call_model', new_callable=AsyncMock)
    def test_api_timeout_error(self, mock_call_model, tmp_path):
        """Should raise QueryCompilationError with helpful message on timeout."""
        import litellm

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_call_model.side_effect = litellm.Timeout(
            message="Request timed out",
            llm_provider="openai",
            model="gpt-4o",
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "API error" in error_msg

    @patch('scripts.query.llm_compiler.call_model', new_callable=AsyncMock)
    def test_general_api_error(self, mock_call_model, tmp_path):
        """Should raise QueryCompilationError on general API errors."""
        import litellm

        cache_file = tmp_path / "cache.jsonl"
        cache_file.touch()

        mock_call_model.side_effect = litellm.APIError(
            message="Service unavailable",
            llm_provider="openai",
            model="gpt-4o",
            status_code=500,
        )

        with patch('scripts.query.llm_compiler.CACHE_PATH', cache_file):
            with pytest.raises(QueryCompilationError) as exc_info:
                compile_query_llm("test query", api_key="test-key")

            error_msg = str(exc_info.value)
            assert "API error" in error_msg


class TestIntegration:
    """Integration tests (require API key to be set)."""

    @pytest.mark.integration
    def test_real_api_call(self):
        """Test with real LLM API (requires API key, run with pytest -m integration)."""
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        plan = compile_query_llm("books published by Oxford between 1500 and 1599")

        assert plan.query_text == "books published by Oxford between 1500 and 1599"
        assert len(plan.filters) >= 2  # Should have publisher and year filters
        assert plan.debug["parser"] == "llm"
        assert plan.debug["model"] == "gpt-4o"
