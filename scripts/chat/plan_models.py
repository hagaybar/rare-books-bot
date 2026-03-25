"""Shared Pydantic models for the scholar pipeline.

This module defines the contract between the three stages of the scholar
pipeline: Interpreter, Executor, and Narrator.

Models are organized into five groups:

1. **Enums & typed params** -- ``StepAction`` enum and one params model per
   action type (``ResolveAgentParams``, ``RetrieveParams``, etc.).
2. **Step output types** -- typed results produced by executor handlers
   (``ResolvedEntity``, ``RecordSet``, ``AggregationResult``, etc.).
3. **Plan models** -- ``ExecutionStep``, ``ScholarlyDirective``,
   ``InterpretationPlan`` (produced by the Interpreter).
4. **Execution models** -- ``StepResult``, ``RecordSummary``,
   ``AgentSummary``, ``GroundingLink``, ``GroundingData``,
   ``SessionContext``, ``ExecutionResult`` (produced by the Executor).
5. **Response model** -- ``ScholarResponse`` (produced by the Narrator).
6. **LLM-facing models** -- ``ExecutionStepLLM``, ``InterpretationPlanLLM``
   (simplified schema for OpenAI Responses API).
"""

from __future__ import annotations

from enum import Enum
from typing import Union

from pydantic import BaseModel, Field

from scripts.chat.models import Message
from scripts.schemas.query_plan import Filter


# ============================================================================
# 1. Enums & typed params
# ============================================================================


class StepAction(str, Enum):
    """Fixed set of executor actions.

    Each action maps to a handler function in the executor and a typed
    params model.
    """

    RESOLVE_AGENT = "resolve_agent"
    RESOLVE_PUBLISHER = "resolve_publisher"
    RETRIEVE = "retrieve"
    AGGREGATE = "aggregate"
    FIND_CONNECTIONS = "find_connections"
    ENRICH = "enrich"
    SAMPLE = "sample"


class ResolveAgentParams(BaseModel):
    """Parameters for the ``resolve_agent`` action.

    The executor looks up the given name (and optional LLM-proposed
    variants) in the agent authority tables.
    """

    name: str
    variants: list[str] = Field(default_factory=list)


class ResolvePublisherParams(BaseModel):
    """Parameters for the ``resolve_publisher`` action.

    Mirrors ``ResolveAgentParams`` for publisher variant lookup.
    """

    name: str
    variants: list[str] = Field(default_factory=list)


class RetrieveParams(BaseModel):
    """Parameters for the ``retrieve`` action.

    Reuses the existing ``Filter`` model from ``scripts.schemas.query_plan``
    for compatibility with ``db_adapter.build_where_clause()``.

    ``scope`` is either ``"full_collection"`` or a ``$step_N`` reference
    to narrow the SQL to a previous step's record set.
    """

    filters: list[Filter]
    scope: str = "full_collection"


class AggregateParams(BaseModel):
    """Parameters for the ``aggregate`` action.

    Computes faceted counts on a given field, optionally scoped to
    a prior step's record set.
    """

    field: str
    scope: str = "full_collection"
    limit: int = 20


class FindConnectionsParams(BaseModel):
    """Parameters for the ``find_connections`` action.

    Finds co-occurrence connections between agents. Agent references
    may be literal names or ``$step_N`` references.
    """

    agents: list[str]
    depth: int = 1


class EnrichParams(BaseModel):
    """Parameters for the ``enrich`` action.

    Fetches biographical data and external links for resolved agents.
    """

    targets: str
    fields: list[str] = Field(default_factory=lambda: ["bio", "links"])


class SampleParams(BaseModel):
    """Parameters for the ``sample`` action.

    Selects a subset of records from a prior step's result set
    using the given strategy.
    """

    scope: str
    n: int = 10
    strategy: str = "diverse"


# ============================================================================
# 2. Step output types
# ============================================================================


class ResolvedEntity(BaseModel):
    """Output of ``resolve_agent`` / ``resolve_publisher``.

    Contains the canonical DB values that matched the query name,
    along with the matching method and confidence.
    """

    query_name: str
    matched_values: list[str]
    match_method: str
    confidence: float


class RecordSet(BaseModel):
    """Output of ``retrieve`` / ``sample``.

    ``mms_ids`` may be truncated; ``total_count`` always reflects
    the full match count.
    """

    mms_ids: list[str]
    total_count: int
    filters_applied: list[dict]


class AggregationResult(BaseModel):
    """Output of ``aggregate``.

    Each facet is a dict with ``value`` and ``count`` keys.
    """

    field: str
    facets: list[dict]
    total_records: int


class ConnectionGraph(BaseModel):
    """Output of ``find_connections``.

    Each connection dict has ``agent_a``, ``agent_b``,
    ``shared_records``, and ``shared_mms_ids`` keys.
    """

    connections: list[dict]
    isolated: list[str]


class GroundingLink(BaseModel):
    """A single external reference link for evidence grounding.

    Links point to Primo, Wikipedia, Wikidata, VIAF, or NLI.
    """

    entity_type: str
    entity_id: str
    label: str
    url: str
    source: str


class AgentSummary(BaseModel):
    """Enriched agent profile for narrator consumption.

    Combines authority data with external enrichment links.
    """

    canonical_name: str
    variants: list[str]
    birth_year: int | None = None
    death_year: int | None = None
    occupations: list[str] = Field(default_factory=list)
    description: str | None = None
    record_count: int = 0
    links: list[GroundingLink] = Field(default_factory=list)
    wikipedia_context: str | None = None  # Extended bio from Wikipedia


