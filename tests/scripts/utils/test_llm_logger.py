"""Tests for LLM logger utility.

Verifies logging of LLM API calls with cost tracking and prompt capture.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from scripts.utils.llm_logger import (
    LLMLogger,
    log_llm_call,
    get_llm_logger,
    PRICING_PER_1M_TOKENS,
)


@pytest.fixture
def temp_log_path(tmp_path):
    """Create temporary log file path."""
    return tmp_path / "test_llm_calls.jsonl"


@pytest.fixture
def mock_response():
    """Create mock OpenAI response with usage stats."""
    response = MagicMock()
    response.usage = MagicMock()
    response.usage.input_tokens = 1000
    response.usage.output_tokens = 500
    return response


@pytest.fixture
def mock_response_no_usage():
    """Create mock OpenAI response without usage stats."""
    response = MagicMock()
    response.usage = None
    return response


class TestLLMLogger:
    """Tests for LLMLogger class."""

    def test_init_creates_log_directory(self, tmp_path):
        """Test that LLMLogger creates log directory if it doesn't exist."""
        log_path = tmp_path / "subdir" / "llm_calls.jsonl"
        logger = LLMLogger(log_path=log_path)

        assert log_path.parent.exists()

    def test_calculate_cost_gpt4o(self):
        """Test cost calculation for gpt-4o model."""
        logger = LLMLogger()

        # 1000 input tokens, 500 output tokens
        # gpt-4o: $2.50/1M input, $10.00/1M output
        # Expected: (1000 * 2.50 / 1_000_000) + (500 * 10.00 / 1_000_000)
        #         = 0.0025 + 0.005 = 0.0075
        cost = logger._calculate_cost("gpt-4o", 1000, 500)

        assert cost == 0.0075

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model returns 0."""
        logger = LLMLogger()

        cost = logger._calculate_cost("unknown-model", 1000, 500)

        assert cost == 0.0

    def test_truncate_short_text(self):
        """Test truncate doesn't modify short text."""
        logger = LLMLogger()

        result = logger._truncate("short text", 100)

        assert result == "short text"

    def test_truncate_long_text(self):
        """Test truncate adds ellipsis to long text."""
        logger = LLMLogger()

        result = logger._truncate("this is a very long text", 10)

        assert result == "this is a ..."
        assert len(result) == 13  # 10 + 3 for "..."

    def test_log_call_writes_to_file(self, temp_log_path, mock_response):
        """Test that log_call writes entry to JSONL file."""
        logger = LLMLogger(log_path=temp_log_path)

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt="You are a test assistant.",
            user_prompt="Test query",
            response=mock_response,
        )

        # Verify file was written
        assert temp_log_path.exists()

        # Read and parse the log entry
        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["call_type"] == "test_call"
        assert entry["model"] == "gpt-4o"
        assert entry["usage"]["input_tokens"] == 1000
        assert entry["usage"]["output_tokens"] == 500
        assert entry["usage"]["total_tokens"] == 1500
        assert entry["cost_usd"] == 0.0075

    def test_log_call_full_prompts(self, temp_log_path, mock_response):
        """Test that log_call captures full prompts when enabled."""
        logger = LLMLogger(log_path=temp_log_path, log_full_prompts=True)

        system_prompt = "System prompt content"
        user_prompt = "User prompt content"

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=mock_response,
        )

        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["prompts"]["system"] == system_prompt
        assert entry["prompts"]["user"] == user_prompt

    def test_log_call_preview_prompts(self, temp_log_path, mock_response):
        """Test that log_call captures prompt previews when full prompts disabled."""
        logger = LLMLogger(
            log_path=temp_log_path,
            log_full_prompts=False,
            preview_length=10,
        )

        system_prompt = "This is a very long system prompt"
        user_prompt = "This is a very long user prompt"

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response=mock_response,
        )

        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert "system_preview" in entry["prompts"]
        assert "user_preview" in entry["prompts"]
        assert entry["prompts"]["system_preview"].endswith("...")
        assert "system" not in entry["prompts"]

    def test_log_call_with_session_id(self, temp_log_path, mock_response):
        """Test that log_call captures session_id."""
        logger = LLMLogger(log_path=temp_log_path)

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
            session_id="session-123",
        )

        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["session_id"] == "session-123"

    def test_log_call_with_extra_metadata(self, temp_log_path, mock_response):
        """Test that log_call captures extra metadata."""
        logger = LLMLogger(log_path=temp_log_path)

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
            extra_metadata={"query_text": "test query", "filter_count": 3},
        )

        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["metadata"]["query_text"] == "test query"
        assert entry["metadata"]["filter_count"] == 3

    def test_log_call_without_usage(self, temp_log_path, mock_response_no_usage):
        """Test that log_call handles response without usage stats."""
        logger = LLMLogger(log_path=temp_log_path)

        logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response_no_usage,
        )

        with open(temp_log_path) as f:
            entry = json.loads(f.readline())

        assert entry["usage"]["input_tokens"] == 0
        assert entry["usage"]["output_tokens"] == 0
        assert entry["cost_usd"] == 0.0

    def test_log_call_returns_entry(self, temp_log_path, mock_response):
        """Test that log_call returns the log entry."""
        logger = LLMLogger(log_path=temp_log_path)

        entry = logger.log_call(
            call_type="test_call",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
        )

        assert entry["call_type"] == "test_call"
        assert entry["model"] == "gpt-4o"


