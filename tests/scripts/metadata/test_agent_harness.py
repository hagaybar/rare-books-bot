"""Tests for the shared agent harness.

Uses in-memory SQLite databases and temporary files to test both the
GroundingLayer (deterministic) and ReasoningLayer (with mocked OpenAI client).
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.metadata.agent_harness import (
    AgentHarness,
    GapRecord,
    GroundingLayer,
    ProposedMapping,
    ReasoningLayer,
)


# ---------------------------------------------------------------------------
# Schema helpers (mirrors test_audit.py pattern)
# ---------------------------------------------------------------------------

RECORDS_SCHEMA = """
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    jsonl_line_number INTEGER
);
"""

IMPRINTS_SCHEMA = """
CREATE TABLE imprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    date_raw TEXT,
    place_raw TEXT,
    publisher_raw TEXT,
    manufacturer_raw TEXT,
    source_tags TEXT NOT NULL,
    date_start INTEGER,
    date_end INTEGER,
    date_label TEXT,
    date_confidence REAL,
    date_method TEXT,
    place_norm TEXT,
    place_display TEXT,
    place_confidence REAL,
    place_method TEXT,
    publisher_norm TEXT,
    publisher_display TEXT,
    publisher_confidence REAL,
    publisher_method TEXT,
    country_code TEXT,
    country_name TEXT,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
"""

AGENTS_SCHEMA = """
CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    agent_index INTEGER NOT NULL,
    agent_raw TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    role_raw TEXT,
    role_source TEXT,
    authority_uri TEXT,
    agent_norm TEXT NOT NULL,
    agent_confidence REAL NOT NULL CHECK(agent_confidence BETWEEN 0 AND 1),
    agent_method TEXT NOT NULL,
    agent_notes TEXT,
    role_norm TEXT NOT NULL,
    role_confidence REAL NOT NULL CHECK(role_confidence BETWEEN 0 AND 1),
    role_method TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
"""


def _create_full_schema(conn: sqlite3.Connection) -> None:
    """Create records, imprints, and agents tables."""
    conn.executescript(RECORDS_SCHEMA)
    conn.executescript(IMPRINTS_SCHEMA)
    conn.executescript(AGENTS_SCHEMA)


def _insert_record(conn: sqlite3.Connection, mms_id: str) -> int:
    """Insert a minimal record and return its id."""
    conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        (mms_id, "test.xml", "2025-01-01T00:00:00"),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_imprint(
    conn: sqlite3.Connection,
    record_id: int,
    *,
    date_raw: str = None,
    date_confidence: float = None,
    date_method: str = None,
    date_label: str = None,
    place_raw: str = None,
    place_norm: str = None,
    place_confidence: float = None,
    place_method: str = None,
    publisher_raw: str = None,
    publisher_norm: str = None,
    publisher_confidence: float = None,
    publisher_method: str = None,
    country_code: str = None,
) -> None:
    """Insert an imprint row with specified fields."""
    conn.execute(
        """INSERT INTO imprints (
            record_id, occurrence, source_tags,
            date_raw, date_label, date_confidence, date_method,
            place_raw, place_norm, place_confidence, place_method,
            publisher_raw, publisher_norm, publisher_confidence, publisher_method,
            country_code
        ) VALUES (?, 0, '["264"]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            record_id,
            date_raw, date_label, date_confidence, date_method,
            place_raw, place_norm, place_confidence, place_method,
            publisher_raw, publisher_norm, publisher_confidence, publisher_method,
            country_code,
        ),
    )


