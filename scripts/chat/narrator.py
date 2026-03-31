"""Scholar Pipeline Stage 3: Scholarly Narrator.

Receives verified ExecutionResult and composes a scholarly response.
Uses LLM with a rich persona prompt. Cannot access the DB directly --
can only reference data present in the ExecutionResult.

Provides two modes:
- ``narrate()``: synchronous, returns full ScholarResponse with structured output
- ``narrate_streaming()``: async, streams narrative text via callback, then returns full response

Replaces: formatter.py, narrative_agent.py, thematic_context.py
"""
import logging
import os
from typing import Awaitable, Callable, Optional

from openai import OpenAI

from scripts.chat.plan_models import (
    ExecutionResult,
    GroundingData,
    RecordSummary,
    AgentSummary,
    GroundingLink,
    ScholarResponse,
    ScholarlyDirective,
    StepResult,
)
from scripts.utils.llm_logger import log_llm_call

logger = logging.getLogger(__name__)


# =============================================================================
# Narrator system prompt with the 6 evidence rules from the spec
# =============================================================================

NARRATOR_SYSTEM_PROMPT = """\
You are a scholar of Jewish book history and early modern print culture,
serving as the voice of a rare books collection discovery system.

You have deep knowledge of Hebrew printing, intellectual networks,
and bibliographic traditions. You speak with authority and nuance.

EVIDENCE RULES (non-negotiable):
1. When citing holdings, use ONLY records from the provided data.
   State exact counts -- never approximate when exact data is available.
2. You MAY use general scholarly knowledge for context, interpretation,
   and historical framing.
3. When stating something from general knowledge, never imply it comes
   from the collection.
4. If the collection holds nothing relevant, say so clearly. You may still
   provide scholarly context and suggest related holdings that WERE found.
5. Every record you mention by specifics (title, date, printer) must appear
   in the provided grounding data.
6. When links are available (Primo, Wikipedia, Wikidata), weave them
   naturally into the response as references.
7. When Wikipedia context is provided for an agent, use it to inform your
   narrative with richer biographical detail. Do not quote it verbatim.
   Wikipedia context is general scholarly knowledge, not collection evidence.

RESPONSE FORMAT:
- Use markdown for structure (headers, bold, lists, links).

IMPORTANT: Do NOT include suggested follow-up questions or confidence scores
in your narrative text. These are handled as separate structured fields.
Your narrative should end with the scholarly content only -- never add
sections like "Suggested Followups", "Confidence", or similar headings.
The narrative field must contain ONLY the scholarly response.
"""


# =============================================================================
# LLM response model for structured output
# =============================================================================

from pydantic import BaseModel, Field, ConfigDict


class NarratorResponseLLM(BaseModel):
    """LLM-compatible response model for the narrator.

    Used with OpenAI's Responses API for structured output parsing.
    """
    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(
        ...,
        description="Scholarly narrative response in markdown format",
    )
    suggested_followups: list[str] = Field(
        default_factory=list,
        description="2-4 suggested follow-up questions",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Self-assessed confidence in response quality (0.0-1.0)",
    )


# =============================================================================
# Public API
# =============================================================================


