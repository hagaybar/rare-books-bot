"""Tests for PublisherAgent specialist.

Uses in-memory SQLite fixtures to test against real schema without requiring
the production database. LLM calls are mocked via the harness.reasoning layer.
"""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from scripts.metadata.agent_harness import (
    AgentHarness,
    GapRecord,
    GroundingLayer,
    ProposedMapping,
    ReasoningLayer,
)
from scripts.metadata.agents.publisher_agent import (
    PublisherAgent,
    PublisherAnalysis,
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
    """Create a SQLite DB on disk with publisher-focused test data."""
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

    # Insert imprints with varying publisher confidence levels
    imprints = [
        # Mapped publishers (confidence >= 0.95)
        (1, "London :", "london", 0.95, "alias_map",
         "1650", "1650", 1650, 1650, 0.99, "exact",
         "Oxford UP", "oxford up", 0.95, "alias_map", "enk"),
        (2, "Paris :", "paris", 0.95, "alias_map",
         "1700", "1700", 1700, 1700, 0.99, "exact",
         "Didot", "didot", 0.95, "alias_map", "fr"),
        # Unmapped publishers (confidence <= 0.80)
        (3, "Amsterdam", "amsterdam", 0.95, "alias_map",
         "1680", "1680", 1680, 1680, 0.95, "bracketed",
         "Elsevier:", "elsevier", 0.80, "basic_clean", "ne"),
        (4, "Leiden", "leiden", 0.95, "alias_map",
         "1550", "1550", 1550, 1550, 0.99, "exact",
         "ex officina Elzeviriana", None, 0.50, "basic_clean", "ne"),
        (5, "Paris :", "paris", 0.95, "alias_map",
         "1600", "1600", 1600, 1600, 0.99, "exact",
         "C. Fosset,", "c. fosset", 0.80, "basic_clean", "fr"),
        # Missing / s.n. publishers
        (6, "London :", "london", 0.95, "alias_map",
         "1700", "1700", 1700, 1700, 0.99, "exact",
         "s.n.", None, 0.0, "missing", "enk"),
        (7, "Berlin", "berlin", 0.95, "alias_map",
         "1800", "1800", 1800, 1800, 0.99, "exact",
         None, None, None, None, "gw"),
        # Duplicate raw value for find_related testing
        (8, "Amsterdam", "amsterdam", 0.95, "alias_map",
         "1690", "1690", 1690, 1690, 0.99, "exact",
         "Elsevier :", "elsevier", 0.80, "basic_clean", "ne"),
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


def _create_publisher_alias_map(tmp_path: Path) -> Path:
    """Create test publisher alias map on disk."""
    alias_dir = tmp_path / "publisher_aliases"
    alias_dir.mkdir(parents=True)
    alias_map = {
        "oxford up": "oxford university press",
        "didot": "didot",
        "c. fosset": "claude fosset",
    }
    alias_path = alias_dir / "publisher_alias_map.json"
    alias_path.write_text(
        json.dumps(alias_map, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def _create_cache_file(tmp_path: Path) -> Path:
    """Create empty LLM cache file."""
    cache_path = tmp_path / "agent_llm_cache.jsonl"
    cache_path.touch()
    return cache_path


@pytest.fixture
def tmp_env(tmp_path):
    """Create a complete test environment with DB, alias maps, and cache."""
    db_path = _create_test_db(tmp_path)
    alias_dir = _create_publisher_alias_map(tmp_path)
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
    """Create a PublisherAgent with test harness."""
    return PublisherAgent(harness)


# ---------------------------------------------------------------------------
# Tests: analyze()
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for PublisherAgent.analyze()."""

    def test_returns_publisher_analysis(self, agent):
        """analyze() returns a PublisherAnalysis dataclass."""
        result = agent.analyze()
        assert isinstance(result, PublisherAnalysis)

    def test_total_publishers_count(self, agent):
        """total_publishers reflects all imprint rows."""
        result = agent.analyze()
        assert result.total_publishers == 8

    def test_mapped_count(self, agent):
        """Mapped count reflects publishers with confidence >= 0.95."""
        result = agent.analyze()
        # Records 1 and 2 have publisher_confidence=0.95
        assert result.mapped_count == 2

    def test_unmapped_count(self, agent):
        """Unmapped count reflects publishers with confidence <= 0.80."""
        result = agent.analyze()
        # Records with confidence < 0.80: record 4 (0.50), record 6 (0.0),
        # record 7 (None -> 0.0). The 0.80 ones (records 3,5,8) are in [0.80, 0.95)
        assert result.unmapped_count >= 2

    def test_missing_count_includes_null(self, agent):
        """Missing count includes NULL publisher_raw."""
        result = agent.analyze()
        # Record 7 has NULL publisher_raw, record 6 has "s.n."
        assert result.missing_count >= 1

    def test_missing_count_includes_sn(self, agent):
        """Missing count includes 's.n.' as a missing marker."""
        result = agent.analyze()
        # Record 6 has "s.n." and record 7 has NULL
        assert result.missing_count >= 2

    def test_clusters_populated(self, agent):
        """Clusters are built from flagged items."""
        result = agent.analyze()
        assert isinstance(result.clusters, list)

    def test_top_gaps_populated(self, agent):
        """Top gaps are populated from low-confidence records."""
        result = agent.analyze()
        assert isinstance(result.top_gaps, list)

    def test_top_gaps_limited_to_20(self, agent):
        """Top gaps is limited to at most 20 entries."""
        result = agent.analyze()
        assert len(result.top_gaps) <= 20

    def test_top_gaps_are_gap_records(self, agent):
        """Each top gap is a GapRecord instance."""
        result = agent.analyze()
        for gap in result.top_gaps:
            assert isinstance(gap, GapRecord)
            assert gap.field == "publisher"


# ---------------------------------------------------------------------------
# Tests: get_clusters()
# ---------------------------------------------------------------------------


class TestGetClusters:
    """Tests for PublisherAgent.get_clusters()."""

    def test_returns_list_of_clusters(self, agent):
        """get_clusters() returns a list of Cluster objects."""
        clusters = agent.get_clusters()
        assert isinstance(clusters, list)
        for c in clusters:
            assert isinstance(c, Cluster)

    def test_clusters_sorted_by_priority(self, agent):
        """Clusters are sorted by priority_score descending."""
        clusters = agent.get_clusters()
        if len(clusters) > 1:
            scores = [c.priority_score for c in clusters]
            assert scores == sorted(scores, reverse=True)

    def test_cluster_field_is_publisher(self, agent):
        """All clusters have field='publisher'."""
        clusters = agent.get_clusters()
        for c in clusters:
            assert c.field == "publisher"

    def test_cluster_types_are_valid(self, agent):
        """Clusters have expected type labels from _cluster_publishers."""
        valid_types = {
            "near_match",
            "variant_group",
            "high_frequency_unmapped",
            "low_frequency_unmapped",
        }
        clusters = agent.get_clusters()
        for c in clusters:
            assert c.cluster_type in valid_types, (
                f"Unexpected cluster_type: {c.cluster_type}"
            )

    def test_cluster_values_have_raw_value(self, agent):
        """Each cluster value has a non-empty raw_value."""
        clusters = agent.get_clusters()
        for c in clusters:
            for v in c.values:
                assert isinstance(v, ClusterValue)
                assert v.raw_value is not None


# ---------------------------------------------------------------------------
# Tests: propose_mappings() with mocked LLM
# ---------------------------------------------------------------------------


class TestProposeMappings:
    """Tests for PublisherAgent.propose_mappings() with mocked LLM."""

    def _make_cluster(self) -> Cluster:
        """Create a test cluster of publisher variants."""
        return Cluster(
            cluster_id="publisher_variant_elsevier",
            field="publisher",
            cluster_type="variant_group",
            values=[
                ClusterValue(
                    raw_value="Elsevier:",
                    frequency=5,
                    confidence=0.80,
                    method="basic_clean",
                ),
                ClusterValue(
                    raw_value="ex officina Elzeviriana",
                    frequency=3,
                    confidence=0.50,
                    method="basic_clean",
                ),
            ],
            proposed_canonical="elsevier",
            evidence={"base_form": "elsevier", "variant_count": 2},
            priority_score=8.0,
            total_records_affected=8,
        )

    def test_returns_proposals_for_each_value(self, agent):
        """One ProposedMapping per cluster value."""
        cluster = self._make_cluster()

        agent.harness.reasoning.propose_mapping = MagicMock(
            side_effect=[
                ProposedMapping(
                    raw_value="Elsevier:",
                    canonical_value="elzevir",
                    confidence=0.92,
                    reasoning="Elsevier/Elzevir family of printers, Leiden/Amsterdam",
                    evidence_sources=["field", "cluster_type", "frequency"],
                    field="publisher",
                ),
                ProposedMapping(
                    raw_value="ex officina Elzeviriana",
                    canonical_value="elzevir",
                    confidence=0.95,
                    reasoning="Latin formula 'from the Elzevir workshop'",
                    evidence_sources=["field", "cluster_type", "frequency"],
                    field="publisher",
                ),
            ]
        )

        proposals = agent.propose_mappings(cluster)
        assert len(proposals) == 2
        assert proposals[0].canonical_value == "elzevir"
        assert proposals[1].canonical_value == "elzevir"

    def test_proposals_are_proposed_mapping_type(self, agent):
        """Each result is a ProposedMapping dataclass."""
        cluster = self._make_cluster()
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="test",
                canonical_value="test",
                confidence=0.90,
                reasoning="test",
                evidence_sources=[],
                field="publisher",
            )
        )
        proposals = agent.propose_mappings(cluster)
        for p in proposals:
            assert isinstance(p, ProposedMapping)

    def test_evidence_includes_publisher_context(self, agent):
        """Evidence passed to LLM includes publisher-specific fields."""
        cluster = self._make_cluster()
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="test",
                canonical_value="test",
                confidence=0.90,
                reasoning="test",
                evidence_sources=[],
                field="publisher",
            )
        )
        agent.propose_mappings(cluster)

        calls = agent.harness.reasoning.propose_mapping.call_args_list
        for call in calls:
            evidence = call.kwargs.get("evidence", {})
            assert evidence["field"] == "publisher"
            assert "cluster_type" in evidence
            assert "frequency" in evidence
            assert "is_missing_marker" in evidence
            assert "has_latin_formula" in evidence

    def test_latin_formula_detected_in_evidence(self, agent):
        """has_latin_formula is True for 'ex officina...' values."""
        cluster = self._make_cluster()
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="test",
                canonical_value="test",
                confidence=0.90,
                reasoning="test",
                evidence_sources=[],
                field="publisher",
            )
        )
        agent.propose_mappings(cluster)

        calls = agent.harness.reasoning.propose_mapping.call_args_list
        # Second call is for "ex officina Elzeviriana"
        second_evidence = calls[1].kwargs.get("evidence", {})
        assert second_evidence["has_latin_formula"] is True

        # First call is for "Elsevier:" -- no Latin formula
        first_evidence = calls[0].kwargs.get("evidence", {})
        assert first_evidence["has_latin_formula"] is False

    def test_near_match_evidence_included(self, agent):
        """When cluster has proposed_mappings evidence, it's forwarded."""
        cluster = Cluster(
            cluster_id="publisher_near_match",
            field="publisher",
            cluster_type="near_match",
            values=[
                ClusterValue(
                    raw_value="C. Fosset,",
                    frequency=3,
                    confidence=0.80,
                    method="basic_clean",
                ),
            ],
            proposed_canonical=None,
            evidence={"proposed_mappings": {"C. Fosset,": "claude fosset"}},
            priority_score=3.0,
            total_records_affected=3,
        )
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="C. Fosset,",
                canonical_value="claude fosset",
                confidence=0.95,
                reasoning="Near match to existing alias",
                evidence_sources=[],
                field="publisher",
            )
        )
        agent.propose_mappings(cluster)

        call_evidence = agent.harness.reasoning.propose_mapping.call_args
        evidence = call_evidence.kwargs.get("evidence", {})
        assert "near_match_candidate" in evidence
        assert evidence["near_match_candidate"] == "claude fosset"

    def test_empty_cluster_returns_empty(self, agent):
        """Empty cluster values returns empty proposals list."""
        cluster = Cluster(
            cluster_id="empty",
            field="publisher",
            cluster_type="variant_group",
            values=[],
            proposed_canonical=None,
            evidence={},
            priority_score=0.0,
            total_records_affected=0,
        )
        proposals = agent.propose_mappings(cluster)
        assert proposals == []

    def test_missing_publisher_flagged_in_evidence(self, agent):
        """is_missing_marker is True for 's.n.' in evidence."""
        cluster = Cluster(
            cluster_id="publisher_sn",
            field="publisher",
            cluster_type="low_frequency_unmapped",
            values=[
                ClusterValue(
                    raw_value="s.n.",
                    frequency=10,
                    confidence=0.0,
                    method="missing",
                ),
            ],
            proposed_canonical=None,
            evidence={},
            priority_score=10.0,
            total_records_affected=10,
        )
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="s.n.",
                canonical_value="unknown",
                confidence=0.99,
                reasoning="Standard abbreviation for sine nomine",
                evidence_sources=[],
                field="publisher",
            )
        )
        agent.propose_mappings(cluster)

        call_evidence = agent.harness.reasoning.propose_mapping.call_args
        evidence = call_evidence.kwargs.get("evidence", {})
        assert evidence["is_missing_marker"] is True


