"""Issue #5 post-fix verification: empty-plan rate + execution recall."""
import asyncio, json
from pathlib import Path
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan

QUERIES = {
    "q14": "Books related to Napoleon",
    "q27": "What Italian language books are in the collection?",
    "q29": "What Yiddish texts are in the collection?",
    "q30": "Books printed in Jerusalem",
}
DB = Path("data/index/bibliographic.db")

async def main():
    out = []
    for qid, q in QUERIES.items():
        for attempt in range(1, 4):
            plan = await interpret(q)
            rec = {"qid": qid, "attempt": attempt,
                   "steps": len(plan.execution_steps),
                   "dropped": plan.dropped_steps}
            if plan.execution_steps:
                result = execute_plan(plan, DB)
                rec["records"] = result.total_record_count
            out.append(rec)
            print(f'{qid} #{attempt}: steps={rec["steps"]} dropped={len(rec["dropped"])} records={rec.get("records")}', flush=True)
            await asyncio.sleep(3)
    empty = [r for r in out if r["steps"] == 0]
    zero = [r for r in out if r.get("records") == 0]
    print(f"\nempty plans: {len(empty)}/12 | zero-record runs: {len(zero)}/12")
    Path("data/eval/runs/2026-06-11-issue5-forensics/postfix_verify.json").write_text(json.dumps(out, indent=1))

asyncio.run(main())