async def narrate(
    query: str,
    execution_result: ExecutionResult,
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> ScholarResponse:
    """Compose a scholarly response from verified execution results.

    This is the main entry point for Stage 3 of the scholar pipeline.
    It calls the LLM with a rich persona prompt and verified data,
    then passes through grounding from the executor.

    On LLM failure, falls back to a structured summary built from
    the execution result data (no LLM needed).

    Args:
        query: The original user query.
        execution_result: Verified output from the executor (Stage 2).
        model: OpenAI model to use (default: gpt-4o).
        api_key: OpenAI API key (or use OPENAI_API_KEY env var).
        token_saving: If True, use lean prompt builder to reduce token
            usage. If False, use the full prompt builder.

    Returns:
        ScholarResponse with narrative, followups, and grounding.
    """
    try:
        response = await _call_llm(
            query, execution_result, model, api_key,
            token_saving=token_saving,
        )
        # Always pass through grounding from executor (narrator doesn't modify it)
        response.grounding = execution_result.grounding
        return response
    except Exception:
        logger.exception("Narrator LLM call failed; using fallback")
        return _fallback_response(query, execution_result)


async def narrate_streaming(
    query: str,
    execution_result: ExecutionResult,
    chunk_callback: Callable[[str], Awaitable[None]],
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> ScholarResponse:
    """Stream a scholarly narrative, forwarding text chunks via callback.

    Uses the OpenAI Responses API in streaming mode (without structured
    output) so that narrative text can be forwarded to the client
    incrementally.  After streaming completes, assembles and returns
    the full ScholarResponse.

    On LLM failure, falls back to the deterministic summary (same as
    ``narrate()``), sending it as a single chunk.

    Args:
        query: The original user query.
        execution_result: Verified output from the executor (Stage 2).
        chunk_callback: Async callable invoked with each text chunk.
        model: OpenAI model to use.
        api_key: OpenAI API key (or use OPENAI_API_KEY env var).
        token_saving: If True, use lean prompt builder to reduce token
            usage. If False, use the full prompt builder.

    Returns:
        ScholarResponse with the full narrative, grounding from executor,
        and default followups/confidence.
    """
    try:
        narrative = await _stream_llm(
            query, execution_result, chunk_callback, model, api_key,
            token_saving=token_saving,
        )
        response = ScholarResponse(
            narrative=narrative,
            suggested_followups=[],
            grounding=execution_result.grounding,
            confidence=0.85,
            metadata={"model": model, "streamed": True},
        )
        return response
    except Exception:
        logger.exception("Narrator streaming LLM call failed; using fallback")
        fallback = _fallback_response(query, execution_result)
        # Send the fallback narrative as a single chunk
        await chunk_callback(fallback.narrative)
        return fallback


# =============================================================================
# LLM call
# =============================================================================


async def _call_llm(
    query: str,
    execution_result: ExecutionResult,
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> ScholarResponse:
    """Call OpenAI with the narrator persona and verified data.

    Uses the Responses API with Pydantic schema enforcement,
    following the same pattern as intent_agent.py.

    Args:
        query: The original user query.
        execution_result: Verified execution result.
        model: OpenAI model name.
        api_key: OpenAI API key override.
        token_saving: If True, use lean prompt builder.

    Returns:
        ScholarResponse parsed from LLM output.

    Raises:
        Exception: On any API or parsing failure (caught by narrate()).
    """
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise ValueError("OPENAI_API_KEY not set and no api_key provided")

    client = OpenAI(api_key=resolved_key)
    if token_saving:
        user_prompt = build_lean_narrator_prompt(query, execution_result)
    else:
        user_prompt = _build_narrator_prompt(query, execution_result)

    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": NARRATOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text_format=NarratorResponseLLM,
    )

    # Count agent profiles actually included in the prompt
    if token_saving:
        agent_profile_count = len(_select_agent_profiles(execution_result, query))
    else:
        agent_profile_count = len(execution_result.grounding.agents) if execution_result.grounding else 0

    log_llm_call(
        call_type="narrator",
        model=model,
        system_prompt=NARRATOR_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response=resp,
        extra_metadata={
            "query": query,
            "token_saving_mode": "lean" if token_saving else "full",
            "prompt_char_count": len(user_prompt),
            "record_count": len(execution_result.grounding.records) if execution_result.grounding else 0,
            "agent_profile_count": agent_profile_count,
        },
    )

    llm_output: NarratorResponseLLM = resp.output_parsed

    return ScholarResponse(
        narrative=llm_output.narrative,
        suggested_followups=llm_output.suggested_followups,
        grounding=GroundingData(),  # placeholder; narrate() overwrites with executor's
        confidence=llm_output.confidence,
        metadata={"model": model},
    )


async def _stream_llm(
    query: str,
    execution_result: ExecutionResult,
    chunk_callback: Callable[[str], Awaitable[None]],
    model: str = "gpt-4.1",
    api_key: Optional[str] = None,
    token_saving: bool = True,
) -> str:
    """Stream the narrator LLM response, forwarding text chunks.

    Uses the Responses API in streaming mode without structured output
    so that narrative text can be forwarded to the client incrementally.

    The system prompt is augmented to request plain markdown only
    (no JSON wrapping), since structured output is incompatible with
    readable text streaming.

    Args:
        query: The original user query.
        execution_result: Verified execution result.
        chunk_callback: Async callable invoked with each text delta.
        model: OpenAI model name.
        api_key: OpenAI API key override.
        token_saving: If True, use lean prompt builder.

    Returns:
        The full assembled narrative text.

    Raises:
        Exception: On any API failure (caught by narrate_streaming()).
    """
    resolved_key = api_key or os.getenv("OPENAI_API_KEY")
    if not resolved_key:
        raise ValueError("OPENAI_API_KEY not set and no api_key provided")

    client = OpenAI(api_key=resolved_key)
    if token_saving:
        user_prompt = build_lean_narrator_prompt(query, execution_result)
    else:
        user_prompt = _build_narrator_prompt(query, execution_result)

    # Use plain text mode (no structured output) for streamable narrative
    streaming_system = (
        NARRATOR_SYSTEM_PROMPT
        + "\n\nRespond with ONLY the scholarly narrative in markdown. "
        "Do not wrap in JSON or add metadata fields."
    )

    stream = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": streaming_system},
            {"role": "user", "content": user_prompt},
        ],
        stream=True,
    )

    full_text: list[str] = []
    response_obj = None
    for event in stream:
        # Text deltas arrive as response.output_text.delta events.
        if event.type == "response.output_text.delta":
            delta = event.delta
            if delta:
                full_text.append(delta)
                await chunk_callback(delta)
        elif event.type == "response.completed":
            response_obj = event.response

    narrative = "".join(full_text)

    # Log with token usage (same as _call_llm for comparison)
    if response_obj:
        log_llm_call(
            call_type="narrator_streaming",
            model=model,
            system_prompt=streaming_system,
            user_prompt=user_prompt,
            response=response_obj,
            extra_metadata={
                "token_saving_mode": "lean" if token_saving else "full",
                "prompt_char_count": len(user_prompt),
                "record_count": len(execution_result.grounding.records) if execution_result.grounding else 0,
                "agent_profile_count": len(_select_agent_profiles(execution_result, query)) if token_saving else (len(execution_result.grounding.agents) if execution_result.grounding else 0),
            },
        )
    else:
        logger.warning("Narrator streaming completed without response object — no usage logged")

    return narrative


