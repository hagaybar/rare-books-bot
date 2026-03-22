"""Tests for PlaceAgent specialist.

Uses in-memory SQLite fixtures to test against real schema without requiring
the production database. LLM calls are mocked via the harness.reasoning layer.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.metadata.agent_harness import (
    AgentHarness,
    ProposedMapping,
)
from scripts.metadata.agents.place_agent import (
    PlaceAgent,
    PlaceAnalysis,
    _build_primo_url,
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
    """Create an in-memory-style SQLite DB on disk with test data."""
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

    # Insert imprints with varying confidence levels
    imprints = [
        # High confidence places (>= 0.95)
        (1, "Paris :", "paris", 0.95, "alias_map", "1650", "1650", 1650, 1650, 0.99, "exact", "C. Fosset,", "c. fosset", 0.80, "basic_clean", "fr"),
        (2, "London :", "london", 0.95, "alias_map", "1700", "1700", 1700, 1700, 0.99, "exact", "Oxford UP", "oxford up", 0.95, "alias_map", "enk"),
        # Medium confidence (0.80 - 0.95)
        (3, "Amstelodami", "amsterdam", 0.80, "basic_clean", "[1680]", "1680", 1680, 1680, 0.95, "bracketed", "Elsevier:", "elsevier", 0.80, "basic_clean", "ne"),
        # Low confidence (< 0.80) -- these are the gaps
        (4, "Lugduni Batavorum", None, 0.50, "basic_clean", "1550", "1550", 1550, 1550, 0.99, "exact", None, None, None, None, "ne"),
        (5, "ירושלים", None, 0.50, "basic_clean", "1890", "1890", 1890, 1890, 0.99, "exact", None, None, None, None, "is"),
        (6, "Argentorati", None, 0.50, "basic_clean", "1600", "1600", 1600, 1600, 0.99, "exact", None, None, None, None, "fr"),
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
        (1, "John Smith", "john smith", 0.90, "basic_clean", "printer", "printer", 0.95, "exact", None),
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


def _create_alias_map(tmp_path: Path) -> Path:
    """Create test place alias map on disk."""
    alias_dir = tmp_path / "place_aliases"
    alias_dir.mkdir(parents=True)
    alias_map = {
        "paris :": "paris",
        "london :": "london",
        "[amsterdam]": "amsterdam",
        "[amstelodami]": "amsterdam",
        "amstelodami": "amsterdam",
    }
    alias_path = alias_dir / "place_alias_map.json"
    alias_path.write_text(json.dumps(alias_map, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def _create_country_codes(tmp_path: Path) -> None:
    """Create test MARC country codes file."""
    codes = {
        "comment": "Test country codes",
        "source": "test",
        "last_updated": "2026-01-01",
        "codes": {
            "fr": "france",
            "enk": "england",
            "ne": "netherlands",
            "is": "israel",
            "gw": "germany",
            "it": "italy",
        },
    }
    codes_path = tmp_path / "marc_country_codes.json"
    codes_path.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")


def _create_cache_file(tmp_path: Path) -> Path:
    """Create empty LLM cache file."""
    cache_path = tmp_path / "agent_llm_cache.jsonl"
    cache_path.touch()
    return cache_path


@pytest.fixture
def tmp_env(tmp_path):
    """Create a complete test environment with DB, alias maps, and cache."""
    db_path = _create_test_db(tmp_path)
    alias_dir = _create_alias_map(tmp_path)
    _create_country_codes(tmp_path)
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
    """Create a PlaceAgent with test harness."""
    return PlaceAgent(harness)


# ---------------------------------------------------------------------------
# Tests: analyze()
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for PlaceAgent.analyze()."""

    def test_returns_place_analysis(self, agent):
        """analyze() returns a PlaceAnalysis dataclass."""
        result = agent.analyze()
        assert isinstance(result, PlaceAnalysis)

    def test_total_places_count(self, agent):
        """total_places reflects all imprint rows."""
        result = agent.analyze()
        assert result.total_places == 6

    def test_high_confidence_count(self, agent):
        """Records with confidence >= 0.95 counted as high."""
        result = agent.analyze()
        assert result.high_confidence_count == 2  # Paris=0.95, London=0.95

    def test_low_confidence_count(self, agent):
        """Records with confidence < 0.80 counted as low."""
        result = agent.analyze()
        # Lugduni=0.50, Jerusalem=0.50, Argentorati=0.50 = 3 low
        # Amstelodami=0.80 goes to medium
        assert result.low_confidence_count == 3

    def test_medium_confidence_count(self, agent):
        """Records with 0.80 <= confidence < 0.95 counted as medium."""
        result = agent.analyze()
        assert result.medium_confidence_count == 1  # Amstelodami=0.80

    def test_clusters_populated(self, agent):
        """Clusters are built from flagged items."""
        result = agent.analyze()
        assert isinstance(result.clusters, list)

    def test_top_gaps_populated(self, agent):
        """Top gaps are populated from low-confidence records."""
        result = agent.analyze()
        assert isinstance(result.top_gaps, list)
        assert len(result.top_gaps) > 0

    def test_top_gaps_limited_to_20(self, agent):
        """Top gaps is limited to at most 20 entries."""
        result = agent.analyze()
        assert len(result.top_gaps) <= 20

    def test_unmapped_count(self, agent):
        """Unmapped count reflects total frequency of flagged items."""
        result = agent.analyze()
        assert result.unmapped_count >= 0


