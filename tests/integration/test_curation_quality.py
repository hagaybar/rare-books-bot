"""Issue #6 acceptance: the 'notable' strategy produces diverse, visually
rich lesson sets — not just the N oldest items. Deterministic, real DB.
"""
import re
import sqlite3
from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    ExecutionStep, InterpretationPlan, SampleParams, StepAction,
)

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")
VISUAL_RE = re.compile(r"map|plate|facsim|ill|engrav", re.IGNORECASE)


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("Bibliographic database not available")


def _sample(strategy, n=12):
    plan = InterpretationPlan(
        intents=["curation"], reasoning="issue-6 acceptance", confidence=0.9,
        directives=[],
        execution_steps=[ExecutionStep(
            action=StepAction.SAMPLE,
            params=SampleParams(scope="full_collection", n=n, strategy=strategy),
            label="curate")],
    )
    result = execute_plan(plan, DB_PATH)
    return result.steps_completed[0].data.mms_ids


def _dimensions(mms_ids):
    conn = sqlite3.connect(str(DB_PATH))
    try:
        ph = ",".join("?" for _ in mms_ids)
        rows = conn.execute(
            f"SELECT r.mms_id, MIN(i.date_start), MIN(i.place_norm), "
            f"(SELECT GROUP_CONCAT(pd.value,' ') FROM physical_descriptions pd "
            f" WHERE pd.record_id = r.id) "
            f"FROM records r LEFT JOIN imprints i ON i.record_id = r.id "
            f"WHERE r.mms_id IN ({ph}) GROUP BY r.mms_id",
            list(mms_ids),
        ).fetchall()
    finally:
        conn.close()
    decades = {row[1] // 10 * 10 for row in rows if row[1]}
    places = {row[2] for row in rows if row[2]}
    visual = sum(1 for row in rows if row[3] and VISUAL_RE.search(row[3]))
    return decades, places, visual


def test_notable_is_diverse_and_visual():
    notable = _sample("notable")
    assert len(notable) == 12
    decades, places, visual = _dimensions(notable)
    assert len(decades) >= 4, f"decade spread too narrow: {sorted(decades)}"
    assert len(places) >= 3, f"place spread too narrow: {sorted(places)}"
    assert visual >= 3, f"only {visual} items with visual material"


def test_notable_beats_earliest_on_diversity():
    notable_decades, _, _ = _dimensions(_sample("notable"))
    earliest_decades, _, _ = _dimensions(_sample("earliest"))
    assert len(notable_decades) > len(earliest_decades), (
        f"notable ({sorted(notable_decades)}) must span more decades than "
        f"the oldest-N baseline ({sorted(earliest_decades)})")