# =============================================================================
# Plan description helper
# =============================================================================


def describe_filters(plan) -> str:
    """Convert an InterpretationPlan to a readable search description.

    Scans the plan's execution steps for ``retrieve`` actions and
    summarises their filters into a human-readable phrase like
    ``"books published in Amsterdam between 1500 and 1599"``.

    Falls back to step labels if no retrieve filters are found.

    Args:
        plan: An InterpretationPlan (imported type not declared here
              to avoid a circular import; duck-typed).

    Returns:
        Human-readable description string.
    """
    parts: list[str] = []

    for step in getattr(plan, "execution_steps", []):
        if step.action.value != "retrieve":
            continue
        filters = getattr(step.params, "filters", [])
        for f in filters:
            field = f.field.value if hasattr(f.field, "value") else str(f.field)
            op = f.op.value if hasattr(f.op, "value") else str(f.op)

            if field == "year" and op == "RANGE" and f.start and f.end:
                parts.append(f"between {f.start} and {f.end}")
            elif field == "imprint_place" and f.value:
                parts.append(f"in {f.value}")
            elif field == "country" and f.value:
                parts.append(f"from {f.value}")
            elif field == "language" and f.value:
                parts.append(f"in {f.value}")
            elif field == "publisher" and f.value:
                parts.append(f"published by {f.value}")
            elif field == "subject" and f.value:
                parts.append(f"about {f.value}")
            elif field == "title" and f.value:
                parts.append(f"titled '{f.value}'")
            elif field in ("agent_norm", "agent") and f.value:
                # Skip $step_N references
                if not str(f.value).startswith("$step_"):
                    parts.append(f"by {f.value}")

    if parts:
        return "books " + " ".join(parts)

    # Fall back to step labels
    labels = [
        step.label
        for step in getattr(plan, "execution_steps", [])
        if step.label
    ]
    if labels:
        return labels[0]

    return "matching records"


# =============================================================================
# Lean prompt builder (token-optimized)
# =============================================================================


