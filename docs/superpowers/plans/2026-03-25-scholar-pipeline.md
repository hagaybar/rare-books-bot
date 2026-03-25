# Scholar Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the rigid detector chain with a three-stage scholar pipeline (Interpret → Execute → Narrate) that handles diverse query styles with scholarly depth while maintaining strict evidence boundaries.

**Architecture:** Two LLM calls sandwich a deterministic executor. The Interpreter LLM produces a structured plan of execution steps and scholarly directives. The Executor walks those steps via SQL/graph queries and produces verified results. The Narrator LLM composes a scholarly response grounded only in verified data.

**Tech Stack:** Python 3.11+, Pydantic v2, OpenAI Responses API (structured output), SQLite, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-scholar-pipeline-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `scripts/chat/plan_models.py` | All shared Pydantic models: `InterpretationPlan`, `ExecutionStep`, `ScholarlyDirective`, `StepAction`, typed params models, step output types, `ExecutionResult`, `ScholarResponse`, `GroundingData`, `RecordSummary`, `AgentSummary`, `GroundingLink`, `SessionContext` |
| `scripts/chat/interpreter.py` | Stage 1: LLM call that produces `InterpretationPlan` from user query + session context |
| `scripts/chat/executor.py` | Stage 2: Deterministic plan walker — step handlers, `$step_N` resolution, grounding/link collection |
| `scripts/chat/narrator.py` | Stage 3: LLM call that produces `ScholarResponse` from `ExecutionResult` |
| `tests/scripts/chat/test_plan_models.py` | Model validation tests |
| `tests/scripts/chat/test_interpreter.py` | Interpreter schema + snapshot tests (mocked LLM) |
| `tests/scripts/chat/test_executor.py` | Executor handler + plan walkthrough tests (in-memory SQLite) |
| `tests/scripts/chat/test_narrator.py` | Narrator grounding compliance tests (mocked LLM) |
| `tests/app/test_scholar_pipeline.py` | Integration: end-to-end pipeline tests, WebSocket streaming |

### Modified files

| File | Change |
|------|--------|
| `scripts/chat/aggregation.py` | Absorb `AggregationResult` model from `exploration_agent.py` (add ~10 lines) |
| `app/api/main.py` | Replace `handle_query_definition_phase` routing chain with 3-stage pipeline (~600 lines removed, ~80 added) |
| `scripts/utils/primo.py` | **Create**: Extract `_generate_primo_url()` from `app/api/metadata.py:910` so executor can use it without importing from `app/` |
| `app/api/metadata.py` | Update to import `generate_primo_url` from `scripts/utils/primo.py` (thin redirect) |

### Removed files (deferred to Task 8)

| File | Replaced By |
|------|-------------|
| `scripts/chat/intent_agent.py` | `interpreter.py` |
| `scripts/chat/analytical_router.py` | Interpreter |
| `scripts/chat/formatter.py` | `narrator.py` |
| `scripts/chat/narrative_agent.py` | `narrator.py` |
| `scripts/chat/thematic_context.py` | Narrator |
| `scripts/chat/clarification.py` | Interpreter clarification field |
| `scripts/chat/curator.py` | Narrator + curation_engine |
| `scripts/chat/exploration_agent.py` | Interpreter + executor |
| `scripts/query/llm_compiler.py` | Interpreter |
| `scripts/query/execute.py` | Executor |

---

## Task Dependency Graph

```
Task 1 (plan_models.py)
  ├── Task 2 (interpreter.py)
  ├── Task 3 (executor.py)
  │     └── Task 4 (executor handlers)
  └── Task 5 (narrator.py)
        └── Task 6 (API integration)
              └── Task 7 (integration tests + evidence reports)
                    └── Task 8 (cleanup removed modules)
```

Tasks 2, 3, and 5 can be parallelized after Task 1 is complete.

---

### Task 1: Plan Models

**Files:**
- Create: `scripts/chat/plan_models.py`
- Create: `tests/scripts/chat/test_plan_models.py`

All shared Pydantic models for the three-stage pipeline. This is the contract between interpreter, executor, and narrator. Built and tested first so all downstream tasks import from here.

- [ ] **Step 1: Write model validation tests**

Create `tests/scripts/chat/test_plan_models.py`:

```python
"""Tests for scholar pipeline shared models."""
import pytest
from pydantic import ValidationError


def test_step_action_enum_values():
    """All 7 executor actions are defined."""
    from scripts.chat.plan_models import StepAction
    assert len(StepAction) == 7
    assert StepAction.RESOLVE_AGENT == "resolve_agent"
    assert StepAction.RETRIEVE == "retrieve"
    assert StepAction.AGGREGATE == "aggregate"


def test_resolve_agent_params_valid():
    from scripts.chat.plan_models import ResolveAgentParams
    p = ResolveAgentParams(name="Joseph Karo", variants=["קארו, יוסף בן אפרים"])
    assert p.name == "Joseph Karo"
    assert len(p.variants) == 1


def test_resolve_agent_params_defaults():
    from scripts.chat.plan_models import ResolveAgentParams
    p = ResolveAgentParams(name="Maimonides")
    assert p.variants == []


def test_retrieve_params_reuses_filter_model():
    """RetrieveParams.filters uses the existing Filter model."""
    from scripts.chat.plan_models import RetrieveParams
    from scripts.schemas.query_plan import Filter, FilterField, FilterOp
    f = Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="test")
    p = RetrieveParams(filters=[f])
    assert p.scope == "full_collection"
    assert len(p.filters) == 1


def test_retrieve_params_with_step_ref_scope():
    from scripts.chat.plan_models import RetrieveParams
    p = RetrieveParams(filters=[], scope="$step_0")
    assert p.scope == "$step_0"


def test_execution_step_valid():
    from scripts.chat.plan_models import ExecutionStep, StepAction, ResolveAgentParams
    step = ExecutionStep(
        action=StepAction.RESOLVE_AGENT,
        params=ResolveAgentParams(name="Karo"),
        label="Resolve Karo",
    )
    assert step.depends_on == []


def test_scholarly_directive_freeform():
    from scripts.chat.plan_models import ScholarlyDirective
    d = ScholarlyDirective(
        directive="contextualize",
        params={"theme": "Jewish legal codification"},
        label="Historical context",
    )
    assert d.directive == "contextualize"


def test_interpretation_plan_with_clarification():
    from scripts.chat.plan_models import InterpretationPlan
    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Ambiguous entity",
        execution_steps=[],
        directives=[],
        confidence=0.55,
        clarification="Which Karo do you mean?",
    )
    assert plan.clarification is not None
    assert plan.confidence < 0.7


def test_interpretation_plan_without_clarification():
    from scripts.chat.plan_models import InterpretationPlan, ExecutionStep, StepAction, ResolveAgentParams
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Clear query",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Karo"),
                label="Resolve",
            )
        ],
        directives=[],
        confidence=0.95,
    )
    assert plan.clarification is None
    assert len(plan.execution_steps) == 1


def test_record_summary_fields():
    from scripts.chat.plan_models import RecordSummary
    r = RecordSummary(
        mms_id="990001234",
        title="Shulchan Aruch",
        date_display="Venice, 1565",
        place="venice",
        publisher="bragadin",
        language="heb",
        agents=["קארו, יוסף בן אפרים"],
        subjects=["Jewish law"],
        primo_url="https://primo.example.com/990001234",
        source_steps=[1],
    )
    assert r.mms_id == "990001234"


def test_agent_summary_fields():
    from scripts.chat.plan_models import AgentSummary
    a = AgentSummary(
        canonical_name="קארו, יוסף בן אפרים",
        variants=["Joseph Karo", "Caro, Joseph"],
        birth_year=1488,
        death_year=1575,
        occupations=["rabbi", "posek"],
        description="Author of the Shulchan Aruch",
        record_count=3,
        links=[],
    )
    assert a.birth_year == 1488


def test_grounding_link():
    from scripts.chat.plan_models import GroundingLink
    link = GroundingLink(
        entity_type="agent",
        entity_id="Q193460",
        label="Joseph Karo on Wikipedia",
        url="https://en.wikipedia.org/wiki/Joseph_Karo",
        source="wikipedia",
    )
    assert link.source == "wikipedia"


def test_step_result_ok():
    from scripts.chat.plan_models import StepResult, RecordSet
    sr = StepResult(
        step_index=0,
        action="retrieve",
        label="Find works",
        status="ok",
        data=RecordSet(mms_ids=["990001"], total_count=1, filters_applied=[]),
        record_count=1,
    )
    assert sr.status == "ok"


def test_step_result_empty():
    from scripts.chat.plan_models import StepResult, RecordSet
    sr = StepResult(
        step_index=0,
        action="retrieve",
        label="Find works",
        status="empty",
        data=RecordSet(mms_ids=[], total_count=0, filters_applied=[]),
        record_count=0,
    )
    assert sr.status == "empty"


def test_execution_result_complete():
    from scripts.chat.plan_models import ExecutionResult, GroundingData
    er = ExecutionResult(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        original_query="test",
        session_context=None,
        truncated=False,
    )
    assert not er.truncated


def test_scholar_response():
    from scripts.chat.plan_models import ScholarResponse, GroundingData
    sr = ScholarResponse(
        narrative="Joseph Karo was...",
        suggested_followups=["What about Maimonides?"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={"intents": ["entity_exploration"]},
    )
    assert len(sr.suggested_followups) == 1


def test_resolved_entity():
    from scripts.chat.plan_models import ResolvedEntity
    re = ResolvedEntity(
        query_name="Joseph Karo",
        matched_values=["קארו, יוסף בן אפרים"],
        match_method="alias_exact",
        confidence=0.95,
    )
    assert len(re.matched_values) == 1


def test_connection_graph():
    from scripts.chat.plan_models import ConnectionGraph
    cg = ConnectionGraph(
        connections=[{"agent_a": "Karo", "agent_b": "Alkabetz", "shared_records": 1, "shared_mms_ids": ["990001"]}],
        isolated=["Isserles"],
    )
    assert len(cg.connections) == 1
    assert len(cg.isolated) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/chat/test_plan_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.chat.plan_models'`

