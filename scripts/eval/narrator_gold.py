"""Narrator gold-standard evaluation: fixtures, pricing, batch request builders.

Pure functions only — no network, no LLM calls. The batch I/O lives in
scripts/eval/batch_client.py; orchestration in run_narrator_gold_eval.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from scripts.chat.narrator import (
    NARRATOR_SYSTEM_PROMPT,
    NarratorResponseLLM,
    build_lean_narrator_prompt,
)
from scripts.chat.plan_models import ExecutionResult
from scripts.eval.judge import NarratorGoldJudgment, build_gold_judge_prompt
from scripts.models.llm_client import pydantic_to_response_format

# Prices in USD per 1M tokens (input, output). Source: OpenAI price list 2026-06.
# Batch API applies a flat 50% discount to both input and output.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5.1": (1.25, 10.00),
    "gpt-5.2": (1.75, 14.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.5": (5.00, 30.00),
}


def estimate_request_cost(model: str, input_tokens: int, max_output_tokens: int, batch: bool) -> float:
    """Upper-bound cost of one request: full input + output at the cap."""
    in_price, out_price = PRICING[model]
    cost = input_tokens * in_price / 1e6 + max_output_tokens * out_price / 1e6
    return cost * 0.5 if batch else cost


def estimate_batch_cost(requests: list[tuple[str, int, int]], batch: bool) -> float:
    """Sum estimate_request_cost over (model, input_tokens, max_output_tokens) triples."""
    return sum(estimate_request_cost(m, i, o, batch) for (m, i, o) in requests)


class CostCeilingExceeded(RuntimeError):
    """Raised when a batch's projected cost exceeds the configured ceiling."""


def estimate_tokens(text: str) -> int:
    """Heuristic token count for pre-submit estimation (~4 chars/token).

    Deliberately simple and model-agnostic — gpt-5.x encodings may be absent
    from local tokenizers. Used only for the ceiling guard's input estimate;
    output is bounded exactly by max_completion_tokens.
    """
    return math.floor(len(text) / 4)


def assert_within_ceiling(requests: list[tuple[str, int, int]], ceiling: float, batch: bool) -> float:
    """Project worst-case batch cost; raise CostCeilingExceeded if over ceiling.

    Returns the projected cost when within budget.
    """
    projected = estimate_batch_cost(requests, batch=batch)
    if projected > ceiling:
        raise CostCeilingExceeded(
            f"Projected ${projected:.4f} exceeds ceiling ${ceiling:.2f} ({len(requests)} requests, batch={batch})"
        )
    return projected


@dataclass
class GoldCase:
    """One gold fixture: query + frozen grounding + Opus-authored gold narrative."""

    case_id: str
    query: str
    grounding: ExecutionResult
    gold_markdown: str


def save_gold_case(root: Path, case: GoldCase) -> Path:
    """Write a case to <root>/<case_id>/ as query.txt, grounding.json, gold.md."""
    case_dir = root / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "query.txt").write_text(case.query, encoding="utf-8")
    (case_dir / "grounding.json").write_text(case.grounding.model_dump_json(indent=2), encoding="utf-8")
    (case_dir / "gold.md").write_text(case.gold_markdown, encoding="utf-8")
    return case_dir


def load_gold_case(case_dir: Path) -> GoldCase:
    """Load a case directory back into a GoldCase."""
    return GoldCase(
        case_id=case_dir.name,
        query=(case_dir / "query.txt").read_text(encoding="utf-8"),
        grounding=ExecutionResult.model_validate_json((case_dir / "grounding.json").read_text(encoding="utf-8")),
        gold_markdown=(case_dir / "gold.md").read_text(encoding="utf-8"),
    )


def bounded_grounding_summary(result: ExecutionResult, max_rows: int = 40) -> str:
    """Compact, capped canonical view of grounding for the judge prompt.

    Renders exact counts + up to max_rows record rows + agents + links, so the
    judge can verify no-fabrication without receiving the full ExecutionResult.
    """
    g = result.grounding
    lines: list[str] = []
    lines.append(f"TOTAL_RECORDS: {result.total_record_count}")
    lines.append(f"RECORDS_SHOWN: {min(len(g.records), max_rows)} of {len(g.records)}")
    for r in g.records[:max_rows]:
        agents = ", ".join(r.agents) if r.agents else "-"
        lines.append(
            f"- mms_id={r.mms_id} | title={r.title} | date={r.date_display or '-'} "
            f"| place={r.place or '-'} | publisher={r.publisher or '-'} "
            f"| lang={r.language or '-'} | agents=[{agents}] | url={r.primo_url or '-'}"
        )
    if g.agents:
        lines.append(f"AGENTS: {len(g.agents)}")
        for a in g.agents[:max_rows]:
            lines.append(f"  * {a.canonical_name} (records={a.record_count}, links={len(a.links)})")
    if g.links:
        lines.append(f"LINKS: {len(g.links)}")
        for ln in g.links[:max_rows]:
            lines.append(f"  ~ {ln.label}: {ln.url} ({ln.source})")
    if g.aggregations:
        lines.append(f"AGGREGATIONS: {list(g.aggregations.keys())}")
    if g.broadening_notes:
        lines.append(f"BROADENING_NOTES: {g.broadening_notes}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Task 7: Batch request builders
# ---------------------------------------------------------------------------


def is_reasoning_model(model: str) -> bool:
    """gpt-5.x are reasoning models (reasoning tokens bill as output)."""
    return model.startswith("gpt-5")


def _chat_body(
    model: str,
    system: str,
    user: str,
    response_schema,
    max_output_tokens: int,
    reasoning_effort: str | None,
) -> dict:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": pydantic_to_response_format(response_schema),
        "max_completion_tokens": max_output_tokens,
    }
    if is_reasoning_model(model) and reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return body


def build_narration_request(
    case: GoldCase,
    model: str,
    max_output_tokens: int,
    reasoning_effort: str | None = None,
) -> dict:
    """One Batch API line for a candidate narration over a frozen gold case."""
    user = build_lean_narrator_prompt(case.query, case.grounding)
    body = _chat_body(model, NARRATOR_SYSTEM_PROMPT, user, NarratorResponseLLM, max_output_tokens, reasoning_effort)
    return {
        "custom_id": f"{case.case_id}::{model}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": body,
    }


def build_judge_request(
    case: GoldCase,
    candidate_text: str,
    judge_model: str,
    candidate_model: str,
    max_output_tokens: int,
    reasoning_effort: str | None = "low",
) -> dict:
    """One Batch API line for judging a candidate narration against the gold.

    The judge's ground truth is the SAME lean prompt the narrator received, so any
    record / agent-bio / aggregation-facet / link the narrator could legitimately use
    is visible to the judge (parity prevents false 'fabrication' flags).
    """
    system, user = build_gold_judge_prompt(
        query=case.query,
        bounded_grounding=build_lean_narrator_prompt(case.query, case.grounding),
        gold_text=case.gold_markdown,
        candidate_text=candidate_text,
    )
    body = _chat_body(judge_model, system, user, NarratorGoldJudgment, max_output_tokens, reasoning_effort)
    return {
        "custom_id": f"{case.case_id}::{candidate_model}::judge",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": body,
    }


def extract_narrative(response_body: dict) -> tuple[str, dict]:
    """Pull narrative text + usage from a batch /v1/chat/completions response body."""
    content = response_body["choices"][0]["message"]["content"]
    parsed = NarratorResponseLLM.model_validate_json(content)
    return parsed.narrative, response_body.get("usage", {})
