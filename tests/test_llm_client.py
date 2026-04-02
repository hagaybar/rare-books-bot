"""Tests for the LLM client wrapper.

These test the wrapper logic (schema conversion, response parsing)
without making actual API calls — litellm.acompletion is mocked.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from scripts.models.llm_client import (
    LLMResult,
    structured_completion,
    streaming_completion,
    pydantic_to_response_format,
)


class SampleSchema(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


def test_pydantic_to_response_format():
    """Converts Pydantic model to JSON schema dict for response_format."""
    fmt = pydantic_to_response_format(SampleSchema)
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "SampleSchema"
    assert "properties" in fmt["json_schema"]["schema"]
    assert "answer" in fmt["json_schema"]["schema"]["properties"]


@pytest.mark.asyncio
async def test_structured_completion_parses_response():
    """structured_completion() calls litellm and parses the Pydantic model."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"answer": "hello", "confidence": 0.9})

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.model = "gpt-4.1"

    with patch("scripts.models.llm_client.litellm") as mock_litellm, \
         patch("scripts.models.llm_client.log_llm_call"):
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm.completion_cost.return_value = 0.001

        result = await structured_completion(
            model="gpt-4.1",
            system="You are helpful.",
            user="Say hello.",
            response_schema=SampleSchema,
        )

    assert isinstance(result, LLMResult)
    assert isinstance(result.parsed, SampleSchema)
    assert result.parsed.answer == "hello"
    assert result.parsed.confidence == 0.9
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cost_usd == 0.001


@pytest.mark.asyncio
async def test_structured_completion_passes_model_to_litellm():
    """The model string is passed through to litellm.acompletion()."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"answer": "hi", "confidence": 0.5})

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.model = "anthropic/claude-sonnet-4-6"

    with patch("scripts.models.llm_client.litellm") as mock_litellm, \
         patch("scripts.models.llm_client.log_llm_call"):
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)
        mock_litellm.completion_cost.return_value = 0.002

        await structured_completion(
            model="anthropic/claude-sonnet-4-6",
            system="sys",
            user="usr",
            response_schema=SampleSchema,
        )

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"