- [ ] **Step 3: Implement plan_models.py**

Create `scripts/chat/plan_models.py` with all models from the spec. Key classes:
- Enums: `StepAction`
- Typed params: `ResolveAgentParams`, `ResolvePublisherParams`, `RetrieveParams`, `AggregateParams`, `FindConnectionsParams`, `EnrichParams`, `SampleParams`
- Step output types: `ResolvedEntity`, `RecordSet`, `AggregationResult` (executor-specific, distinct from chat aggregation module), `ConnectionGraph`, `EnrichmentBundle`
- Plan: `ExecutionStep`, `ScholarlyDirective`, `InterpretationPlan`
- Execution: `StepResult`, `RecordSummary`, `AgentSummary`, `GroundingLink`, `GroundingData`, `SessionContext`, `ExecutionResult`
- Response: `ScholarResponse`

Import the existing `Filter` model from `scripts.schemas.query_plan` for `RetrieveParams.filters`.

Use `from __future__ import annotations` for forward references. Use `Annotated[Union[...], Field(discriminator=...)]` for the params union on `ExecutionStep` if Pydantic v2 supports it, otherwise use a plain `Union` with a validator.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/chat/test_plan_models.py -v`
Expected: All 20 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/plan_models.py tests/scripts/chat/test_plan_models.py
git commit -m "feat: add scholar pipeline shared models (plan_models.py)"
```

---

### Task 2: Interpreter

**Files:**
- Create: `scripts/chat/interpreter.py`
- Create: `tests/scripts/chat/test_interpreter.py`

**Depends on:** Task 1 (plan_models.py)

The interpreter receives a user query and session context, calls the LLM, and returns an `InterpretationPlan`. Uses OpenAI Responses API with Pydantic schema enforcement (same pattern as existing `intent_agent.py`).

- [ ] **Step 1: Write interpreter tests with mocked LLM**

Create `tests/scripts/chat/test_interpreter.py`:

```python
"""Tests for the interpreter (Stage 1).

All tests mock the OpenAI client — no API key needed.
"""
import json
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from scripts.chat.plan_models import (
    InterpretationPlan, ExecutionStep, ScholarlyDirective,
    StepAction, ResolveAgentParams, RetrieveParams,
    AggregateParams, SessionContext,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp
from scripts.chat.models import Message


# =============================================================================
# Fixtures
# =============================================================================

def _make_plan(**overrides) -> InterpretationPlan:
    """Helper to build a valid InterpretationPlan for mocking."""
    defaults = dict(
        intents=["retrieval"],
        reasoning="Test plan",
        execution_steps=[],
        directives=[],
        confidence=0.95,
        clarification=None,
    )
    defaults.update(overrides)
    return InterpretationPlan(**defaults)


def _mock_openai_response(plan: InterpretationPlan):
    """Create a mock OpenAI response that returns the given plan."""
    mock_parsed = MagicMock()
    mock_parsed.model_dump.return_value = plan.model_dump()

    # Simulate the OpenAI Responses API parsed output
    mock_output = MagicMock()
    mock_output.parsed = plan  # Return actual Pydantic object

    mock_response = MagicMock()
    mock_response.output = [mock_output]

    return mock_response


# =============================================================================
# Schema validation tests
# =============================================================================

def test_interpret_returns_interpretation_plan():
    """interpret() returns a valid InterpretationPlan."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(
        intents=["retrieval"],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")],
                ),
                label="Books from Venice",
            )
        ],
    )

    with patch("scripts.chat.interpreter._call_llm", return_value=plan):
        import asyncio
        result = asyncio.run(interpret("books from Venice", session_context=None))

    assert isinstance(result, InterpretationPlan)
    assert result.intents == ["retrieval"]
    assert len(result.execution_steps) == 1
    assert result.execution_steps[0].action == StepAction.RETRIEVE


def test_interpret_entity_exploration():
    """Entity exploration query produces resolve + retrieve + enrich steps."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(
        intents=["entity_exploration"],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Joseph Karo", variants=["קארו, יוסף בן אפרים"]),
                label="Resolve Karo",
            ),
        ],
        directives=[
            ScholarlyDirective(directive="expand", params={"focus": "Joseph Karo"}, label="Expand"),
        ],
    )

    with patch("scripts.chat.interpreter._call_llm", return_value=plan):
        import asyncio
        result = asyncio.run(interpret("who was Joseph Karo?", session_context=None))

    assert "entity_exploration" in result.intents
    assert result.execution_steps[0].action == StepAction.RESOLVE_AGENT


def test_interpret_clarification():
    """Low-confidence query returns clarification."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(
        intents=["entity_exploration"],
        confidence=0.55,
        clarification="Which Karo do you mean?",
    )

    with patch("scripts.chat.interpreter._call_llm", return_value=plan):
        import asyncio
        result = asyncio.run(interpret("tell me about Karo", session_context=None))

    assert result.clarification is not None
    assert result.confidence < 0.7


def test_interpret_with_session_context():
    """Follow-up query receives session context."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(intents=["follow_up"])

    ctx = SessionContext(
        recent_messages=[
            Message(role="user", content="books by Karo"),
            Message(role="assistant", content="Found 3 works..."),
        ],
        previous_plan=None,
        previous_record_ids=["990001", "990002"],
        previous_query="books by Karo",
    )

    with patch("scripts.chat.interpreter._call_llm", return_value=plan) as mock_llm:
        import asyncio
        result = asyncio.run(interpret("only from Venice", session_context=ctx))

    # Verify session context was passed to LLM
    call_args = mock_llm.call_args
    assert call_args is not None


def test_interpret_out_of_scope():
    """Out-of-scope query returns empty steps."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(
        intents=["out_of_scope"],
        reasoning="Weather question, not bibliographic",
        confidence=0.99,
    )

    with patch("scripts.chat.interpreter._call_llm", return_value=plan):
        import asyncio
        result = asyncio.run(interpret("what's the weather?", session_context=None))

    assert "out_of_scope" in result.intents
    assert len(result.execution_steps) == 0


def test_interpret_mixed_intents():
    """Complex query produces multiple intent labels."""
    from scripts.chat.interpreter import interpret

    plan = _make_plan(intents=["entity_exploration", "comparison"])

    with patch("scripts.chat.interpreter._call_llm", return_value=plan):
        import asyncio
        result = asyncio.run(interpret("compare Karo and Maimonides", session_context=None))

    assert len(result.intents) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/chat/test_interpreter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.chat.interpreter'`

- [ ] **Step 3: Implement interpreter.py**

Create `scripts/chat/interpreter.py`. Key structure:

