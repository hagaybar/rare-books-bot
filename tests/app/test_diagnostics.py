"""Tests for diagnostic API endpoints (B5-B12).

Tests cover:
- POST /diagnostics/query-run (B5)
- GET /diagnostics/query-runs (B6)
- POST /diagnostics/labels (B7)
- GET /diagnostics/labels/{run_id} (B8)
- GET /diagnostics/gold-set/export (B9)
- POST /diagnostics/gold-set/regression (B10)
- GET /diagnostics/tables (B11)
- GET /diagnostics/tables/{table_name}/rows (B12)

Strategy: Use in-memory / temporary SQLite databases to avoid depending on
production data. Mock QueryService for B5 and compile_query/execute_plan for B10.
"""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_bib_db(tmp_path):
    """Create a minimal bibliographic SQLite database for testing."""
    db_path = tmp_path / "bibliographic.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY,
            mms_id TEXT NOT NULL
        );
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            place_norm TEXT,
            publisher_norm TEXT,
            date_start INTEGER
        );
        CREATE TABLE titles (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            title TEXT
        );
        CREATE TABLE subjects (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            heading TEXT
        );
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            name TEXT,
            role TEXT
        );
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            code TEXT
        );
        CREATE TABLE notes (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            note TEXT
        );
        CREATE TABLE publisher_authorities (
            id INTEGER PRIMARY KEY,
            canonical_name TEXT
        );
        CREATE TABLE publisher_variants (
            id INTEGER PRIMARY KEY,
            authority_id INTEGER,
            variant_name TEXT
        );
        CREATE TABLE physical_descriptions (
            id INTEGER PRIMARY KEY,
            record_id INTEGER,
            extent TEXT,
            dimensions TEXT
        );
        CREATE TABLE authority_enrichment (
            id INTEGER PRIMARY KEY,
            authority_id INTEGER,
            source TEXT
        );

        INSERT INTO records (id, mms_id) VALUES (1, '990001');
        INSERT INTO records (id, mms_id) VALUES (2, '990002');
        INSERT INTO imprints (record_id, place_norm, publisher_norm, date_start) VALUES (1, 'venice', 'aldus', 1501);
        INSERT INTO imprints (record_id, place_norm, publisher_norm, date_start) VALUES (2, 'paris', 'estienne', 1550);
        INSERT INTO titles (record_id, title) VALUES (1, 'De rerum natura');
        INSERT INTO titles (record_id, title) VALUES (2, 'Institutiones');
        INSERT INTO subjects (record_id, heading) VALUES (1, 'Philosophy');
        INSERT INTO agents (record_id, name, role) VALUES (1, 'Lucretius', 'author');
        INSERT INTO languages (record_id, code) VALUES (1, 'lat');
        INSERT INTO notes (record_id, note) VALUES (1, 'First edition');
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def tmp_qa_db(tmp_path):
    """Create a temporary QA database."""
    db_path = tmp_path / "qa.db"
    # Patch the config before calling init_db
    with patch("scripts.qa.config.QA_DB_PATH", db_path):
        with patch("scripts.qa.db.QA_DB_PATH", db_path):
            from scripts.qa.db import init_db
            init_db()
    return db_path


@pytest.fixture()
def env_dbs(tmp_bib_db, tmp_qa_db, monkeypatch):
    """Set environment variables pointing to temp databases."""
    monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
    monkeypatch.setenv("QA_DB_PATH", str(tmp_qa_db))
    return {"bib": tmp_bib_db, "qa": tmp_qa_db}