# ---------------------------------------------------------------------------
# Tests: get_clusters()
# ---------------------------------------------------------------------------


class TestGetClusters:
    """Tests for PlaceAgent.get_clusters()."""

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

    def test_cluster_field_is_place(self, agent):
        """All clusters have field='place'."""
        clusters = agent.get_clusters()
        for c in clusters:
            assert c.field == "place"

    def test_cluster_types(self, agent):
        """Clusters have expected type labels."""
        valid_types = {
            "near_match",
            "hebrew_place_names",
            "arabic_place_names",
            "latin_place_names",
            "empty_place_values",
        }
        clusters = agent.get_clusters()
        for c in clusters:
            assert c.cluster_type in valid_types, (
                f"Unexpected cluster_type: {c.cluster_type}"
            )

    def test_hebrew_cluster_contains_hebrew_values(self, agent):
        """Hebrew cluster values contain Hebrew script characters."""
        clusters = agent.get_clusters()
        hebrew_clusters = [
            c for c in clusters if c.cluster_type == "hebrew_place_names"
        ]
        for hc in hebrew_clusters:
            for v in hc.values:
                assert any(
                    0x0590 <= ord(ch) <= 0x05FF for ch in v.raw_value
                ), f"Expected Hebrew chars in {v.raw_value!r}"

    def test_latin_cluster_contains_latin_values(self, agent):
        """Latin cluster values are Latin-script strings."""
        clusters = agent.get_clusters()
        latin_clusters = [
            c for c in clusters if c.cluster_type == "latin_place_names"
        ]
        for lc in latin_clusters:
            for v in lc.values:
                # Should have at least one alpha Latin character
                assert any(ch.isalpha() for ch in v.raw_value)


# ---------------------------------------------------------------------------
# Tests: propose_mappings() with mocked LLM
# ---------------------------------------------------------------------------


