"""Acceptance regression for issue #2: multi-concept Hebrew curatorial query.

"שיעור שעוסק באמנות, מפות וקרטוגרפיה. מה תציע לי להראות מהאוסף?"
previously returned 0 records because three coordinate topics were ANDed
and the catalog's vocabulary never says "cartography". These tests run the
deterministic executor directly (no LLM) against the real DB.
"""
from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    ExecutionStep,
    InterpretationPlan,
    RetrieveParams,
    SampleParams,
    StepAction,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")

# Real records ChatGPT referenced by (fabricated ID but) real title — they
# exist in our collection and MUST be recoverable (issue #2 acceptance).
RELAND_PALAESTINA_1714 = "9933749415904146"
SURVEY_OF_WESTERN_PALESTINE = "990014484230204146"
BILDER_GEOGRAPHIE_1736 = "990020368010204146"


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def test_worst_case_anded_plan_recovers_via_ladder():
    """Even if the interpreter still emits the bad single-step AND plan,
    the executor ladder must recover a non-empty, relevant CandidateSet."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="issue #2 regression: worst-case AND plan",
        directives=[],
        confidence=0.9,
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="maps"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
                ]),
                label="art maps cartography (ANDed)",
            )
        ],
    )
    result = execute_plan(plan, DB_PATH)
    step = result.steps_completed[0]
    assert step.status == "ok"
    assert step.data.total_count >= 10
    for target in (RELAND_PALAESTINA_1714, SURVEY_OF_WESTERN_PALESTINE, BILDER_GEOGRAPHIE_1736):
        assert target in step.data.mms_ids
    assert step.data.relaxations, "ladder must record its evidence"


def test_good_curatorial_plan_returns_curated_sample():
    """The plan shape the re-prompted interpreter should emit: one retrieve
    per concept, curated sample over the union."""
    plan = InterpretationPlan(
        intents=["curation", "topical"],
        reasoning="issue #2 regression: decomposed curatorial plan",
        directives=[],
        confidence=0.9,
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                ]),
                label="art",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
                ]),
                label="geography/cartography",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.PHYSICAL_DESC, op=FilterOp.CONTAINS, value="map"),
                ]),
                label="contains maps",
            ),
            ExecutionStep(
                action=StepAction.SAMPLE,
                params=SampleParams(scope="$step_0+$step_1+$step_2", n=12, strategy="notable"),
                label="curate",
                depends_on=[0, 1, 2],
            ),
        ],
    )
    result = execute_plan(plan, DB_PATH)
    geo = result.steps_completed[1].data
    phys = result.steps_completed[2].data
    sample = result.steps_completed[3].data
    assert RELAND_PALAESTINA_1714 in geo.mms_ids
    assert phys.total_count >= 50  # 106 records have maps in MARC 300
    assert 1 <= len(sample.mms_ids) <= 12
    union = set(result.steps_completed[0].data.mms_ids) | set(geo.mms_ids) | set(phys.mms_ids)
    assert set(sample.mms_ids) <= union, "no fabricated identifiers — sample ⊆ retrieved union"