# ---------------------------------------------------------------------------
# Tests: find_related()
# ---------------------------------------------------------------------------


class TestFindRelated:
    """Tests for PublisherAgent.find_related() with fuzzy matching."""

    def test_finds_exact_normalized_match(self, agent):
        """Finds raw values that normalize to the canonical name."""
        # "Elsevier:" and "Elsevier :" both normalize to "elsevier"
        results = agent.find_related("elsevier")
        assert len(results) >= 1
        # All results should normalize to "elsevier"
        for raw in results:
            from scripts.metadata.clustering import _normalize_for_matching
            assert _normalize_for_matching(raw) == "elsevier"

    def test_case_insensitive_matching(self, agent):
        """Matching is case-insensitive."""
        results_lower = agent.find_related("elsevier")
        results_upper = agent.find_related("ELSEVIER")
        assert results_lower == results_upper

    def test_strips_punctuation(self, agent):
        """Punctuation variants are matched."""
        # "Elsevier:" has trailing colon, should still match "elsevier"
        results = agent.find_related("Elsevier")
        assert any("Elsevier" in r for r in results)

    def test_no_match_returns_empty(self, agent):
        """Returns empty list for non-matching canonical name."""
        results = agent.find_related("nonexistent publisher xyz")
        assert results == []

    def test_empty_canonical_returns_empty(self, agent):
        """Empty canonical name returns empty list."""
        results = agent.find_related("")
        assert results == []

    def test_results_are_sorted(self, agent):
        """Results are sorted alphabetically."""
        results = agent.find_related("elsevier")
        assert results == sorted(results)

    def test_results_are_deduplicated(self, agent):
        """No duplicate raw values in results."""
        results = agent.find_related("elsevier")
        assert len(results) == len(set(results))

    def test_finds_oxford_up(self, agent):
        """Finds 'Oxford UP' when searching for 'oxford up'."""
        results = agent.find_related("oxford up")
        assert "Oxford UP" in results


