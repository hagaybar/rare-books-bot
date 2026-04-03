"""POST /chat/compare -- run same query through multiple model configs side-by-side.

Uses per-pipeline metric tracking instead of the global token_accumulator,
since parallel asyncio.gather() calls share the same thread and would
reset each other's accumulator.
"""

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
from scripts.models.llm_client import _call_metrics

logger = logging.getLogger(__name__)


async def _run_pipeline_with_config(
    message: str,
    config: ModelPair,
    db_path: str,
    token_saving: bool,
) -> ComparisonResult:
    """Run the full scholar pipeline with a specific model configuration."""
    start = time.monotonic()
    _call_metrics.clear()

    try:
        plan = await interpret(message, model=config.interpreter)
        exec_result = execute_plan(plan, db_path=Path(db_path))
        scholar_resp = await narrate(
            message, exec_result,
            model=config.narrator,
            token_saving=token_saving,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        total_input = sum(m.get("input_tokens", 0) for m in _call_metrics)
        total_output = sum(m.get("output_tokens", 0) for m in _call_metrics)
        total_cost = sum(m.get("cost_usd", 0.0) for m in _call_metrics)

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
                cost_usd=round(total_cost, 4),
                tokens={
                    "input": total_input,
                    "output": total_output,
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
    """Run the comparison -- sequentially to get accurate per-config metrics.

    We run sequentially rather than parallel because the metric collection
    (_call_metrics list) is module-global and would intermingle across
    concurrent pipelines on the same event loop thread.
    """
    results = []
    for cfg in request.configs:
        result = await _run_pipeline_with_config(
            request.message, cfg, db_path, request.token_saving
        )
        results.append(result)
    return CompareResponse(comparisons=results)
