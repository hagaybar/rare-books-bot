"""Tests for scholar pipeline shared models."""
import pytest
from pydantic import ValidationError


def test_step_action_enum_values():
    """All 7 executor actions are defined."""
    from scripts.chat.plan_models import StepAction
    assert len(StepAction) == 7
    assert StepAction.RESOLVE_AGENT == "resolve_agent"
    assert StepAction.RETRIEVE == "retrieve"
    assert StepAction.AGGREGATE == "aggregate"


def test_resolve_agent_params_valid():
    from scripts.chat.plan_models import ResolveAgentParams
    p = ResolveAgentParams(name="Joseph Karo", variants=["קארו, יוסף בן אפרים"])
    assert p.name == "Joseph Karo"
    assert len(p.variants) == 1


def test_resolve_agent_params_defaults():
    from scripts.chat.plan_models import ResolveAgentParams
    p = ResolveAgentParams(name="Maimonides")
    assert p.variants == []


def test_retrieve_params_reuses_filter_model():
    """RetrieveParams.filters uses the existing Filter model."""
    from scripts.chat.plan_models import RetrieveParams
    from scripts.schemas.query_plan import Filter, FilterField, FilterOp
    f = Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="test")
    p = RetrieveParams(filters=[f])
    assert p.scope == "full_collection"
    assert len(p.filters) == 1


def test_retrieve_params_with_step_ref_scope():
    from scripts.chat.plan_models import RetrieveParams
    p = RetrieveParams(filters=[], scope="$step_0")
    assert p.scope == "$step_0"


def test_execution_step_valid():
    from scripts.chat.plan_models import ExecutionStep, StepAction, ResolveAgentParams
    step = ExecutionStep(
        action=StepAction.RESOLVE_AGENT,
        params=ResolveAgentParams(name="Karo"),
        label="Resolve Karo",
    )
    assert step.depends_on == []


def test_scholarly_directive_freeform():
    from scripts.chat.plan_models import ScholarlyDirective
    d = ScholarlyDirective(
        directive="contextualize",
        params={"theme": "Jewish legal codification"},
        label="Historical context",
    )
    assert d.directive == "contextualize"


def test_interpretation_plan_with_clarification():
    from scripts.chat.plan_models import InterpretationPlan
    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Ambiguous entity",
        execution_steps=[],
        directives=[],
        confidence=0.55,
        clarification="Which Karo do you mean?",
    )
    assert plan.clarification is not None
    assert plan.confidence < 0.7


def test_interpretation_plan_without_clarification():
    from scripts.chat.plan_models import InterpretationPlan, ExecutionStep, StepAction, ResolveAgentParams
    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Clear query",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Karo"),
                label="Resolve",
            )
        ],
        directives=[],
        confidence=0.95,
    )
    assert plan.clarification is None
    assert len(plan.execution_steps) == 1


def test_record_summary_fields():
    from scripts.chat.plan_models import RecordSummary
    r = RecordSummary(
        mms_id="990001234",
        title="Shulchan Aruch",
        date_display="Venice, 1565",
        place="venice",
        publisher="bragadin",
        language="heb",
        agents=["קארו, יוסף בן אפרים"],
        subjects=["Jewish law"],
        primo_url="https://primo.example.com/990001234",
        source_steps=[1],
    )
    assert r.mms_id == "990001234"


def test_agent_summary_fields():
    from scripts.chat.plan_models import AgentSummary
    a = AgentSummary(
        canonical_name="קארו, יוסף בן אפרים",
        variants=["Joseph Karo", "Caro, Joseph"],
        birth_year=1488,
        death_year=1575,
        occupations=["rabbi", "posek"],
        description="Author of the Shulchan Aruch",
        record_count=3,
        links=[],
    )
    assert a.birth_year == 1488


def test_grounding_link():
    from scripts.chat.plan_models import GroundingLink
    link = GroundingLink(
        entity_type="agent",
        entity_id="Q193460",
        label="Joseph Karo on Wikipedia",
        url="https://en.wikipedia.org/wiki/Joseph_Karo",
        source="wikipedia",
    )
    assert link.source == "wikipedia"


def test_step_result_ok():
    from scripts.chat.plan_models import StepResult, RecordSet
    sr = StepResult(
        step_index=0,
        action="retrieve",
        label="Find works",
        status="ok",
        data=RecordSet(mms_ids=["990001"], total_count=1, filters_applied=[]),
        record_count=1,
    )
    assert sr.status == "ok"


def test_step_result_empty():
    from scripts.chat.plan_models import StepResult, RecordSet
    sr = StepResult(
        step_index=0,
        action="retrieve",
        label="Find works",
        status="empty",
        data=RecordSet(mms_ids=[], total_count=0, filters_applied=[]),
        record_count=0,
    )
    assert sr.status == "empty"


def test_execution_result_complete():
    from scripts.chat.plan_models import ExecutionResult, GroundingData
    er = ExecutionResult(
        steps_completed=[],
        directives=[],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        original_query="test",
        session_context=None,
        truncated=False,
    )
    assert not er.truncated


