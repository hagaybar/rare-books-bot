"""Tests for NameAgent specialist.

Uses in-memory SQLite fixtures to test against real schema without requiring
the production database. LLM calls are mocked via the harness.reasoning layer.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.metadata.agent_harness import (
    AgentHarness,
    ProposedMapping,
)
from scripts.metadata.agents.name_agent import (
    AgentAnalysis,
    AgentRecord,
    NameAgent,
    ProposedAuthority,
    ValidationResult,
    names_match,
    normalize_name_for_comparison,
    reorder_name,
)


# ---------------------------------------------------------------------------
# Schema DDL matching the production M3 database
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE
);

CREATE TABLE imprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id),
    place_raw TEXT,
    place_norm TEXT,
    place_confidence REAL,
    place_method TEXT,
    date_raw TEXT,
    date_label TEXT,
    date_start INTEGER,
    date_end INTEGER,
    date_confidence REAL,
    date_method TEXT,
    publisher_raw TEXT,
    publisher_norm TEXT,
    publisher_confidence REAL,
    publisher_method TEXT,
    country_code TEXT
);

CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL REFERENCES records(id),
    agent_raw TEXT,
    agent_norm TEXT,
    agent_confidence REAL NOT NULL DEFAULT 0.0,
    agent_method TEXT,
    role_raw TEXT,
    role_norm TEXT,
    role_confidence REAL NOT NULL DEFAULT 0.0,
    role_method TEXT,
    authority_uri TEXT
);

CREATE TABLE authority_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_uri TEXT NOT NULL UNIQUE,
    nli_id TEXT,
    wikidata_id TEXT,
    viaf_id TEXT,
    isni_id TEXT,
    loc_id TEXT,
    label TEXT,
    description TEXT,
    person_info TEXT,
    place_info TEXT,
    image_url TEXT,
    wikipedia_url TEXT,
    source TEXT NOT NULL,
    confidence REAL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_test_db(tmp_path: Path) -> Path:
    """Create a SQLite DB on disk with test data for name agent tests."""
    db_path = tmp_path / "test_biblio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA_DDL)

    # Insert test records
    records = [
        (1, "990001111110204146"),
        (2, "990002222220204146"),
        (3, "990003333330204146"),
        (4, "990004444440204146"),
        (5, "990005555550204146"),
        (6, "990006666660204146"),
    ]
    conn.executemany("INSERT INTO records (id, mms_id) VALUES (?, ?)", records)

    # Insert imprints (required by coverage report / harness)
    imprints = [
        (1, "Paris", "paris", 0.95, "alias_map", "1650", "1650", 1650, 1650,
         0.99, "exact", "Dupont", "dupont", 0.95, "alias_map", "fr"),
    ]
    conn.executemany(
        """INSERT INTO imprints
           (record_id, place_raw, place_norm, place_confidence, place_method,
            date_raw, date_label, date_start, date_end, date_confidence,
            date_method, publisher_raw, publisher_norm, publisher_confidence,
            publisher_method, country_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        imprints,
    )

    # Insert agents with varying conditions
    agents = [
        # High confidence, with authority URI
        (1, "Smith, John", "john smith", 0.90, "base_clean",
         "printer", "printer", 0.95, "relator_code",
         "https://nli.org/auth/000111"),
        # High confidence, with authority URI (different record)
        (2, "Manutius, Aldus", "aldus manutius", 0.92, "base_clean",
         "publisher", "publisher", 0.95, "relator_code",
         "https://nli.org/auth/000222"),
        # Low confidence, no authority URI
        (3, "יוסף בן אברהם", "יוסף בן אברהם", 0.50, "base_clean",
         "author", "author", 0.90, "relator_term", None),
        # Low confidence, with authority URI
        (4, "Plantin, Christophe", "christophe plantin", 0.70, "base_clean",
         "printer", "printer", 0.95, "relator_code",
         "https://nli.org/auth/000333"),
        # Medium confidence, no authority, no role
        (5, "Unknown Author", "unknown author", 0.85, "base_clean",
         None, "unknown", 0.50, "inferred", None),
        # Low confidence, no authority, empty role
        (6, "רמב\"ם", "רמבם", 0.40, "base_clean",
         "", "unknown", 0.50, "inferred", None),
    ]
    conn.executemany(
        """INSERT INTO agents
           (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
            role_raw, role_norm, role_confidence, role_method, authority_uri)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        agents,
    )

    # Insert authority_enrichment data
    enrichment = [
        ("https://nli.org/auth/000111", "NLI111", "Q12345", "VIAF111",
         None, None, "John Smith", "English printer, 17th century",
         '{"birth_year": 1620, "death_year": 1680}', None, None, None,
         "wikidata", 0.95, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("https://nli.org/auth/000222", "NLI222", "Q67890", "VIAF222",
         None, None, "Aldus Manutius", "Venetian printer and publisher",
         '{"birth_year": 1449, "death_year": 1515}', None, None, None,
         "wikidata", 0.95, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("https://nli.org/auth/000333", "NLI333", "Q54321", "VIAF333",
         None, None, "Christophe Plantin", "French-Flemish printer",
         '{"birth_year": 1520, "death_year": 1589}', None, None, None,
         "wikidata", 0.95, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"),
    ]
    conn.executemany(
        """INSERT INTO authority_enrichment
           (authority_uri, nli_id, wikidata_id, viaf_id,
            isni_id, loc_id, label, description,
            person_info, place_info, image_url, wikipedia_url,
            source, confidence, fetched_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        enrichment,
    )

    conn.commit()
    conn.close()
    return db_path


def _create_cache_file(tmp_path: Path) -> Path:
    """Create empty LLM cache file."""
    cache_path = tmp_path / "agent_llm_cache.jsonl"
    cache_path.touch()
    return cache_path


@pytest.fixture
def tmp_env(tmp_path):
    """Create a complete test environment with DB and cache."""
    db_path = _create_test_db(tmp_path)
    alias_dir = tmp_path / "normalization"
    alias_dir.mkdir()
    cache_path = _create_cache_file(tmp_path)
    return db_path, alias_dir, cache_path


@pytest.fixture
def harness(tmp_env):
    """Create an AgentHarness pointing at the test environment."""
    db_path, alias_dir, cache_path = tmp_env
    return AgentHarness(
        db_path=db_path,
        alias_map_dir=alias_dir,
        cache_path=cache_path,
        api_key="test-key-not-used",
    )


@pytest.fixture
def agent(harness):
    """Create a NameAgent with test harness."""
    return NameAgent(harness)


# ---------------------------------------------------------------------------
# Tests: analyze()
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for NameAgent.analyze()."""

    def test_returns_agent_analysis(self, agent):
        """analyze() returns an AgentAnalysis dataclass."""
        result = agent.analyze()
        assert isinstance(result, AgentAnalysis)

    def test_total_agents_count(self, agent):
        """total_agents reflects all agent rows."""
        result = agent.analyze()
        assert result.total_agents == 6

    def test_with_authority_count(self, agent):
        """Counts agents that have authority URIs."""
        result = agent.analyze()
        # Records 1, 2, 4 have authority URIs
        assert result.with_authority == 3

    def test_without_authority_count(self, agent):
        """Counts agents without authority URIs."""
        result = agent.analyze()
        # Records 3, 5, 6 lack authority URIs
        assert result.without_authority == 3

    def test_low_confidence_count(self, agent):
        """Counts agents with confidence < 0.8."""
        result = agent.analyze()
        # record 3 (0.50), record 4 (0.70), record 6 (0.40) = 3
        assert result.low_confidence_count == 3

    def test_missing_role_count(self, agent):
        """Counts agents with NULL or empty role_raw."""
        result = agent.analyze()
        # record 5 (NULL role), record 6 (empty role) = 2
        assert result.missing_role_count == 2

    def test_top_gaps_populated(self, agent):
        """Top gaps are populated from low-confidence records."""
        result = agent.analyze()
        assert isinstance(result.top_gaps, list)
        assert len(result.top_gaps) > 0

    def test_top_gaps_are_agent_records(self, agent):
        """Each gap is an AgentRecord instance."""
        result = agent.analyze()
        for gap in result.top_gaps:
            assert isinstance(gap, AgentRecord)

    def test_top_gaps_limited_to_20(self, agent):
        """Top gaps limited to at most 20 entries."""
        result = agent.analyze()
        assert len(result.top_gaps) <= 20

    def test_top_gaps_all_low_confidence(self, agent):
        """All top gap entries have confidence < 0.8."""
        result = agent.analyze()
        for gap in result.top_gaps:
            assert gap.confidence < 0.8


# ---------------------------------------------------------------------------
# Tests: get_without_authority()
# ---------------------------------------------------------------------------


class TestGetWithoutAuthority:
    """Tests for NameAgent.get_without_authority()."""

    def test_returns_list_of_agent_records(self, agent):
        """Returns a list of AgentRecord instances."""
        result = agent.get_without_authority()
        assert isinstance(result, list)
        for rec in result:
            assert isinstance(rec, AgentRecord)

    def test_filters_correctly(self, agent):
        """Only returns agents without authority URIs."""
        result = agent.get_without_authority()
        for rec in result:
            assert rec.authority_uri is None or rec.authority_uri == ""

    def test_correct_count(self, agent):
        """Returns expected number of records."""
        result = agent.get_without_authority()
        # Records 3, 5, 6 have no authority URI
        assert len(result) == 3

    def test_includes_expected_agents(self, agent):
        """Expected agent names are present."""
        result = agent.get_without_authority()
        raw_names = {rec.agent_raw for rec in result}
        assert "יוסף בן אברהם" in raw_names
        assert "Unknown Author" in raw_names


# ---------------------------------------------------------------------------
# Tests: get_low_confidence()
# ---------------------------------------------------------------------------


class TestGetLowConfidence:
    """Tests for NameAgent.get_low_confidence()."""

    def test_returns_list_of_agent_records(self, agent):
        """Returns a list of AgentRecord instances."""
        result = agent.get_low_confidence()
        assert isinstance(result, list)
        for rec in result:
            assert isinstance(rec, AgentRecord)

    def test_filters_below_threshold(self, agent):
        """All returned agents have confidence < 0.8."""
        result = agent.get_low_confidence()
        for rec in result:
            assert rec.confidence < 0.8

    def test_correct_count(self, agent):
        """Returns expected number of low-confidence agents."""
        result = agent.get_low_confidence()
        # Records 3 (0.50), 4 (0.70), 6 (0.40) = 3
        assert len(result) == 3

    def test_custom_threshold(self, agent):
        """Custom threshold filters differently."""
        result = agent.get_low_confidence(threshold=0.6)
        # Records 3 (0.50), 6 (0.40) = 2
        assert len(result) == 2
        for rec in result:
            assert rec.confidence < 0.6

    def test_high_threshold_includes_more(self, agent):
        """Higher threshold includes more agents."""
        result = agent.get_low_confidence(threshold=0.95)
        # All but record 2 (0.92) and potentially others
        # Records: 0.90, 0.92, 0.50, 0.70, 0.85, 0.40
        # < 0.95 means 0.90, 0.92, 0.50, 0.70, 0.85, 0.40 = 6
        assert len(result) == 6


# ---------------------------------------------------------------------------
# Tests: propose_authority_match()
# ---------------------------------------------------------------------------


class TestProposeAuthorityMatch:
    """Tests for NameAgent.propose_authority_match()."""

    def test_existing_enrichment_match(self, agent):
        """Finds match in authority_enrichment table."""
        # "Smith, John" should match "John Smith" in enrichment
        result = agent.propose_authority_match("Smith, John")
        assert isinstance(result, ProposedAuthority)
        assert result.canonical_name == "John Smith"
        assert result.suggested_uri == "https://nli.org/auth/000111"
        assert result.confidence == 0.90
        assert result.source != "llm"

    def test_existing_enrichment_exact_match(self, agent):
        """Exact label match returns authority data."""
        result = agent.propose_authority_match("Aldus Manutius")
        assert isinstance(result, ProposedAuthority)
        assert result.canonical_name == "Aldus Manutius"
        assert result.suggested_uri == "https://nli.org/auth/000222"

    def test_no_enrichment_falls_back_to_llm(self, agent):
        """Falls back to LLM when no enrichment match."""
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="Unknown Person",
                canonical_value="unknown person",
                confidence=0.60,
                reasoning="Cannot identify this name with certainty",
                evidence_sources=["context", "request"],
                field="agent",
            )
        )
        result = agent.propose_authority_match("Unknown Person")
        assert isinstance(result, ProposedAuthority)
        assert result.source == "llm"
        assert result.canonical_name == "unknown person"
        assert result.suggested_uri is None

    def test_llm_called_with_correct_field(self, agent):
        """LLM fallback passes field='agent'."""
        mock_propose = MagicMock(
            return_value=ProposedMapping(
                raw_value="test",
                canonical_value="test",
                confidence=0.5,
                reasoning="test",
                evidence_sources=[],
                field="agent",
            )
        )
        agent.harness.reasoning.propose_mapping = mock_propose

        agent.propose_authority_match("Nonexistent Author Name XYZ")

        mock_propose.assert_called_once()
        call_kwargs = mock_propose.call_args
        assert call_kwargs.kwargs.get("field") == "agent" or call_kwargs[1].get("field") == "agent"

    def test_reordered_name_match(self, agent):
        """Matches 'Last, First' against 'First Last' in enrichment."""
        result = agent.propose_authority_match("Manutius, Aldus")
        assert result.canonical_name == "Aldus Manutius"
        assert result.suggested_uri == "https://nli.org/auth/000222"


# ---------------------------------------------------------------------------
# Tests: validate_against_authority()
# ---------------------------------------------------------------------------


class TestValidateAgainstAuthority:
    """Tests for NameAgent.validate_against_authority()."""

    def test_returns_validation_results(self, agent):
        """Returns a list of ValidationResult instances."""
        results = agent.validate_against_authority(["990001111110204146"])
        assert isinstance(results, list)
        for vr in results:
            assert isinstance(vr, ValidationResult)

    def test_matching_name_has_match_true(self, agent):
        """Agent norm matching authority label sets match=True."""
        # Record 1: agent_norm="john smith", enrichment label="John Smith"
        results = agent.validate_against_authority(["990001111110204146"])
        assert len(results) == 1
        assert results[0].match is True
        assert results[0].authority_canonical == "John Smith"

    def test_matching_name_gets_confidence_boost(self, agent):
        """Matching name with confidence < 0.95 gets a boost."""
        # Record 1: confidence=0.90, should get boost
        results = agent.validate_against_authority(["990001111110204146"])
        assert len(results) == 1
        assert results[0].confidence_boost is not None
        assert results[0].confidence_boost > 0.90

    def test_matching_name_boost_capped_at_095(self, agent):
        """Confidence boost does not exceed 0.95."""
        results = agent.validate_against_authority(["990001111110204146"])
        assert results[0].confidence_boost <= 0.95

    def test_reordered_name_still_matches(self, agent):
        """'christophe plantin' matches 'Christophe Plantin' label."""
        # Record 4: agent_norm="christophe plantin",
        #   enrichment label="Christophe Plantin"
        results = agent.validate_against_authority(["990004444440204146"])
        assert len(results) == 1
        assert results[0].match is True

    def test_skips_agents_without_authority(self, agent):
        """Agents without authority URI are not included."""
        # Record 3 has no authority URI
        results = agent.validate_against_authority(["990003333330204146"])
        assert len(results) == 0

    def test_multiple_mms_ids(self, agent):
        """Handles multiple MMS IDs at once."""
        results = agent.validate_against_authority([
            "990001111110204146",
            "990002222220204146",
            "990004444440204146",
        ])
        assert len(results) == 3
        mms_ids = {r.mms_id for r in results}
        assert "990001111110204146" in mms_ids
        assert "990002222220204146" in mms_ids
        assert "990004444440204146" in mms_ids

    def test_empty_mms_ids_returns_empty(self, agent):
        """Empty input returns empty list."""
        results = agent.validate_against_authority([])
        assert results == []

    def test_nonexistent_mms_id_returns_empty(self, agent):
        """Non-existent MMS ID returns empty list."""
        results = agent.validate_against_authority(["999999999999"])
        assert results == []

    def test_missing_enrichment_data(self, tmp_path):
        """Agent with authority URI but no enrichment entry gets match=False."""
        db_path = tmp_path / "no_enrichment.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_X')"
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence,
                agent_method, role_raw, role_norm, role_confidence,
                role_method, authority_uri)
               VALUES (1, 'Some Author', 'some author', 0.80,
                       'base_clean', 'author', 'author', 0.90,
                       'relator_term', 'https://nli.org/auth/UNKNOWN')"""
        )
        # No authority_enrichment entry for this URI
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)
        results = na.validate_against_authority(["MMS_X"])
        assert len(results) == 1
        assert results[0].match is False
        assert results[0].authority_canonical is None
        assert results[0].confidence_boost is None


