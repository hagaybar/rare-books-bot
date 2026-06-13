"""Run the gold-standard diagnostic suite through the live chat pipeline.

For each test case in data/eval/gold_standard_diagnostic_suite.json:

1. Stage 1 (interpreter, LLM): ``interpret(query)`` -> InterpretationPlan.
   Captured verbatim, including ``clarification`` and ``dropped_steps``.
2. Stage 2 (executor, deterministic): ``execute_plan`` -> step results with
   RecordSet.total_count / relaxations / filters_applied.
3. Evidence pass (deterministic, no LLM): rebuilds a QueryPlan from each
   retrieve step's *post-resolution* ``filters_applied`` and runs the M5
   internals (build_full_query + fetch_candidates + extract_evidence_for_filter)
   to capture per-candidate MARC evidence. The legacy subject-hint LLM retry
   is deliberately bypassed.

Artifacts: one JSON per test plus _combined.json in the output run directory.

Usage:
    poetry run python scripts/eval/run_diagnostic_suite.py [--only TEST-ID ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from scripts.chat.executor import execute_plan as chat_execute_plan
from scripts.chat.interpreter import interpret
from scripts.chat.plan_models import RecordSet
from scripts.query.execute import (
    extract_evidence_for_filter,
    fetch_candidates,
    get_connection,
)
from scripts.query.db_adapter import build_full_query
from scripts.schemas.query_plan import Filter, QueryPlan

SUITE_PATH = Path("data/eval/gold_standard_diagnostic_suite.json")
DB_PATH = Path("data/index/bibliographic.db")
EVIDENCE_SAMPLE_CAP = 10  # candidates per retrieve step to carry full evidence


def _dump_step_result(sr) -> dict:
    out = {
        "step_index": sr.step_index,
        "action": sr.action,
        "label": sr.label,
        "status": sr.status,
        "record_count": sr.record_count,
        "error_message": sr.error_message,
    }
    data = sr.data
    if isinstance(data, RecordSet):
        out["data"] = {
            "type": "RecordSet",
            "total_count": data.total_count,
            "mms_ids_sample": data.mms_ids[:15],
            "filters_applied": data.filters_applied,
            "relaxations": data.relaxations,
        }
    else:
        try:
            dumped = data.model_dump()
        except Exception:
            dumped = {"repr": repr(data)[:500]}
        out["data"] = {"type": type(data).__name__, **_truncate(dumped)}
    return out


def _truncate(obj, max_list=15, max_str=400):
    if isinstance(obj, dict):
        return {k: _truncate(v, max_list, max_str) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate(v, max_list, max_str) for v in obj[:max_list]]
    if isinstance(obj, str) and len(obj) > max_str:
        return obj[:max_str] + "…"
    return obj


def _evidence_pass(filters_applied: list[dict], query_text: str) -> dict:
    """Deterministic M5 evidence audit over post-resolution filters.

    ``filters_applied`` is polymorphic (issue #59 Defect B): retrieve steps
    store real filter dicts (with a ``field`` key) while sample steps store
    ``{"strategy", "n"}``. Only field-bearing entries are auditable; the
    rest are skipped so a sample-shaped entry never crashes the audit.
    """
    filter_dicts = [f for f in filters_applied if isinstance(f, dict) and "field" in f]
    if not filter_dicts:
        return {"error": "no auditable filters (no field-bearing entries)"}
    try:
        filters = [Filter(**f) for f in filter_dicts]
    except Exception as e:
        return {"error": f"filter reconstruction failed: {e}"}
    if not filters:
        return {"error": "no filters to audit"}
    plan = QueryPlan(query_text=query_text, filters=filters)
    sql, params = build_full_query(plan)
    conn = get_connection(DB_PATH)
    try:
        rows = fetch_candidates(conn, sql, params)
        sample_evidence = []
        for row in rows[:EVIDENCE_SAMPLE_CAP]:
            ev_list = []
            for f in filters:
                try:
                    ev = extract_evidence_for_filter(f, row)
                    ev_list.append(_truncate(ev.model_dump()))
                except Exception as e:
                    ev_list.append(
                        {
                            "field": str(f.field),
                            "source": "extraction_failed",
                            "extraction_error": str(e),
                        }
                    )
            sample_evidence.append({"record_id": row["mms_id"], "evidence": ev_list})
        return {
            "sql": sql,
            "sql_parameters": _truncate(dict(params)),
            "total_count": len(rows),
            "evidence_sample": sample_evidence,
        }
    finally:
        conn.close()


async def run_test(test: dict) -> dict:
    result = {
        "test_id": test["test_id"],
        "language": test.get("language"),
        "user_query": test["user_query"],
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        plan = await interpret(test["user_query"])
        result["actual_m3_plan"] = _truncate(plan.model_dump(), max_list=30)
    except Exception as e:
        result["interpreter_error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-1500:]
        return result

    if plan.clarification:
        result["outcome"] = "clarification"
        result["clarification_text"] = plan.clarification
        return result

    try:
        exec_result = chat_execute_plan(plan, DB_PATH, original_query=test["user_query"])
        result["outcome"] = "executed"
        result["total_record_count"] = exec_result.total_record_count
        result["steps"] = [_dump_step_result(sr) for sr in exec_result.steps_completed]
    except Exception as e:
        result["executor_error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-1500:]
        return result

    # Evidence audit per retrieve/sample step that produced a RecordSet
    audits = []
    for sr in exec_result.steps_completed:
        if isinstance(sr.data, RecordSet) and sr.data.filters_applied:
            audit = _evidence_pass(sr.data.filters_applied, test["user_query"])
            audit["step_index"] = sr.step_index
            audits.append(audit)
    result["actual_m4_evidence"] = audits
    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="run only these test_ids")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    tests = suite["test_cases"]
    if args.only:
        tests = [t for t in tests if t["test_id"] in set(args.only)]

    out_dir = args.out or Path(f"data/runs/diagnostic_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)

    combined = []
    for i, test in enumerate(tests, 1):
        print(f"[{i}/{len(tests)}] {test['test_id']} … ", end="", flush=True)
        r = await run_test(test)
        combined.append(r)
        outcome = r.get("outcome") or r.get("interpreter_error", "error")[:60]
        counts = r.get("total_record_count")
        print(f"{outcome}" + (f" ({counts} records)" if counts is not None else ""))
        (out_dir / f"{test['test_id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    (out_dir / "_combined.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nArtifacts: {out_dir}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
