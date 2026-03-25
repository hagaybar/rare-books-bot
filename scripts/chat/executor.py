"""Scholar Pipeline Stage 2: Deterministic Plan Executor.

Walks execution steps in dependency order, runs DB queries,
resolves aliases, computes aggregations, and collects grounding links.

Replaces: execute.py, analytical_router.py routing
Reuses: db_adapter.py, aggregation.py, cross_reference.py,
        agent_authority.py, publisher_authority.py, curation_engine.py
"""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.chat.plan_models import (
    AggregateParams,
    AggregationResult,
    ConnectionGraph,
    EnrichmentBundle,
    EnrichParams,
    ExecutionResult,
    ExecutionStep,
    FindConnectionsParams,
    GroundingData,
    InterpretationPlan,
    RecordSet,
    ResolveAgentParams,
    ResolvedEntity,
    ResolvePublisherParams,
    RetrieveParams,
    SampleParams,
    SessionContext,
    StepAction,
    StepOutputData,
    StepResult,
)

logger = logging.getLogger(__name__)

# Regex for $step_N references
_STEP_REF_RE = re.compile(r"^\$step_(\d+)$")


# =============================================================================
# Exceptions
# =============================================================================


class PlanValidationError(Exception):
    """Raised when the plan contains invalid structure."""

    pass


# =============================================================================
# Public API
# =============================================================================


def execute_plan(
    plan: InterpretationPlan,
    db_path: Path,
    session_context: Optional[SessionContext] = None,
    original_query: str = "",
) -> ExecutionResult:
    """Execute an InterpretationPlan and return verified results.

    Args:
        plan: The interpretation plan produced by Stage 1 (Interpreter).
        db_path: Path to the bibliographic SQLite database.
        session_context: Optional follow-up context from a previous turn.
        original_query: The user's original query text (echoed in result).

    Returns:
        ExecutionResult with step results, directives, and grounding data.
    """
    steps = plan.execution_steps

    # Resolve execution order (validates dependencies)
    if steps:
        execution_order = _resolve_execution_order(steps)
    else:
        execution_order = []

    # Execute steps in order
    step_results: Dict[int, StepResult] = {}
    for step_idx in execution_order:
        step = steps[step_idx]
        step_result = _execute_step(step, step_idx, db_path, step_results, session_context)
        step_results[step_idx] = step_result

    # Collect grounding data from all step results
    grounding = _collect_grounding(step_results, db_path)

    # Build ordered list of step results
    steps_completed = [step_results[i] for i in execution_order]

    return ExecutionResult(
        steps_completed=steps_completed,
        directives=list(plan.directives),
        grounding=grounding,
        original_query=original_query,
        session_context=session_context,
        truncated=False,
    )


# =============================================================================
# Dependency resolution
# =============================================================================


def _resolve_execution_order(steps: List[ExecutionStep]) -> List[int]:
    """Topological sort of steps by depends_on.

    Raises PlanValidationError on circular dependencies or
    out-of-range step references.

    Args:
        steps: List of execution steps with depends_on indices.

    Returns:
        List of step indices in execution order.
    """
    n = len(steps)

    # Validate all dependency references are in range
    for i, step in enumerate(steps):
        for dep in step.depends_on:
            if dep < 0 or dep >= n:
                raise PlanValidationError(
                    f"Step {i} depends on step {dep} which is out of range "
                    f"(plan has {n} steps)"
                )

    # Kahn's algorithm for topological sort
    in_degree = [0] * n
    adjacency: Dict[int, List[int]] = {i: [] for i in range(n)}

    for i, step in enumerate(steps):
        for dep in step.depends_on:
            adjacency[dep].append(i)
            in_degree[i] += 1

    queue: deque[int] = deque()
    for i in range(n):
        if in_degree[i] == 0:
            queue.append(i)

    order: List[int] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != n:
        raise PlanValidationError(
            "Plan contains circular dependencies: "
            f"resolved {len(order)} of {n} steps"
        )

    return order


# =============================================================================
# Step reference resolution
# =============================================================================


