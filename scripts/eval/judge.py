"""LLM-as-judge scoring for interpreter and narrator outputs.

Combines deterministic checks (intent match, filter overlap) with
LLM-based quality assessment (step quality, narrative criteria).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
        return intent_score * 0.3 + filter_score * 0.3 + self.step_quality * 0.4


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

A plan that asks for clarification (clarification set, empty steps) on a
garbled, ambiguous, or unintelligible query is CORRECT behavior — rate it
4-5, not as an empty plan.

Cap the rating at 3 when the plan adds hard constraints the user never
stated — e.g. inventing specific city/country/year filters when the user
only gave broad context like "in Europe". Invented hard constraints
silently exclude relevant records.

Respond with your rating and a brief justification."""


def deterministic_checks(
    query: EvalQuery,
    plan_dict: dict[str, Any],
) -> tuple[bool, float]:
    """Intent match + filter overlap (issue #10: pure, testable).

    Expected intent 'clarification' is satisfied by the clarification FIELD
    being set — it is not in the interpreter's intent vocabulary, and asking
    (empty steps + question) is the correct behavior for garbled queries.
    """
    if query.intent == "clarification":
        intent_match = bool(plan_dict.get("clarification"))
    else:
        intent_match = query.intent in plan_dict.get("intents", [])
    filter_overlap = _compute_filter_overlap(query.expected_filters, plan_dict.get("filters_produced", {}))
    return intent_match, filter_overlap


