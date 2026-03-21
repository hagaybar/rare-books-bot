"""Tests for DateAgent specialist.

Uses in-memory SQLite fixtures to test against real schema without requiring
the production database. LLM calls are mocked via the harness.reasoning layer.
"""

import json
import sqlite3
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

import pytest

from scripts.metadata.agent_harness import (
    AgentHarness,
    GapRecord,
    ProposedMapping,
)
from scripts.metadata.agents.date_agent import (
    DateAgent,
    DateAnalysis,
    ProposedDate,
    UnparsedDate,
)
from scripts.metadata.clustering import Cluster, ClusterValue


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
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_test_db(tmp_path: Path) -> Path:
    """Create a SQLite DB with test date data covering various scenarios."""
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
        (7, "990007777770204146"),
        (8, "990008888880204146"),
    ]
    conn.executemany("INSERT INTO records (id, mms_id) VALUES (?, ?)", records)

    # Insert imprints with varying date confidence levels and methods
    imprints = [
        # High confidence dates (>= 0.8) -- parsed
        (1, "Paris", "paris", 0.95, "alias_map",
         "1650", "1650", 1650, 1650, 0.99, "year_exact",
         "Dupont", "dupont", 0.95, "alias_map", "fr"),
        (2, "London", "london", 0.95, "alias_map",
         "[1680]", "1680", 1680, 1680, 0.95, "year_bracketed",
         "OUP", "oup", 0.95, "alias_map", "enk"),
        (3, "Amsterdam", "amsterdam", 0.95, "alias_map",
         "1500-1599", "1500-1599", 1500, 1599, 0.90, "year_range",
         "Elsevier", "elsevier", 0.95, "alias_map", "ne"),
        # Low confidence / unparsed dates -- gaps
        (4, "Roma", "rome", 0.95, "alias_map",
         "[17--?]", "[17--?]", None, None, 0.0, "unparsed",
         None, None, None, None, "it"),
        (5, "Berlin", "berlin", 0.95, "alias_map",
         "Anno MDCCCX", "Anno MDCCCX", None, None, 0.0, "unparsed",
         None, None, None, None, "gw"),
        (6, "Jerusalem", "jerusalem", 0.95, "alias_map",
         'שנת תר"ל', 'שנת תר"ל', None, None, 0.0, "unparsed",
         None, None, None, None, "is"),
        (7, "Paris", "paris", 0.95, "alias_map",
         "", "", None, None, 0.0, "missing",
         None, None, None, None, "fr"),
        (8, "Vienna", "vienna", 0.95, "alias_map",
         "ca. 1750?", "ca. 1750?", None, None, 0.0, "unparsed",
         None, None, None, None, "au"),
    ]
    conn.executemany(
        """INSERT INTO imprints
           (record_id, place_raw, place_norm, place_confidence, place_method,
            date_raw, date_label, date_start, date_end, date_confidence, date_method,
            publisher_raw, publisher_norm, publisher_confidence, publisher_method,
            country_code)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        imprints,
    )

    # Insert agents (required by coverage report)
    agents = [
        (1, "John Smith", "john smith", 0.90, "basic_clean",
         "printer", "printer", 0.95, "exact", None),
    ]
    conn.executemany(
        """INSERT INTO agents
           (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
            role_raw, role_norm, role_confidence, role_method, authority_uri)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        agents,
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
    """Create a DateAgent with test harness."""
    return DateAgent(harness)


# ---------------------------------------------------------------------------
# Tests: classify_date_pattern (static method)
# ---------------------------------------------------------------------------


class TestClassifyDatePattern:
    """Tests for DateAgent.classify_date_pattern()."""

    def test_partial_century(self):
        """Partial century patterns like [17--?] classified correctly."""
        assert DateAgent.classify_date_pattern("[17--?]") == "partial_century"
        assert DateAgent.classify_date_pattern("18--") == "partial_century"
        assert DateAgent.classify_date_pattern("[16--]") == "partial_century"

    def test_hebrew_gematria(self):
        """Hebrew letter date patterns classified correctly."""
        assert DateAgent.classify_date_pattern('שנת תר"ל') == "hebrew_gematria"
        assert DateAgent.classify_date_pattern('תק"ח') == "hebrew_gematria"

    def test_latin_convention(self):
        """Latin date conventions classified correctly."""
        assert DateAgent.classify_date_pattern("Anno MDCCCX") == "latin_convention"
        assert DateAgent.classify_date_pattern("MDCCC") == "latin_convention"
        assert DateAgent.classify_date_pattern("A.D. 1650") == "latin_convention"

    def test_ambiguous_range(self):
        """Ambiguous range patterns classified correctly."""
        assert DateAgent.classify_date_pattern("1500-99") == "ambiguous_range"

    def test_circa(self):
        """Circa patterns classified correctly."""
        assert DateAgent.classify_date_pattern("ca. 1750") == "circa"
        assert DateAgent.classify_date_pattern("circa 1650") == "circa"

    def test_empty_missing(self):
        """Empty and whitespace-only strings classified as empty_missing."""
        assert DateAgent.classify_date_pattern("") == "empty_missing"
        assert DateAgent.classify_date_pattern("   ") == "empty_missing"

    def test_other_unparsed(self):
        """Unrecognized patterns classified as other_unparsed."""
        assert DateAgent.classify_date_pattern("unknown date") == "other_unparsed"
        assert DateAgent.classify_date_pattern("n.d.") == "other_unparsed"

    def test_single_hebrew_char_not_gematria(self):
        """A single Hebrew character should not trigger hebrew_gematria."""
        # classify_date_pattern requires >= 2 Hebrew chars
        assert DateAgent.classify_date_pattern("x א y") != "hebrew_gematria"


# ---------------------------------------------------------------------------
# Tests: analyze()
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for DateAgent.analyze()."""

    def test_returns_date_analysis(self, agent):
        """analyze() returns a DateAnalysis dataclass."""
        result = agent.analyze()
        assert isinstance(result, DateAnalysis)

    def test_total_dates_count(self, agent):
        """total_dates reflects all imprint rows."""
        result = agent.analyze()
        assert result.total_dates == 8

    def test_parsed_count(self, agent):
        """parsed_count includes dates with confidence >= 0.8."""
        result = agent.analyze()
        # Records 1-3 have high confidence (0.99, 0.95, 0.90)
        assert result.parsed_count == 3

    def test_unparsed_count(self, agent):
        """unparsed_count includes dates with confidence < 0.8."""
        result = agent.analyze()
        # Records 4-8 have confidence 0.0
        assert result.unparsed_count == 5

    def test_by_method_populated(self, agent):
        """by_method dict has entries for each normalization method."""
        result = agent.analyze()
        assert isinstance(result.by_method, dict)
        assert len(result.by_method) > 0
        assert "year_exact" in result.by_method
        assert "unparsed" in result.by_method

    def test_by_pattern_populated(self, agent):
        """by_pattern dict has entries for unparsed pattern types."""
        result = agent.analyze()
        assert isinstance(result.by_pattern, dict)
        # We have partial_century, latin_convention, hebrew_gematria,
        # empty_missing, and circa patterns in test data
        assert len(result.by_pattern) > 0

    def test_clusters_populated(self, agent):
        """Clusters are built from flagged items."""
        result = agent.analyze()
        assert isinstance(result.clusters, list)

    def test_top_unparsed_limited(self, agent):
        """top_unparsed is limited to at most 20 entries."""
        result = agent.analyze()
        assert isinstance(result.top_unparsed, list)
        assert len(result.top_unparsed) <= 20

    def test_top_unparsed_are_unparsed_date_type(self, agent):
        """Each item in top_unparsed is an UnparsedDate."""
        result = agent.analyze()
        for item in result.top_unparsed:
            assert isinstance(item, UnparsedDate)


# ---------------------------------------------------------------------------
# Tests: get_unparsed()
# ---------------------------------------------------------------------------


class TestGetUnparsed:
    """Tests for DateAgent.get_unparsed()."""

    def test_returns_unparsed_dates(self, agent):
        """get_unparsed() returns list of UnparsedDate."""
        results = agent.get_unparsed()
        assert isinstance(results, list)
        for item in results:
            assert isinstance(item, UnparsedDate)

    def test_unparsed_have_low_confidence(self, agent):
        """All returned items have confidence <= 0.8."""
        results = agent.get_unparsed()
        for item in results:
            assert item.current_confidence <= 0.8

    def test_unparsed_have_pattern_type(self, agent):
        """Each unparsed date has a pattern_type classification."""
        valid_patterns = {
            "partial_century",
            "hebrew_gematria",
            "latin_convention",
            "ambiguous_range",
            "circa",
            "empty_missing",
            "other_unparsed",
        }
        results = agent.get_unparsed()
        for item in results:
            assert item.pattern_type in valid_patterns, (
                f"Unexpected pattern_type: {item.pattern_type}"
            )

    def test_unparsed_contains_expected_values(self, agent):
        """Known unparsed values from test data appear in results."""
        results = agent.get_unparsed()
        raw_values = {item.raw_value for item in results}
        # These should be in the results (confidence 0.0)
        assert "[17--?]" in raw_values
        assert "Anno MDCCCX" in raw_values

    def test_parsed_dates_excluded(self, agent):
        """High confidence dates are not returned."""
        results = agent.get_unparsed()
        raw_values = {item.raw_value for item in results}
        # These have high confidence and should not appear
        assert "1650" not in raw_values
        assert "[1680]" not in raw_values


# ---------------------------------------------------------------------------
# Tests: group_by_pattern()
# ---------------------------------------------------------------------------


class TestGroupByPattern:
    """Tests for DateAgent.group_by_pattern()."""

    def test_returns_dict(self, agent):
        """group_by_pattern() returns a dict."""
        groups = agent.group_by_pattern()
        assert isinstance(groups, dict)

    def test_groups_have_correct_keys(self, agent):
        """Group keys match known pattern types."""
        valid_patterns = {
            "partial_century",
            "hebrew_gematria",
            "latin_convention",
            "ambiguous_range",
            "circa",
            "empty_missing",
            "other_unparsed",
        }
        groups = agent.group_by_pattern()
        for key in groups:
            assert key in valid_patterns, f"Unexpected key: {key}"

    def test_partial_century_group(self, agent):
        """Partial century dates grouped correctly."""
        groups = agent.group_by_pattern()
        if "partial_century" in groups:
            for item in groups["partial_century"]:
                assert item.pattern_type == "partial_century"

    def test_hebrew_gematria_group(self, agent):
        """Hebrew gematria dates grouped correctly."""
        groups = agent.group_by_pattern()
        if "hebrew_gematria" in groups:
            for item in groups["hebrew_gematria"]:
                assert item.pattern_type == "hebrew_gematria"

    def test_latin_convention_group(self, agent):
        """Latin convention dates grouped correctly."""
        groups = agent.group_by_pattern()
        if "latin_convention" in groups:
            for item in groups["latin_convention"]:
                assert item.pattern_type == "latin_convention"

    def test_all_items_accounted_for(self, agent):
        """Total items across groups equals total unparsed count."""
        groups = agent.group_by_pattern()
        total_in_groups = sum(len(items) for items in groups.values())
        all_unparsed = agent.get_unparsed()
        assert total_in_groups == len(all_unparsed)


# ---------------------------------------------------------------------------
# Tests: propose_dates() with mocked LLM
# ---------------------------------------------------------------------------


class TestProposeDates:
    """Tests for DateAgent.propose_dates() with mocked LLM."""

    def _make_unparsed(self) -> List[UnparsedDate]:
        """Create test unparsed dates."""
        return [
            UnparsedDate(
                mms_id="990004444440204146",
                raw_value="[17--?]",
                current_confidence=0.0,
                current_method="unparsed",
                pattern_type="partial_century",
            ),
            UnparsedDate(
                mms_id="990005555550204146",
                raw_value="Anno MDCCCX",
                current_confidence=0.0,
                current_method="unparsed",
                pattern_type="latin_convention",
            ),
        ]

    def test_returns_proposed_dates(self, agent):
        """propose_dates() returns list of ProposedDate."""
        unparsed = self._make_unparsed()

        # Mock the reasoning layer
        agent.harness.reasoning.propose_mapping = MagicMock(
            side_effect=[
                ProposedMapping(
                    raw_value="[17--?]",
                    canonical_value="1700-1799",
                    confidence=0.70,
                    reasoning="Partial century indicator for the 18th century",
                    evidence_sources=["field", "pattern_type"],
                    field="date",
                ),
                ProposedMapping(
                    raw_value="Anno MDCCCX",
                    canonical_value="1810",
                    confidence=0.90,
                    reasoning="Roman numeral MDCCCX = 1810",
                    evidence_sources=["field", "pattern_type"],
                    field="date",
                ),
            ]
        )

        proposals = agent.propose_dates(unparsed)
        assert len(proposals) == 2
        for p in proposals:
            assert isinstance(p, ProposedDate)

    def test_proposed_date_fields(self, agent):
        """Proposed dates have expected fields populated."""
        unparsed = [self._make_unparsed()[0]]

        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="[17--?]",
                canonical_value="1700-1799",
                confidence=0.70,
                reasoning="Partial century",
                evidence_sources=[],
                field="date",
            )
        )

        proposals = agent.propose_dates(unparsed)
        assert len(proposals) == 1
        p = proposals[0]
        assert p.raw_value == "[17--?]"
        assert p.date_start == 1700
        assert p.date_end == 1799
        assert p.confidence == 0.70
        assert p.method == "llm_proposed"
        assert "century" in p.reasoning.lower()

    def test_single_year_extraction(self, agent):
        """Single year in canonical_value is extracted correctly."""
        unparsed = [self._make_unparsed()[1]]

        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="Anno MDCCCX",
                canonical_value="1810",
                confidence=0.90,
                reasoning="Roman numeral MDCCCX = 1810",
                evidence_sources=[],
                field="date",
            )
        )

        proposals = agent.propose_dates(unparsed)
        p = proposals[0]
        assert p.date_start == 1810
        assert p.date_end == 1810

    def test_json_canonical_value(self, agent):
        """JSON-formatted canonical_value is parsed correctly."""
        unparsed = [self._make_unparsed()[0]]

        json_response = json.dumps({
            "date_start": 1700,
            "date_end": 1799,
            "method": "llm_proposed",
            "confidence": 0.75,
            "reasoning": "18th century range",
        })

        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="[17--?]",
                canonical_value=json_response,
                confidence=0.75,
                reasoning="18th century range",
                evidence_sources=[],
                field="date",
            )
        )

        proposals = agent.propose_dates(unparsed)
        p = proposals[0]
        assert p.date_start == 1700
        assert p.date_end == 1799
        assert p.method == "llm_proposed"

    def test_unparseable_canonical_value(self, agent):
        """Unparseable canonical_value results in None dates."""
        unparsed = [
            UnparsedDate(
                mms_id="MMS_X",
                raw_value="mystery date",
                current_confidence=0.0,
                current_method="unparsed",
                pattern_type="other_unparsed",
            )
        ]

        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="mystery date",
                canonical_value="unable to determine",
                confidence=0.10,
                reasoning="No recognizable date pattern",
                evidence_sources=[],
                field="date",
            )
        )

        proposals = agent.propose_dates(unparsed)
        p = proposals[0]
        assert p.date_start is None
        assert p.date_end is None
        assert p.confidence == 0.10

    def test_empty_unparsed_returns_empty(self, agent):
        """Empty input returns empty proposals list."""
        proposals = agent.propose_dates([])
        assert proposals == []

    def test_evidence_passed_to_llm(self, agent):
        """Evidence dict passed to LLM includes pattern_type."""
        unparsed = [self._make_unparsed()[0]]

        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="[17--?]",
                canonical_value="1700-1799",
                confidence=0.70,
                reasoning="century range",
                evidence_sources=[],
                field="date",
            )
        )

        agent.propose_dates(unparsed)

        call_args = agent.harness.reasoning.propose_mapping.call_args
        evidence = call_args.kwargs.get("evidence", {})
        assert evidence["field"] == "date"
        assert evidence["pattern_type"] == "partial_century"
        assert evidence["current_method"] == "unparsed"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty database, all dates parsed."""

    def test_empty_database(self, tmp_path):
        """DateAgent works with an empty database (no records)."""
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
        da = DateAgent(harness)

        result = da.analyze()
        assert result.total_dates == 0
        assert result.parsed_count == 0
        assert result.unparsed_count == 0
        assert result.by_method == {}
        assert result.by_pattern == {}
        assert result.clusters == []
        assert result.top_unparsed == []

    def test_all_dates_parsed(self, tmp_path):
        """No gaps when all records have high confidence dates."""
        db_path = tmp_path / "all_parsed.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_1')"
        )
        conn.execute(
            """INSERT INTO imprints
               (record_id, place_raw, place_norm, place_confidence, place_method,
                date_raw, date_label, date_start, date_end,
                date_confidence, date_method,
                publisher_raw, publisher_norm, publisher_confidence, publisher_method,
                country_code)
               VALUES (1, 'Paris', 'paris', 0.99, 'alias_map',
                       '1650', '1650', 1650, 1650, 0.99, 'year_exact',
                       'Dupont', 'dupont', 0.99, 'alias_map', 'fr')"""
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
                role_raw, role_norm, role_confidence, role_method, authority_uri)
               VALUES (1, 'A', 'a', 0.99, 'exact',
                       'printer', 'printer', 0.99, 'exact', NULL)"""
        )
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias_dir"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        da = DateAgent(harness)

        result = da.analyze()
        assert result.total_dates == 1
        assert result.parsed_count == 1
        assert result.unparsed_count == 0
        assert result.top_unparsed == []

    def test_get_unparsed_empty_db(self, tmp_path):
        """get_unparsed() returns empty list on empty DB."""
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
        da = DateAgent(harness)
        results = da.get_unparsed()
        assert results == []

    def test_group_by_pattern_empty_db(self, tmp_path):
        """group_by_pattern() returns empty dict on empty DB."""
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
        da = DateAgent(harness)
        groups = da.group_by_pattern()
        assert groups == {}

    def test_all_high_confidence_no_gaps(self, tmp_path):
        """No gaps returned when all dates are high confidence."""
        db_path = tmp_path / "high_conf.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)

        for i in range(1, 4):
            conn.execute(
                "INSERT INTO records (id, mms_id) VALUES (?, ?)",
                (i, f"MMS_{i}"),
            )
            conn.execute(
                """INSERT INTO imprints
                   (record_id, place_raw, place_norm, place_confidence, place_method,
                    date_raw, date_label, date_start, date_end,
                    date_confidence, date_method,
                    publisher_raw, publisher_norm, publisher_confidence,
                    publisher_method, country_code)
                   VALUES (?, 'P', 'p', 0.99, 'm',
                           ?, ?, ?, ?, 0.99, 'year_exact',
                           'X', 'x', 0.99, 'm', 'fr')""",
                (i, f"{1600 + i}", f"{1600 + i}", 1600 + i, 1600 + i),
            )
            conn.execute(
                """INSERT INTO agents
                   (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
                    role_raw, role_norm, role_confidence, role_method, authority_uri)
                   VALUES (?, 'A', 'a', 0.99, 'exact',
                           'r', 'r', 0.99, 'exact', NULL)""",
                (i,),
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
        da = DateAgent(harness)

        unparsed = da.get_unparsed()
        assert unparsed == []

        groups = da.group_by_pattern()
        assert groups == {}

        result = da.analyze()
        assert result.parsed_count == 3
        assert result.unparsed_count == 0


# ---------------------------------------------------------------------------
# Tests: _mapping_to_proposed_date (static method)
# ---------------------------------------------------------------------------


class TestMappingToProposedDate:
    """Tests for the static _mapping_to_proposed_date helper."""

    def test_range_extraction(self):
        """Extracts year range from canonical_value."""
        mapping = ProposedMapping(
            raw_value="[17--?]",
            canonical_value="1700-1799",
            confidence=0.70,
            reasoning="Century range",
            evidence_sources=[],
            field="date",
        )
        result = DateAgent._mapping_to_proposed_date("[17--?]", mapping)
        assert result.date_start == 1700
        assert result.date_end == 1799

    def test_single_year_extraction(self):
        """Extracts single year from canonical_value."""
        mapping = ProposedMapping(
            raw_value="MDCCCX",
            canonical_value="1810",
            confidence=0.90,
            reasoning="Roman numeral",
            evidence_sources=[],
            field="date",
        )
        result = DateAgent._mapping_to_proposed_date("MDCCCX", mapping)
        assert result.date_start == 1810
        assert result.date_end == 1810

    def test_json_response_parsing(self):
        """Parses JSON-formatted canonical_value."""
        json_str = json.dumps({
            "date_start": 1700,
            "date_end": 1799,
            "method": "llm_proposed",
            "confidence": 0.75,
            "reasoning": "18th century",
        })
        mapping = ProposedMapping(
            raw_value="[17--?]",
            canonical_value=json_str,
            confidence=0.75,
            reasoning="from json",
            evidence_sources=[],
            field="date",
        )
        result = DateAgent._mapping_to_proposed_date("[17--?]", mapping)
        assert result.date_start == 1700
        assert result.date_end == 1799
        assert result.method == "llm_proposed"

    def test_unparseable_returns_none(self):
        """Unparseable canonical_value gives None dates."""
        mapping = ProposedMapping(
            raw_value="???",
            canonical_value="cannot determine",
            confidence=0.10,
            reasoning="Unknown",
            evidence_sources=[],
            field="date",
        )
        result = DateAgent._mapping_to_proposed_date("???", mapping)
        assert result.date_start is None
        assert result.date_end is None
        assert result.confidence == 0.10

    def test_invalid_year_out_of_range(self):
        """Years outside 1000-2100 not extracted."""
        mapping = ProposedMapping(
            raw_value="ancient",
            canonical_value="500",
            confidence=0.30,
            reasoning="Too early",
            evidence_sources=[],
            field="date",
        )
        result = DateAgent._mapping_to_proposed_date("ancient", mapping)
        assert result.date_start is None
        assert result.date_end is None
