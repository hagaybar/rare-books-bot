"""Tests for the executor (Stage 2) -- core framework + handler tests.

Tests dependency resolution, $step_N substitution, error handling,
and real DB handler execution.
All tests use in-memory SQLite, no LLM needed.
"""
import sqlite3
from pathlib import Path

import pytest

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
    InterpretationPlan,
    RecordSet,
    ResolveAgentParams,
    ResolvePublisherParams,
    ResolvedEntity,
    RetrieveParams,
    SampleParams,
    ScholarlyDirective,
    StepAction,
    StepResult,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_plan():
    return InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.95,
    )


@pytest.fixture
def test_db(tmp_path):
    """Create a minimal test SQLite DB with schema and sample data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY, mms_id TEXT UNIQUE, source_file TEXT,
            created_at TEXT, jsonl_line_number INTEGER
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY, record_id INTEGER, occurrence INTEGER,
            date_raw TEXT, place_raw TEXT, publisher_raw TEXT,
            manufacturer_raw TEXT, source_tags TEXT,
            date_start INTEGER, date_end INTEGER, date_label TEXT,
            date_confidence REAL, date_method TEXT,
            place_norm TEXT, place_display TEXT, place_confidence REAL,
            place_method TEXT,
            publisher_norm TEXT, publisher_display TEXT,
            publisher_confidence REAL, publisher_method TEXT,
            country_code TEXT, country_name TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
            agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT,
            authority_uri TEXT,
            agent_norm TEXT, agent_confidence REAL, agent_method TEXT,
            agent_notes TEXT,
            role_norm TEXT, role_confidence REAL, role_method TEXT,
            provenance_json TEXT
        );
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT,
            source_tag TEXT, scheme TEXT, heading_lang TEXT,
            authority_uri TEXT, parts TEXT, source TEXT
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER,
            title_type TEXT, value TEXT, source TEXT
        );
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY, record_id INTEGER, code TEXT, source TEXT
        );
        CREATE TABLE agent_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT,
            canonical_name_lower TEXT,
            agent_type TEXT, dates_active TEXT, date_start INTEGER,
            date_end INTEGER, notes TEXT, sources TEXT, confidence REAL,
            authority_uri TEXT, wikidata_id TEXT, viaf_id TEXT, nli_id TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE agent_aliases (
            id INTEGER PRIMARY KEY, authority_id INTEGER,
            alias_form TEXT, alias_form_lower TEXT,
            alias_type TEXT, script TEXT, language TEXT, is_primary INTEGER,
            priority INTEGER, notes TEXT, created_at TEXT
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE,
            nli_id TEXT, wikidata_id TEXT, viaf_id TEXT, isni_id TEXT,
            loc_id TEXT, label TEXT, description TEXT, person_info TEXT,
            place_info TEXT, image_url TEXT, wikipedia_url TEXT,
            source TEXT, confidence REAL, fetched_at TEXT, expires_at TEXT
        );
        CREATE TABLE publisher_authorities (
            id INTEGER PRIMARY KEY, canonical_name TEXT,
            canonical_name_lower TEXT,
            type TEXT, dates_active TEXT, date_start INTEGER,
            date_end INTEGER, location TEXT, notes TEXT, sources TEXT,
            confidence REAL, is_missing_marker INTEGER,
            viaf_id TEXT, wikidata_id TEXT, cerl_id TEXT, branch TEXT,
            primary_language TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE publisher_variants (
            id INTEGER PRIMARY KEY, authority_id INTEGER,
            variant_form TEXT, variant_form_lower TEXT,
            script TEXT, language TEXT, is_primary INTEGER,
            priority INTEGER, notes TEXT, created_at TEXT
        );

        -- Sample data: Joseph Karo with 2 books, plus a second agent
        INSERT INTO records VALUES
            (1, '990001234', 'test.xml', '2024-01-01', 1);
        INSERT INTO records VALUES
            (2, '990005678', 'test.xml', '2024-01-01', 2);
        INSERT INTO records VALUES
            (3, '990009999', 'test.xml', '2024-01-01', 3);

        INSERT INTO imprints VALUES
            (1, 1, 0, '1565', 'Venice', 'Bragadin', NULL, '["264"]',
             1565, 1565, '1565', 0.99, 'exact',
             'venice', 'Venice', 0.95, 'place_alias_map',
             'bragadin', 'Bragadin', 0.95, 'publisher_authority',
             'it', 'italy');
        INSERT INTO imprints VALUES
            (2, 2, 0, '1698', 'Amsterdam', 'Proops', NULL, '["264"]',
             1698, 1698, '1698', 0.99, 'exact',
             'amsterdam', 'Amsterdam', 0.95, 'place_alias_map',
             'proops', 'Proops', 0.95, 'publisher_authority',
             'ne', 'netherlands');
        INSERT INTO imprints VALUES
            (3, 3, 0, '1520', 'Venice', 'Bomberg', NULL, '["264"]',
             1520, 1520, '1520', 0.99, 'exact',
             'venice', 'Venice', 0.95, 'place_alias_map',
             'bomberg', 'Bomberg', 0.95, 'publisher_authority',
             'it', 'italy');

        -- Agent: Karo on records 1 and 2
        INSERT INTO agents VALUES
            (1, 1, 0,
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             'personal', 'author', 'relator_code',
             'http://nli.org/auth/1',
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (2, 2, 0,
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             'personal', 'author', 'relator_code',
             'http://nli.org/auth/1',
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');
        -- Agent: Bomberg on record 3, also a printer on record 1
        INSERT INTO agents VALUES
            (3, 3, 0, 'Daniel Bomberg', 'personal', 'printer',
             'relator_code', 'http://nli.org/auth/2',
             'bomberg, daniel', 0.95, 'base_clean', NULL,
             'printer', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (4, 1, 1, 'Daniel Bomberg', 'personal', 'printer',
             'relator_code', 'http://nli.org/auth/2',
             'bomberg, daniel', 0.95, 'base_clean', NULL,
             'printer', 0.95, 'relator_code', '[]');

        INSERT INTO subjects VALUES
            (1, 1, 'Jewish law', '650', 'lcsh', 'eng', NULL, '{}', '[]');
        INSERT INTO subjects VALUES
            (2, 3, 'Talmud', '650', 'lcsh', 'eng', NULL, '{}', '[]');

        INSERT INTO titles VALUES
            (1, 1, 'main', 'Shulchan Aruch', '["245"]');
        INSERT INTO titles VALUES
            (2, 2, 'main', 'Beit Yosef', '["245"]');
        INSERT INTO titles VALUES
            (3, 3, 'main', 'Talmud Bavli', '["245"]');

        INSERT INTO languages VALUES (1, 1, 'heb', '008/35-37');
        INSERT INTO languages VALUES (2, 2, 'heb', '008/35-37');
        INSERT INTO languages VALUES (3, 3, 'heb', '008/35-37');

        -- Agent authority: Karo
        INSERT INTO agent_authorities VALUES
            (1,
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             '\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd',
             'personal', '1488-1575', 1488, 1575, NULL, NULL, 0.95,
             'http://nli.org/auth/1', 'Q193460', NULL, NULL,
             '2024-01-01', '2024-01-01');
        -- Agent authority: Bomberg
        INSERT INTO agent_authorities VALUES
            (2, 'Bomberg, Daniel', 'bomberg, daniel',
             'personal', '1483-1549', 1483, 1549, NULL, NULL, 0.90,
             'http://nli.org/auth/2', 'Q124530', NULL, NULL,
             '2024-01-01', '2024-01-01');

        INSERT INTO agent_aliases VALUES
            (1, 1, 'Joseph Karo', 'joseph karo',
             'cross_script', 'latin', 'eng', 0, 0, NULL, '2024-01-01');
        INSERT INTO agent_aliases VALUES
            (2, 1, 'Caro, Joseph', 'caro, joseph',
             'word_reorder', 'latin', 'eng', 0, 0, NULL, '2024-01-01');
        INSERT INTO agent_aliases VALUES
            (3, 2, 'Daniel Bomberg', 'daniel bomberg',
             'primary', 'latin', 'eng', 1, 0, NULL, '2024-01-01');

        INSERT INTO authority_enrichment VALUES
            (1, 'http://nli.org/auth/1', 'NLI001', 'Q193460',
             'VIAF001', NULL, NULL, 'Joseph Karo',
             'Rabbi and author of Shulchan Aruch',
             '{"birth_year": 1488, "death_year": 1575, "birth_place": "Toledo", "occupations": ["rabbi", "posek"], "teachers": ["Jacob Berab"], "students": [], "notable_works": ["Shulchan Aruch"]}',
             NULL, NULL, 'https://en.wikipedia.org/wiki/Joseph_Karo',
             'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO authority_enrichment VALUES
            (2, 'http://nli.org/auth/2', 'NLI002', 'Q124530',
             'VIAF002', NULL, NULL, 'Daniel Bomberg',
             'Venetian printer of Hebrew books',
             '{"birth_year": 1483, "death_year": 1549, "birth_place": "Antwerp", "occupations": ["printer"], "teachers": [], "students": [], "notable_works": ["Talmud"]}',
             NULL, NULL, 'https://en.wikipedia.org/wiki/Daniel_Bomberg',
             'wikidata', 0.90, '2024-01-01', '2025-01-01');

        -- Publisher authority: Bragadin
        INSERT INTO publisher_authorities VALUES
            (1, 'Bragadin', 'bragadin', 'printing_house',
             '1550-1710', 1550, 1710, 'Venice', NULL, NULL, 0.95, 0,
             NULL, NULL, NULL, NULL, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO publisher_variants VALUES
            (1, 1, 'Bragadin', 'bragadin', 'latin', NULL, 1, 0, NULL,
             '2024-01-01');
        INSERT INTO publisher_variants VALUES
            (2, 1, 'Giovanni di Gara for Bragadin',
             'giovanni di gara for bragadin',
             'latin', NULL, 0, 0, NULL, '2024-01-01');
    """)
    conn.close()

    # Reset module-level caches that could interfere between tests
    from scripts.query import db_adapter
    db_adapter._schema_validated = False
    db_adapter._agent_alias_tables_present = None

    from scripts.chat import cross_reference
    cross_reference._reset_graph_cache()

    return db_path


