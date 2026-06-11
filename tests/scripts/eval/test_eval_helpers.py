"""Tests for eval-framework helpers (2026-06-10 critical review).

Flaws fixed: filters_produced lost all but the last value per field
(last-wins dict); plans were never executed so a 5/5 plan could return
0 records; no run-to-run comparison existed.
"""
from pathlib import Path

import pytest

from scripts.chat.plan_models import (
    ExecutionStep,
    InterpretationPlan,
    RetrieveParams,
    StepAction,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

DB_PATH = Path("data/index/bibliographic.db")


def _plan(steps_filters):
    return InterpretationPlan(
        intents=["retrieval"],
        reasoning="t",
        confidence=0.9,
        directives=[],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=fs),
                label=f"s{i}",
            )
            for i, fs in enumerate(steps_filters)
        ],
    )


class TestExtractFilters:
    def test_collects_all_values_per_field_across_steps(self):
        from scripts.eval.run_eval import extract_filters
        plan = _plan([
            [Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
             Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="maps")],
            [Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
             Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")],
        ])
        out = extract_filters(plan)
        assert out["subject"] == ["art", "maps", "geography"]
        assert out["imprint_place"] == ["venice"]


class TestComputeRecall:
    @pytest.fixture(autouse=True)
    def _require_db(self):
        if not DB_PATH.exists():
            pytest.skip("Bibliographic database not available")

    def test_nonzero_recall_reported(self):
        from scripts.eval.run_eval import compute_recall
        plan = _plan([[Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="printing")]])
        recall = compute_recall(plan, str(DB_PATH))
        assert recall["total_records"] >= 50
        assert recall["zero_result"] is False
        assert recall["relaxations_used"] is False

    def test_zero_result_flagged(self):
        from scripts.eval.run_eval import compute_recall
        plan = _plan([[Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="xyzzyplugh")]])
        recall = compute_recall(plan, str(DB_PATH))
        assert recall["zero_result"] is True


class TestCompareRuns:
    def test_compare_produces_per_query_deltas(self, tmp_path):

        from scripts.eval.compare_runs import compare_results
        a = [{"query_id": "q1", "stage": "interpreter", "success": True, "score_combined": 3.0},
             {"query_id": "q2", "stage": "interpreter", "success": True, "score_combined": 5.0}]
        b = [{"query_id": "q1", "stage": "interpreter", "success": True, "score_combined": 4.5,
              "recall": {"zero_result": False, "total_records": 12}},
             {"query_id": "q2", "stage": "interpreter", "success": True, "score_combined": 4.0}]
        cmp = compare_results(a, b)
        assert cmp["summary"]["avg_before"] == 4.0
        assert cmp["summary"]["avg_after"] == 4.25
        deltas = {d["query_id"]: d for d in cmp["queries"]}
        assert deltas["q1"]["delta"] == 1.5
        assert deltas["q2"]["delta"] == -1.0


class TestRangeFilterSerialization:
    """Issue #10a: RANGE filters serialized as None — every year-expecting
    query lost overlap credit (q34: overlap 0.5 beside a 5/5 judge note)."""

    def test_range_serializes_start_end(self):
        from scripts.eval.run_eval import extract_filters
        plan = _plan([[Filter(field=FilterField.YEAR, op=FilterOp.RANGE,
                              start=1500, end=1599)]])
        out = extract_filters(plan)
        assert out["year"] == ["1500-1599"]


class TestClarificationScoring:
    """Issue #10b: expected intent 'clarification' was unmatchable and the
    judge never saw the clarification field — asking could not be rewarded."""

    def _q(self, intent):
        from scripts.eval.query_set import EvalQuery
        return EvalQuery(id="t", query="פילוסופיה חד", intent=intent,
                         difficulty="hard", expected_filters={})

    def test_clarification_intent_satisfied_by_clarification_field(self):
        from scripts.eval.judge import deterministic_checks
        intent_match, _ = deterministic_checks(
            self._q("clarification"),
            {"intents": ["retrieval"], "clarification": "האם התכוונת ל...?",
             "filters_produced": {}})
        assert intent_match is True

    def test_clarification_intent_fails_without_field(self):
        from scripts.eval.judge import deterministic_checks
        intent_match, _ = deterministic_checks(
            self._q("clarification"),
            {"intents": ["retrieval"], "clarification": None,
             "filters_produced": {}})
        assert intent_match is False

    def test_judge_prompt_rewards_asking(self):
        from scripts.eval.judge import INTERPRETER_JUDGE_PROMPT
        assert "clarification" in INTERPRETER_JUDGE_PROMPT.lower()


class TestRecallIntentAwareness:
    """Issue #11: 6 of 22 zero_result entries were metric artifacts."""

    @pytest.fixture(autouse=True)
    def _require_db(self):
        if not DB_PATH.exists():
            pytest.skip("Bibliographic database not available")

    def test_out_of_scope_empty_plan_is_not_a_failure(self):
        from scripts.eval.run_eval import compute_recall
        plan = InterpretationPlan(intents=["out_of_scope"], reasoning="t",
                                  confidence=0.9, directives=[], execution_steps=[])
        recall = compute_recall(plan, str(DB_PATH), expected_intent="out_of_scope")
        assert recall["zero_result"] is False

    def test_aggregate_only_overview_counts_facets_as_success(self):
        from scripts.chat.plan_models import AggregateParams
        from scripts.eval.run_eval import compute_recall
        plan = InterpretationPlan(
            intents=["overview"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[ExecutionStep(
                action=StepAction.AGGREGATE,
                params=AggregateParams(field="language", scope="full_collection", limit=5),
                label="langs")])
        recall = compute_recall(plan, str(DB_PATH), expected_intent="overview")
        assert recall["has_aggregations"] is True
        assert recall["zero_result"] is False

    def test_follow_up_recall_is_skipped(self):
        from scripts.eval.run_eval import compute_recall
        plan = _plan([[Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS,
                              value="$previous")]])
        recall = compute_recall(plan, str(DB_PATH), expected_intent="follow_up")
        assert recall.get("skipped"), "follow-ups need session context the harness lacks"
        assert recall["zero_result"] is None