def _resolve_step_ref(
    ref: str,
    step_results: Dict[int, StepResult],
    context: str,
) -> Any:
    """Resolve a $step_N reference to concrete data.

    Args:
        ref: A string that may be "$step_N" or a literal value.
        step_results: Map of step index to completed StepResult.
        context: Resolution context -- determines what data to extract:
            "value" -- extract matched_values from ResolvedEntity
            "scope" -- extract mms_ids from RecordSet
            "agents" -- extract agent list from connection data
            "targets" -- extract targets for enrichment

    Returns:
        Resolved data. For "$step_N" references, returns the extracted
        data based on context. For non-reference strings, returns the
        string as-is.

    Raises:
        PlanValidationError: If the referenced step is not found in results.
    """
    match = _STEP_REF_RE.match(ref)
    if not match:
        return ref

    step_idx = int(match.group(1))
    if step_idx not in step_results:
        raise PlanValidationError(
            f"Reference $step_{step_idx} not found in completed step results"
        )

    result = step_results[step_idx]
    data = result.data

    if context == "value":
        # Extract matched values from resolve actions
        if isinstance(data, ResolvedEntity):
            return data.matched_values
        # Fallback: return mms_ids if it's a RecordSet
        if isinstance(data, RecordSet):
            return data.mms_ids
        return []

    if context == "scope":
        # Extract mms_ids for scoping
        if isinstance(data, RecordSet):
            return data.mms_ids
        # A ResolvedEntity doesn't have mms_ids -- return empty
        return []

    if context == "agents":
        # Extract agent names from resolved entities
        if isinstance(data, ResolvedEntity):
            return data.matched_values
        return []

    if context == "targets":
        # Extract targets for enrichment
        if isinstance(data, ResolvedEntity):
            return data.matched_values
        return []

    # Unknown context -- return raw data
    return data


