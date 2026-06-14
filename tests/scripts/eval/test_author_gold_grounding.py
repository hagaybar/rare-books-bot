from pathlib import Path
import pytest
from scripts.eval.author_gold_grounding import grounding_from_plan_file

DB = Path("data/index/bibliographic.db")


@pytest.mark.skipif(not DB.exists(), reason="requires bibliographic.db")
def test_grounding_from_plan_file_runs_executor(tmp_path: Path):
    # Minimal empty plan (no steps) -> executor returns an empty-but-valid result.
    # InterpretationPlan requires: intents (list), reasoning, execution_steps,
    # directives, confidence (verified against scripts/chat/plan_models.py).
    plan_json = (
        '{"intents": ["retrieval"], "reasoning": "test", "execution_steps": [], "directives": [], "confidence": 0.9}'
    )
    plan_path = tmp_path / "c01.plan.json"
    plan_path.write_text(plan_json, encoding="utf-8")
    result = grounding_from_plan_file(plan_path, query="books in Mantua", db_path=DB)
    assert result.original_query == "books in Mantua"
    assert result.total_record_count == 0
