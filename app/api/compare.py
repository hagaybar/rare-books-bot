"""POST /chat/compare -- run same query through multiple model configs side-by-side."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from app.api.models import (
    CompareRequest,
    CompareResponse,
    ComparisonResult,
    ComparisonMetrics,
    ModelPair,
)
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan
from scripts.chat.narrator import narrate
from scripts.chat.models import ChatResponse, ConversationPhase
from scripts.utils.llm_logger import token_accumulator

logger = logging.getLogger(__name__)


async def _run_pipeline_with_config(
    message: str,
    config: ModelPair,
    db_path: str,
    token_saving: bool,
) -> ComparisonResult:
    """Run the full scholar pipeline with a specific model configuration."""
    start = time.monotonic()
    token_accumulator.reset()

    try:
        plan = await interpret(message, model=config.interpreter)
        exec_result = execute_plan(plan, db_path=Path(db_path))
        scholar_resp = await narrate(
            message, exec_result,
            model=config.narrator,
            token_saving=token_saving,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        breakdown = token_accumulator.get_breakdown()

        response = ChatResponse(
            message=scholar_resp.narrative,
            candidate_set=None,
            suggested_followups=scholar_resp.suggested_followups,
            clarification_needed=None,
            session_id="compare",
            phase=ConversationPhase.QUERY_DEFINITION,
            confidence=scholar_resp.confidence,
            metadata={"model_config": {"interpreter": config.interpreter, "narrator": config.narrator}},
        )

        return ComparisonResult(
            config=config,
            response=response,
            metrics=ComparisonMetrics(
                latency_ms=latency_ms,
                cost_usd=round(breakdown.get("cost_usd", 0), 4),
                tokens={
                    "input": breakdown.get("input_tokens", 0),
                    "output": breakdown.get("output_tokens", 0),
                },
            ),
        )
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Compare pipeline failed for config %s", config)
        return ComparisonResult(
            config=config,
            response=None,
            metrics=ComparisonMetrics(latency_ms=latency_ms, cost_usd=0, tokens={"input": 0, "output": 0}),
            error=str(e),
        )


async def run_comparison(
    request: CompareRequest,
    db_path: str,
) -> CompareResponse:
    """Run the comparison -- all configs in parallel."""
    tasks = [
        _run_pipeline_with_config(request.message, cfg, db_path, request.token_saving)
        for cfg in request.configs
    ]
    results = await asyncio.gather(*tasks)
    return CompareResponse(comparisons=list(results))
