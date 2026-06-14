from pathlib import Path
from scripts.chat.plan_models import ExecutionResult, GroundingData, RecordSummary
from scripts.eval.narrator_gold import GoldCase, save_gold_case
from scripts.eval.run_narrator_gold_eval import build_all_narration_requests, dry_run


def _case(cid: str) -> GoldCase:
    r = ExecutionResult(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=[RecordSummary(mms_id="1", title="T", date_display="1500")]),
        original_query="q",
        total_record_count=1,
    )
    return GoldCase(cid, "q", r, "gold")


def test_build_all_narration_requests_one_per_case_model(tmp_path: Path):
    for cid in ["c01", "c02"]:
        save_gold_case(tmp_path, _case(cid))
    models = ["gpt-4.1", "gpt-5-mini"]
    reqs = build_all_narration_requests(tmp_path, models, max_output_tokens=2000, reasoning_effort="low")
    assert len(reqs) == 4  # 2 cases x 2 models
    assert {r["custom_id"] for r in reqs} == {"c01::gpt-4.1", "c01::gpt-5-mini", "c02::gpt-4.1", "c02::gpt-5-mini"}


def test_dry_run_projects_cost_and_writes_jsonl(tmp_path: Path):
    save_gold_case(tmp_path, _case("c01"))
    out = tmp_path / "run"
    projected = dry_run(
        gold_dir=tmp_path,
        models=["gpt-4.1", "gpt-5-mini"],
        judge_model="gpt-5.4",
        output_dir=out,
        ceiling=2.00,
        max_narration_tokens=2000,
        max_judge_tokens=1200,
        reasoning_effort="low",
    )
    assert projected > 0 and projected <= 2.00
    assert (out / "narration_batch.jsonl").exists()
