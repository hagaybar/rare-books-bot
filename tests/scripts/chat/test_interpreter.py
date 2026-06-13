"""Tests for the interpreter (Stage 1).

All tests mock the OpenAI client -- no API key needed.
"""
import asyncio
import json
from unittest.mock import patch

import pytest

from scripts.chat.plan_models import (
    InterpretationPlan,
    InterpretationPlanLLM,
    ExecutionStep,
    ExecutionStepLLM,
    ScholarlyDirective,
    ScholarlyDirectiveLLM,
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
                    params=json.dumps({
                        "filters": [
                            {"field": "imprint_place", "op": "EQUALS", "value": "venice"}
                        ],
                    }),
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
                    params=json.dumps({"name": "Joseph Karo", "variants": ["Caro, Joseph"]}),
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
                    params=json.dumps({"field": "date_decade", "scope": "$step_0", "limit": 20}),
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
                    params=json.dumps({"filters": []}),
                    label="S0",
                ),
                ExecutionStepLLM(
                    action="aggregate",
                    params=json.dumps({"field": "date_decade", "scope": "$step_0"}),
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
                ScholarlyDirectiveLLM(
                    directive="expand",
                    params=json.dumps({"focus": "Joseph Karo"}),
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
                    params=json.dumps({"foo": "bar"}),
                    label="Bad step",
                ),
                ExecutionStepLLM(
                    action="retrieve",
                    params=json.dumps({"filters": []}),
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
                    params=json.dumps({"name": "Karo"}),
                    label="Resolve",
                ),
                ExecutionStepLLM(
                    action="retrieve",
                    params=json.dumps({
                        "filters": [
                            {"field": "agent_norm", "op": "EQUALS", "value": "$step_0"}
                        ],
                    }),
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


# =============================================================================
# Hebrew gershayim JSON repair (Issue 1)
# =============================================================================


class TestHebrewGershayimRepair:
    """Verify that Hebrew abbreviations with gershayim parse correctly."""

    def test_convert_step_with_escaped_gershayim(self):
        """Already-escaped gershayim parses normally."""
        from scripts.chat.interpreter import _convert_llm_step

        # The escaped form: \" inside the Hebrew string
        params_json = '{"name": "Maimonides", "variants": ["\\u05e8\\u05de\\u05d1\\"\\u05dd", "Rambam"]}'
        step = ExecutionStepLLM(
            action="resolve_agent",
            params=params_json,
            label="Resolve Rambam",
        )
        result = _convert_llm_step(step)
        assert result.params.name == "Maimonides"
        assert len(result.params.variants) == 2

    def test_convert_step_with_hebrew_gershayim(self):
        r"""Broken gershayim (unescaped \" inside string value) is repaired."""
        from scripts.chat.interpreter import _convert_llm_step

        # Broken form: the raw " inside רמב"ם is NOT escaped
        # This is: {"name": "Maimonides", "variants": ["רמב"ם", "Rambam"]}
        params_json = '{"name": "Maimonides", "variants": ["\u05e8\u05de\u05d1"\u05dd", "Rambam"]}'
        step = ExecutionStepLLM(
            action="resolve_agent",
            params=params_json,
            label="Resolve Rambam",
        )
        result = _convert_llm_step(step)
        assert result.params.name == "Maimonides"
        assert len(result.params.variants) == 2
        # The first variant should contain the gershayim character
        assert '"' in result.params.variants[0] or '\u05dd' in result.params.variants[0]

    def test_repair_json_string_basic(self):
        """_repair_json_string fixes interior quotes."""
        from scripts.chat.interpreter import _repair_json_string
        import json

        broken = '{"name": "Maimonides", "variants": ["\u05e8\u05de\u05d1"\u05dd", "Rambam"]}'
        repaired = _repair_json_string(broken)
        parsed = json.loads(repaired)
        assert parsed["name"] == "Maimonides"
        assert len(parsed["variants"]) == 2

    def test_repair_json_string_no_change_needed(self):
        """_repair_json_string returns valid JSON unchanged."""
        from scripts.chat.interpreter import _repair_json_string
        import json

        valid = '{"name": "Maimonides", "variants": ["Rambam"]}'
        repaired = _repair_json_string(valid)
        assert json.loads(repaired) == json.loads(valid)

    def test_parse_json_params_valid(self):
        """_parse_json_params handles valid JSON."""
        from scripts.chat.interpreter import _parse_json_params

        result = _parse_json_params('{"name": "Karo"}')
        assert result == {"name": "Karo"}

    def test_parse_json_params_broken_gershayim(self):
        """_parse_json_params repairs broken gershayim."""
        from scripts.chat.interpreter import _parse_json_params

        broken = '{"name": "Maimonides", "variants": ["\u05e8\u05de\u05d1"\u05dd", "Rambam"]}'
        result = _parse_json_params(broken)
        assert result["name"] == "Maimonides"
        assert len(result["variants"]) == 2


# =============================================================================
# Step index remapping after skip (Issue 2)
# =============================================================================


class TestStepIndexRemapping:
    """Verify depends_on and $step_N refs are remapped when steps are skipped."""

    def test_convert_plan_remaps_depends_on_after_skip(self):
        """Skipping step 0 remaps depends_on for surviving steps."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                # Step 0: invalid action -- will be skipped
                ExecutionStepLLM(
                    action="nonexistent_action",
                    params=json.dumps({"foo": "bar"}),
                    label="Bad step",
                ),
                # Step 1: depends on step 0 (which is skipped)
                ExecutionStepLLM(
                    action="retrieve",
                    params=json.dumps({"filters": []}),
                    label="Retrieve",
                    depends_on=[0],
                ),
                # Step 2: depends on step 1 (which becomes new index 0)
                ExecutionStepLLM(
                    action="aggregate",
                    params=json.dumps({"field": "date_decade", "scope": "$step_1"}),
                    label="Aggregate",
                    depends_on=[1],
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)

        # Only 2 surviving steps
        assert len(plan.execution_steps) == 2

        # Step 0 (was step 1): depends_on ref to skipped step 0 is removed
        assert plan.execution_steps[0].depends_on == []
        assert plan.execution_steps[0].action == StepAction.RETRIEVE

        # Step 1 (was step 2): depends_on remapped from [1] to [0]
        assert plan.execution_steps[1].depends_on == [0]
        assert plan.execution_steps[1].action == StepAction.AGGREGATE
        # Scope $step_1 should be remapped to $step_0
        assert plan.execution_steps[1].params.scope == "$step_0"

    def test_convert_plan_no_skip_no_change(self):
        """When no steps are skipped, depends_on is unchanged."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="resolve_agent",
                    params=json.dumps({"name": "Karo"}),
                    label="Resolve",
                ),
                ExecutionStepLLM(
                    action="retrieve",
                    params=json.dumps({
                        "filters": [
                            {"field": "agent_norm", "op": "EQUALS", "value": "$step_0"}
                        ],
                    }),
                    label="Retrieve",
                    depends_on=[0],
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert len(plan.execution_steps) == 2
        assert plan.execution_steps[1].depends_on == [0]
        assert plan.execution_steps[1].params.filters[0].value == "$step_0"

    def test_convert_plan_middle_step_skipped(self):
        """Skipping a middle step remaps later references correctly."""
        from scripts.chat.interpreter import _convert_llm_plan

        llm_plan = _make_llm_plan(
            execution_steps=[
                # Step 0: valid
                ExecutionStepLLM(
                    action="retrieve",
                    params=json.dumps({"filters": []}),
                    label="S0",
                ),
                # Step 1: invalid -- skipped
                ExecutionStepLLM(
                    action="nonexistent_action",
                    params=json.dumps({"x": 1}),
                    label="Bad",
                ),
                # Step 2: depends on step 0 (unchanged) and step 1 (dropped)
                ExecutionStepLLM(
                    action="aggregate",
                    params=json.dumps({"field": "date_decade", "scope": "$step_0"}),
                    label="S2",
                    depends_on=[0, 1],
                ),
            ],
        )

        plan = _convert_llm_plan(llm_plan)
        assert len(plan.execution_steps) == 2
        # Step 1 (was step 2): depends_on only [0] (ref to skipped step 1 removed)
        assert plan.execution_steps[1].depends_on == [0]
        # scope $step_0 stays $step_0 (step 0 not skipped)
        assert plan.execution_steps[1].params.scope == "$step_0"


# =============================================================================
# Prompt integrity: coordinate topics, physical_desc, curatorial routing
# =============================================================================


class TestPromptCoordinateTopics:
    """The system prompt must teach multi-topic decomposition, the
    physical_desc field, and curatorial routing (issue #2 A3/C8)."""

    def test_prompt_forbids_anding_coordinate_topics(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "COORDINATE TOPICS" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_documents_physical_desc_field(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "physical_desc" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_has_curatorial_example_with_sample_step(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "מה תציע לי להראות" in INTERPRETER_SYSTEM_PROMPT
        # NB: no surrounding quotes in the assertion — inside the prompt the
        # scope value sits in an escaped-JSON params string (\"...\").
        assert "$step_0+$step_1+$step_2" in INTERPRETER_SYSTEM_PROMPT

    def test_convert_filter_dict_accepts_physical_desc(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict(
            {"field": "physical_desc", "op": "CONTAINS", "value": "map"}
        )
        assert f.field.value == "physical_desc"


class TestYearEqualsCoercion:
    """Issue #44: the LLM emits year EQUALS <v>, but the SQL adapter supports
    only RANGE for year — db_adapter raised ValueError and the step died as a
    silent empty result (diagnostic TEST-DATE-04: a correct gematria
    conversion תקס"ה -> 1805 was destroyed by the IR gap). Coerce at the
    conversion boundary to a degenerate RANGE."""

    def test_year_equals_string_coerced_to_range(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict({"field": "year", "op": "EQUALS", "value": "1805"})
        assert f.op.value == "RANGE"
        assert f.start == 1805
        assert f.end == 1805
        assert f.value is None

    def test_year_equals_int_coerced_to_range(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict({"field": "year", "op": "EQUALS", "value": 1650})
        assert f.op.value == "RANGE"
        assert f.start == 1650
        assert f.end == 1650

    def test_year_equals_preserves_negate(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict(
            {"field": "year", "op": "EQUALS", "value": "1805", "negate": True}
        )
        assert f.op.value == "RANGE"
        assert f.negate is True

    def test_year_equals_step_ref_rejected_loudly(self):
        """Issue #56 B3: a $step_N year EQUALS bypassed the #44 coercion and
        died as an unhandled ValueError in SQL generation. No step produces
        years, so the filter is nonsense: Filter validation now rejects it
        with a clear message and the step is dropped (recorded in
        dropped_steps), never reaching SQL."""
        from scripts.chat.interpreter import _convert_filter_dict
        with pytest.raises(ValueError, match="year"):
            _convert_filter_dict({"field": "year", "op": "EQUALS", "value": "$step_0"})

    def test_year_equals_unparseable_rejected_loudly(self):
        """Issue #56 B3: same — unparseable values must be rejected at
        validation, not silently produce a wrong-empty CandidateSet."""
        from scripts.chat.interpreter import _convert_filter_dict
        with pytest.raises(ValueError, match="year"):
            _convert_filter_dict({"field": "year", "op": "EQUALS", "value": "uncertain"})

    def test_year_contains_parseable_coerced_to_range(self):
        """Issue #56: the #44 coercion is extended to CONTAINS."""
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict({"field": "year", "op": "CONTAINS", "value": "1525"})
        assert f.op.value == "RANGE"
        assert f.start == 1525
        assert f.end == 1525

    def test_step_with_unparseable_year_filter_is_dropped_not_crashed(self):
        """A retrieve step carrying a rejected filter must be skipped loudly
        (dropped_steps), not crash plan conversion."""
        from scripts.chat.interpreter import _convert_llm_plan
        from scripts.chat.plan_models import ExecutionStepLLM
        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="retrieve",
                    params='{"filters": [{"field": "year", "op": "EQUALS", "value": "uncertain"}]}',
                    label="bad year",
                ),
            ],
        )
        plan = _convert_llm_plan(llm_plan)
        assert plan.execution_steps == []
        assert any("year" in d for d in plan.dropped_steps)

    def test_non_year_equals_not_coerced(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict({"field": "publisher", "op": "EQUALS", "value": "1805"})
        assert f.op.value == "EQUALS"
        assert f.value == "1805"


class TestPromptFilterDiscipline:
    """The prompt must forbid invented constraints, malformed multi-value
    filters, and concept-words routed as agent names (printing-houses case)."""

    def test_prompt_forbids_inventing_constraints(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "NEVER INVENT" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_requires_proper_in_arrays(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "comma-joined" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_routes_concept_adjectives_to_subject(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "יהודיים" in INTERPRETER_SYSTEM_PROMPT


class TestPromptSineLocoSentinel:
    """Issue #49: 'no place of publication' compiled to imprint_place
    EQUALS "" — a silent 0 instead of the 41 records carrying the
    place_norm sentinel '[sine loco]'. The prompt must teach the
    absence-sentinel mapping."""

    def test_prompt_maps_missing_place_to_sentinel(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "[sine loco]" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_lists_hebrew_absence_phrasings(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert 'ח"מ' in INTERPRETER_SYSTEM_PROMPT
        assert "ללא מקום הוצאה" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_forbids_empty_string_for_absence(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "NEVER use an empty-string filter value" in INTERPRETER_SYSTEM_PROMPT


class TestEmptyFilterValueDropped:
    """Issue #49 (conversion side): if the LLM emits an empty/whitespace-only
    filter value anyway, _convert_filter_dict must drop THAT filter with a
    warning — not let Filter validation kill the whole retrieve step."""

    def test_equals_empty_value_dropped(self, caplog):
        from scripts.chat.interpreter import _convert_filter_dict
        with caplog.at_level("WARNING"):
            f = _convert_filter_dict(
                {"field": "imprint_place", "op": "EQUALS", "value": ""}
            )
        assert f is None
        assert any("empty" in r.message for r in caplog.records)

    def test_contains_whitespace_value_dropped(self):
        from scripts.chat.interpreter import _convert_filter_dict
        assert _convert_filter_dict(
            {"field": "subject", "op": "CONTAINS", "value": "   "}
        ) is None

    def test_in_empty_members_pruned_others_kept(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict(
            {"field": "language", "op": "IN", "value": ["lat", "", "heb"]}
        )
        assert f is not None
        assert f.value == ["lat", "heb"]

    def test_in_all_members_empty_dropped(self):
        from scripts.chat.interpreter import _convert_filter_dict
        assert _convert_filter_dict(
            {"field": "language", "op": "IN", "value": ["", "  "]}
        ) is None

    def test_sine_loco_sentinel_survives_conversion(self):
        from scripts.chat.interpreter import _convert_filter_dict
        f = _convert_filter_dict(
            {"field": "imprint_place", "op": "EQUALS", "value": "[sine loco]"}
        )
        assert f is not None
        assert f.value == "[sine loco]"

    def test_step_keeps_remaining_filters_when_one_dropped(self):
        """The retrieve step survives with the non-empty filters intact."""
        from scripts.chat.interpreter import _convert_llm_plan
        from scripts.chat.plan_models import ExecutionStepLLM
        llm_plan = _make_llm_plan(
            execution_steps=[
                ExecutionStepLLM(
                    action="retrieve",
                    params=(
                        '{"filters": ['
                        '{"field": "imprint_place", "op": "EQUALS", "value": ""}, '
                        '{"field": "language", "op": "EQUALS", "value": "heb"}]}'
                    ),
                    label="empty place + language",
                ),
            ],
        )
        plan = _convert_llm_plan(llm_plan)
        assert len(plan.execution_steps) == 1
        filters = plan.execution_steps[0].params.filters
        assert len(filters) == 1
        assert filters[0].value == "heb"


class TestPromptGarbledTerms:
    """Typo incident ('פילוסופיה חד' answered as Kabbalah): garbled terms
    must trigger clarification, never silent concept substitution."""

    def test_prompt_forbids_silent_substitution(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "NEVER silently substitute" in INTERPRETER_SYSTEM_PROMPT

    def test_prompt_lists_garbled_terms_as_clarification_trigger(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "garbled" in INTERPRETER_SYSTEM_PROMPT
        assert "פילוסופיה חד" in INTERPRETER_SYSTEM_PROMPT


class TestPromptClarificationLanguage:
    """Clarifications bypass the narrator (short-circuit), so the language
    rule must live in the interpreter prompt: Hebrew question → Hebrew
    clarification (observed: 'צשפט' typo got an English clarification)."""

    def test_prompt_requires_clarification_in_user_language(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "clarification in the language of the user's query" in INTERPRETER_SYSTEM_PROMPT


class TestIssue5EmptyPlans:
    """Issue #5 forensics (2026-06-11): the LLM intermittently emits params
    JSON with a missing closing brace; _convert_llm_plan silently dropped the
    step, producing empty plans at 0.9 confidence. The parser must repair
    unbalanced brackets, and any step that still drops must be recorded."""

    def test_parse_repairs_missing_closing_brace(self):
        from scripts.chat.interpreter import _parse_json_params
        # the exact malformed string captured from gpt-4.1-mini (q27 #3)
        raw = '{"filters":[{"field":"language","op":"EQUALS","value":"ita"}]'
        parsed = _parse_json_params(raw)
        assert parsed["filters"][0]["value"] == "ita"

    def test_parse_repairs_missing_bracket_and_brace(self):
        from scripts.chat.interpreter import _parse_json_params
        raw = '{"filters":[{"field":"subject","op":"CONTAINS","value":"art"'
        parsed = _parse_json_params(raw)
        assert parsed["filters"][0]["field"] == "subject"

    def test_dropped_steps_are_recorded_on_plan(self):
        from scripts.chat.interpreter import _convert_llm_plan, InterpretationPlanLLM
        llm_plan = InterpretationPlanLLM(
            intents=["retrieval"], reasoning="t", confidence=0.9,
            execution_steps=[
                {"action": "retrieve", "params": "totally not json {{{", "label": "bad"},
                {"action": "no_such_action", "params": "{}", "label": "worse"},
            ],
            directives=[],
        )
        plan = _convert_llm_plan(llm_plan)
        assert plan.execution_steps == []
        assert len(plan.dropped_steps) == 2
        assert "bad" in plan.dropped_steps[0] or "0" in plan.dropped_steps[0]


class TestUnionScopeValidationAndRemap:
    """Issue #8: '$step_0+$step_1' union scopes were invisible to validation
    and step-index remapping — dropped steps left stale indices pointing at
    the WRONG record sets (a silent wrong-answer path)."""

    def test_validate_rejects_out_of_range_union_member(self):
        from scripts.chat.interpreter import _validate_step_refs
        from scripts.chat.plan_models import (
            ExecutionStep, InterpretationPlan, RetrieveParams, SampleParams, StepAction,
        )
        from scripts.schemas.query_plan import Filter, FilterField, FilterOp
        plan = InterpretationPlan(
            intents=["curation"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[
                ExecutionStep(action=StepAction.RETRIEVE, label="a",
                              params=RetrieveParams(filters=[Filter(
                                  field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art")])),
                ExecutionStep(action=StepAction.SAMPLE, label="s",
                              params=SampleParams(scope="$step_0+$step_7", n=5),
                              depends_on=[0]),
            ])
        import pytest as _pytest
        with _pytest.raises(ValueError):
            _validate_step_refs(plan)

    def test_remap_drops_skipped_member_and_renumbers(self):
        from scripts.chat.interpreter import _convert_llm_plan
        from scripts.chat.plan_models import InterpretationPlanLLM
        llm_plan = InterpretationPlanLLM(
            intents=["curation"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[
                {"action": "retrieve", "label": "a",
                 "params": '{"filters":[{"field":"subject","op":"CONTAINS","value":"art"}]}'},
                {"action": "no_such_action", "label": "bad", "params": "{}"},
                {"action": "retrieve", "label": "b",
                 "params": '{"filters":[{"field":"subject","op":"CONTAINS","value":"maps"}]}'},
                {"action": "sample", "label": "s",
                 "params": '{"scope": "$step_0+$step_1+$step_2", "n": 5}'},
            ])
        plan = _convert_llm_plan(llm_plan)
        # bad step dropped: old 0->0, old 2->1, old 3->2
        assert len(plan.execution_steps) == 3
        scope = plan.execution_steps[2].params.scope
        assert scope == "$step_0+$step_1", f"stale union scope: {scope}"

    def test_union_with_all_members_dropped_becomes_full_collection(self):
        from scripts.chat.interpreter import _convert_llm_plan
        from scripts.chat.plan_models import InterpretationPlanLLM
        llm_plan = InterpretationPlanLLM(
            intents=["curation"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[
                {"action": "no_such_action", "label": "bad1", "params": "{}"},
                {"action": "no_such_action2", "label": "bad2", "params": "{}"},
                {"action": "sample", "label": "s",
                 "params": '{"scope": "$step_0+$step_1", "n": 5}'},
            ])
        plan = _convert_llm_plan(llm_plan)
        assert plan.execution_steps[0].params.scope == "full_collection"

    def test_spec_section_documents_union_syntax(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        spec = INTERPRETER_SYSTEM_PROMPT.split("# $step_N REFERENCES")[1].split("#")[0]
        assert "+" in spec and "$step_0+$step_1" in spec


class TestPromptClarificationContractCoherence:
    """Issue #7: the prompt told the model to proceed WITH a clarification at
    low confidence — but the runtime short-circuits whenever clarification is
    set. One contract now: clarification => always ask; proceeding with an
    assumed reading means leaving clarification EMPTY."""

    def test_garbled_rule_says_leave_clarification_empty(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "leave the clarification field EMPTY" in INTERPRETER_SYSTEM_PROMPT

    def test_out_of_scope_rule_no_longer_pairs_plan_with_clarification(self):
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT
        assert "add a clarification noting that the topic is" not in INTERPRETER_SYSTEM_PROMPT


class TestPromptThreeIntentHeldSet:
    """Issue #60: the interpreter must classify each follow-up turn against a
    held result set as one of three intents -- new search / explore-in-set /
    refine-in-set -- and map that to full_collection vs $previous_results
    scope. Prompt-discipline assertions: the vocabulary + the $previous_results
    keyword are present, and a held set's record count reaches the user prompt."""

    def test_system_prompt_teaches_three_intent_model(self):
        """The system prompt names the three held-set intents and the keyword."""
        from scripts.chat.interpreter import INTERPRETER_SYSTEM_PROMPT

        prompt = INTERPRETER_SYSTEM_PROMPT
        assert "$previous_results" in prompt
        # the three-intent vocabulary
        for token in ("new search", "explore", "refine"):
            assert token.lower() in prompt.lower()

    def test_held_set_context_rendered_with_count_and_keyword(self):
        """When a held set is present, its count + the scope keyword reach the
        user prompt."""
        from scripts.chat.interpreter import _build_user_prompt

        ctx = SessionContext(
            session_id="s1",
            previous_record_ids=[str(i) for i in range(73)],
        )
        user_prompt = _build_user_prompt("how many are in Hebrew?", session_context=ctx)
        assert "73" in user_prompt
        assert "$previous_results" in user_prompt