# ---------------------------------------------------------------------------
# Tests: name matching utilities
# ---------------------------------------------------------------------------


class TestNormalizeName:
    """Tests for normalize_name_for_comparison()."""

    def test_casefold(self):
        assert normalize_name_for_comparison("John SMITH") == "john smith"

    def test_strip_punctuation(self):
        assert normalize_name_for_comparison("Smith, John.") == "smith john"

    def test_collapse_whitespace(self):
        assert normalize_name_for_comparison("John   Smith") == "john smith"

    def test_strip_brackets(self):
        assert normalize_name_for_comparison("[Smith]") == "smith"

    def test_empty_string(self):
        assert normalize_name_for_comparison("") == ""

    def test_unicode_nfc(self):
        # Composed vs decomposed forms should produce same result
        composed = "Caf\u00e9"
        decomposed = "Cafe\u0301"
        assert normalize_name_for_comparison(composed) == normalize_name_for_comparison(decomposed)


class TestReorderName:
    """Tests for reorder_name()."""

    def test_last_first_to_first_last(self):
        assert reorder_name("Smith, John") == "john smith"

    def test_no_comma_unchanged(self):
        assert reorder_name("John Smith") == "john smith"

    def test_last_first_middle(self):
        assert reorder_name("Smith, John William") == "john william smith"

    def test_empty_string(self):
        assert reorder_name("") == ""

    def test_only_comma(self):
        # Edge case: just a comma
        result = reorder_name(",")
        assert result == ""