class TestProposeMappings:
    """Tests for PlaceAgent.propose_mappings() with mocked LLM."""

    def _make_cluster(self) -> Cluster:
        """Create a test cluster."""
        return Cluster(
            cluster_id="place_latin",
            field="place",
            cluster_type="latin_place_names",
            values=[
                ClusterValue(
                    raw_value="Lugduni Batavorum",
                    frequency=5,
                    confidence=0.50,
                    method="basic_clean",
                ),
                ClusterValue(
                    raw_value="Argentorati",
                    frequency=3,
                    confidence=0.50,
                    method="basic_clean",
                ),
            ],
            proposed_canonical=None,
            evidence={"script": "latin", "count": 2},
            priority_score=8.0,
            total_records_affected=8,
        )

    def test_returns_proposals_for_each_value(self, agent):
        """One ProposedMapping per cluster value."""
        cluster = self._make_cluster()

        # Mock the reasoning layer's propose_mapping
        agent.harness.reasoning.propose_mapping = MagicMock(
            side_effect=[
                ProposedMapping(
                    raw_value="Lugduni Batavorum",
                    canonical_value="leiden",
                    confidence=0.92,
                    reasoning="Latin genitive form of Leiden (Lugdunum Batavorum)",
                    evidence_sources=["field", "cluster_type", "country_codes", "frequency"],
                    field="place",
                ),
                ProposedMapping(
                    raw_value="Argentorati",
                    canonical_value="strasbourg",
                    confidence=0.95,
                    reasoning="Latin locative form of Strasbourg (Argentoratum)",
                    evidence_sources=["field", "cluster_type", "country_codes", "frequency"],
                    field="place",
                ),
            ]
        )

        proposals = agent.propose_mappings(cluster)
        assert len(proposals) == 2
        assert proposals[0].canonical_value == "leiden"
        assert proposals[1].canonical_value == "strasbourg"

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
                field="place",
            )
        )
        proposals = agent.propose_mappings(cluster)
        for p in proposals:
            assert isinstance(p, ProposedMapping)

    def test_evidence_includes_country_codes(self, agent):
        """Evidence passed to LLM includes country_codes."""
        cluster = self._make_cluster()
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="test",
                canonical_value="test",
                confidence=0.90,
                reasoning="test",
                evidence_sources=[],
                field="place",
            )
        )
        agent.propose_mappings(cluster)

        # Check the evidence dict passed to propose_mapping
        calls = agent.harness.reasoning.propose_mapping.call_args_list
        for call in calls:
            evidence = call.kwargs.get("evidence") or call[1].get("evidence")
            if evidence is None:
                # positional args
                evidence = call[0][2] if len(call[0]) > 2 else call.kwargs["evidence"]
            assert "country_codes" in evidence
            assert "cluster_type" in evidence
            assert evidence["field"] == "place"

    def test_near_match_evidence_included(self, agent):
        """When cluster has proposed_mappings in evidence, it's forwarded."""
        cluster = Cluster(
            cluster_id="place_near_match",
            field="place",
            cluster_type="near_match",
            values=[
                ClusterValue(
                    raw_value="Amstelodami",
                    frequency=3,
                    confidence=0.50,
                    method="basic_clean",
                ),
            ],
            proposed_canonical=None,
            evidence={"proposed_mappings": {"Amstelodami": "amsterdam"}},
            priority_score=3.0,
            total_records_affected=3,
        )
        agent.harness.reasoning.propose_mapping = MagicMock(
            return_value=ProposedMapping(
                raw_value="Amstelodami",
                canonical_value="amsterdam",
                confidence=0.95,
                reasoning="Latin form of Amsterdam",
                evidence_sources=[],
                field="place",
            )
        )
        agent.propose_mappings(cluster)

        call_evidence = agent.harness.reasoning.propose_mapping.call_args
        evidence = call_evidence.kwargs.get("evidence", {})
        assert "near_match_candidate" in evidence
        assert evidence["near_match_candidate"] == "amsterdam"

    def test_empty_cluster_returns_empty(self, agent):
        """Empty cluster values returns empty proposals list."""
        cluster = Cluster(
            cluster_id="empty",
            field="place",
            cluster_type="latin_place_names",
            values=[],
            proposed_canonical=None,
            evidence={},
            priority_score=0.0,
            total_records_affected=0,
        )
        proposals = agent.propose_mappings(cluster)
        assert proposals == []


# ---------------------------------------------------------------------------
# Tests: get_primo_links()
# ---------------------------------------------------------------------------


class TestGetPrimoLinks:
    """Tests for PlaceAgent.get_primo_links()."""

    def test_returns_urls_for_existing_place(self, agent):
        """Returns Primo URLs for records with matching place_raw."""
        urls = agent.get_primo_links("Paris :")
        assert len(urls) == 1
        assert "990001111110204146" in urls[0]
        assert "primo.exlibrisgroup.com" in urls[0]

    def test_url_contains_alma_prefix(self, agent):
        """Primo URL contains alma-prefixed docid."""
        urls = agent.get_primo_links("Paris :")
        assert "alma990001111110204146" in urls[0]

    def test_returns_empty_for_nonexistent_place(self, agent):
        """Returns empty list for non-matching place value."""
        urls = agent.get_primo_links("Nonexistent City")
        assert urls == []

    def test_returns_multiple_for_shared_place(self, tmp_path):
        """Multiple records with same place return multiple URLs."""
        db_path = tmp_path / "multi.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(_SCHEMA_DDL)
        conn.executemany(
            "INSERT INTO records (id, mms_id) VALUES (?, ?)",
            [(1, "MMS_A"), (2, "MMS_B")],
        )
        conn.executemany(
            """INSERT INTO imprints
               (record_id, place_raw, place_norm, place_confidence, place_method,
                date_raw, date_label, date_confidence, date_method,
                publisher_raw, publisher_norm, publisher_confidence, publisher_method,
                country_code)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (1, "Roma", "rome", 0.95, "alias_map", "1600", "1600", 0.99, "exact", None, None, None, None, "it"),
                (2, "Roma", "rome", 0.95, "alias_map", "1650", "1650", 0.99, "exact", None, None, None, None, "it"),
            ],
        )
        conn.executemany(
            """INSERT INTO agents
               (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
                role_raw, role_norm, role_confidence, role_method, authority_uri)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(1, "A", "a", 0.9, "m", "r", "r", 0.9, "m", None)],
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
        pa = PlaceAgent(harness)
        urls = pa.get_primo_links("Roma")
        assert len(urls) == 2
        assert "MMS_A" in urls[0] or "MMS_A" in urls[1]
        assert "MMS_B" in urls[0] or "MMS_B" in urls[1]


