"""Tests for metadata quality GET endpoints.

Tests cover:
- GET /metadata/coverage
- GET /metadata/issues
- GET /metadata/unmapped
- GET /metadata/methods
- GET /metadata/clusters

The corrections endpoints (POST /metadata/corrections, GET /metadata/corrections/history,
POST /metadata/corrections/batch, POST /metadata/primo-urls, GET /metadata/records/*/primo)
are tested separately in test_metadata_corrections.py.

Strategy: Mock `generate_coverage_report` and `cluster_field_gaps`/`cluster_all_gaps`
to return known dataclass instances, so we test endpoint wiring, serialization, query
param validation, and error handling without needing a real database.

For the /issues endpoint, we create a minimal in-memory SQLite database with just
enough schema and data to exercise the SQL queries directly.
"""

import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.metadata.audit import (
    ConfidenceBand,
    CoverageReport,
    FieldCoverage,
    LowConfidenceItem,
    MethodBreakdown,
)
from scripts.metadata.clustering import Cluster, ClusterValue
from tests.app.conftest import make_test_token


# ---------------------------------------------------------------------------
# Helpers: build known dataclass instances for mocking
# ---------------------------------------------------------------------------


def _make_field_coverage(
    total: int = 100,
    non_null: int = 90,
    methods: list | None = None,
    flagged: list | None = None,
) -> FieldCoverage:
    """Build a FieldCoverage dataclass with controlled data."""
    if methods is None:
        methods = [
            MethodBreakdown(method="exact", count=50),
            MethodBreakdown(method="alias_map", count=30),
            MethodBreakdown(method="base_clean", count=20),
        ]
    if flagged is None:
        flagged = [
            LowConfidenceItem(
                raw_value="unknown_val",
                norm_value=None,
                confidence=0.3,
                method="base_clean",
                frequency=15,
            ),
            LowConfidenceItem(
                raw_value="ambig_val",
                norm_value="ambig",
                confidence=0.6,
                method="alias_map",
                frequency=5,
            ),
        ]
    bands = [
        ConfidenceBand(band_label="0.00", lower=0.0, upper=0.5, count=10),
        ConfidenceBand(band_label="0.50", lower=0.5, upper=0.8, count=5),
        ConfidenceBand(band_label="0.80", lower=0.8, upper=0.95, count=20),
        ConfidenceBand(band_label="0.95", lower=0.95, upper=0.99, count=30),
        ConfidenceBand(band_label="0.99", lower=0.99, upper=1.01, count=35),
    ]
    return FieldCoverage(
        total_records=total,
        non_null_count=non_null,
        null_count=total - non_null,
        confidence_distribution=bands,
        method_distribution=methods,
        flagged_items=flagged,
    )


def _make_coverage_report() -> CoverageReport:
    """Build a complete CoverageReport with controlled data."""
    return CoverageReport(
        date_coverage=_make_field_coverage(
            methods=[
                MethodBreakdown(method="exact", count=60),
                MethodBreakdown(method="circa", count=25),
                MethodBreakdown(method="unparsed", count=15),
            ],
        ),
        place_coverage=_make_field_coverage(
            methods=[
                MethodBreakdown(method="alias_map", count=70),
                MethodBreakdown(method="base_clean", count=30),
            ],
        ),
        publisher_coverage=_make_field_coverage(),
        agent_name_coverage=_make_field_coverage(
            total=50,
            non_null=50,
            methods=[
                MethodBreakdown(method="base_clean", count=40),
                MethodBreakdown(method="ambiguous", count=10),
            ],
        ),
        agent_role_coverage=_make_field_coverage(
            total=50,
            non_null=50,
            methods=[
                MethodBreakdown(method="relator_code", count=45),
                MethodBreakdown(method="inferred", count=5),
            ],
            flagged=[
                LowConfidenceItem(
                    raw_value="role_raw",
                    norm_value="role_norm",
                    confidence=0.5,
                    method="inferred",
                    frequency=3,
                ),
            ],
        ),
        total_imprint_rows=100,
        total_agent_rows=50,
    )


