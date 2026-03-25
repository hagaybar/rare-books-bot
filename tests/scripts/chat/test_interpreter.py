"""Tests for the interpreter (Stage 1).

All tests mock the OpenAI client -- no API key needed.
"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from scripts.chat.plan_models import (
    InterpretationPlan,
    InterpretationPlanLLM,
    ExecutionStep,
    ExecutionStepLLM,
    ScholarlyDirective,
    StepAction,
    ResolveAgentParams,
    RetrieveParams,
    AggregateParams,
    SessionContext,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp
from scripts.chat.models import Message


# =============================================================================
# Helpers
# =============================================================================


def _make_plan(**overrides) -> InterpretationPlan:
    """Build a valid InterpretationPlan for mocking."""
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


def _make_llm_plan(**overrides) -> InterpretationPlanLLM:
    """Build an InterpretationPlanLLM (raw LLM output format)."""
    defaults = dict(
        intents=["retrieval"],
        reasoning="Test plan",
        execution_steps=[],
        directives=[],
        confidence=0.95,
        clarification=None,
    )
    defaults.update(overrides)
    return InterpretationPlanLLM(**defaults)


# =============================================================================
# Schema / round-trip: _convert_llm_plan
# =============================================================================


class TestConvertLLMPlan:
    """Validate the LLM-plan -> typed-plan conversion."""

    def test_basic_retrieve(self):
        """Simple retrieve step converts correctly."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            intents=["retrieval"],
            execution_steps=[
                ExecutionStepLLM(
                    action="retrieve",
                    params={
                        "filters": [
                            {"field": "imprint_place", "op": "EQUALS", "value": "venice"}
                        ],
                    },
                    label="Books from Venice",
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert isinstance(plan, InterpretationPlan)
        assert len(plan.execution_steps) == 1
        step = plan.execution_steps[0]
        assert step.action == StepAction.RETRIEVE
        assert isinstance(step.params, RetrieveParams)
        assert step.params.filters[0].field == FilterField.IMPRINT_PLACE

    def test_resolve_agent(self):
        """resolve_agent step with variants converts correctly."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            intents=["entity_exploration"],
            execution_steps=[
                ExecutionStepLLM(
                    action="resolve_agent",
                    params={"name": "Joseph Karo", "variants": ["Caro, Joseph"]},
                    label="Resolve Karo",
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        step = plan.execution_steps[0]
        assert step.action == StepAction.RESOLVE_AGENT
        assert isinstance(step.params, ResolveAgentParams)
        assert step.params.name == "Joseph Karo"
        assert "Caro, Joseph" in step.params.variants

    def test_aggregate_step(self):
        """aggregate step converts correctly."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="aggregate",
                    params={"field": "date_decade", "scope": "$step_0", "limit": 20},
                    label="Temporal distribution",
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        step = plan.execution_steps[0]
        assert step.action == StepAction.AGGREGATE
        assert isinstance(step.params, AggregateParams)
        assert step.params.scope == "$step_0"

    def test_depends_on_preserved(self):
        """depends_on indices are preserved through conversion."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="retrieve",
                    params={"filters": []},
                    label="S0",
                ),
                ExecutionStepLLM(
                    action="aggregate",
                    params={"field": "date_decade", "scope": "$step_0"},
                    label="S1",
                    depends_on=[0],
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert plan.execution_steps[1].depends_on == [0]

    def test_directives_preserved(self):
        """Scholarly directives pass through unchanged."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            directives=[
                ScholarlyDirective(
                    directive="expand",
                    params={"focus": "Joseph Karo"},
                    label="Expand on Karo",
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert len(plan.directives) == 1
        assert plan.directives[0].directive == "expand"
        assert plan.directives[0].params == {"focus": "Joseph Karo"}

    def test_clarification_preserved(self):
        """Clarification string passes through."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            confidence=0.4,
            clarification="Which Karo do you mean?",
        )

        plan = _convert_llm_plan(llm_plan)
        assert plan.clarification == "Which Karo do you mean?"
        assert plan.confidence == pytest.approx(0.4)

    def test_invalid_action_skipped(self):
        """Unknown action type is skipped, not crash."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="nonexistent_action",
                    params={"foo": "bar"},
                    label="Bad step",
                ),
                ExecutionStepLLM(
                    action="retrieve",
                    params={"filters": []},
                    label="Good step",
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        # The invalid step is skipped; only the valid one remains
        assert len(plan.execution_steps) == 1
        assert plan.execution_steps[0].action == StepAction.RETRIEVE

    def test_filter_with_step_ref_in_value(self):
        """Filter value containing $step_N passes through as string."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="resolve_agent",
                    params={"name": "Karo"},
                    label="Resolve",
                ),
                ExecutionStepLLM(
                    action="retrieve",
                    params={
                        "filters": [
                            {"field": "agent_norm", "op": "EQUALS", "value": "$step_0"}
                        ],
                    },
                    label="Retrieve by agent",
                    depends_on=[0],
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert len(plan.execution_steps) == 2
        retrieve_step = plan.execution_steps[1]
        assert retrieve_step.params.filters[0].value == "$step_0"


# =============================================================================
# Step reference validation
# =============================================================================


class TestValidateStepRefs:
    """Validate $step_N reference checking."""

    def test_valid_refs_pass(self):
        """Valid forward references pass validation."""
        from scripts.chat.interpreter import _validate_step_refs

        plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RESOLVE_AGENT,
                    params=ResolveAgentParams(name="Karo"),
                    label="S0",
                ),
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(
                        filters=[
                            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0")
                        ],
                    ),
                    label="S1",
                    depends_on=[0],
                ),
            ],
        )

        # Should not raise
        _validate_step_refs(plan)

    def test_out_of_range_ref_raises(self):
        """$step_99 in depends_on raises ValueError."""
        from scripts.chat.interpreter import _validate_step_refs

        plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[]),
                    label="S0",
                    depends_on=[99],
                ),
            ],
        )

        with pytest.raises(ValueError, match="out of range"):
            _validate_step_refs(plan)

    def test_self_reference_raises(self):
        """Step depending on itself raises ValueError."""
        from scripts.chat.interpreter import _validate_step_refs

        plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[]),
                    label="S0",
                    depends_on=[0],
                ),
            ],
        )

        with pytest.raises(ValueError, match="circular|self"):
            _validate_step_refs(plan)

    def test_circular_deps_raises(self):
        """Circular dependency chain raises ValueError."""
        from scripts.chat.interpreter import _validate_step_refs

        plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[]),
                    label="S0",
                    depends_on=[1],
                ),
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[]),
                    label="S1",
                    depends_on=[0],
                ),
            ],
        )

        with pytest.raises(ValueError, match="circular"):
            _validate_step_refs(plan)

    def test_scope_step_ref_validated(self):
        """$step_N in scope param is validated for range."""
        from scripts.chat.interpreter import _validate_step_refs

        plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.AGGREGATE,
                    params=AggregateParams(field="date_decade", scope="$step_5"),
                    label="Aggregate",
                ),
            ],
        )

        with pytest.raises(ValueError, match="out of range"):
            _validate_step_refs(plan)


# =============================================================================
# interpret() end-to-end with mocked LLM
# =============================================================================


class TestInterpret:
    """End-to-end tests with _call_llm mocked."""

    def test_returns_interpretation_plan(self):
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
            result = asyncio.run(interpret("books from Venice", session_context=None))

        assert isinstance(result, InterpretationPlan)
        assert result.intents == ["retrieval"]
        assert len(result.execution_steps) == 1
        assert result.execution_steps[0].action == StepAction.RETRIEVE

    def test_entity_exploration(self):
        """Entity exploration query produces resolve step."""
        from scripts.chat.interpreter import interpret

        plan = _make_plan(
            intents=["entity_exploration"],
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RESOLVE_AGENT,
                    params=ResolveAgentParams(name="Joseph Karo", variants=["Caro, Joseph"]),
                    label="Resolve Karo",
                ),
            ],
            directives=[
                ScholarlyDirective(directive="expand", params={"focus": "Joseph Karo"}, label="Expand"),
            ],
        )

        with patch("scripts.chat.interpreter._call_llm", return_value=plan):
            result = asyncio.run(interpret("who was Joseph Karo?", session_context=None))

        assert "entity_exploration" in result.intents
        assert result.execution_steps[0].action == StepAction.RESOLVE_AGENT

    def test_clarification(self):
        """Low-confidence query returns clarification."""
        from scripts.chat.interpreter import interpret

        plan = _make_plan(
            intents=["entity_exploration"],
            confidence=0.55,
            clarification="Which Karo do you mean?",
        )

        with patch("scripts.chat.interpreter._call_llm", return_value=plan):
            result = asyncio.run(interpret("tell me about Karo", session_context=None))

        assert result.clarification is not None
        assert result.confidence < 0.7

    def test_with_session_context(self):
        """Follow-up query passes session context to _call_llm."""
        from scripts.chat.interpreter import interpret

        plan = _make_plan(intents=["follow_up"])

        ctx = SessionContext(
            session_id="test-session",
            previous_messages=[
                Message(role="user", content="books by Karo"),
                Message(role="assistant", content="Found 3 works..."),
            ],
            previous_record_ids=["990001", "990002"],
        )

        with patch("scripts.chat.interpreter._call_llm", return_value=plan) as mock_llm:
            result = asyncio.run(interpret("only from Venice", session_context=ctx))

        # Verify session context was forwarded to _call_llm
        call_args = mock_llm.call_args
        assert call_args is not None
        # _call_llm is called with (query, session_context, model, api_key)
        passed_ctx = call_args[0][1] if call_args[0] else call_args[1].get("session_context")
        assert passed_ctx is not None

    def test_out_of_scope(self):
        """Out-of-scope query returns empty steps."""
        from scripts.chat.interpreter import interpret

        plan = _make_plan(
            intents=["out_of_scope"],
            reasoning="Weather question, not bibliographic",
            confidence=0.99,
        )

        with patch("scripts.chat.interpreter._call_llm", return_value=plan):
            result = asyncio.run(interpret("what's the weather?", session_context=None))

        assert "out_of_scope" in result.intents
        assert len(result.execution_steps) == 0

    def test_mixed_intents(self):
        """Complex query produces multiple intent labels."""
        from scripts.chat.interpreter import interpret

        plan = _make_plan(intents=["entity_exploration", "comparison"])

        with patch("scripts.chat.interpreter._call_llm", return_value=plan):
            result = asyncio.run(interpret("compare Karo and Maimonides", session_context=None))

        assert len(result.intents) == 2
        assert "entity_exploration" in result.intents
        assert "comparison" in result.intents

    def test_validation_runs_after_llm(self):
        """_validate_step_refs is called on the LLM output."""
        from scripts.chat.interpreter import interpret

        # Plan with an out-of-range dep -- should be caught by validation
        bad_plan = _make_plan(
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[]),
                    label="S0",
                    depends_on=[5],
                ),
            ],
        )

        with patch("scripts.chat.interpreter._call_llm", return_value=bad_plan):
            with pytest.raises(ValueError, match="out of range"):
                asyncio.run(interpret("books from Venice", session_context=None))


# =============================================================================
# System prompt construction
# =============================================================================


class TestBuildUserPrompt:
    """Test user prompt assembly."""

    def test_simple_query(self):
        """Simple query without context produces clean prompt."""
        from scripts.chat.interpreter import _build_user_prompt

        prompt = _build_user_prompt("books from Venice", session_context=None)
        assert "books from Venice" in prompt

    def test_session_context_included(self):
        """Session context is included in the prompt."""
        from scripts.chat.interpreter import _build_user_prompt

        ctx = SessionContext(
            session_id="s1",
            previous_messages=[
                Message(role="user", content="books by Karo"),
                Message(role="assistant", content="Found 3 works..."),
            ],
            previous_record_ids=["990001", "990002"],
        )

        prompt = _build_user_prompt("only from Venice", session_context=ctx)
        assert "books by Karo" in prompt
        assert "only from Venice" in prompt
        assert "990001" in prompt  # Previous record IDs provide context

    def test_no_context_no_crash(self):
        """None context doesn't crash."""
        from scripts.chat.interpreter import _build_user_prompt

        prompt = _build_user_prompt("hello", session_context=None)
        assert "hello" in prompt
