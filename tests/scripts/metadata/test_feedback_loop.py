"""Tests for the HITL feedback loop.

Uses in-memory SQLite with a subset of the M3 schema.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.metadata.feedback_loop import FeedbackLoop


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal M3 schema (imprints + agents only - the tables we UPDATE)
_MINI_SCHEMA = """
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE imprints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    occurrence INTEGER NOT NULL,
    date_raw TEXT,
    place_raw TEXT,
    publisher_raw TEXT,
    manufacturer_raw TEXT,
    source_tags TEXT NOT NULL DEFAULT '[]',
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
    agent_type TEXT NOT NULL DEFAULT 'personal',
    role_raw TEXT,
    role_source TEXT,
    authority_uri TEXT,
    agent_norm TEXT NOT NULL,
    agent_confidence REAL NOT NULL DEFAULT 0.5,
    agent_method TEXT NOT NULL DEFAULT 'base_clean',
    agent_notes TEXT,
    role_norm TEXT NOT NULL DEFAULT 'author',
    role_confidence REAL NOT NULL DEFAULT 0.5,
    role_method TEXT NOT NULL DEFAULT 'inferred',
    provenance_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
"""


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Create a temp directory structure for alias maps."""
    (tmp_path / "place_aliases").mkdir()
    (tmp_path / "publisher_aliases").mkdir()
    (tmp_path / "agent_aliases").mkdir()
    return tmp_path


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create an in-memory-style on-disk SQLite with the mini schema."""
    db_file = tmp_path / "test_biblio.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(_MINI_SCHEMA)

    # Seed records
    conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        ("990001", "test.xml", "2025-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        ("990002", "test.xml", "2025-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO records (mms_id, source_file, created_at) VALUES (?, ?, ?)",
        ("990003", "test.xml", "2025-01-01T00:00:00Z"),
    )

    # Seed imprints with low-confidence place/publisher normalisations
    conn.execute(
        "INSERT INTO imprints (record_id, occurrence, place_raw, place_norm, place_confidence, place_method, "
        "publisher_raw, publisher_norm, publisher_confidence, publisher_method) "
        "VALUES (1, 0, 'Lugduni Batavorum', 'lugduni batavorum', 0.80, 'place_casefold_strip', "
        "'C. Fosset,', 'c. fosset,', 0.80, 'publisher_casefold_strip')",
    )
    conn.execute(
        "INSERT INTO imprints (record_id, occurrence, place_raw, place_norm, place_confidence, place_method, "
        "publisher_raw, publisher_norm, publisher_confidence, publisher_method) "
        "VALUES (2, 0, 'Lugduni Batavorum', 'lugduni batavorum', 0.80, 'place_casefold_strip', "
        "'Elsevier:', 'elsevier:', 0.80, 'publisher_casefold_strip')",
    )
    conn.execute(
        "INSERT INTO imprints (record_id, occurrence, place_raw, place_norm, place_confidence, place_method, "
        "publisher_raw, publisher_norm, publisher_confidence, publisher_method) "
        "VALUES (3, 0, 'Paris :', 'paris', 0.95, 'place_alias_map', "
        "'Gauthier-Villars', 'gauthier-villars', 0.80, 'publisher_casefold_strip')",
    )

    # Seed agents
    conn.execute(
        "INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, agent_confidence, agent_method, "
        "role_norm, role_confidence, role_method, provenance_json) "
        "VALUES (1, 0, 'Smith, John', 'smith, john', 0.70, 'base_clean', "
        "'author', 0.90, 'relator_code', '[]')",
    )
    conn.execute(
        "INSERT INTO agents (record_id, agent_index, agent_raw, agent_norm, agent_confidence, agent_method, "
        "role_norm, role_confidence, role_method, provenance_json) "
        "VALUES (2, 0, 'Smith, John', 'smith, john', 0.70, 'base_clean', "
        "'printer', 0.90, 'relator_code', '[]')",
    )

    conn.commit()
    conn.close()
    return db_file


@pytest.fixture()
def loop(db_path: Path, tmp_dir: Path, tmp_path: Path) -> FeedbackLoop:
    """Create a FeedbackLoop wired to test fixtures."""
    return FeedbackLoop(
        db_path=db_path,
        alias_map_dir=tmp_dir,
        review_log_path=tmp_path / "review_log.jsonl",
    )


# ---------------------------------------------------------------------------
# Tests: apply_correction writes to alias map
# ---------------------------------------------------------------------------

class TestApplyCorrectionAliasMap:
    """Verify that apply_correction writes the alias map correctly."""

    def test_creates_alias_map_entry(self, loop: FeedbackLoop, tmp_dir: Path):
        result = loop.apply_correction("place", "lugduni batavorum", "leiden")

        assert result.success is True
        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        assert alias_path.exists()

        with open(alias_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["lugduni batavorum"] == "leiden"

    def test_preserves_existing_entries(self, loop: FeedbackLoop, tmp_dir: Path):
        # Pre-populate alias map
        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        with open(alias_path, "w", encoding="utf-8") as f:
            json.dump({"amsterdam": "amsterdam"}, f)

        loop.apply_correction("place", "lugduni batavorum", "leiden")

        with open(alias_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["amsterdam"] == "amsterdam"
        assert data["lugduni batavorum"] == "leiden"

    def test_conflict_returns_error(self, loop: FeedbackLoop, tmp_dir: Path):
        # Pre-populate with a different mapping
        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        with open(alias_path, "w", encoding="utf-8") as f:
            json.dump({"lugduni batavorum": "lyon"}, f)

        result = loop.apply_correction("place", "lugduni batavorum", "leiden")

        assert result.success is False
        assert "Conflict" in result.error

    def test_duplicate_is_noop_success(self, loop: FeedbackLoop, tmp_dir: Path):
        # Same mapping already exists
        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        with open(alias_path, "w", encoding="utf-8") as f:
            json.dump({"lugduni batavorum": "leiden"}, f)

        result = loop.apply_correction("place", "lugduni batavorum", "leiden")

        assert result.success is True

    def test_unknown_field_returns_error(self, loop: FeedbackLoop):
        result = loop.apply_correction("title", "foo", "bar")

        assert result.success is False
        assert "Unknown field" in result.error


# ---------------------------------------------------------------------------
# Tests: apply_correction updates database records
# ---------------------------------------------------------------------------

class TestApplyCorrectionDatabase:
    """Verify that apply_correction re-normalises records in the DB."""

    def test_updates_place_norm(self, loop: FeedbackLoop, db_path: Path):
        result = loop.apply_correction("place", "Lugduni Batavorum", "leiden")

        assert result.success is True
        assert result.records_updated == 2  # records 990001 and 990002

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT place_norm, place_confidence, place_method FROM imprints WHERE place_raw = ?",
            ("Lugduni Batavorum",),
        ).fetchall()
        conn.close()

        for norm, conf, method in rows:
            assert norm == "leiden"
            assert conf == 0.95
            assert method == "place_alias_map_correction"

    def test_updates_publisher_norm(self, loop: FeedbackLoop, db_path: Path):
        result = loop.apply_correction("publisher", "Elsevier:", "elsevier")

        assert result.success is True
        assert result.records_updated == 1

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT publisher_norm, publisher_confidence, publisher_method "
            "FROM imprints WHERE publisher_raw = ?",
            ("Elsevier:",),
        ).fetchone()
        conn.close()

        assert row[0] == "elsevier"
        assert row[1] == 0.95
        assert row[2] == "publisher_alias_map_correction"

    def test_updates_agent_norm(self, loop: FeedbackLoop, db_path: Path):
        result = loop.apply_correction("agent", "Smith, John", "smith, john (1650-1720)")

        assert result.success is True
        assert result.records_updated == 2

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT agent_norm, agent_confidence, agent_method FROM agents WHERE agent_raw = ?",
            ("Smith, John",),
        ).fetchall()
        conn.close()

        for norm, conf, method in rows:
            assert norm == "smith, john (1650-1720)"
            assert conf == 0.95
            assert method == "agent_alias_map_correction"

    def test_no_matching_records_returns_zero(self, loop: FeedbackLoop):
        result = loop.apply_correction("place", "nonexistent_place", "nowhere")

        assert result.success is True
        assert result.records_updated == 0


# ---------------------------------------------------------------------------
# Tests: apply_correction logs to review log
# ---------------------------------------------------------------------------

class TestApplyCorrectionLog:
    """Verify that corrections are logged to review_log.jsonl."""

    def test_creates_review_log(self, loop: FeedbackLoop, tmp_path: Path):
        loop.apply_correction("place", "lugduni batavorum", "leiden", evidence="reference text")

        log_path = tmp_path / "review_log.jsonl"
        assert log_path.exists()

        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["field"] == "place"
        assert entry["raw_value"] == "lugduni batavorum"
        assert entry["canonical_value"] == "leiden"
        assert entry["evidence"] == "reference text"
        assert entry["source"] == "human"
        assert entry["action"] == "approved"
        assert "timestamp" in entry
        assert "records_updated" in entry

    def test_appends_to_existing_log(self, loop: FeedbackLoop, tmp_path: Path):
        loop.apply_correction("place", "lugduni batavorum", "leiden")
        loop.apply_correction("publisher", "Elsevier:", "elsevier")

        log_path = tmp_path / "review_log.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_log_records_source(self, loop: FeedbackLoop, tmp_path: Path):
        loop.apply_correction("place", "foo", "bar", source="agent")

        log_path = tmp_path / "review_log.jsonl"
        with open(log_path, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["source"] == "agent"


# ---------------------------------------------------------------------------
# Tests: apply_batch groups by field
# ---------------------------------------------------------------------------

class TestApplyBatch:
    """Verify batch corrections group by field for efficiency."""

    def test_batch_applies_multiple_corrections(self, loop: FeedbackLoop, tmp_dir: Path):
        corrections = [
            {"field": "place", "raw_value": "lugduni batavorum", "canonical_value": "leiden"},
            {"field": "place", "raw_value": "paris", "canonical_value": "paris"},
            {"field": "publisher", "raw_value": "Elsevier:", "canonical_value": "elsevier"},
        ]

        results = loop.apply_batch(corrections)

        assert len(results) == 3
        assert all(r.success for r in results)

        # Check both alias maps written
        place_map = json.loads(
            (tmp_dir / "place_aliases" / "place_alias_map.json").read_text()
        )
        assert "lugduni batavorum" in place_map
        assert "paris" in place_map

        pub_map = json.loads(
            (tmp_dir / "publisher_aliases" / "publisher_alias_map.json").read_text()
        )
        assert "Elsevier:" in pub_map

    def test_batch_handles_unknown_field(self, loop: FeedbackLoop):
        corrections = [
            {"field": "date", "raw_value": "1680", "canonical_value": "1680"},
        ]
        results = loop.apply_batch(corrections)
        assert len(results) == 1
        assert results[0].success is False

    def test_batch_handles_conflict(self, loop: FeedbackLoop, tmp_dir: Path):
        # Pre-populate
        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        with open(alias_path, "w", encoding="utf-8") as f:
            json.dump({"lugduni batavorum": "lyon"}, f)

        corrections = [
            {"field": "place", "raw_value": "lugduni batavorum", "canonical_value": "leiden"},
            {"field": "place", "raw_value": "amsterdam", "canonical_value": "amsterdam"},
        ]

        results = loop.apply_batch(corrections)
        assert results[0].success is False  # conflict
        assert results[1].success is True   # should still succeed

    def test_batch_writes_alias_map_once_per_field(self, loop: FeedbackLoop, tmp_dir: Path, monkeypatch):
        """Batch should write the alias map once per field, not once per correction."""
        write_count = {"place": 0}
        original_save = FeedbackLoop._save_alias_map_atomic

        @staticmethod
        def counting_save(path, alias_map):
            if "place_aliases" in str(path):
                write_count["place"] += 1
            original_save(path, alias_map)

        monkeypatch.setattr(FeedbackLoop, "_save_alias_map_atomic", counting_save)

        corrections = [
            {"field": "place", "raw_value": "lugduni batavorum", "canonical_value": "leiden"},
            {"field": "place", "raw_value": "amsterdam", "canonical_value": "amsterdam"},
            {"field": "place", "raw_value": "constantinopolis", "canonical_value": "istanbul"},
        ]
        results = loop.apply_batch(corrections)
        assert all(r.success for r in results)
        # Only ONE atomic write for the place field
        assert write_count["place"] == 1


# ---------------------------------------------------------------------------
# Tests: _renormalize_records updates correct columns per field
# ---------------------------------------------------------------------------

class TestRenormalizeRecords:
    """Verify the incremental UPDATE targets the right columns."""

    def test_place_update_columns(self, loop: FeedbackLoop, db_path: Path):
        loop._renormalize_records("place", "Paris :", "paris")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT place_norm, place_confidence, place_method "
            "FROM imprints WHERE place_raw = 'Paris :'",
        ).fetchone()
        conn.close()

        assert row == ("paris", 0.95, "place_alias_map_correction")

    def test_publisher_update_columns(self, loop: FeedbackLoop, db_path: Path):
        loop._renormalize_records("publisher", "C. Fosset,", "fosset")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT publisher_norm, publisher_confidence, publisher_method "
            "FROM imprints WHERE publisher_raw = 'C. Fosset,'",
        ).fetchone()
        conn.close()

        assert row == ("fosset", 0.95, "publisher_alias_map_correction")

    def test_agent_update_columns(self, loop: FeedbackLoop, db_path: Path):
        loop._renormalize_records("agent", "Smith, John", "smith, j.")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT agent_norm, agent_confidence, agent_method "
            "FROM agents WHERE agent_raw = 'Smith, John'",
        ).fetchone()
        conn.close()

        assert row == ("smith, j.", 0.95, "agent_alias_map_correction")

    def test_unknown_field_returns_zero(self, loop: FeedbackLoop):
        count = loop._renormalize_records("date", "1680", "1680")
        assert count == 0


# ---------------------------------------------------------------------------
# Tests: atomic write (tmp file cleanup)
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    """Verify atomic write behaviour."""

    def test_no_tmp_file_left_behind(self, loop: FeedbackLoop, tmp_dir: Path):
        loop.apply_correction("place", "lugduni batavorum", "leiden")

        tmp_file = tmp_dir / "place_aliases" / "place_alias_map.tmp"
        assert not tmp_file.exists()

    def test_alias_map_is_valid_json_after_write(self, loop: FeedbackLoop, tmp_dir: Path):
        loop.apply_correction("place", "lugduni batavorum", "leiden")

        alias_path = tmp_dir / "place_aliases" / "place_alias_map.json"
        with open(alias_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data["lugduni batavorum"] == "leiden"


# ---------------------------------------------------------------------------
# Tests: coverage_delta
# ---------------------------------------------------------------------------

class TestCoverageDelta:
    """Verify coverage band calculation."""

    def test_coverage_before_correction(self, loop: FeedbackLoop):
        delta = loop.get_coverage_delta("place")

        assert delta["field"] == "place"
        assert delta["total"] == 3
        # 2 records at 0.80 => medium, 1 at 0.95 => high
        assert delta["high"] == 1
        assert delta["medium"] == 2
        assert delta["low"] == 0
        assert delta["missing"] == 0

    def test_coverage_after_correction(self, loop: FeedbackLoop):
        # Apply correction - upgrades 2 records from 0.80 to 0.95
        loop.apply_correction("place", "Lugduni Batavorum", "leiden")

        delta = loop.get_coverage_delta("place")
        assert delta["high"] == 3  # all three now >= 0.90
        assert delta["medium"] == 0

    def test_coverage_unknown_field(self, loop: FeedbackLoop):
        delta = loop.get_coverage_delta("title")
        assert "error" in delta

    def test_coverage_agent_field(self, loop: FeedbackLoop):
        delta = loop.get_coverage_delta("agent")

        assert delta["field"] == "agent"
        assert delta["total"] == 2
        # Both agents have confidence 0.70 => medium
        assert delta["medium"] == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases: missing dirs, empty DB, etc."""

    def test_missing_alias_map_dir_creates_it(self, tmp_path: Path, db_path: Path):
        """If the alias map subdirectory doesn't exist, it is created."""
        alias_dir = tmp_path / "nonexistent_alias_dir"
        # Don't create subdirectories manually - they should be created automatically

        loop = FeedbackLoop(
            db_path=db_path,
            alias_map_dir=alias_dir,
            review_log_path=tmp_path / "review_log.jsonl",
        )

        result = loop.apply_correction("place", "test_place", "test_canonical")

        assert result.success is True
        assert (alias_dir / "place_aliases" / "place_alias_map.json").exists()

    def test_empty_database(self, tmp_path: Path):
        """Correction against an empty database succeeds with 0 updates."""
        db_file = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_file))
        conn.executescript(_MINI_SCHEMA)
        conn.close()

        alias_dir = tmp_path / "aliases"
        (alias_dir / "place_aliases").mkdir(parents=True)
        (alias_dir / "publisher_aliases").mkdir()
        (alias_dir / "agent_aliases").mkdir()

        loop = FeedbackLoop(
            db_path=db_file,
            alias_map_dir=alias_dir,
            review_log_path=tmp_path / "review_log.jsonl",
        )

        result = loop.apply_correction("place", "nonexistent", "somewhere")
        assert result.success is True
        assert result.records_updated == 0

    def test_get_pending_empty(self, loop: FeedbackLoop):
        """No pending file means empty list."""
        pending = loop.get_pending_corrections()
        assert pending == []

    def test_get_pending_with_file(self, loop: FeedbackLoop, tmp_path: Path):
        """Pending corrections are read from the queue file."""
        pending_path = tmp_path / "pending_corrections.json"
        pending_data = [
            {"field": "place", "raw_value": "foo", "canonical_value": "bar"},
        ]
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_data, f)

        # Override review_log_path parent to match where pending file is
        loop.review_log_path = tmp_path / "review_log.jsonl"
        pending = loop.get_pending_corrections()
        assert len(pending) == 1
        assert pending[0]["raw_value"] == "foo"
