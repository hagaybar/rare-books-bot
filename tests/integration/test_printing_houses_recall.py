"""Regression for the Jewish-printing-houses failure (2026-06-10 user report).

"אני מעוניין לערוך שיעור על בתי דפוס יהודיים באירופה" returned 0 records
because the interpreter (a) ANDed three Hebrew subject concepts and
(b) fabricated malformed hard filters: place IN
['venice,amsterdam,prague,warsaw,wordsworth'] — one comma-joined string,
including a hallucinated non-city. These tests replay that worst-case plan
through the deterministic executor against the real DB.
"""
from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    ExecutionStep,
    InterpretationPlan,
    RetrieveParams,
    StepAction,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def test_malformed_fabricated_plan_recovers():
    """The exact malformed plan shape the interpreter emitted on 2026-06-10."""
    plan = InterpretationPlan(
        intents=["curation"],
        reasoning="printing-houses regression: worst-case malformed plan",
        confidence=0.9,
        directives=[],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="בתי דפוס"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="יהודי"),
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="דפוס"),
                    Filter(
                        field=FilterField.IMPRINT_PLACE,
                        op=FilterOp.IN,
                        value=["venice,amsterdam,prague,warsaw,wordsworth"],
                    ),
                    Filter(
                        field=FilterField.COUNTRY,
                        op=FilterOp.IN,
                        value=["italy,netherlands,czech republic,poland,germany"],
                    ),
                ]),
                label="Jewish printing houses (malformed)",
            )
        ],
    )
    result = execute_plan(plan, DB_PATH)
    step = result.steps_completed[0]
    assert step.status == "ok"
    # Verified against the DB: subject 'jews' within the (split) city/country
    # constraints alone covers 26 records; 'printing' covers 5 more.
    assert step.data.total_count >= 5
    assert step.data.relaxations, "ladder evidence must be recorded"
    # Hard geo constraints stayed hard: every record's place is in the list.
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cities = {"venice", "amsterdam", "prague", "warsaw", "wordsworth"}
    for mms in step.data.mms_ids[:10]:
        places = {
            row[0]
            for row in conn.execute(
                "SELECT LOWER(i.place_norm) FROM imprints i "
                "JOIN records r ON i.record_id = r.id WHERE r.mms_id = ?",
                (mms,),
            )
        }
        assert places & cities, f"{mms} not in the requested cities — hard filter loosened!"
    conn.close()


def test_well_formed_printing_query_needs_no_relaxation():
    """A clean single-concept plan: subject 'printing' alone → 105 records."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="printing-houses regression: clean plan",
        confidence=0.9,
        directives=[],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(filters=[
                    Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="printing"),
                ]),
                label="printing",
            )
        ],
    )
    result = execute_plan(plan, DB_PATH)
    step = result.steps_completed[0]
    assert step.data.total_count >= 50
    assert step.data.relaxations == []
