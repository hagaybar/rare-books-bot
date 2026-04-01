"""Scholar Pipeline Stage 2: Deterministic Plan Executor.

Walks execution steps in dependency order, runs DB queries,
resolves aliases, computes aggregations, and collects grounding links.

Replaces: execute.py, analytical_router.py routing
Reuses: db_adapter.py, aggregation.py, cross_reference.py,
        agent_authority.py, publisher_authority.py, curation_engine.py
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.chat.plan_models import (
    AggregateParams,
    AggregationResult,
    AgentSummary,
    ConnectionGraph,
    EnrichmentBundle,
    EnrichParams,
    ExecutionResult,
    ExecutionStep,
    FindConnectionsParams,
    GroundingData,
    GroundingLink,
    InterpretationPlan,
    RecordSet,
    RecordSummary,
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

# Confidence thresholds
CONFIDENCE_HIGH = 0.95
CONFIDENCE_ALIAS_MATCH = 0.90
CONFIDENCE_MEDIUM = 0.80
CONFIDENCE_LOW = 0.70

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
    grounding, was_truncated = _collect_grounding(step_results, db_path)

    # Build ordered list of step results
    steps_completed = [step_results[i] for i in execution_order]

    return ExecutionResult(
        steps_completed=steps_completed,
        directives=list(plan.directives),
        grounding=grounding,
        original_query=original_query,
        session_context=session_context,
        truncated=was_truncated,
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
# DB helper
# =============================================================================


def _fix_wikipedia_url(url: str, wikidata_id: Optional[str] = None) -> str:
    """Fix broken Wikipedia URLs stored in authority_enrichment.

    The enrichment pipeline stores URLs like:
      https://en.wikipedia.org/wiki/Special:GoToLinkedPage/enwiki/Q467148
    These 404 on en.wikipedia.org. The correct redirect host is wikidata.org:
      https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/Q467148
    """
    if "Special:GoToLinkedPage" in url and "en.wikipedia.org" in url:
        return url.replace("https://en.wikipedia.org", "https://www.wikidata.org")
    return url


def _get_conn(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# Step handlers
# =============================================================================


def _handle_resolve_agent(
    params: ResolveAgentParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ResolvedEntity:
    """Resolve an agent name to canonical forms via authority lookup.

    Queries agent_aliases table for alias_form_lower matching the name
    or any provided variants. Falls back to token-based matching.

    Returns ResolvedEntity with matched canonical names.
    """
    conn = _get_conn(db_path)
    try:
        candidates_to_try = [params.name] + list(params.variants)
        matched_canonical: List[str] = []
        match_method = "none"

        for candidate in candidates_to_try:
            # Exact alias lookup (case-insensitive)
            row = conn.execute(
                """SELECT aa.canonical_name
                   FROM agent_authorities aa
                   JOIN agent_aliases al ON al.authority_id = aa.id
                   WHERE al.alias_form_lower = ?""",
                (candidate.lower(),),
            ).fetchone()
            if row:
                canonical = row["canonical_name"]
                if canonical not in matched_canonical:
                    matched_canonical.append(canonical)
                match_method = "alias_exact"

        # If no exact alias match, try direct canonical_name_lower match
        if not matched_canonical:
            for candidate in candidates_to_try:
                row = conn.execute(
                    """SELECT canonical_name FROM agent_authorities
                       WHERE canonical_name_lower = ?""",
                    (candidate.lower(),),
                ).fetchone()
                if row:
                    canonical = row["canonical_name"]
                    if canonical not in matched_canonical:
                        matched_canonical.append(canonical)
                    match_method = "canonical_exact"

        # Fall back to token-based matching on aliases
        if not matched_canonical:
            name_lower = params.name.lower()
            tokens = name_lower.split()
            if tokens:
                # Find aliases where all tokens appear
                rows = conn.execute(
                    "SELECT al.alias_form_lower, aa.canonical_name "
                    "FROM agent_aliases al "
                    "JOIN agent_authorities aa ON al.authority_id = aa.id"
                ).fetchall()
                for row in rows:
                    alias_lower = row["alias_form_lower"]
                    if all(tok in alias_lower for tok in tokens):
                        canonical = row["canonical_name"]
                        if canonical not in matched_canonical:
                            matched_canonical.append(canonical)
                        match_method = "alias_token"

        confidence = CONFIDENCE_HIGH if match_method == "alias_exact" else (
            CONFIDENCE_ALIAS_MATCH if match_method == "canonical_exact" else (
                CONFIDENCE_LOW if match_method == "alias_token" else 0.0
            )
        )

        return ResolvedEntity(
            query_name=params.name,
            matched_values=matched_canonical,
            match_method=match_method,
            confidence=confidence,
        )
    finally:
        conn.close()


def _handle_resolve_publisher(
    params: ResolvePublisherParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ResolvedEntity:
    """Resolve a publisher name to canonical forms via variant lookup.

    Queries publisher_variants table for variant_form_lower matching
    the name or any provided variants.

    Returns ResolvedEntity with matched canonical publisher names.
    """
    conn = _get_conn(db_path)
    try:
        candidates_to_try = [params.name] + list(params.variants)
        matched_canonical: List[str] = []
        match_method = "none"

        for candidate in candidates_to_try:
            row = conn.execute(
                """SELECT pa.id, pa.canonical_name_lower
                   FROM publisher_authorities pa
                   JOIN publisher_variants pv ON pv.authority_id = pa.id
                   WHERE pv.variant_form_lower = ?""",
                (candidate.lower(),),
            ).fetchone()
            if row:
                # Collect actual publisher_norm values from imprints that
                # belong to any variant of this authority
                norm_rows = conn.execute(
                    """SELECT DISTINCT i.publisher_norm
                       FROM imprints i
                       WHERE LOWER(i.publisher_norm) IN (
                           SELECT pv.variant_form_lower
                           FROM publisher_variants pv
                           WHERE pv.authority_id = ?
                       )""",
                    (row["id"],),
                ).fetchall()
                for nr in norm_rows:
                    v = nr["publisher_norm"]
                    if v and v not in matched_canonical:
                        matched_canonical.append(v)
                # Also include the canonical name (in case it appears directly)
                cn = row["canonical_name_lower"]
                if cn and cn not in matched_canonical:
                    matched_canonical.append(cn)
                match_method = "variant_exact"

        # Try direct canonical_name_lower match
        if not matched_canonical:
            for candidate in candidates_to_try:
                row = conn.execute(
                    """SELECT id, canonical_name_lower FROM publisher_authorities
                       WHERE canonical_name_lower = ?""",
                    (candidate.lower(),),
                ).fetchone()
                if row:
                    norm_rows = conn.execute(
                        """SELECT DISTINCT i.publisher_norm
                           FROM imprints i
                           WHERE LOWER(i.publisher_norm) IN (
                               SELECT pv.variant_form_lower
                               FROM publisher_variants pv
                               WHERE pv.authority_id = ?
                           )""",
                        (row["id"],),
                    ).fetchall()
                    for nr in norm_rows:
                        v = nr["publisher_norm"]
                        if v and v not in matched_canonical:
                            matched_canonical.append(v)
                    cn = row["canonical_name_lower"]
                    if cn and cn not in matched_canonical:
                        matched_canonical.append(cn)
                    match_method = "canonical_exact"

        # Token-based fallback on variants
        if not matched_canonical:
            name_lower = params.name.lower()
            tokens = name_lower.split()
            if tokens:
                rows = conn.execute(
                    "SELECT pv.variant_form_lower, pa.canonical_name "
                    "FROM publisher_variants pv "
                    "JOIN publisher_authorities pa ON pv.authority_id = pa.id"
                ).fetchall()
                for row in rows:
                    variant_lower = row["variant_form_lower"]
                    if all(tok in variant_lower for tok in tokens):
                        canonical = row["canonical_name"]
                        if canonical not in matched_canonical:
                            matched_canonical.append(canonical)
                        match_method = "variant_token"

        confidence = CONFIDENCE_HIGH if match_method == "variant_exact" else (
            CONFIDENCE_ALIAS_MATCH if match_method == "canonical_exact" else (
                CONFIDENCE_LOW if match_method == "variant_token" else 0.0
            )
        )

        return ResolvedEntity(
            query_name=params.name,
            matched_values=matched_canonical,
            match_method=match_method,
            confidence=confidence,
        )
    finally:
        conn.close()


def _handle_retrieve(
    params: RetrieveParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> RecordSet:
    """Retrieve records matching filters, optionally scoped.

    Converts RetrieveParams.filters to a QueryPlan, resolves $step_N
    references in filter values, calls db_adapter.build_full_query()
    and db_adapter.fetch_candidates(). If scope is set, adds WHERE
    r.mms_id IN (...) constraint.

    Returns RecordSet with matched mms_ids.
    """
    from scripts.query.db_adapter import build_where_clause, build_select_columns
    from scripts.query.db_adapter import build_join_clauses, fetch_candidates
    from scripts.schemas.query_plan import QueryPlan

    # Resolve $step_N references in filter values
    resolved_filters = []
    multi_value_map: Dict[int, List[str]] = {}  # filter_index -> all resolved values
    for f in params.filters:
        if isinstance(f.value, str):
            match = _STEP_REF_RE.match(f.value)
            if match:
                values = _resolve_step_ref(f.value, step_results, context="value")
                if isinstance(values, list) and values:
                    resolved_filters.append(
                        f.model_copy(update={"value": values[0]})
                    )
                    if len(values) > 1:
                        multi_value_map[len(resolved_filters) - 1] = values
                    continue
        resolved_filters.append(f)

    # Resolve scope
    scope_ids = _resolve_scope(params.scope, step_results, session_context)

    conn = _get_conn(db_path)
    try:
        # Build query from filters
        plan = QueryPlan(query_text="executor_retrieve", filters=resolved_filters)
        where_clause, sql_params, needed_joins = build_where_clause(plan, conn=conn)

        # Replace single-value EQUALS with IN(...) for multi-value resolved filters
        for filter_idx, all_values in multi_value_map.items():
            f = resolved_filters[filter_idx]
            # Find the param key used by build_where_clause for this filter
            param_key = f"filter_{filter_idx}_{f.field.value}"
            if param_key in sql_params:
                # Replace LOWER(col) = LOWER(:param) with LOWER(col) IN (LOWER(:mv_N), ...)
                old_cond = f"LOWER(:{param_key})"
                mv_keys = [f"mv_{filter_idx}_{i}" for i in range(len(all_values))]
                multi_placeholders = ", ".join(f"LOWER(:{k})" for k in mv_keys)
                where_clause = where_clause.replace(
                    f"= {old_cond}",
                    f"IN ({multi_placeholders})"
                )
                del sql_params[param_key]
                for k, v in zip(mv_keys, all_values):
                    sql_params[k] = v

        select_columns = build_select_columns(needed_joins)
        join_clauses = build_join_clauses(needed_joins)

        # Add scope constraint
        scope_clause = ""
        if scope_ids is not None:
            if not scope_ids:
                # Empty scope = no results
                return RecordSet(
                    mms_ids=[],
                    total_count=0,
                    filters_applied=[f.model_dump() for f in resolved_filters],
                )
            scope_keys = [f"scope_{i}" for i in range(len(scope_ids))]
            scope_placeholders = ",".join(f":{k}" for k in scope_keys)
            scope_clause = f" AND r.mms_id IN ({scope_placeholders})"
            for k, mms in zip(scope_keys, scope_ids):
                sql_params[k] = mms

        sql = (
            f"SELECT DISTINCT r.mms_id"
            f"\nFROM records r"
        )
        if join_clauses:
            sql += f"\n{join_clauses}"
        sql += f"\nWHERE {where_clause}{scope_clause}"
        sql += f"\nORDER BY r.mms_id"

        rows = conn.execute(sql, sql_params).fetchall()
        mms_ids = [row["mms_id"] for row in rows]

        return RecordSet(
            mms_ids=mms_ids,
            total_count=len(mms_ids),
            filters_applied=[f.model_dump() for f in resolved_filters],
        )
    finally:
        conn.close()


def _handle_aggregate(
    params: AggregateParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> AggregationResult:
    """Compute faceted aggregation on a field.

    Resolves scope to record IDs, runs SQL GROUP BY on the
    appropriate column. Returns AggregationResult with facets.
    """
    scope_ids = _resolve_scope(params.scope, step_results, session_context)

    if scope_ids is not None and not scope_ids:
        return AggregationResult(field=params.field, facets=[], total_records=0)

    conn = _get_conn(db_path)
    try:
        # Build scope constraint
        if scope_ids is not None:
            placeholders = ",".join("?" for _ in scope_ids)
            scope_where = f"r.mms_id IN ({placeholders})"
            scope_params = list(scope_ids)
        else:
            scope_where = "1=1"
            scope_params = []

        # Field-specific aggregation SQL
        field_map = {
            "date_decade": (
                "SELECT (i.date_start / 10 * 10) || 's' AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} AND i.date_start IS NOT NULL "
                "GROUP BY i.date_start / 10 * 10 "
                "ORDER BY i.date_start / 10 * 10 ASC LIMIT ?"
            ),
            "place": (
                "SELECT i.place_norm AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} AND i.place_norm IS NOT NULL AND i.place_norm != '' "
                "GROUP BY i.place_norm ORDER BY count DESC LIMIT ?"
            ),
            "publisher": (
                "SELECT i.publisher_norm AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} AND i.publisher_norm IS NOT NULL AND i.publisher_norm != '' "
                "GROUP BY i.publisher_norm ORDER BY count DESC LIMIT ?"
            ),
            "language": (
                "SELECT l.code AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN languages l ON r.id = l.record_id "
                f"WHERE {scope_where} "
                "GROUP BY l.code ORDER BY count DESC LIMIT ?"
            ),
            "subject": (
                "SELECT s.value AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN subjects s ON r.id = s.record_id "
                f"WHERE {scope_where} "
                "GROUP BY s.value ORDER BY count DESC LIMIT ?"
            ),
            "agent": (
                "SELECT a.agent_norm AS value, "
                "COUNT(DISTINCT r.mms_id) AS count "
                "FROM records r JOIN agents a ON r.id = a.record_id "
                f"WHERE {scope_where} "
                "GROUP BY a.agent_norm ORDER BY count DESC LIMIT ?"
            ),
        }

        # Normalize field name aliases (LLM may use variant names)
        field_aliases = {
            "imprint_place": "place",
            "city": "place",
            "location": "place",
            "country": "place",
            "date": "date_decade",
            "year": "date_decade",
            "decade": "date_decade",
            "century": "date_decade",
            "agent_norm": "agent",
            "author": "agent",
            "printer": "agent",
        }
        normalized_field = field_aliases.get(params.field, params.field)

        sql_template = field_map.get(normalized_field)
        if not sql_template:
            return AggregationResult(field=params.field, facets=[], total_records=0)

        rows = conn.execute(sql_template, scope_params + [params.limit]).fetchall()
        facets = [{"value": row["value"], "count": row["count"]} for row in rows]

        # Count total records in scope
        total_sql = f"SELECT COUNT(DISTINCT r.mms_id) AS cnt FROM records r WHERE {scope_where}"
        total_row = conn.execute(total_sql, scope_params).fetchone()
        total_records = total_row["cnt"] if total_row else 0

        return AggregationResult(
            field=params.field,
            facets=facets,
            total_records=total_records,
        )
    finally:
        conn.close()


def _handle_find_connections(
    params: FindConnectionsParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> ConnectionGraph:
    """Find co-occurrence connections between agents.

    Resolves agent names (potentially from $step_N references),
    then calls cross_reference.find_connections() to discover
    teacher/student, co-publication, and same-place-period
    relationships. Returns ConnectionGraph.
    """
    from scripts.chat.cross_reference import find_connections

    # Resolve agent references -- each may be a $step_N or a literal
    agent_norms: List[str] = []
    for agent_ref in params.agents:
        match = _STEP_REF_RE.match(agent_ref)
        if match:
            values = _resolve_step_ref(agent_ref, step_results, context="agents")
            if isinstance(values, list):
                agent_norms.extend(values)
            else:
                agent_norms.append(str(values))
        else:
            agent_norms.append(agent_ref)

    if not agent_norms:
        return ConnectionGraph(connections=[], isolated=[])

    connections = find_connections(db_path, agent_norms)

    # Determine which agents are isolated (not in any connection)
    connected = set()
    conn_dicts = []
    for c in connections:
        connected.add(c.agent_a)
        connected.add(c.agent_b)
        conn_dicts.append({
            "agent_a": c.agent_a,
            "agent_b": c.agent_b,
            "relationship_type": c.relationship_type,
            "evidence": c.evidence,
            "confidence": c.confidence,
        })

    isolated = [a for a in agent_norms if a not in connected]

    return ConnectionGraph(
        connections=conn_dicts,
        isolated=isolated,
    )


def _handle_enrich(
    params: EnrichParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> EnrichmentBundle:
    """Fetch biographical data and external links for resolved agents.

    Resolves agent names from $step_N, joins through agents.authority_uri
    to the authority_enrichment table. Builds AgentSummary objects with
    biographical info and links.

    Returns EnrichmentBundle.
    """
    # Resolve targets (typically a $step_N reference to a resolve step)
    target_ref = params.targets
    match = _STEP_REF_RE.match(target_ref)
    if match:
        targets = _resolve_step_ref(target_ref, step_results, context="targets")
        if not isinstance(targets, list):
            targets = [str(targets)]
    else:
        targets = [target_ref]

    if not targets:
        return EnrichmentBundle(agents=[])

    conn = _get_conn(db_path)
    try:
        agent_summaries: List[AgentSummary] = []

        for agent_name in targets:
            # Find authority_uri via agents table
            auth_row = conn.execute(
                """SELECT DISTINCT a.authority_uri
                   FROM agents a
                   WHERE a.agent_norm = ?
                   AND a.authority_uri IS NOT NULL
                   LIMIT 1""",
                (agent_name,),
            ).fetchone()

            if not auth_row or not auth_row["authority_uri"]:
                # Still create a minimal summary
                agent_summaries.append(AgentSummary(
                    canonical_name=agent_name,
                    variants=[],
                ))
                continue

            authority_uri = auth_row["authority_uri"]

            # Fetch enrichment data
            enrich_row = conn.execute(
                """SELECT ae.*, aa.canonical_name, aa.date_start, aa.date_end
                   FROM authority_enrichment ae
                   LEFT JOIN agent_authorities aa
                       ON aa.authority_uri = ae.authority_uri
                   WHERE ae.authority_uri = ?""",
                (authority_uri,),
            ).fetchone()

            if not enrich_row:
                agent_summaries.append(AgentSummary(
                    canonical_name=agent_name,
                    variants=[],
                ))
                continue

            # Parse person_info JSON
            person_info = {}
            if enrich_row["person_info"]:
                try:
                    person_info = json.loads(enrich_row["person_info"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Collect variant forms
            variants = []
            if enrich_row["canonical_name"]:
                alias_rows = conn.execute(
                    """SELECT alias_form FROM agent_aliases
                       WHERE authority_id = (
                           SELECT id FROM agent_authorities
                           WHERE authority_uri = ?
                       )""",
                    (authority_uri,),
                ).fetchall()
                variants = [r["alias_form"] for r in alias_rows]

            # Count records
            rec_count_row = conn.execute(
                """SELECT COUNT(DISTINCT record_id) AS cnt
                   FROM agents WHERE authority_uri = ?""",
                (authority_uri,),
            ).fetchone()
            record_count = rec_count_row["cnt"] if rec_count_row else 0

            # Build links
            links: List[GroundingLink] = []
            if enrich_row["wikipedia_url"]:
                links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=agent_name,
                    label=f"Wikipedia: {enrich_row['label'] or agent_name}",
                    url=_fix_wikipedia_url(enrich_row["wikipedia_url"], enrich_row["wikidata_id"] if "wikidata_id" in enrich_row.keys() else None),
                    source="wikipedia",
                ))
            if enrich_row["wikidata_id"]:
                links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=agent_name,
                    label=f"Wikidata: {enrich_row['wikidata_id']}",
                    url=f"https://www.wikidata.org/wiki/{enrich_row['wikidata_id']}",
                    source="wikidata",
                ))
            if enrich_row["viaf_id"]:
                links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=agent_name,
                    label=f"VIAF: {enrich_row['viaf_id']}",
                    url=f"https://viaf.org/en/viaf/{enrich_row['viaf_id']}",
                    source="viaf",
                ))
            if enrich_row["nli_id"]:
                links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=agent_name,
                    label=f"NLI: {enrich_row['nli_id']}",
                    url=f"https://www.nli.org.il/en/authorities/{enrich_row['nli_id']}",
                    source="nli",
                ))

            canonical_name = enrich_row["canonical_name"] or agent_name

            agent_summary = AgentSummary(
                canonical_name=canonical_name,
                variants=variants,
                birth_year=person_info.get("birth_year"),
                death_year=person_info.get("death_year"),
                occupations=person_info.get("occupations", []),
                description=enrich_row["description"],
                record_count=record_count,
                links=links,
            )

            # Enrich with Wikipedia data if available
            try:
                wikidata_id = enrich_row["wikidata_id"] if "wikidata_id" in enrich_row.keys() else None
                wiki_row = conn.execute(
                    """SELECT summary_extract FROM wikipedia_cache
                       WHERE wikidata_id = ? AND language = 'en'
                       AND summary_extract IS NOT NULL""",
                    (wikidata_id,),
                ).fetchone() if wikidata_id else None
            except Exception:
                wiki_row = None  # Table may not exist

            if wiki_row and wiki_row["summary_extract"]:
                wp_text = wiki_row["summary_extract"]
                if len(wp_text) > len(agent_summary.description or ""):
                    agent_summary.description = wp_text[:500]
                agent_summary.wikipedia_context = wp_text

            agent_summaries.append(agent_summary)

        return EnrichmentBundle(agents=agent_summaries)
    finally:
        conn.close()


def _handle_sample(
    params: SampleParams,
    db_path: Path,
    step_results: Dict[int, StepResult],
    session_context: Optional[SessionContext],
) -> RecordSet:
    """Select a subset of records using the given strategy.

    Strategies:
    - "earliest": ORDER BY date_start ASC LIMIT n
    - "notable": Use curation_engine.score_for_curation() if available,
      else fall back to earliest.
    - "diverse": Sample across decades/places for variety.

    Returns RecordSet with the sampled mms_ids.
    """
    scope_ids = _resolve_scope(params.scope, step_results, session_context)

    if scope_ids is not None and not scope_ids:
        return RecordSet(
            mms_ids=[],
            total_count=0,
            filters_applied=[{"strategy": params.strategy, "n": params.n}],
        )

    conn = _get_conn(db_path)
    try:
        if scope_ids is not None:
            placeholders = ",".join("?" for _ in scope_ids)
            scope_where = f"r.mms_id IN ({placeholders})"
            scope_params: list = list(scope_ids)
        else:
            scope_where = "1=1"
            scope_params = []

        if params.strategy == "earliest":
            sql = (
                f"SELECT DISTINCT r.mms_id, MIN(i.date_start) AS d "
                f"FROM records r "
                f"LEFT JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} "
                f"GROUP BY r.mms_id "
                f"ORDER BY d ASC NULLS LAST "
                f"LIMIT ?"
            )
            rows = conn.execute(sql, scope_params + [params.n]).fetchall()
            mms_ids = [row["mms_id"] for row in rows]

        elif params.strategy == "diverse":
            # Sample across decades by picking one from each decade bucket
            sql = (
                f"SELECT r.mms_id, (i.date_start / 10 * 10) AS decade "
                f"FROM records r "
                f"LEFT JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} AND i.date_start IS NOT NULL "
                f"GROUP BY r.mms_id "
                f"ORDER BY decade ASC"
            )
            rows = conn.execute(sql, scope_params).fetchall()
            # Pick one per decade, cycling until we reach n
            decades: Dict[int, List[str]] = {}
            for row in rows:
                d = row["decade"] if row["decade"] is not None else 0
                decades.setdefault(d, []).append(row["mms_id"])

            mms_ids: List[str] = []
            seen = set()
            round_num = 0
            while len(mms_ids) < params.n:
                added = False
                for decade in sorted(decades.keys()):
                    bucket = decades[decade]
                    if round_num < len(bucket):
                        mms = bucket[round_num]
                        if mms not in seen:
                            mms_ids.append(mms)
                            seen.add(mms)
                            added = True
                            if len(mms_ids) >= params.n:
                                break
                if not added:
                    break
                round_num += 1

        else:
            # "notable" or unknown strategy -- fall back to earliest
            sql = (
                f"SELECT DISTINCT r.mms_id, MIN(i.date_start) AS d "
                f"FROM records r "
                f"LEFT JOIN imprints i ON r.id = i.record_id "
                f"WHERE {scope_where} "
                f"GROUP BY r.mms_id "
                f"ORDER BY d ASC NULLS LAST "
                f"LIMIT ?"
            )
            rows = conn.execute(sql, scope_params + [params.n]).fetchall()
            mms_ids = [row["mms_id"] for row in rows]

        total_sql = f"SELECT COUNT(DISTINCT r.mms_id) AS cnt FROM records r WHERE {scope_where}"
        total_row = conn.execute(total_sql, scope_params).fetchone()
        total = total_row["cnt"] if total_row else 0

        return RecordSet(
            mms_ids=mms_ids,
            total_count=total,
            filters_applied=[{"strategy": params.strategy, "n": params.n}],
        )
    finally:
        conn.close()


# =============================================================================
# Grounding data collection
# =============================================================================


_MAX_GROUNDING_RECORDS = 30


def _collect_grounding(
    step_results: Dict[int, StepResult],
    db_path: Path,
) -> tuple[GroundingData, bool]:
    """Sweep all step results and collect records, agents, links.

    - Deduplicates records across retrieve steps (merges source_steps).
    - Builds RecordSummary for each record (join records + imprints + titles).
    - Builds AgentSummary for enriched agents.
    - Collects links: Primo for records, Wikipedia/Wikidata/NLI/VIAF for agents.
    - Truncates to 30 records if needed.

    Returns (GroundingData, truncated: bool).
    """
    from scripts.utils.primo import generate_primo_url

    # 1. Collect all mms_ids across retrieve/sample steps, tracking source steps
    mms_to_steps: Dict[str, List[int]] = {}
    for step_idx, sr in step_results.items():
        if isinstance(sr.data, RecordSet) and sr.data.mms_ids:
            for mms_id in sr.data.mms_ids:
                mms_to_steps.setdefault(mms_id, [])
                if step_idx not in mms_to_steps[mms_id]:
                    mms_to_steps[mms_id].append(step_idx)

    # 2. Collect aggregation results
    aggregations: Dict[str, list] = {}
    for step_idx, sr in step_results.items():
        if isinstance(sr.data, AggregationResult) and sr.data.facets:
            aggregations[sr.data.field] = sr.data.facets

    # 3. Collect agent summaries from enrich steps
    agent_summaries: List[AgentSummary] = []
    for step_idx, sr in step_results.items():
        if isinstance(sr.data, EnrichmentBundle):
            for agent in sr.data.agents:
                # Deduplicate by canonical_name
                existing = [a for a in agent_summaries if a.canonical_name == agent.canonical_name]
                if not existing:
                    agent_summaries.append(agent)

    if not mms_to_steps:
        return GroundingData(
            records=[],
            agents=agent_summaries,
            aggregations=aggregations,
            links=[lnk for a in agent_summaries for lnk in a.links],
        ), False

    # 4. Build RecordSummary for each mms_id from DB
    all_mms = list(mms_to_steps.keys())

    # Truncate if needed
    truncated = len(all_mms) > _MAX_GROUNDING_RECORDS
    if truncated:
        all_mms = all_mms[:_MAX_GROUNDING_RECORDS]

    conn = _get_conn(db_path)
    try:
        records: List[RecordSummary] = []
        links: List[GroundingLink] = []

        for mms_id in all_mms:
            # Get title
            title_row = conn.execute(
                """SELECT t.value FROM titles t
                   JOIN records r ON t.record_id = r.id
                   WHERE r.mms_id = ? AND t.title_type = 'main'
                   LIMIT 1""",
                (mms_id,),
            ).fetchone()
            title = title_row["value"] if title_row else ""

            # Get imprint info
            imp_row = conn.execute(
                """SELECT i.date_start, i.date_end, i.date_label,
                          i.place_norm, i.place_display,
                          i.publisher_norm, i.publisher_display
                   FROM imprints i
                   JOIN records r ON i.record_id = r.id
                   WHERE r.mms_id = ?
                   ORDER BY i.occurrence ASC LIMIT 1""",
                (mms_id,),
            ).fetchone()

            date_display = None
            place = None
            publisher = None
            if imp_row:
                date_display = imp_row["date_label"] or (
                    str(imp_row["date_start"]) if imp_row["date_start"] else None
                )
                place = imp_row["place_display"] or imp_row["place_norm"]
                publisher = imp_row["publisher_display"] or imp_row["publisher_norm"]

            # Get language
            lang_row = conn.execute(
                """SELECT l.code FROM languages l
                   JOIN records r ON l.record_id = r.id
                   WHERE r.mms_id = ? LIMIT 1""",
                (mms_id,),
            ).fetchone()
            language = lang_row["code"] if lang_row else None

            # Get agents
            agent_rows = conn.execute(
                """SELECT DISTINCT a.agent_norm FROM agents a
                   JOIN records r ON a.record_id = r.id
                   WHERE r.mms_id = ?""",
                (mms_id,),
            ).fetchall()
            agents = [r["agent_norm"] for r in agent_rows if r["agent_norm"]]

            # Get subjects
            subj_rows = conn.execute(
                """SELECT DISTINCT s.value FROM subjects s
                   JOIN records r ON s.record_id = r.id
                   WHERE r.mms_id = ?""",
                (mms_id,),
            ).fetchall()
            subjects = [r["value"] for r in subj_rows if r["value"]]

            # Generate Primo URL
            primo_url = generate_primo_url(mms_id)

            records.append(RecordSummary(
                mms_id=mms_id,
                title=title,
                date_display=date_display,
                place=place,
                publisher=publisher,
                language=language,
                agents=agents,
                subjects=subjects,
                primo_url=primo_url,
                source_steps=mms_to_steps.get(mms_id, []),
            ))

            # Add Primo link
            links.append(GroundingLink(
                entity_type="record",
                entity_id=mms_id,
                label=f"Primo: {title[:50]}" if title else f"Primo: {mms_id}",
                url=primo_url,
                source="primo",
            ))

        # 5. Collect agent external links from authority_enrichment
        # for agents found in records, even without an explicit enrich step.
        enriched_names = {a.canonical_name for a in agent_summaries}

        # Gather unique authority_uris from agents on the grounded records
        placeholders = ",".join("?" for _ in all_mms)
        auth_rows = conn.execute(
            f"""SELECT DISTINCT a.authority_uri, a.agent_norm
                FROM agents a
                JOIN records r ON a.record_id = r.id
                WHERE r.mms_id IN ({placeholders})
                  AND a.authority_uri IS NOT NULL""",
            all_mms,
        ).fetchall()

        for arow in auth_rows:
            agent_name = arow["agent_norm"]
            authority_uri = arow["authority_uri"]

            # Skip agents already covered by an enrich step
            if agent_name and agent_name in enriched_names:
                continue

            enrich_row = conn.execute(
                """SELECT ae.*, aa.canonical_name AS aa_name,
                          aa.date_start, aa.date_end
                   FROM authority_enrichment ae
                   LEFT JOIN agent_authorities aa
                       ON aa.authority_uri = ae.authority_uri
                   WHERE ae.authority_uri = ?""",
                (authority_uri,),
            ).fetchone()
            if not enrich_row:
                continue

            # Build agent links
            agent_links: List[GroundingLink] = []
            display_name = enrich_row["aa_name"] or agent_name or authority_uri
            if enrich_row["wikipedia_url"]:
                agent_links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=display_name,
                    label=f"Wikipedia: {enrich_row['label'] or display_name}",
                    url=_fix_wikipedia_url(enrich_row["wikipedia_url"], enrich_row["wikidata_id"] if "wikidata_id" in enrich_row.keys() else None),
                    source="wikipedia",
                ))
            if enrich_row["wikidata_id"]:
                agent_links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=display_name,
                    label=f"Wikidata: {enrich_row['wikidata_id']}",
                    url=f"https://www.wikidata.org/wiki/{enrich_row['wikidata_id']}",
                    source="wikidata",
                ))
            if enrich_row["viaf_id"]:
                agent_links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=display_name,
                    label=f"VIAF: {enrich_row['viaf_id']}",
                    url=f"https://viaf.org/en/viaf/{enrich_row['viaf_id']}",
                    source="viaf",
                ))
            if enrich_row["nli_id"]:
                agent_links.append(GroundingLink(
                    entity_type="agent",
                    entity_id=display_name,
                    label=f"NLI: {enrich_row['nli_id']}",
                    url=f"https://www.nli.org.il/en/authorities/{enrich_row['nli_id']}",
                    source="nli",
                ))

            if agent_links:
                # Parse person_info for bio data
                person_info = {}
                if enrich_row["person_info"]:
                    try:
                        person_info = json.loads(enrich_row["person_info"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                agent_summaries.append(AgentSummary(
                    canonical_name=display_name,
                    variants=[],
                    birth_year=person_info.get("birth_year"),
                    death_year=person_info.get("death_year"),
                    occupations=person_info.get("occupations", []),
                    description=enrich_row["description"],
                    links=agent_links,
                ))
                enriched_names.add(display_name)
                if agent_name:
                    enriched_names.add(agent_name)

        # Add agent links from all agent summaries
        for agent in agent_summaries:
            links.extend(agent.links)

        return GroundingData(
            records=records,
            agents=agent_summaries,
            aggregations=aggregations,
            links=links,
        ), truncated
    finally:
        conn.close()