def _has_mixed_languages(records: list[RecordSummary]) -> bool:
    """Check whether the result set contains more than one language."""
    langs = {r.language for r in records if r.language}
    return len(langs) > 1


def _query_mentions_subject(query: str) -> bool:
    """Check if the query mentions a topic/subject keyword."""
    lower = query.lower()
    topic_signals = [
        "about", "subject", "topic", "on ", "regarding",
        "concerning", "related to", "dealing with",
    ]
    return any(signal in lower for signal in topic_signals)


_PRINTER_PUBLISHER_ROLES = frozenset({
    "printer", "publisher", "bookseller", "engraver",
    "typographer", "prt", "pbl", "bsl",
})

_AUTHOR_EDITOR_ROLES = frozenset({
    "author", "editor", "compiler", "translator",
    "commentator", "aut", "edt", "com", "trl",
})


def _select_relevant_agents(agents: list[str], limit: int = 2) -> list[str]:
    """Select up to *limit* agents from a record, preferring printer/publisher roles.

    Since ``RecordSummary.agents`` is a flat list of agent-name strings
    (no role metadata), we use a heuristic: the DB typically stores
    agents in MARC field order (1XX before 7XX), but we cannot
    distinguish roles here. Return the first *limit* agents as-is;
    the real role-based filtering happens at the agent-profile level.
    """
    return agents[:limit]


def _select_agent_profiles(
    result: ExecutionResult,
    query: str,
) -> list[AgentSummary]:
    """Select 0-3 agent profiles for the lean prompt.

    Selection logic (deterministic, no LLM):
      a) If a step had action "resolve_agent" or "enrich", include that agent.
      b) If an agent appears in 3+ records in the result set, include them.
      c) If the query mentions "printer"/"publisher"/"author" and an agent
         matches, include them.
      d) Otherwise include ZERO agent profiles.

    Returns at most 3 profiles.
    """
    all_agents = result.grounding.agents
    if not all_agents:
        return []

    agent_by_name: dict[str, AgentSummary] = {
        a.canonical_name.lower(): a for a in all_agents
    }

    selected_names: set[str] = set()

    # (a) Agents from resolve_agent / enrich steps
    for step in result.steps_completed:
        if step.action in ("resolve_agent", "enrich"):
            if hasattr(step.data, "matched_values"):
                # ResolvedEntity
                for val in step.data.matched_values:
                    if val.lower() in agent_by_name:
                        selected_names.add(val.lower())
                if hasattr(step.data, "query_name"):
                    qn = step.data.query_name.lower()
                    if qn in agent_by_name:
                        selected_names.add(qn)
            elif hasattr(step.data, "agents"):
                # EnrichmentBundle
                for a in step.data.agents:
                    if a.canonical_name.lower() in agent_by_name:
                        selected_names.add(a.canonical_name.lower())

    # (b) Agents appearing in 3+ records
    records = result.grounding.records
    if records:
        from collections import Counter
        agent_counts: Counter = Counter()
        for rec in records:
            for agent_name in rec.agents:
                agent_counts[agent_name.lower()] += 1
        for name, count in agent_counts.items():
            if count >= 3 and name in agent_by_name:
                selected_names.add(name)

    # (c) Query mentions role keywords
    lower_query = query.lower()
    role_keywords = {
        "printer", "publisher", "bookseller", "author", "editor",
        "translator", "compiler",
    }
    query_has_role = any(kw in lower_query for kw in role_keywords)
    if query_has_role:
        for a in all_agents:
            occupations_lower = [o.lower() for o in a.occupations]
            name_lower = a.canonical_name.lower()
            # Check if agent's occupation matches a query keyword
            if any(kw in occ for kw in role_keywords for occ in occupations_lower):
                selected_names.add(name_lower)
            # Check if agent name appears in query
            if name_lower in lower_query:
                selected_names.add(name_lower)

    # (d) If nothing selected, return empty
    if not selected_names:
        return []

    # Collect and cap at 3
    selected: list[AgentSummary] = []
    for name in selected_names:
        if name in agent_by_name and len(selected) < 3:
            selected.append(agent_by_name[name])

    return selected


