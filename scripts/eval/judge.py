"""LLM-as-judge scoring for interpreter and narrator outputs.

Combines deterministic checks (intent match, filter overlap) with
LLM-based quality assessment (step quality, narrative criteria).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from scripts.eval.query_set import EvalQuery
from scripts.models.llm_client import structured_completion

logger = logging.getLogger(__name__)


# -- Judge schemas (what the LLM returns) --

class InterpreterJudgment(BaseModel):
    """LLM judge output for interpreter step quality."""
    step_quality: int = Field(ge=1, le=5, description="Quality of execution steps (1-5)")
    justification: str = Field(description="Brief justification for the score")


class NarratorJudgment(BaseModel):
    """LLM judge output for narrator quality."""
    accuracy: int = Field(ge=1, le=5, description="Does narrative reflect grounding data?")
    completeness: int = Field(ge=1, le=5, description="Are all relevant records/agents mentioned?")
    scholarly_tone: int = Field(ge=1, le=5, description="Appropriate for bibliographic discovery?")
    conciseness: int = Field(ge=1, le=5, description="No filler or hallucination?")
    justification: str = Field(description="Brief justification")


# -- Score dataclasses --

@dataclass
class InterpreterScore:
    """Combined score for an interpreter output."""
    intent_match: bool
    filter_overlap: float  # 0.0 - 1.0
    step_quality: int  # 1-5 from LLM judge
    justification: str

    @property
    def combined(self) -> float:
        """Weighted combined score (0.0 - 5.0 scale)."""
        intent_score = 5.0 if self.intent_match else 1.0
        filter_score = self.filter_overlap * 5.0
        return (intent_score * 0.3 + filter_score * 0.3 + self.step_quality * 0.4)


@dataclass
class NarratorScore:
    """Combined score for a narrator output."""
    accuracy: int
    completeness: int
    scholarly_tone: int
    conciseness: int
    justification: str

    @property
    def combined(self) -> float:
        """Average of all criteria (1.0 - 5.0 scale)."""
        return (self.accuracy + self.completeness + self.scholarly_tone + self.conciseness) / 4.0


# -- Filter overlap computation --

# Map expected_filters keys to actual filter field names
_FILTER_KEY_MAP = {
    "place": {"place", "imprint_place"},
    "publisher": {"publisher"},
    "agent": {"agent", "agent_norm"},
    "year": {"year"},
    "language": {"language"},
    "subject": {"subject"},
    "title": {"title"},
}


def _compute_filter_overlap(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> float:
    """Compute overlap between expected and actual filters.

    Returns 1.0 if all expected filters have a matching key (with mapped names)
    and matching value in actual. Returns proportional score for partial matches.
    Returns 1.0 if expected is empty (nothing to match).
    """
    if not expected:
        return 1.0

    matches = 0
    for key, expected_val in expected.items():
        # Get all possible field names for this key
        possible_keys = _FILTER_KEY_MAP.get(key, {key})
        matched = False
        for possible_key in possible_keys:
            if possible_key in actual:
                actual_val = actual[possible_key]
                if str(expected_val).lower() in str(actual_val).lower():
                    matched = True
                    break
        if matched:
            matches += 1

    return matches / len(expected)


# -- Scoring functions --

INTERPRETER_JUDGE_PROMPT = """You are evaluating the quality of a bibliographic query interpretation.

Given a user's query and the execution plan produced by the interpreter, rate the quality of the execution steps on a 1-5 scale:

1 = Steps are completely wrong or irrelevant
2 = Steps address the query but with significant errors
3 = Steps are reasonable but miss important aspects
4 = Steps are good with minor improvements possible
5 = Steps are excellent and comprehensive

Respond with your rating and a brief justification."""


async def score_interpreter(
    query: EvalQuery,
    plan_dict: dict[str, Any],
    judge_model: str = "gpt-4.1",
) -> InterpreterScore:
    """Score an interpreter output using deterministic checks + LLM judge."""
    # Deterministic: intent match
    plan_intents = plan_dict.get("intents", [])
    intent_match = query.intent in plan_intents

    # Deterministic: filter overlap
    filters_produced = plan_dict.get("filters_produced", {})
    filter_overlap = _compute_filter_overlap(query.expected_filters, filters_produced)

    # LLM judge: step quality
    user_prompt = (
        f"Query: {query.query}\n"
        f"Expected intent: {query.intent}\n"
        f"Execution steps: {plan_dict.get('execution_steps', [])}\n"
    )
    result = await structured_completion(
        model=judge_model,
        system=INTERPRETER_JUDGE_PROMPT,
        user=user_prompt,
        response_schema=InterpreterJudgment,
        call_type="eval_judge_interpreter",
    )
    judgment: InterpreterJudgment = result.parsed

    return InterpreterScore(
        intent_match=intent_match,
        filter_overlap=filter_overlap,
        step_quality=judgment.step_quality,
        justification=judgment.justification,
    )


NARRATOR_JUDGE_PROMPT = """You are evaluating the quality of a scholarly bibliographic narrative.

Given a user's query, the grounding data (records, agents), and the narrative produced, rate on a 1-5 scale:

- Accuracy: Does the narrative correctly reflect the grounding data?
- Completeness: Are all relevant records and agents mentioned?
- Scholarly tone: Is it appropriate for a bibliographic discovery tool?
- Conciseness: No filler, no hallucination, no unsupported claims?

Respond with ratings for each criterion and a brief justification."""


async def score_narrator(
    query: EvalQuery,
    narrative: str,
    grounding_summary: str,
    judge_model: str = "gpt-4.1",
) -> NarratorScore:
    """Score a narrator output using LLM judge."""
    user_prompt = (
        f"Query: {query.query}\n\n"
        f"Grounding data:\n{grounding_summary}\n\n"
        f"Narrative produced:\n{narrative}\n"
    )
    result = await structured_completion(
        model=judge_model,
        system=NARRATOR_JUDGE_PROMPT,
        user=user_prompt,
        response_schema=NarratorJudgment,
        call_type="eval_judge_narrator",
    )
    judgment: NarratorJudgment = result.parsed

    return NarratorScore(
        accuracy=judgment.accuracy,
        completeness=judgment.completeness,
        scholarly_tone=judgment.scholarly_tone,
        conciseness=judgment.conciseness,
        justification=judgment.justification,
    )