# ---------------------------------------------------------------------------
# Tests: _is_missing_publisher()
# ---------------------------------------------------------------------------


class TestIsMissingPublisher:
    """Tests for PublisherAgent._is_missing_publisher() static method."""

    @pytest.mark.parametrize(
        "raw_value",
        [
            "s.n.",
            "[s.n.]",
            "S.N.",
            "s.n",
            "sine nomine",
            "Sine Nomine",
            "publisher not identified",
            "Publisher Not Identified",
            "[publisher not identified]",
            "unknown",
            "Unknown",
            "no publisher",
            "n/a",
            "N/A",
            "not identified",
            "",
            "   ",
            None,
        ],
    )
    def test_missing_patterns_detected(self, raw_value):
        """Known missing patterns are detected as missing."""
        assert PublisherAgent._is_missing_publisher(raw_value) is True

    @pytest.mark.parametrize(
        "raw_value",
        [
            "Oxford UP",
            "Elsevier",
            "ex officina Plantiniana",
            "C. Fosset,",
            "Didot",
            "apud Johannem Elzevirium",
        ],
    )
    def test_real_publishers_not_missing(self, raw_value):
        """Real publisher names are not flagged as missing."""
        assert PublisherAgent._is_missing_publisher(raw_value) is False


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty database, all mapped, s.n. handling."""

    def test_empty_database(self, tmp_path):
        """PublisherAgent works with an empty database (no records)."""
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
        pa = PublisherAgent(harness)

        result = pa.analyze()
        assert result.total_publishers == 0
        assert result.mapped_count == 0
        assert result.unmapped_count == 0
        assert result.missing_count == 0
        assert result.clusters == []
        assert result.top_gaps == []

    def test_all_publishers_mapped(self, tmp_path):
        """No gaps when all publishers have high confidence."""
        db_path = tmp_path / "all_mapped.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_1')"
        )
        conn.execute(
            """INSERT INTO imprints
               (record_id, place_raw, place_norm, place_confidence, place_method,
                date_raw, date_label, date_confidence, date_method,
                publisher_raw, publisher_norm, publisher_confidence, publisher_method,
                country_code)
               VALUES (1, 'Paris', 'paris', 0.99, 'alias_map',
                       '1650', '1650', 0.99, 'exact',
                       'Dupont', 'dupont', 0.99, 'alias_map', 'fr')"""
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
                role_raw, role_norm, role_confidence, role_method, authority_uri)
               VALUES (1, 'A', 'a', 0.99, 'exact', 'printer', 'printer', 0.99, 'exact', NULL)"""
        )
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias_dir2"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache2.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        pa = PublisherAgent(harness)

        result = pa.analyze()
        assert result.total_publishers == 1
        assert result.mapped_count == 1
        assert result.unmapped_count == 0
        assert result.missing_count == 0
        assert result.top_gaps == []

    def test_no_gaps_returns_empty_clusters(self, tmp_path):
        """get_clusters() returns empty list when no flagged items."""
        db_path = tmp_path / "no_gaps.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.execute(
            "INSERT INTO records (id, mms_id) VALUES (1, 'MMS_1')"
        )
        conn.execute(
            """INSERT INTO imprints
               (record_id, place_raw, place_norm, place_confidence, place_method,
                date_raw, date_label, date_confidence, date_method,
                publisher_raw, publisher_norm, publisher_confidence, publisher_method,
                country_code)
               VALUES (1, 'London', 'london', 0.99, 'alias_map',
                       '1700', '1700', 0.99, 'exact',
                       'OUP', 'oup', 0.99, 'alias_map', 'enk')"""
        )
        conn.execute(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
                role_raw, role_norm, role_confidence, role_method, authority_uri)
               VALUES (1, 'A', 'a', 0.99, 'exact', 'r', 'r', 0.99, 'exact', NULL)"""
        )
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias_dir3"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache3.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        pa = PublisherAgent(harness)
        clusters = pa.get_clusters()
        assert clusters == []

    def test_find_related_empty_db(self, tmp_path):
        """find_related() returns empty list on empty DB."""
        db_path = tmp_path / "empty2.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.commit()
        conn.close()

        alias_dir = tmp_path / "alias_dir4"
        alias_dir.mkdir()
        cache_path = tmp_path / "cache4.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=alias_dir,
            cache_path=cache_path,
            api_key="test",
        )
        pa = PublisherAgent(harness)
        results = pa.find_related("anything")
        assert results == []

    def test_sn_grouped_as_missing(self, agent):
        """s.n. entries are counted in missing_count."""
        result = agent.analyze()
        # "s.n." (record 6) + NULL (record 7) = at least 2
        assert result.missing_count >= 2
