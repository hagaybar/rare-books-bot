"""Narrator gold-standard evaluation runner (Phase 3).

Loads frozen gold cases, narrates each with every candidate model via the
OpenAI Batch API, judges each narration against the gold with a reference-
anchored rubric, and writes a ranked report. A cost-ceiling guard aborts
before any submission if projected spend exceeds the ceiling.

Usage:
    poetry run python -m scripts.eval.run_narrator_gold_eval \
      --gold-dir data/eval/narrator_gold \
      --models gpt-4.1,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini \
      --judge-model gpt-5.4 --judge-reasoning-effort low \
      --batch --cost-ceiling 2.00 \
      --max-narration-tokens 2000 --max-judge-tokens 1200 \
      --output-dir data/eval/runs/2026-06-14-narrator-gold \
      [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.eval.narrator_gold import (
    GoldCase,
    load_gold_case,
    build_narration_request,
    build_judge_request,
    extract_narrative,
    estimate_tokens,
    estimate_request_cost,
    assert_within_ceiling,
    is_reasoning_model,
)
from scripts.eval.judge import parse_gold_judgment
from scripts.eval import batch_client


def load_gold_cases(gold_dir: Path) -> list[GoldCase]:
    """Load every case sub-directory under gold_dir (those with grounding.json)."""
    cases = [load_gold_case(d) for d in sorted(gold_dir.iterdir()) if d.is_dir() and (d / "grounding.json").exists()]
    if not cases:
        raise SystemExit(f"No gold cases found under {gold_dir}")
    return cases


def build_all_narration_requests(
    gold_dir: Path, models: list[str], max_output_tokens: int, reasoning_effort: str | None
) -> list[dict]:
    cases = load_gold_cases(gold_dir)
    return [
        build_narration_request(c, m, max_output_tokens, reasoning_effort if is_reasoning_model(m) else None)
        for c in cases
        for m in models
    ]


def _cost_triples(requests: list[dict], max_output_tokens: int) -> list[tuple[str, int, int]]:
    """Map batch requests to (model, est_input_tokens, max_output_tokens) for the guard."""
    triples = []
    for r in requests:
        text = "".join(m["content"] for m in r["body"]["messages"])
        triples.append((r["body"]["model"], estimate_tokens(text), max_output_tokens))
    return triples


def dry_run(
    gold_dir: Path,
    models: list[str],
    judge_model: str,
    output_dir: Path,
    ceiling: float,
    max_narration_tokens: int,
    max_judge_tokens: int,
    reasoning_effort: str | None,
) -> float:
    """Build batch files + project worst-case cost WITHOUT submitting. Returns projected $."""
    output_dir.mkdir(parents=True, exist_ok=True)
    narration = build_all_narration_requests(gold_dir, models, max_narration_tokens, reasoning_effort)
    batch_client.write_batch_jsonl(narration, output_dir / "narration_batch.jsonl")

    n_triples = _cost_triples(narration, max_narration_tokens)
    j_triples = [(judge_model, 4000, max_judge_tokens) for _ in narration]
    projected = assert_within_ceiling(n_triples, ceiling, batch=True) + assert_within_ceiling(
        j_triples, ceiling, batch=True
    )
    assert_within_ceiling(n_triples + j_triples, ceiling, batch=True)
    print(
        f"[dry-run] {len(narration)} narrations + {len(narration)} judgments "
        f"-> projected ${projected:.4f} (ceiling ${ceiling:.2f})"
    )
    return projected


def run(
    gold_dir: Path,
    models: list[str],
    judge_model: str,
    output_dir: Path,
    ceiling: float,
    max_narration_tokens: int,
    max_judge_tokens: int,
    reasoning_effort: str | None,
) -> None:
    """Full paid run: guard -> narrate (batch) -> judge (batch) -> report."""
    from openai import OpenAI

    client = OpenAI()
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = {c.case_id: c for c in load_gold_cases(gold_dir)}

    narration = build_all_narration_requests(gold_dir, models, max_narration_tokens, reasoning_effort)
    assert_within_ceiling(
        _cost_triples(narration, max_narration_tokens) + [(judge_model, 4000, max_judge_tokens) for _ in narration],
        ceiling,
        batch=True,
    )
    # OpenAI Batch API requires a SINGLE model per batch, so submit one narration
    # batch per candidate model. Submit all first (they run concurrently), then poll.
    nresults: dict = {}
    submitted: list[tuple[str, str]] = []
    for m in models:
        m_reqs = [r for r in narration if r["body"]["model"] == m]
        if not m_reqs:
            continue
        safe = m.replace("/", "_")
        mpath = batch_client.write_batch_jsonl(m_reqs, output_dir / f"narration_{safe}.jsonl")
        bid = batch_client.submit_batch(client, mpath, f"narrator-gold narrations {m}")
        submitted.append((m, bid))
        print(f"[narration] submitted {len(m_reqs)} reqs for {m}: {bid}")
    for m, bid in submitted:
        b = batch_client.poll_until_done(client, bid)
        print(f"[narration] {m} batch -> {b.status}")
        nresults.update(batch_client.download_results(client, b))
    matched, missing = batch_client.reconcile(narration, nresults)
    if missing:
        print(f"WARNING: {len(missing)} narrations missing: {missing}")

    judge_reqs: list[dict] = []
    narratives: dict[str, str] = {}
    narr_cost: dict[str, dict] = {}
    failed_narr: list[dict] = []
    for cid, body in matched.items():
        case_id, model = cid.split("::")[0], cid.split("::")[1]
        usage = body.get("usage") or {}
        n_in = usage.get("prompt_tokens", 0)
        n_out = usage.get("completion_tokens", 0)
        cost = estimate_request_cost(model, n_in, n_out, batch=True)
        narr_cost[cid] = {"in": n_in, "out": n_out, "cost": cost}
        # A truncated/invalid narration (e.g. reasoning model hit the token cap and
        # emitted no JSON) is a real model failure, not a crash: record and continue.
        try:
            text, _ = extract_narrative(body)
        except Exception:
            reason = (body.get("choices") or [{}])[0].get("finish_reason", "parse_error")
            print(f"WARNING: unusable narration {cid} (finish={reason}); scoring as failure")
            failed_narr.append(
                {"case_id": case_id, "model": model, "in": n_in, "out": n_out,
                 "cost": cost, "reason": f"narration unusable (finish={reason})"}
            )
            continue
        narratives[cid] = text
        judge_reqs.append(
            build_judge_request(
                cases[case_id],
                candidate_text=text,
                judge_model=judge_model,
                candidate_model=model,
                max_output_tokens=max_judge_tokens,
                reasoning_effort=reasoning_effort,
            )
        )
    if not judge_reqs:
        print("ERROR: no narrations succeeded; nothing to judge. Aborting (no spend on judging).")
        (output_dir / "results.json").write_text(json.dumps(failed_narr, indent=2), encoding="utf-8")
        return
    jpath = batch_client.write_batch_jsonl(judge_reqs, output_dir / "judge_batch.jsonl")
    jbatch = batch_client.poll_until_done(client, batch_client.submit_batch(client, jpath, "narrator-gold judging"))
    jresults = batch_client.download_results(client, jbatch)

    rows = []
    for jreq in judge_reqs:
        cid = jreq["custom_id"]
        case_id, model, _ = cid.split("::")
        body = jresults.get(cid)
        if body is None:
            rows.append({"case": case_id, "model": model, "error": "missing judgment"})
            continue
        score = parse_gold_judgment(body["choices"][0]["message"]["content"])
        j_usage = body.get("usage", {})
        j_in = j_usage.get("prompt_tokens", 0)
        j_out = j_usage.get("completion_tokens", 0)
        nm = narr_cost.get(f"{case_id}::{model}", {})
        rows.append(
            {
                "case": case_id,
                "model": model,
                "composite": round(score.composite, 4),
                "grounding": score.grounding,
                "coverage": score.coverage,
                "evidence_fidelity": score.evidence_fidelity,
                "scholarly_quality": score.scholarly_quality,
                "scope_handling": score.scope_handling,
                "fabrication": score.fabrication_detected,
                "fabricated_claims": score.fabricated_claims,
                "rationale": score.rationale,
                # measured cost (batch pricing, actual tokens incl. reasoning):
                "narration_in_tok": nm.get("in", 0),
                "narration_out_tok": nm.get("out", 0),
                "narration_cost_usd": round(nm.get("cost", 0.0), 6),  # production-relevant
                "judge_in_tok": j_in,
                "judge_out_tok": j_out,
                "judge_cost_usd": round(estimate_request_cost(judge_model, j_in, j_out, batch=True), 6),
                "narrative": narratives.get(f"{case_id}::{model}", ""),
            }
        )
    # Failed narrations count as composite-0 results (real model failures), cost included.
    for fn in failed_narr:
        rows.append(
            {
                "case": fn["case_id"],
                "model": fn["model"],
                "composite": 0.0,
                "grounding": 0,
                "coverage": 0,
                "evidence_fidelity": 0,
                "scholarly_quality": 0,
                "scope_handling": 0,
                "fabrication": False,
                "fabricated_claims": [],
                "rationale": fn["reason"],
                "narration_in_tok": fn["in"],
                "narration_out_tok": fn["out"],
                "narration_cost_usd": round(fn["cost"], 6),
                "judge_in_tok": 0,
                "judge_out_tok": 0,
                "judge_cost_usd": 0.0,
                "narrative": "",
            }
        )
    (output_dir / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_report(output_dir, rows, models)
    print(f"Done. Report at {output_dir / 'REPORT.md'}")


def _write_report(output_dir: Path, rows: list[dict], models: list[str]) -> None:
    """Rank models by mean composite; report quality alongside measured cost."""
    by_model: dict[str, list[dict]] = {m: [] for m in models}
    for r in rows:
        if "composite" in r:
            by_model.setdefault(r["model"], []).append(r)

    def mean_narr_cost(rs: list[dict]) -> float:
        return sum(x.get("narration_cost_usd", 0.0) for x in rs) / len(rs) if rs else 0.0

    baseline = "gpt-4.1"
    base_cost = mean_narr_cost(by_model.get(baseline, []))

    lines = ["# Narrator Gold-Standard Eval — Report", ""]
    lines.append(
        "Judge: gpt-5.4 (reasoning_effort=low) · OpenAI Batch pricing · "
        "costs are MEASURED from actual tokens (incl. reasoning)."
    )
    lines.append("")
    lines.append("| Model | Mean composite (0-3) | Fabrications | Cases | $/query (narration) | vs gpt-4.1 |")
    lines.append("|-------|----------------------|--------------|-------|---------------------|------------|")
    ranked = sorted(by_model.items(), key=lambda kv: -(sum(x["composite"] for x in kv[1]) / len(kv[1]) if kv[1] else 0))
    for model, rs in ranked:
        if not rs:
            lines.append(f"| {model} | n/a | n/a | 0 | n/a | n/a |")
            continue
        mean = sum(x["composite"] for x in rs) / len(rs)
        fab = sum(1 for x in rs if x["fabrication"])
        qcost = mean_narr_cost(rs)
        if model == baseline:
            delta = "baseline"
        elif base_cost > 0:
            delta = f"{(1 - qcost / base_cost) * 100:+.0f}% cost"
        else:
            delta = "—"
        lines.append(f"| {model} | {mean:.2f} | {fab} | {len(rs)} | ${qcost:.5f} | {delta} |")

    total_eval = sum(
        x.get("narration_cost_usd", 0.0) + x.get("judge_cost_usd", 0.0)
        for x in rows
        if "composite" in x
    )
    lines.append("")
    lines.append(f"**Total eval spend (this run, batch): ${total_eval:.4f}** (narration + gpt-5.4 judging).")
    lines.append("")
    lines.append(
        "*$/query is the production-relevant narration cost (judge cost is eval-only). "
        "The 'vs gpt-4.1' column shows cost reduction, NOT quality — read it alongside the "
        "composite score.*"
    )
    (output_dir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Narrator gold-standard evaluation")
    p.add_argument("--gold-dir", type=Path, default=Path("data/eval/narrator_gold"))
    p.add_argument("--models", required=True, help="Comma-separated candidate models")
    p.add_argument("--judge-model", default="gpt-5.4")
    p.add_argument("--judge-reasoning-effort", default="low")
    p.add_argument("--batch", action="store_true", help="(always batched; kept for clarity)")
    p.add_argument("--cost-ceiling", type=float, default=2.00)
    p.add_argument("--max-narration-tokens", type=int, default=2000)
    p.add_argument("--max-judge-tokens", type=int, default=1200)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true", help="Build batches + estimate, no submit")
    args = p.parse_args()
    models = [m.strip() for m in args.models.split(",")]

    if args.dry_run:
        dry_run(
            args.gold_dir,
            models,
            args.judge_model,
            args.output_dir,
            args.cost_ceiling,
            args.max_narration_tokens,
            args.max_judge_tokens,
            args.judge_reasoning_effort,
        )
        return
    run(
        args.gold_dir,
        models,
        args.judge_model,
        args.output_dir,
        args.cost_ceiling,
        args.max_narration_tokens,
        args.max_judge_tokens,
        args.judge_reasoning_effort,
    )


if __name__ == "__main__":
    main()
