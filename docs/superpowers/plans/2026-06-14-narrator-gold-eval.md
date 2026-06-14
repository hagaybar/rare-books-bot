# Narrator Gold-Standard Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cost-bounded harness that scores cheaper narrator models against an Opus-4.8-authored gold standard, on frozen grounding, via the OpenAI Batch API.

**Architecture:** Three phases. **Phase 1** builds the harness with TDD and no live LLM calls (pricing, fixture I/O, prompt/request builders, batch client, ceiling guard, orchestrator). **Phase 2** is in-session gold authoring by Opus 4.8 ($0): author a plan per query, run the real DB executor to freeze grounding, write the gold narrative — then a user-approval gate. **Phase 3** runs the gated, paid batch eval and emits a ranked report.

**Tech Stack:** Python 3.12, pydantic v2, pytest, the `openai` SDK (2.30.0, `client.files` + `client.batches`), litellm (existing pipeline), SQLite (`data/index/bibliographic.db`).

---

## Reference: existing seams (verified, do not re-derive)

- `scripts/chat/narrator.py`
  - `NARRATOR_SYSTEM_PROMPT: str` — the production system prompt.
  - `build_lean_narrator_prompt(query: str, result: ExecutionResult) -> str` — **public**, builds the lean user prompt with no LLM call.
  - `NarratorResponseLLM(BaseModel)` — fields `narrative: str`, `confidence: float`. The structured response schema.
- `scripts/models/llm_client.py`
  - `pydantic_to_response_format(schema: Type[BaseModel]) -> dict` — builds the `response_format` dict.
- `scripts/chat/plan_models.py`
  - `ExecutionResult(BaseModel)`: `steps_completed`, `directives`, `grounding: GroundingData`, `original_query`, `session_context`, `truncated`, `total_record_count`. Round-trips via `.model_dump_json()` / `.model_validate_json()`.
  - `GroundingData`: `records: list[RecordSummary]`, `agents: list[AgentSummary]`, `aggregations`, `aggregation_meta`, `links: list[GroundingLink]`, `publishers`, `connections`, `broadening_notes`.
  - `RecordSummary`: `mms_id`, `title`, `date_display`, `place`, `publisher`, `language`, `agents`, `subjects`, `physical_description`, `notes`, `primo_url`.
  - `InterpretationPlan` (validate hand-authored plans with `.model_validate_json()`).
  - `execute_plan(plan: InterpretationPlan, db_path: Path, session_context=None, original_query: str = "") -> ExecutionResult` (in `scripts/chat/executor.py`) — **pure DB, no LLM, no network** (enrichment is read from DB tables).
- `scripts/eval/judge.py` — existing `NarratorJudgment`/`NarratorScore` (1–5). We **add** new gold-rubric types here; we do not touch the existing ones.
- Tests live under `tests/scripts/eval/` (mirrors `scripts/eval/`).

---

# Phase 1 — Harness (TDD, no live LLM)

## Task 1: Pricing table + cost estimator

**Files:**
- Create: `scripts/eval/narrator_gold.py`
- Test: `tests/scripts/eval/test_narrator_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/eval/test_narrator_gold.py
from scripts.eval.narrator_gold import estimate_request_cost, estimate_batch_cost, PRICING

def test_pricing_table_has_slate_and_judge():
    for m in ["gpt-4.1", "gpt-4.1-mini", "gpt-5-mini", "gpt-5.4-mini", "gpt-5.4"]:
        assert m in PRICING

def test_estimate_request_cost_standard():
    # gpt-4.1: $2/1M in, $8/1M out
    cost = estimate_request_cost("gpt-4.1", input_tokens=1000, max_output_tokens=1000, batch=False)
    assert abs(cost - (1000 * 2.0 / 1e6 + 1000 * 8.0 / 1e6)) < 1e-9

def test_estimate_request_cost_batch_is_half():
    full = estimate_request_cost("gpt-4.1", 1000, 1000, batch=False)
    half = estimate_request_cost("gpt-4.1", 1000, 1000, batch=True)
    assert abs(half - full / 2) < 1e-9

def test_estimate_batch_cost_sums_requests():
    reqs = [("gpt-4.1", 1000, 1000), ("gpt-5-mini", 1000, 1000)]
    total = estimate_batch_cost(reqs, batch=True)
    expected = (estimate_request_cost("gpt-4.1", 1000, 1000, batch=True)
                + estimate_request_cost("gpt-5-mini", 1000, 1000, batch=True))
    assert abs(total - expected) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError: cannot import name 'estimate_request_cost'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/narrator_gold.py
"""Narrator gold-standard evaluation: fixtures, pricing, batch request builders.

Pure functions only — no network, no LLM calls. The batch I/O lives in
scripts/eval/batch_client.py; orchestration in run_narrator_gold_eval.py.
"""
from __future__ import annotations

# Prices in USD per 1M tokens (input, output). Source: OpenAI price list 2026-06.
# Batch API applies a flat 50% discount to both input and output.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5":        (1.25, 10.00),
    "gpt-5-mini":   (0.25, 2.00),
    "gpt-5-nano":   (0.05, 0.40),
    "gpt-5.1":      (1.25, 10.00),
    "gpt-5.2":      (1.75, 14.00),
    "gpt-5.4":      (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.5":      (5.00, 30.00),
}


def estimate_request_cost(model: str, input_tokens: int, max_output_tokens: int,
                          batch: bool) -> float:
    """Upper-bound cost of one request: full input + output at the cap."""
    in_price, out_price = PRICING[model]
    cost = input_tokens * in_price / 1e6 + max_output_tokens * out_price / 1e6
    return cost * 0.5 if batch else cost


def estimate_batch_cost(requests: list[tuple[str, int, int]], batch: bool) -> float:
    """Sum estimate_request_cost over (model, input_tokens, max_output_tokens) triples."""
    return sum(estimate_request_cost(m, i, o, batch) for (m, i, o) in requests)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/narrator_gold.py tests/scripts/eval/test_narrator_gold.py
git commit -m "$(cat <<'EOF'
feat(eval): add narrator-gold pricing table + cost estimator

Pure-function pricing for the candidate slate + judge, with batch 50%
discount and worst-case (output-at-cap) estimation for the ceiling guard.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Token estimator + cost-ceiling guard

**Files:**
- Modify: `scripts/eval/narrator_gold.py`
- Test: `tests/scripts/eval/test_narrator_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scripts/eval/test_narrator_gold.py
import pytest
from scripts.eval.narrator_gold import estimate_tokens, assert_within_ceiling, CostCeilingExceeded