# ---------------------------------------------------------------------------
# Tests: country code cross-referencing
# ---------------------------------------------------------------------------


class TestCountryCodeCrossRef:
    """Tests for country code cross-referencing."""

    def test_known_code_returns_country(self, agent):
        """Known MARC code returns the country name."""
        result = agent.cross_reference_country_code("Paris :", "fr")
        assert result == "france"

    def test_unknown_code_returns_none(self, agent):
        """Unknown MARC code returns None."""
        result = agent.cross_reference_country_code("Somewhere", "zz")
        assert result is None

    def test_empty_code_returns_none(self, agent):
        """Empty country code returns None."""
        result = agent.cross_reference_country_code("Paris", "")
        assert result is None

    def test_country_codes_map_loaded(self, agent):
        """Country codes map is loaded from file."""
        codes = agent.get_country_codes_map()
        assert isinstance(codes, dict)
        assert "fr" in codes
        assert codes["fr"] == "france"

    def test_country_codes_cached(self, agent):
        """Country codes are cached after first load."""
        codes1 = agent.get_country_codes_map()
        codes2 = agent.get_country_codes_map()
        assert codes1 is codes2  # Same object reference

    def test_missing_country_codes_file(self, tmp_path):
        """Missing country codes file returns empty dict."""
        db_path = _create_test_db(tmp_path)
        # Point to dir without marc_country_codes.json
        empty_dir = tmp_path / "empty_normalization"
        empty_dir.mkdir()
        cache_path = tmp_path / "cache.jsonl"
        cache_path.touch()

        harness = AgentHarness(
            db_path=db_path,
            alias_map_dir=empty_dir,
            cache_path=cache_path,
            api_key="test",
        )
        pa = PlaceAgent(harness)
        codes = pa.get_country_codes_map()
        assert codes == {}

    def test_get_country_codes_for_value(self, agent):
        """Internal method returns country codes for a place value."""
        codes = agent._get_country_codes_for_value("Paris :")
        assert "fr" in codes

    def test_get_country_codes_for_nonexistent(self, agent):
        """Returns empty list for non-matching place."""
        codes = agent._get_country_codes_for_value("Nowhere")
        assert codes == []


# ---------------------------------------------------------------------------
# Tests: Primo URL builder
# ---------------------------------------------------------------------------


class TestBuildPrimoUrl:
    """Tests for the standalone _build_primo_url function."""

    def test_contains_mms_id(self):
        """URL contains the MMS ID."""
        url = _build_primo_url("990001234")
        assert "990001234" in url

    def test_contains_alma_prefix(self):
        """URL contains alma-prefixed docid."""
        url = _build_primo_url("990001234")
        assert "alma990001234" in url

    def test_base_url(self):
        """URL starts with expected Primo base."""
        url = _build_primo_url("990001234")
        assert url.startswith("https://tau.primo.exlibrisgroup.com")

    def test_contains_vid(self):
        """URL contains the VID parameter."""
        url = _build_primo_url("990001234")
        assert "972TAU_INST" in url


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases: empty database, no gaps, all high confidence."""

    def test_empty_database(self, tmp_path):
        """PlaceAgent works with an empty database (no records)."""
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
        pa = PlaceAgent(harness)

        result = pa.analyze()
        assert result.total_places == 0
        assert result.high_confidence_count == 0
        assert result.medium_confidence_count == 0
        assert result.low_confidence_count == 0
        assert result.clusters == []
        assert result.top_gaps == []

    def test_all_high_confidence(self, tmp_path):
        """No gaps when all records have high confidence."""
        db_path = tmp_path / "all_high.db"
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
        pa = PlaceAgent(harness)

        result = pa.analyze()
        assert result.total_places == 1
        assert result.high_confidence_count == 1
        assert result.low_confidence_count == 0
        assert result.unmapped_count == 0
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
        pa = PlaceAgent(harness)
        clusters = pa.get_clusters()
        assert clusters == []

    def test_primo_links_empty_db(self, tmp_path):
        """get_primo_links() returns empty list on empty DB."""
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
        pa = PlaceAgent(harness)
        urls = pa.get_primo_links("anything")
        assert urls == []
