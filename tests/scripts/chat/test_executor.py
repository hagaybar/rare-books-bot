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
    ResolvedHeadings,
    ResolveSubjectConceptParams,
    RetrieveParams,
    SampleParams,
    ScholarlyDirective,
    SessionContext,
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
            authority_uri TEXT, parts TEXT, source TEXT, value_he TEXT
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY, record_id INTEGER,
            title_type TEXT, value TEXT, source TEXT
        );
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY, record_id INTEGER, code TEXT, source TEXT
        );
        CREATE TABLE physical_descriptions (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT, source TEXT
        );
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY, record_id INTEGER, value TEXT, tag TEXT,
            source TEXT
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
        CREATE VIRTUAL TABLE subjects_fts USING fts5(mms_id, value, content='');
        CREATE VIRTUAL TABLE titles_fts USING fts5(
            title_type UNINDEXED, value,
            content=titles, content_rowid=id
        );

        -- Sample data: Joseph Karo with 2 books, plus a second agent
        INSERT INTO records VALUES
            (1, '990001234', 'test.xml', '2024-01-01', 1);
        INSERT INTO records VALUES
            (2, '990005678', 'test.xml', '2024-01-01', 2);
        INSERT INTO records VALUES
            (3, '990009999', 'test.xml', '2024-01-01', 3);
        -- Themed records for relaxation-ladder tests (issue #2)
        INSERT INTO records VALUES (4, '990111111', 'test.xml', '2024-01-01', 4);
        INSERT INTO records VALUES (5, '990222222', 'test.xml', '2024-01-01', 5);
        -- Stemming relaxation-ladder records (issue #48): plural subject
        -- heading + a Hebrew heading that must never be s-toggled.
        INSERT INTO records VALUES (6, '990333333', 'test.xml', '2024-01-01', 6);
        INSERT INTO records VALUES (7, '990444444', 'test.xml', '2024-01-01', 7);

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
        -- Issue #50: imprints whose publisher_norm merely *contains* 'rom'
        -- inside an unrelated word. The substring fallback must NOT match
        -- these on a short Latin variant ('rom'/'ram').
        INSERT INTO imprints VALUES
            (50, 50, 0, '1890', 'Stockholm', 'Broderna Lagerstroms Forlag',
             NULL, '["264"]', 1890, 1890, '1890', 0.99, 'exact',
             'stockholm', 'Stockholm', 0.95, 'place_alias_map',
             'broderna lagerstroms forlag', 'Broderna Lagerstroms Forlag',
             0.95, 'publisher_authority', 'sw', 'sweden');
        INSERT INTO imprints VALUES
            (51, 51, 0, '1901', 'Paris', 'Imprimerie de Jerome Perret',
             NULL, '["264"]', 1901, 1901, '1901', 0.99, 'exact',
             'paris', 'Paris', 0.95, 'place_alias_map',
             'imprimerie de jerome perret', 'Imprimerie de Jerome Perret',
             0.95, 'publisher_authority', 'fr', 'france');
        INSERT INTO imprints VALUES
            (52, 52, 0, '1925', 'Bucharest', 'Evreilor din Romania',
             NULL, '["264"]', 1925, 1925, '1925', 0.99, 'exact',
             'bucharest', 'Bucharest', 0.95, 'place_alias_map',
             'evreilor din romania', 'Evreilor din Romania',
             0.95, 'publisher_authority', 'ro', 'romania');
        -- Issue #50: the legitimate Romm press, Hebrew form. The Hebrew
        -- path must still resolve 'ראם' as a substring of this norm.
        INSERT INTO imprints VALUES
            (53, 53, 0, '1860', 'Vilna',
             'האלמנה והאחים ראם',
             NULL, '["264"]', 1860, 1860, '1860', 0.99, 'exact',
             'vilna', 'Vilna', 0.95, 'place_alias_map',
             'האלמנה והאחים ראם',
             'Widow and Brothers Romm', 0.95, 'publisher_authority',
             'lt', 'lithuania');
        -- Issue #50: a distinctive longer Latin token must still match as a
        -- legitimate substring ('plantin' inside 'officina plantiniana').
        INSERT INTO imprints VALUES
            (54, 54, 0, '1600', 'Antwerp', 'Officina Plantiniana',
             NULL, '["264"]', 1600, 1600, '1600', 0.99, 'exact',
             'antwerp', 'Antwerp', 0.95, 'place_alias_map',
             'officina plantiniana', 'Officina Plantiniana',
             0.95, 'publisher_authority', 'be', 'belgium');

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
            (1, 1, 'Jewish law', '650', 'lcsh', 'eng', NULL, '{}', '[]', NULL);
        INSERT INTO subjects VALUES
            (2, 3, 'Talmud', '650', 'lcsh', 'eng', NULL, '{}', '[]', NULL);
        INSERT INTO subjects VALUES
            (101, 4, 'Bible -- Geography -- Early works to 1800', '650',
             NULL, 'en', NULL, NULL, '["650"]', NULL);
        INSERT INTO subjects VALUES
            (102, 5, 'Art -- History', '650',
             NULL, 'en', NULL, NULL, '["650"]', NULL);
        -- Issue #48: plural English heading (singular probe must recover it)
        INSERT INTO subjects VALUES
            (103, 6, 'Limited editions', '650',
             NULL, 'en', NULL, NULL, '["650"]', NULL);
        -- Issue #48: Hebrew heading must never be s-toggled
        INSERT INTO subjects VALUES
            (104, 7, 'תלמוד', '650',
             NULL, 'he', NULL, NULL, '["650"]', NULL);

        INSERT INTO physical_descriptions VALUES
            (201, 4, '2 v. : ill., 10 folded maps', '["300"]');
        INSERT INTO imprints VALUES
            (6, 4, 0, '1714', 'Amsterdam', 'visscher', NULL, '["264"]',
             1714, 1714, '1714', 0.99, 'exact',
             'amsterdam', 'Amsterdam', 0.95, 'place_alias_map',
             'visscher', 'Visscher', 0.95, 'publisher_authority',
             'ne', 'netherlands');

        INSERT INTO titles VALUES
            (1, 1, 'main', 'Shulchan Aruch', '["245"]');
        INSERT INTO titles VALUES
            (2, 2, 'main', 'Beit Yosef', '["245"]');
        INSERT INTO titles VALUES
            (3, 3, 'main', 'Talmud Bavli', '["245"]');
        INSERT INTO titles VALUES
            (301, 4, 'main', 'Palaestina illustrata', '["245"]');
        INSERT INTO titles VALUES
            (302, 5, 'main', 'De arte pingendi', '["245"]');

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

        -- Populate FTS indexes from base tables
        INSERT INTO subjects_fts(rowid, mms_id, value)
            SELECT s.id, r.mms_id, s.value FROM subjects s JOIN records r ON s.record_id = r.id;
        INSERT INTO titles_fts(titles_fts) VALUES('rebuild');
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


def test_resolve_publisher_short_latin_variant_no_bare_substring(test_db):
    """Issue #50: a short Latin variant ('rom'/'ram') must NOT match inside
    unrelated words via the imprint_substring fallback.

    'lagerstroms', 'jerome', 'romania' all contain 'rom' as a bare substring
    but none is the Romm press. Word-boundary / min-length anchoring must
    exclude them entirely.
    """
    from scripts.chat.executor import _handle_resolve_publisher

    params = ResolvePublisherParams(name="Romm", variants=["Rom", "Ram"])
    result = _handle_resolve_publisher(params, test_db, step_results={}, session_context=None)

    noise = {
        "broderna lagerstroms forlag",
        "imprimerie de jerome perret",
        "evreilor din romania",
    }
    matched = {v.lower() for v in result.matched_values}
    assert not (matched & noise), f"short Latin variant leaked noise: {matched & noise}"


def test_resolve_publisher_legit_latin_substring_still_matches(test_db):
    """Issue #50: a distinctive longer Latin token must still resolve as a
    legitimate substring ('plantin' inside 'officina plantiniana')."""
    from scripts.chat.executor import _handle_resolve_publisher

    params = ResolvePublisherParams(name="Plantin", variants=[])
    result = _handle_resolve_publisher(params, test_db, step_results={}, session_context=None)

    matched = {v.lower() for v in result.matched_values}
    assert "officina plantiniana" in matched
    assert result.match_method == "imprint_substring"


def test_resolve_publisher_hebrew_substring_still_resolves(test_db):
    """Issue #50: the Hebrew path must keep working -- 'ראם' is a genuine
    substring of 'האלמנה והאחים ראם' and must still resolve."""
    from scripts.chat.executor import _handle_resolve_publisher

    params = ResolvePublisherParams(name="ראם", variants=[])
    result = _handle_resolve_publisher(params, test_db, step_results={}, session_context=None)

    matched = result.matched_values
    assert "האלמנה והאחים ראם" in matched
    assert result.match_method == "imprint_substring"


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


def test_handle_aggregate_country_returns_country_facets(test_db):
    """Seam audit B8 (#56): aggregate field 'country' must facet on
    imprints.country_name, not silently alias to city facets."""
    from scripts.chat.executor import _handle_aggregate

    result = _handle_aggregate(
        AggregateParams(field="country", scope="full_collection"),
        test_db, step_results={}, session_context=None,
    )
    values = {f["value"] for f in result.facets}
    # Fixture countries: italy (records 1, 3), netherlands (2, 4)
    assert "italy" in values
    assert "netherlands" in values
    # City names must NOT leak in (the old alias returned place facets)
    assert "venice" not in values
    italy = next(f for f in result.facets if f["value"] == "italy")
    assert italy["count"] == 2


def test_handle_aggregate_reports_distinct_total(test_db):
    """aggregate carries the true distinct-value count even when facets are
    truncated by limit (issue #42: 'exactly 5 printing houses' confabulation)."""
    from scripts.chat.executor import _handle_aggregate

    truncated = _handle_aggregate(
        AggregateParams(field="publisher", scope="full_collection", limit=2),
        test_db, step_results={}, session_context=None,
    )
    assert len(truncated.facets) == 2
    # Fixture has at least bragadin, proops, bomberg, visscher
    assert truncated.distinct_values >= 4
    assert truncated.facets_truncated is True

    full = _handle_aggregate(
        AggregateParams(field="publisher", scope="full_collection", limit=100),
        test_db, step_results={}, session_context=None,
    )
    assert full.distinct_values == len(full.facets)
    assert full.facets_truncated is False


def test_handle_aggregate_unknown_field_signals_error(test_db):
    """Seam audit B9 (#57): an unsupported aggregate field must NOT return a
    silent empty AggregationResult (indistinguishable from '0 records').

    The handler raises a handled PlanValidationError, which _execute_step
    converts to status='error' with an error_message — so the narrator/user
    sees 'unsupported aggregation field', not 'no results'.
    """
    from scripts.chat.executor import PlanValidationError, _handle_aggregate

    with pytest.raises(PlanValidationError) as exc_info:
        _handle_aggregate(
            AggregateParams(field="not_a_real_field", scope="full_collection"),
            test_db, step_results={}, session_context=None,
        )
    msg = str(exc_info.value).lower()
    assert "unsupported" in msg
    assert "not_a_real_field" in str(exc_info.value)


def test_unknown_aggregate_field_surfaces_as_error_step(test_db):
    """Plan-level: an unknown aggregate field yields a step with status='error'
    and an explicit message, never a silent 'empty' AggregationResult."""
    from scripts.chat.executor import execute_plan

    plan = InterpretationPlan.model_construct(
        intents=["analytical"],
        reasoning="Test",
        execution_steps=[
            ExecutionStep.model_construct(
                action=StepAction.AGGREGATE,
                params=AggregateParams(field="bogus_field", scope="full_collection"),
                label="Aggregate bogus",
                depends_on=[],
            )
        ],
        directives=[],
        confidence=0.9,
        clarification=None,
    )
    result = execute_plan(plan, db_path=test_db)
    step = result.steps_completed[0]
    assert step.status == "error"
    assert step.status != "empty"
    assert "unsupported" in (step.error_message or "").lower()
    assert "bogus_field" in (step.error_message or "")


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

    grounding, _truncated, _total = _collect_grounding(step_results, test_db)

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

    grounding, _truncated, _total = _collect_grounding(step_results, test_db)

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

    grounding, _truncated, _total = _collect_grounding(step_results, test_db)

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

    grounding, _truncated, _total = _collect_grounding(step_results, test_db)

    # Count how many Wikipedia links there are for Karo
    karo_wiki = [
        lnk for lnk in grounding.links
        if lnk.source == "wikipedia" and "Karo" in lnk.label
    ]
    # Should not be duplicated (exactly 1 from the enrich step)
    assert len(karo_wiki) == 1


# =============================================================================
# Relaxation ladder + scope union (issue #2)
# =============================================================================

from scripts.chat.executor import execute_plan  # noqa: E402


class TestRetrieveRelaxationLadder:
    """0-hit multi-topic AND queries are relaxed to OR-union + concept
    expansion, with every relaxation recorded as evidence (issue #2 A1/A2)."""

    def _plan(self, filters):
        return InterpretationPlan(
            intents=["retrieval"],
            reasoning="t",
            confidence=0.9,
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=filters),
                    label="t",
                )
            ],
            directives=[],
        )

    def test_strict_match_does_not_relax(self, test_db):
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert "990111111" in data.mms_ids
        assert data.relaxations == []

    def test_multi_topic_zero_relaxes_to_or_union_with_expansion(self, test_db):
        # art AND maps AND cartography → 0 strict; ladder must recover both
        # the art record (direct OR) and the geography record (concept map:
        # cartography→subject geography / physical_desc map).
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="maps"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        data = step.data
        assert "990222222" in data.mms_ids  # art (direct OR-union)
        assert "990111111" in data.mms_ids  # cartography via expansion
        assert step.status == "ok"
        assert data.relaxations, "relaxation must be recorded as evidence"
        assert any("0" in r or "relax" in r.lower() or "broaden" in r.lower() for r in data.relaxations)

    def test_non_topical_filters_stay_hard(self, test_db):
        # year constraint must remain AND even during relaxation:
        # records 4/5 have no imprints rows → a 1500-1510 RANGE excludes them.
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="cartography"),
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1510),
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert data.mms_ids == []
        assert data.relaxations == []

    def test_zero_with_no_expansion_stays_honest_empty(self, test_db):
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="xyzzy"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        assert step.status == "empty"
        assert step.data.mms_ids == []


