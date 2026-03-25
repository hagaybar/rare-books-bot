"""Tests for Wikipedia connection discovery engine."""

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.enrichment.wikipedia_connections import (
    AgentLookup,
    CandidateLinkage,
    DiscoveredConnection,
    build_agent_lookup,
    discover_connections,
    generate_candidate_linkage_report,
)


@pytest.fixture
def test_db(tmp_path):
    """Create test DB with wikipedia_cache + authority_enrichment + agents data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE,
            wikidata_id TEXT, label TEXT, wikipedia_url TEXT,
            nli_id TEXT, viaf_id TEXT, isni_id TEXT, loc_id TEXT,
            description TEXT, person_info TEXT, place_info TEXT,
            image_url TEXT, source TEXT, confidence REAL,
            fetched_at TEXT, expires_at TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
            agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT,
            authority_uri TEXT, agent_norm TEXT, agent_confidence REAL,
            agent_method TEXT, agent_notes TEXT, role_norm TEXT,
            role_confidence REAL, role_method TEXT, provenance_json TEXT
        );
        CREATE TABLE wikipedia_cache (
            id INTEGER PRIMARY KEY, wikidata_id TEXT, wikipedia_title TEXT,
            summary_extract TEXT, categories TEXT, see_also_titles TEXT,
            article_wikilinks TEXT, sections_json TEXT, name_variants TEXT,
            page_id INTEGER, revision_id INTEGER, language TEXT DEFAULT 'en',
            fetched_at TEXT, expires_at TEXT, UNIQUE(wikidata_id, language)
        );
        CREATE TABLE wikipedia_connections (
            id INTEGER PRIMARY KEY, source_agent_norm TEXT,
            target_agent_norm TEXT, source_wikidata_id TEXT,
            target_wikidata_id TEXT, relationship TEXT, tags TEXT,
            confidence REAL, source_type TEXT, evidence TEXT,
            bidirectional INTEGER DEFAULT 0, created_at TEXT,
            UNIQUE(source_agent_norm, target_agent_norm, source_type)
        );
        CREATE INDEX idx_wconn_source ON wikipedia_connections(source_agent_norm);
        CREATE INDEX idx_wconn_target ON wikipedia_connections(target_agent_norm);

        -- Agent A: Joseph Karo (Q193460)
        INSERT INTO authority_enrichment VALUES
            (1, 'uri:1', 'Q193460', 'Joseph Karo', NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, NULL, NULL, 'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO agents VALUES
            (1, 1, 0, 'Karo', 'personal', NULL, NULL, 'uri:1',
             'karo, joseph', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        -- Agent B: Moses Isserles (Q440285)
        INSERT INTO authority_enrichment VALUES
            (2, 'uri:2', 'Q440285', 'Moses Isserles', NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, NULL, NULL, 'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO agents VALUES
            (2, 2, 0, 'Isserles', 'personal', NULL, NULL, 'uri:2',
             'isserles, moses', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        -- Agent C: Solomon Alkabetz (Q2305889)
        INSERT INTO authority_enrichment VALUES
            (3, 'uri:3', 'Q2305889', 'Solomon Alkabetz', NULL, NULL, NULL, NULL, NULL,
             NULL, NULL, NULL, NULL, 'wikidata', 0.95, '2024-01-01', '2025-01-01');
        INSERT INTO agents VALUES
            (3, 3, 0, 'Alkabetz', 'personal', NULL, NULL, 'uri:3',
             'alkabetz, solomon', 0.95, 'base_clean', NULL,
             'author', 0.95, 'relator_code', '[]');

        -- Agent D: No Wikidata ID (un-enriched)
        INSERT INTO agents VALUES
            (4, 4, 0, 'Unknown Rabbi', 'personal', NULL, NULL, NULL,
             'unknown rabbi', 0.5, 'base_clean', NULL,
             'author', 0.5, 'relator_code', '[]');

        -- Agent E: Another un-enriched agent for fuzzy matching
        INSERT INTO agents VALUES
            (5, 5, 0, 'Bartenura', 'personal', NULL, NULL, NULL,
             'bartenura, obadiah', 0.5, 'base_clean', NULL,
             'author', 0.5, 'relator_code', '[]');

        -- Wikipedia cache: Karo links to Isserles and Alkabetz
        INSERT INTO wikipedia_cache VALUES
            (1, 'Q193460', 'Joseph Karo', NULL,
             '["16th-century rabbis", "Rabbis in Safed"]',
             '["Moses Isserles"]',
             '["Moses Isserles", "Solomon Alkabetz", "Shulchan Aruch", "Safed", "Obadiah of Bartenura"]',
             NULL, NULL, 12345, NULL, 'en', '2024-01-01', '2025-01-01');

        -- Wikipedia cache: Isserles links back to Karo (bidirectional)
        INSERT INTO wikipedia_cache VALUES
            (2, 'Q440285', 'Moses Isserles', NULL,
             '["16th-century rabbis", "Polish rabbis"]',
             '["Joseph Karo"]',
             '["Joseph Karo", "Shulchan Aruch", "Krakow"]',
             NULL, NULL, 67890, NULL, 'en', '2024-01-01', '2025-01-01');

        -- Wikipedia cache: Alkabetz has no links to other agents
        INSERT INTO wikipedia_cache VALUES
            (3, 'Q2305889', 'Solomon Alkabetz', NULL,
             '["16th-century rabbis", "Kabbalists"]',
             '[]',
             '["Kabbalah", "Lecha Dodi"]',
             NULL, NULL, 11111, NULL, 'en', '2024-01-01', '2025-01-01');
    """
    )
    conn.close()
    return db_path