def _make_cluster(
    cluster_id: str = "cluster_1",
    field: str = "place",
    cluster_type: str = "latin_place_names",
    priority: float = 25.0,
) -> Cluster:
    """Build a Cluster dataclass with controlled data."""
    return Cluster(
        cluster_id=cluster_id,
        field=field,
        cluster_type=cluster_type,
        values=[
            ClusterValue(
                raw_value="Lugduni",
                frequency=15,
                confidence=0.3,
                method="base_clean",
            ),
            ClusterValue(
                raw_value="Lugdunum",
                frequency=10,
                confidence=0.4,
                method="base_clean",
            ),
        ],
        proposed_canonical="lyon",
        evidence={"country": "fr", "pattern": "latin_genitive"},
        priority_score=priority,
        total_records_affected=25,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Provide a test client with auth token."""
    return TestClient(app, cookies={"access_token": make_test_token()})


@pytest.fixture
def mock_report():
    """Provide a mocked coverage report via generate_coverage_report."""
    report = _make_coverage_report()
    with patch(
        "app.api.metadata.generate_coverage_report", return_value=report
    ) as mock_fn:
        yield mock_fn, report


@pytest.fixture
def issues_db(tmp_path):
    """Create an in-memory-like SQLite database with test data for /issues.

    The /issues endpoint queries the imprints and agents tables directly,
    referencing mms_id as a column name. We create a simplified schema
    matching what the endpoint code expects.
    """
    db_path = tmp_path / "test_bib.db"
    conn = sqlite3.connect(str(db_path))

    # Create records table (master table with mms_id)
    conn.execute("""
        CREATE TABLE records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mms_id TEXT NOT NULL
        )
    """)

    # Create minimal imprints table with record_id FK (as expected by endpoint code)
    conn.execute("""
        CREATE TABLE imprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES records(id),
            date_raw TEXT,
            date_start INTEGER,
            date_confidence REAL,
            date_method TEXT,
            place_raw TEXT,
            place_norm TEXT,
            place_confidence REAL,
            place_method TEXT,
            publisher_raw TEXT,
            publisher_norm TEXT,
            publisher_confidence REAL,
            publisher_method TEXT
        )
    """)

    # Create minimal agents table with record_id FK
    conn.execute("""
        CREATE TABLE agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL REFERENCES records(id),
            agent_raw TEXT NOT NULL,
            agent_norm TEXT NOT NULL,
            agent_confidence REAL NOT NULL,
            agent_method TEXT NOT NULL,
            role_raw TEXT,
            role_norm TEXT,
            role_confidence REAL,
            role_method TEXT
        )
    """)

    # Insert records (one per MMS ID, id values 1-8)
    mms_ids = ["MMS001", "MMS002", "MMS003", "MMS004",
               "MMS005", "MMS006", "MMS007", "MMS008"]
    conn.executemany(
        "INSERT INTO records (mms_id) VALUES (?)",
        [(m,) for m in mms_ids],
    )

    # Insert test imprints with varying confidence levels
    # record_id corresponds to records.id (1-8 matching MMS001-MMS008)
    imprint_rows = [
        (1, "1650", 1650, 0.99, "exact", "Paris", "paris", 0.95, "alias_map", "Elsevier", "elsevier", 0.95, "alias_map"),
        (2, "[1700]", 1700, 0.90, "bracketed", "London", "london", 0.95, "alias_map", "C. Fosset", "fosset", 0.80, "base_clean"),
        (3, "ca. 1550", 1550, 0.80, "circa", "אמשטרדם", "amsterdam", 0.80, "base_clean", "Unknown", None, 0.30, "base_clean"),
        (4, None, None, None, "missing", "Lugduni", None, 0.30, "base_clean", None, None, None, None),
        (5, "1500-1599", 1500, 0.85, "range", "[Berlin]", "berlin", 0.80, "base_clean", "Oxford", "oxford", 0.95, "alias_map"),
        (6, "???", None, 0.0, "unparsed", "Venice", "venice", 0.95, "alias_map", "Press", None, 0.50, "base_clean"),
        (7, "1680", 1680, 0.99, "exact", "Rome", "rome", 0.95, "alias_map", "Printer A", "printer_a", 0.70, "base_clean"),
        (8, "1720", 1720, 0.99, "exact", "Madrid", "madrid", 0.90, "alias_map", "Printer B", "printer_b", 0.60, "base_clean"),
    ]
    conn.executemany(
        """INSERT INTO imprints
           (record_id, date_raw, date_start, date_confidence, date_method,
            place_raw, place_norm, place_confidence, place_method,
            publisher_raw, publisher_norm, publisher_confidence, publisher_method)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        imprint_rows,
    )

    # Insert test agents with varying confidence
    # record_id 1-4 map to MMS001-MMS004
    agent_rows = [
        (1, "John Smith", "smith, john", 0.95, "base_clean", "printer", "printer", 0.90, "relator_code"),
        (2, "Jan de Vries", "vries, jan de", 0.70, "base_clean", "prt", "printer", 0.95, "relator_code"),
        (3, "Unknown Author", "unknown author", 0.30, "ambiguous", None, "author", 0.50, "inferred"),
        (4, "Ibn Sina", "ibn sina", 0.60, "base_clean", "aut", "author", 0.95, "relator_code"),
    ]
    conn.executemany(
        """INSERT INTO agents
           (record_id, agent_raw, agent_norm, agent_confidence, agent_method,
            role_raw, role_norm, role_confidence, role_method)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        agent_rows,
    )

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# GET /metadata/coverage
# ---------------------------------------------------------------------------


class TestGetCoverage:
    """Tests for the coverage endpoint."""

    def test_returns_200_with_valid_structure(self, client, mock_report):
        """Coverage endpoint returns 200 with expected top-level fields."""
        resp = client.get("/metadata/coverage")
        assert resp.status_code == 200
        body = resp.json()
        expected_keys = {
            "date_coverage",
            "place_coverage",
            "publisher_coverage",
            "agent_name_coverage",
            "agent_role_coverage",
            "total_imprint_rows",
            "total_agent_rows",
        }
        assert set(body.keys()) == expected_keys

    def test_total_row_counts(self, client, mock_report):
        """Coverage response includes correct total row counts."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        assert body["total_imprint_rows"] == 100
        assert body["total_agent_rows"] == 50

    def test_field_coverage_has_required_fields(self, client, mock_report):
        """Each field coverage object has the expected sub-fields."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        for field_key in [
            "date_coverage",
            "place_coverage",
            "publisher_coverage",
            "agent_name_coverage",
            "agent_role_coverage",
        ]:
            fc = body[field_key]
            assert "total_records" in fc
            assert "non_null_count" in fc
            assert "null_count" in fc
            assert "confidence_distribution" in fc
            assert "method_distribution" in fc
            assert "flagged_items" in fc

    def test_confidence_distribution_structure(self, client, mock_report):
        """Confidence distribution contains bands with correct structure."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        bands = body["date_coverage"]["confidence_distribution"]
        assert len(bands) == 5
        for band in bands:
            assert "band_label" in band
            assert "lower" in band
            assert "upper" in band
            assert "count" in band
            assert isinstance(band["count"], int)

    def test_method_distribution_structure(self, client, mock_report):
        """Method distribution contains entries with method and count."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        methods = body["date_coverage"]["method_distribution"]
        assert len(methods) == 3
        method_names = [m["method"] for m in methods]
        assert "exact" in method_names
        assert "circa" in method_names
        assert "unparsed" in method_names

    def test_flagged_items_structure(self, client, mock_report):
        """Flagged items contain raw_value, confidence, frequency, etc."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        flagged = body["place_coverage"]["flagged_items"]
        assert len(flagged) == 2
        item = flagged[0]
        assert "raw_value" in item
        assert "confidence" in item
        assert "frequency" in item
        assert "method" in item

    def test_null_counts_are_correct(self, client, mock_report):
        """null_count = total_records - non_null_count."""
        resp = client.get("/metadata/coverage")
        body = resp.json()
        fc = body["date_coverage"]
        assert fc["null_count"] == fc["total_records"] - fc["non_null_count"]

    def test_database_not_found_returns_503(self, client):
        """When database file is missing, returns 503."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=FileNotFoundError("Database not found"),
        ):
            resp = client.get("/metadata/coverage")
            assert resp.status_code == 503

    def test_database_error_returns_500(self, client):
        """When database has operational error, returns 500."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=sqlite3.OperationalError("no such table"),
        ):
            resp = client.get("/metadata/coverage")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /metadata/issues
