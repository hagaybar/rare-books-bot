"""Integration tests for the scholar pipeline in the API layer.

Tests the three-stage pipeline wired into /chat and /ws/chat.
Mocks LLM calls (interpret, narrate) but uses real (test) DB for executor.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.chat.plan_models import (
    ExecutionResult,
    ExecutionStep,
    GroundingData,
    InterpretationPlan,
    RecordSet,
    RetrieveParams,
    ScholarResponse,
    ScholarlyDirective,
    StepAction,
    StepResult,
)
from scripts.schemas.query_plan import Filter, FilterField, FilterOp
from tests.app.conftest import make_test_token


# =============================================================================
# Test DB setup — replicates the executor test fixture
# =============================================================================

_DB_SCHEMA = """
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
    CREATE TABLE physical_descriptions (
        id INTEGER PRIMARY KEY, record_id INTEGER,
        value TEXT, source TEXT
    );
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY, record_id INTEGER,
        tag TEXT, value TEXT, source TEXT
    );
"""

_SEED_DATA = """
    INSERT INTO records VALUES
        (1, '990001234', 'test.xml', '2024-01-01', 1);
    INSERT INTO records VALUES
        (2, '990005678', 'test.xml', '2024-01-01', 2);

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

    INSERT INTO titles VALUES
        (1, 1, 'main', 'Shulchan Aruch', '["245"]');
    INSERT INTO titles VALUES
        (2, 2, 'main', 'Beit Yosef', '["245"]');

    INSERT INTO languages VALUES (1, 1, 'heb', '008/35-37');
    INSERT INTO languages VALUES (2, 2, 'heb', '008/35-37');