def _format_lean_agent(agent: AgentSummary) -> str:
    """Format a single agent profile for the lean prompt.

    Includes: canonical_name, birth/death years, description,
    record_count, ONE link (Wikipedia preferred).
    """
    parts = [f"  - {agent.canonical_name}"]

    life_parts: list[str] = []
    if agent.birth_year:
        life_parts.append(f"b. {agent.birth_year}")
    if agent.death_year:
        life_parts.append(f"d. {agent.death_year}")
    if life_parts:
        parts.append(f"    Dates: {', '.join(life_parts)}")

    if agent.description:
        parts.append(f"    Description: {agent.description}")

    parts.append(f"    Records in collection: {agent.record_count}")

    # ONE link, Wikipedia preferred
    if agent.links:
        wiki_link = next(
            (lnk for lnk in agent.links if lnk.source == "wikipedia"),
            None,
        )
        best_link = wiki_link or agent.links[0]
        parts.append(f"    Link: [{best_link.label}]({best_link.url})")

    return "\n".join(parts)


def build_lean_narrator_prompt(query: str, result: ExecutionResult) -> str:
    """Assemble a token-optimized user prompt with verified data.

    Compared to ``_build_narrator_prompt()``, this version:
    - Drops full agent lists, full subject lists, source_steps, place field
    - Includes language only when mixed across records
    - Includes up to 2 agents per record (role-relevant)
    - Includes up to 2 subjects per record only if query mentions a subject
    - Selects 0-3 agent profiles total (not all)
    - Caps aggregations to top 5 per field and drops single-value fields
    - Drops the AVAILABLE LINKS section entirely

    Args:
        query: The original user query.
        result: ExecutionResult from the executor.

    Returns:
        Formatted prompt string for the narrator LLM call.
    """
    sections: list[str] = []

    # --- Query ---
    sections.append(f"USER QUERY: {query}")
    sections.append("")

    # --- Scholarly directives ---
    if result.directives:
        sections.append("SCHOLARLY DIRECTIVES:")
        for d in result.directives:
            line = f"  - {d.directive}"
            if d.params:
                params_str = ", ".join(f"{k}={v}" for k, v in d.params.items())
                line += f" ({params_str})"
            if d.label:
                line += f"  [{d.label}]"
            sections.append(line)
        sections.append("")

    # --- Records ---
    records = result.grounding.records
    mixed_langs = _has_mixed_languages(records) if records else False
    include_subjects = _query_mentions_subject(query)

    if records:
        sections.append(f"COLLECTION RECORDS ({len(records)} found):")
        for rec in records:
            parts = [f"  - [{rec.mms_id}] {rec.title}"]
            if rec.date_display:
                parts.append(f"    Date: {rec.date_display}")
            if rec.publisher:
                parts.append(f"    Publisher: {rec.publisher}")
            if mixed_langs and rec.language:
                parts.append(f"    Language: {rec.language}")
            if rec.agents:
                selected = _select_relevant_agents(rec.agents, limit=2)
                if selected:
                    parts.append(f"    Agents: {', '.join(selected)}")
            if include_subjects and rec.subjects:
                selected_subj = rec.subjects[:2]
                if selected_subj:
                    parts.append(f"    Subjects: {', '.join(selected_subj)}")
            if rec.primo_url:
                parts.append(f"    Catalog link: {rec.primo_url}")
            sections.append("\n".join(parts))
        sections.append("")
    else:
        sections.append("COLLECTION RECORDS: None found.")
        sections.append("")

    # --- Agent profiles (0-3 selected) ---
    selected_agents = _select_agent_profiles(result, query)
    if selected_agents:
        sections.append("AGENT PROFILES:")
        for agent in selected_agents:
            sections.append(_format_lean_agent(agent))
        sections.append("")

    # --- Aggregations (top 5 per field, drop single-value fields) ---
    aggregations = result.grounding.aggregations
    if aggregations:
        agg_lines: list[str] = []
        for field, facets in aggregations.items():
            # Drop fields with only 1 value
            if len(facets) <= 1:
                continue
            field_lines = [f"  {field}:"]
            for facet in facets[:5]:
                if isinstance(facet, dict):
                    field_lines.append(
                        f"    - {facet.get('value', '?')}: {facet.get('count', '?')}"
                    )
                else:
                    field_lines.append(f"    - {facet}")
            agg_lines.extend(field_lines)
        if agg_lines:
            sections.append("AGGREGATION RESULTS:")
            sections.extend(agg_lines)
            sections.append("")

    # --- Empty / failed steps ---
    empty_steps = [
        s for s in result.steps_completed
        if s.status in ("empty", "error")
    ]
    if empty_steps:
        sections.append("STEPS WITH NO RESULTS:")
        for s in empty_steps:
            msg = s.error_message or "no results"
            sections.append(f"  - Step {s.step_index} ({s.label}): {s.status} -- {msg}")
        sections.append("")

    # --- Truncation notice ---
    if result.truncated:
        sections.append(
            "NOTE: Results were truncated. The total count cited in step "
            "results is accurate, but only a subset of records is shown above."
        )
        sections.append("")

    # --- Session context ---
    if result.session_context and result.session_context.previous_messages:
        sections.append("CONVERSATION CONTEXT (recent messages):")
        for msg in result.session_context.previous_messages[-5:]:
            sections.append(f"  {msg.role.upper()}: {msg.content[:200]}")
        sections.append("")

    sections.append(
        "Compose a scholarly response following the evidence rules. "
        "Include exact counts and weave links naturally into the text."
    )

    return "\n".join(sections)


