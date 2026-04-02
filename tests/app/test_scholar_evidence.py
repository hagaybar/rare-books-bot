"""Evidence capture tests for the scholar pipeline.

Runs the 20 historian evaluation queries through the full pipeline
and saves traces to reports/scholar-pipeline/<run-id>/.

These tests require OPENAI_API_KEY and bibliographic.db.
Mark with @pytest.mark.integration.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

# Skip entire module unless explicitly opted in via RUN_SCHOLAR_EVIDENCE=1.
# These are expensive integration tests that make real LLM calls via litellm.
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SCHOLAR_EVIDENCE"),
    reason="Requires RUN_SCHOLAR_EVIDENCE=1 (expensive LLM integration tests)",
)

HISTORIAN_QUERIES = [
    ("Q01", "books printed by Bragadin press in Venice"),
    ("Q02", "Hebrew books printed in Amsterdam between 1620 and 1650"),
    ("Q03", "books published by the Aldine Press"),
    ("Q04", "incunabula in the collection (books printed before 1500)"),
    ("Q05", "books printed in Constantinople"),
    ("Q06", "works by Johann Buxtorf"),
    ("Q07", "works by Moses Mendelssohn"),
    ("Q08", "works by Maimonides"),
    ("Q09", "works by Josephus Flavius"),
    ("Q10", "books on Jewish philosophy"),
    ("Q11", "books from the Napoleonic era 1795-1815"),
    ("Q12", "materials about Ethiopia or Ethiopian Jews"),
    ("Q13", "books about book collecting or bibliography"),
    ("Q14", "chronological distribution of the collection"),
    ("Q15", "major Hebrew printing centers represented"),
    ("Q16", "biblical commentaries"),
    ("Q17", "Hebrew grammar books"),
    ("Q18", "Talmud editions"),
    ("Q19", "works by Joseph Karo"),
    ("Q20", "curated selection for Hebrew printing exhibit"),
]

BIB_DB = Path("data/index/bibliographic.db")


@pytest.fixture(scope="module")
def run_dir():
    """Create a timestamped run directory for evidence."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = Path(f"reports/scholar-pipeline/{run_id}")
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.mark.integration
@pytest.mark.parametrize("query_id,query_text", HISTORIAN_QUERIES)
def test_historian_query(query_id, query_text, run_dir):
    """Run a historian query and save the evidence trace."""
    import asyncio

    from scripts.chat.executor import execute_plan
    from scripts.chat.interpreter import interpret
    from scripts.chat.narrator import narrate

    trace = {
        "query_id": query_id,
        "query": query_text,
        "timestamp": datetime.now().isoformat(),
    }

    # Stage 1: Interpret
    t0 = time.time()
    plan = asyncio.run(interpret(query_text, session_context=None))
    trace["interpreter"] = {
        "plan": plan.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Stage 2: Execute
    t0 = time.time()
    result = execute_plan(plan, BIB_DB)
    trace["executor"] = {
        "result": result.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Stage 3: Narrate
    t0 = time.time()
    response = asyncio.run(narrate(query_text, result))
    trace["narrator"] = {
        "response": response.model_dump(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

    # Scores (null until manually evaluated)
    trace["scores"] = {
        "accuracy": None,
        "richness": None,
        "cross_ref": None,
        "narrative": None,
        "pedagogical": None,
    }

    # Save trace
    safe_name = (
        query_id.lower()
        + "_"
        + query_text[:40].replace(" ", "_").replace("/", "_")
    )
    out_path = run_dir / f"{safe_name}.json"
    out_path.write_text(
        json.dumps(trace, indent=2, ensure_ascii=False, default=str)
    )

    # Basic assertion: pipeline didn't crash
    assert response.narrative is not None
    assert len(response.narrative) > 0


@pytest.mark.integration
def test_generate_summary(run_dir):
    """Generate summary.md after all queries run."""
    traces = list(run_dir.glob("*.json"))
    lines = [
        "# Scholar Pipeline Evidence Run\n",
        f"**Date:** {datetime.now().isoformat()}\n",
    ]
    lines.append(f"**Queries:** {len(traces)}\n\n")
    lines.append("| Query | Records | Latency (ms) | Has Narrative |\n")
    lines.append("|-------|---------|-------------|---------------|\n")

    for path in sorted(traces):
        t = json.loads(path.read_text())
        record_count = sum(
            s.get("record_count", 0) or 0
            for s in t.get("executor", {})
            .get("result", {})
            .get("steps_completed", [])
        )
        total_ms = (
            t.get("interpreter", {}).get("latency_ms", 0)
            + t.get("executor", {}).get("latency_ms", 0)
            + t.get("narrator", {}).get("latency_ms", 0)
        )
        has_narrative = bool(
            t.get("narrator", {}).get("response", {}).get("narrative")
        )
        lines.append(
            f"| {t['query_id']} | {record_count} | {total_ms} "
            f"| {'Yes' if has_narrative else 'No'} |\n"
        )

    (run_dir / "summary.md").write_text("".join(lines))
    assert (run_dir / "summary.md").exists()
