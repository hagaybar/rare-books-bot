"""Thin async wrapper around litellm for structured and streaming completions.

Replaces direct OpenAI client calls throughout the codebase. All LLM calls
go through this module, making model switching a config change.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Type, TypeVar

import litellm
from pydantic import BaseModel

from scripts.utils.llm_logger import log_llm_call

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResult:
    """Result from a structured LLM completion."""
    parsed: Any  # The parsed Pydantic model instance
    raw_content: str  # Raw JSON string from the LLM
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    response: Any  # The raw litellm response object


def pydantic_to_response_format(schema: Type[BaseModel]) -> dict:
    """Convert a Pydantic model to a JSON schema dict for litellm response_format.

    This explicit conversion is more reliable across providers than passing
    the Pydantic class directly.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": schema.model_json_schema(),
            "name": schema.__name__,
            "strict": True,
        },
    }


async def structured_completion(
    model: str,
    system: str,
    user: str,
    response_schema: Type[T],
    call_type: str = "unknown",
    extra_metadata: Optional[dict] = None,
) -> LLMResult:
    """Run a structured completion via litellm, returning a parsed Pydantic model.

    Args:
        model: LiteLLM model string (e.g., "gpt-4.1", "anthropic/claude-sonnet-4-6")
        system: System prompt
        user: User prompt
        response_schema: Pydantic model class for structured output
        call_type: Label for logging (e.g., "scholar_interpreter", "narrator")
        extra_metadata: Additional metadata for the log entry

    Returns:
        LLMResult with the parsed model, token usage, cost, and latency.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    start = time.monotonic()
    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        response_format=pydantic_to_response_format(response_schema),
    )
    latency_ms = (time.monotonic() - start) * 1000

    raw_content = resp.choices[0].message.content
    parsed = response_schema.model_validate_json(raw_content)

    input_tokens = resp.usage.prompt_tokens
    output_tokens = resp.usage.completion_tokens
    try:
        cost = litellm.completion_cost(completion_response=resp)
    except Exception:
        cost = 0.0
        logger.debug("litellm.completion_cost() failed for model %s", model)

    log_llm_call(
        call_type=call_type,
        model=model,
        system_prompt=system,
        user_prompt=user,
        response=resp,
        extra_metadata=extra_metadata,
    )

    return LLMResult(
        parsed=parsed,
        raw_content=raw_content,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        response=resp,
    )


async def streaming_completion(
    model: str,
    system: str,
    user: str,
    call_type: str = "unknown",
    extra_metadata: Optional[dict] = None,
) -> AsyncIterator[str]:
    """Stream a plain-text completion via litellm.

    Yields text chunks as they arrive. Does not support structured output
    (streaming and structured parsing are incompatible).

    Usage:
        async for chunk in streaming_completion(model, system, user):
            await send_to_client(chunk)
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    response = await litellm.acompletion(
        model=model,
        messages=messages,
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
