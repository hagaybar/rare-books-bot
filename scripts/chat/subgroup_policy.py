"""Deterministic held-set ("active_subgroup") lifecycle policy.

Pure, LLM-free helpers that decide — from a completed turn's interpretation
plan and its ExecutionResult — whether the held result set is redefined, and
that build the surfacing summary. The interpreter decides *scoping* (whether to
scope steps to "$previous_results"); these helpers decide the *lifecycle*
(replace vs. leave unchanged) from the resulting step shape.

Three-intent model (issue #60 part 2):
- New search      : full-collection retrieve with results -> held set replaced
- Refine-in-set   : retrieve scoped to "$previous_results" -> replaced (narrowed)
- Explore-in-set  : aggregate/connections-only over the held set -> unchanged
"""

from typing import Optional

from scripts.chat.models import ActiveSubgroup
from scripts.chat.plan_models import (
    ExecutionResult,
    InterpretationPlan,
    RecordSet,
    StepAction,
)

# The scope keyword that names the held set (already wired in executor +
# interpreter). Reused here rather than introducing a new "active_subgroup"
# keyword (see the plan's "Key decisions").
HELD_SET_SCOPE = "$previous_results"


def was_scoped_to_held_set(plan: InterpretationPlan) -> bool:
    """True if any execution step scoped to the held set ($previous_results).

    Drives the conversation phase: a scoped turn is corpus exploration.
    """
    for step in plan.execution_steps:
        if getattr(step.params, "scope", None) == HELD_SET_SCOPE:
            return True
    return False


def summarize_filters(plan: InterpretationPlan) -> str:
    """Short human description of a plan's retrieve filters for the chip.

    Example: "place contains Venice; date 1500-1599". Empty string when the
    plan has no retrieve filters.
    """
    parts: list[str] = []
    for step in plan.execution_steps:
        if step.action != StepAction.RETRIEVE:
            continue
        for f in getattr(step.params, "filters", []) or []:
            field = getattr(getattr(f, "field", None), "value", None) or str(getattr(f, "field", ""))
            op = getattr(getattr(f, "op", None), "value", None) or str(getattr(f, "op", ""))
            if getattr(f, "start", None) is not None:
                parts.append(f"{field} {f.start}-{f.end}")
            else:
                value = getattr(f, "value", None)
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                parts.append(f"{field} {op.lower()} {value}".strip())
    return "; ".join(parts)


def held_record_ids(execution_result: ExecutionResult) -> list[str]:
    """The full held-set ids: order-preserving deduped union of every retrieve
    step's RecordSet.mms_ids. Its length equals total_record_count — this is the
    UNtruncated set, unlike the display grounding (capped at 30)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for step in execution_result.steps_completed:
        data = getattr(step, "data", None)
        if isinstance(data, RecordSet):
            for mms in data.mms_ids:
                if mms not in seen:
                    seen.add(mms)
                    ordered.append(mms)
    return ordered


def build_subgroup_update(
    plan: InterpretationPlan,
    execution_result: ExecutionResult,
    query_text: str,
) -> Optional[ActiveSubgroup]:
    """Decide the held-set update for a completed turn.

    Returns an ActiveSubgroup to replace the held set, or None to leave it
    unchanged. A turn redefines the held set iff it produced a non-empty retrieve
    result (new search or refine-in-set). The held set's record_ids are the FULL
    match set (held_record_ids), NOT the truncated display set — fixes the
    74-vs-30 defect. Aggregate-only (explore) and empty/clarification turns return
    None.
    """
    has_retrieve = any(
        step.action == StepAction.RETRIEVE for step in plan.execution_steps
    )
    if not has_retrieve:
        return None

    record_ids = held_record_ids(execution_result)
    if not record_ids:
        return None

    return ActiveSubgroup(
        candidate_set=None,
        defining_query=query_text,
        filter_summary=summarize_filters(plan),
        record_ids=record_ids,
    )


def subgroup_summary(subgroup: Optional[ActiveSubgroup]) -> Optional[dict]:
    """Compact summary for the response metadata / frontend chip.

    Returns ``{"defining_query": str, "count": int}`` or None.
    """
    if subgroup is None:
        return None
    return {
        "defining_query": subgroup.defining_query,
        "count": len(subgroup.record_ids),
    }