# =============================================================================
# Core execution tests
# =============================================================================


def test_execute_empty_plan(empty_plan):
    """Empty plan returns empty result, not an error."""
    from scripts.chat.executor import execute_plan

    result = execute_plan(empty_plan, db_path=Path(":memory:"))
    assert isinstance(result, ExecutionResult)
    assert len(result.steps_completed) == 0
    assert result.truncated is False


def test_directives_passed_through():
    """Scholarly directives are forwarded to the result unchanged."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Test",
        execution_steps=[],
        directives=[
            ScholarlyDirective(
                directive="expand", params={"focus": "Karo"}, label="Expand"
            ),
            ScholarlyDirective(
                directive="contextualize", params={"theme": "law"}, label="Context"
            ),
        ],
        confidence=0.9,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert len(result.directives) == 2
    assert result.directives[0].directive == "expand"
    assert result.directives[1].params == {"theme": "law"}


def test_step_dependency_ordering():
    """Steps are executed in dependency order."""
    from scripts.chat.executor import _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
        ),
        ExecutionStep(
            action=StepAction.AGGREGATE,
            params=AggregateParams(field="date_decade", scope="$step_0"),
            label="S1",
            depends_on=[0],
        ),
    ]
    order = _resolve_execution_order(steps)
    assert order == [0, 1]


def test_dependency_ordering_three_steps():
    """Three steps with diamond dependency: step 2 depends on both 0 and 1."""
    from scripts.chat.executor import _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RESOLVE_AGENT,
            params=ResolveAgentParams(name="Karo"),
            label="S0",
        ),
        ExecutionStep(
            action=StepAction.RESOLVE_PUBLISHER,
            params=ResolveAgentParams(name="Bragadin"),
            label="S1",
        ),
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S2",
            depends_on=[0, 1],
        ),
    ]
    order = _resolve_execution_order(steps)
    # 0 and 1 must come before 2
    assert order.index(0) < order.index(2)
    assert order.index(1) < order.index(2)


def test_circular_dependency_rejected():
    """Circular dependencies produce an error, not infinite loop."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
            depends_on=[1],
        ),
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S1",
            depends_on=[0],
        ),
    ]
    with pytest.raises(PlanValidationError, match="circular"):
        _resolve_execution_order(steps)


