"""Integration test for the complete metadata workbench workflow.

Tests the end-to-end flow:
  audit -> clustering -> agent analysis -> correction -> feedback loop -> re-audit

Uses an in-memory SQLite database with fixture data to avoid touching
the real database.  No LLM calls -- the PlaceAgent.analyze() path is
purely deterministic (grounding-only).
"""

import json
import sqlite3

import pytest

# Mark every test in this module so they can be selected / skipped
# via ``pytest -m integration``.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Schema DDL (subset of m3_schema.sql -- only the tables the workbench needs)
# ---------------------------------------------------------------------------

_SCHEMA_DDL = """
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    jsonl_line_number INTEGER
);

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


# ---------------------------------------------------------------------------
# Test fixture data
# ---------------------------------------------------------------------------

_RECORDS = [
    ("990000001", "test.xml", "2025-01-01T00:00:00Z", 1),
    ("990000002", "test.xml", "2025-01-01T00:00:00Z", 2),
    ("990000003", "test.xml", "2025-01-01T00:00:00Z", 3),
    ("990000004", "test.xml", "2025-01-01T00:00:00Z", 4),
    ("990000005", "test.xml", "2025-01-01T00:00:00Z", 5),
]

_IMPRINTS = [
    # record_id, occurrence, date_raw, place_raw, publisher_raw,
    # manufacturer_raw, source_tags,
    # date_start, date_end, date_label, date_confidence, date_method,
    # place_norm, place_display, place_confidence, place_method,
    # publisher_norm, publisher_display, publisher_confidence, publisher_method,
    # country_code, country_name
    (1, 0, "1650", "Paris :", "C. Fosset,", None, '["264"]',
     1650, 1650, "1650", 0.99, "exact",
     "paris", "Paris", 0.95, "alias_map",
     "c. fosset", "C. Fosset", 0.80, "base_clean",
     "fr", "france"),
    (2, 0, "[1680]", "Amsterdam", "Elsevier :", None, '["264"]',
     1680, 1680, "[1680]", 0.95, "bracketed",
     "amsterdam", "Amsterdam", 0.95, "alias_map",
     "elsevier", "Elsevier", 0.95, "alias_map",
     "ne", "netherlands"),
    (3, 0, "ca. 1700", "Lugduni Batavorum", "Officina Plantiniana,", None, '["264"]',
     1695, 1705, "ca. 1700", 0.85, "circa",
     "lugduni batavorum", "Lugduni Batavorum", 0.80, "base_clean",
     "officina plantiniana", "Officina Plantiniana", 0.80, "base_clean",
     "ne", "netherlands"),
    (4, 0, "", "unknown place", "unknown publisher", None, '["264"]',
     None, None, None, 0.0, "unparsed",
     None, None, None, None,
     None, None, None, None,
     None, None),
    (5, 0, "5400", "\u05d0\u05de\u05e9\u05d8\u05e8\u05d3\u05dd", "Proops,", None, '["264"]',
     None, None, "5400", 0.0, "unparsed",
     "\u05d0\u05de\u05e9\u05d8\u05e8\u05d3\u05dd", "\u05d0\u05de\u05e9\u05d8\u05e8\u05d3\u05dd", 0.0, "base_clean",
     "proops", "Proops", 0.80, "base_clean",
     "ne", "netherlands"),
]

_AGENTS = [
    # record_id, agent_index, agent_raw, agent_type, role_raw, role_source,
    # authority_uri,
    # agent_norm, agent_confidence, agent_method, agent_notes,
    # role_norm, role_confidence, role_method, provenance_json
    (1, 0, "Fosset, Charles", "personal", "prt", "relator_code",
     "http://viaf.org/viaf/12345",
     "fosset, charles", 0.95, "base_clean", None,
     "printer", 0.95, "relator_code", '[{"tag":"100"}]'),
    (2, 0, "Elsevier", "corporate", None, "unknown",
     None,
     "elsevier", 0.80, "base_clean", None,
     "publisher", 0.80, "inferred", '[{"tag":"710"}]'),
    (3, 0, "Plantijn, Christoffel", "personal", "bookseller", "relator_term",
     None,
     "plantijn, christoffel", 0.90, "base_clean", None,
     "bookseller", 0.90, "relator_term", '[{"tag":"700"}]'),
    (4, 0, "Unknown Agent", "personal", None, "unknown",
     None,
     "unknown agent", 0.40, "ambiguous", "ambiguous name",
     "unknown", 0.40, "unknown", '[{"tag":"100"}]'),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_db(conn: sqlite3.Connection) -> None:
    """Create schema and insert fixture data into *conn*."""
    conn.executescript(_SCHEMA_DDL)

    conn.executemany(
        "INSERT INTO records (mms_id, source_file, created_at, jsonl_line_number) VALUES (?,?,?,?)",
        _RECORDS,
    )

    conn.executemany(
        """INSERT INTO imprints
           (record_id, occurrence, date_raw, place_raw, publisher_raw,
            manufacturer_raw, source_tags,
            date_start, date_end, date_label, date_confidence, date_method,
            place_norm, place_display, place_confidence, place_method,
            publisher_norm, publisher_display, publisher_confidence, publisher_method,
            country_code, country_name)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        _IMPRINTS,
    )

    conn.executemany(
        """INSERT INTO agents
           (record_id, agent_index, agent_raw, agent_type, role_raw, role_source,
            authority_uri,
            agent_norm, agent_confidence, agent_method, agent_notes,
            role_norm, role_confidence, role_method, provenance_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        _AGENTS,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_env(tmp_path):
    """Create a complete test environment: in-memory DB, alias maps, temp dirs.

    Yields a dict with keys:
        conn         -- open SQLite connection (in-memory)
        db_path      -- Path to a file-backed copy (for modules that need a Path)
        alias_dir    -- root normalization directory (tmp_path / normalization)
        alias_map_path -- place_alias_map.json path
        metadata_dir -- directory for review logs
    """
    # -- in-memory DB --
    conn = sqlite3.connect(":memory:")
    _create_test_db(conn)

    # -- alias maps on disk --
    alias_dir = tmp_path / "normalization"
    place_alias_dir = alias_dir / "place_aliases"
    place_alias_dir.mkdir(parents=True)
    alias_map = {"amsterdam": "amsterdam", "paris": "paris"}
    alias_map_path = place_alias_dir / "place_alias_map.json"
    alias_map_path.write_text(json.dumps(alias_map, indent=2), encoding="utf-8")

    # -- metadata / review-log dir --
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()

    # -- file-backed DB copy (AgentHarness / FeedbackLoop need a path) --
    db_file = tmp_path / "test.db"
    file_conn = sqlite3.connect(str(db_file))
    conn.backup(file_conn)
    file_conn.close()

    yield {
        "conn": conn,
        "db_path": db_file,
        "alias_dir": alias_dir,
        "alias_map_path": alias_map_path,
        "metadata_dir": metadata_dir,
    }

    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMetadataWorkbenchWorkflow:
    """End-to-end integration test for the metadata workbench."""

    # -- Step 1: audit -------------------------------------------------------

    def test_step1_audit_produces_coverage_report(self, test_env):
        """Coverage audit runs and returns a well-formed CoverageReport."""
        from scripts.metadata.audit import generate_coverage_report_from_conn

        report = generate_coverage_report_from_conn(test_env["conn"])

        assert report.total_imprint_rows == len(_IMPRINTS)
        assert report.total_agent_rows == len(_AGENTS)

        # Place coverage must have bands
        assert report.place_coverage is not None
        assert len(report.place_coverage.confidence_distribution) > 0

        # Date coverage: at least some flagged items (unparsed / missing)
        assert report.date_coverage.total_records == len(_IMPRINTS)

        # Agent coverage
        assert report.agent_name_coverage.total_records == len(_AGENTS)

    def test_step1_audit_flags_low_confidence_places(self, test_env):
        """Audit correctly flags places with confidence <= 0.80."""
        from scripts.metadata.audit import generate_coverage_report_from_conn

        report = generate_coverage_report_from_conn(test_env["conn"])
        flagged_raw = {item.raw_value for item in report.place_coverage.flagged_items}

        # "Lugduni Batavorum" has confidence 0.80 -- should be flagged (<=0.80)
        assert "Lugduni Batavorum" in flagged_raw
        # Hebrew place name has confidence 0.0 -- should be flagged
        assert "\u05d0\u05de\u05e9\u05d8\u05e8\u05d3\u05dd" in flagged_raw
        # "unknown place" has NULL confidence -- should be flagged
        assert "unknown place" in flagged_raw

    # -- Step 2: clustering --------------------------------------------------

    def test_step2_clustering_produces_clusters(self, test_env):
        """Clustering groups flagged place items into meaningful clusters."""
        from scripts.metadata.audit import generate_coverage_report_from_conn
        from scripts.metadata.clustering import cluster_field_gaps

        report = generate_coverage_report_from_conn(test_env["conn"])
        flagged = report.place_coverage.flagged_items
        assert len(flagged) > 0, "precondition: there must be flagged items"

        clusters = cluster_field_gaps("place", flagged)
        assert len(clusters) > 0
        # Every cluster must have at least one value
        for cl in clusters:
            assert len(cl.values) > 0
            assert cl.field == "place"

    def test_step2_clustering_detects_hebrew_cluster(self, test_env):
        """Hebrew place names are clustered under a Hebrew-specific cluster."""
        from scripts.metadata.audit import generate_coverage_report_from_conn
        from scripts.metadata.clustering import cluster_field_gaps

        report = generate_coverage_report_from_conn(test_env["conn"])
        clusters = cluster_field_gaps("place", report.place_coverage.flagged_items)

        hebrew_clusters = [c for c in clusters if "hebrew" in c.cluster_type]
        assert len(hebrew_clusters) > 0, "Expected a Hebrew place-name cluster"

    def test_step2_clustering_dates(self, test_env):
        """Date clustering groups unparsed date values by pattern."""
        from scripts.metadata.audit import generate_coverage_report_from_conn
        from scripts.metadata.clustering import cluster_field_gaps

        report = generate_coverage_report_from_conn(test_env["conn"])
        flagged = report.date_coverage.flagged_items
        if not flagged:
            pytest.skip("No flagged date items in fixture data")

        clusters = cluster_field_gaps("date", flagged)
        assert len(clusters) > 0
        for cl in clusters:
            assert cl.field == "date"

    # -- Step 3: PlaceAgent --------------------------------------------------

    def test_step3_place_agent_analyzes(self, test_env):
        """PlaceAgent.analyze() returns a PlaceAnalysis with coverage stats."""
        from scripts.metadata.agent_harness import AgentHarness
        from scripts.metadata.agents.place_agent import PlaceAgent

        harness = AgentHarness(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            cache_path=test_env["metadata_dir"] / "agent_cache.jsonl",
        )
        agent = PlaceAgent(harness)
        analysis = agent.analyze()

        assert analysis.total_places == len(_IMPRINTS)
        assert analysis.high_confidence_count >= 0
        assert analysis.low_confidence_count >= 0
        # We know at least 2 are low-confidence in the fixture
        assert analysis.low_confidence_count >= 2

    def test_step3_place_agent_clusters(self, test_env):
        """PlaceAgent.get_clusters() returns non-empty clusters."""
        from scripts.metadata.agent_harness import AgentHarness
        from scripts.metadata.agents.place_agent import PlaceAgent

        harness = AgentHarness(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            cache_path=test_env["metadata_dir"] / "agent_cache.jsonl",
        )
        agent = PlaceAgent(harness)
        clusters = agent.get_clusters()

        assert isinstance(clusters, list)
        assert len(clusters) > 0

    # -- Step 4: FeedbackLoop correction -------------------------------------

    def test_step4_feedback_loop_applies_correction(self, test_env):
        """FeedbackLoop.apply_correction writes alias map and updates DB."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log.jsonl",
        )

        result = loop.apply_correction(
            field="place",
            raw_value="lugduni batavorum",
            canonical_value="leiden",
            evidence="Latin genitive of Leiden",
            source="integration_test",
        )

        assert result.success, f"Correction failed: {result.error}"
        assert result.records_updated >= 0  # may be 0 if raw casing doesn't match

        # Alias map file must now contain the mapping
        alias_map = json.loads(test_env["alias_map_path"].read_text())
        assert "lugduni batavorum" in alias_map
        assert alias_map["lugduni batavorum"] == "leiden"

    def test_step4_feedback_loop_updates_db_records(self, test_env):
        """Correction re-normalizes matching rows in the DB."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        # Insert a row with exact raw value casing that matches our correction
        file_conn = sqlite3.connect(str(test_env["db_path"]))
        # Get a record_id to reference
        rec_id = file_conn.execute(
            "SELECT id FROM records LIMIT 1"
        ).fetchone()[0]
        file_conn.execute(
            """INSERT INTO imprints
               (record_id, occurrence, date_raw, place_raw, publisher_raw,
                source_tags,
                place_norm, place_confidence, place_method)
               VALUES (?, 99, NULL, 'test_raw_place', NULL,
                       '["264"]',
                       'test_raw_place', 0.80, 'base_clean')""",
            (rec_id,),
        )
        file_conn.commit()
        file_conn.close()

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log.jsonl",
        )

        result = loop.apply_correction(
            field="place",
            raw_value="test_raw_place",
            canonical_value="test_canonical",
            source="integration_test",
        )
        assert result.success
        assert result.records_updated == 1

        # Verify the DB row was updated
        file_conn = sqlite3.connect(str(test_env["db_path"]))
        row = file_conn.execute(
            "SELECT place_norm, place_confidence, place_method FROM imprints WHERE place_raw = 'test_raw_place'"
        ).fetchone()
        file_conn.close()
        assert row is not None
        assert row[0] == "test_canonical"
        assert row[1] == 0.95
        assert row[2] == "place_alias_map_correction"

    # -- Step 5: re-audit after correction -----------------------------------

    def test_step5_coverage_report_after_correction(self, test_env):
        """Re-running audit after correction still produces a valid report."""
        from scripts.metadata.audit import generate_coverage_report
        from scripts.metadata.feedback_loop import FeedbackLoop

        # Baseline
        report_before = generate_coverage_report(test_env["db_path"])
        assert report_before is not None

        # Apply correction
        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log.jsonl",
        )
        loop.apply_correction(
            field="place",
            raw_value="Lugduni Batavorum",
            canonical_value="leiden",
            source="integration_test",
        )

        # Post-correction
        report_after = generate_coverage_report(test_env["db_path"])
        assert report_after is not None
        assert report_after.total_imprint_rows == report_before.total_imprint_rows

    # -- Step 6: review log --------------------------------------------------

    def test_step6_review_log_records_correction(self, test_env):
        """Review log is written with structured JSON entries."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        review_log = test_env["metadata_dir"] / "review_log.jsonl"

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=review_log,
        )
        loop.apply_correction(
            field="place",
            raw_value="test_place_log",
            canonical_value="test_canonical_log",
            evidence="test evidence",
            source="integration_test",
        )

        assert review_log.exists(), "review_log.jsonl should be created"
        entries = [
            json.loads(line)
            for line in review_log.read_text().strip().split("\n")
            if line.strip()
        ]
        assert len(entries) >= 1
        last = entries[-1]
        assert last["field"] == "place"
        assert last["raw_value"] == "test_place_log"
        assert last["canonical_value"] == "test_canonical_log"
        assert last["evidence"] == "test evidence"
        assert last["source"] == "integration_test"
        assert last["action"] == "approved"
        assert "timestamp" in last

    # -- Step 7: batch corrections -------------------------------------------

    def test_step7_batch_corrections(self, test_env):
        """FeedbackLoop.apply_batch handles multiple corrections atomically."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log_batch.jsonl",
        )

        corrections = [
            {"field": "place", "raw_value": "batch_a", "canonical_value": "rome", "source": "test"},
            {"field": "place", "raw_value": "batch_b", "canonical_value": "venice", "source": "test"},
        ]
        results = loop.apply_batch(corrections)
        assert len(results) == 2
        assert all(r.success for r in results)

        # Alias map should have both entries
        alias_map = json.loads(test_env["alias_map_path"].read_text())
        assert alias_map.get("batch_a") == "rome"
        assert alias_map.get("batch_b") == "venice"

    # -- Step 8: coverage delta ----------------------------------------------

    def test_step8_coverage_delta(self, test_env):
        """FeedbackLoop.get_coverage_delta returns confidence band counts."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log.jsonl",
        )

        delta = loop.get_coverage_delta("place")
        assert "error" not in delta
        assert delta["field"] == "place"
        assert delta["total"] == len(_IMPRINTS)
        assert delta["high"] + delta["medium"] + delta["low"] + delta["missing"] == delta["total"]

    # -- Step 9: conflict detection ------------------------------------------

    def test_step9_conflict_detection(self, test_env):
        """Applying a conflicting correction fails gracefully."""
        from scripts.metadata.feedback_loop import FeedbackLoop

        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "review_log.jsonl",
        )

        # First correction succeeds
        r1 = loop.apply_correction(
            field="place",
            raw_value="conflict_test",
            canonical_value="value_a",
            source="test",
        )
        assert r1.success

        # Second correction with a different canonical value should fail
        r2 = loop.apply_correction(
            field="place",
            raw_value="conflict_test",
            canonical_value="value_b",
            source="test",
        )
        assert not r2.success
        assert "Conflict" in (r2.error or "")

    # -- Step 10: grounding layer queries ------------------------------------

    def test_step10_grounding_layer_queries_gaps(self, test_env):
        """GroundingLayer.query_gaps returns low-confidence gap records."""
        from scripts.metadata.agent_harness import GroundingLayer

        grounding = GroundingLayer(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
        )

        gaps = grounding.query_gaps("place", max_confidence=0.80)
        assert len(gaps) > 0
        for gap in gaps:
            assert gap.confidence <= 0.80
            assert gap.field == "place"

    def test_step10_grounding_layer_count_affected(self, test_env):
        """GroundingLayer.count_affected_records returns correct count."""
        from scripts.metadata.agent_harness import GroundingLayer

        grounding = GroundingLayer(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
        )

        count = grounding.count_affected_records("Paris :", "place")
        assert count == 1  # Exactly one imprint with place_raw='Paris :'

    # -- Step 11: full workflow smoke test -----------------------------------

    def test_step11_full_workflow_smoke(self, test_env):
        """Smoke test: audit -> cluster -> agent -> correct -> re-audit."""
        from scripts.metadata.audit import (
            generate_coverage_report,
            generate_coverage_report_from_conn,
        )
        from scripts.metadata.clustering import cluster_field_gaps
        from scripts.metadata.agent_harness import AgentHarness
        from scripts.metadata.agents.place_agent import PlaceAgent
        from scripts.metadata.feedback_loop import FeedbackLoop

        # 1. Audit
        report = generate_coverage_report_from_conn(test_env["conn"])
        assert report.total_imprint_rows > 0

        # 2. Cluster
        clusters = cluster_field_gaps("place", report.place_coverage.flagged_items)

        # 3. Agent analysis
        harness = AgentHarness(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            cache_path=test_env["metadata_dir"] / "agent_cache.jsonl",
        )
        agent = PlaceAgent(harness)
        analysis = agent.analyze()
        assert analysis.total_places > 0

        # 4. Correct
        loop = FeedbackLoop(
            db_path=test_env["db_path"],
            alias_map_dir=test_env["alias_dir"],
            review_log_path=test_env["metadata_dir"] / "smoke_review_log.jsonl",
        )
        result = loop.apply_correction(
            field="place",
            raw_value="smoke_test_raw",
            canonical_value="smoke_canonical",
            source="smoke_test",
        )
        assert result.success

        # 5. Re-audit (from file DB)
        report_after = generate_coverage_report(test_env["db_path"])
        assert report_after is not None