class EnrichmentBundle(BaseModel):
    """Output of ``enrich``.

    Wraps one or more enriched agent profiles.
    """

    agents: list[AgentSummary]


# ============================================================================
# 3. Plan models (Interpreter output)
# ============================================================================

# Union of all typed param models for ExecutionStep.params
StepParams = Union[
    ResolveAgentParams,
    ResolvePublisherParams,
    RetrieveParams,
    AggregateParams,
    FindConnectionsParams,
    EnrichParams,
    SampleParams,
]


class ExecutionStep(BaseModel):
    """A single step in the execution plan.

    ``action`` determines the executor handler; ``params`` carries
    the action-specific configuration. ``depends_on`` lists step
    indices that must complete before this step runs.
    """

    action: StepAction
    params: StepParams
    label: str
    depends_on: list[int] = Field(default_factory=list)


class ScholarlyDirective(BaseModel):
    """Free-form instruction passed through to the narrator.

    The ``directive`` field is not an enum -- new directive types
    require only a narrator prompt update, no code change.
    """

    directive: str
    params: dict = Field(default_factory=dict)
    label: str = ""


class InterpretationPlan(BaseModel):
    """Complete plan produced by the Interpreter (Stage 1).

    Contains the execution steps for the deterministic executor
    and scholarly directives for the narrator.

    If ``clarification`` is set, the pipeline short-circuits:
    the plan is returned to the user as a clarification prompt
    instead of being executed.
    """

    intents: list[str]
    reasoning: str
    execution_steps: list[ExecutionStep]
    directives: list[ScholarlyDirective]
    confidence: float = Field(ge=0.0, le=1.0)
    clarification: str | None = None


# ============================================================================
# 4. Execution models (Executor output)
# ============================================================================

# Union of all step output types for StepResult.data
StepOutputData = Union[
    ResolvedEntity,
    RecordSet,
    AggregationResult,
    ConnectionGraph,
    EnrichmentBundle,
]


class StepResult(BaseModel):
    """Result of executing a single plan step.

    ``status`` is one of: ``"ok"``, ``"empty"``, ``"partial"``,
    ``"error"``.  If ``"error"``, ``error_message`` explains why.
    """

    step_index: int
    action: str
    label: str
    status: str
    data: StepOutputData
    record_count: int | None = None
    error_message: str | None = None


class RecordSummary(BaseModel):
    """Summary of a bibliographic record for narrator consumption.

    Carries enough detail for the narrator to compose a scholarly
    response without direct DB access.
    """

    mms_id: str
    title: str
    date_display: str | None = None
    place: str | None = None
    publisher: str | None = None
    language: str | None = None
    agents: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    primo_url: str = ""
    source_steps: list[int] = Field(default_factory=list)


class GroundingData(BaseModel):
    """Aggregated grounding evidence for the narrator.

    Deduplicated across all execution steps.
    """

    records: list[RecordSummary] = Field(default_factory=list)
    agents: list[AgentSummary] = Field(default_factory=list)
    aggregations: dict[str, list] = Field(default_factory=dict)
    links: list[GroundingLink] = Field(default_factory=list)


class SessionContext(BaseModel):
    """Follow-up context from a previous conversation turn.

    Enables the ``$previous_results`` scope reference for
    follow-up refinement queries.
    """

    session_id: str
    previous_messages: list[Message] = Field(default_factory=list)
    previous_record_ids: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Complete output of the Executor (Stage 2).

    Contains all step results, directives (passed through from the
    plan), and aggregated grounding data for the narrator.
    """

    steps_completed: list[StepResult]
    directives: list[ScholarlyDirective]
    grounding: GroundingData
    original_query: str
    session_context: SessionContext | None = None
    truncated: bool = False


# ============================================================================
# 5. Response model (Narrator output)
# ============================================================================


class ScholarResponse(BaseModel):
    """Final scholarly response produced by the Narrator (Stage 3).

    The ``narrative`` is markdown text suitable for display.
    ``grounding`` is passed through from the executor for
    structured frontend rendering.
    """

    narrative: str
    suggested_followups: list[str] = Field(default_factory=list)
    grounding: GroundingData
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


# ============================================================================
# 6. LLM-facing models (for OpenAI Responses API)
# ============================================================================


class ExecutionStepLLM(BaseModel):
    """Simplified execution step schema for the LLM.

    Uses ``str`` action and a JSON-encoded ``str`` for params instead
    of typed unions, which are compatible with the OpenAI Responses API
    (which requires ``additionalProperties: false`` on all objects).
    The interpreter converts these to typed ``ExecutionStep`` objects.
    """

    action: str
    params: str  # JSON-encoded dict; parsed in _convert_llm_plan()
    label: str
    depends_on: list[int] = Field(default_factory=list)


class ScholarlyDirectiveLLM(BaseModel):
    """LLM-facing version of ScholarlyDirective.

    Uses ``str`` for params to satisfy OpenAI structured output
    requirements (``additionalProperties: false``).
    """

    directive: str
    params: str = ""  # JSON-encoded dict; parsed in _convert_llm_plan()
    label: str = ""


class InterpretationPlanLLM(BaseModel):
    """LLM output schema for the Interpreter.

    Uses ``ExecutionStepLLM`` (string action + JSON params) instead
    of the typed ``ExecutionStep`` union. The interpreter validates
    and converts this to a typed ``InterpretationPlan``.
    """

    intents: list[str]
    reasoning: str
    execution_steps: list[ExecutionStepLLM]
    directives: list[ScholarlyDirectiveLLM]
    confidence: float = Field(ge=0.0, le=1.0)
    clarification: str | None = None