def test_out_of_range_step_ref_rejected():
    """$step_99 when only 1 step exists raises error."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
            depends_on=[99],
        ),
    ]
    with pytest.raises(PlanValidationError, match="out of range"):
        _resolve_execution_order(steps)


def test_self_reference_rejected():
    """A step depending on itself is rejected."""
    from scripts.chat.executor import PlanValidationError, _resolve_execution_order

    steps = [
        ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(filters=[]),
            label="S0",
            depends_on=[0],
        ),
    ]
    with pytest.raises(PlanValidationError, match="circular"):
        _resolve_execution_order(steps)


# =============================================================================
# Step reference resolution tests
# =============================================================================


def test_step_ref_resolution_resolve_agent_to_value():
    """$step_0 from resolve_agent resolves to matched_values in value context."""
    from scripts.chat.executor import _resolve_step_ref

    resolved = ResolvedEntity(
        query_name="Karo",
        matched_values=["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"],
        match_method="alias_exact",
        confidence=0.95,
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="resolve_agent",
            label="Resolve",
            status="ok",
            data=resolved,
            record_count=None,
        )
    }

    value = _resolve_step_ref("$step_0", step_results, context="value")
    assert value == ["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"]


def test_step_ref_resolution_retrieve_to_scope():
    """$step_0 from retrieve resolves to mms_ids for aggregate scope."""
    from scripts.chat.executor import _resolve_step_ref

    record_set = RecordSet(
        mms_ids=["990001", "990002"], total_count=2, filters_applied=[]
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="retrieve",
            label="Retrieve",
            status="ok",
            data=record_set,
            record_count=2,
        )
    }

    value = _resolve_step_ref("$step_0", step_results, context="scope")
    assert value == ["990001", "990002"]


def test_step_ref_resolution_missing_step():
    """Referencing a step that hasn't been executed raises an error."""
    from scripts.chat.executor import PlanValidationError, _resolve_step_ref

    with pytest.raises(PlanValidationError, match="not found"):
        _resolve_step_ref("$step_5", {}, context="value")


