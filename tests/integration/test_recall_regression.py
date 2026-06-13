"""Deterministic recall regression: replay AUTH-04 and a singular-subject plan
through the executor against the live DB (no interpreter, no LLM).

Both plans are constructed inline as the contract — they reproduce the two
failure modes the seam-hardening batch fixed:

* Issue #45 (AUTH-04, "Books by Jacob ibn Habib"): a resolve_agent that fails
  to resolve, feeding an `agent_norm EQUALS $step_0` retrieve. Pre-fix, the
  unresolved-entity probe unioned a non-selective common given name ('Jacob')
  and flooded the result set (119/234 records). Post-fix, probes exceeding the
  selectivity ceiling are rejected as non-selective and only the honest small
  recovery survives.

* Issue #48 ("limited edition", singular): FTS5 has no stemmer, so the singular
  probe misses the plural 'Limited editions' heading. The relaxation ladder
  toggles trailing-'s' morphology and recovers the catalogued plural (103
  records) — recorded as a variant relaxation, never an index rebuild.

Fully deterministic: inline plans + real read-only DB, no network, no LLM.
"""

from pathlib import Path

import pytest

from scripts.chat.executor import execute_plan
from scripts.chat.plan_models import (
    ExecutionStep,
    InterpretationPlan,
    ResolveAgentParams,
    RetrieveParams,
    StepAction,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

pytestmark = pytest.mark.integration

DB_PATH = Path("data/index/bibliographic.db")


@pytest.fixture(autouse=True)
def _require_db():
    if not DB_PATH.exists():
        pytest.skip("real bibliographic.db not available")


def _all_relaxations(result) -> list[str]:
    """Flatten every relaxation note across all step results."""
    return [
        note
        for step in result.steps_completed
        for note in (getattr(step.data, "relaxations", []) or [])
    ]


def test_auth04_unresolved_agent_does_not_flood(_require_db):
    """Issue #45: the unresolved 'Jacob ibn Habib' probe must reject the
    non-selective 'Jacob' token and return an honest small recovery, not the
    old 119/234-record flood."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="AUTH-04 replay",
        confidence=0.9,
        directives=[],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(
                    name="Jacob ibn Habib",
                    variants=["אבן חביב, יעקב", "ibn Habib, Jacob"],
                ),
                label="Resolve Jacob ibn Habib",
                depends_on=[],
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.AGENT_NORM,
                            op=FilterOp.EQUALS,
                            value="$step_0",
                        )
                    ],
                    scope="full_collection",
                ),
                label="Books by Jacob ibn Habib",
                depends_on=[0],
            ),
        ],
    )

    result = execute_plan(plan, DB_PATH)

    # The resolve step must have genuinely failed (this is the precondition
    # for the unresolved-entity probe path).
    resolve = result.steps_completed[0]
    assert resolve.action == "resolve_agent"
    assert resolve.status == "empty"

    # Flood guard: was 119/234 pre-fix; the honest recovery is well under 30.
    assert result.total_record_count <= 30, (
        f"expected honest small recovery, got {result.total_record_count} "
        f"(pre-fix flood was 119/234)"
    )

    relaxations = _all_relaxations(result)
    assert relaxations, "recovery must be recorded as relaxation evidence"
    # The non-selective common given name must be explicitly rejected, OR (if
    # the data ever shifts) the result is at least an honest small recovery.
    assert any("rejected as non-selective" in n for n in relaxations), (
        f"expected a 'rejected as non-selective' note; got {relaxations!r}"
    )

    # The literal step reference must never reach an executed filter.
    for step in result.steps_completed:
        for applied in getattr(step.data, "filters_applied", []) or []:
            assert applied.get("value") != "$step_0", (
                "literal $step_0 was queried as a filter value!"
            )


def test_singular_subject_recovers_plural_heading(_require_db):
    """Issue #48: subject CONTAINS 'limited edition' (singular) must recover the
    plural 'Limited editions' heading (ground truth 103) via the stemming
    relaxation, recorded as a variant relaxation note."""
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="singular-subject replay",
        confidence=0.9,
        directives=[],
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.SUBJECT,
                            op=FilterOp.CONTAINS,
                            value="limited edition",
                        )
                    ],
                    scope="full_collection",
                ),
                label="subject limited edition (singular)",
                depends_on=[],
            ),
        ],
    )

    result = execute_plan(plan, DB_PATH)

    # Ground truth for the plural heading is 103 records.
    assert result.total_record_count >= 100, (
        f"expected the plural heading recovered (~103), got "
        f"{result.total_record_count}"
    )

    relaxations = _all_relaxations(result)
    assert relaxations, "recovery must be recorded as relaxation evidence"
    # A stemming/variant relaxation note must explain the singular->plural bridge.
    assert any(
        "variant" in n and "limited editions" in n for n in relaxations
    ), f"expected a stemming/variant relaxation note; got {relaxations!r}"