class TestGetSessionCosts:
    """Tests for session cost tracking."""

    def test_get_session_costs_empty_file(self, temp_log_path):
        """Test get_session_costs with no log file."""
        logger = LLMLogger(log_path=temp_log_path)

        result = logger.get_session_costs("session-123")

        assert result["total_cost"] == 0
        assert result["total_tokens"] == 0
        assert result["call_count"] == 0

    def test_get_session_costs_with_entries(self, temp_log_path, mock_response):
        """Test get_session_costs sums up session entries."""
        logger = LLMLogger(log_path=temp_log_path)

        # Log multiple calls for same session
        logger.log_call(
            call_type="test1",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
            session_id="session-123",
        )
        logger.log_call(
            call_type="test2",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
            session_id="session-123",
        )
        # Different session
        logger.log_call(
            call_type="test3",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
            session_id="session-456",
        )

        result = logger.get_session_costs("session-123")

        assert result["call_count"] == 2
        assert result["total_tokens"] == 3000  # 1500 * 2
        assert result["total_cost"] == 0.015  # 0.0075 * 2


class TestGetSummary:
    """Tests for summary statistics."""

    def test_get_summary_empty_file(self, temp_log_path):
        """Test get_summary with no log file."""
        logger = LLMLogger(log_path=temp_log_path)

        result = logger.get_summary(hours=24)

        assert result["total_cost"] == 0
        assert result["total_tokens"] == 0
        assert result["call_count"] == 0
        assert result["by_type"] == {}

    def test_get_summary_groups_by_type(self, temp_log_path, mock_response):
        """Test get_summary groups by call type."""
        logger = LLMLogger(log_path=temp_log_path)

        # Log different call types
        logger.log_call(
            call_type="intent_interpretation",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
        )
        logger.log_call(
            call_type="intent_interpretation",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
        )
        logger.log_call(
            call_type="query_compilation",
            model="gpt-4o",
            system_prompt="test",
            user_prompt="test",
            response=mock_response,
        )

        result = logger.get_summary(hours=24)

        assert result["call_count"] == 3
        assert "intent_interpretation" in result["by_type"]
        assert "query_compilation" in result["by_type"]
        assert result["by_type"]["intent_interpretation"]["count"] == 2
        assert result["by_type"]["query_compilation"]["count"] == 1


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_llm_logger_singleton(self):
        """Test that get_llm_logger returns same instance."""
        logger1 = get_llm_logger()
        logger2 = get_llm_logger()

        assert logger1 is logger2

    @patch("scripts.utils.llm_logger._llm_logger", None)
    def test_log_llm_call_uses_global_logger(self, mock_response, tmp_path):
        """Test that log_llm_call uses global logger."""
        # Reset global logger
        import scripts.utils.llm_logger as llm_logger_module
        llm_logger_module._llm_logger = None

        with patch.object(LLMLogger, 'log_call', return_value={}) as mock_log:
            log_llm_call(
                call_type="test",
                model="gpt-4o",
                system_prompt="test",
                user_prompt="test",
                response=mock_response,
            )

            mock_log.assert_called_once()
