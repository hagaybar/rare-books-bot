"""Generate comparison reports from evaluation results."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def generate_report(
    results: list[dict[str, Any]],
    output_dir: Path,
) -> Path:
    """Generate evaluation report artifacts in output_dir.

    Creates:
      - results.json (raw results)
      - scores.json (aggregated scores per model x stage)
      - human_review.csv (template for human calibration)
      - summary.md (readable comparison table)

    Returns the output directory path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Raw results
    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str)
    )

    # 2. Aggregated scores
    scores = _aggregate_scores(results)
    (output_dir / "scores.json").write_text(
        json.dumps(scores, indent=2, default=str)
    )

    # 3. Human review CSV
    _write_human_review_csv(results, output_dir / "human_review.csv")

    # 4. Summary markdown
    _write_summary_md(scores, output_dir / "summary.md")

    return output_dir


def _aggregate_scores(results: list[dict]) -> list[dict]:
    """Aggregate scores by model x stage."""
    buckets: dict[tuple[str, str], list[float]] = {}
    latencies: dict[tuple[str, str], list[float]] = {}
    costs: dict[tuple[str, str], list[float]] = {}
    tokens: dict[tuple[str, str], list[int]] = {}

    for r in results:
        key = (r["model"], r["stage"])
        buckets.setdefault(key, []).append(r.get("score_combined", 0))
        latencies.setdefault(key, []).append(r.get("latency_ms", 0))
        costs.setdefault(key, []).append(r.get("cost_usd", 0))
        tokens.setdefault(key, []).append(r.get("total_tokens", 0))

    aggregated = []
    for (model, stage), score_list in sorted(buckets.items()):
        n = len(score_list)
        aggregated.append({
            "model": model,
            "stage": stage,
            "avg_score": round(sum(score_list) / n, 2) if n else 0,
            "avg_latency_ms": round(sum(latencies[model, stage]) / n) if n else 0,
            "avg_cost_usd": round(sum(costs[model, stage]) / n, 4) if n else 0,
            "avg_tokens": round(sum(tokens[model, stage]) / n) if n else 0,
            "n_queries": n,
        })
    return aggregated


def _write_human_review_csv(results: list[dict], path: Path) -> None:
    """Write human review template CSV."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["query_id", "model", "stage", "auto_score", "human_score", "notes"])
        for r in results:
            writer.writerow([
                r.get("query_id", ""),
                r.get("model", ""),
                r.get("stage", ""),
                round(r.get("score_combined", 0), 2),
                "",  # Human fills this in
                "",  # Human fills this in
            ])


def _write_summary_md(scores: list[dict], path: Path) -> None:
    """Write readable summary markdown table."""
    lines = [
        f"# Evaluation Summary — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| Model | Stage | Avg Score | Avg Latency | Avg Cost | Avg Tokens | N |",
        "|-------|-------|-----------|-------------|----------|------------|---|",
    ]
    for s in scores:
        lines.append(
            f"| {s['model']} | {s['stage']} | {s['avg_score']} "
            f"| {s['avg_latency_ms']}ms | ${s['avg_cost_usd']:.4f} "
            f"| {s['avg_tokens']} | {s['n_queries']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines))
