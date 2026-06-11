"""Issues #3 + #4 acceptance: replay the four stored zero-result plans
(2026-06-10-postfix benchmark run) whose entity resolution failed, and
assert the executor recovers real records instead of querying the
literal '$step_0'. Fully deterministic — stored plans + real DB.

Floors reflect the data's actual ceilings (verified by SQL):
Bomberg publisher=5; Aldus: publisher aldus/aldo=5 ∪ agent manuzio=7;
Plantin publisher=12.
"""
import json
from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    AggregateParams, EnrichParams, ExecutionStep, FindConnectionsParams,
    InterpretationPlan, ResolveAgentParams, ResolvePublisherParams,
    RetrieveParams, SampleParams, StepAction,
)

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")
STORED = Path("data/eval/runs/2026-06-10-postfix/results.json")

_PARAMS = {
    "resolve_agent": ResolveAgentParams,
    "resolve_publisher": ResolvePublisherParams,
    "retrieve": RetrieveParams,
    "aggregate": AggregateParams,
    "find_connections": FindConnectionsParams,
    "enrich": EnrichParams,
    "sample": SampleParams,
}


@pytest.fixture(autouse=True)
def _require_artifacts():
    if not DB_PATH.exists() or not STORED.exists():
        pytest.skip("real DB or stored benchmark run not available")


def _replay(query_id: str):
    entry = next(e for e in json.loads(STORED.read_text()) if e["query_id"] == query_id)
    steps = [
        ExecutionStep(
            action=StepAction(s["action"]),
            params=_PARAMS[s["action"]](**s["params"]),
            label=s["label"],
            depends_on=[],
        )
        for s in entry["plan"]["execution_steps"]
    ]
    plan = InterpretationPlan(
        intents=entry["plan"]["intents"], reasoning="replay",
        confidence=0.9, directives=[], execution_steps=steps,
    )
    return execute_plan(plan, DB_PATH)


@pytest.mark.parametrize("query_id,floor", [
    ("q01", 5),   # Daniel Bomberg in Venice
    ("q04", 10),  # Aldo Manuzio (publisher ∪ agent routes)
    ("q25", 1),   # aggregate-derived ref, filter dropped
    ("q51", 12),  # דפוס פלנטין via Latin variant token
])
def test_unresolved_ref_plans_recover(query_id, floor):
    result = _replay(query_id)
    assert result.total_record_count >= floor
    notes = [n for s in result.steps_completed
             for n in getattr(s.data, "relaxations", [])]
    assert notes, "recovery must be recorded as relaxation evidence"
    # the literal ref must never appear as an executed filter value
    for s in result.steps_completed:
        for f in getattr(s.data, "filters_applied", []) or []:
            assert f.get("value") != "$step_0", "literal step ref was queried!"