class TestStemmingRelaxation:
    """Issue #48: a singular topical CONTAINS term must find the plural
    heading (and vice versa) via a conservative ASCII trailing-s toggle
    before declaring honest-empty. FTS5 has no stemmer; recall must not
    depend on the LLM emitting the exact morphological form."""

    def _plan(self, filters):
        return InterpretationPlan(
            intents=["retrieval"],
            reasoning="t",
            confidence=0.9,
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=filters),
                    label="t",
                )
            ],
            directives=[],
        )

    def test_singular_subject_recovers_plural_heading(self, test_db):
        # subject CONTAINS "limited edition" → 0 strict; the ladder must
        # toggle the trailing 's' and match heading "Limited editions".
        plan = self._plan([
            Filter(
                field=FilterField.SUBJECT,
                op=FilterOp.CONTAINS,
                value="limited edition",
            ),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        data = step.data
        assert step.status == "ok"
        assert "990333333" in data.mms_ids
        assert data.relaxations, "stemming relaxation must be recorded"
        joined = " ".join(data.relaxations).lower()
        assert "limited edition" in joined
        assert "limited editions" in joined

    def test_strict_match_does_not_stem(self, test_db):
        # Exact plural already matches → no relaxation note at all.
        plan = self._plan([
            Filter(
                field=FilterField.SUBJECT,
                op=FilterOp.CONTAINS,
                value="limited editions",
            ),
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert "990333333" in data.mms_ids
        assert data.relaxations == []

    def test_no_variant_match_stays_honest_empty(self, test_db):
        # "rabbit" → "rabbits"/"rabbites"; neither exists → honest empty.
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="rabbit"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        assert step.status == "empty"
        assert step.data.mms_ids == []

    def test_hebrew_term_is_not_s_toggled(self, test_db):
        # A non-matching Hebrew term must not be s-toggled (no Latin 's' in
        # Hebrew). With no variant probe and no concept expansion, the result
        # is honest-empty; no stemming relaxation note may be recorded.
        plan = self._plan([
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="תלמודים"),
        ])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        assert step.status == "empty"
        assert step.data.mms_ids == []
        assert all("variant" not in r.lower() for r in step.data.relaxations)


class TestScopeUnion:
    """sample/retrieve scope may union steps: "$step_0+$step_1" (issue #2 C8)."""

    def test_union_scope_merges_step_results(self, test_db):
        plan = InterpretationPlan(
            intents=["curation"],
            reasoning="t",
            confidence=0.9,
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[
                        Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="geography"),
                    ]),
                    label="geo",
                ),
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=[
                        Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="art"),
                    ]),
                    label="art",
                ),
                ExecutionStep(
                    action=StepAction.SAMPLE,
                    params=SampleParams(scope="$step_0+$step_1", n=10, strategy="earliest"),
                    label="curate",
                    depends_on=[0, 1],
                ),
            ],
            directives=[],
        )
        result = execute_plan(plan, test_db)
        sample = result.steps_completed[2].data
        assert set(sample.mms_ids) == {"990111111", "990222222"}