async def score_interpreter(
    query: EvalQuery,
    plan_dict: dict[str, Any],
    judge_model: str = "gpt-4.1",
) -> InterpreterScore:
    """Score an interpreter output using deterministic checks + LLM judge."""
    intent_match, filter_overlap = deterministic_checks(query, plan_dict)

    # LLM judge: step quality — must see clarification + confidence
    # (issue #10: a correct clarification looked like an empty plan).
    user_prompt = (
        f"Query: {query.query}\n"
        f"Expected intent: {query.intent}\n"
        f"Plan confidence: {plan_dict.get('confidence')}\n"
        f"Clarification asked: {plan_dict.get('clarification') or '(none)'}\n"
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
    user_prompt = f"Query: {query.query}\n\nGrounding data:\n{grounding_summary}\n\nNarrative produced:\n{narrative}\n"
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


FABRICATION_CAP = 1.0  # composite ceiling when any fabrication is detected

# Reference-anchored rubric weights (sum to 1.0)
GOLD_WEIGHTS = {
    "grounding": 0.40,
    "coverage": 0.20,
    "evidence_fidelity": 0.15,
    "scholarly_quality": 0.15,
    "scope_handling": 0.10,
}


class NarratorGoldJudgment(BaseModel):
    """Judge output: candidate narrative scored against the gold, 0-3 per dim."""

    model_config = ConfigDict(extra="forbid")
    grounding: int = Field(ge=0, le=3, description="Claims appear in grounding; no fabrication")
    coverage: int = Field(ge=0, le=3, description="Covers holdings/facts the gold covers")
    evidence_fidelity: int = Field(ge=0, le=3, description="Exact counts/titles/links correct")
    scholarly_quality: int = Field(ge=0, le=3, description="Clarity, structure, scholarly framing")
    scope_handling: int = Field(ge=0, le=3, description="Empty-set honesty; clarification; no overreach")
    fabrication_detected: bool = Field(description="Any invented record/figure/claim?")
    fabricated_claims: list[str] = Field(default_factory=list)
    rationale: str = Field(description="Brief justification across dimensions")


@dataclass
class GoldScore:
    """Weighted composite for a candidate narrative vs gold (0.0-3.0 scale)."""

    grounding: int
    coverage: int
    evidence_fidelity: int
    scholarly_quality: int
    scope_handling: int
    fabrication_detected: bool
    fabricated_claims: list[str]
    rationale: str

    @classmethod
    def from_judgment(cls, j: "NarratorGoldJudgment") -> "GoldScore":
        return cls(
            grounding=j.grounding,
            coverage=j.coverage,
            evidence_fidelity=j.evidence_fidelity,
            scholarly_quality=j.scholarly_quality,
            scope_handling=j.scope_handling,
            fabrication_detected=j.fabrication_detected,
            fabricated_claims=list(j.fabricated_claims),
            rationale=j.rationale,
        )

    @property
    def composite(self) -> float:
        raw = (
            self.grounding * GOLD_WEIGHTS["grounding"]
            + self.coverage * GOLD_WEIGHTS["coverage"]
            + self.evidence_fidelity * GOLD_WEIGHTS["evidence_fidelity"]
            + self.scholarly_quality * GOLD_WEIGHTS["scholarly_quality"]
            + self.scope_handling * GOLD_WEIGHTS["scope_handling"]
        )
        return min(raw, FABRICATION_CAP) if self.fabrication_detected else raw


def parse_gold_judgment(raw_json: str) -> GoldScore:
    """Validate raw judge JSON into a GoldScore."""
    return GoldScore.from_judgment(NarratorGoldJudgment.model_validate_json(raw_json))


GOLD_JUDGE_SYSTEM = """\
You are an exacting evaluator of scholarly bibliographic narratives for a rare books
discovery system. You score a CANDIDATE narrative against a GOLD reference. The GROUNDING
block is the EXACT data the narrator was given; it is the source of truth for COLLECTION
facts only.

CRITICAL — what is and is NOT fabrication:
- The narrator is EXPLICITLY ALLOWED to use general scholarly, historical, and biographical
  knowledge for context and interpretation — e.g. the significance of a press, an author's
  life and dates, the printing history of a city, why an empty result is unsurprising. This
  is NOT fabrication. Do NOT flag it, even though it does not appear in the GROUNDING.
- Fabrication = a COLLECTION claim the GROUNDING does not support: inventing a record, title,
  date, printer, place, or count attributed to the collection; stating a count that
  contradicts the exact count in the GROUNDING; mischaracterizing the holdings (e.g. calling
  printed books "manuscripts"); or presenting a Primo/Wikipedia/Wikidata link as collection
  evidence when that link is not in the GROUNDING.
- When unsure whether a statement is general knowledge or a collection claim, treat it as
  general knowledge and do NOT flag it. Aggregation facets, agent bios, and links that ARE in
  the GROUNDING are supported — do not flag them.

Score each dimension 0-3 (0 = broken, 1 = poor, 2 = good with issues, 3 = excellent):
- grounding: collection claims are supported by the GROUNDING; no fabricated holdings.
- coverage: covers the holdings/facts the GOLD covers (records, matched headings, counts).
- evidence_fidelity: exact counts, titles, and grounded links are correct.
- scholarly_quality: clarity, structure, scholarly framing; general knowledge framed as
  context rather than presented as collection data.
- scope_handling: empty-set honesty, clarification when ambiguous, no overreach.

Set fabrication_detected=true and list fabricated_claims ONLY for genuine COLLECTION-claim
fabrications per the definition above. Do NOT penalize valid prose that differs in wording or
structure from the GOLD — only missing or wrong substance.
Return ONLY the structured fields."""


def build_gold_judge_prompt(
    query: str,
    bounded_grounding: str,
    gold_text: str,
    candidate_text: str,
) -> tuple[str, str]:
    """Build (system, user) messages for the reference-anchored judge."""
    user = (
        f"QUERY:\n{query}\n\n"
        f"GROUNDING (the EXACT data the narrator was given — source of truth for "
        f"collection facts):\n{bounded_grounding}\n\n"
        f"GOLD REFERENCE NARRATIVE:\n{gold_text}\n\n"
        f"CANDIDATE NARRATIVE (score this):\n{candidate_text}\n"
    )
    return GOLD_JUDGE_SYSTEM, user
