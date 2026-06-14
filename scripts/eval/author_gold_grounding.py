"""Phase-2 helper: freeze grounding from an Opus-authored plan ($0, DB-only).

Opus simulates the interpreter by writing an InterpretationPlan JSON per query;
this runs the pure-DB executor (no LLM, no network) and writes grounding.json.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.chat.plan_models import InterpretationPlan, ExecutionResult
from scripts.chat.executor import execute_plan

DB_PATH = Path("data/index/bibliographic.db")


def grounding_from_plan_file(plan_path: Path, query: str, db_path: Path = DB_PATH) -> ExecutionResult:
    """Validate a hand-authored plan and run the executor to freeze grounding."""
    plan = InterpretationPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    return execute_plan(plan, db_path, original_query=query)


def main() -> None:
    p = argparse.ArgumentParser(description="Freeze grounding from an authored plan")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--case-id", required=True)
    p.add_argument("--gold-dir", type=Path, default=Path("data/eval/narrator_gold"))
    p.add_argument("--db-path", type=Path, default=DB_PATH)
    args = p.parse_args()
    result = grounding_from_plan_file(args.plan, args.query, args.db_path)
    case_dir = args.gold_dir / args.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "query.txt").write_text(args.query, encoding="utf-8")
    (case_dir / "grounding.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {case_dir / 'grounding.json'} ({result.total_record_count} records). Now author gold.md.")


if __name__ == "__main__":
    main()
