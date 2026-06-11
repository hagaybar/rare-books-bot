"""Narrator groundedness probe (committee eval E3, approved 2026-06-11).

Questions: (1) Does the narrator judge actually measure groundedness —
does giving it FULL grounding change its accuracy scores vs the thin
10-line summary it gets today? (2) Do judges correlate with a
deterministic hallucination/coverage check? (3) Does gpt-4.1 judging
favor gpt-4.1 narratives over gpt-4.1-mini ones beyond what the
deterministic check justifies?

Cost guard: 15 queries -> 15 interpreter (mini) + 30 narrator + 90 judge
calls ~= $0.6.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan
from scripts.chat.narrator import narrate
from scripts.eval.judge import score_narrator
from scripts.eval.query_set import load_query_set

DB = Path("data/index/bibliographic.db")
OUT = Path(__file__).parent / "results.json"
MMS_RE = re.compile(r"\b9{2}\d{8,14}\b")

# 15 diverse queries that had non-zero recall in the 2026-06-10-postfix run
QUERY_IDS = ["q03", "q05", "q08", "q10", "q12", "q20", "q22", "q31", "q37",
             "q41", "q43", "q47", "q50", "q56", "q57"]


def thin_summary(exec_result) -> str:
    records = exec_result.grounding.records[:10]
    return "\n".join(f"- {r.title} ({r.date_display}, {r.place})" for r in records)


def full_summary(exec_result) -> str:
    g = exec_result.grounding
    lines = [f"TOTAL MATCHING RECORDS: {exec_result.total_record_count}",
             f"RECORDS SHOWN: {len(g.records)}"]
    for r in g.records[:30]:
        subj = "; ".join((r.subjects or [])[:3])
        lines.append(f"- [{r.mms_id}] {r.title} | {r.date_display} | {r.place} | "
                     f"{r.publisher} | subjects: {subj}")
    if g.agents:
        lines.append("AGENTS: " + ", ".join(a.canonical_name for a in g.agents[:10]))
    return "\n".join(lines)


def deterministic_check(narrative: str, exec_result) -> dict:
    grounded_ids = {r.mms_id for r in exec_result.grounding.records}
    cited = set(MMS_RE.findall(narrative))
    hallucinated = sorted(cited - grounded_ids)
    titles = [(r.title or "")[:25].casefold() for r in exec_result.grounding.records if r.title]
    mentioned = sum(1 for t in titles if t and t in narrative.casefold())
    return {
        "cited_ids": len(cited),
        "hallucinated_ids": hallucinated,
        "title_coverage": round(mentioned / len(titles), 3) if titles else None,
    }


async def _retry(coro_fn, attempts=5, base_sleep=15):
    for i in range(attempts):
        try:
            return await coro_fn()
        except Exception as e:
            if "RateLimit" not in type(e).__name__ and "rate limit" not in str(e).lower():
                raise
            wait = base_sleep * (i + 1)
            print(f"  rate-limited; sleeping {wait}s", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError("rate limit retries exhausted")


async def run_one(q):
    plan = await _retry(lambda: interpret(q.query))
    exec_result = execute_plan(plan, DB)
    if exec_result.total_record_count == 0 and not exec_result.grounding.records:
        return {"query_id": q.id, "skipped": "zero grounding"}
    thin, full = thin_summary(exec_result), full_summary(exec_result)
    out = {"query_id": q.id, "total_records": exec_result.total_record_count,
           "narratives": {}}
    for nmodel in ("gpt-4.1", "gpt-4.1-mini"):
        resp = await _retry(lambda nm=nmodel: narrate(q.query, exec_result, model=nm))
        det = deterministic_check(resp.narrative, exec_result)
        judges = {}
        for jname, (summary, jmodel) in {
            "thin_41": (thin, "gpt-4.1"),
            "full_41": (full, "gpt-4.1"),
            "full_mini": (full, "gpt-4.1-mini"),
        }.items():
            try:
                s = await _retry(lambda su=summary, jm=jmodel: score_narrator(q, resp.narrative, su, judge_model=jm))
                judges[jname] = {"accuracy": s.accuracy, "completeness": s.completeness,
                                 "combined": round(s.combined, 2)}
            except Exception as e:
                judges[jname] = {"error": str(e)[:120]}
        out["narratives"][nmodel] = {
            "len": len(resp.narrative), "deterministic": det, "judges": judges}
    return out


async def main():
    queries = {q.id: q for q in load_query_set(Path("data/eval/queries.json"))}
    picked = [queries[i] for i in QUERY_IDS if i in queries]
    done_ids = set()
    results = []
    if OUT.exists():  # resume partial runs
        results = json.loads(OUT.read_text())
        done_ids = {r["query_id"] for r in results}
    for n, q in enumerate(picked, 1):  # serial: stay under 30k TPM for gpt-4.1
        if q.id in done_ids:
            continue
        results.append(await run_one(q))
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(f"done {n}/{len(picked)} ({q.id})", flush=True)
        await asyncio.sleep(20)
    print(f"wrote {OUT}")

if __name__ == "__main__":
    asyncio.run(main())
