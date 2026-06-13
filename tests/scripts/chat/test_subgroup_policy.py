"""Unit tests for the held-set lifecycle policy (issue #60 part 2)."""

from scripts.chat.plan_models import (
    AggregateParams,
    ExecutionResult,
    ExecutionStep,
    GroundingData,
    InterpretationPlan,
    RecordSet,
    RetrieveParams,
    StepAction,
    StepResult,
)
from scripts.chat.subgroup_policy import (
    build_subgroup_update,
    subgroup_summary,
    summarize_filters,
    was_scoped_to_held_set,
)
from scripts.schemas import (
    Filter,
    FilterField,
    FilterOp,
)


def _retrieve_step(scope="full_collection", filters=None):
    return ExecutionStep(
        label="retrieve",
        action=StepAction.RETRIEVE,
        params=RetrieveParams(filters=filters or [], scope=scope),
    )


def _aggregate_step(scope="$previous_results"):
    return ExecutionStep(
        label="aggregate",
        action=StepAction.AGGREGATE,
        params=AggregateParams(field="language", scope=scope),
    )


def _plan(steps):
    return InterpretationPlan(
        intents=["search"],
        execution_steps=steps,
        directives=[],
        reasoning="r",
        confidence=0.9,
    )


def _exec_result(retrieve_ids_per_step, total_record_count):
    """Build an ExecutionResult with one retrieve StepResult per id-list."""
    steps = []
    for i, ids in enumerate(retrieve_ids_per_step):
        steps.append(StepResult(
            step_index=i,
            label="retrieve",
            action="retrieve",
            status="ok",
            data=RecordSet(mms_ids=list(ids), total_count=len(ids), filters_applied=[]),
        ))
    return ExecutionResult(
        steps_completed=steps,
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}),
        original_query="q",
        total_record_count=total_record_count,
    )


def test_held_record_ids_unions_retrieve_steps_dedup_order():
    from scripts.chat.subgroup_policy import held_record_ids
    result = _exec_result([["1", "2", "3"], ["3", "4"]], total_record_count=4)
    assert held_record_ids(result) == ["1", "2", "3", "4"]


def test_held_record_ids_empty_when_no_retrieve():
    from scripts.chat.subgroup_policy import held_record_ids
    result = _exec_result([], total_record_count=0)
    assert held_record_ids(result) == []


def test_build_subgroup_update_uses_full_set_not_truncated_display():
    """Regression for the 74-vs-30 bug: held set is the FULL retrieve set,
    even though the display/grounding (and any candidate_set) was truncated."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    full_ids = [str(i) for i in range(74)]
    result = _exec_result([full_ids], total_record_count=74)
    sub = build_subgroup_update(plan, result, "printed in Venice")
    assert sub is not None
    assert len(sub.record_ids) == 74           # NOT 30
    assert sub.record_ids == full_ids


def test_build_subgroup_update_none_when_no_records():
    plan = _plan([_retrieve_step(scope="full_collection")])
    result = _exec_result([[]], total_record_count=0)
    assert build_subgroup_update(plan, result, "q") is None


def test_build_subgroup_update_none_for_aggregate_only_turn():
    plan = _plan([_aggregate_step(scope="$previous_results")])
    # An aggregate-only turn has no retrieve RecordSet -> no held-set redefinition
    result = _exec_result([], total_record_count=0)
    assert build_subgroup_update(plan, result, "how many in Hebrew?") is None


def test_new_search_replaces_held_set():
    """A full-collection retrieve with results defines a new held set."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    result = _exec_result([["0", "1", "2"]], total_record_count=3)
    sub = build_subgroup_update(plan, result, "printed in Venice")
    assert sub is not None
    assert sub.record_ids == ["0", "1", "2"]
    assert sub.defining_query == "printed in Venice"


def test_refine_in_set_replaces_held_set():
    """A retrieve scoped to the held set narrows and replaces it."""
    plan = _plan([_retrieve_step(scope="$previous_results")])
    result = _exec_result([["0", "1"]], total_record_count=2)
    sub = build_subgroup_update(plan, result, "only the Hebrew ones")
    assert sub is not None
    assert sub.record_ids == ["0", "1"]


def test_explore_in_set_leaves_held_set_unchanged():
    """An aggregate-only turn does not redefine the held set."""
    plan = _plan([_aggregate_step(scope="$previous_results")])
    result = _exec_result([], total_record_count=0)
    sub = build_subgroup_update(plan, result, "how many are in Hebrew?")
    assert sub is None


def test_empty_result_leaves_held_set_unchanged():
    """A retrieve with zero results does not redefine the held set."""
    plan = _plan([_retrieve_step(scope="full_collection")])
    result = _exec_result([[]], total_record_count=0)
    sub = build_subgroup_update(plan, result, "books from Atlantis")
    assert sub is None


def test_no_retrieve_steps_leaves_held_set_unchanged():
    """A plan with no retrieve step never redefines the held set."""
    plan = _plan([_aggregate_step(scope="$previous_results")])
    result = _exec_result([], total_record_count=0)
    assert build_subgroup_update(plan, result, "q") is None


def test_was_scoped_to_held_set_true_for_previous_results():
    plan = _plan([_aggregate_step(scope="$previous_results")])
    assert was_scoped_to_held_set(plan) is True


def test_was_scoped_to_held_set_false_for_full_collection():
    plan = _plan([_retrieve_step(scope="full_collection")])
    assert was_scoped_to_held_set(plan) is False


def test_summarize_filters_describes_retrieve_filters():
    plan = _plan([_retrieve_step(filters=[
        Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.CONTAINS, value="Venice"),
        Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599),
    ])])
    summary = summarize_filters(plan)
    assert "place" in summary.lower()
    assert "Venice" in summary
    assert "1500" in summary


def test_summarize_filters_empty_when_no_filters():
    plan = _plan([_retrieve_step(filters=[])])
    assert summarize_filters(plan) == ""


def test_subgroup_summary_shape():
    from scripts.chat.models import ActiveSubgroup

    sub = ActiveSubgroup(
        defining_query="printed in Venice",
        filter_summary="place contains Venice",
        record_ids=["1", "2", "3"],
    )
    assert subgroup_summary(sub) == {
        "defining_query": "printed in Venice",
        "count": 3,
    }
    assert subgroup_summary(None) is None