def _insert_qa_run(qa_path: Path, query_text: str = "test query", total: int = 5) -> int:
    """Insert a test query run directly into the QA DB. Returns run_id."""
    from datetime import datetime
    conn = sqlite3.connect(str(qa_path))
    cursor = conn.execute(
        """
        INSERT INTO qa_queries (
            created_at, query_text, db_path, plan_json, sql_text,
            status, total_candidates
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(),
            query_text,
            "test.db",
            '{"filters": []}',
            "SELECT * FROM records",
            "OK",
            total,
        ),
    )
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def _insert_qa_label(qa_path: Path, query_id: int, record_id: str, label: str):
    """Insert a label directly into the QA DB."""
    from datetime import datetime
    now = datetime.now().isoformat()
    conn = sqlite3.connect(str(qa_path))
    conn.execute(
        """
        INSERT INTO qa_candidate_labels (
            query_id, record_id, label, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (query_id, record_id, label, now, now),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# B5: POST /diagnostics/query-run
# ---------------------------------------------------------------------------


class TestQueryRun:
    """Tests for POST /diagnostics/query-run (B5)."""

    def test_query_run_success(self, env_dbs):
        """Successful query execution returns run_id and candidates."""
        from scripts.schemas.candidate_set import Candidate, CandidateSet, Evidence
        from scripts.schemas.query_plan import QueryPlan
        from scripts.query.models import QueryResult

        mock_candidate = Candidate(
            record_id="990001",
            match_rationale="publisher_norm='aldus'",
            evidence=[
                Evidence(
                    field="publisher_norm",
                    value="aldus",
                    operator="=",
                    matched_against="aldus",
                    source="marc:264$b",
                )
            ],
            title="De rerum natura",
        )
        mock_cs = CandidateSet(
            query_text="books by aldus",
            plan_hash="abc123",
            sql="SELECT * FROM records",
            candidates=[mock_candidate],
            total_count=1,
        )
        plan = QueryPlan(
            query_text="books by aldus",
            filters=[],
            limit=50,
        )

        mock_result = QueryResult(
            query_plan=plan,
            sql="SELECT * FROM records",
            params=[],
            candidate_set=mock_cs,
            execution_time_ms=42.5,
        )

        with patch("app.api.diagnostics._ensure_qa_db"), \
             patch("scripts.query.QueryService") as MockService, \
             patch("scripts.qa.db.insert_query_run", return_value=1):
            instance = MockService.return_value
            instance.execute.return_value = mock_result

            resp = client.post(
                "/diagnostics/query-run",
                json={"query_text": "books by aldus", "limit": 50},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == 1
        assert data["query_text"] == "books by aldus"
        assert data["total_count"] == 1
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["record_id"] == "990001"
        assert data["execution_time_ms"] > 0

    def test_query_run_empty_query(self, env_dbs):
        """Empty query text is rejected by validation."""
        resp = client.post(
            "/diagnostics/query-run",
            json={"query_text": "", "limit": 50},
        )
        assert resp.status_code == 422

    def test_query_run_missing_db(self, monkeypatch, tmp_path):
        """Returns 503 if bibliographic DB does not exist."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_path / "missing.db"))
        resp = client.post(
            "/diagnostics/query-run",
            json={"query_text": "books by aldus"},
        )
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# B6: GET /diagnostics/query-runs
# ---------------------------------------------------------------------------


class TestQueryRuns:
    """Tests for GET /diagnostics/query-runs (B6)."""

    def test_empty_list(self, env_dbs):
        """Returns empty list when no runs exist."""
        with patch("app.api.diagnostics._get_qa_db_path", return_value=env_dbs["qa"]):
            resp = client.get("/diagnostics/query-runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_with_runs(self, env_dbs):
        """Returns runs when they exist in the QA DB."""
        qa_path = env_dbs["qa"]
        _insert_qa_run(qa_path, "query 1", 10)
        _insert_qa_run(qa_path, "query 2", 20)

        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path):
            resp = client.get("/diagnostics/query-runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_pagination(self, env_dbs):
        """Respects limit and offset parameters."""
        qa_path = env_dbs["qa"]
        for i in range(5):
            _insert_qa_run(qa_path, f"query {i}", i)

        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path):
            resp = client.get("/diagnostics/query-runs?limit=2&offset=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_missing_qa_db(self, monkeypatch, tmp_path):
        """Returns empty list when QA DB does not exist."""
        monkeypatch.setenv("QA_DB_PATH", str(tmp_path / "nonexistent.db"))
        with patch("app.api.diagnostics._get_qa_db_path", return_value=tmp_path / "nonexistent.db"):
            resp = client.get("/diagnostics/query-runs")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# B7: POST /diagnostics/labels
# ---------------------------------------------------------------------------


class TestSaveLabels:
    """Tests for POST /diagnostics/labels (B7)."""

    def test_save_labels_success(self, env_dbs):
        """Successfully saves labels for a run."""
        qa_path = env_dbs["qa"]
        run_id = _insert_qa_run(qa_path)

        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path), \
             patch("app.api.diagnostics._ensure_qa_db"), \
             patch("scripts.qa.db.QA_DB_PATH", qa_path):
            resp = client.post(
                "/diagnostics/labels",
                json={
                    "run_id": run_id,
                    "labels": [
                        {"record_id": "990001", "label": "TP", "issue_tags": []},
                        {"record_id": "990002", "label": "FP", "issue_tags": ["NORM_PLACE_BAD"]},
                    ],
                },
            )
        assert resp.status_code == 200
        assert resp.json()["saved_count"] == 2

    def test_save_labels_invalid_label(self, env_dbs):
        """Rejects invalid label values."""
        qa_path = env_dbs["qa"]
        run_id = _insert_qa_run(qa_path)

        resp = client.post(
            "/diagnostics/labels",
            json={
                "run_id": run_id,
                "labels": [
                    {"record_id": "990001", "label": "INVALID"},
                ],
            },
        )
        assert resp.status_code == 422

    def test_save_labels_nonexistent_run(self, env_dbs):
        """Returns 404 for nonexistent run."""
        qa_path = env_dbs["qa"]
        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path), \
             patch("app.api.diagnostics._ensure_qa_db"), \
             patch("scripts.qa.db.QA_DB_PATH", qa_path):
            resp = client.post(
                "/diagnostics/labels",
                json={
                    "run_id": 99999,
                    "labels": [
                        {"record_id": "990001", "label": "TP"},
                    ],
                },
            )
        assert resp.status_code == 404

    def test_save_labels_empty_list(self, env_dbs):
        """Rejects empty labels list."""
        resp = client.post(
            "/diagnostics/labels",
            json={"run_id": 1, "labels": []},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# B8: GET /diagnostics/labels/{run_id}
# ---------------------------------------------------------------------------


class TestGetLabels:
    """Tests for GET /diagnostics/labels/{run_id} (B8)."""

    def test_get_labels_with_data(self, env_dbs):
        """Returns labels for a run that has them."""
        qa_path = env_dbs["qa"]
        run_id = _insert_qa_run(qa_path)
        _insert_qa_label(qa_path, run_id, "990001", "TP")
        _insert_qa_label(qa_path, run_id, "990002", "FP")

        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path), \
             patch("scripts.qa.db.QA_DB_PATH", qa_path):
            resp = client.get(f"/diagnostics/labels/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["labels"]) == 2
        record_ids = {lbl["record_id"] for lbl in data["labels"]}
        assert record_ids == {"990001", "990002"}

    def test_get_labels_empty(self, env_dbs):
        """Returns empty list for a run with no labels."""
        qa_path = env_dbs["qa"]
        run_id = _insert_qa_run(qa_path)

        with patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path), \
             patch("scripts.qa.db.QA_DB_PATH", qa_path):
            resp = client.get(f"/diagnostics/labels/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["labels"] == []

    def test_get_labels_missing_db(self, monkeypatch, tmp_path):
        """Returns empty list when QA DB does not exist."""
        monkeypatch.setenv("QA_DB_PATH", str(tmp_path / "nonexistent.db"))
        with patch("app.api.diagnostics._get_qa_db_path", return_value=tmp_path / "nonexistent.db"):
            resp = client.get("/diagnostics/labels/1")
        assert resp.status_code == 200
        assert resp.json()["labels"] == []


# ---------------------------------------------------------------------------
# B9: GET /diagnostics/gold-set/export
# ---------------------------------------------------------------------------


class TestGoldSetExport:
    """Tests for GET /diagnostics/gold-set/export (B9)."""

    def test_export_from_file(self, tmp_path):
        """Reads gold set from gold.json when it exists."""
        gold_data = {
            "version": "1.0",
            "exported_at": "2025-01-01T00:00:00",
            "queries": [
                {
                    "query_text": "books by aldus",
                    "expected_includes": ["990001"],
                    "expected_excludes": [],
                }
            ],
        }
        gold_path = tmp_path / "gold.json"
        gold_path.write_text(json.dumps(gold_data))

        with patch("app.api.diagnostics._get_gold_set_path", return_value=gold_path):
            resp = client.get("/diagnostics/gold-set/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert len(data["queries"]) == 1
        assert data["queries"][0]["query_text"] == "books by aldus"

    def test_export_fallback_to_db(self, env_dbs):
        """Falls back to QA DB when gold.json does not exist."""
        qa_path = env_dbs["qa"]
        # Insert a run and label to generate gold set from DB
        run_id = _insert_qa_run(qa_path, "test query")
        _insert_qa_label(qa_path, run_id, "990001", "TP")

        nonexistent_gold = Path(str(env_dbs["qa"]).replace("qa.db", "gold.json"))

        with patch("app.api.diagnostics._get_gold_set_path", return_value=nonexistent_gold), \
             patch("app.api.diagnostics._get_qa_db_path", return_value=qa_path), \
             patch("scripts.qa.db.QA_DB_PATH", qa_path):
            resp = client.get("/diagnostics/gold-set/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "1.0"
        assert len(data["queries"]) >= 1

    def test_export_empty(self, tmp_path, monkeypatch):
        """Returns empty queries when no data exists."""
        nonexistent_gold = tmp_path / "gold.json"
        nonexistent_qa = tmp_path / "qa.db"
        with patch("app.api.diagnostics._get_gold_set_path", return_value=nonexistent_gold), \
             patch("app.api.diagnostics._get_qa_db_path", return_value=nonexistent_qa):
            resp = client.get("/diagnostics/gold-set/export")
        assert resp.status_code == 200
        assert resp.json()["queries"] == []


# ---------------------------------------------------------------------------
# B10: POST /diagnostics/gold-set/regression
# ---------------------------------------------------------------------------


class TestRegression:
    """Tests for POST /diagnostics/gold-set/regression (B10)."""

    def test_regression_pass(self, tmp_path, monkeypatch):
        """Regression test passes when results match gold set."""
        bib_db = tmp_path / "bib.db"
        bib_db.touch()  # Just needs to exist for the path check
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(bib_db))

        gold_data = {
            "version": "1.0",
            "queries": [
                {
                    "query_text": "books by aldus",
                    "expected_includes": ["990001"],
                    "expected_excludes": ["990999"],
                }
            ],
        }
        gold_path = tmp_path / "gold.json"
        gold_path.write_text(json.dumps(gold_data))

        # Mock compile_query and execute_plan
        mock_plan = MagicMock()
        mock_result = MagicMock()
        mock_candidate = MagicMock()
        mock_candidate.record_id = "990001"
        mock_result.candidates = [mock_candidate]

        with patch("app.api.diagnostics._get_gold_set_path", return_value=gold_path), \
             patch("app.api.diagnostics._get_bib_db_path", return_value=bib_db), \
             patch("scripts.query.compile.compile_query", return_value=mock_plan), \
             patch("scripts.query.execute.execute_plan", return_value=mock_result):
            resp = client.post("/diagnostics/gold-set/regression")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 1
        assert data["passed"] == 1
        assert data["failed"] == 0
        assert data["results"][0]["status"] == "pass"

    def test_regression_fail(self, tmp_path, monkeypatch):
        """Regression test fails when expected record is missing."""
        bib_db = tmp_path / "bib.db"
        bib_db.touch()
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(bib_db))

        gold_data = {
            "version": "1.0",
            "queries": [
                {
                    "query_text": "books by aldus",
                    "expected_includes": ["990001", "990002"],
                    "expected_excludes": [],
                }
            ],
        }
        gold_path = tmp_path / "gold.json"
        gold_path.write_text(json.dumps(gold_data))

        mock_plan = MagicMock()
        mock_result = MagicMock()
        mock_candidate = MagicMock()
        mock_candidate.record_id = "990001"  # 990002 is missing
        mock_result.candidates = [mock_candidate]

        with patch("app.api.diagnostics._get_gold_set_path", return_value=gold_path), \
             patch("app.api.diagnostics._get_bib_db_path", return_value=bib_db), \
             patch("scripts.query.compile.compile_query", return_value=mock_plan), \
             patch("scripts.query.execute.execute_plan", return_value=mock_result):
            resp = client.post("/diagnostics/gold-set/regression")

        assert resp.status_code == 200
        data = resp.json()
        assert data["passed"] == 0
        assert data["failed"] == 1
        assert "990002" in data["results"][0]["missing"]

    def test_regression_no_gold(self, tmp_path, monkeypatch):
        """Returns 404 when no gold set exists."""
        bib_db = tmp_path / "bib.db"
        bib_db.touch()
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(bib_db))

        with patch("app.api.diagnostics._get_gold_set_path", return_value=tmp_path / "gold.json"), \
             patch("app.api.diagnostics._get_bib_db_path", return_value=bib_db), \
             patch("app.api.diagnostics._get_qa_db_path", return_value=tmp_path / "qa.db"):
            resp = client.post("/diagnostics/gold-set/regression")
        assert resp.status_code == 404

    def test_regression_empty_gold(self, tmp_path, monkeypatch):
        """Returns zero-count result for empty gold set."""
        bib_db = tmp_path / "bib.db"
        bib_db.touch()
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(bib_db))

        gold_data = {"version": "1.0", "queries": []}
        gold_path = tmp_path / "gold.json"
        gold_path.write_text(json.dumps(gold_data))

        with patch("app.api.diagnostics._get_gold_set_path", return_value=gold_path), \
             patch("app.api.diagnostics._get_bib_db_path", return_value=bib_db):
            resp = client.post("/diagnostics/gold-set/regression")
        assert resp.status_code == 200
        assert resp.json()["total_queries"] == 0


# ---------------------------------------------------------------------------
# B11: GET /diagnostics/tables
# ---------------------------------------------------------------------------


class TestListTables:
    """Tests for GET /diagnostics/tables (B11)."""

    def test_list_tables(self, tmp_bib_db, monkeypatch):
        """Returns all tables with row counts and column info."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables")
        assert resp.status_code == 200
        data = resp.json()
        tables = data["tables"]
        table_names = {t["name"] for t in tables}
        # Our fixture has 10 tables
        assert "records" in table_names
        assert "imprints" in table_names
        assert "titles" in table_names

        # Check records table has correct row count
        records_table = next(t for t in tables if t["name"] == "records")
        assert records_table["row_count"] == 2

        # Check columns are present
        assert len(records_table["columns"]) > 0
        col_names = {c["name"] for c in records_table["columns"]}
        assert "mms_id" in col_names

    def test_list_tables_missing_db(self, monkeypatch, tmp_path):
        """Returns 503 when DB does not exist."""
        missing = tmp_path / "missing.db"
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(missing))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=missing):
            resp = client.get("/diagnostics/tables")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# B12: GET /diagnostics/tables/{table_name}/rows