"""


def _create_test_db(path: Path) -> None:
    """Create a minimal bibliographic SQLite database for testing."""
    conn = sqlite3.connect(path)
    conn.executescript(_DB_SCHEMA)
    conn.executescript(_SEED_DATA)
    conn.close()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bib_db(tmp_path):
    """Create and return path to a test bibliographic DB."""
    db_path = tmp_path / "bib.db"
    _create_test_db(db_path)
    return db_path


@pytest.fixture
def client(tmp_path, bib_db):
    """TestClient with mocked DB paths pointing to temp directories."""
    import app.api.main as main_module

    sessions_db = tmp_path / "sessions.db"
    enrichment_db = tmp_path / "enrichment" / "cache.db"

    with patch.dict("os.environ", {
        "SESSIONS_DB_PATH": str(sessions_db),
        "BIBLIOGRAPHIC_DB_PATH": str(bib_db),
        "ENRICHMENT_DB_PATH": str(enrichment_db),
    }):
        # Disable rate limiter to avoid 429s when tests share the app singleton
        main_module.limiter.enabled = False
        with TestClient(app, cookies={"access_token": make_test_token()}) as c:
            yield c
        main_module.limiter.enabled = True


# =============================================================================
# Helper: build mock plan and response
# =============================================================================


def _make_retrieval_plan(**overrides) -> InterpretationPlan:
    """Build a basic retrieval InterpretationPlan for mocking."""
    defaults = dict(
        intents=["retrieval"],
        reasoning="Looking for Venice books",
        execution_steps=[
            ExecutionStep(
                action=StepAction.RETRIEVE,
                params=RetrieveParams(
                    filters=[Filter(
                        field=FilterField.IMPRINT_PLACE,
                        op=FilterOp.EQUALS,
                        value="venice",
                    )],
                ),
                label="Venice books",
            ),
        ],
        directives=[],
        confidence=0.95,
        clarification=None,
    )
    defaults.update(overrides)
    return InterpretationPlan(**defaults)


def _make_narrator_response(**overrides) -> ScholarResponse:
    """Build a ScholarResponse for mocking the narrator."""
    defaults = dict(
        narrative="Found books from Venice.",
        suggested_followups=["Try Amsterdam", "Explore printers"],
        grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
        confidence=0.9,
        metadata={},
    )
    defaults.update(overrides)
    return ScholarResponse(**defaults)


# =============================================================================
# Tests
# =============================================================================


class TestChatPipelineBasic:
    """POST /chat routes through interpret -> execute -> narrate."""

    def test_chat_pipeline_basic(self, client):
        """Full pipeline: interpret produces a plan, executor runs SQL,
        narrator formats the response."""
        plan = _make_retrieval_plan()
        narrator_response = _make_narrator_response(
            narrative="Found 2 books from Venice in the collection."
        )

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp = client.post("/chat", json={"message": "books from Venice"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"] is not None
        assert "Venice" in data["response"]["message"]
        assert data["response"]["session_id"]  # session was created
        assert data["response"]["suggested_followups"]  # narrator followups passed through

    def test_chat_pipeline_maps_grounding_to_metadata(self, client):
        """ScholarResponse.grounding is placed in ChatResponse.metadata."""
        plan = _make_retrieval_plan()
        grounding = GroundingData(
            records=[], agents=[], aggregations={"place": [{"value": "venice", "count": 2}]}, links=[]
        )
        narrator_response = _make_narrator_response(grounding=grounding)

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp = client.post("/chat", json={"message": "books from Venice"})

        data = resp.json()
        assert data["success"] is True
        metadata = data["response"]["metadata"]
        assert "grounding" in metadata
        assert metadata["grounding"]["aggregations"]["place"][0]["value"] == "venice"

    def test_chat_pipeline_preserves_session(self, client):
        """Session is created on first call and reusable on second."""
        plan = _make_retrieval_plan()
        narrator_response = _make_narrator_response()

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp1 = client.post("/chat", json={"message": "books from Venice"})

        session_id = resp1.json()["response"]["session_id"]

        # Second request reuses session
        plan2 = _make_retrieval_plan(
            intents=["follow_up"],
            reasoning="Narrowing to 16th century",
        )
        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan2),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp2 = client.post("/chat", json={
                "message": "only 16th century",
                "session_id": session_id,
            })

        assert resp2.status_code == 200
        assert resp2.json()["response"]["session_id"] == session_id


class TestChatClarification:
    """Clarification plan skips executor and narrator."""

    def test_chat_clarification_shortcircuit(self, client):
        """Low-confidence plan with clarification skips executor/narrator."""
        plan = InterpretationPlan(
            intents=["entity_exploration"],
            reasoning="Ambiguous reference",
            execution_steps=[],
            directives=[],
            confidence=0.55,
            clarification="Which Karo do you mean? Joseph Karo the halakhist or another?",
        )

        with patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan):
            resp = client.post("/chat", json={"message": "tell me about Karo"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["response"]["clarification_needed"] is not None
        assert "Karo" in data["response"]["clarification_needed"]
        assert data["response"]["confidence"] == 0.55

    def test_high_confidence_clarification_still_executes(self, client):
        """If confidence >= 0.7, clarification is ignored and pipeline executes."""
        plan = InterpretationPlan(
            intents=["retrieval"],
            reasoning="Slight ambiguity but proceeding",
            execution_steps=[
                ExecutionStep(
                    action=StepAction.RETRIEVE,
                    params=RetrieveParams(
                        filters=[Filter(
                            field=FilterField.IMPRINT_PLACE,
                            op=FilterOp.EQUALS,
                            value="venice",
                        )],
                    ),
                    label="Venice books",
                ),
            ],
            directives=[],
            confidence=0.85,
            clarification="Minor ambiguity noted",
        )
        narrator_response = _make_narrator_response()

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp = client.post("/chat", json={"message": "books from Venice"})

        data = resp.json()
        assert data["success"] is True
        # Should have gone through the full pipeline (narrator was called)
        assert "Found books from Venice" in data["response"]["message"]


class TestChatOutOfScope:
    """Out-of-scope query returns polite redirect."""

    def test_chat_out_of_scope(self, client):
        """Out-of-scope intent goes through narrator which returns a redirect."""
        plan = InterpretationPlan(
            intents=["out_of_scope"],
            reasoning="Not bibliographic",
            execution_steps=[],
            directives=[],
            confidence=0.99,
        )
        narrator_response = ScholarResponse(
            narrative="I'm a specialist in rare books and Hebrew printing history. "
                      "I can't help with weather, but I'd be happy to help you "
                      "explore the collection!",
            suggested_followups=["What's in this collection?", "Show me incunabula"],
            grounding=GroundingData(records=[], agents=[], aggregations={}, links=[]),
            confidence=0.99,
            metadata={},
        )

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock, return_value=narrator_response),
        ):
            resp = client.post("/chat", json={"message": "what's the weather?"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "rare books" in data["response"]["message"].lower()


class TestChatErrorHandling:
    """Error scenarios for the scholar pipeline."""

    def test_interpret_failure_returns_error(self, client):
        """If interpret() raises, the endpoint returns a graceful error."""
        with patch("app.api.main.interpret", new_callable=AsyncMock,
                    side_effect=RuntimeError("LLM call failed")):
            resp = client.post("/chat", json={"message": "books from Venice"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["error"] is not None

    def test_narrate_failure_still_returns(self, client):
        """If narrate() raises, the endpoint returns a graceful error."""
        plan = _make_retrieval_plan()

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate", new_callable=AsyncMock,
                  side_effect=RuntimeError("Narrator failed")),
        ):
            resp = client.post("/chat", json={"message": "books from Venice"})

        # Should still return -- error is caught at the outer level
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False


class TestWebSocketPipeline:
    """WebSocket handler routes through the three-stage pipeline."""

    def test_ws_basic_pipeline(self, client):
        """WebSocket streams thinking + stream_chunk + complete through the pipeline."""
        plan = _make_retrieval_plan()
        narrator_response = _make_narrator_response(
            narrative="Found Venice books via WebSocket."
        )

        async def _fake_narrate_streaming(query, execution_result, *, chunk_callback=None, token_saving=True):
            if chunk_callback:
                await chunk_callback("Found Venice books via WebSocket.")
            return narrator_response

        with (
            patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan),
            patch("app.api.main.narrate_streaming", new_callable=AsyncMock, side_effect=_fake_narrate_streaming),
        ):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_json({"message": "books from Venice"})

                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("complete", "error"):
                        break

        # Should have thinking messages and a complete message
        types = [m["type"] for m in messages]
        assert "session_created" in types
        assert "thinking" in types
        assert "complete" in types

        complete_msg = next(m for m in messages if m["type"] == "complete")
        assert "Venice" in complete_msg["response"]["message"]

    def test_ws_clarification_shortcircuit(self, client):
        """WebSocket returns clarification without executing or narrating."""
        plan = InterpretationPlan(
            intents=["entity_exploration"],
            reasoning="Ambiguous",
            execution_steps=[],
            directives=[],
            confidence=0.5,
            clarification="Could you be more specific?",
        )

        with patch("app.api.main.interpret", new_callable=AsyncMock, return_value=plan):
            with client.websocket_connect("/ws/chat") as ws:
                ws.send_json({"message": "tell me about it"})

                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg["type"] in ("complete", "error"):
                        break

        complete_msg = next(m for m in messages if m["type"] == "complete")
        assert complete_msg["response"]["clarification_needed"] is not None


class TestHealthCheck:
    """Health endpoint includes executor_ready check."""

    def test_health_includes_executor_ready(self, client):
        """Health check reports executor_ready based on required tables."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "executor_ready" in data
        assert data["executor_ready"] is True

    def test_health_executor_not_ready_missing_tables(self, tmp_path):
        """executor_ready is False when required tables are missing."""
        sessions_db = tmp_path / "sessions.db"
        bib_db = tmp_path / "empty.db"
        enrichment_db = tmp_path / "enrichment" / "cache.db"

        # Create an empty DB (no tables)
        conn = sqlite3.connect(bib_db)
        conn.close()

        with patch.dict("os.environ", {
            "SESSIONS_DB_PATH": str(sessions_db),
            "BIBLIOGRAPHIC_DB_PATH": str(bib_db),
            "ENRICHMENT_DB_PATH": str(enrichment_db),
        }):
            with TestClient(app) as c:
                resp = c.get("/health")

        data = resp.json()
        assert data["executor_ready"] is False