# =============================================================================
# Full prompt builder (original, non-optimized)
# =============================================================================


def _build_narrator_prompt(query: str, result: ExecutionResult) -> str:
    """Assemble the user prompt with verified data and directives.

    Renders the original query, scholarly directives, record details,
    agent profiles, aggregation results, and any empty/failed steps
    into a readable format for the LLM.

    Args:
        query: The original user query.
        result: ExecutionResult from the executor.

    Returns:
        Formatted prompt string for the narrator LLM call.
    """
    sections: list[str] = []

    # --- Query ---
    sections.append(f"USER QUERY: {query}")
    sections.append("")

    # --- Scholarly directives ---
    if result.directives:
        sections.append("SCHOLARLY DIRECTIVES:")
        for d in result.directives:
            line = f"  - {d.directive}"
            if d.params:
                params_str = ", ".join(f"{k}={v}" for k, v in d.params.items())
                line += f" ({params_str})"
            if d.label:
                line += f"  [{d.label}]"
            sections.append(line)
        sections.append("")

    # --- Records ---
    records = result.grounding.records
    if records:
        sections.append(f"COLLECTION RECORDS ({len(records)} found):")
        for rec in records:
            parts = [f"  - [{rec.mms_id}] {rec.title}"]
            if rec.date_display:
                parts.append(f"    Date/Place: {rec.date_display}")
            detail_items: list[str] = []
            if rec.publisher:
                detail_items.append(f"Publisher: {rec.publisher}")
            if rec.language:
                detail_items.append(f"Language: {rec.language}")
            if detail_items:
                parts.append(f"    {', '.join(detail_items)}")
            if rec.agents:
                parts.append(f"    Agents: {', '.join(rec.agents)}")
            if rec.subjects:
                parts.append(f"    Subjects: {', '.join(rec.subjects)}")
            if rec.primo_url:
                parts.append(f"    Catalog link: {rec.primo_url}")
            sections.append("\n".join(parts))
        sections.append("")
    else:
        sections.append("COLLECTION RECORDS: None found.")
        sections.append("")

    # --- Agent profiles ---
    agents = result.grounding.agents
    if agents:
        sections.append("AGENT PROFILES:")
        for agent in agents:
            parts = [f"  - {agent.canonical_name}"]
            if agent.variants:
                parts.append(f"    Also known as: {', '.join(agent.variants)}")
            life_parts: list[str] = []
            if agent.birth_year:
                life_parts.append(f"b. {agent.birth_year}")
            if agent.death_year:
                life_parts.append(f"d. {agent.death_year}")
            if life_parts:
                parts.append(f"    Dates: {', '.join(life_parts)}")
            if agent.occupations:
                parts.append(f"    Occupations: {', '.join(agent.occupations)}")
            if agent.description:
                parts.append(f"    Description: {agent.description}")
            parts.append(f"    Records in collection: {agent.record_count}")
            if agent.wikipedia_context:
                parts.append(f"    Wikipedia context: {agent.wikipedia_context[:800]}")
            if agent.links:
                link_strs = [f"[{lnk.label}]({lnk.url})" for lnk in agent.links]
                parts.append(f"    Links: {', '.join(link_strs)}")
            sections.append("\n".join(parts))
        sections.append("")

    # --- Aggregations ---
    aggregations = result.grounding.aggregations
    if aggregations:
        sections.append("AGGREGATION RESULTS:")
        for field, facets in aggregations.items():
            sections.append(f"  {field}:")
            for facet in facets[:20]:  # cap display
                if isinstance(facet, dict):
                    sections.append(f"    - {facet.get('value', '?')}: {facet.get('count', '?')}")
                else:
                    sections.append(f"    - {facet}")
        sections.append("")

    # --- Global grounding links ---
    links = result.grounding.links
    if links:
        sections.append("AVAILABLE LINKS:")
        for link in links:
            sections.append(f"  - [{link.label}]({link.url}) ({link.source})")
        sections.append("")

    # --- Empty / failed steps ---
    empty_steps = [
        s for s in result.steps_completed
        if s.status in ("empty", "error")
    ]
    if empty_steps:
        sections.append("STEPS WITH NO RESULTS:")
        for s in empty_steps:
            msg = s.error_message or "no results"
            sections.append(f"  - Step {s.step_index} ({s.label}): {s.status} -- {msg}")
        sections.append("")

    # --- Truncation notice ---
    if result.truncated:
        sections.append(
            "NOTE: Results were truncated. The total count cited in step "
            "results is accurate, but only a subset of records is shown above."
        )
        sections.append("")

    # --- Session context ---
    if result.session_context and result.session_context.previous_messages:
        sections.append("CONVERSATION CONTEXT (recent messages):")
        for msg in result.session_context.previous_messages[-5:]:
            sections.append(f"  {msg.role.upper()}: {msg.content[:200]}")
        sections.append("")

    sections.append(
        "Compose a scholarly response following the evidence rules. "
        "Include exact counts and weave links naturally into the text."
    )

    return "\n".join(sections)


