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
    npath = batch_client.write_batch_jsonl(narration, output_dir / "narration_batch.jsonl")
    nbatch = batch_client.poll_until_done(client, batch_client.submit_batch(client, npath, "narrator-gold narrations"))
    nresults = batch_client.download_results(client, nbatch)
    matched, missing = batch_client.reconcile(narration, nresults)
    if missing:
        print(f"WARNING: {len(missing)} narrations missing: {missing}")

    judge_reqs: list[dict] = []
    narratives: dict[str, str] = {}
    for cid, body in matched.items():
        case_id, model = cid.split("::")[0], cid.split("::")[1]
        text, _usage = extract_narrative(body)
        narratives[cid] = text
        judge_reqs.append(
            build_judge_request(
                cases[case_id],
                candidate_text=text,
                judge_model=judge_model,
                candidate_model=model,
                max_output_tokens=max_judge_tokens,
                reasoning_effort="low",
            )
        )
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
                "narrative": narratives.get(f"{case_id}::{model}", ""),
            }
        )
    (output_dir / "results.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_report(output_dir, rows, models)
    print(f"Done. Report at {output_dir / 'REPORT.md'}")


def _write_report(output_dir: Path, rows: list[dict], models: list[str]) -> None:
    """Rank models by mean composite; write REPORT.md."""
    by_model: dict[str, list[dict]] = {m: [] for m in models}
    for r in rows:
        if "composite" in r:
            by_model.setdefault(r["model"], []).append(r)
    lines = ["# Narrator Gold-Standard Eval — Report", ""]
    lines.append("| Model | Mean composite (0-3) | Fabrications | Cases |")
    lines.append("|-------|----------------------|--------------|-------|")
    ranked = sorted(by_model.items(), key=lambda kv: -(sum(x["composite"] for x in kv[1]) / len(kv[1]) if kv[1] else 0))
    for model, rs in ranked:
        if not rs:
            lines.append(f"| {model} | n/a | n/a | 0 |")
            continue
        mean = sum(x["composite"] for x in rs) / len(rs)
        fab = sum(1 for x in rs if x["fabrication"])
        lines.append(f"| {model} | {mean:.2f} | {fab} | {len(rs)} |")
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
