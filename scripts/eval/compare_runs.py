"""Compare two eval runs per query (2026-06-10 framework enhancement).

The benchmark loop's missing piece: a fix must hold or improve the WHOLE
benchmark, not just the example that motivated it. This joins two
results.json files on query_id and reports per-query score deltas plus
recall changes (zero-result count), so regressions on previously-good
queries are visible immediately.

Usage:
    python scripts/eval/compare_runs.py \
        data/eval/runs/2026-06-10-baseline/results.json \
        data/eval/runs/2026-06-10-postfix/results.json \
        [--out comparison.md]
"""
import argparse
import json
from pathlib import Path
from typing import Any


def _score(entry: dict[str, Any]) -> float | None:
    if not entry.get("success"):
        return 0.0
    return entry.get("score_combined")


def compare_results(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    """Join two result lists on query_id; return per-query deltas + summary."""
    before_by_id = {e["query_id"]: e for e in before}
    after_by_id = {e["query_id"]: e for e in after}
    common = sorted(set(before_by_id) & set(after_by_id))

    queries = []
    before_scores, after_scores = [], []
    zero_before = zero_after = 0
    for qid in common:
        b, a = before_by_id[qid], after_by_id[qid]
        sb, sa = _score(b), _score(a)
        if sb is not None:
            before_scores.append(sb)
        if sa is not None:
            after_scores.append(sa)
        zb = (b.get("recall") or {}).get("zero_result")
        za = (a.get("recall") or {}).get("zero_result")
        zero_before += 1 if zb else 0
        zero_after += 1 if za else 0
        queries.append({
            "query_id": qid,
            "before": sb,
            "after": sa,
            "delta": round((sa or 0) - (sb or 0), 2) if sb is not None and sa is not None else None,
            "zero_before": zb,
            "zero_after": za,
        })

    summary = {
        "common_queries": len(common),
        "avg_before": round(sum(before_scores) / len(before_scores), 3) if before_scores else None,
        "avg_after": round(sum(after_scores) / len(after_scores), 3) if after_scores else None,
        "regressions": sum(1 for q in queries if q["delta"] is not None and q["delta"] <= -1.0),
        "improvements": sum(1 for q in queries if q["delta"] is not None and q["delta"] >= 1.0),
        "zero_results_before": zero_before,
        "zero_results_after": zero_after,
    }
    return {"summary": summary, "queries": queries}


def render_markdown(cmp: dict[str, Any], before_name: str, after_name: str) -> str:
    s = cmp["summary"]
    lines = [
        f"# Eval comparison: {before_name} → {after_name}",
        "",
        f"- Common queries: {s['common_queries']}",
        f"- Avg judge score: {s['avg_before']} → {s['avg_after']}",
        f"- Regressions (Δ ≤ -1.0): {s['regressions']} | Improvements (Δ ≥ +1.0): {s['improvements']}",
        f"- Zero-result queries: {s['zero_results_before']} → {s['zero_results_after']}"
        " (recall data may be absent in older runs)",
        "",
        "| query | before | after | Δ | zero→ |",
        "|---|---|---|---|---|",
    ]
    for q in cmp["queries"]:
        flag = ""
        if q["delta"] is not None and q["delta"] <= -1.0:
            flag = " ⚠"
        zero = f"{q['zero_before']}→{q['zero_after']}" if q["zero_after"] is not None else "-"
        lines.append(
            f"| {q['query_id']}{flag} | {q['before']} | {q['after']} | {q['delta']} | {zero} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    cmp = compare_results(before, after)
    md = render_markdown(cmp, args.before.parent.name, args.after.parent.name)
    print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"\nWritten to {args.out}")


if __name__ == "__main__":
    main()