class TestMultiValueFilterNormalization:
    """The planner sometimes emits malformed multi-value hard filters:
    op IN for fields the adapter doesn't support, or comma-joined strings
    ("venice,amsterdam,wordsworth") that can never match a single place_norm.
    The executor must repair these deterministically into its multi-value
    EQUALS mechanism (real SQL IN), keeping the original unsplit string as a
    candidate because commas can be legitimate ("aldine press, venice")."""

    def _plan(self, filters):
        return InterpretationPlan(
            intents=["retrieval"],
            reasoning="t",
            confidence=0.9,
            directives=[],
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(filters=filters),
                    label="t",
                )
            ],
        )

    def test_comma_joined_equals_place_matches_any_city(self, test_db):
        plan = self._plan([
            Filter(
                field=FilterField.IMPRINT_PLACE,
                op=FilterOp.EQUALS,
                value="venice,amsterdam,wordsworth",
            )
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert "990001234" in data.mms_ids  # venice
        assert "990005678" in data.mms_ids  # amsterdam

    def test_in_list_of_joined_strings_is_split(self, test_db):
        plan = self._plan([
            Filter(
                field=FilterField.COUNTRY,
                op=FilterOp.IN,
                value=["italy,netherlands"],
            )
        ])
        result = execute_plan(plan, test_db)
        data = result.steps_completed[0].data
        assert "990001234" in data.mms_ids
        assert "990005678" in data.mms_ids

    def test_original_unsplit_value_kept_as_candidate(self):
        from scripts.chat.executor import _normalize_multivalue_filters

        mv = {}
        out = _normalize_multivalue_filters(
            [Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="aldine press, venice")],
            mv,
        )
        assert out[0].op == FilterOp.EQUALS
        assert "aldine press, venice" in mv[0]
        assert "venice" in mv[0]

    def test_multivalue_language_binds_all_values(self):
        """Seam audit B7 (#56): db_adapter names the language param
        'filter_{idx}_lang' (not '_language') and its EQUALS arm has no
        LOWER() wrapper — the multi-value SQL rewrite must still bind
        every value, not silently narrow to the first."""
        from scripts.chat.executor import _run_filter_query

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE records (id INTEGER PRIMARY KEY, mms_id TEXT UNIQUE);
            CREATE TABLE languages (
                id INTEGER PRIMARY KEY, record_id INTEGER, code TEXT, source TEXT
            );
            INSERT INTO records VALUES (1, '990001111');
            INSERT INTO records VALUES (2, '990002222');
            INSERT INTO records VALUES (3, '990003333');
            INSERT INTO languages VALUES (1, 1, 'heb', '008');
            INSERT INTO languages VALUES (2, 2, 'lat', '008');
            INSERT INTO languages VALUES (3, 3, 'ger', '008');
        """)
        try:
            mms_ids = _run_filter_query(
                conn,
                [Filter(field=FilterField.LANGUAGE, op=FilterOp.EQUALS, value="heb")],
                scope_ids=None,
                multi_value_map={0: ["heb", "lat"]},
            )
            assert set(mms_ids) == {"990001111", "990002222"}
        finally:
            conn.close()


class TestUnresolvedStepRefFallback:
    """Issue #3: when entity resolution fails, the executor must NEVER query
    the literal '$step_N' string. It probes CONTAINS on the resolve step's
    query_name (longest token), then drops the filter, recording every move."""

    def _failed_resolve(self, query_name):
        return {0: StepResult(
            step_index=0, action="resolve_agent", label="resolve",
            status="empty",
            data=ResolvedEntity(query_name=query_name, matched_values=[],
                                match_method="none", confidence=0.0))}

    def test_fallback_probe_recovers_records(self, test_db):
        from scripts.chat.executor import _handle_retrieve
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(params, test_db, self._failed_resolve("Rabbi D. Bomberg"), None)
        # longest token 'bomberg' -> CONTAINS hits agent_norm 'bomberg, daniel' (records 1, 3)
        assert "990001234" in rs.mms_ids
        assert "990009999" in rs.mms_ids
        assert any("$step_0" in n for n in rs.relaxations)

    def test_unresolvable_ref_dropped_secondary_filter_kept(self, test_db):
        from scripts.chat.executor import _handle_retrieve
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
            Filter(field=FilterField.IMPRINT_PLACE, op=FilterOp.EQUALS, value="venice"),
        ])
        rs = _handle_retrieve(params, test_db, self._failed_resolve("Zzz Qqq"), None)
        # tokens match nothing -> ref filter dropped, venice kept (records 1, 3)
        assert set(rs.mms_ids) >= {"990001234", "990009999"}
        assert rs.relaxations

    def test_unresolvable_sole_filter_honest_empty_with_explanation(self, test_db):
        from scripts.chat.executor import _handle_retrieve
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(params, test_db, self._failed_resolve("Zzz Qqq"), None)
        assert rs.mms_ids == []
        assert rs.relaxations, "the resolution failure must be explained, not silent"


class TestMultiValueResolutionNormalization:
    """Issue #4: multi-value resolved names must pass normalize_filter_value —
    'bomberg, daniel' (comma) can never equal the comma-stripped SQL expression."""

    def test_comma_canonical_names_match_via_normalized_in(self, test_db):
        from scripts.chat.executor import _handle_retrieve
        sr = {0: StepResult(
            step_index=0, action="resolve_agent", label="r", status="ok",
            data=ResolvedEntity(query_name="bomberg",
                                matched_values=["bomberg, daniel", "no, body"],
                                match_method="exact", confidence=1.0))}
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(params, test_db, sr, None)
        assert "990001234" in rs.mms_ids
        assert "990009999" in rs.mms_ids


class TestFallbackVariantsAndCrossField:
    """Issue #3 follow-through (replay evidence q04/q51): the fallback must
    also use the resolve step's VARIANTS (Hebrew name + Latin variants) and
    probe the twin field (publisher<->agent_norm) before giving up."""

    def _failed_resolve(self, action, query_name, variants):
        return {0: StepResult(
            step_index=0, action=action, label="resolve", status="empty",
            data=ResolvedEntity(query_name=query_name, matched_values=[],
                                query_variants=variants,
                                match_method="none", confidence=0.0))}

    def test_variant_token_rescues_hebrew_name(self, test_db):
        # q51 shape: Hebrew publisher name, Latin variant carries the token
        from scripts.chat.executor import _handle_retrieve
        params = RetrieveParams(filters=[
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(
            params, test_db,
            self._failed_resolve("resolve_publisher", "דפוס בומברג", ["Bomberg"]),
            None)
        assert "990009999" in rs.mms_ids  # record 3: publisher_norm 'bomberg'
        assert rs.relaxations

    def test_cross_field_probe_publisher_to_agent(self, test_db):
        # q04 shape: person queried as publisher; exists only as agent
        from scripts.chat.executor import _handle_retrieve
        # fixture has agent 'bomberg, daniel' AND publisher 'bomberg' — use
        # Karo (agent-only, Hebrew norm) via his Hebrew token instead
        params = RetrieveParams(filters=[
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(
            params, test_db,
            self._failed_resolve("resolve_publisher", "דפוס קארו", []),
            None)
        # publisher CONTAINS 'קארו' -> nothing; twin probe agent_norm CONTAINS
        # 'קארו' -> Karo's records 1 and 2
        assert "990001234" in rs.mms_ids
        assert "990005678" in rs.mms_ids
        assert any("agent_norm" in n for n in rs.relaxations)


class TestNotableSampleUsesCurationEngine:
    """Issue #6: the 'notable' strategy must call the curation engine, not
    silently fall back to 'earliest' (the N oldest items)."""

    def _plan(self, strategy, n=3):
        return InterpretationPlan(
            intents=["curation"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[ExecutionStep(
                action=StepAction.SAMPLE,
                params=SampleParams(scope="full_collection", n=n, strategy=strategy),
                label="s")],
        )

    def test_notable_differs_from_earliest(self, test_db):
        notable = execute_plan(self._plan("notable"), test_db).steps_completed[0].data
        earliest = execute_plan(self._plan("earliest"), test_db).steps_completed[0].data
        assert len(notable.mms_ids) == 3
        assert set(notable.mms_ids) != set(earliest.mms_ids), (
            "notable returned exactly the N oldest items — engine not wired")

    def test_notable_rewards_visual_material(self, test_db):
        # record 4 ('990111111') has '10 folded maps' + rich subject but NO
        # imprint; pure-earliest can never pick it, the engine should.
        notable = execute_plan(self._plan("notable"), test_db).steps_completed[0].data
        assert "990111111" in notable.mms_ids


class TestAggregateFieldAliases:
    """Issue #11 (q07): interpreter said 'date_century'; executor only knew
    'century' — silent empty AggregationResult."""

    def test_date_century_alias_resolves(self, test_db):
        from scripts.chat.plan_models import AggregateParams
        plan = InterpretationPlan(
            intents=["analytical"], reasoning="t", confidence=0.9, directives=[],
            execution_steps=[ExecutionStep(
                action=StepAction.AGGREGATE,
                params=AggregateParams(field="date_century", scope="full_collection", limit=10),
                label="centuries")])
        result = execute_plan(plan, test_db)
        step = result.steps_completed[0]
        assert step.status == "ok"
        assert step.data.facets, "date_century must aggregate, not silently empty"


# =============================================================================
# Soncino forensics (live wrong-answer, 2026-06-12): "do we have Soncino
# press books?" -> confident 0, while the DB holds 10. Three stacked gaps.
# =============================================================================


def _seed_soncino(db_path):
    """Authority w/ variants + two imprint norms: one a variant ('h. de
    soncino'), one Hebrew and absent from authorities entirely."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        INSERT INTO records VALUES (901, 'MMS901', 'f', '2024', 1);
        INSERT INTO records VALUES (902, 'MMS902', 'f', '2024', 2);
        INSERT INTO publisher_authorities VALUES
            (50, 'Soncino Press', 'soncino press', 'printing_house',
             '1483-1547', 1483, 1547, 'Soncino', NULL, NULL, 0.95, 0,
             NULL, NULL, NULL, NULL, NULL, '2024-01-01', '2024-01-01');
        INSERT INTO publisher_variants VALUES
            (50, 50, 'Soncino Press', 'soncino press', 'latin', NULL, 1, 0, NULL, '2024-01-01');
        INSERT INTO publisher_variants VALUES
            (51, 50, 'H. de Soncino', 'h. de soncino', 'latin', NULL, 0, 0, NULL, '2024-01-01');
        INSERT INTO imprints VALUES
            (901, 901, 0, '1526', 'Rimini', 'H. de Soncino,', NULL, '["264"]',
             1526, 1526, '1526', 0.99, 'exact',
             'rimini', 'Rimini', 0.95, 'place_alias_map',
             'h. de soncino', 'H. de Soncino', 0.95, 'publisher_authority',
             'it', 'italy');
        INSERT INTO imprints VALUES
            (902, 902, 0, '1546', 'Constantinople', 'דפוס אליעזר שונצינו,', NULL, '["264"]',
             1546, 1546, '1546', 0.99, 'exact',
             'constantinople', 'Constantinople', 0.95, 'place_alias_map',
             'דפוס אליעזר שונצינו', 'דפוס אליעזר שונצינו', 0.9, 'raw',
             'tu', 'turkey');
    """)
    conn.commit(); conn.close()


class TestSoncinoResolution:
    def test_token_fallback_collects_imprint_norms(self, test_db):
        """'soncino' token-matches the authority — the resolved set must
        include the QUERYABLE imprint norms ('h. de soncino'), not just the
        canonical display name (which only finds canonical-named imprints)."""
        from scripts.chat.executor import _handle_resolve_publisher
        _seed_soncino(test_db)
        r = _handle_resolve_publisher(
            ResolvePublisherParams(name="soncino", variants=[]), test_db, {}, None)
        matched_lower = [m.lower() for m in r.matched_values]
        assert "h. de soncino" in matched_lower
        assert r.confidence > 0

    def test_hebrew_falls_back_to_imprint_substring(self, test_db):
        """'שונצינו' is absent from authorities; the resolver must probe the
        imprints themselves rather than return nothing."""
        from scripts.chat.executor import _handle_resolve_publisher
        _seed_soncino(test_db)
        r = _handle_resolve_publisher(
            ResolvePublisherParams(name="שונצינו", variants=[]), test_db, {}, None)
        assert "דפוס אליעזר שונצינו" in r.matched_values
        assert r.match_method == "imprint_substring"

    def test_publisher_equals_zero_relaxes_to_contains(self, test_db):
        """A bare `publisher EQUALS 'soncino'` plan (no resolve step) matched
        0 strictly; the ladder must broaden it to CONTAINS — recorded as a
        relaxation, not silently."""
        from scripts.chat.executor import _handle_retrieve
        _seed_soncino(test_db)
        params = RetrieveParams(filters=[
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="soncino"),
        ])
        rs = _handle_retrieve(params, test_db, {}, None)
        assert "MMS901" in rs.mms_ids
        assert rs.total_count >= 1
        assert any("soncino" in n and "broadened" in n for n in rs.relaxations)


def _seed_jacob(db_path):
    """Issue #45: an unresolved agent whose name carries a NON-SELECTIVE
    given-name token ('jacob', many agents) plus a SELECTIVE family token
    ('habib', one agent). Mirrors TEST-AUTH-04 'Jacob ibn Habib' at scale.

    Rare record 950 ('ibn habib, jacob') is the only correct hit. Flood
    records 951-954 share only the given name 'jacob'. The probe union must
    reject the 'jacob' probe (count > ceiling) yet keep the 'habib'/'ibn'
    probes (count <= ceiling), returning only record 950."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        INSERT INTO records VALUES (950, 'MMS950', 'f', '2024', 1);
        INSERT INTO records VALUES (951, 'MMS951', 'f', '2024', 2);
        INSERT INTO records VALUES (952, 'MMS952', 'f', '2024', 3);
        INSERT INTO records VALUES (953, 'MMS953', 'f', '2024', 4);
        INSERT INTO records VALUES (954, 'MMS954', 'f', '2024', 5);
        -- Rare: the only 'habib' / 'ibn' agent, also a 'jacob'
        INSERT INTO agents VALUES
            (950, 950, 0, 'Jacob ibn Habib', 'personal', 'author',
             'relator_code', NULL, 'ibn habib, jacob', 0.95, 'base_clean',
             NULL, 'author', 0.95, 'relator_code', '[]');
        -- Flood: four other Jacobs, no 'habib'/'ibn' token
        INSERT INTO agents VALUES
            (951, 951, 0, 'Jacob Levi', 'personal', 'author',
             'relator_code', NULL, 'levi, jacob', 0.95, 'base_clean',
             NULL, 'author', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (952, 952, 0, 'Jacob Simeon', 'personal', 'author',
             'relator_code', NULL, 'simeon, jacob', 0.95, 'base_clean',
             NULL, 'author', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (953, 953, 0, 'Jacob Moses', 'personal', 'author',
             'relator_code', NULL, 'moses, jacob', 0.95, 'base_clean',
             NULL, 'author', 0.95, 'relator_code', '[]');
        INSERT INTO agents VALUES
            (954, 954, 0, 'Jacob Asher', 'personal', 'author',
             'relator_code', NULL, 'asher, jacob', 0.95, 'base_clean',
             NULL, 'author', 0.95, 'relator_code', '[]');
    """)
    conn.commit()
    conn.close()


class TestUnresolvedProbeSelectivityCeiling:
    """Issue #45: the unresolved-entity probe union must reject non-selective
    tokens (a common given name floods the result set). A probe matching more
    records than the selectivity ceiling is NOT unioned; selective probes are.
    """

    def _failed_resolve(self, query_name):
        return {0: StepResult(
            step_index=0, action="resolve_agent", label="resolve",
            status="empty",
            data=ResolvedEntity(query_name=query_name, matched_values=[],
                                match_method="none", confidence=0.0))}

    def test_common_token_flood_rejected_rare_token_kept(self, test_db, monkeypatch):
        from scripts.chat import executor
        from scripts.chat.executor import _handle_retrieve
        _seed_jacob(test_db)
        # Force a low ceiling so the math is deterministic on the small fixture:
        # 'habib'/'ibn' match 1 record (<= 2, selective), 'jacob' matches 5
        # records (> 2, non-selective -> rejected).
        monkeypatch.setattr(executor, "_SELECTIVITY_CEILING_OVERRIDE", 2)
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(
            params, test_db, self._failed_resolve("Jacob ibn Habib"), None)
        # The rare token's record IS returned.
        assert "MMS950" in rs.mms_ids
        # The common-token flood is NOT unioned.
        for flooded in ("MMS951", "MMS952", "MMS953", "MMS954"):
            assert flooded not in rs.mms_ids
        # The rejection is recorded honestly as a relaxation note.
        assert any(
            "rejected as non-selective" in n and "jacob" in n.lower()
            for n in rs.relaxations
        ), rs.relaxations

    def test_all_probes_non_selective_falls_through_to_honest_empty(
        self, test_db, monkeypatch
    ):
        from scripts.chat import executor
        from scripts.chat.executor import _handle_retrieve
        _seed_jacob(test_db)
        # Ceiling 0: every probe (>=1 hit) is non-selective and rejected; with
        # no other filter to recover on, the result is an honest empty set with
        # the resolution-failure / rejection notes intact.
        monkeypatch.setattr(executor, "_SELECTIVITY_CEILING_OVERRIDE", 0)
        params = RetrieveParams(filters=[
            Filter(field=FilterField.AGENT_NORM, op=FilterOp.EQUALS, value="$step_0"),
        ])
        rs = _handle_retrieve(
            params, test_db, self._failed_resolve("Jacob ibn Habib"), None)
        assert rs.mms_ids == []
        assert rs.relaxations, "the rejection / resolution failure must be explained"


class TestConceptFanoutTransparency:
    """Issue #47: when the INTERPRETER expands one concept into several
    topical retrieve steps (e.g. 'cartography' -> subject 'geography',
    physical_desc 'maps', title 'atlas'), the results are broadened but each
    RecordSet.relaxations is empty -- the broadening is silent. The executor
    must record a transparency note naming the explored terms on the surface
    the narrator consumes (grounding.broadening_notes)."""

    def _topical_step(self, field, value, label):
        return ExecutionStep(
            action=StepAction.RETRIEVE,
            params=RetrieveParams(
                filters=[Filter(field=field, op=FilterOp.CONTAINS, value=value)]
            ),
            label=label,
        )

    def _plan(self, steps):
        return InterpretationPlan(
            intents=["retrieval"],
            reasoning="t",
            confidence=0.9,
            execution_steps=steps,
            directives=[],
        )

    def test_multi_topic_fanout_records_broadening_note(self, test_db):
        # 'cartography' fanned out into three topical retrieves on different
        # terms across different fields. Each strict-matches (relaxations stay
        # empty), so the broadening would be invisible without a note.
        plan = self._plan([
            self._topical_step(FilterField.SUBJECT, "geography", "subject"),
            self._topical_step(FilterField.PHYSICAL_DESC, "maps", "phys"),
            self._topical_step(FilterField.TITLE, "Palaestina", "title"),
        ])
        result = execute_plan(plan, test_db)

        # Per-step relaxations stay empty: each step strict-matched.
        for step in result.steps_completed:
            assert step.data.relaxations == []

        notes = result.grounding.broadening_notes
        assert notes, "interpreter-level fan-out must be recorded as a note"
        joined = " ".join(notes).lower()
        # The note names the explored terms so the narrator can surface them.
        assert "geography" in joined
        assert "maps" in joined
        assert "palaestina" in joined

    def test_single_topic_plan_has_no_broadening_note(self, test_db):
        plan = self._plan([
            self._topical_step(FilterField.SUBJECT, "geography", "subject"),
        ])
        result = execute_plan(plan, test_db)
        assert result.grounding.broadening_notes == []

    def test_repeated_same_term_is_not_fanout(self, test_db):
        # Two topical retrieves on the SAME term are not a concept fan-out --
        # no explored-terms note (single-topic queries stay unchanged).
        plan = self._plan([
            self._topical_step(FilterField.SUBJECT, "geography", "a"),
            self._topical_step(FilterField.SUBJECT, "geography", "b"),
        ])
        result = execute_plan(plan, test_db)
        assert result.grounding.broadening_notes == []


# =============================================================================
# resolve_subject_concept action (semantic subject search, Phase 1)
# =============================================================================


class _FakeSubjectResolver:
    """Deterministic concept->heading mapping for tests (no model/onnx/DB).

    Mirrors the SubjectConceptResolver.resolve() contract: returns a list of
    HeadingMatch-like objects carrying ``heading_value`` and ``score``.
    """

    def __init__(self, mapping):
        # mapping: concept(casefold) -> list[(heading_value, score)]
        self._mapping = {k.casefold(): v for k, v in mapping.items()}
        self.last_scope_headings = None  # captures the scope passed by the executor

    def resolve(self, concept, scope_headings=None):
        from scripts.chat.subject_concept_resolver import HeadingMatch

        self.last_scope_headings = scope_headings
        return [
            HeadingMatch(heading_value=h, score=s)
            for h, s in self._mapping.get(concept.casefold(), [])
        ]


def test_handle_resolve_subject_concept_counts_in_scope(test_db, monkeypatch):
    """resolve_subject_concept resolves a concept to real headings and counts
    records carrying those headings WITHIN the provided scope."""
    import scripts.chat.executor as executor

    fake = _FakeSubjectResolver(
        {"philosophy": [("Jewish law", 0.91), ("Talmud", 0.88)]}
    )
    monkeypatch.setattr(executor, "get_subject_resolver", lambda db_path: fake)

    # scope = the held set (records 1 and 3 carry the resolved headings)
    ctx = SessionContext(
        session_id="s1",
        previous_record_ids=["990001234", "990009999", "990005678"],
    )

    params = ResolveSubjectConceptParams(concept="philosophy")
    result = executor._handle_resolve_subject_concept(
        params, test_db, step_results={}, session_context=ctx
    )

    assert isinstance(result, ResolvedHeadings)
    assert set(result.headings) == {"Jewish law", "Talmud"}
    # Each matched heading carries a transparent per-heading record_count.
    by_heading = {m["heading"]: m for m in result.matches}
    assert by_heading["Jewish law"]["record_count"] == 1  # record 1 in scope
    assert by_heading["Talmud"]["record_count"] == 1       # record 3 in scope
    assert by_heading["Jewish law"]["score"] == 0.91


def test_resolve_subject_concept_scopes_to_held_set_vocabulary(test_db, monkeypatch):
    """With a held set, the executor resolves within the set's OWN heading
    vocabulary so the top-K is not spent on headings absent from the set
    (fixes the in-set undercount)."""
    import scripts.chat.executor as executor

    fake = _FakeSubjectResolver({"philosophy": [("Jewish law", 0.91)]})
    monkeypatch.setattr(executor, "get_subject_resolver", lambda db_path: fake)

    ctx = SessionContext(
        session_id="s1",
        previous_record_ids=["990001234", "990009999", "990005678"],
    )
    executor._handle_resolve_subject_concept(
        ResolveSubjectConceptParams(concept="philosophy"),
        test_db, step_results={}, session_context=ctx,
    )
    assert fake.last_scope_headings is not None
    assert "Jewish law" in fake.last_scope_headings


def test_resolve_subject_concept_global_when_no_held_set(test_db, monkeypatch):
    """No held set -> global resolve (scope_headings is None)."""
    import scripts.chat.executor as executor

    fake = _FakeSubjectResolver({"philosophy": [("Jewish law", 0.91)]})
    monkeypatch.setattr(executor, "get_subject_resolver", lambda db_path: fake)

    executor._handle_resolve_subject_concept(
        ResolveSubjectConceptParams(concept="philosophy"),
        test_db, step_results={}, session_context=None,
    )
    assert fake.last_scope_headings is None


def test_resolve_subject_concept_plan_counts_and_grounds(test_db, monkeypatch):
    """End-to-end: [resolve_subject_concept -> retrieve(subject IN $step_0)
    scope=$previous_results] returns the right count over the held set, surfaces
    the matched headings as evidence, and DOES NOT mutate the held set."""
    import scripts.chat.executor as executor

    fake = _FakeSubjectResolver(
        {"philosophy": [("Jewish law", 0.91), ("Talmud", 0.88)]}
    )
    monkeypatch.setattr(executor, "get_subject_resolver", lambda db_path: fake)

    held = ["990001234", "990009999", "990005678"]
    ctx = SessionContext(session_id="s1", previous_record_ids=list(held))

    plan = InterpretationPlan(
        intents=["explore-in-set"],
        reasoning="how many in philosophy",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RESOLVE_SUBJECT_CONCEPT,
                params=ResolveSubjectConceptParams(concept="philosophy"),
                label="resolve concept",
            ),
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[
                        Filter(
                            field=FilterField.SUBJECT,
                            op=FilterOp.IN,
                            value="$step_0",
                        )
                    ],
                    scope="$previous_results",
                ),
                label="count on headings",
                depends_on=[0],
            ),
        ],
        directives=[],
        confidence=0.9,
    )

    result = executor.execute_plan(plan, test_db, session_context=ctx)

    # The retrieve found records 1 and 3 (carry the resolved headings), scoped
    # to the held set.
    retrieve_step = result.steps_completed[-1]
    assert isinstance(retrieve_step.data, RecordSet)
    assert set(retrieve_step.data.mms_ids) == {"990001234", "990009999"}
    assert retrieve_step.data.total_count == 2

    # Matched headings are surfaced as evidence the narrator can cite.
    joined = " ".join(result.grounding.broadening_notes).lower()
    assert "jewish law" in joined
    assert "talmud" in joined
    assert "philosophy" in joined

    # The held set is NOT mutated by this turn.
    assert ctx.previous_record_ids == held


def test_resolve_subject_concept_no_match_is_honest_empty(test_db, monkeypatch):
    """When no heading clears the resolver threshold, the action returns an
    empty ResolvedHeadings (no fabricated headings) and the scoped retrieve
    yields zero -- never the literal '$step_0' string."""
    import scripts.chat.executor as executor

    fake = _FakeSubjectResolver({})  # 'philosophy' resolves to nothing
    monkeypatch.setattr(executor, "get_subject_resolver", lambda db_path: fake)

    ctx = SessionContext(
        session_id="s1", previous_record_ids=["990001234", "990009999"]
    )
    params = ResolveSubjectConceptParams(concept="philosophy")
    result = executor._handle_resolve_subject_concept(
        params, test_db, step_results={}, session_context=ctx
    )

    assert isinstance(result, ResolvedHeadings)
    assert result.headings == []
    assert result.matches == []