```python
"""Scholar Pipeline Stage 1: Query Interpreter.

Receives a user query and session context, calls the LLM,
and returns an InterpretationPlan with execution steps and
scholarly directives.

Replaces: intent_agent.py, analytical_router.py, clarification.py
"""
import os
from typing import Optional

from openai import OpenAI

from scripts.chat.plan_models import (
    InterpretationPlan, SessionContext,
)
from scripts.utils.llm_logger import log_llm_call

# The interpreter system prompt — defines the scholar persona,
# available step types, and examples.
INTERPRETER_SYSTEM_PROMPT = """..."""  # Full prompt with step vocabulary, examples

async def interpret(
    query: str,
    session_context: Optional[SessionContext] = None,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
) -> InterpretationPlan:
    """Interpret a user query into an execution plan."""
    plan = await _call_llm(query, session_context, model, api_key)
    _validate_step_refs(plan)  # Check $step_N references are valid
    return plan


async def _call_llm(...) -> InterpretationPlan:
    """Call OpenAI Responses API with schema enforcement."""
    # Uses client.responses.parse() with InterpretationPlan schema
    # Same pattern as intent_agent.py lines 370-430
    ...


def _validate_step_refs(plan: InterpretationPlan) -> None:
    """Validate $step_N references: no circular deps, no out-of-range."""
    ...


def _build_user_prompt(query, session_context) -> str:
    """Assemble user prompt with session context."""
    ...
```

The system prompt should include:
- Available `StepAction` types with param descriptions
- Available scholarly directive types
- Intent classification guidance
- Examples for each query type (from spec: entity_exploration, comparison, retrieval)
- Clarification guidance (when to set `clarification` field)
- Century conversion rules, country vs city distinction (from existing intent_agent prompt)

Reference the existing `INTENT_AGENT_SYSTEM_PROMPT` in `scripts/chat/intent_agent.py:168-335` for domain-specific rules (filter fields, operations, century conversion) that must be preserved.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/chat/test_interpreter.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/interpreter.py tests/scripts/chat/test_interpreter.py
git commit -m "feat: add interpreter (Stage 1) with LLM plan generation"
```

---

### Task 3: Executor Core + $step_N Resolution

**Files:**
- Create: `scripts/chat/executor.py`
- Create: `tests/scripts/chat/test_executor.py`

**Depends on:** Task 1 (plan_models.py)

The executor walks execution steps in dependency order, resolves `$step_N` references, and produces an `ExecutionResult`. This task implements the core framework; Task 4 adds the individual step handlers.

- [ ] **Step 1: Write executor core tests**

Create `tests/scripts/chat/test_executor.py`:

```python
"""Tests for the executor (Stage 2) — core framework.

Tests dependency resolution, $step_N substitution, and error handling.
All tests use in-memory SQLite, no LLM needed.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.chat.plan_models import (
    InterpretationPlan, ExecutionStep, ScholarlyDirective,
    StepAction, ResolveAgentParams, RetrieveParams, AggregateParams,
    ExecutionResult, StepResult, ResolvedEntity, RecordSet,
    GroundingData,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def empty_plan():
    return InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.95,
    )


# =============================================================================
# Core execution tests
# =============================================================================

def test_execute_empty_plan(empty_plan):
    """Empty plan returns empty result, not an error."""
    from scripts.chat.executor import execute_plan
    result = execute_plan(empty_plan, db_path=Path(":memory:"))
    assert isinstance(result, ExecutionResult)
    assert len(result.steps_completed) == 0
    assert result.truncated is False


def test_directives_passed_through():
    """Scholarly directives are forwarded to the result unchanged."""
    from scripts.chat.executor import execute_plan
    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Test",
        execution_steps=[],
        directives=[
            ScholarlyDirective(directive="expand", params={"focus": "Karo"}, label="Expand"),
            ScholarlyDirective(directive="contextualize", params={"theme": "law"}, label="Context"),
        ],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.directives) == 2
    assert result.directives[0].directive == "expand"


def test_step_dependency_ordering():
    """Steps are executed in dependency order."""
    from scripts.chat.executor import _resolve_execution_order
    steps = [
        ExecutionStep(action=StepAction.RETRIEVE, params=RetrieveParams(filters=[]), label="S0"),
        ExecutionStep(action=StepAction.AGGREGATE, params=AggregateParams(field="date_decade", scope="$step_0"), label="S1", depends_on=[0]),
    ]
    order = _resolve_execution_order(steps)
    assert order == [0, 1]


def test_circular_dependency_rejected():
    """Circular dependencies produce an error, not infinite loop."""
    from scripts.chat.executor import _resolve_execution_order, PlanValidationError
    steps = [
        ExecutionStep(action=StepAction.RETRIEVE, params=RetrieveParams(filters=[]), label="S0", depends_on=[1]),
        ExecutionStep(action=StepAction.RETRIEVE, params=RetrieveParams(filters=[]), label="S1", depends_on=[0]),
    ]
    with pytest.raises(PlanValidationError, match="circular"):
        _resolve_execution_order(steps)


def test_out_of_range_step_ref_rejected():
    """$step_99 when only 2 steps exist raises error."""
    from scripts.chat.executor import _resolve_execution_order, PlanValidationError
    steps = [
        ExecutionStep(action=StepAction.RETRIEVE, params=RetrieveParams(filters=[]), label="S0", depends_on=[99]),
    ]
    with pytest.raises(PlanValidationError, match="out of range"):
        _resolve_execution_order(steps)


def test_step_ref_resolution_resolve_agent_to_retrieve():
    """$step_0 from resolve_agent resolves to matched_values in retrieve filter."""
    from scripts.chat.executor import _resolve_step_ref

    resolved = ResolvedEntity(
        query_name="Karo",
        matched_values=["קארו, יוסף בן אפרים"],
        match_method="alias_exact",
        confidence=0.95,
    )
    step_results = {0: StepResult(
        step_index=0, action="resolve_agent", label="Resolve",
        status="ok", data=resolved, record_count=None,
    )}

    value = _resolve_step_ref("$step_0", step_results, context="value")
    assert value == ["קארו, יוסף בן אפרים"]


def test_step_ref_resolution_retrieve_to_aggregate_scope():
    """$step_0 from retrieve resolves to mms_ids for aggregate scope."""
    from scripts.chat.executor import _resolve_step_ref

    record_set = RecordSet(mms_ids=["990001", "990002"], total_count=2, filters_applied=[])
    step_results = {0: StepResult(
        step_index=0, action="retrieve", label="Retrieve",
        status="ok", data=record_set, record_count=2,
    )}

    value = _resolve_step_ref("$step_0", step_results, context="scope")
    assert value == ["990001", "990002"]


def test_unknown_action_skipped():
    """Unknown step action is marked as error, not a crash."""
    from scripts.chat.executor import execute_plan
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[
            ExecutionStep(action="search_fulltext", params=RetrieveParams(filters=[]), label="Bad step"),
        ],
        directives=[],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert result.steps_completed[0].status == "error"
    assert "Unknown action" in result.steps_completed[0].error_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/chat/test_executor.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement executor core**

Create `scripts/chat/executor.py`. Key structure:

```python
"""Scholar Pipeline Stage 2: Deterministic Plan Executor.

Walks execution steps in dependency order, runs DB queries,
resolves aliases, computes aggregations, and collects grounding links.

Replaces: execute.py, analytical_router.py routing
Reuses: db_adapter.py, aggregation.py, cross_reference.py,
        agent_authority.py, publisher_authority.py, curation_engine.py