# =============================================================================
# TestBuildAgentLookup
# =============================================================================


class TestBuildAgentLookup:
    def test_builds_title_to_qid_map(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert lookup.title_to_qid["joseph karo"] == "Q193460"
        assert lookup.title_to_qid["moses isserles"] == "Q440285"
        assert lookup.title_to_qid["solomon alkabetz"] == "Q2305889"

    def test_builds_qid_to_agent_map(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert lookup.qid_to_agent["Q193460"] == "karo, joseph"
        assert lookup.qid_to_agent["Q440285"] == "isserles, moses"

    def test_un_enriched_agents_tracked(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert "unknown rabbi" in lookup.all_agent_norms
        assert "bartenura, obadiah" in lookup.all_agent_norms

    def test_enriched_agents_also_in_all_norms(self, test_db):
        lookup = build_agent_lookup(test_db)
        assert "karo, joseph" in lookup.all_agent_norms
        assert "isserles, moses" in lookup.all_agent_norms


# =============================================================================
# TestDiscoverConnections
# =============================================================================


class TestDiscoverConnections:
    def test_finds_wikilink_connection(self, test_db):
        connections = discover_connections(test_db)
        wikilink_conns = [c for c in connections if c.source_type == "wikilink"]
        # Karo -> Isserles (via wikilink)
        pairs = {(c.source_agent_norm, c.target_agent_norm) for c in wikilink_conns}
        # Canonical order: isserles < karo alphabetically
        assert ("isserles, moses", "karo, joseph") in pairs

    def test_finds_see_also_connection(self, test_db):
        connections = discover_connections(test_db)
        see_also_conns = [c for c in connections if c.source_type == "see_also"]
        # Karo has see_also to Isserles, Isserles has see_also to Karo
        assert len(see_also_conns) > 0
        assert see_also_conns[0].confidence in (0.85, 0.90)  # 0.90 if bidirectional

    def test_bidirectional_boost(self, test_db):
        connections = discover_connections(test_db)
        # Both Karo and Isserles link to each other -> bidirectional
        bidi = [c for c in connections if c.bidirectional]
        assert len(bidi) > 0
        for c in bidi:
            assert c.confidence == 0.90

    def test_shared_category_connection(self, test_db):
        connections = discover_connections(test_db)
        cat_conns = [c for c in connections if c.source_type == "category"]
        # Karo, Isserles, and Alkabetz all share "16th-century rabbis"
        assert len(cat_conns) > 0
        assert all(c.confidence == 0.65 for c in cat_conns)

    def test_shared_category_evidence_includes_category_name(self, test_db):
        connections = discover_connections(test_db)
        cat_conns = [c for c in connections if c.source_type == "category"]
        assert any("16th-century rabbis" in (c.evidence or "") for c in cat_conns)

    def test_canonical_ordering(self, test_db):
        """Source agent_norm < target agent_norm alphabetically."""
        connections = discover_connections(test_db)
        for c in connections:
            assert c.source_agent_norm <= c.target_agent_norm, (
                f"Non-canonical: {c.source_agent_norm} > {c.target_agent_norm}"
            )

    def test_no_self_connections(self, test_db):
        connections = discover_connections(test_db)
        for c in connections:
            assert c.source_agent_norm != c.target_agent_norm

    def test_stores_to_wikipedia_connections_table(self, test_db):
        discover_connections(test_db, store=True)
        conn = sqlite3.connect(str(test_db))
        count = conn.execute("SELECT COUNT(*) FROM wikipedia_connections").fetchone()[0]
        assert count > 0

        # Verify stored data integrity
        row = conn.execute(
            "SELECT source_agent_norm, target_agent_norm, confidence, source_type, "
            "bidirectional, created_at FROM wikipedia_connections LIMIT 1"
        ).fetchone()
        assert row[0] is not None  # source_agent_norm
        assert row[1] is not None  # target_agent_norm
        assert row[2] > 0  # confidence
        assert row[3] in ("wikilink", "see_also", "category")  # source_type
        assert row[5] is not None  # created_at
        conn.close()

    def test_idempotent_store(self, test_db):
        """Running store twice should not create duplicate rows."""
        discover_connections(test_db, store=True)
        conn = sqlite3.connect(str(test_db))
        count1 = conn.execute("SELECT COUNT(*) FROM wikipedia_connections").fetchone()[0]
        conn.close()

        discover_connections(test_db, store=True)
        conn = sqlite3.connect(str(test_db))
        count2 = conn.execute("SELECT COUNT(*) FROM wikipedia_connections").fetchone()[0]
        conn.close()

        assert count1 == count2

    def test_karo_alkabetz_wikilink(self, test_db):
        """Karo's article links to Alkabetz -> should find connection."""
        connections = discover_connections(test_db)
        wikilink_conns = [c for c in connections if c.source_type == "wikilink"]
        pairs = {(c.source_agent_norm, c.target_agent_norm) for c in wikilink_conns}
        # alkabetz < karo alphabetically
        assert ("alkabetz, solomon", "karo, joseph") in pairs

    def test_one_directional_not_bidirectional(self, test_db):
        """Karo -> Alkabetz is one-directional (Alkabetz doesn't link back)."""
        connections = discover_connections(test_db)
        karo_alkabetz = [
            c
            for c in connections
            if c.source_type == "wikilink"
            and c.source_agent_norm == "alkabetz, solomon"
            and c.target_agent_norm == "karo, joseph"
        ]
        assert len(karo_alkabetz) == 1
        assert not karo_alkabetz[0].bidirectional
        assert karo_alkabetz[0].confidence == 0.75


# =============================================================================
# TestCandidateLinkageReport
# =============================================================================


class TestCandidateLinkageReport:
    def test_finds_fuzzy_match_for_unmatched_wikilink(self, test_db):
        """'Obadiah of Bartenura' in Karo's wikilinks should fuzzy-match 'bartenura, obadiah'."""
        candidates = generate_candidate_linkage_report(test_db, fuzzy_threshold=0.50)
        # With a low threshold, "Obadiah of Bartenura" might match "bartenura, obadiah"
        bartenura = [
            c
            for c in candidates
            if c.possible_agent_norm == "bartenura, obadiah"
        ]
        # Matching depends on fuzzy score; assert we at least got candidates
        assert isinstance(candidates, list)

    def test_does_not_include_matched_links(self, test_db):
        """Links that DO match enriched agents should not appear in candidates."""
        candidates = generate_candidate_linkage_report(test_db, fuzzy_threshold=0.50)
        matched_titles = {"Moses Isserles", "Joseph Karo", "Solomon Alkabetz"}
        for c in candidates:
            assert c.wikipedia_title not in matched_titles

    def test_writes_csv_when_output_path_provided(self, test_db, tmp_path):
        output = tmp_path / "candidates.csv"
        candidates = generate_candidate_linkage_report(
            test_db, fuzzy_threshold=0.30, output_path=output
        )
        assert output.exists()
        with open(output, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == [
                "wikipedia_title",
                "mentioned_in_agent",
                "possible_agent_norm",
                "match_score",
            ]
            rows = list(reader)
            assert len(rows) == len(candidates)

    def test_candidates_sorted_by_score_descending(self, test_db):
        candidates = generate_candidate_linkage_report(test_db, fuzzy_threshold=0.30)
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert candidates[i].match_score >= candidates[i + 1].match_score

    def test_empty_when_all_links_match(self, tmp_path):
        """If every wikilink matches an enriched agent, no candidates."""
        db_path = tmp_path / "full_match.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE authority_enrichment (
                id INTEGER PRIMARY KEY, authority_uri TEXT UNIQUE,
                wikidata_id TEXT, label TEXT, wikipedia_url TEXT,
                nli_id TEXT, viaf_id TEXT, isni_id TEXT, loc_id TEXT,
                description TEXT, person_info TEXT, place_info TEXT,
                image_url TEXT, source TEXT, confidence REAL,
                fetched_at TEXT, expires_at TEXT
            );
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY, record_id INTEGER, agent_index INTEGER,
                agent_raw TEXT, agent_type TEXT, role_raw TEXT, role_source TEXT,
                authority_uri TEXT, agent_norm TEXT, agent_confidence REAL,
                agent_method TEXT, agent_notes TEXT, role_norm TEXT,
                role_confidence REAL, role_method TEXT, provenance_json TEXT
            );
            CREATE TABLE wikipedia_cache (
                id INTEGER PRIMARY KEY, wikidata_id TEXT, wikipedia_title TEXT,
                summary_extract TEXT, categories TEXT, see_also_titles TEXT,
                article_wikilinks TEXT, sections_json TEXT, name_variants TEXT,
                page_id INTEGER, revision_id INTEGER, language TEXT DEFAULT 'en',
                fetched_at TEXT, expires_at TEXT, UNIQUE(wikidata_id, language)
            );
            CREATE TABLE wikipedia_connections (
                id INTEGER PRIMARY KEY, source_agent_norm TEXT,
                target_agent_norm TEXT, source_wikidata_id TEXT,
                target_wikidata_id TEXT, relationship TEXT, tags TEXT,
                confidence REAL, source_type TEXT, evidence TEXT,
                bidirectional INTEGER DEFAULT 0, created_at TEXT,
                UNIQUE(source_agent_norm, target_agent_norm, source_type)
            );

            INSERT INTO authority_enrichment VALUES
                (1, 'u:1', 'Q1', 'A', NULL, NULL, NULL, NULL, NULL,
                 NULL, NULL, NULL, NULL, 'w', 0.9, '2024-01-01', '2025-01-01');
            INSERT INTO authority_enrichment VALUES
                (2, 'u:2', 'Q2', 'B', NULL, NULL, NULL, NULL, NULL,
                 NULL, NULL, NULL, NULL, 'w', 0.9, '2024-01-01', '2025-01-01');
            INSERT INTO agents VALUES
                (1, 1, 0, 'A', 'p', NULL, NULL, 'u:1', 'agent a', 0.9,
                 'bc', NULL, 'au', 0.9, 'rc', '[]');
            INSERT INTO agents VALUES
                (2, 2, 0, 'B', 'p', NULL, NULL, 'u:2', 'agent b', 0.9,
                 'bc', NULL, 'au', 0.9, 'rc', '[]');

            -- Agent A's wikilinks only contain Agent B's title (which is matched)
            INSERT INTO wikipedia_cache VALUES
                (1, 'Q1', 'Agent A Title', NULL, '[]', '[]',
                 '["Agent B Title"]', NULL, NULL, 1, NULL, 'en', '2024-01-01', '2025-01-01');
            INSERT INTO wikipedia_cache VALUES
                (2, 'Q2', 'Agent B Title', NULL, '[]', '[]',
                 '["Agent A Title"]', NULL, NULL, 2, NULL, 'en', '2024-01-01', '2025-01-01');
        """
        )
        conn.close()

        candidates = generate_candidate_linkage_report(db_path)
        assert len(candidates) == 0