# ---------------------------------------------------------------------------


class TestGetIssues:
    """Tests for the issues endpoint (low-confidence records)."""

    def test_returns_200_with_valid_field(self, client, issues_db):
        """Issues endpoint returns 200 for valid field param."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=date")
            assert resp.status_code == 200
            body = resp.json()
            assert body["field"] == "date"
            assert "total" in body
            assert "items" in body
            assert isinstance(body["items"], list)

    def test_default_max_confidence_is_0_8(self, client, issues_db):
        """Default max_confidence of 0.8 filters correctly."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=date")
            body = resp.json()
            assert body["max_confidence"] == 0.8
            # All returned items should have confidence <= 0.8
            for item in body["items"]:
                assert item["confidence"] <= 0.8

    def test_filters_by_max_confidence(self, client, issues_db):
        """Custom max_confidence threshold filters correctly."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            # Very low threshold - should return fewer results
            resp = client.get("/metadata/issues?field=date&max_confidence=0.0")
            body = resp.json()
            for item in body["items"]:
                assert item["confidence"] <= 0.0

    def test_pagination_limit(self, client, issues_db):
        """Limit parameter controls page size."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=date&limit=2&max_confidence=1.0")
            body = resp.json()
            assert body["limit"] == 2
            assert len(body["items"]) <= 2

    def test_pagination_offset(self, client, issues_db):
        """Offset parameter shifts the page."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            # Get all results first
            resp_all = client.get(
                "/metadata/issues?field=date&limit=100&max_confidence=1.0"
            )
            all_items = resp_all.json()["items"]

            # Now get with offset
            resp_offset = client.get(
                "/metadata/issues?field=date&limit=100&offset=1&max_confidence=1.0"
            )
            offset_items = resp_offset.json()["items"]

            # Offset by 1 should skip the first item
            if len(all_items) > 1:
                assert len(offset_items) == len(all_items) - 1

    def test_total_reflects_all_matching_records(self, client, issues_db):
        """Total count reflects all matches, not just the page."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get(
                "/metadata/issues?field=date&limit=1&max_confidence=1.0"
            )
            body = resp.json()
            # Total should be >= items returned in this page
            assert body["total"] >= len(body["items"])

    def test_place_field_returns_place_data(self, client, issues_db):
        """Issues for 'place' field returns place-related data."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=place&max_confidence=0.5")
            body = resp.json()
            assert body["field"] == "place"
            # MMS004 has place_confidence=0.3
            mms_ids = [item["mms_id"] for item in body["items"]]
            assert "MMS004" in mms_ids

    def test_publisher_field(self, client, issues_db):
        """Issues for 'publisher' field returns publisher data."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get(
                "/metadata/issues?field=publisher&max_confidence=0.6"
            )
            body = resp.json()
            assert body["field"] == "publisher"
            # MMS003 has publisher_confidence=0.30, MMS006 has 0.50
            for item in body["items"]:
                assert item["confidence"] <= 0.6

    def test_agent_field(self, client, issues_db):
        """Issues for 'agent' field returns agent data."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=agent&max_confidence=0.7")
            body = resp.json()
            assert body["field"] == "agent"
            for item in body["items"]:
                assert item["confidence"] <= 0.7

    def test_items_ordered_by_confidence_ascending(self, client, issues_db):
        """Results are ordered by confidence ascending (lowest first)."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get(
                "/metadata/issues?field=date&max_confidence=1.0&limit=100"
            )
            items = resp.json()["items"]
            confidences = [item["confidence"] for item in items]
            assert confidences == sorted(confidences)

    def test_missing_field_param_returns_422(self, client, issues_db):
        """Missing required 'field' parameter returns 422."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues")
            assert resp.status_code == 422

    def test_invalid_field_value_returns_422(self, client, issues_db):
        """Invalid field value returns 422 (FastAPI enum validation)."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get("/metadata/issues?field=invalid_field")
            assert resp.status_code == 422

    def test_issue_record_structure(self, client, issues_db):
        """Each issue record has mms_id, raw_value, norm_value, confidence, method."""
        with patch("app.api.metadata._get_db_path", return_value=issues_db):
            resp = client.get(
                "/metadata/issues?field=date&max_confidence=1.0"
            )
            body = resp.json()
            if body["items"]:
                item = body["items"][0]
                assert "mms_id" in item
                assert "raw_value" in item
                assert "confidence" in item
                assert "method" in item
                # norm_value can be null
                assert "norm_value" in item