def test_estimate_tokens_heuristic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100  # ~4 chars/token

def test_ceiling_guard_passes_under():
    # tiny batch well under $2
    projected = assert_within_ceiling([("gpt-4.1", 1000, 1000)], ceiling=2.00, batch=True)
    assert projected < 2.00

def test_ceiling_guard_aborts_over():
    # 100k requests would blow past $2
    reqs = [("gpt-5.4", 5000, 1200)] * 1000
    with pytest.raises(CostCeilingExceeded):
        assert_within_ceiling(reqs, ceiling=2.00, batch=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k "tokens or ceiling" -v`
Expected: FAIL with `ImportError: cannot import name 'estimate_tokens'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/narrator_gold.py
import math


class CostCeilingExceeded(RuntimeError):
    """Raised when a batch's projected cost exceeds the configured ceiling."""


def estimate_tokens(text: str) -> int:
    """Heuristic token count for pre-submit estimation (~4 chars/token).

    Deliberately simple and model-agnostic — gpt-5.x encodings may be absent
    from local tokenizers. Used only for the ceiling guard's input estimate;
    output is bounded exactly by max_completion_tokens.
    """
    return math.floor(len(text) / 4)


def assert_within_ceiling(requests: list[tuple[str, int, int]], ceiling: float,
                          batch: bool) -> float:
    """Project worst-case batch cost; raise CostCeilingExceeded if over ceiling.

    Returns the projected cost when within budget.
    """
    projected = estimate_batch_cost(requests, batch=batch)
    if projected > ceiling:
        raise CostCeilingExceeded(
            f"Projected ${projected:.4f} exceeds ceiling ${ceiling:.2f} "
            f"({len(requests)} requests, batch={batch})"
        )
    return projected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k "tokens or ceiling" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/narrator_gold.py tests/scripts/eval/test_narrator_gold.py
git commit -m "$(cat <<'EOF'
feat(eval): add token heuristic + cost-ceiling guard

assert_within_ceiling projects worst-case batch cost (input estimate +
output at max_completion_tokens) and aborts before submit if over budget.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Gold-case fixture model + grounding round-trip

**Files:**
- Modify: `scripts/eval/narrator_gold.py`
- Test: `tests/scripts/eval/test_narrator_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scripts/eval/test_narrator_gold.py
from pathlib import Path
from scripts.chat.plan_models import ExecutionResult, GroundingData, RecordSummary
from scripts.eval.narrator_gold import GoldCase, load_gold_case, save_gold_case

def _sample_result() -> ExecutionResult:
    return ExecutionResult(
        steps_completed=[], directives=[],
        grounding=GroundingData(records=[
            RecordSummary(mms_id="990001", title="Sefer Yetzirah", date_display="1562",
                          place="Mantua", primo_url="https://primo/990001"),
        ]),
        original_query="books printed in Mantua", total_record_count=1,
    )

def test_gold_case_round_trip(tmp_path: Path):
    case = GoldCase(case_id="c01_mantua", query="books printed in Mantua",
                    grounding=_sample_result(), gold_markdown="# Holdings\n1 record...")
    save_gold_case(tmp_path, case)
    loaded = load_gold_case(tmp_path / "c01_mantua")
    assert loaded.case_id == "c01_mantua"
    assert loaded.query == case.query
    assert loaded.gold_markdown == case.gold_markdown
    # grounding survives the JSON round-trip exactly
    assert loaded.grounding.model_dump() == case.grounding.model_dump()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k round_trip -v`
Expected: FAIL with `ImportError: cannot import name 'GoldCase'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/narrator_gold.py
from dataclasses import dataclass
from pathlib import Path

from scripts.chat.plan_models import ExecutionResult


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
    (case_dir / "grounding.json").write_text(
        case.grounding.model_dump_json(indent=2), encoding="utf-8")
    (case_dir / "gold.md").write_text(case.gold_markdown, encoding="utf-8")
    return case_dir


def load_gold_case(case_dir: Path) -> GoldCase:
    """Load a case directory back into a GoldCase."""
    return GoldCase(
        case_id=case_dir.name,
        query=(case_dir / "query.txt").read_text(encoding="utf-8"),
        grounding=ExecutionResult.model_validate_json(
            (case_dir / "grounding.json").read_text(encoding="utf-8")),
        gold_markdown=(case_dir / "gold.md").read_text(encoding="utf-8"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k round_trip -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/narrator_gold.py tests/scripts/eval/test_narrator_gold.py
git commit -m "$(cat <<'EOF'
feat(eval): add GoldCase fixture model with grounding round-trip

Persists each case as query.txt + grounding.json + gold.md; grounding is a
faithful ExecutionResult JSON round-trip so candidates see identical input.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Bounded grounding summary (for the judge)

**Files:**
- Modify: `scripts/eval/narrator_gold.py`
- Test: `tests/scripts/eval/test_narrator_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scripts/eval/test_narrator_gold.py
from scripts.chat.plan_models import AgentSummary, GroundingLink
from scripts.eval.narrator_gold import bounded_grounding_summary

def test_bounded_summary_caps_rows_and_states_total():
    recs = [RecordSummary(mms_id=str(i), title=f"T{i}", date_display="1500", place="Venice")
            for i in range(100)]
    result = ExecutionResult(steps_completed=[], directives=[],
                             grounding=GroundingData(records=recs),
                             original_query="q", total_record_count=100)
    summary = bounded_grounding_summary(result, max_rows=40)
    # exact total is stated even though rows are capped
    assert "100" in summary
    # at most 40 record rows rendered
    assert sum(1 for line in summary.splitlines() if line.startswith("- mms_id=")) <= 40

def test_bounded_summary_empty_set():
    result = ExecutionResult(steps_completed=[], directives=[],
                             grounding=GroundingData(records=[]),
                             original_query="q", total_record_count=0)
    summary = bounded_grounding_summary(result)
    assert "0" in summary  # zero-result honesty signal for the judge
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k bounded -v`
Expected: FAIL with `ImportError: cannot import name 'bounded_grounding_summary'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/narrator_gold.py

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
            lines.append(f"  * {a.canonical_name} (records={a.record_count}, "
                         f"links={len(a.links)})")
    if g.links:
        lines.append(f"LINKS: {len(g.links)}")
        for ln in g.links[:max_rows]:
            lines.append(f"  ~ {ln.label}: {ln.url} ({ln.source})")
    if g.aggregations:
        lines.append(f"AGGREGATIONS: {list(g.aggregations.keys())}")
    if g.broadening_notes:
        lines.append(f"BROADENING_NOTES: {g.broadening_notes}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k bounded -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/narrator_gold.py tests/scripts/eval/test_narrator_gold.py
git commit -m "$(cat <<'EOF'
feat(eval): add bounded grounding summary for judge prompts

Caps record rows (default 40) while always stating exact totals, keeping
judge prompts ~3-5K tokens even for 100+ record cases.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Reference-anchored judge schema + scoring (judge.py)

**Files:**
- Modify: `scripts/eval/judge.py`
- Test: `tests/scripts/eval/test_gold_judge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/eval/test_gold_judge.py
from scripts.eval.judge import NarratorGoldJudgment, GoldScore, parse_gold_judgment

def _judgment(**over):
    base = dict(grounding=3, coverage=3, evidence_fidelity=3, scholarly_quality=3,
                scope_handling=3, fabrication_detected=False, fabricated_claims=[],
                rationale="ok")
    base.update(over)
    return NarratorGoldJudgment(**base)

def test_composite_weights_sum_to_one():
    s = GoldScore.from_judgment(_judgment())
    assert abs(s.composite - 3.0) < 1e-9  # all 3s -> 3.0

def test_composite_weighting():
    # only grounding perfect (weight .40), rest zero
    s = GoldScore.from_judgment(_judgment(grounding=3, coverage=0, evidence_fidelity=0,
                                          scholarly_quality=0, scope_handling=0))
    assert abs(s.composite - (3 * 0.40)) < 1e-9

def test_fabrication_hard_caps_score():
    s = GoldScore.from_judgment(_judgment(fabrication_detected=True,
                                          fabricated_claims=["invented title X"]))
    assert s.composite <= 1.0  # fabrication caps composite regardless of other dims

def test_parse_gold_judgment_from_json():
    raw = _judgment(coverage=2).model_dump_json()
    s = parse_gold_judgment(raw)
    assert s.coverage == 2 and not s.fabrication_detected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_gold_judge.py -v`
Expected: FAIL with `ImportError: cannot import name 'NarratorGoldJudgment'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/judge.py
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
            grounding=j.grounding, coverage=j.coverage,
            evidence_fidelity=j.evidence_fidelity, scholarly_quality=j.scholarly_quality,
            scope_handling=j.scope_handling, fabrication_detected=j.fabrication_detected,
            fabricated_claims=list(j.fabricated_claims), rationale=j.rationale,
        )

    @property
    def composite(self) -> float:
        raw = (self.grounding * GOLD_WEIGHTS["grounding"]
               + self.coverage * GOLD_WEIGHTS["coverage"]
               + self.evidence_fidelity * GOLD_WEIGHTS["evidence_fidelity"]
               + self.scholarly_quality * GOLD_WEIGHTS["scholarly_quality"]
               + self.scope_handling * GOLD_WEIGHTS["scope_handling"])
        return min(raw, FABRICATION_CAP) if self.fabrication_detected else raw


def parse_gold_judgment(raw_json: str) -> GoldScore:
    """Validate raw judge JSON into a GoldScore."""
    return GoldScore.from_judgment(NarratorGoldJudgment.model_validate_json(raw_json))
```

Note: add `from pydantic import ConfigDict` to the imports at the top of `judge.py` (it currently imports `BaseModel, Field` only).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_gold_judge.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/judge.py tests/scripts/eval/test_gold_judge.py
git commit -m "$(cat <<'EOF'
feat(eval): add reference-anchored narrator gold judge schema + scoring

NarratorGoldJudgment (0-3 per dimension) + GoldScore weighted composite
(grounding .40, coverage .20, fidelity .15, quality .15, scope .10) with a
hard fabrication cap. Leaves existing NarratorScore untouched.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Judge prompt builder (judge.py)

**Files:**
- Modify: `scripts/eval/judge.py`
- Test: `tests/scripts/eval/test_gold_judge.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scripts/eval/test_gold_judge.py
from scripts.eval.judge import build_gold_judge_prompt

def test_judge_prompt_includes_all_parts():
    system, user = build_gold_judge_prompt(
        query="books in Venice", bounded_grounding="TOTAL_RECORDS: 3",
        gold_text="GOLD NARRATIVE", candidate_text="CANDIDATE NARRATIVE")
    assert "books in Venice" in user
    assert "TOTAL_RECORDS: 3" in user
    assert "GOLD NARRATIVE" in user
    assert "CANDIDATE NARRATIVE" in user
    # rubric + fabrication instruction present in system prompt
    assert "fabricat" in system.lower()
    assert "0" in system and "3" in system  # 0-3 scale described
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_gold_judge.py -k judge_prompt -v`
Expected: FAIL with `ImportError: cannot import name 'build_gold_judge_prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/judge.py
GOLD_JUDGE_SYSTEM = """\
You are an exacting evaluator of scholarly bibliographic narratives for a rare
books discovery system. You score a CANDIDATE narrative against a GOLD reference,
using only the provided GROUNDING data as ground truth.

Score each dimension 0-3 (0 = broken, 1 = poor, 2 = good with issues, 3 = excellent):
- grounding: every specific claim (count, title, date, printer, place, link) appears
  in the GROUNDING. Invented specifics are fabrication.
- coverage: covers the holdings/facts the GOLD covers.
- evidence_fidelity: exact counts, titles, and links are correct.
- scholarly_quality: clarity, structure, scholarly framing; general knowledge clearly
  labeled as not-from-collection.
- scope_handling: empty-set honesty, clarification when ambiguous, no overreach.

Set fabrication_detected=true and list fabricated_claims if ANY specific claim is not
supported by the GROUNDING. Do NOT penalize valid prose that differs in wording or
structure from the GOLD — only missing or wrong substance.
Return ONLY the structured fields."""


def build_gold_judge_prompt(query: str, bounded_grounding: str, gold_text: str,
                            candidate_text: str) -> tuple[str, str]:
    """Build (system, user) messages for the reference-anchored judge."""
    user = (
        f"QUERY:\n{query}\n\n"
        f"GROUNDING (ground truth — bounded):\n{bounded_grounding}\n\n"
        f"GOLD REFERENCE NARRATIVE:\n{gold_text}\n\n"
        f"CANDIDATE NARRATIVE (score this):\n{candidate_text}\n"
    )
    return GOLD_JUDGE_SYSTEM, user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_gold_judge.py -k judge_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/judge.py tests/scripts/eval/test_gold_judge.py
git commit -m "$(cat <<'EOF'
feat(eval): add reference-anchored gold judge prompt builder

System prompt encodes the 0-3 rubric + fabrication rule; user prompt carries
query, bounded grounding, gold, and candidate. Substance-not-style scoring.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Batch request builders (narrator_gold.py)

**Files:**
- Modify: `scripts/eval/narrator_gold.py`
- Test: `tests/scripts/eval/test_narrator_gold.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scripts/eval/test_narrator_gold.py
from scripts.eval.narrator_gold import (
    build_narration_request, build_judge_request, extract_narrative, is_reasoning_model)

def test_is_reasoning_model():
    assert is_reasoning_model("gpt-5-mini")
    assert is_reasoning_model("gpt-5.4")
    assert not is_reasoning_model("gpt-4.1")
    assert not is_reasoning_model("gpt-4.1-mini")

def test_narration_request_shape_non_reasoning():
    case = GoldCase("c01", "books in Mantua", _sample_result(), "gold")
    req = build_narration_request(case, model="gpt-4.1", max_output_tokens=2000)
    assert req["custom_id"] == "c01::gpt-4.1"
    assert req["method"] == "POST" and req["url"] == "/v1/chat/completions"
    b = req["body"]
    assert b["model"] == "gpt-4.1"
    assert b["max_completion_tokens"] == 2000
    assert "reasoning_effort" not in b           # non-reasoning model
    assert b["messages"][0]["role"] == "system"
    assert b["response_format"]["type"] == "json_schema"

def test_narration_request_reasoning_model_sets_effort():
    case = GoldCase("c01", "q", _sample_result(), "gold")
    req = build_narration_request(case, model="gpt-5-mini", max_output_tokens=2000,
                                  reasoning_effort="low")
    assert req["body"]["reasoning_effort"] == "low"

def test_judge_request_shape():
    case = GoldCase("c01", "q", _sample_result(), "gold narrative")
    req = build_judge_request(case, candidate_text="cand", judge_model="gpt-5.4",
                              candidate_model="gpt-4.1", max_output_tokens=1200,
                              reasoning_effort="low")
    assert req["custom_id"] == "c01::gpt-4.1::judge"
    assert req["body"]["model"] == "gpt-5.4"
    assert req["body"]["reasoning_effort"] == "low"
    assert req["body"]["max_completion_tokens"] == 1200

def test_extract_narrative_parses_structured_output():
    body = {"choices": [{"message": {"content": '{"narrative": "Hello", "confidence": 0.9}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    text, usage = extract_narrative(body)
    assert text == "Hello"
    assert usage["completion_tokens"] == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k "request or narrative or reasoning" -v`
Expected: FAIL with `ImportError: cannot import name 'build_narration_request'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to scripts/eval/narrator_gold.py
import json

from scripts.chat.narrator import NARRATOR_SYSTEM_PROMPT, build_lean_narrator_prompt
from scripts.chat.plan_models import NarratorResponseLLM
from scripts.models.llm_client import pydantic_to_response_format
from scripts.eval.judge import (
    NarratorGoldJudgment, build_gold_judge_prompt)


def is_reasoning_model(model: str) -> bool:
    """gpt-5.x are reasoning models (reasoning tokens bill as output)."""
    return model.startswith("gpt-5")


def _chat_body(model: str, system: str, user: str, response_schema,
               max_output_tokens: int, reasoning_effort: str | None) -> dict:
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


def build_narration_request(case: GoldCase, model: str, max_output_tokens: int,
                            reasoning_effort: str | None = None) -> dict:
    """One Batch API line for a candidate narration over a frozen gold case."""
    user = build_lean_narrator_prompt(case.query, case.grounding)
    body = _chat_body(model, NARRATOR_SYSTEM_PROMPT, user, NarratorResponseLLM,
                      max_output_tokens, reasoning_effort)
    return {"custom_id": f"{case.case_id}::{model}", "method": "POST",
            "url": "/v1/chat/completions", "body": body}


def build_judge_request(case: GoldCase, candidate_text: str, judge_model: str,
                        candidate_model: str, max_output_tokens: int,
                        reasoning_effort: str | None = "low") -> dict:
    """One Batch API line for judging a candidate narration against the gold."""
    system, user = build_gold_judge_prompt(
        query=case.query,
        bounded_grounding=bounded_grounding_summary(case.grounding),
        gold_text=case.gold_markdown, candidate_text=candidate_text)
    body = _chat_body(judge_model, system, user, NarratorGoldJudgment,
                      max_output_tokens, reasoning_effort)
    return {"custom_id": f"{case.case_id}::{candidate_model}::judge", "method": "POST",
            "url": "/v1/chat/completions", "body": body}


def extract_narrative(response_body: dict) -> tuple[str, dict]:
    """Pull narrative text + usage from a batch /v1/chat/completions response body."""
    content = response_body["choices"][0]["message"]["content"]
    parsed = NarratorResponseLLM.model_validate_json(content)
    return parsed.narrative, response_body.get("usage", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_narrator_gold.py -k "request or narrative or reasoning" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/narrator_gold.py tests/scripts/eval/test_narrator_gold.py
git commit -m "$(cat <<'EOF'
feat(eval): add batch request builders for narration + judging

Builds byte-identical production narration prompts (NARRATOR_SYSTEM_PROMPT +
build_lean_narrator_prompt + NarratorResponseLLM schema) and gold-judge
requests; sets max_completion_tokens always and reasoning_effort only for
gpt-5.x. custom_id encodes case::model[::judge] for reconciliation.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: OpenAI batch client wrapper

**Files:**
- Create: `scripts/eval/batch_client.py`
- Test: `tests/scripts/eval/test_batch_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/eval/test_batch_client.py
import json
from pathlib import Path
from scripts.eval.batch_client import write_batch_jsonl, reconcile, parse_output_line

def test_write_batch_jsonl(tmp_path: Path):
    reqs = [{"custom_id": "a::m", "method": "POST", "url": "/v1/chat/completions",
             "body": {"model": "m"}}]
    p = write_batch_jsonl(reqs, tmp_path / "in.jsonl")
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["custom_id"] == "a::m"

def test_reconcile_flags_missing():
    reqs = [{"custom_id": "a"}, {"custom_id": "b"}]
    results = {"a": {"ok": 1}}  # b missing
    matched, missing = reconcile(reqs, results)
    assert "a" in matched and missing == ["b"]

def test_parse_output_line_extracts_body_and_custom_id():
    line = json.dumps({
        "custom_id": "a::m",
        "response": {"status_code": 200, "body": {"choices": [], "usage": {}}},
        "error": None,
    })
    cid, body, err = parse_output_line(line)
    assert cid == "a::m" and err is None and "choices" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_batch_client.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.eval.batch_client`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/batch_client.py
"""Thin wrapper over the OpenAI Batch API for offline eval runs.

Pure helpers (write_batch_jsonl, reconcile, parse_output_line) are unit-tested;
the networked submit/poll/download functions take an OpenAI client so they can
be exercised with a fake in tests.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def write_batch_jsonl(requests: list[dict], path: Path) -> Path:
    """Serialize batch request dicts to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in requests:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def parse_output_line(line: str) -> tuple[str, dict | None, Any]:
    """Parse one Batch API output line -> (custom_id, response_body|None, error)."""
    obj = json.loads(line)
    cid = obj["custom_id"]
    err = obj.get("error")
    resp = obj.get("response") or {}
    body = resp.get("body") if err is None else None
    return cid, body, err


def reconcile(requests: list[dict], results: dict[str, Any]
              ) -> tuple[dict[str, Any], list[str]]:
    """Split requested custom_ids into matched results and missing ids."""
    matched: dict[str, Any] = {}
    missing: list[str] = []
    for r in requests:
        cid = r["custom_id"]
        if cid in results:
            matched[cid] = results[cid]
        else:
            missing.append(cid)
    return matched, missing


def submit_batch(client: Any, jsonl_path: Path, description: str) -> str:
    """Upload the JSONL and create a batch; return the batch id."""
    with jsonl_path.open("rb") as fh:
        uploaded = client.files.create(file=fh, purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/chat/completions",
        completion_window="24h",
        metadata={"description": description},
    )
    return batch.id


def poll_until_done(client: Any, batch_id: str, interval: float = 20.0,
                    timeout: float = 86400.0) -> Any:
    """Poll a batch until terminal state; return the batch object."""
    waited = 0.0
    terminal = {"completed", "failed", "expired", "cancelled"}
    while True:
        batch = client.batches.retrieve(batch_id)
        if batch.status in terminal:
            return batch
        if waited >= timeout:
            raise TimeoutError(f"Batch {batch_id} not done after {timeout}s "
                               f"(status={batch.status})")
        time.sleep(interval)
        waited += interval


def download_results(client: Any, batch: Any) -> dict[str, dict | None]:
    """Download the output file and map custom_id -> response body (None on error)."""
    if not getattr(batch, "output_file_id", None):
        return {}
    content = client.files.content(batch.output_file_id).text
    out: dict[str, dict | None] = {}
    for line in content.splitlines():
        if not line.strip():
            continue
        cid, body, _err = parse_output_line(line)
        out[cid] = body
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_batch_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/batch_client.py tests/scripts/eval/test_batch_client.py
git commit -m "$(cat <<'EOF'
feat(eval): add OpenAI Batch API client wrapper

write_batch_jsonl/reconcile/parse_output_line are pure + tested; submit_batch,
poll_until_done, download_results take an injected client for offline testing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Orchestrator CLI + dry-run

**Files:**
- Create: `scripts/eval/run_narrator_gold_eval.py`
- Test: `tests/scripts/eval/test_run_narrator_gold_eval.py`

- [ ] **Step 1: Write the failing test (dry-run, no network)**

```python
# tests/scripts/eval/test_run_narrator_gold_eval.py
from pathlib import Path
from scripts.chat.plan_models import ExecutionResult, GroundingData, RecordSummary
from scripts.eval.narrator_gold import GoldCase, save_gold_case
from scripts.eval.run_narrator_gold_eval import build_all_narration_requests, dry_run

def _case(cid: str) -> GoldCase:
    r = ExecutionResult(steps_completed=[], directives=[],
                        grounding=GroundingData(records=[
                            RecordSummary(mms_id="1", title="T", date_display="1500")]),
                        original_query="q", total_record_count=1)
    return GoldCase(cid, "q", r, "gold")

def test_build_all_narration_requests_one_per_case_model(tmp_path: Path):
    for cid in ["c01", "c02"]:
        save_gold_case(tmp_path, _case(cid))
    models = ["gpt-4.1", "gpt-5-mini"]
    reqs = build_all_narration_requests(tmp_path, models, max_output_tokens=2000,
                                        reasoning_effort="low")
    assert len(reqs) == 4  # 2 cases x 2 models
    assert {r["custom_id"] for r in reqs} == {
        "c01::gpt-4.1", "c01::gpt-5-mini", "c02::gpt-4.1", "c02::gpt-5-mini"}

def test_dry_run_projects_cost_and_writes_jsonl(tmp_path: Path):
    save_gold_case(tmp_path, _case("c01"))
    out = tmp_path / "run"
    projected = dry_run(gold_dir=tmp_path, models=["gpt-4.1", "gpt-5-mini"],
                        judge_model="gpt-5.4", output_dir=out, ceiling=2.00,
                        max_narration_tokens=2000, max_judge_tokens=1200,
                        reasoning_effort="low")
    assert projected > 0 and projected <= 2.00
    assert (out / "narration_batch.jsonl").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_run_narrator_gold_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.eval.run_narrator_gold_eval`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/run_narrator_gold_eval.py
"""Narrator gold-standard evaluation runner (Phase 3).

Loads frozen gold cases, narrates each with every candidate model via the
OpenAI Batch API, judges each narration against the gold with a reference-
anchored rubric, and writes a ranked report. A cost-ceiling guard aborts
before any submission if projected spend exceeds the ceiling.

Usage:
    poetry run python -m scripts.eval.run_narrator_gold_eval \
      --gold-dir data/eval/narrator_gold \
      --models gpt-4.1,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini \
      --judge-model gpt-5.4 --judge-reasoning-effort low \
      --batch --cost-ceiling 2.00 \
      --max-narration-tokens 2000 --max-judge-tokens 1200 \
      --output-dir data/eval/runs/2026-06-14-narrator-gold \
      [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.eval.narrator_gold import (
    GoldCase, load_gold_case, build_narration_request, build_judge_request,
    extract_narrative, estimate_tokens, assert_within_ceiling, is_reasoning_model)
from scripts.eval.judge import parse_gold_judgment
from scripts.eval import batch_client


def load_gold_cases(gold_dir: Path) -> list[GoldCase]:
    """Load every case sub-directory under gold_dir (those with grounding.json)."""
    cases = [load_gold_case(d) for d in sorted(gold_dir.iterdir())
             if d.is_dir() and (d / "grounding.json").exists()]
    if not cases:
        raise SystemExit(f"No gold cases found under {gold_dir}")
    return cases


def build_all_narration_requests(gold_dir: Path, models: list[str],
                                 max_output_tokens: int,
                                 reasoning_effort: str | None) -> list[dict]:
    cases = load_gold_cases(gold_dir)
    return [build_narration_request(c, m, max_output_tokens,
                                    reasoning_effort if is_reasoning_model(m) else None)
            for c in cases for m in models]


def _cost_triples(requests: list[dict], max_output_tokens: int) -> list[tuple[str, int, int]]:
    """Map batch requests to (model, est_input_tokens, max_output_tokens) for the guard."""
    triples = []
    for r in requests:
        text = "".join(m["content"] for m in r["body"]["messages"])
        triples.append((r["body"]["model"], estimate_tokens(text), max_output_tokens))
    return triples


def dry_run(gold_dir: Path, models: list[str], judge_model: str, output_dir: Path,
            ceiling: float, max_narration_tokens: int, max_judge_tokens: int,
            reasoning_effort: str | None) -> float:
    """Build batch files + project worst-case cost WITHOUT submitting. Returns projected $."""
    output_dir.mkdir(parents=True, exist_ok=True)
    narration = build_all_narration_requests(gold_dir, models, max_narration_tokens,
                                             reasoning_effort)
    batch_client.write_batch_jsonl(narration, output_dir / "narration_batch.jsonl")

    n_triples = _cost_triples(narration, max_narration_tokens)
    # Judge cost: one judgment per narration; approximate judge input by a fixed budget
    # (bounded grounding + gold + candidate ~= 4000 tokens).
    j_triples = [(judge_model, 4000, max_judge_tokens) for _ in narration]
    projected = (assert_within_ceiling(n_triples, ceiling, batch=True)
                 + assert_within_ceiling(j_triples, ceiling, batch=True))
    assert_within_ceiling(n_triples + j_triples, ceiling, batch=True)  # combined guard
    print(f"[dry-run] {len(narration)} narrations + {len(narration)} judgments "
          f"-> projected ${projected:.4f} (ceiling ${ceiling:.2f})")
    return projected


def run(gold_dir: Path, models: list[str], judge_model: str, output_dir: Path,
        ceiling: float, max_narration_tokens: int, max_judge_tokens: int,
        reasoning_effort: str | None) -> None:
    """Full paid run: guard -> narrate (batch) -> judge (batch) -> report."""
    from openai import OpenAI
    client = OpenAI()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = {c.case_id: c for c in load_gold_cases(gold_dir)}

    # --- Narration batch (guarded) ---
    narration = build_all_narration_requests(gold_dir, models, max_narration_tokens,
                                             reasoning_effort)
    assert_within_ceiling(_cost_triples(narration, max_narration_tokens)
                          + [(judge_model, 4000, max_judge_tokens) for _ in narration],
                          ceiling, batch=True)
    npath = batch_client.write_batch_jsonl(narration, output_dir / "narration_batch.jsonl")
    nbatch = batch_client.poll_until_done(
        client, batch_client.submit_batch(client, npath, "narrator-gold narrations"))
    nresults = batch_client.download_results(client, nbatch)
    matched, missing = batch_client.reconcile(narration, nresults)
    if missing:
        print(f"WARNING: {len(missing)} narrations missing: {missing}")

    # --- Build judge batch from narration results ---
    judge_reqs: list[dict] = []
    narratives: dict[str, str] = {}
    for cid, body in matched.items():
        case_id, model = cid.split("::")[0], cid.split("::")[1]
        text, _usage = extract_narrative(body)
        narratives[cid] = text
        judge_reqs.append(build_judge_request(
            cases[case_id], candidate_text=text, judge_model=judge_model,
            candidate_model=model, max_output_tokens=max_judge_tokens,
            reasoning_effort="low"))
    jpath = batch_client.write_batch_jsonl(judge_reqs, output_dir / "judge_batch.jsonl")
    jbatch = batch_client.poll_until_done(
        client, batch_client.submit_batch(client, jpath, "narrator-gold judging"))
    jresults = batch_client.download_results(client, jbatch)

    # --- Assemble results ---
    rows = []
    for jreq in judge_reqs:
        cid = jreq["custom_id"]                  # case::model::judge
        case_id, model, _ = cid.split("::")
        body = jresults.get(cid)
        if body is None:
            rows.append({"case": case_id, "model": model, "error": "missing judgment"})
            continue
        score = parse_gold_judgment(body["choices"][0]["message"]["content"])
        rows.append({
            "case": case_id, "model": model,
            "composite": round(score.composite, 4),
            "grounding": score.grounding, "coverage": score.coverage,
            "evidence_fidelity": score.evidence_fidelity,
            "scholarly_quality": score.scholarly_quality,
            "scope_handling": score.scope_handling,
            "fabrication": score.fabrication_detected,
            "fabricated_claims": score.fabricated_claims,
            "rationale": score.rationale,
            "narrative": narratives.get(f"{case_id}::{model}", ""),
        })
    (output_dir / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    _write_report(output_dir, rows, models)
    print(f"Done. Report at {output_dir / 'REPORT.md'}")


def _write_report(output_dir: Path, rows: list[dict], models: list[str]) -> None:
    """Rank models by mean composite; write REPORT.md."""
    by_model: dict[str, list[dict]] = {m: [] for m in models}
    for r in rows:
        if "composite" in r:
            by_model.setdefault(r["model"], []).append(r)
    lines = ["# Narrator Gold-Standard Eval — Report", ""]
    lines.append("| Model | Mean composite (0-3) | Fabrications | Cases |")
    lines.append("|-------|----------------------|--------------|-------|")
    ranked = sorted(
        by_model.items(),
        key=lambda kv: -(sum(x["composite"] for x in kv[1]) / len(kv[1]) if kv[1] else 0))
    for model, rs in ranked:
        if not rs:
            lines.append(f"| {model} | n/a | n/a | 0 |")
            continue
        mean = sum(x["composite"] for x in rs) / len(rs)
        fab = sum(1 for x in rs if x["fabrication"])
        lines.append(f"| {model} | {mean:.2f} | {fab} | {len(rs)} |")
    (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Narrator gold-standard evaluation")
    p.add_argument("--gold-dir", type=Path, default=Path("data/eval/narrator_gold"))
    p.add_argument("--models", required=True, help="Comma-separated candidate models")
    p.add_argument("--judge-model", default="gpt-5.4")
    p.add_argument("--judge-reasoning-effort", default="low")
    p.add_argument("--batch", action="store_true", help="(always batched; kept for clarity)")
    p.add_argument("--cost-ceiling", type=float, default=2.00)
    p.add_argument("--max-narration-tokens", type=int, default=2000)
    p.add_argument("--max-judge-tokens", type=int, default=1200)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true", help="Build batches + estimate, no submit")
    args = p.parse_args()
    models = [m.strip() for m in args.models.split(",")]

    if args.dry_run:
        dry_run(args.gold_dir, models, args.judge_model, args.output_dir,
                args.cost_ceiling, args.max_narration_tokens, args.max_judge_tokens,
                args.judge_reasoning_effort)
        return
    run(args.gold_dir, models, args.judge_model, args.output_dir, args.cost_ceiling,
        args.max_narration_tokens, args.max_judge_tokens, args.judge_reasoning_effort)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_run_narrator_gold_eval.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run full new-test suite + lint**

Run: `poetry run pytest tests/scripts/eval/ -v && poetry run ruff check scripts/eval/`
Expected: all PASS, no lint errors

- [ ] **Step 6: Commit**

```bash
git add scripts/eval/run_narrator_gold_eval.py tests/scripts/eval/test_run_narrator_gold_eval.py
git commit -m "$(cat <<'EOF'
feat(eval): add narrator gold-standard eval orchestrator + dry-run

run_narrator_gold_eval.py loads frozen gold cases, batches narration then
judging, applies the cost-ceiling guard before each submit, reconciles by
custom_id, and writes results.json + ranked REPORT.md. --dry-run builds the
JSONLs and projects worst-case cost without any network call.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Grounding generator from a hand-authored plan ($0, DB-only)

**Files:**
- Create: `scripts/eval/author_gold_grounding.py`
- Test: `tests/scripts/eval/test_author_gold_grounding.py`

This is the tool Phase 2 uses: Opus authors an `InterpretationPlan` JSON per query (simulating the interpreter — no LLM), and this script runs the **pure-DB** executor to freeze grounding.

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/eval/test_author_gold_grounding.py
from pathlib import Path
from scripts.eval.author_gold_grounding import grounding_from_plan_file

def test_grounding_from_plan_file_runs_executor(tmp_path: Path):
    # Minimal empty plan (no steps) -> executor returns an empty-but-valid result.
    # InterpretationPlan requires: intents (list), reasoning, execution_steps,
    # directives, confidence (verified against scripts/chat/plan_models.py).
    plan_json = '{"intents": ["retrieval"], "reasoning": "test", '\
                '"execution_steps": [], "directives": [], "confidence": 0.9}'
    plan_path = tmp_path / "c01.plan.json"
    plan_path.write_text(plan_json, encoding="utf-8")
    result = grounding_from_plan_file(plan_path, query="books in Mantua",
                                      db_path=Path("data/index/bibliographic.db"))
    assert result.original_query == "books in Mantua"
    assert result.total_record_count == 0
```

Note: confirm `InterpretationPlan`'s exact required fields by reading
`scripts/chat/plan_models.py` (search `class InterpretationPlan`) before finalizing the
empty-plan JSON above; adjust keys to match (the executor is invoked with a validated plan).

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/scripts/eval/test_author_gold_grounding.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.eval.author_gold_grounding`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/eval/author_gold_grounding.py
"""Phase-2 helper: freeze grounding from an Opus-authored plan ($0, DB-only).

Opus simulates the interpreter by writing an InterpretationPlan JSON per query;
this runs the pure-DB executor (no LLM, no network) and writes grounding.json.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scripts.chat.plan_models import InterpretationPlan, ExecutionResult
from scripts.chat.executor import execute_plan

DB_PATH = Path("data/index/bibliographic.db")


def grounding_from_plan_file(plan_path: Path, query: str,
                             db_path: Path = DB_PATH) -> ExecutionResult:
    """Validate a hand-authored plan and run the executor to freeze grounding."""
    plan = InterpretationPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    return execute_plan(plan, db_path, original_query=query)


def main() -> None:
    p = argparse.ArgumentParser(description="Freeze grounding from an authored plan")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--case-id", required=True)
    p.add_argument("--gold-dir", type=Path, default=Path("data/eval/narrator_gold"))
    p.add_argument("--db-path", type=Path, default=DB_PATH)
    args = p.parse_args()
    result = grounding_from_plan_file(args.plan, args.query, args.db_path)
    case_dir = args.gold_dir / args.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "query.txt").write_text(args.query, encoding="utf-8")
    (case_dir / "grounding.json").write_text(result.model_dump_json(indent=2),
                                             encoding="utf-8")
    print(f"Wrote {case_dir/'grounding.json'} "
          f"({result.total_record_count} records). Now author gold.md.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/scripts/eval/test_author_gold_grounding.py -v`
Expected: PASS (requires `data/index/bibliographic.db`; if absent in CI, mark with `pytest.mark.skipif(not Path(...).exists())`)

- [ ] **Step 5: Commit**

```bash
git add scripts/eval/author_gold_grounding.py tests/scripts/eval/test_author_gold_grounding.py
git commit -m "$(cat <<'EOF'
feat(eval): add $0 grounding generator from authored plans

Validates an Opus-authored InterpretationPlan and runs the pure-DB executor to
freeze grounding.json — the Phase-2 'simulate the interpreter without an API
key' path.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 2 — Gold authoring (Opus 4.8, in-session, $0) — GATED

This phase is performed by Opus 4.8 in the active session, not by a subagent. It produces
`data/eval/narrator_gold/<case_id>/{query.txt, grounding.json, gold.md}` for ~11 cases.

**Per case, Opus:**
1. Writes the query and an `InterpretationPlan` JSON that the production interpreter would
   plausibly produce (simulating the interpreter).
2. Runs `poetry run python -m scripts.eval.author_gold_grounding --plan <case>.plan.json
   --query "<q>" --case-id <case_id>` to freeze `grounding.json` (pure DB, $0).
3. Reads the frozen grounding and authors `gold.md` applying the narrator's 7 evidence rules
   (`scripts/chat/narrator.py:NARRATOR_SYSTEM_PROMPT`): exact counts, only-grounded specifics,
   labeled general knowledge, woven links, honest empty-set handling.

**Case list (~11):** publisher retrieval (small) · place retrieval (medium) · agent+role ·
multi-filter (Hebrew + place + date range) · semantic subject concept (#63) · aggregation /
analytical · entity exploration with enrichment links · large result set (100+) · empty /
zero-result in-scope · Hebrew-language query · ambiguous query. (See the design spec §5.2.)

**Quality bar for each gold.md:** zero fabrication; every specific traceable to
`grounding.json`; exact counts; links present where grounding has them; empty-set cases say so
plainly. Write a `manifest.json` listing `{case_id, query, intent_type, language, set_size_bucket}`.

- [ ] **GATE — user reviews & approves the gold set.** Present the ~11 cases (query, record
  counts, gold narrative) for the user to approve before ANY paid call. Do not proceed to
  Phase 3 without explicit approval. (Per project policy: show data for approval; never spend
  on paid LLM calls without sign-off.)

- [ ] **Commit the approved gold set:**

```bash
git add data/eval/narrator_gold/
git commit -m "$(cat <<'EOF'
test(eval): add Opus-authored narrator gold set (11 cases)

Frozen grounding + gold narratives across publisher/place/agent/subject/
aggregation/enrichment/large-set/empty/Hebrew/ambiguous cases. Authored
in-session ($0); grounding generated via the pure-DB executor.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

# Phase 3 — Paid batch eval — GATED

- [ ] **Step 1: Verify model strings + batch eligibility (free).**

Run:
```bash
poetry run python -c "from openai import OpenAI; ids={m.id for m in OpenAI().models.list()}; \
print([m for m in ['gpt-4.1','gpt-4.1-mini','gpt-5-mini','gpt-5.4-mini','gpt-5.4'] if m in ids])"
```
Expected: all five present. If a string differs, update `--models`/`--judge-model` and the
`PRICING` table; fall back to `gpt-5.2`/`gpt-5.1` for the judge if `gpt-5.4` is unavailable.

- [ ] **Step 2: Dry-run cost check (no submit).**

Run:
```bash
poetry run python -m scripts.eval.run_narrator_gold_eval \
  --models gpt-4.1,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini --judge-model gpt-5.4 \
  --cost-ceiling 2.00 --output-dir data/eval/runs/2026-06-14-narrator-gold --dry-run
```
Expected: prints projected cost (~$0.5–0.8) ≤ $2.00, writes `narration_batch.jsonl`.

- [ ] **GATE — explicit user go-ahead to spend.** Confirm the projected cost with the user
  before the real run.

- [ ] **Step 3: Full paid run (batched).**

Run:
```bash
poetry run python -m scripts.eval.run_narrator_gold_eval \
  --models gpt-4.1,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini \
  --judge-model gpt-5.4 --judge-reasoning-effort low --batch --cost-ceiling 2.00 \
  --max-narration-tokens 2000 --max-judge-tokens 1200 \
  --output-dir data/eval/runs/2026-06-14-narrator-gold
```
Expected: two batch jobs complete; `results.json` + `REPORT.md` written.

- [ ] **Step 4: Review + commit the run artifacts.**

```bash
git add data/eval/runs/2026-06-14-narrator-gold/
git commit -m "$(cat <<'EOF'
test(eval): add narrator gold-standard eval run results

Ranked quality (reference-anchored rubric) x measured cost for gpt-4.1,
gpt-5.4-mini, gpt-5-mini, gpt-4.1-mini judged against the Opus gold.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5:** Summarize findings for the user; the production narrator-model decision is a
  separate follow-up informed by this report (out of scope for this plan).

---

## Self-Review Notes (author checklist — completed)

- **Spec coverage:** gold generation (Tasks 3, 10, Phase 2) · frozen grounding (Task 3) ·
  ~11-case coverage (Phase 2) · reference-anchored rubric + fabrication cap (Tasks 5–6) ·
  judge gpt-5.4 + reasoning_effort low (Tasks 6–7, 9) · batch everything (Tasks 8–9) ·
  bounded grounding (Task 4) · max_completion_tokens caps (Task 7) · $2.00 ceiling guard
  (Tasks 2, 9) · cost estimate (Task 1) · report (Task 9) · gates (Phases 2–3). All mapped.
- **Type consistency:** `GoldCase`, `ExecutionResult`, `NarratorResponseLLM`,
  `NarratorGoldJudgment`/`GoldScore`, `custom_id` scheme `case::model[::judge]` are used
  consistently across tasks.
- **Open item carried forward:** confirm `InterpretationPlan` required fields before the
  Task 10 empty-plan test (noted inline); verify gpt-5.x model strings in Phase 3 Step 1.