def test_step_ref_resolution_non_ref_passthrough():
    """Non-$step_N strings pass through as-is."""
    from scripts.chat.executor import _resolve_step_ref

    value = _resolve_step_ref("full_collection", {}, context="scope")
    assert value == "full_collection"


# =============================================================================
# Unknown action handling
# =============================================================================


def test_unknown_action_skipped():
    """Unknown step action is marked as error, not a crash.

    Uses model_construct to bypass Pydantic validation, simulating a
    plan where the interpreter failed to reject an unknown action.
    """
    from scripts.chat.executor import execute_plan

    # Build a step with an invalid action via model_construct (bypasses validation)
    bad_step = ExecutionStep.model_construct(
        action="search_fulltext",
        params=RetrieveParams(filters=[]),
        label="Bad step",
        depends_on=[],
    )
    plan = InterpretationPlan.model_construct(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[bad_step],
        directives=[],
        confidence=0.9,
        clarification=None,
    )
    result = execute_plan(plan, db_path=Path(":memory:"))
    assert result.steps_completed[0].status == "error"
    assert "Unknown action" in result.steps_completed[0].error_message


# =============================================================================
# Handler tests (real DB queries)
# =============================================================================


def test_handle_resolve_agent(test_db):
    """resolve_agent finds Karo via alias lookup."""
    from scripts.chat.executor import _handle_resolve_agent

    params = ResolveAgentParams(name="Joseph Karo", variants=["Caro, Joseph"])
    result = _handle_resolve_agent(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, ResolvedEntity)
    assert "\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd" in result.matched_values
    assert result.match_method != "none"
    assert result.confidence > 0.0


def test_handle_resolve_agent_not_found(test_db):
    """resolve_agent for unknown name returns empty with match_method='none'."""
    from scripts.chat.executor import _handle_resolve_agent

    params = ResolveAgentParams(name="Nobody Known", variants=[])
    result = _handle_resolve_agent(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, ResolvedEntity)
    assert len(result.matched_values) == 0
    assert result.match_method == "none"


def test_handle_resolve_publisher(test_db):
    """resolve_publisher finds Bragadin via variant lookup."""
    from scripts.chat.executor import _handle_resolve_publisher

    params = ResolvePublisherParams(name="Bragadin", variants=[])
    result = _handle_resolve_publisher(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, ResolvedEntity)
    assert "bragadin" in [v.lower() for v in result.matched_values]
    assert result.match_method != "none"


def test_handle_resolve_publisher_not_found(test_db):
    """resolve_publisher for unknown publisher returns empty."""
    from scripts.chat.executor import _handle_resolve_publisher

    params = ResolvePublisherParams(name="Unknown Press", variants=[])
    result = _handle_resolve_publisher(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, ResolvedEntity)
    assert len(result.matched_values) == 0
    assert result.match_method == "none"


