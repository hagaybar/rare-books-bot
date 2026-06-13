"""Deterministic held-set ("active_subgroup") lifecycle policy.

Pure, LLM-free helpers that decide — from a completed turn's interpretation
plan and its CandidateSet — whether the held result set is redefined, and that
build the surfacing summary. The interpreter decides *scoping* (whether to
scope steps to "$previous_results"); these helpers decide the *lifecycle*
(replace vs. leave unchanged) from the resulting step shape.

Three-intent model (issue #60 part 2):
- New search      : full-collection retrieve with results -> held set replaced
- Refine-in-set   : retrieve scoped to "$previous_results" -> replaced (narrowed)
- Explore-in-set  : aggregate/connections-only over the held set -> unchanged
"""

from typing import Optional

from scripts.chat.models import ActiveSubgroup
from scripts.chat.plan_models import InterpretationPlan, StepAction
from scripts.schemas import CandidateSet

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


def build_subgroup_update(
    plan: InterpretationPlan,
    candidate_set: Optional[CandidateSet],
    query_text: str,
) -> Optional[ActiveSubgroup]:
    """Decide the held-set update for a completed turn.

    Returns an ActiveSubgroup to write/replace the held set, or None to leave
    the held set unchanged.

    A turn redefines the held set iff it has a retrieve step AND produced a
    non-empty CandidateSet (new search or refine-in-set). Aggregate/connections
    -only turns (explore-in-set) and empty/clarification turns return None.
    """
    if candidate_set is None or candidate_set.total_count == 0:
        return None

    has_retrieve = any(step.action == StepAction.RETRIEVE for step in plan.execution_steps)
    if not has_retrieve:
        return None

    return ActiveSubgroup(
        candidate_set=candidate_set,
        defining_query=query_text,
        filter_summary=summarize_filters(plan),
        record_ids=[c.record_id for c in candidate_set.candidates],
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