# =============================================================================
# Fallback (no LLM)
# =============================================================================


def _fallback_response(
    query: str,
    execution_result: ExecutionResult,
) -> ScholarResponse:
    """Build a structured summary when the LLM fails.

    Produces a readable but non-scholarly response directly from
    the execution result data, requiring no LLM call.

    Args:
        query: The original user query.
        execution_result: Verified execution result.

    Returns:
        ScholarResponse with a deterministic fallback narrative.
    """
    parts: list[str] = []
    grounding = execution_result.grounding
    records = grounding.records
    agents = grounding.agents
    links = grounding.links

    # Header
    if records:
        parts.append(
            f"Found {len(records)} record(s) matching your query: \"{query}\""
        )
        parts.append("")

        # List records
        for rec in records:
            line = f"- **{rec.title}**"
            if rec.date_display:
                line += f" ({rec.date_display})"
            line += f" [{rec.mms_id}]"
            if rec.primo_url:
                line += f" ([catalog]({rec.primo_url}))"
            parts.append(line)
        parts.append("")
    else:
        parts.append(
            f"No records were found in our collection matching: \"{query}\""
        )
        parts.append("")

    # Agent profiles
    if agents:
        parts.append("**Related people:**")
        for agent in agents:
            line = f"- {agent.canonical_name}"
            life_parts: list[str] = []
            if agent.birth_year:
                life_parts.append(str(agent.birth_year))
            if agent.death_year:
                life_parts.append(str(agent.death_year))
            if life_parts:
                line += f" ({'-'.join(life_parts)})"
            if agent.description:
                line += f" -- {agent.description}"
            parts.append(line)
        parts.append("")

    # Links
    if links:
        parts.append("**Links:**")
        for link in links:
            parts.append(f"- [{link.label}]({link.url})")
        parts.append("")

    # Suggested followups
    followups: list[str] = []
    if records:
        followups.append(f"Tell me more about one of these {len(records)} records")
    if agents:
        followups.append(f"What else did {agents[0].canonical_name} write?")
    if not records:
        followups.append("Try a broader search or different terms")

    narrative = "\n".join(parts).strip()

    return ScholarResponse(
        narrative=narrative,
        suggested_followups=followups,
        grounding=grounding,
        confidence=0.5,  # lower confidence for fallback
        metadata={"fallback": True},
    )