# ---------------------------------------------------------------------------
# GET /metadata/unmapped
# ---------------------------------------------------------------------------


class TestGetUnmapped:
    """Tests for the unmapped values endpoint."""

    def test_returns_200_for_valid_field(self, client, mock_report):
        """Unmapped endpoint returns 200 for a valid field."""
        resp = client.get("/metadata/unmapped?field=place")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_returns_frequency_sorted_results(self, client, mock_report):
        """Results are sorted by frequency descending."""
        resp = client.get("/metadata/unmapped?field=place")
        body = resp.json()
        if len(body) >= 2:
            frequencies = [item["frequency"] for item in body]
            assert frequencies == sorted(frequencies, reverse=True)

    def test_unmapped_item_structure(self, client, mock_report):
        """Each unmapped value has raw_value, frequency, confidence, method."""
        resp = client.get("/metadata/unmapped?field=date")
        body = resp.json()
        assert len(body) > 0
        item = body[0]
        assert "raw_value" in item
        assert "frequency" in item
        assert "confidence" in item
        assert "method" in item

    def test_date_field(self, client, mock_report):
        """Unmapped for 'date' returns date flagged items."""
        resp = client.get("/metadata/unmapped?field=date")
        assert resp.status_code == 200
        body = resp.json()
        # Should have the flagged items from our mock
        assert len(body) == 2
        raw_values = [item["raw_value"] for item in body]
        assert "unknown_val" in raw_values

    def test_publisher_field(self, client, mock_report):
        """Unmapped for 'publisher' returns publisher flagged items."""
        resp = client.get("/metadata/unmapped?field=publisher")
        assert resp.status_code == 200

    def test_agent_field(self, client, mock_report):
        """Unmapped for 'agent' returns agent name flagged items."""
        resp = client.get("/metadata/unmapped?field=agent")
        assert resp.status_code == 200

    def test_missing_field_returns_422(self, client, mock_report):
        """Missing 'field' parameter returns 422."""
        resp = client.get("/metadata/unmapped")
        assert resp.status_code == 422

    def test_invalid_field_returns_422(self, client, mock_report):
        """Invalid field value returns 422."""
        resp = client.get("/metadata/unmapped?field=invalid")
        assert resp.status_code == 422

    def test_database_not_found_returns_503(self, client):
        """When database is missing, returns 503."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=FileNotFoundError("not found"),
        ):
            resp = client.get("/metadata/unmapped?field=place")
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /metadata/methods
# ---------------------------------------------------------------------------


class TestGetMethods:
    """Tests for the method distribution endpoint."""

    def test_returns_200_for_valid_field(self, client, mock_report):
        """Methods endpoint returns 200 for a valid field."""
        resp = client.get("/metadata/methods?field=date")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)

    def test_method_entry_structure(self, client, mock_report):
        """Each method entry has method, count, and percentage."""
        resp = client.get("/metadata/methods?field=date")
        body = resp.json()
        assert len(body) > 0
        entry = body[0]
        assert "method" in entry
        assert "count" in entry
        assert "percentage" in entry

    def test_percentages_sum_to_approximately_100(self, client, mock_report):
        """Percentages should sum to approximately 100%."""
        resp = client.get("/metadata/methods?field=date")
        body = resp.json()
        total_pct = sum(entry["percentage"] for entry in body)
        assert 99.0 <= total_pct <= 101.0, f"Percentages sum to {total_pct}"

    def test_date_methods(self, client, mock_report):
        """Date field returns expected normalization methods."""
        resp = client.get("/metadata/methods?field=date")
        body = resp.json()
        method_names = [entry["method"] for entry in body]
        assert "exact" in method_names
        assert "circa" in method_names
        assert "unparsed" in method_names

    def test_place_methods(self, client, mock_report):
        """Place field returns expected methods."""
        resp = client.get("/metadata/methods?field=place")
        body = resp.json()
        method_names = [entry["method"] for entry in body]
        assert "alias_map" in method_names
        assert "base_clean" in method_names

    def test_agent_methods(self, client, mock_report):
        """Agent field returns agent_name_coverage methods."""
        resp = client.get("/metadata/methods?field=agent")
        body = resp.json()
        method_names = [entry["method"] for entry in body]
        assert "base_clean" in method_names
        assert "ambiguous" in method_names

    def test_counts_are_positive_integers(self, client, mock_report):
        """All method counts should be positive integers."""
        resp = client.get("/metadata/methods?field=date")
        body = resp.json()
        for entry in body:
            assert isinstance(entry["count"], int)
            assert entry["count"] > 0

    def test_missing_field_returns_422(self, client, mock_report):
        """Missing 'field' parameter returns 422."""
        resp = client.get("/metadata/methods")
        assert resp.status_code == 422

    def test_invalid_field_returns_422(self, client, mock_report):
        """Invalid field value returns 422."""
        resp = client.get("/metadata/methods?field=bogus")
        assert resp.status_code == 422

    def test_database_not_found_returns_503(self, client):
        """When database is missing, returns 503."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=FileNotFoundError("not found"),
        ):
            resp = client.get("/metadata/methods?field=place")
            assert resp.status_code == 503

    def test_database_error_returns_500(self, client):
        """When database has operational error, returns 500."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=sqlite3.OperationalError("broken"),
        ):
            resp = client.get("/metadata/methods?field=place")
            assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /metadata/clusters
# ---------------------------------------------------------------------------


class TestGetClusters:
    """Tests for the gap clusters endpoint."""

    def test_returns_200_with_field_filter(self, client, mock_report):
        """Clusters endpoint returns 200 when filtering by field."""
        cluster = _make_cluster()
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[cluster]
        ):
            resp = client.get("/metadata/clusters?field=place")
            assert resp.status_code == 200
            body = resp.json()
            assert isinstance(body, list)
            assert len(body) == 1

    def test_cluster_structure(self, client, mock_report):
        """Each cluster has expected fields."""
        cluster = _make_cluster()
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[cluster]
        ):
            resp = client.get("/metadata/clusters?field=place")
            body = resp.json()
            c = body[0]
            assert "cluster_id" in c
            assert "field" in c
            assert "cluster_type" in c
            assert "values" in c
            assert "proposed_canonical" in c
            assert "evidence" in c
            assert "priority_score" in c
            assert "total_records_affected" in c

    def test_cluster_values_structure(self, client, mock_report):
        """Each value in a cluster has raw_value, frequency, confidence, method."""
        cluster = _make_cluster()
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[cluster]
        ):
            resp = client.get("/metadata/clusters?field=place")
            body = resp.json()
            values = body[0]["values"]
            assert len(values) == 2
            val = values[0]
            assert "raw_value" in val
            assert "frequency" in val
            assert "confidence" in val
            assert "method" in val

    def test_cluster_field_matches_query(self, client, mock_report):
        """Cluster field matches the requested field."""
        cluster = _make_cluster(field="publisher")
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[cluster]
        ):
            resp = client.get("/metadata/clusters?field=publisher")
            body = resp.json()
            assert body[0]["field"] == "publisher"

    def test_no_field_returns_all_clusters(self, client, mock_report):
        """Omitting field returns clusters from all fields."""
        clusters_map = {
            "date": [_make_cluster(cluster_id="c_date", field="date", priority=10.0)],
            "place": [_make_cluster(cluster_id="c_place", field="place", priority=25.0)],
            "publisher": [],
            "agent": [_make_cluster(cluster_id="c_agent", field="agent", priority=5.0)],
        }
        with patch(
            "app.api.metadata.cluster_all_gaps", return_value=clusters_map
        ):
            resp = client.get("/metadata/clusters")
            assert resp.status_code == 200
            body = resp.json()
            # Should contain clusters from date + place + agent (publisher is empty)
            assert len(body) == 3
            # Should be sorted by priority_score descending
            priorities = [c["priority_score"] for c in body]
            assert priorities == sorted(priorities, reverse=True)

    def test_all_clusters_sorted_by_priority(self, client, mock_report):
        """When fetching all clusters, they are sorted by priority_score desc."""
        clusters_map = {
            "date": [_make_cluster(cluster_id="c1", field="date", priority=3.0)],
            "place": [_make_cluster(cluster_id="c2", field="place", priority=50.0)],
            "publisher": [_make_cluster(cluster_id="c3", field="publisher", priority=20.0)],
            "agent": [_make_cluster(cluster_id="c4", field="agent", priority=1.0)],
        }
        with patch(
            "app.api.metadata.cluster_all_gaps", return_value=clusters_map
        ):
            resp = client.get("/metadata/clusters")
            body = resp.json()
            priorities = [c["priority_score"] for c in body]
            assert priorities == sorted(priorities, reverse=True)

    def test_empty_clusters(self, client, mock_report):
        """Endpoint returns empty list when no clusters found."""
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[]
        ):
            resp = client.get("/metadata/clusters?field=date")
            assert resp.status_code == 200
            assert resp.json() == []

    def test_cluster_proposed_canonical_can_be_null(self, client, mock_report):
        """proposed_canonical field can be null."""
        cluster = _make_cluster()
        cluster.proposed_canonical = None
        with patch(
            "app.api.metadata.cluster_field_gaps", return_value=[cluster]
        ):
            resp = client.get("/metadata/clusters?field=place")
            body = resp.json()
            assert body[0]["proposed_canonical"] is None

    def test_invalid_field_returns_422(self, client, mock_report):
        """Invalid field value returns 422."""
        resp = client.get("/metadata/clusters?field=invalid")
        assert resp.status_code == 422

    def test_database_not_found_returns_503(self, client):
        """When database is missing, returns 503."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=FileNotFoundError("not found"),
        ):
            resp = client.get("/metadata/clusters?field=place")
            assert resp.status_code == 503

    def test_database_error_returns_500(self, client):
        """When database has operational error, returns 500."""
        with patch(
            "app.api.metadata.generate_coverage_report",
            side_effect=sqlite3.OperationalError("broken"),
        ):
            resp = client.get("/metadata/clusters")
            assert resp.status_code == 500