def test_scholar_response():
    from scripts.chat.plan_models import ScholarResponse, GroundingData
    sr = ScholarResponse(
        narrative="Joseph Karo was...",
        suggested_followups=["What about Maimonides?"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={"intents": ["entity_exploration"]},
    )
    assert len(sr.suggested_followups) == 1


def test_resolved_entity():
    from scripts.chat.plan_models import ResolvedEntity
    re = ResolvedEntity(
        query_name="Joseph Karo",
        matched_values=["קארו, יוסף בן אפרים"],
        match_method="alias_exact",
        confidence=0.95,
    )
    assert len(re.matched_values) == 1


def test_connection_graph():
    from scripts.chat.plan_models import ConnectionGraph
    cg = ConnectionGraph(
        connections=[{"agent_a": "Karo", "agent_b": "Alkabetz", "shared_records": 1, "shared_mms_ids": ["990001"]}],
        isolated=["Isserles"],
    )
    assert len(cg.connections) == 1
    assert len(cg.isolated) == 1


def test_llm_facing_step_model():
    """ExecutionStepLLM uses string action and dict params for OpenAI schema."""
    from scripts.chat.plan_models import ExecutionStepLLM
    step = ExecutionStepLLM(
        action="resolve_agent",
        params={"name": "Joseph Karo", "variants": []},
        label="Resolve Karo",
    )
    assert step.action == "resolve_agent"
    assert isinstance(step.params, dict)


def test_llm_facing_plan_model():
    """InterpretationPlanLLM uses ExecutionStepLLM for OpenAI Responses API."""
    from scripts.chat.plan_models import InterpretationPlanLLM, ExecutionStepLLM, ScholarlyDirective
    plan = InterpretationPlanLLM(
        intents=["retrieval"],
        reasoning="Simple query",
        execution_steps=[
            ExecutionStepLLM(
                action="retrieve",
                params={"filters": [], "scope": "full_collection"},
                label="Find books",
            )
        ],
        directives=[
            ScholarlyDirective(directive="interpret", params={}, label="Interpret results"),
        ],
        confidence=0.90,
    )
    assert len(plan.execution_steps) == 1
    assert plan.execution_steps[0].action == "retrieve"


def test_session_context_with_previous_records():
    """SessionContext captures follow-up state."""
    from scripts.chat.plan_models import SessionContext
    from scripts.chat.models import Message
    ctx = SessionContext(
        session_id="sess-123",
        previous_messages=[
            Message(role="user", content="books by Karo"),
            Message(role="assistant", content="Found 3 books."),
        ],
        previous_record_ids=["990001", "990002", "990003"],
    )
    assert len(ctx.previous_messages) == 2
    assert len(ctx.previous_record_ids) == 3


def test_aggregation_result():
    """AggregationResult captures faceted aggregation output."""
    from scripts.chat.plan_models import AggregationResult
    ar = AggregationResult(
        field="date_decade",
        facets=[{"value": "1550", "count": 12}, {"value": "1560", "count": 8}],
        total_records=20,
    )
    assert ar.field == "date_decade"
    assert len(ar.facets) == 2
    assert ar.total_records == 20


def test_enrichment_bundle():
    """EnrichmentBundle wraps enriched agent profiles."""
    from scripts.chat.plan_models import EnrichmentBundle, AgentSummary
    eb = EnrichmentBundle(
        agents=[
            AgentSummary(
                canonical_name="קארו, יוסף בן אפרים",
                variants=["Joseph Karo"],
                birth_year=1488,
                death_year=1575,
                occupations=["rabbi"],
                description="Author of the Shulchan Aruch",
                record_count=3,
                links=[],
            )
        ]
    )
    assert len(eb.agents) == 1


def test_sample_params():
    """SampleParams controls sampling strategy."""
    from scripts.chat.plan_models import SampleParams
    sp = SampleParams(scope="$step_1", n=5, strategy="notable")
    assert sp.n == 5
    assert sp.strategy == "notable"


def test_find_connections_params():
    """FindConnectionsParams lists agents and depth."""
    from scripts.chat.plan_models import FindConnectionsParams
    fcp = FindConnectionsParams(agents=["$step_0"], depth=2)
    assert fcp.depth == 2
    assert len(fcp.agents) == 1


def test_enrich_params():
    """EnrichParams references targets and fields."""
    from scripts.chat.plan_models import EnrichParams
    ep = EnrichParams(targets="$step_0", fields=["bio", "links"])
    assert ep.targets == "$step_0"
    assert "bio" in ep.fields


def test_aggregate_params():
    """AggregateParams configures field aggregation."""
    from scripts.chat.plan_models import AggregateParams
    ap = AggregateParams(field="date_decade", scope="$step_0", limit=10)
    assert ap.field == "date_decade"
    assert ap.limit == 10


def test_resolve_publisher_params():
    """ResolvePublisherParams mirrors agent resolution for publishers."""
    from scripts.chat.plan_models import ResolvePublisherParams
    rpp = ResolvePublisherParams(name="Elsevier", variants=["ex officina elzeviriana"])
    assert rpp.name == "Elsevier"
    assert len(rpp.variants) == 1
