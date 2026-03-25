"""Tests for the executor (Stage 2) -- core framework.

Tests dependency resolution, $step_N substitution, and error handling.
All tests use in-memory SQLite, no LLM needed.
"""
from pathlib import Path

import pytest

from scripts.chat.plan_models import (
    AggregateParams,
    ExecutionResult,
    ExecutionStep,
    InterpretationPlan,
    RecordSet,
    ResolveAgentParams,
    ResolvedEntity,
    RetrieveParams,
    ScholarlyDirective,
    StepAction,
    StepResult,
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
            ScholarlyDirective(
                directive="expand", params={"focus": "Karo"}, label="Expand"
            ),
            ScholarlyDirective(
                directive="contextualize", params={"theme": "law"}, label="Context"
            ),
        ],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.directives) == 2
    assert result.directives[0].directive == "expand"
    assert result.directives[1].params == {"theme": "law"}


def test_step_dependency_ordering():
    """Steps are executed in dependency order."""
    from scripts.chat.executor import _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
        ),
        ExecutionStep(
            action=StepAction.AGGREGATE,
            params=AggregateParams(field="date_decade", scope="$step_0"),
            label="S1",
            depends_on=[0],
        ),
    ]
    order = _resolve_execution_order(steps)
    assert order == [0, 1]


def test_dependency_ordering_three_steps():
    """Three steps with diamond dependency: step 2 depends on both 0 and 1."""
    from scripts.chat.executor import _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RESOLVE_AGENT,
            params=ResolveAgentParams(name="Karo"),
            label="S0",
        ),
        ExecutionStep(
            action=StepAction.RESOLVE_PUBLISHER,
            params=ResolveAgentParams(name="Bragadin"),
            label="S1",
        ),
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S2",
            depends_on=[0, 1],
        ),
    ]
    order = _resolve_execution_order(steps)
    # 0 and 1 must come before 2
    assert order.index(0) < order.index(2)
    assert order.index(1) < order.index(2)


def test_circular_dependency_rejected():
    """Circular dependencies produce an error, not infinite loop."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
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
    ]
    with pytest.raises(PlanValidationError, match="circular"):
        _resolve_execution_order(steps)


def test_out_of_range_step_ref_rejected():
    """$step_99 when only 1 step exists raises error."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
            depends_on=[99],
        ),
    ]
    with pytest.raises(PlanValidationError, match="out of range"):
        _resolve_execution_order(steps)


def test_self_reference_rejected():
    """A step depending on itself is rejected."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
            depends_on=[0],
        ),
    ]
    with pytest.raises(PlanValidationError, match="circular"):
        _resolve_execution_order(steps)


# =============================================================================
# Step reference resolution tests
# =============================================================================


def test_step_ref_resolution_resolve_agent_to_value():
    """$step_0 from resolve_agent resolves to matched_values in value context."""
    from scripts.chat.executor import _resolve_step_ref

    resolved = ResolvedEntity(
        query_name="Karo",
        matched_values=["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"],
        match_method="alias_exact",
        confidence=0.95,
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="resolve_agent",
            label="Resolve",
            status="ok",
            data=resolved,
            record_count=None,
        )
    }

    value = _resolve_step_ref("$step_0", step_results, context="value")
    assert value == ["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"]


def test_step_ref_resolution_retrieve_to_scope():
    """$step_0 from retrieve resolves to mms_ids for aggregate scope."""
    from scripts.chat.executor import _resolve_step_ref

    record_set = RecordSet(
        mms_ids=["990001", "990002"], total_count=2, filters_applied=[]
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="retrieve",
            label="Retrieve",
            status="ok",
            data=record_set,
            record_count=2,
        )
    }

    value = _resolve_step_ref("$step_0", step_results, context="scope")
    assert value == ["990001", "990002"]


def test_step_ref_resolution_missing_step():
    """Referencing a step that hasn't been executed raises an error."""
    from scripts.chat.executor import PlanValidationError, _resolve_step_ref

    with pytest.raises(PlanValidationError, match="not found"):
        _resolve_step_ref("$step_5", {}, context="value")


def test_step_ref_resolution_non_ref_passthrough():
    """Non-$step_N strings pass through as-is."""
    from scripts.chat.executor import _resolve_step_ref

    value = _resolve_step_ref("full_collection", {}, context="scope")
    assert value == "full_collection"


# =============================================================================
# Unknown action handling
# =============================================================================