# ---------------------------------------------------------------------------


class TestTableRows:
    """Tests for GET /diagnostics/tables/{table_name}/rows (B12)."""

    def test_get_rows(self, tmp_bib_db, monkeypatch):
        """Returns paginated rows from an allowed table."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/records/rows")
        assert resp.status_code == 200
        data = resp.json()
        assert data["table_name"] == "records"
        assert data["total"] == 2
        assert len(data["rows"]) == 2

    def test_pagination(self, tmp_bib_db, monkeypatch):
        """Respects limit and offset."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/records/rows?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["rows"]) == 1
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_search(self, tmp_bib_db, monkeypatch):
        """Filters rows by search term across text columns."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/records/rows?search=990001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["rows"][0]["mms_id"] == "990001"

    def test_search_no_match(self, tmp_bib_db, monkeypatch):
        """Returns empty rows when search has no matches."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/records/rows?search=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["rows"] == []

    def test_disallowed_table(self, tmp_bib_db, monkeypatch):
        """Rejects table names not in the allowlist (SQL injection prevention)."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/sqlite_master/rows")
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]

    def test_sql_injection_attempt(self, tmp_bib_db, monkeypatch):
        """SQL injection via table name is blocked by allowlist."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get(
                '/diagnostics/tables/records; DROP TABLE records--/rows'
            )
        # FastAPI URL routing may not even match, but if it does, it must reject
        assert resp.status_code in (400, 404, 422)

    def test_missing_db(self, monkeypatch, tmp_path):
        """Returns 503 when DB does not exist."""
        missing = tmp_path / "missing.db"
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(missing))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=missing):
            resp = client.get("/diagnostics/tables/records/rows")
        assert resp.status_code == 503

    def test_all_allowed_tables(self, tmp_bib_db, monkeypatch):
        """All tables in the allowlist are accepted."""
        from app.api.diagnostics import ALLOWED_TABLES
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            for table in ALLOWED_TABLES:
                resp = client.get(f"/diagnostics/tables/{table}/rows?limit=1")
                assert resp.status_code == 200, f"Table {table} returned {resp.status_code}"

    def test_imprints_search(self, tmp_bib_db, monkeypatch):
        """Search works on tables with multiple text columns."""
        monkeypatch.setenv("BIBLIOGRAPHIC_DB_PATH", str(tmp_bib_db))
        with patch("app.api.diagnostics._get_bib_db_path", return_value=tmp_bib_db):
            resp = client.get("/diagnostics/tables/imprints/rows?search=venice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["rows"][0]["place_norm"] == "venice"