def _insert_agent(
    conn: sqlite3.Connection,
    record_id: int,
    *,
    agent_raw: str,
    agent_norm: str,
    agent_confidence: float,
    agent_method: str = "base_clean",
    authority_uri: str = None,
) -> None:
    """Insert an agent row."""
    conn.execute(
        """INSERT INTO agents (
            record_id, agent_index, agent_raw, agent_type,
            role_raw, role_source, authority_uri,
            agent_norm, agent_confidence, agent_method, agent_notes,
            role_norm, role_confidence, role_method, provenance_json
        ) VALUES (?, 0, ?, 'personal', NULL, NULL, ?,
                  ?, ?, ?, NULL,
                  'author', 0.9, 'inferred_from_tag', '[]')""",
        (record_id, agent_raw, authority_uri,
         agent_norm, agent_confidence, agent_method),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create an in-memory-like SQLite database file with schema and test data."""
    db_file = tmp_path / "test_biblio.db"
    conn = sqlite3.connect(str(db_file))
    _create_full_schema(conn)

    # Insert test records with varied confidence levels
    rid1 = _insert_record(conn, "990001")
    _insert_imprint(
        conn, rid1,
        place_raw="Lugduni Batavorum",
        place_norm="lugduni batavorum",
        place_confidence=0.60,
        place_method="base_clean",
        date_raw="[1680]",
        date_label="1680",
        date_confidence=0.95,
        date_method="bracketed",
        publisher_raw="Apud Elzevirium",
        publisher_norm="apud elzevirium",
        publisher_confidence=0.70,
        publisher_method="base_clean",
        country_code="ne",
    )

    rid2 = _insert_record(conn, "990002")
    _insert_imprint(
        conn, rid2,
        place_raw="Paris :",
        place_norm="paris",
        place_confidence=0.95,
        place_method="alias_map",
        date_raw="c. 1650",
        date_label="circa 1650",
        date_confidence=0.80,
        date_method="circa",
        publisher_raw="Chez l'auteur",
        publisher_norm="chez lauteur",
        publisher_confidence=0.75,
        publisher_method="base_clean",
        country_code="fr",
    )

    rid3 = _insert_record(conn, "990003")
    _insert_imprint(
        conn, rid3,
        place_raw="Lugduni Batavorum",
        place_norm="lugduni batavorum",
        place_confidence=0.60,
        place_method="base_clean",
        date_raw="unknown",
        date_label=None,
        date_confidence=0.0,
        date_method="unparsed",
        publisher_raw="Apud Elzevirium",
        publisher_norm="apud elzevirium",
        publisher_confidence=0.70,
        publisher_method="base_clean",
        country_code="ne",
    )

    # Agents
    _insert_agent(
        conn, rid1,
        agent_raw="Elzevir, Daniel",
        agent_norm="elzevir daniel",
        agent_confidence=0.75,
        authority_uri="http://viaf.org/viaf/123456",
    )
    _insert_agent(
        conn, rid2,
        agent_raw="Molière",
        agent_norm="moliere",
        agent_confidence=0.90,
        authority_uri="http://viaf.org/viaf/789",
    )
    _insert_agent(
        conn, rid3,
        agent_raw="Unknown Author",
        agent_norm="unknown author",
        agent_confidence=0.50,
    )

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def alias_map_dir(tmp_path: Path) -> Path:
    """Create a temporary alias map directory with a place_alias_map.json."""
    alias_dir = tmp_path / "normalization"
    place_dir = alias_dir / "place_aliases"
    place_dir.mkdir(parents=True)

    alias_map = {
        "lugduni batavorum": "leiden",
        "lutetiae": "paris",
        "amstelodami": "amsterdam",
        "venetiis": "venice",
    }
    map_file = place_dir / "place_alias_map.json"
    map_file.write_text(json.dumps(alias_map, ensure_ascii=False), encoding="utf-8")

    return alias_dir


@pytest.fixture
def grounding(db_path: Path, alias_map_dir: Path) -> GroundingLayer:
    """Create a GroundingLayer with test DB and alias maps."""
    return GroundingLayer(db_path, alias_map_dir)


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    """Return path for a temporary LLM cache file."""
    return tmp_path / "llm_cache.jsonl"


# ---------------------------------------------------------------------------
# GroundingLayer tests
# ---------------------------------------------------------------------------


class TestGroundingLayerQueryGaps:
    """Tests for GroundingLayer.query_gaps."""

    def test_place_gaps_default_threshold(self, grounding: GroundingLayer):
        """Records with place_confidence <= 0.8 should be returned."""
        gaps = grounding.query_gaps("place", max_confidence=0.8)
        # rid1 (0.60) and rid3 (0.60) should match; rid2 (0.95) should not
        assert len(gaps) == 2
        mms_ids = {g.mms_id for g in gaps}
        assert mms_ids == {"990001", "990003"}

    def test_place_gaps_strict_threshold(self, grounding: GroundingLayer):
        """Tighter threshold narrows results."""
        gaps = grounding.query_gaps("place", max_confidence=0.5)
        assert len(gaps) == 0

    def test_date_gaps(self, grounding: GroundingLayer):
        """Date gaps should include records with date_confidence <= threshold."""
        gaps = grounding.query_gaps("date", max_confidence=0.8)
        # rid2 (0.80) and rid3 (0.0) should match; rid1 (0.95) should not
        assert len(gaps) == 2
        mms_ids = {g.mms_id for g in gaps}
        assert mms_ids == {"990002", "990003"}

    def test_publisher_gaps(self, grounding: GroundingLayer):
        """Publisher gaps below threshold."""
        gaps = grounding.query_gaps("publisher", max_confidence=0.75)
        # rid1 (0.70) and rid2 (0.75) and rid3 (0.70)
        assert len(gaps) == 3

    def test_agent_gaps(self, grounding: GroundingLayer):
        """Agent gaps below threshold."""
        gaps = grounding.query_gaps("agent", max_confidence=0.8)
        # rid1 (0.75) and rid3 (0.50) should match; rid2 (0.90) should not
        assert len(gaps) == 2
        mms_ids = {g.mms_id for g in gaps}
        assert mms_ids == {"990001", "990003"}

    def test_gap_record_fields(self, grounding: GroundingLayer):
        """GapRecord should have correct field values."""
        gaps = grounding.query_gaps("place", max_confidence=0.8)
        gap = next(g for g in gaps if g.mms_id == "990001")
        assert gap.field == "place"
        assert gap.raw_value == "Lugduni Batavorum"
        assert gap.current_norm == "lugduni batavorum"
        assert gap.confidence == 0.60
        assert gap.method == "base_clean"
        assert gap.country_code == "ne"

    def test_invalid_field_raises(self, grounding: GroundingLayer):
        """Unknown field should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown field"):
            grounding.query_gaps("nonexistent")

    def test_high_threshold_returns_all(self, grounding: GroundingLayer):
        """Threshold of 1.0 should return all non-null records."""
        gaps = grounding.query_gaps("place", max_confidence=1.0)
        assert len(gaps) == 3


class TestGroundingLayerAliasMap:
    """Tests for GroundingLayer.query_alias_map."""

    def test_load_place_alias_map(self, grounding: GroundingLayer):
        """Should load place alias map from JSON."""
        alias_map = grounding.query_alias_map("place")
        assert alias_map["lugduni batavorum"] == "leiden"
        assert alias_map["lutetiae"] == "paris"
        assert len(alias_map) == 4

    def test_missing_alias_map_returns_empty(self, grounding: GroundingLayer):
        """Non-existent alias map file returns empty dict."""
        alias_map = grounding.query_alias_map("publisher")
        assert alias_map == {}

    def test_unknown_field_returns_empty(self, grounding: GroundingLayer):
        """Unknown field returns empty dict (no file mapping)."""
        alias_map = grounding.query_alias_map("language")
        assert alias_map == {}


class TestGroundingLayerCountryAndAuthority:
    """Tests for query_country_codes and query_authority_uris."""

    def test_query_country_codes(self, grounding: GroundingLayer):
        """Should return country codes for given MMS IDs."""
        codes = grounding.query_country_codes(["990001", "990002"])
        assert codes["990001"] == "ne"
        assert codes["990002"] == "fr"

    def test_query_country_codes_empty_input(self, grounding: GroundingLayer):
        """Empty MMS ID list returns empty dict."""
        codes = grounding.query_country_codes([])
        assert codes == {}

    def test_query_country_codes_nonexistent_id(self, grounding: GroundingLayer):
        """Non-existent MMS ID returns empty dict."""
        codes = grounding.query_country_codes(["999999"])
        assert codes == {}

    def test_query_authority_uris(self, grounding: GroundingLayer):
        """Should return authority URIs for agents with non-null URIs."""
        uris = grounding.query_authority_uris(["990001", "990002"])
        assert uris["990001"] == "http://viaf.org/viaf/123456"
        assert uris["990002"] == "http://viaf.org/viaf/789"

    def test_query_authority_uris_null_uri(self, grounding: GroundingLayer):
        """MMS ID with null authority_uri should not appear."""
        uris = grounding.query_authority_uris(["990003"])
        assert "990003" not in uris

    def test_query_authority_uris_empty_input(self, grounding: GroundingLayer):
        """Empty input returns empty dict."""
        uris = grounding.query_authority_uris([])
        assert uris == {}


class TestGroundingLayerCountAffected:
    """Tests for GroundingLayer.count_affected_records."""

    def test_count_place_two_records(self, grounding: GroundingLayer):
        """'Lugduni Batavorum' appears in two imprints."""
        count = grounding.count_affected_records("Lugduni Batavorum", "place")
        assert count == 2

    def test_count_place_one_record(self, grounding: GroundingLayer):
        """'Paris :' appears in one imprint."""
        count = grounding.count_affected_records("Paris :", "place")
        assert count == 1

    def test_count_nonexistent_value(self, grounding: GroundingLayer):
        """Non-existent value returns 0."""
        count = grounding.count_affected_records("Nonexistent Place", "place")
        assert count == 0

    def test_count_publisher(self, grounding: GroundingLayer):
        """Publisher count."""
        count = grounding.count_affected_records("Apud Elzevirium", "publisher")
        assert count == 2

    def test_count_agent(self, grounding: GroundingLayer):
        """Agent count."""
        count = grounding.count_affected_records("Elzevir, Daniel", "agent")
        assert count == 1

    def test_count_date(self, grounding: GroundingLayer):
        """Date count."""
        count = grounding.count_affected_records("[1680]", "date")
        assert count == 1

    def test_count_invalid_field(self, grounding: GroundingLayer):
        """Invalid field raises ValueError."""
        with pytest.raises(ValueError, match="Unknown field"):
            grounding.count_affected_records("test", "invalid_field")


class TestGroundingLayerEmptyDB:
    """Tests with an empty database."""

    def test_empty_db_returns_no_gaps(self, tmp_path: Path):
        """Empty DB should return empty list, not error."""
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        _create_full_schema(conn)
        conn.commit()
        conn.close()

        grounding = GroundingLayer(db_file, tmp_path)
        gaps = grounding.query_gaps("place")
        assert gaps == []

    def test_empty_db_count_returns_zero(self, tmp_path: Path):
        """Empty DB should return 0 for count."""
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        _create_full_schema(conn)
        conn.commit()
        conn.close()

        grounding = GroundingLayer(db_file, tmp_path)
        count = grounding.count_affected_records("anything", "place")
        assert count == 0


# ---------------------------------------------------------------------------
# ReasoningLayer tests
# ---------------------------------------------------------------------------

def _make_mock_completion(content_json: dict) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response."""
    mock_message = MagicMock()
    mock_message.content = json.dumps(content_json)
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


class TestReasoningLayerCache:
    """Tests for cache hit/miss behavior."""

    def test_cache_miss_calls_llm(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """On cache miss, should call OpenAI API and cache result."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")

        llm_response = {
            "canonical_value": "leiden",
            "confidence": 0.95,
            "reasoning": "Lugduni Batavorum is the Latin name for Leiden.",
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            _make_mock_completion(llm_response)
        )
        layer.client = mock_client

        result = layer.propose_mapping("Lugduni Batavorum", "place")

        assert result.canonical_value == "leiden"
        assert result.confidence == 0.95
        assert result.field == "place"
        assert "Leiden" in result.reasoning
        # Verify API was called
        mock_client.chat.completions.create.assert_called_once()
        # Verify cache file was written
        assert cache_path.exists()
        cache_content = cache_path.read_text(encoding="utf-8").strip()
        entry = json.loads(cache_content)
        assert entry["field"] == "place"
        assert entry["raw_value"] == "Lugduni Batavorum"

    def test_cache_hit_skips_llm(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """On cache hit, should return cached result without calling LLM."""
        # Pre-populate cache file
        entry = {
            "field": "place",
            "raw_value": "Amstelodami",
            "result": {
                "canonical_value": "amsterdam",
                "confidence": 0.92,
                "reasoning": "Latin for Amsterdam.",
                "evidence_sources": [],
            },
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
        cache_path.write_text(
            json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        # No client set -- would fail if LLM was called
        result = layer.propose_mapping("Amstelodami", "place")

        assert result.canonical_value == "amsterdam"
        assert result.confidence == 0.92
        assert result.field == "place"

    def test_empty_cache_file(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """Empty cache file should not cause errors."""
        cache_path.write_text("", encoding="utf-8")
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        assert len(layer._cache) == 0

    def test_nonexistent_cache_file(
        self, grounding: GroundingLayer, tmp_path: Path
    ):
        """Non-existent cache file should not cause errors."""
        missing_path = tmp_path / "nonexistent" / "cache.jsonl"
        layer = ReasoningLayer(grounding, missing_path, api_key="test-key")
        assert len(layer._cache) == 0

    def test_malformed_cache_entries_skipped(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """Malformed JSON lines in cache should be skipped gracefully."""
        lines = [
            '{"field": "place", "raw_value": "ok", "result": {"canonical_value": "valid", "confidence": 0.9, "reasoning": "ok"}}',
            "this is not json",
            '{"missing_field": true}',
        ]
        cache_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        # Only the first valid entry should be in cache
        assert len(layer._cache) == 1
        key = ReasoningLayer._cache_key("place", "ok")
        assert key in layer._cache


class TestReasoningLayerPromptConstruction:
    """Tests for system prompt construction."""

    def test_prompt_includes_field_and_value(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """System prompt should include the field and raw value."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        prompt = layer._build_system_prompt("place", "Lugduni Batavorum")
        assert "FIELD: place" in prompt
        assert 'RAW VALUE: "Lugduni Batavorum"' in prompt

    def test_prompt_includes_vocabulary(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """System prompt should include existing alias map entries."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        prompt = layer._build_system_prompt("place", "test")
        assert '"lugduni batavorum" -> "leiden"' in prompt
        assert '"lutetiae" -> "paris"' in prompt

    def test_prompt_with_evidence(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """System prompt should include evidence JSON when provided."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        evidence = {"country_code": "ne", "source": "MARC 008"}
        prompt = layer._build_system_prompt("place", "test", evidence)
        assert '"country_code": "ne"' in prompt

    def test_prompt_no_alias_map(self, db_path: Path, cache_path: Path, tmp_path: Path):
        """When alias map is missing, prompt should show placeholder."""
        empty_dir = tmp_path / "empty_aliases"
        empty_dir.mkdir()
        grounding = GroundingLayer(db_path, empty_dir)
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        prompt = layer._build_system_prompt("publisher", "test")
        assert "(no existing mappings)" in prompt


class TestReasoningLayerProposedMapping:
    """Tests for propose_mapping response parsing."""

    def test_mapping_with_evidence_sources(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """Evidence dict keys should become evidence_sources."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")

        llm_response = {
            "canonical_value": "leiden",
            "confidence": 0.95,
            "reasoning": "Dutch city.",
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            _make_mock_completion(llm_response)
        )
        layer.client = mock_client

        evidence = {"country_code": "ne", "marc_source": "008/15-17"}
        result = layer.propose_mapping(
            "Lugduni Batavorum", "place", evidence=evidence
        )

        assert set(result.evidence_sources) == {"country_code", "marc_source"}

    def test_mapping_low_confidence_response(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """Low-confidence LLM response should be preserved."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")

        llm_response = {
            "canonical_value": "",
            "confidence": 0.3,
            "reasoning": "Cannot determine the canonical form.",
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            _make_mock_completion(llm_response)
        )
        layer.client = mock_client

        result = layer.propose_mapping("???", "place")
        assert result.confidence == 0.3
        assert result.canonical_value == ""


class TestReasoningLayerExplainAndSuggest:
    """Tests for explain_cluster and suggest_investigation."""

    def test_explain_cluster(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """explain_cluster should call LLM and return string."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "These are all Latin place names for Dutch cities."
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        layer.client = mock_client

        explanation = layer.explain_cluster(
            "latin_place_names",
            ["Lugduni Batavorum", "Amstelodami"],
            "place",
        )
        assert "Latin" in explanation
        mock_client.chat.completions.create.assert_called_once()

    def test_suggest_investigation(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """suggest_investigation should call LLM and return string."""
        layer = ReasoningLayer(grounding, cache_path, api_key="test-key")
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "1. Check VIAF authority files.\n2. Cross-reference country codes."
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        layer.client = mock_client

        suggestions = layer.suggest_investigation(
            "latin_place_names",
            ["Lugduni Batavorum"],
            "place",
        )
        assert "VIAF" in suggestions or "Cross-reference" in suggestions


class TestReasoningLayerNoApiKey:
    """Tests for missing API key handling."""

    def test_no_api_key_raises_on_llm_call(
        self, grounding: GroundingLayer, cache_path: Path
    ):
        """Should raise RuntimeError when no API key is available."""
        # Clear env var to ensure no fallback
        with patch.dict("os.environ", {}, clear=True):
            layer = ReasoningLayer(grounding, cache_path, api_key=None)
            with pytest.raises(RuntimeError, match="No OpenAI API key"):
                layer.propose_mapping("test", "place")


# ---------------------------------------------------------------------------
# AgentHarness integration tests
# ---------------------------------------------------------------------------


class TestAgentHarness:
    """Tests for the combined AgentHarness interface."""

    def test_harness_grounding_delegates(
        self, db_path: Path, alias_map_dir: Path, cache_path: Path
    ):
        """AgentHarness should delegate grounding methods correctly."""
        harness = AgentHarness(
            db_path, alias_map_dir, cache_path=cache_path, api_key="test-key"
        )

        # query_gaps
        gaps = harness.query_gaps("place", max_confidence=0.8)
        assert len(gaps) == 2

        # query_alias_map
        alias_map = harness.query_alias_map("place")
        assert "lugduni batavorum" in alias_map

        # query_country_codes
        codes = harness.query_country_codes(["990001"])
        assert codes["990001"] == "ne"

        # query_authority_uris
        uris = harness.query_authority_uris(["990001"])
        assert "viaf" in uris["990001"]

        # count_affected_records
        count = harness.count_affected_records("Lugduni Batavorum", "place")
        assert count == 2

    def test_harness_reasoning_delegates(
        self, db_path: Path, alias_map_dir: Path, cache_path: Path
    ):
        """AgentHarness should delegate reasoning methods correctly."""
        harness = AgentHarness(
            db_path, alias_map_dir, cache_path=cache_path, api_key="test-key"
        )

        # Mock the OpenAI client on the reasoning layer
        llm_response = {
            "canonical_value": "leiden",
            "confidence": 0.95,
            "reasoning": "Latin for Leiden.",
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = (
            _make_mock_completion(llm_response)
        )
        harness.reasoning.client = mock_client

        result = harness.propose_mapping("Lugduni Batavorum", "place")
        assert result.canonical_value == "leiden"

    def test_harness_default_cache_path(
        self, db_path: Path, alias_map_dir: Path
    ):
        """When no cache_path is given, default should be used."""
        harness = AgentHarness(db_path, alias_map_dir, api_key="test-key")
        assert harness.reasoning.cache_path == Path(
            "data/metadata/agent_llm_cache.jsonl"
        )


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Tests for GapRecord and ProposedMapping data classes."""

    def test_gap_record_defaults(self):
        """GapRecord should have correct default for country_code."""
        gap = GapRecord(
            mms_id="990001",
            field="place",
            raw_value="test",
            current_norm=None,
            confidence=0.5,
            method="base_clean",
        )
        assert gap.country_code is None

    def test_proposed_mapping_defaults(self):
        """ProposedMapping should have correct defaults."""
        mapping = ProposedMapping(
            raw_value="test",
            canonical_value="test_canonical",
            confidence=0.9,
            reasoning="test reasoning",
        )
        assert mapping.evidence_sources == []
        assert mapping.field == ""

    def test_proposed_mapping_with_all_fields(self):
        """ProposedMapping with all fields populated."""
        mapping = ProposedMapping(
            raw_value="Lugduni",
            canonical_value="leiden",
            confidence=0.95,
            reasoning="Latin name",
            evidence_sources=["country_code", "alias_map"],
            field="place",
        )
        assert len(mapping.evidence_sources) == 2
        assert mapping.field == "place"