class TestNamesMatch:
    """Tests for names_match()."""

    def test_exact_match(self):
        assert names_match("John Smith", "John Smith") is True

    def test_case_insensitive(self):
        assert names_match("john smith", "JOHN SMITH") is True

    def test_last_first_vs_first_last(self):
        assert names_match("Smith, John", "John Smith") is True

    def test_first_last_vs_last_first(self):
        assert names_match("John Smith", "Smith, John") is True

    def test_with_punctuation(self):
        assert names_match("Smith, John.", "John Smith") is True

    def test_different_names(self):
        assert names_match("John Smith", "Jane Doe") is False

    def test_empty_strings(self):
        assert names_match("", "") is False
        assert names_match("John", "") is False
        assert names_match("", "John") is False

    def test_partial_name(self):
        # "John" != "John Smith" - they are different
        assert names_match("John", "John Smith") is False

    def test_unicode_names(self):
        assert names_match("José García", "josé garcía") is True

    def test_with_middle_name_reorder(self):
        assert names_match("Manutius, Aldus", "Aldus Manutius") is True


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty database, all agents have authority, etc."""

    def test_empty_database(self, tmp_path):
        """NameAgent works with an empty database."""
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)

        result = na.analyze()
        assert result.total_agents == 0
        assert result.with_authority == 0
        assert result.without_authority == 0
        assert result.low_confidence_count == 0
        assert result.missing_role_count == 0
        assert result.top_gaps == []

    def test_empty_db_get_without_authority(self, tmp_path):
        """get_without_authority() returns empty list on empty DB."""
        db_path = tmp_path / "empty2.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias2"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache2.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)
        result = na.get_without_authority()
        assert result == []

    def test_empty_db_get_low_confidence(self, tmp_path):
        """get_low_confidence() returns empty list on empty DB."""
        db_path = tmp_path / "empty3.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias3"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache3.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)
        result = na.get_low_confidence()
        assert result == []

    def test_all_agents_have_authority(self, tmp_path):
        """Analyze shows zero without_authority when all have URIs."""
        db_path = tmp_path / "all_auth.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_1')"
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence,
                agent_method, role_raw, role_norm, role_confidence,
                role_method, authority_uri)
               VALUES (1, 'Test Author', 'test author', 0.95,
                       'base_clean', 'author', 'author', 0.95,
                       'relator_code', 'https://nli.org/auth/999')"""
        )
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias4"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache4.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)

        result = na.analyze()
        assert result.total_agents == 1
        assert result.with_authority == 1
        assert result.without_authority == 0

    def test_no_enrichment_data_propose(self, tmp_path):
        """propose_authority_match falls back to LLM when no enrichment."""
        db_path = tmp_path / "no_enrich.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias5"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache5.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)

        # Mock the LLM since no enrichment data exists
        harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="Gutenberg, Johannes",
                canonical_value="johannes gutenberg",
                confidence=0.85,
                reasoning="Well-known historical figure",
                evidence_sources=[],
                field="agent",
            )
        )

        result = na.propose_authority_match("Gutenberg, Johannes")
        assert result.source == "llm"
        assert result.canonical_name == "johannes gutenberg"
        assert result.suggested_uri is None

    def test_validate_with_no_enrichment_table_data(self, tmp_path):
        """Validate returns match=False when enrichment table is empty."""
        db_path = tmp_path / "no_enrich2.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_Y')"
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence,
                agent_method, role_raw, role_norm, role_confidence,
                role_method, authority_uri)
               VALUES (1, 'Author X', 'author x', 0.80,
                       'base_clean', 'author', 'author', 0.90,
                       'relator_term', 'https://nli.org/auth/MISSING')"""
        )
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias6"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache6.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        na = NameAgent(harness)
        results = na.validate_against_authority(["MMS_Y"])
        assert len(results) == 1
        assert results[0].match is False
        assert results[0].authority_canonical is None
