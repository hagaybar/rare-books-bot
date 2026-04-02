"""Batch evaluation CLI — run queries through multiple models and score results.

Usage:
    python3 scripts/eval/run_eval.py \
        --models gpt-4.1,gpt-4.1-mini,gpt-5-mini \
        --stages interpreter,narrator \
        --queries data/eval/queries.json \
        --judge-model gpt-4.1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.eval.query_set import load_query_set, validate_query_set, EvalQuery
from scripts.eval.judge import score_interpreter, score_narrator
from scripts.eval.report import generate_report
from scripts.models.llm_client import structured_completion
from scripts.models.config import load_config

logger = logging.getLogger(__name__)


async def evaluate_interpreter(
    query: EvalQuery,
    model: str,
    db_path: str,
) -> dict[str, Any]:
    """Run interpreter for a single query x model and return raw result."""
    from scripts.chat.interpreter import interpret

    start = time.monotonic()
    try:
        plan = await interpret(query.query, model=model)
        latency_ms = (time.monotonic() - start) * 1000

        # Extract filters from plan for scoring
        filters_produced = {}
        for step in plan.execution_steps:
            if hasattr(step.params, 'filters'):
                for f in step.params.filters:
                    filters_produced[f.field.value if hasattr(f.field, 'value') else str(f.field)] = f.value

        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": True,
            "latency_ms": round(latency_ms),
            "plan": {
                "intents": plan.intents,
                "execution_steps": [
                    {"action": s.action.value if hasattr(s.action, 'value') else str(s.action),
                     "label": s.label}
                    for s in plan.execution_steps
                ],
                "filters_produced": filters_produced,
                "confidence": plan.confidence,
            },
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "query_id": query.id,
            "model": model,
            "stage": "interpreter",
            "success": False,
            "latency_ms": round(latency_ms),
            "error": str(e),
        }


async def evaluate_narrator(
    query: EvalQuery,
    model: str,
    db_path: str,
) -> dict[str, Any]:
    """Run full pipeline (interpret + execute + narrate) for a query x narrator model."""
    from scripts.chat.interpreter import interpret
    from scripts.chat.executor import execute
    from scripts.chat.narrator import narrate

    start = time.monotonic()
    try:
        # Use default interpreter model, only vary narrator
        plan = await interpret(query.query)
        exec_result = await execute(plan, db_path=db_path)
        scholar_resp = await narrate(query.query, exec_result, model=model)
        latency_ms = (time.monotonic() - start) * 1000

        # Summarize grounding for judge
        grounding_summary = ""
        if exec_result.grounding:
            records = exec_result.grounding.records[:10]
            grounding_summary = "\n".join(
                f"- {r.title} ({r.date_display}, {r.place})" for r in records
            )

        return {
            "query_id": query.id,
            "model": model,
            "stage": "narrator",
            "success": True,
            "latency_ms": round(latency_ms),
            "narrative": scholar_resp.narrative,
            "grounding_summary": grounding_summary,
            "confidence": scholar_resp.confidence,
            "followups": scholar_resp.suggested_followups,
        }
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "query_id": query.id,
            "model": model,
            "stage": "narrator",
            "success": False,
            "latency_ms": round(latency_ms),
            "error": str(e),
        }


async def run_evaluation(
    queries: list[EvalQuery],
    models: list[str],
    stages: list[str],
    judge_model: str,
    db_path: str,
) -> list[dict[str, Any]]:
    """Run full evaluation: all queries x models x stages, then score."""
    results: list[dict[str, Any]] = []

    total = len(queries) * len(models) * len(stages)
    done = 0

    for query in queries:
        for model in models:
            for stage in stages:
                done += 1
                print(f"  [{done}/{total}] {query.id} x {model} x {stage}")

                if stage == "interpreter":
                    result = await evaluate_interpreter(query, model, db_path)
                elif stage == "narrator":
                    result = await evaluate_narrator(query, model, db_path)
                else:
                    continue

                # Score successful results
                if result.get("success"):
                    try:
                        if stage == "interpreter":
                            score = await score_interpreter(
                                query, result["plan"], judge_model=judge_model,
                            )
                            result["score_combined"] = score.combined
                            result["score_detail"] = {
                                "intent_match": score.intent_match,
                                "filter_overlap": score.filter_overlap,
                                "step_quality": score.step_quality,
                                "justification": score.justification,
                            }
                        elif stage == "narrator":
                            score = await score_narrator(
                                query,
                                result["narrative"],
                                result.get("grounding_summary", ""),
                                judge_model=judge_model,
                            )
                            result["score_combined"] = score.combined
                            result["score_detail"] = {
                                "accuracy": score.accuracy,
                                "completeness": score.completeness,
                                "scholarly_tone": score.scholarly_tone,
                                "conciseness": score.conciseness,
                                "justification": score.justification,
                            }
                    except Exception as e:
                        logger.warning("Scoring failed for %s x %s: %s", query.id, model, e)
                        result["score_combined"] = 0
                        result["score_error"] = str(e)

                results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Batch model evaluation")
    parser.add_argument("--models", required=True, help="Comma-separated model list")
    parser.add_argument("--stages", default="interpreter,narrator", help="Comma-separated stages")
    parser.add_argument("--queries", default="data/eval/queries.json", help="Query set JSON file")
    parser.add_argument("--judge-model", default=None, help="Model for LLM judge (default: from config)")
    parser.add_argument("--db-path", default="data/index/bibliographic.db", help="Database path")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: auto-generated)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    models = [m.strip() for m in args.models.split(",")]
    stages = [s.strip() for s in args.stages.split(",")]
    queries = load_query_set(Path(args.queries))

    # Validate query set
    warnings = validate_query_set(queries)
    for w in warnings:
        print(f"  WARNING: {w}")

    judge_model = args.judge_model
    if judge_model is None:
        config = load_config()
        judge_model = config.judge.model

    output_dir = Path(args.output_dir) if args.output_dir else Path(
        f"data/eval/runs/{datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M%S')}"
    )

    print(f"\nEvaluation: {len(queries)} queries x {len(models)} models x {len(stages)} stages")
    print(f"Judge model: {judge_model}")
    print(f"Output: {output_dir}\n")

    results = asyncio.run(run_evaluation(queries, models, stages, judge_model, args.db_path))

    report_dir = generate_report(results, output_dir)
    print(f"\nReport saved to {report_dir}/")
    print(f"  - results.json ({len(results)} entries)")
    print(f"  - scores.json (aggregated)")
    print(f"  - human_review.csv (fill in human_score column)")
    print(f"  - summary.md (readable table)")


if __name__ == "__main__":
    main()