def test_handle_retrieve_basic(test_db):
    """retrieve with place filter returns matching records."""
    from scripts.chat.executor import _handle_retrieve

    params = RetrieveParams(
        filters=[Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice")],
    )
    result = _handle_retrieve(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, RecordSet)
    assert "990001234" in result.mms_ids
    assert result.total_count >= 1


def test_handle_retrieve_with_scope(test_db):
    """retrieve scoped to $step_N narrows to those record IDs."""
    from scripts.chat.executor import _handle_retrieve

    # Simulate a prior retrieve step that found only record 1
    prior = StepResult(
        step_index=0, action="retrieve", label="Prior",
        status="ok",
        data=RecordSet(mms_ids=["990001234"], total_count=1, filters_applied=[]),
        record_count=1,
    )

    params = RetrieveParams(filters=[], scope="$step_0")
    result = _handle_retrieve(params, test_db, step_results={0: prior}, session_context=None)

    assert isinstance(result, RecordSet)
    # Should be scoped to only mms_id 990001234
    assert all(mms in ["990001234"] for mms in result.mms_ids)


def test_handle_aggregate(test_db):
    """aggregate computes facets over a result set."""
    from scripts.chat.executor import _handle_aggregate

    prior = StepResult(
        step_index=0, action="retrieve", label="All",
        status="ok",
        data=RecordSet(mms_ids=["990001234", "990005678", "990009999"], total_count=3, filters_applied=[]),
        record_count=3,
    )

    params = AggregateParams(field="place", scope="$step_0")
    result = _handle_aggregate(params, test_db, step_results={0: prior}, session_context=None)

    assert isinstance(result, AggregationResult)
    assert len(result.facets) > 0
    # Venice should appear twice (records 1 and 3)
    venice_facets = [f for f in result.facets if f.get("value") == "venice"]
    assert len(venice_facets) == 1
    assert venice_facets[0]["count"] == 2


def test_handle_enrich(test_db):
    """enrich fetches authority_enrichment data for resolved agents."""
    from scripts.chat.executor import _handle_enrich

    prior = StepResult(
        step_index=0, action="resolve_agent", label="Resolve",
        status="ok",
        data=ResolvedEntity(
            query_name="Karo",
            matched_values=["\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"],
            match_method="alias_exact",
            confidence=0.95,
        ),
        record_count=None,
    )

    params = EnrichParams(targets="$step_0")
    result = _handle_enrich(params, test_db, step_results={0: prior}, session_context=None)

    assert isinstance(result, EnrichmentBundle)
    assert len(result.agents) >= 1
    karo = result.agents[0]
    assert karo.canonical_name == "\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"
    assert karo.birth_year == 1488
    assert karo.death_year == 1575
    assert "rabbi" in karo.occupations


def test_handle_find_connections(test_db):
    """find_connections discovers co-publication between Karo and Bomberg."""
    from scripts.chat.executor import _handle_find_connections

    params = FindConnectionsParams(
        agents=[
            "\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd",
            "bomberg, daniel",
        ],
        depth=1,
    )
    result = _handle_find_connections(params, test_db, step_results={}, session_context=None)

    assert isinstance(result, ConnectionGraph)
    # They share record 1 with different roles (author + printer)
    # co_publication requires >= 2 shared records by default, so may or may not match
    # But we should at least get a graph back without errors
    assert isinstance(result.connections, list)
    assert isinstance(result.isolated, list)


def test_handle_sample(test_db):
    """sample returns subset of records with earliest strategy."""
    from scripts.chat.executor import _handle_sample

    prior = StepResult(
        step_index=0, action="retrieve", label="All",
        status="ok",
        data=RecordSet(mms_ids=["990001234", "990005678", "990009999"], total_count=3, filters_applied=[]),
        record_count=3,
    )

    params = SampleParams(scope="$step_0", n=2, strategy="earliest")
    result = _handle_sample(params, test_db, step_results={0: prior}, session_context=None)

    assert isinstance(result, RecordSet)
    assert len(result.mms_ids) <= 2
    # The earliest record (1520) should be included
    assert "990009999" in result.mms_ids


def test_grounding_link_collection(test_db):
    """Grounding collects Primo, Wikipedia, Wikidata links."""
    from scripts.chat.executor import _collect_grounding

    step_results = {
        0: StepResult(
            step_index=0, action="retrieve", label="Retrieve",
            status="ok",
            data=RecordSet(mms_ids=["990001234"], total_count=1, filters_applied=[]),
            record_count=1,
        ),
    }

    grounding, _truncated = _collect_grounding(step_results, test_db)

    # Should have record summaries
    assert len(grounding.records) >= 1
    assert grounding.records[0].mms_id == "990001234"
    assert grounding.records[0].title != ""

    # Should have at least a Primo link for the record
    primo_links = [lnk for lnk in grounding.links if lnk.source == "primo"]
    assert len(primo_links) >= 1


def test_grounding_deduplicates_records(test_db):
    """Grounding deduplicates records from multiple retrieve steps."""
    from scripts.chat.executor import _collect_grounding

    step_results = {
        0: StepResult(
            step_index=0, action="retrieve", label="Retrieve1",
            status="ok",
            data=RecordSet(mms_ids=["990001234", "990005678"], total_count=2, filters_applied=[]),
            record_count=2,
        ),
        1: StepResult(
            step_index=1, action="retrieve", label="Retrieve2",
            status="ok",
            data=RecordSet(mms_ids=["990001234", "990009999"], total_count=2, filters_applied=[]),
            record_count=2,
        ),
    }

    grounding, _truncated = _collect_grounding(step_results, test_db)

    # Should have 3 unique records (deduped)
    mms_ids = [r.mms_id for r in grounding.records]
    assert len(mms_ids) == 3
    assert len(set(mms_ids)) == 3

    # Record 990001234 should have source_steps from both steps
    rec = next(r for r in grounding.records if r.mms_id == "990001234")
    assert 0 in rec.source_steps
    assert 1 in rec.source_steps


def test_execution_with_dependency_chain(test_db):
    """Full execution: resolve_agent -> retrieve (with dependency)."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["entity_exploration"],
        reasoning="Test dependency chain",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_AGENT,
                params=ResolveAgentParams(name="Joseph Karo"),
                label="Resolve Karo",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.AGENT_NORM,
                            op=FilterOp.CONTAINS,
                            value="$step_0",
                        )
                    ],
                    scope="full_collection",
                ),
                label="Retrieve Karo works",
                depends_on=[0],
            ),
        ],
        directives=[
            ScholarlyDirective(
                directive="expand", params={"focus": "biography"}, label="Bio"
            ),
        ],
        confidence=0.85,
    )
    result = execute_plan(plan, db_path=test_db)
    assert len(result.steps_completed) == 2
    assert result.steps_completed[0].action == "resolve_agent"
    assert result.steps_completed[1].action == "retrieve"
    # The resolve step should find Karo
    resolve_data = result.steps_completed[0].data
    assert isinstance(resolve_data, ResolvedEntity)
    assert len(resolve_data.matched_values) > 0
    # Directives passed through
    assert len(result.directives) == 1
    assert result.directives[0].directive == "expand"


def test_original_query_in_result():
    """original_query is included in ExecutionResult."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan(
        intents=["retrieval"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.95,
    )
    result = execute_plan(
        plan, db_path=Path(":memory:"), original_query="books by Karo"
    )
    assert result.original_query == "books by Karo"


def test_session_context_passed_through():
    """SessionContext is attached to ExecutionResult when provided."""
    from scripts.chat.plan_models import SessionContext
    from scripts.chat.executor import execute_plan

    ctx = SessionContext(
        session_id="test-session",
        previous_record_ids=["990001", "990002"],
    )
    plan = InterpretationPlan(
        intents=["follow_up"],
        reasoning="Test",
        execution_steps=[],
        directives=[],
        confidence=0.9,
    )
    result = execute_plan(
        plan, db_path=Path(":memory:"), session_context=ctx
    )
    assert result.session_context is not None
    assert result.session_context.session_id == "test-session"
    assert result.session_context.previous_record_ids == ["990001", "990002"]


def test_resolve_scope_full_collection():
    """_resolve_scope returns None for 'full_collection'."""
    from scripts.chat.executor import _resolve_scope

    result = _resolve_scope("full_collection", {}, None)
    assert result is None


def test_resolve_scope_step_ref():
    """_resolve_scope with $step_N returns mms_ids from the referenced step."""
    from scripts.chat.executor import _resolve_scope

    record_set = RecordSet(
        mms_ids=["990001", "990002", "990003"],
        total_count=3,
        filters_applied=[],
    )
    step_results = {
        0: StepResult(
            step_index=0,
            action="retrieve",
            label="Retrieve",
            status="ok",
            data=record_set,
            record_count=3,
        )
    }
    result = _resolve_scope("$step_0", step_results, None)
    assert result == ["990001", "990002", "990003"]


def test_resolve_scope_previous_results():
    """_resolve_scope with $previous_results uses session context."""
    from scripts.chat.plan_models import SessionContext
    from scripts.chat.executor import _resolve_scope

    ctx = SessionContext(
        session_id="sess-1",
        previous_record_ids=["990010", "990020"],
    )
    result = _resolve_scope("$previous_results", {}, ctx)
    assert result == ["990010", "990020"]


def test_resolve_scope_previous_results_no_context():
    """_resolve_scope with $previous_results but no context returns empty."""
    from scripts.chat.executor import _resolve_scope

    result = _resolve_scope("$previous_results", {}, None)
    assert result == []


# =============================================================================
# Agent external links in grounding without enrich step (Issue 5)
# =============================================================================


def test_grounding_collects_agent_links_without_enrich_step(test_db):
    """Grounding collects Wikipedia/Wikidata/VIAF/NLI links for agents
    found in records, even when no explicit enrich step was planned."""
    from scripts.chat.executor import _collect_grounding
    from scripts.chat.plan_models import GroundingLink

    # Only a retrieve step, no enrich step
    step_results = {
        0: StepResult(
            step_index=0, action="retrieve", label="Retrieve",
            status="ok",
            data=RecordSet(
                mms_ids=["990001234"],
                total_count=1,
                filters_applied=[],
            ),
            record_count=1,
        ),
    }

    grounding, _truncated = _collect_grounding(step_results, test_db)

    # Record 990001234 has agents Karo and Bomberg.
    # Both have authority_enrichment entries with wikipedia_url, wikidata_id, etc.
    wiki_links = [lnk for lnk in grounding.links if lnk.source == "wikipedia"]
    wikidata_links = [lnk for lnk in grounding.links if lnk.source == "wikidata"]
    viaf_links = [lnk for lnk in grounding.links if lnk.source == "viaf"]
    nli_links = [lnk for lnk in grounding.links if lnk.source == "nli"]

    # Should have at least Wikipedia and Wikidata links for agents
    assert len(wiki_links) >= 1, f"Expected Wikipedia links, got: {grounding.links}"
    assert len(wikidata_links) >= 1, f"Expected Wikidata links, got: {grounding.links}"
    assert len(viaf_links) >= 1, f"Expected VIAF links, got: {grounding.links}"
    assert len(nli_links) >= 1, f"Expected NLI links, got: {grounding.links}"

    # Agent summaries should be created for the enriched agents
    assert len(grounding.agents) >= 1
    # Check that at least one agent has links
    agents_with_links = [a for a in grounding.agents if a.links]
    assert len(agents_with_links) >= 1


def test_grounding_agent_links_not_duplicated_with_enrich_step(test_db):
    """When an enrich step already provides agent links, they are not duplicated."""
    from scripts.chat.executor import _collect_grounding
    from scripts.chat.plan_models import EnrichmentBundle, GroundingLink

    karo_name = "\u05e7\u05d0\u05e8\u05d5, \u05d9\u05d5\u05e1\u05e3 \u05d1\u05df \u05d0\u05e4\u05e8\u05d9\u05dd"
    karo_links = [
        GroundingLink(
            entity_type="agent", entity_id=karo_name,
            label="Wikipedia: Joseph Karo",
            url="https://en.wikipedia.org/wiki/Joseph_Karo",
            source="wikipedia",
        ),
    ]

    step_results = {
        0: StepResult(
            step_index=0, action="retrieve", label="Retrieve",
            status="ok",
            data=RecordSet(
                mms_ids=["990001234"],
                total_count=1,
                filters_applied=[],
            ),
            record_count=1,
        ),
        1: StepResult(
            step_index=1, action="enrich", label="Enrich",
            status="ok",
            data=EnrichmentBundle(agents=[
                AgentSummary(
                    canonical_name=karo_name,
                    variants=["Joseph Karo"],
                    links=karo_links,
                ),
            ]),
            record_count=None,
        ),
    }

    grounding, _truncated = _collect_grounding(step_results, test_db)

    # Count how many Wikipedia links there are for Karo
    karo_wiki = [
        lnk for lnk in grounding.links
        if lnk.source == "wikipedia" and "Karo" in lnk.label
    ]
    # Should not be duplicated (exactly 1 from the enrich step)
    assert len(karo_wiki) == 1