"""
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.chat.plan_models import (
    InterpretationPlan, ExecutionStep, ExecutionResult,
    StepResult, StepAction, GroundingData, GroundingLink,
    RecordSummary, AgentSummary, SessionContext,
    ResolvedEntity, RecordSet, AggregationResult as PlanAggResult,
    ConnectionGraph, EnrichmentBundle,
)


class PlanValidationError(Exception):
    """Raised when the plan contains invalid structure."""
    pass


def execute_plan(
    plan: InterpretationPlan,
    db_path: Path,
    session_context: Optional[SessionContext] = None,
) -> ExecutionResult:
    """Execute an InterpretationPlan and return verified results."""
    ...


def _resolve_execution_order(steps: List[ExecutionStep]) -> List[int]:
    """Topological sort of steps by depends_on. Raises on cycles/bad refs."""
    ...


def _resolve_step_ref(
    ref: str,
    step_results: Dict[int, StepResult],
    context: str,  # "value", "scope", "agents", "targets"
) -> Any:
    """Resolve a $step_N reference to concrete data."""
    ...


def _collect_grounding(
    step_results: Dict[int, StepResult],
    db_path: Path,
) -> GroundingData:
    """Sweep all results and collect records, agents, links."""
    ...


# Per-action handlers (stubs — implemented in Task 4)
def _handle_resolve_agent(params, db_path, step_results): ...
def _handle_resolve_publisher(params, db_path, step_results): ...
def _handle_retrieve(params, db_path, step_results): ...
def _handle_aggregate(params, db_path, step_results): ...
def _handle_find_connections(params, db_path, step_results): ...
def _handle_enrich(params, db_path, step_results): ...
def _handle_sample(params, db_path, step_results): ...
```

Implement:
1. `execute_plan()` — main entry point
2. `_resolve_execution_order()` — topological sort with cycle detection
3. `_resolve_step_ref()` — typed resolution based on context
4. Handler dispatch (calls per-action handlers, catches exceptions, marks status)
5. Stub handlers that return empty results (filled in Task 4)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/chat/test_executor.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/executor.py tests/scripts/chat/test_executor.py
git commit -m "feat: add executor core (Stage 2) with dependency resolution"
```

---

### Task 4: Executor Step Handlers

**Files:**
- Modify: `scripts/chat/executor.py`
- Modify: `scripts/chat/aggregation.py` (absorb `AggregationResult`)
- Modify: `tests/scripts/chat/test_executor.py` (add handler tests)

**Depends on:** Task 3 (executor core)

Implement the 7 step handlers that do real DB work. Each handler reuses an existing module.

- [ ] **Step 1: Migrate AggregationResult model**

In `scripts/chat/aggregation.py`, add the `AggregationResult` model that's currently in `exploration_agent.py`. Add it near the top of the file so it can be imported from aggregation directly. Update the existing import in `exploration_agent.py` to point to `aggregation.py` (or leave both for now — cleanup in Task 8).

- [ ] **Step 2: Write handler tests**

Add to `tests/scripts/chat/test_executor.py`. Each handler test needs a test SQLite DB fixture:

```python
# =============================================================================
# Test DB fixture
# =============================================================================

@pytest.fixture
def test_db(tmp_path):
    """Create a minimal test SQLite DB with schema and sample data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY, mms_id TEXT UNIQUE, source_file TEXT, created_at TEXT, jsonl_line_number INTEGER
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, occurrence INTEGER,
            date_raw TEXT, place_raw TEXT, publisher_raw TEXT, manufacturer_raw TEXT, source_tags TEXT,
            date_start INTEGER, date_end INTEGER, date_label TEXT, date_confidence REAL, date_method TEXT,
            place_norm TEXT, place_display TEXT, place_confidence REAL, place_method TEXT,
            publisher_norm TEXT, publisher_display TEXT, publisher_confidence REAL, publisher_method TEXT,
            country_code TEXT, country_name TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
            agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT, authority_uri TEXT,
            agent_norm TEXT, agent_confidence REAL, agent_method TEXT, agent_notes TEXT,
            role_norm TEXT, role_confidence REAL, role_method TEXT, provenance_json TEXT
        );
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT, source_tag TEXT,
            scheme TEXT, heading_lang TEXT, authority_uri TEXT, parts TEXT, source TEXT
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER, title_raw TEXT, title_norm TEXT,
            title_type TEXT, source_tag TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT,
            agent_type TEXT, dates_active TEXT, date_start INTEGER, date_end INTEGER,
            notes TEXT, sources TEXT, confidence REAL, authority_uri TEXT,
            wikidata_id TEXT, viaf_id TEXT, nli_id TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER, alias_form TEXT, alias_form_lower TEXT,
            alias_type TEXT, script TEXT, language TEXT, is_primary INTEGER, priority INTEGER,
            notes TEXT, created_at TEXT
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE, nli_id TEXT, wikidata_id TEXT,
            viaf_id TEXT, isni_id TEXT, loc_id TEXT, label TEXT, description TEXT,
            person_info TEXT, place_info TEXT, image_url TEXT, wikipedia_url TEXT,
            source TEXT, confidence REAL, fetched_at TEXT, expires_at TEXT
        );
        CREATE TABLE publisher_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT, canonical_name_lower TEXT,
            type TEXT, dates_active TEXT, date_start INTEGER, date_end INTEGER,
            location TEXT, notes TEXT, sources TEXT, confidence REAL, is_missing_marker INTEGER,
            viaf_id TEXT, wikidata_id TEXT, cerl_id TEXT, branch TEXT, primary_language TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE publisher_variants (
            id INTEGER PRIMARY KEY, authority_id INTEGER, variant_form TEXT, variant_form_lower TEXT,
            script TEXT, language TEXT, is_primary INTEGER, priority INTEGER, notes TEXT, created_at TEXT
        );

        -- Sample data: Joseph Karo with 2 books
        INSERT INTO records VALUES (1, '990001234', 'test.xml', '2024-01-01', 1);
        INSERT INTO records VALUES (2, '990005678', 'test.xml', '2024-01-01', 2);

        INSERT INTO imprints VALUES (1, 1, 0, '1565', 'Venice', 'Bragadin', NULL, '["264"]',
            1565, 1565, '1565', 0.99, 'exact', 'venice', 'Venice', 0.95, 'place_alias_map',
            'bragadin', 'Bragadin', 0.95, 'publisher_authority', 'it', 'italy');
        INSERT INTO imprints VALUES (2, 2, 0, '1698', 'Amsterdam', 'Proops', NULL, '["264"]',
            1698, 1698, '1698', 0.99, 'exact', 'amsterdam', 'Amsterdam', 0.95, 'place_alias_map',
            'proops', 'Proops', 0.95, 'publisher_authority', 'ne', 'netherlands');

        INSERT INTO agents VALUES (1, 1, 0, 'קארו, יוסף בן אפרים', 'personal', 'author', 'relator_code',
            'http://nli.org/auth/1', 'קארו, יוסף בן אפרים', 0.95, 'base_clean', NULL,
            'author', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES (2, 2, 0, 'קארו, יוסף בן אפרים', 'personal', 'author', 'relator_code',
            'http://nli.org/auth/1', 'קארו, יוסף בן אפרים', 0.95, 'base_clean', NULL,
            'author', 0.95, 'relator_code', '[]');

        INSERT INTO subjects VALUES (1, 1, 'Jewish law', '650', 'lcsh', 'eng', NULL, '{}', '[]');

        INSERT INTO titles VALUES (1, 1, 'Shulchan Aruch', 'shulchan aruch', 'main', '245');
        INSERT INTO titles VALUES (2, 2, 'Shulchan Aruch', 'shulchan aruch', 'main', '245');

        INSERT INTO agent_authorities VALUES (1, 'קארו, יוסף בן אפרים', 'קארו, יוסף בן אפרים',
            'personal', '1488-1575', 1488, 1575, NULL, NULL, 0.95, 'http://nli.org/auth/1',
            'Q193460', NULL, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO agent_aliases VALUES (1, 1, 'Joseph Karo', 'joseph karo', 'cross_script', 'latin', 'eng', 0, 0, NULL, '2024-01-01');
        INSERT INTO agent_aliases VALUES (2, 1, 'Caro, Joseph', 'caro, joseph', 'word_reorder', 'latin', 'eng', 0, 0, NULL, '2024-01-01');

        INSERT INTO authority_enrichment VALUES (1, 'http://nli.org/auth/1', 'NLI001', 'Q193460',
            'VIAF001', NULL, NULL, 'Joseph Karo', 'Rabbi and author of Shulchan Aruch',
            '{"birth_year": 1488, "death_year": 1575, "occupations": ["rabbi", "posek"]}',
            NULL, NULL, 'https://en.wikipedia.org/wiki/Joseph_Karo',
            'wikidata', 0.95, '2024-01-01', '2025-01-01');
    """)
    conn.close()
    return db_path


# =============================================================================
# Handler tests
# =============================================================================

def test_handle_resolve_agent(test_db):
    """resolve_agent finds Karo via alias lookup."""
    from scripts.chat.executor import _handle_resolve_agent
    from scripts.chat.plan_models import ResolveAgentParams

    params = ResolveAgentParams(name="Joseph Karo", variants=["Caro, Joseph"])
    result = _handle_resolve_agent(params, test_db, step_results={})

    assert isinstance(result, ResolvedEntity)
    assert "קארו, יוסף בן אפרים" in result.matched_values
    assert result.match_method != "none"


def test_handle_resolve_agent_not_found(test_db):
    """resolve_agent for unknown name returns empty with match_method='none'."""
    from scripts.chat.executor import _handle_resolve_agent
    from scripts.chat.plan_models import ResolveAgentParams

    params = ResolveAgentParams(name="Nobody Known", variants=[])
    result = _handle_resolve_agent(params, test_db, step_results={})

    assert isinstance(result, ResolvedEntity)
    assert len(result.matched_values) == 0
    assert result.match_method == "none"


def test_handle_retrieve_basic(test_db):
    """retrieve with place filter returns matching records."""
    from scripts.chat.executor import _handle_retrieve
    from scripts.chat.plan_models import RetrieveParams
    from scripts.schemas.query_plan import Filter, FilterField, FilterOp

    params = RetrieveParams(
        filters=[Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")],
    )
    result = _handle_retrieve(params, test_db, step_results={})

    assert isinstance(result, RecordSet)
    assert "990001234" in result.mms_ids
    assert result.total_count >= 1


def test_handle_retrieve_with_scope(test_db):
    """retrieve scoped to $step_N narrows to those record IDs."""
    from scripts.chat.executor import _handle_retrieve
    from scripts.chat.plan_models import RetrieveParams, ResolvedEntity, StepResult, RecordSet

    # Simulate a prior retrieve step that found both records
    prior = StepResult(
        step_index=0, action="retrieve", label="Prior",
        status="ok",
        data=RecordSet(mms_ids=["990001234"], total_count=1, filters_applied=[]),
        record_count=1,
    )

    params = RetrieveParams(filters=[], scope="$step_0")
    result = _handle_retrieve(params, test_db, step_results={0: prior})

    assert isinstance(result, RecordSet)
    # Should be scoped to only mms_id 990001234
    assert all(mms in ["990001234"] for mms in result.mms_ids)


def test_handle_aggregate(test_db):
    """aggregate computes facets over a result set."""
    from scripts.chat.executor import _handle_aggregate
    from scripts.chat.plan_models import AggregateParams, RecordSet, StepResult
    from scripts.chat.plan_models import AggregationResult as PlanAggResult

    prior = StepResult(
        step_index=0, action="retrieve", label="All",
        status="ok",
        data=RecordSet(mms_ids=["990001234", "990005678"], total_count=2, filters_applied=[]),
        record_count=2,
    )

    params = AggregateParams(field="place", scope="$step_0")
    result = _handle_aggregate(params, test_db, step_results={0: prior})

    assert isinstance(result, PlanAggResult)
    assert len(result.facets) > 0


def test_handle_enrich(test_db):
    """enrich fetches authority_enrichment data for resolved agents."""
    from scripts.chat.executor import _handle_enrich
    from scripts.chat.plan_models import EnrichParams, ResolvedEntity, StepResult, EnrichmentBundle

    prior = StepResult(
        step_index=0, action="resolve_agent", label="Resolve",
        status="ok",
        data=ResolvedEntity(
            query_name="Karo",
            matched_values=["קארו, יוסף בן אפרים"],
            match_method="alias_exact",
            confidence=0.95,
        ),
        record_count=None,
    )

    params = EnrichParams(targets="$step_0")
    result = _handle_enrich(params, test_db, step_results={0: prior})

    assert isinstance(result, EnrichmentBundle)
    assert len(result.agents) >= 1
    assert result.agents[0].canonical_name == "קארו, יוסף בן אפרים"


def test_grounding_link_collection(test_db):
    """Grounding collects Primo, Wikipedia, Wikidata links."""
    from scripts.chat.executor import _collect_grounding
    from scripts.chat.plan_models import StepResult, RecordSet, ResolvedEntity, EnrichmentBundle, AgentSummary

    step_results = {
        0: StepResult(
            step_index=0, action="retrieve", label="Retrieve",
            status="ok",
            data=RecordSet(mms_ids=["990001234"], total_count=1, filters_applied=[]),
            record_count=1,
        ),
    }

    grounding = _collect_grounding(step_results, test_db)

    # Should have at least a Primo link for the record
    primo_links = [l for l in grounding.links if l.source == "primo"]
    assert len(primo_links) >= 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/scripts/chat/test_executor.py::test_handle_resolve_agent -v`
Expected: FAIL — handler returns stub/empty result

- [ ] **Step 4: Implement step handlers**

In `scripts/chat/executor.py`, implement each handler:

1. **`_handle_resolve_agent`**: Query `agent_aliases` table for `alias_form_lower` matching name or variants. Fall back to order-insensitive matching (split into tokens, check all tokens present). Use `AgentAuthorityStore` from `scripts/metadata/agent_authority.py`.

2. **`_handle_resolve_publisher`**: Query `publisher_variants` table. Use `PublisherAuthorityStore` pattern.

3. **`_handle_retrieve`**: Convert `RetrieveParams.filters` to a `QueryPlan`, resolve `$step_N` in filter values, call `db_adapter.build_full_query()` + `db_adapter.fetch_candidates()`. If `scope` is set, add `WHERE mms_id IN (...)`.

4. **`_handle_aggregate`**: Resolve `scope` to record IDs, call `aggregation.execute_aggregation()` scoped to those IDs. Map result to `PlanAggResult`.

5. **`_handle_find_connections`**: Resolve agent names from `$step_N`, call `cross_reference.find_connections()`. Map to `ConnectionGraph`.

6. **`_handle_enrich`**: Resolve agent names from `$step_N`, query `authority_enrichment` by `authority_uri` (join through `agents` table). Build `AgentSummary` objects with links.

7. **`_handle_sample`**: Resolve scope to record IDs, apply strategy. `"earliest"` = ORDER BY date_start LIMIT n. `"notable"` = use `curation_engine.score_for_curation()`. `"diverse"` = sample across decades/places.

Also implement `_collect_grounding()`:
- Deduplicate records across all retrieve steps (merge `source_steps`)
- Build `RecordSummary` for each (join records + imprints + titles)
- Build `AgentSummary` for enriched agents
- Collect all links: Primo for records, Wikipedia/Wikidata/NLI/VIAF for agents
- Truncate to 30 records if needed, set `truncated=True`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/scripts/chat/test_executor.py -v`
Expected: All handler tests PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/chat/executor.py scripts/chat/aggregation.py tests/scripts/chat/test_executor.py
git commit -m "feat: implement executor step handlers (resolve, retrieve, aggregate, enrich, connect)"
```

---

### Task 5: Narrator

**Files:**
- Create: `scripts/chat/narrator.py`
- Create: `tests/scripts/chat/test_narrator.py`

**Depends on:** Task 1 (plan_models.py)

The narrator receives `ExecutionResult` and composes a scholarly response. Uses OpenAI Responses API with a rich persona prompt.

- [ ] **Step 1: Write narrator tests with mocked LLM**

Create `tests/scripts/chat/test_narrator.py`:

```python
"""Tests for the narrator (Stage 3).

Tests enforce evidence rules: grounding compliance, no fabrication,
link inclusion. All tests mock the OpenAI client.
"""
from unittest.mock import MagicMock, patch

import pytest

from scripts.chat.plan_models import (
    ExecutionResult, ScholarResponse, GroundingData,
    RecordSummary, AgentSummary, GroundingLink,
    StepResult, RecordSet, ScholarlyDirective,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_execution_result(**overrides) -> ExecutionResult:
    defaults = dict(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        original_query="test query",
        session_context=None,
        truncated=False,
    )
    defaults.update(overrides)
    return ExecutionResult(**defaults)


def _make_karo_result() -> ExecutionResult:
    """Execution result with 2 Karo records."""
    records = [
        RecordSummary(
            mms_id="990001234", title="Shulchan Aruch",
            date_display="Venice, 1565", place="venice",
            publisher="bragadin", language="heb",
            agents=["קארו, יוסף בן אפרים"],
            subjects=["Jewish law"],
            primo_url="https://primo.example.com/990001234",
            source_steps=[0],
        ),
        RecordSummary(
            mms_id="990005678", title="Shulchan Aruch",
            date_display="Amsterdam, 1698", place="amsterdam",
            publisher="proops", language="heb",
            agents=["קארו, יוסף בן אפרים"],
            subjects=["Jewish law"],
            primo_url="https://primo.example.com/990005678",
            source_steps=[0],
        ),
    ]
    agents = [
        AgentSummary(
            canonical_name="קארו, יוסף בן אפרים",
            variants=["Joseph Karo"],
            birth_year=1488, death_year=1575,
            occupations=["rabbi", "posek"],
            description="Author of the Shulchan Aruch",
            record_count=2,
            links=[
                GroundingLink(entity_type="agent", entity_id="Q193460",
                    label="Wikipedia", url="https://en.wikipedia.org/wiki/Joseph_Karo", source="wikipedia"),
            ],
        ),
    ]
    return _make_execution_result(
        grounding=GroundingData(
            records=records,
            agents=agents,
            aggregations={},
            links=[
                GroundingLink(entity_type="record", entity_id="990001234",
                    label="Catalog", url="https://primo.example.com/990001234", source="primo"),
                GroundingLink(entity_type="record", entity_id="990005678",
                    label="Catalog", url="https://primo.example.com/990005678", source="primo"),
                GroundingLink(entity_type="agent", entity_id="Q193460",
                    label="Wikipedia", url="https://en.wikipedia.org/wiki/Joseph_Karo", source="wikipedia"),
            ],
        ),
        directives=[
            ScholarlyDirective(directive="expand", params={"focus": "Joseph Karo"}, label="Expand"),
        ],
        original_query="who was Joseph Karo?",
    )


# =============================================================================
# Tests
# =============================================================================

def test_narrate_returns_scholar_response():
    """narrate() returns a ScholarResponse."""
    from scripts.chat.narrator import narrate

    mock_narrative = "Joseph Karo (1488-1575) was a great scholar. **Our collection holds 2 editions**."
    mock_response = ScholarResponse(
        narrative=mock_narrative,
        suggested_followups=["What about Maimonides?"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("who was Karo?", _make_karo_result()))

    assert isinstance(result, ScholarResponse)
    assert "Karo" in result.narrative


def test_narrate_empty_results():
    """Narrator handles zero records gracefully."""
    from scripts.chat.narrator import narrate

    mock_response = ScholarResponse(
        narrative="We do not hold works by this author in our collection.",
        suggested_followups=["Try searching for related authors"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.85,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("who was Nobody?", _make_execution_result()))

    assert "do not hold" in result.narrative.lower() or "no " in result.narrative.lower()


def test_narrate_grounding_passthrough():
    """Narrator passes through grounding data from executor."""
    from scripts.chat.narrator import narrate

    exec_result = _make_karo_result()

    mock_response = ScholarResponse(
        narrative="Test narrative",
        suggested_followups=[],
        grounding=exec_result.grounding,  # Pass through
        confidence=0.9,
        metadata={},
    )

    with patch("scripts.chat.narrator._call_llm", return_value=mock_response):
        import asyncio
        result = asyncio.run(narrate("test", exec_result))

    # Grounding should contain the records from the execution result
    assert len(result.grounding.records) == 2
    assert result.grounding.records[0].mms_id == "990001234"


def test_narrate_fallback_on_llm_failure():
    """When LLM fails, narrator returns a structured summary."""
    from scripts.chat.narrator import narrate

    exec_result = _make_karo_result()

    with patch("scripts.chat.narrator._call_llm", side_effect=Exception("API error")):
        import asyncio
        result = asyncio.run(narrate("who was Karo?", exec_result))

    # Should return a valid ScholarResponse with fallback narrative
    assert isinstance(result, ScholarResponse)
    assert "990001234" in result.narrative or "2 " in result.narrative


def test_build_narrator_prompt_includes_records():
    """The narrator prompt includes record details from ExecutionResult."""
    from scripts.chat.narrator import _build_narrator_prompt

    exec_result = _make_karo_result()
    prompt = _build_narrator_prompt("who was Karo?", exec_result)

    assert "990001234" in prompt
    assert "Shulchan Aruch" in prompt
    assert "Venice, 1565" in prompt


def test_build_narrator_prompt_includes_directives():
    """The narrator prompt includes scholarly directives."""
    from scripts.chat.narrator import _build_narrator_prompt

    exec_result = _make_karo_result()
    prompt = _build_narrator_prompt("who was Karo?", exec_result)

    assert "expand" in prompt.lower()
    assert "Joseph Karo" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/chat/test_narrator.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement narrator.py**

Create `scripts/chat/narrator.py`. Key structure:

```python
"""Scholar Pipeline Stage 3: Scholarly Narrator.

Receives verified ExecutionResult and composes a scholarly response.
Uses LLM with a rich persona prompt. Cannot access the DB directly —
can only reference data present in the ExecutionResult.

Replaces: formatter.py, narrative_agent.py, thematic_context.py
"""
import os
from typing import Optional

from openai import OpenAI

from scripts.chat.plan_models import (
    ExecutionResult, ScholarResponse, GroundingData,
    ScholarlyDirective,
)
from scripts.utils.llm_logger import log_llm_call

NARRATOR_SYSTEM_PROMPT = """You are a scholar of Jewish book history..."""
# Full prompt from spec Section "Persona Prompt (Core Rules)"

async def narrate(
    query: str,
    execution_result: ExecutionResult,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
) -> ScholarResponse:
    """Compose a scholarly response from verified execution results."""
    try:
        response = await _call_llm(query, execution_result, model, api_key)
        # Ensure grounding is passed through from executor
        response.grounding = execution_result.grounding
        return response
    except Exception:
        return _fallback_response(query, execution_result)


async def _call_llm(...) -> ScholarResponse:
    """Call OpenAI with narrator persona."""
    ...


def _build_narrator_prompt(query: str, result: ExecutionResult) -> str:
    """Assemble the user prompt with verified data and directives."""
    # Renders: query, directives, records, agents, aggregations, empty steps
    ...


def _fallback_response(query: str, result: ExecutionResult) -> ScholarResponse:
    """Structured summary when LLM fails — no LLM needed."""
    # Build a basic response from GroundingData: list records, agents, links
    ...
```

The narrator system prompt must include the 6 evidence rules from the spec. The `_build_narrator_prompt` function assembles verified data into a readable format for the LLM.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/chat/test_narrator.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/chat/narrator.py tests/scripts/chat/test_narrator.py
git commit -m "feat: add narrator (Stage 3) with scholarly persona and evidence rules"
```

---

### Task 6: API Integration

**Files:**
- Modify: `app/api/main.py`
- Create: `tests/app/test_scholar_pipeline.py`

**Depends on:** Tasks 2, 3/4, 5

Wire the three-stage pipeline into the FastAPI endpoints, replacing the current routing chain.

- [ ] **Step 1: Write integration tests**

Create `tests/app/test_scholar_pipeline.py`:

```python
"""Integration tests for the scholar pipeline in the API layer.

Tests the three-stage pipeline wired into /chat and /ws/chat.
Mocks LLM calls but uses real (test) DB for executor.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.chat.plan_models import (
    InterpretationPlan, ExecutionStep, ScholarlyDirective,
    ScholarResponse, GroundingData, StepAction,
    ResolveAgentParams, RetrieveParams,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp


@pytest.fixture
def client(tmp_path):
    """TestClient with mocked DB paths."""
    sessions_db = tmp_path / "sessions.db"
    bib_db = tmp_path / "bib.db"
    # Create minimal bib DB (same schema as test_executor fixture)
    # ... (reuse test DB creation from Task 4)

    with patch.dict("os.environ", {
        "SESSIONS_DB_PATH": str(sessions_db),
        "BIBLIOGRAPHIC_DB_PATH": str(bib_db),
    }):
        yield TestClient(app)


def test_chat_pipeline_basic(client):
    """POST /chat routes through interpret → execute → narrate."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Looking for Venice books",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")],
                ),
                label="Venice books",
            )
        ],
        directives=[],
        confidence=0.95,
    )
    narrator_response = ScholarResponse(
        narrative="Found books from Venice.",
        suggested_followups=["Try Amsterdam"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={},
    )

    with patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan), \
         patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response):
        resp = client.post("/chat", json={"message": "books from Venice"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Venice" in data["response"]["message"]


def test_chat_clarification_shortcircuit(client):
    """Clarification plan skips executor and narrator."""
    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Ambiguous",
        execution_steps=[],
        directives=[],
        confidence=0.55,
        clarification="Which Karo do you mean?",
    )

    with patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan):
        resp = client.post("/chat", json={"message": "tell me about Karo"})

    assert resp.status_code == 200
    data = resp.json()
    assert "clarification" in str(data).lower() or "Karo" in str(data)


def test_chat_out_of_scope(client):
    """Out-of-scope query returns polite redirect."""
    plan = InterpretationPlan(
        intents=["out_of_scope"],
        reasoning="Not bibliographic",
        execution_steps=[],
        directives=[],
        confidence=0.99,
    )
    narrator_response = ScholarResponse(
        narrative="I'm a specialist in rare books. I can't help with that, but I'd be happy to help you explore the collection.",
        suggested_followups=["What's in this collection?"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.99,
        metadata={},
    )

    with patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan), \
         patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response):
        resp = client.post("/chat", json={"message": "what's the weather?"})

    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/app/test_scholar_pipeline.py -v`
Expected: FAIL — old routing still in place

- [ ] **Step 3: Replace handle_query_definition_phase**

In `app/api/main.py`:

1. Add new imports at the top:
```python
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan
from scripts.chat.narrator import narrate
from scripts.chat.plan_models import InterpretationPlan, ScholarResponse, SessionContext
```

2. Replace `handle_query_definition_phase()` body with the three-stage pipeline:
```python
async def handle_query_definition_phase(chat_request, session, store, bib_db):
    # Build session context for follow-ups
    session_context = SessionContext(
        recent_messages=session.get_recent_messages(5),
        previous_plan=None,  # TODO: store previous plan in session
        previous_record_ids=None,  # TODO: from active_subgroup
        previous_query=session.context.get("last_query") if session.context else None,
    )

    # Stage 1: Interpret
    plan = await interpret(chat_request.message, session_context)

    # Clarification short-circuit
    if plan.clarification and plan.confidence < 0.7:
        response = ChatResponse(
            message=plan.clarification,
            candidate_set=None,
            clarification_needed=plan.clarification,
            session_id=session.session_id,
            phase=ConversationPhase.QUERY_DEFINITION,
            confidence=plan.confidence,
            metadata={"intents": plan.intents},
        )
        store.add_message(session.session_id, Message(role="assistant", content=plan.clarification))
        return ChatResponseAPI(success=True, response=response, error=None)

    # Stage 2: Execute
    execution_result = execute_plan(plan, bib_db, session_context)

    # Stage 3: Narrate
    scholar_response = await narrate(chat_request.message, execution_result)

    # Map to ChatResponse for API compatibility
    response = ChatResponse(
        message=scholar_response.narrative,
        candidate_set=None,  # Grounding replaces candidate_set
        suggested_followups=scholar_response.suggested_followups,
        clarification_needed=None,
        session_id=session.session_id,
        phase=ConversationPhase.QUERY_DEFINITION,
        confidence=scholar_response.confidence,
        metadata={
            "intents": plan.intents,
            "grounding": scholar_response.grounding.model_dump(),
            **scholar_response.metadata,
        },
    )

    store.add_message(session.session_id, Message(role="assistant", content=scholar_response.narrative))
    return ChatResponseAPI(success=True, response=response, error=None)
```

3. Remove old imports that are no longer needed (intent_agent, analytical_router, clarification, formatter, thematic_context, narrative_agent). Keep them commented with `# DEPRECATED: removed in scholar pipeline migration` until Task 8.

4. Update the WebSocket handler similarly — replace the routing chain with the same three-stage pipeline, emitting progress messages at each stage.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/app/test_scholar_pipeline.py -v`
Expected: All 3 tests PASS

Also run existing tests to check for regressions:
Run: `pytest tests/app/test_api.py -v -k "not integration"`
Expected: Tests that don't depend on old routing should still pass. Tests that test old routing (analytical detection, etc.) may fail — that's expected and they'll be cleaned up in Task 8.

- [ ] **Step 5: Commit**

```bash
git add app/api/main.py tests/app/test_scholar_pipeline.py
git commit -m "feat: wire scholar pipeline into /chat and /ws/chat endpoints"
```

---

### Task 7: Integration Tests + Evidence Reports

**Files:**
- Create: `tests/app/test_scholar_evidence.py`
- Create: `reports/scholar-pipeline/` (directory for evidence)

**Depends on:** Task 6

End-to-end tests using the 20 historian evaluation queries. Each test captures the full pipeline trace and saves it as an evidence report.

- [ ] **Step 1: Create evidence report infrastructure**

```bash
mkdir -p reports/scholar-pipeline
```

- [ ] **Step 2: Write evidence capture tests**

Create `tests/app/test_scholar_evidence.py`:

```python
"""Evidence capture tests for the scholar pipeline.

Runs the 20 historian evaluation queries through the full pipeline
and saves traces to reports/scholar-pipeline/<run-id>/.

These tests require OPENAI_API_KEY and bibliographic.db.
Mark with @pytest.mark.integration.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

# Skip if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY",
)

HISTORIAN_QUERIES = [
    ("Q01", "books printed by Bragadin press in Venice"),
    ("Q02", "Hebrew books printed in Amsterdam between 1620 and 1650"),
    ("Q03", "books published by the Aldine Press"),
    ("Q04", "incunabula in the collection (books printed before 1500)"),
    ("Q05", "books printed in Constantinople"),
    ("Q06", "works by Johann Buxtorf"),
    ("Q07", "works by Moses Mendelssohn"),
    ("Q08", "works by Maimonides"),
    ("Q09", "works by Josephus Flavius"),
    ("Q10", "books on Jewish philosophy"),
    ("Q11", "books from the Napoleonic era 1795-1815"),
    ("Q12", "materials about Ethiopia or Ethiopian Jews"),
    ("Q13", "books about book collecting or bibliography"),
    ("Q14", "chronological distribution of the collection"),
    ("Q15", "major Hebrew printing centers represented"),
    ("Q16", "biblical commentaries"),
    ("Q17", "Hebrew grammar books"),
    ("Q18", "Talmud editions"),
    ("Q19", "works by Joseph Karo"),
    ("Q20", "curated selection for Hebrew printing exhibit"),
]

BIB_DB = Path("data/index/bibliographic.db")


@pytest.fixture(scope="module")
def run_dir():
    """Create a timestamped run directory for evidence."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = Path(f"reports/scholar-pipeline/{run_id}")
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.integration
@pytest.mark.parametrize("query_id,query_text", HISTORIAN_QUERIES)
def test_historian_query(query_id, query_text, run_dir):
    """Run a historian query and save the evidence trace."""
    from scripts.chat.interpreter import interpret
    from scripts.chat.executor import execute_plan
    from scripts.chat.narrator import narrate
    import asyncio

    trace = {
        "query_id": query_id,
        "query": query_text,
        "timestamp": datetime.now().isoformat(),
    }

    # Stage 1: Interpret
    t0 = time.time()
    plan = asyncio.run(interpret(query_text, session_context=None))
    trace["interpreter"] = {
        "plan": plan.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Stage 2: Execute
    t0 = time.time()
    result = execute_plan(plan, BIB_DB)
    trace["executor"] = {
        "result": result.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Stage 3: Narrate
    t0 = time.time()
    response = asyncio.run(narrate(query_text, result))
    trace["narrator"] = {
        "response": response.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Scores (null until manually evaluated)
    trace["scores"] = {
        "accuracy": None,
        "richness": None,
        "cross_ref": None,
        "narrative": None,
        "pedagogical": None,
    }

    # Save trace
    safe_name = query_id.lower() + "_" + query_text[:40].replace(" ", "_").replace("/", "_")
    out_path = run_dir / f"{safe_name}.json"
    out_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False, default=str))

    # Basic assertion: pipeline didn't crash
    assert response.narrative is not None
    assert len(response.narrative) > 0


@pytest.mark.integration
def test_generate_summary(run_dir):
    """Generate summary.md after all queries run."""
    traces = list(run_dir.glob("*.json"))
    lines = [f"# Scholar Pipeline Evidence Run\n", f"**Date:** {datetime.now().isoformat()}\n"]
    lines.append(f"**Queries:** {len(traces)}\n\n")
    lines.append("| Query | Records | Latency (ms) | Has Narrative |\n")
    lines.append("|-------|---------|-------------|---------------|\n")

    for path in sorted(traces):
        t = json.loads(path.read_text())
        record_count = sum(
            s.get("record_count", 0) or 0
            for s in t.get("executor", {}).get("result", {}).get("steps_completed", [])
        )
        total_ms = (
            t.get("interpreter", {}).get("latency_ms", 0)
            + t.get("executor", {}).get("latency_ms", 0)
            + t.get("narrator", {}).get("latency_ms", 0)
        )
        has_narrative = bool(t.get("narrator", {}).get("response", {}).get("narrative"))
        lines.append(f"| {t['query_id']} | {record_count} | {total_ms} | {'Yes' if has_narrative else 'No'} |\n")

    (run_dir / "summary.md").write_text("".join(lines))
    assert (run_dir / "summary.md").exists()
```

- [ ] **Step 3: Run unit tests (no API key needed)**

Run: `pytest tests/app/test_scholar_pipeline.py -v`
Expected: PASS (mocked LLM)

- [ ] **Step 4: Run evidence tests (requires API key)**

Run: `pytest tests/app/test_scholar_evidence.py -v --run-integration`
Expected: 20 queries run, evidence saved to `reports/scholar-pipeline/<run-id>/`

- [ ] **Step 5: Commit**

```bash
git add tests/app/test_scholar_evidence.py reports/scholar-pipeline/
git commit -m "feat: add evidence capture tests for historian evaluation queries"
```

---

### Task 8: Cleanup Removed Modules

**Files:**
- Remove: 10 deprecated modules (see Module Disposition in spec)
- Remove: associated test files
- Modify: `app/api/main.py` (remove commented-out imports)

**Depends on:** Task 7 (all tests passing first)

This task removes the old modules that have been replaced by the scholar pipeline. Only do this after confirming the new pipeline works end-to-end.

- [ ] **Step 1: Verify new pipeline tests pass**

Run: `pytest tests/scripts/chat/test_plan_models.py tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py tests/app/test_scholar_pipeline.py -v`
Expected: All PASS

- [ ] **Step 2: Remove deprecated source files**

```bash
git rm scripts/chat/intent_agent.py
git rm scripts/chat/analytical_router.py
git rm scripts/chat/formatter.py
git rm scripts/chat/narrative_agent.py
git rm scripts/chat/thematic_context.py
git rm scripts/chat/clarification.py
git rm scripts/chat/curator.py
git rm scripts/chat/exploration_agent.py
git rm scripts/query/llm_compiler.py
git rm scripts/query/execute.py
```

- [ ] **Step 3: Remove deprecated test files**

```bash
git rm tests/scripts/chat/test_analytical_router.py
git rm tests/scripts/chat/test_formatter.py
git rm tests/scripts/chat/test_formatter_e3.py
git rm tests/scripts/chat/test_formatter_pedagogical.py
git rm tests/scripts/chat/test_narrative_agent_e3.py
git rm tests/scripts/chat/test_thematic_context.py
git rm tests/scripts/chat/test_clarification.py
git rm tests/scripts/chat/test_curator.py
git rm tests/app/test_api_analytical.py
```

- [ ] **Step 4: Clean up main.py imports**

Remove the commented-out deprecated imports from `app/api/main.py`. Remove any dead code paths that referenced the old modules.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --ignore=tests/app/test_scholar_evidence.py`
Expected: All remaining tests PASS. Any failures indicate something still depends on a removed module — fix the import.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove deprecated modules replaced by scholar pipeline

Removed: intent_agent, analytical_router, formatter, narrative_agent,
thematic_context, clarification, curator, exploration_agent,
llm_compiler, execute. All functionality now in interpreter.py,
executor.py, narrator.py."
```

---

## Execution Notes

**Parallelization:** After Task 1 completes, Tasks 2, 3, and 5 can be developed in parallel (they share only `plan_models.py`). Task 4 depends on Task 3. Task 6 depends on Tasks 2, 4, and 5. Task 7 depends on Task 6. Task 8 depends on Task 7.

**Testing without API key:** Tasks 1-6 use mocked LLM calls and run without `OPENAI_API_KEY`. Only Task 7's evidence tests require a real API key.

**Incremental verification:** Each task has a commit. After each commit, run `pytest tests/ -v --ignore=tests/app/test_scholar_evidence.py` to catch regressions. The old routing code stays in place (just unused) until Task 8 removes it.

**Key domain knowledge for implementer:**
- MARC stores names surname-first: "buxtorf, johann", not "Johann Buxtorf"
- Hebrew script names are common: "קארו, יוסף בן אפרים" = Joseph Karo
- The `authority_enrichment` table has Wikidata/Wikipedia data for many agents
- Primo URLs are generated from MMS IDs via `_generate_primo_url(mms_id)` — currently in `app/api/metadata.py:910`, must be extracted to `scripts/utils/primo.py` before executor can use it (see Modified files table)
- The OpenAI Responses API pattern with Pydantic schemas is used in `intent_agent.py` function `_interpret_with_openai()` — follow the same pattern for interpreter and narrator
- The `AggregateParams.field` values map to SQL columns: `date_decade` → computed from `date_start`, `place` → `place_norm`, `publisher` → `publisher_norm`, `language` → `languages` table, `subject` → `subjects` table, `agent` → `agent_norm`. See `aggregation.py:execute_aggregation()` for the existing mapping.

---

## Review-Driven Amendments

The following items were identified during plan review and must be addressed during implementation:

### Critical: `$previous_results` Scope Resolution

**Where:** Task 3 (executor core) and Task 4 (handlers)

The spec defines `"$previous_results"` as a special scope that resolves to MMS IDs from the prior conversation turn. This must be implemented in the executor alongside `$step_N` resolution:

```python
def _resolve_scope(scope: str, step_results, session_context) -> list[str] | None:
    if scope == "full_collection":
        return None  # No scope restriction
    if scope == "$previous_results":
        if session_context and session_context.previous_record_ids:
            return session_context.previous_record_ids
        return []  # No previous results — empty scope
    if scope.startswith("$step_"):
        return _resolve_step_ref(scope, step_results, context="scope")
    raise PlanValidationError(f"Unknown scope: {scope}")
```

Add tests for this in `test_executor.py`:
- Follow-up query with `$previous_results` scope narrows to prior IDs
- `$previous_results` with no session context returns empty set

### Critical: Primo URL Extraction

**Where:** Before Task 4 (preparatory step)

Extract `_generate_primo_url()` from `app/api/metadata.py:910` to `scripts/utils/primo.py`. Update `app/api/metadata.py` to import from the new location. This prevents `scripts/chat/executor.py` from importing from `app/api/`.

### Critical: ExecutionStep.params Union Serialization

**Where:** Task 1 (plan_models.py)

The `ExecutionStep.params` is a union of 7 Pydantic models. For OpenAI Responses API, avoid sending this union to the LLM. Instead, the interpreter LLM schema should use a simpler representation:

```python
# LLM-facing schema (for OpenAI Responses API)
class ExecutionStepLLM(BaseModel):
    """Schema the LLM produces — no union, just dict params."""
    action: str          # Action name as string
    params: dict         # Untyped params
    label: str
    depends_on: list[int] = []

class InterpretationPlanLLM(BaseModel):
    """LLM output schema — uses string action + dict params."""
    intents: list[str]
    reasoning: str
    execution_steps: list[ExecutionStepLLM]
    directives: list[ScholarlyDirective]
    confidence: float
    clarification: str | None = None
```

The interpreter then **validates and converts** the LLM output to typed `ExecutionStep` objects:

```python
def _convert_llm_plan(raw: InterpretationPlanLLM) -> InterpretationPlan:
    """Convert LLM output to typed plan. Validates action names and params."""
    typed_steps = []
    for step in raw.execution_steps:
        action = StepAction(step.action)  # Raises ValueError if unknown
        params = _parse_params(action, step.params)  # Validates per-action
        typed_steps.append(ExecutionStep(action=action, params=params, ...))
    ...
```

This avoids the Pydantic union serialization issue with OpenAI's API entirely.

### Important: Health Check Extension

**Where:** Task 6 (API integration), add a step

Extend the `/health` endpoint to verify executor readiness:

```python
@app.get("/health")
async def health():
    # ... existing checks ...
    executor_ready = verify_executor_tables(bib_db)
    return {"status": "healthy", "database_connected": True, "executor_ready": executor_ready}
```

The `verify_executor_tables()` function checks all tables from the data contract (spec section "Data Contract: Executor ↔ Database").

### Important: Missing Handler Tests

**Where:** Task 4

Add tests for the two untested handlers:
- `test_handle_find_connections(test_db)` — add a second agent to the test fixture, verify the graph has a connection
- `test_handle_sample(test_db)` — test `strategy="earliest"` returns records ordered by `date_start`

### Important: WebSocket Streaming Tests

**Where:** Task 6

Add at least one WebSocket test using the new message types:

```python
def test_websocket_scholar_pipeline(client):
    """WebSocket emits plan, evidence, narrative_chunk, complete messages."""
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"message": "books from Venice"})
        messages = []
        while True:
            msg = ws.receive_json()
            messages.append(msg)
            if msg["type"] == "complete":
                break
        types = [m["type"] for m in messages]
        assert "progress" in types
        assert "complete" in types
```

### Important: Shared Test DB Fixture

**Where:** `tests/conftest.py` or `tests/scripts/chat/conftest.py`

Extract the test DB fixture from Task 4 into a shared conftest, since Tasks 3, 4, 6, and 7 all need it.

### Deferred Items (Not Blocking)

- **Narrator token-by-token streaming**: Use standard (non-streaming) responses API initially. Add streaming in a follow-up.
- **Partial clarification execution (confidence 0.7-0.85)**: Start with the simple short-circuit for < 0.7. Add the partial execution path after the basic pipeline works.
- **Interpreter snapshot tests with mocked LLM for the 20 historian queries**: Start with the 6 tests in Task 2. Add structural snapshot assertions for all 20 queries as a follow-up after the interpreter prompt is stable.
