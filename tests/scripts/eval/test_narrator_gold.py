import pytest
from pathlib import Path
from scripts.eval.narrator_gold import (
    estimate_request_cost,
    estimate_batch_cost,
    estimate_tokens,
    assert_within_ceiling,
    CostCeilingExceeded,
    PRICING,
    GoldCase,
    load_gold_case,
    save_gold_case,
    bounded_grounding_summary,
)
from scripts.chat.plan_models import ExecutionResult, GroundingData, RecordSummary


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
    expected = estimate_request_cost("gpt-4.1", 1000, 1000, batch=True) + estimate_request_cost(
        "gpt-5-mini", 1000, 1000, batch=True
    )
    assert abs(total - expected) < 1e-9


def test_estimate_tokens_heuristic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100  # ~4 chars/token


def test_ceiling_guard_passes_under():
    projected = assert_within_ceiling([("gpt-4.1", 1000, 1000)], ceiling=2.00, batch=True)
    assert projected < 2.00


def test_ceiling_guard_aborts_over():
    reqs = [("gpt-5.4", 5000, 1200)] * 1000
    with pytest.raises(CostCeilingExceeded):
        assert_within_ceiling(reqs, ceiling=2.00, batch=True)


def _sample_result() -> ExecutionResult:
    return ExecutionResult(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(
            records=[
                RecordSummary(
                    mms_id="990001",
                    title="Sefer Yetzirah",
                    date_display="1562",
                    place="Mantua",
                    primo_url="https://primo/990001",
                ),
            ]
        ),
        original_query="books printed in Mantua",
        total_record_count=1,
    )


def test_gold_case_round_trip(tmp_path: Path):
    case = GoldCase(
        case_id="c01_mantua",
        query="books printed in Mantua",
        grounding=_sample_result(),
        gold_markdown="# Holdings\n1 record...",
    )
    save_gold_case(tmp_path, case)
    loaded = load_gold_case(tmp_path / "c01_mantua")
    assert loaded.case_id == "c01_mantua"
    assert loaded.query == case.query
    assert loaded.gold_markdown == case.gold_markdown
    assert loaded.grounding.model_dump() == case.grounding.model_dump()


def test_bounded_summary_caps_rows_and_states_total():
    recs = [RecordSummary(mms_id=str(i), title=f"T{i}", date_display="1500", place="Venice") for i in range(100)]
    result = ExecutionResult(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=recs),
        original_query="q",
        total_record_count=100,
    )
    summary = bounded_grounding_summary(result, max_rows=40)
    assert "100" in summary
    assert sum(1 for line in summary.splitlines() if line.startswith("- mms_id=")) <= 40


def test_bounded_summary_empty_set():
    result = ExecutionResult(
        steps_completed=[], directives=[], grounding=GroundingData(records=[]), original_query="q", total_record_count=0
    )
    summary = bounded_grounding_summary(result)
    assert "0" in summary