def _resolve_scope(
    scope: str,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> Optional[List[str]]:
    """Resolve a scope reference to a list of mms_ids or None.

    Args:
        scope: One of "full_collection", "$step_N", or "$previous_results".
        step_results: Map of step index to completed StepResult.
        session_context: Optional session context for follow-up queries.

    Returns:
        None for "full_collection" (query entire DB),
        list of mms_ids for scoped queries.
    """
    if scope == "full_collection":
        return None

    if scope == "$previous_results":
        if session_context and session_context.previous_record_ids:
            return list(session_context.previous_record_ids)
        return []

    # Try to resolve as a step reference
    match = _STEP_REF_RE.match(scope)
    if match:
        return _resolve_step_ref(scope, step_results, context="scope")

    # Unknown scope -- treat as full collection
    logger.warning("Unknown scope '%s', treating as full_collection", scope)
    return None


# =============================================================================
# Step execution dispatch
# =============================================================================


def _execute_step(
    step: ExecutionStep,
    step_idx: int,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> StepResult:
    """Execute a single plan step and return a StepResult.

    Dispatches to the appropriate handler based on step.action.
    Catches handler exceptions and returns error status instead of crashing.
    """
    # Build handler dispatch table
    handlers: Dict[str, Callable] = {
        StepAction.RESOLVE_AGENT: _handle_resolve_agent,
        StepAction.RESOLVE_PUBLISHER: _handle_resolve_publisher,
        StepAction.RETRIEVE: _handle_retrieve,
        StepAction.AGGREGATE: _handle_aggregate,
        StepAction.FIND_CONNECTIONS: _handle_find_connections,
        StepAction.ENRICH: _handle_enrich,
        StepAction.SAMPLE: _handle_sample,
    }

    # Get action value (handle both enum and string)
    action_value = step.action.value if isinstance(step.action, StepAction) else step.action
    action_key = step.action if isinstance(step.action, StepAction) else None

    handler = handlers.get(action_key)
    if handler is None:
        # Unknown action -- return error result
        return StepResult(
            step_index=step_idx,
            action=action_value,
            label=step.label,
            status="error",
            data=RecordSet(mms_ids=[], total_count=0, filters_applied=[]),
            record_count=None,
            error_message=f"Unknown action: {action_value}",
        )

    try:
        data = handler(step.params, db_path, step_results, session_context)
        status = _determine_status(data)
        record_count = _count_records(data)
        return StepResult(
            step_index=step_idx,
            action=action_value,
            label=step.label,
            status=status,
            data=data,
            record_count=record_count,
        )
    except Exception as exc:
        logger.exception("Error executing step %d (%s): %s", step_idx, action_value, exc)
        return StepResult(
            step_index=step_idx,
            action=action_value,
            label=step.label,
            status="error",
            data=RecordSet(mms_ids=[], total_count=0, filters_applied=[]),
            record_count=None,
            error_message=str(exc),
        )


def _determine_status(data: StepOutputData) -> str:
    """Determine step status based on output data."""
    if isinstance(data, ResolvedEntity):
        return "ok" if data.matched_values else "empty"
    if isinstance(data, RecordSet):
        return "ok" if data.mms_ids else "empty"
    if isinstance(data, AggregationResult):
        return "ok" if data.facets else "empty"
    if isinstance(data, ConnectionGraph):
        return "ok" if data.connections else "empty"
    if isinstance(data, EnrichmentBundle):
        return "ok" if data.agents else "empty"
    return "ok"


def _count_records(data: StepOutputData) -> Optional[int]:
    """Extract a record count from step output, if applicable."""
    if isinstance(data, RecordSet):
        return data.total_count
    if isinstance(data, AggregationResult):
        return data.total_records
    return None


# =============================================================================
# Stub handlers (Task 4 fills these in with real DB queries)
# =============================================================================


def _handle_resolve_agent(
    params: ResolveAgentParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ResolvedEntity:
    """Resolve an agent name to canonical forms via authority lookup.

    STUB: Returns empty ResolvedEntity. Task 4 implements real lookup.
    """
    return ResolvedEntity(
        query_name=params.name,
        matched_values=[],
        match_method="stub",
        confidence=0.0,
    )


def _handle_resolve_publisher(
    params: ResolvePublisherParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ResolvedEntity:
    """Resolve a publisher name to canonical forms via variant lookup.

    STUB: Returns empty ResolvedEntity. Task 4 implements real lookup.
    """
    return ResolvedEntity(
        query_name=params.name,
        matched_values=[],
        match_method="stub",
        confidence=0.0,
    )


def _handle_retrieve(
    params: RetrieveParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> RecordSet:
    """Retrieve records matching filters, optionally scoped.

    STUB: Returns empty RecordSet. Task 4 implements real SQL query.
    """
    return RecordSet(
        mms_ids=[],
        total_count=0,
        filters_applied=[f.model_dump() for f in params.filters],
    )


def _handle_aggregate(
    params: AggregateParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> AggregationResult:
    """Compute faceted aggregation on a field.

    STUB: Returns empty AggregationResult. Task 4 implements real query.
    """
    return AggregationResult(
        field=params.field,
        facets=[],
        total_records=0,
    )


def _handle_find_connections(
    params: FindConnectionsParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ConnectionGraph:
    """Find co-occurrence connections between agents.

    STUB: Returns empty ConnectionGraph. Task 4 implements real query.
    """
    return ConnectionGraph(
        connections=[],
        isolated=list(params.agents),
    )


def _handle_enrich(
    params: EnrichParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> EnrichmentBundle:
    """Fetch biographical data and external links for resolved agents.

    STUB: Returns empty EnrichmentBundle. Task 4 implements real query.
    """
    return EnrichmentBundle(agents=[])


def _handle_sample(
    params: SampleParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> RecordSet:
    """Select a subset of records using the given strategy.

    STUB: Returns empty RecordSet. Task 4 implements real sampling.
    """
    return RecordSet(
        mms_ids=[],
        total_count=0,
        filters_applied=[{"strategy": params.strategy, "n": params.n}],
    )


# =============================================================================
# Grounding data collection (stub -- Task 4 fills this in)
# =============================================================================


def _collect_grounding(
    step_results: Dict[int, StepResult],
    db_path: Path,
) -> GroundingData:
    """Sweep all results and collect records, agents, links.

    STUB: Returns empty GroundingData. Task 4 implements real collection
    with record deduplication, agent enrichment, and link generation.
    """
    return GroundingData(
        records=[],
        agents=[],
        aggregations={},
        links=[],
    )