def test_unknown_action_skipped():
    """Unknown step action is marked as error, not a crash.

    Uses model_construct to bypass Pydantic validation, simulating a
    plan where the interpreter failed to reject an unknown action.
    """
    from scripts.chat.executor import execute_plan

    # Build a step with an invalid action via model_construct (bypasses validation)
    bad_step = ExecutionStep.model_construct(
        action="search_fulltext",
        params=RetrieveParams(filters=[]),
        label="Bad step",
        depends_on=[],
    )
    plan = InterpretationPlan.model_construct(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[bad_step],
        directives=[],
        confidence=0.9,
        clarification=None,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert result.steps_completed[0].status == "error"
    assert "Unknown action" in result.steps_completed[0].error_message


# =============================================================================
# Stub handler tests (verify stubs return valid empty results)
# =============================================================================


def test_stub_resolve_agent_returns_empty():
    """Stub resolve_agent handler returns empty ResolvedEntity."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Test",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Unknown Author"),
                label="Resolve agent",
            ),
        ],
        directives=[],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.steps_completed) == 1
    step = result.steps_completed[0]
    assert isinstance(step.data, ResolvedEntity)
    assert step.status in ("ok", "empty")


def test_stub_retrieve_returns_empty():
    """Stub retrieve handler returns empty RecordSet."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.PUBLISHER,
                            op=FilterOp.EQUALS,
                            value="Oxford",
                        )
                    ]
                ),
                label="Retrieve books",
            ),
        ],
        directives=[],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.steps_completed) == 1
    step = result.steps_completed[0]
    assert isinstance(step.data, RecordSet)
    assert step.status in ("ok", "empty")


def test_execution_with_dependency_chain():
    """Full execution: resolve_agent -> retrieve (with dependency)."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Test dependency chain",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Karo"),
                label="Resolve Karo",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.AGENT_NORM,
                            op=FilterOp.CONTAINS,
                            value="$step_0",
                        )
                    ],
                    scope="full_collection",
                ),
                label="Retrieve Karo works",
                depends_on=[0],
            ),
        ],
        directives=[
            ScholarlyDirective(
                directive="expand", params={"focus": "biography"}, label="Bio"
            ),
        ],
        confidence=0.85,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.steps_completed) == 2
    assert result.steps_completed[0].action == "resolve_agent"
    assert result.steps_completed[1].action == "retrieve"
    # Directives passed through
    assert len(result.directives) == 1
    assert result.directives[0].directive == "expand"


def test_original_query_in_result():
    """original_query is included in ExecutionResult."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.95,
    )
    result = execute_plan(
        plan, db_path=Path(":memory:"), original_query="books by Karo"
    )
    assert result.original_query == "books by Karo"


def test_session_context_passed_through():
    """SessionContext is attached to ExecutionResult when provided."""
    from scripts.chat.plan_models import SessionContext
    from scripts.chat.executor import execute_plan

    ctx = SessionContext(
        session_id="test-session",
        previous_record_ids=["990001", "990002"],
    )
    plan = InterpretationPlan(
        intents=["follow_up"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.9,
    )
    result = execute_plan(
        plan, db_path=Path(":memory:"), session_context=ctx
    )
    assert result.session_context is not None
    assert result.session_context.session_id == "test-session"
    assert result.session_context.previous_record_ids == ["990001", "990002"]


def test_resolve_scope_full_collection():
    """_resolve_scope returns None for 'full_collection'."""
    from scripts.chat.executor import _resolve_scope

    result = _resolve_scope("full_collection", {}, None)
    assert result is None


def test_resolve_scope_step_ref():
    """_resolve_scope with $step_N returns mms_ids from the referenced step."""
    from scripts.chat.executor import _resolve_scope

    record_set = RecordSet(
        mms_ids=["990001", "990002", "990003"],
        total_count=3,
        filters_applied=[],
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="retrieve",
            label="Retrieve",
            status="ok",
            data=record_set,
            record_count=3,
        )
    }
    result = _resolve_scope("$step_0", step_results, None)
    assert result == ["990001", "990002", "990003"]


def test_resolve_scope_previous_results():
    """_resolve_scope with $previous_results uses session context."""
    from scripts.chat.plan_models import SessionContext
    from scripts.chat.executor import _resolve_scope

    ctx = SessionContext(
        session_id="sess-1",
        previous_record_ids=["990010", "990020"],
    )
    result = _resolve_scope("$previous_results", {}, ctx)
    assert result == ["990010", "990020"]


def test_resolve_scope_previous_results_no_context():
    """_resolve_scope with $previous_results but no context returns empty."""
    from scripts.chat.executor import _resolve_scope

    result = _resolve_scope("$previous_results", {}, None)
    assert result == []
