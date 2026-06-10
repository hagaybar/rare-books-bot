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
