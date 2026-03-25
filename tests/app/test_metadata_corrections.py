"""Tests for metadata correction endpoints.

Tests cover:
- POST /metadata/corrections (single correction)
- GET /metadata/corrections/history
- POST /metadata/corrections/batch
- Conflict detection, atomic writes, review log
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api import metadata as metadata_mod


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path):
    """Redirect alias maps and review log to temp dirs for test isolation."""
    # Create temp alias map paths
    place_dir = tmp_path / "place_aliases"
    place_dir.mkdir()
    publisher_dir = tmp_path / "publisher_aliases"
    publisher_dir.mkdir()
    agent_dir = tmp_path / "agent_aliases"
    agent_dir.mkdir()

    test_alias_paths = {
        "place": place_dir / "place_alias_map.json",
        "publisher": publisher_dir / "publisher_alias_map.json",
        "agent": agent_dir / "agent_alias_map.json",
    }
    test_review_log = tmp_path / "review_log.jsonl"

    with patch.object(metadata_mod, "_ALIAS_MAP_PATHS", test_alias_paths), \
         patch.object(metadata_mod, "_REVIEW_LOG_PATH", test_review_log), \
         patch.object(metadata_mod, "_count_affected_records", return_value=5):
        yield


@pytest.fixture
def client():
    """Provide a test client."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /metadata/corrections
# ---------------------------------------------------------------------------


class TestPostCorrection:
    """Tests for the single correction endpoint."""

    def test_create_new_correction(self, client):
        resp = client.post(
            "/metadata/corrections",
            json={
                "field": "place",
                "raw_value": "Lugduni Batavorum",
                "canonical_value": "leiden",
                "evidence": "Latin genitive, country=ne",
                "source": "agent",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "place_alias" in body["alias_map_updated"]
        assert body["records_affected"] == 5

    def test_creates_alias_map_file(self, client):
        """The alias map file should be created if it doesn't exist."""
        resp = client.post(
            "/metadata/corrections",
            json={
                "field": "publisher",
                "raw_value": "C. Fosset",
                "canonical_value": "fosset",
            },
        )
        assert resp.status_code == 200
        # Verify the alias map file now contains our entry
        alias_path = metadata_mod._ALIAS_MAP_PATHS["publisher"]
        assert alias_path.exists()
        data = json.loads(alias_path.read_text())
        assert data["C. Fosset"] == "fosset"

    def test_idempotent_same_mapping(self, client):
        """Submitting the same mapping twice should succeed (idempotent)."""
        payload = {
            "field": "place",
            "raw_value": "Paris",
            "canonical_value": "paris",
        }
        resp1 = client.post("/metadata/corrections", json=payload)
        assert resp1.status_code == 200

        resp2 = client.post("/metadata/corrections", json=payload)
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True

    def test_conflict_different_canonical(self, client):
        """Should return 409 if raw_value already maps to a different value."""
        client.post(
            "/metadata/corrections",
            json={
                "field": "place",
                "raw_value": "Lugdunum",
                "canonical_value": "lyon",
            },
        )
        resp = client.post(
            "/metadata/corrections",
            json={
                "field": "place",
                "raw_value": "Lugdunum",
                "canonical_value": "leiden",
            },
        )
        assert resp.status_code == 409
        assert "Conflict" in resp.json()["detail"]

    def test_invalid_field(self, client):
        resp = client.post(
            "/metadata/corrections",
            json={
                "field": "invalid_field",
                "raw_value": "test",
                "canonical_value": "test",
            },
        )
        assert resp.status_code == 400
        assert "Unknown field" in resp.json()["detail"]

    def test_review_log_written(self, client):
        """Correction should append an entry to the review log."""
        client.post(
            "/metadata/corrections",
            json={
                "field": "agent",
                "raw_value": "John Smith",
                "canonical_value": "smith, john",
                "evidence": "Name inversion",
                "source": "human",
            },
        )
        log_path = metadata_mod._REVIEW_LOG_PATH
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["field"] == "agent"
        assert entry["raw_value"] == "John Smith"
        assert entry["canonical_value"] == "smith, john"
        assert entry["evidence"] == "Name inversion"
        assert entry["source"] == "human"
        assert entry["action"] == "approved"
        assert "timestamp" in entry


# ---------------------------------------------------------------------------
# GET /metadata/corrections/history
# ---------------------------------------------------------------------------


class TestGetCorrectionHistory:
    """Tests for the correction history endpoint."""

    def test_empty_history(self, client):
        resp = client.get("/metadata/corrections/history")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["entries"] == []

    def test_history_after_corrections(self, client):
        """History should reflect submitted corrections."""
        client.post(
            "/metadata/corrections",
            json={"field": "place", "raw_value": "A", "canonical_value": "a"},
        )
        client.post(
            "/metadata/corrections",
            json={"field": "publisher", "raw_value": "B", "canonical_value": "b"},
        )
        resp = client.get("/metadata/corrections/history")
        body = resp.json()
        assert body["total"] == 2
        assert len(body["entries"]) == 2

    def test_history_field_filter(self, client):
        """Should filter by field when query param provided."""
        client.post(
            "/metadata/corrections",
            json={"field": "place", "raw_value": "A", "canonical_value": "a"},
        )
        client.post(
            "/metadata/corrections",
            json={"field": "publisher", "raw_value": "B", "canonical_value": "b"},
        )
        resp = client.get("/metadata/corrections/history?field=place")
        body = resp.json()
        assert body["total"] == 1
        assert body["entries"][0]["field"] == "place"

    def test_history_pagination(self, client):
        """Pagination should work correctly."""
        for i in range(5):
            client.post(
                "/metadata/corrections",
                json={
                    "field": "place",
                    "raw_value": f"val_{i}",
                    "canonical_value": f"canon_{i}",
                },
            )
        resp = client.get("/metadata/corrections/history?limit=2&offset=1")
        body = resp.json()
        assert body["total"] == 5
        assert len(body["entries"]) == 2
        assert body["entries"][0]["raw_value"] == "val_1"


# ---------------------------------------------------------------------------
# POST /metadata/corrections/batch
# ---------------------------------------------------------------------------


class TestPostBatchCorrections:
    """Tests for the batch correction endpoint."""

    def test_batch_success(self, client):
        resp = client.post(
            "/metadata/corrections/batch",
            json={
                "corrections": [
                    {"field": "place", "raw_value": "X", "canonical_value": "x"},
                    {"field": "place", "raw_value": "Y", "canonical_value": "y"},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_applied"] == 2
        assert body["total_skipped"] == 0
        assert body["total_records_affected"] == 10  # 5 per correction (mocked)
        assert len(body["results"]) == 2
        assert all(r["success"] for r in body["results"])

    def test_batch_with_conflict(self, client):
        """Conflicts in batch should be reported per-item, not fail the whole batch."""
        # Pre-seed a mapping
        client.post(
            "/metadata/corrections",
            json={"field": "place", "raw_value": "Z", "canonical_value": "z_original"},
        )
        resp = client.post(
            "/metadata/corrections/batch",
            json={
                "corrections": [
                    {"field": "place", "raw_value": "A", "canonical_value": "a"},
                    {
                        "field": "place",
                        "raw_value": "Z",
                        "canonical_value": "z_different",
                    },
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_applied"] == 1
        assert body["total_skipped"] == 1
        # Find the failed result
        failed = [r for r in body["results"] if not r["success"]]
        assert len(failed) == 1
        assert "Conflict" in failed[0]["error"]

    def test_batch_empty(self, client):
        resp = client.post(
            "/metadata/corrections/batch",
            json={"corrections": []},
        )
        assert resp.status_code == 400

    def test_batch_unknown_field(self, client):
        resp = client.post(
            "/metadata/corrections/batch",
            json={
                "corrections": [
                    {"field": "unknown", "raw_value": "A", "canonical_value": "a"},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_skipped"] == 1
        assert not body["results"][0]["success"]

    def test_batch_multi_field(self, client):
        """Batch with corrections across multiple fields."""
        resp = client.post(
            "/metadata/corrections/batch",
            json={
                "corrections": [
                    {"field": "place", "raw_value": "P1", "canonical_value": "p1"},
                    {"field": "publisher", "raw_value": "Pub1", "canonical_value": "pub1"},
                    {"field": "agent", "raw_value": "Ag1", "canonical_value": "ag1"},
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_applied"] == 3
        assert body["total_skipped"] == 0
        # Each field's alias map should have been created
        for field in ["place", "publisher", "agent"]:
            alias_path = metadata_mod._ALIAS_MAP_PATHS[field]
            assert alias_path.exists()

    def test_batch_writes_review_log(self, client):
        """Batch corrections should write to the review log."""
        client.post(
            "/metadata/corrections/batch",
            json={
                "corrections": [
                    {"field": "place", "raw_value": "M1", "canonical_value": "m1"},
                    {"field": "place", "raw_value": "M2", "canonical_value": "m2"},
                ]
            },
        )
        log_path = metadata_mod._REVIEW_LOG_PATH
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# POST /metadata/primo-urls
# ---------------------------------------------------------------------------


class TestPostPrimoUrls:
    """Tests for the batch Primo URL generation endpoint."""

    def test_single_mms_id(self, client):
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ["990009748710204146"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["urls"]) == 1
        entry = body["urls"][0]
        assert entry["mms_id"] == "990009748710204146"
        assert "990009748710204146" in entry["primo_url"]
        assert "query=990009748710204146" in entry["primo_url"]
        assert "primo.exlibrisgroup.com" in entry["primo_url"]

    def test_multiple_mms_ids(self, client):
        ids = ["990001111110204146", "990002222220204146", "990003333330204146"]
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ids},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["urls"]) == 3
        returned_ids = [e["mms_id"] for e in body["urls"]]
        assert returned_ids == ids

    def test_custom_base_url(self, client):
        custom = "https://custom.primo.example.com/display"
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ["990009748710204146"], "base_url": custom},
        )
        assert resp.status_code == 200
        url = resp.json()["urls"][0]["primo_url"]
        assert url.startswith(custom + "?")

    def test_empty_mms_ids(self, client):
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["urls"] == []

    def test_url_contains_expected_params(self, client):
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ["990009748710204146"]},
        )
        url = resp.json()["urls"][0]["primo_url"]
        assert "tab=TAU" in url
        assert "search_scope=TAU" in url
        assert "vid=" in url
        assert "query=990009748710204146" in url

    @patch.dict("os.environ", {"PRIMO_BASE_URL": "https://env.primo.example.com/view"})
    def test_env_var_override(self, client):
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ["990009748710204146"]},
        )
        url = resp.json()["urls"][0]["primo_url"]
        assert url.startswith("https://env.primo.example.com/view?")

    @patch.dict("os.environ", {"PRIMO_BASE_URL": "https://env.example.com"})
    def test_request_base_url_overrides_env(self, client):
        """base_url in the request body takes precedence over env var."""
        custom = "https://request.example.com/primo"
        resp = client.post(
            "/metadata/primo-urls",
            json={"mms_ids": ["990009748710204146"], "base_url": custom},
        )
        url = resp.json()["urls"][0]["primo_url"]
        assert url.startswith(custom + "?")


# ---------------------------------------------------------------------------
# GET /metadata/records/{mms_id}/primo
# ---------------------------------------------------------------------------


class TestGetPrimoUrl:
    """Tests for the single-record Primo URL endpoint."""

    def test_basic_get(self, client):
        resp = client.get("/metadata/records/990009748710204146/primo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["mms_id"] == "990009748710204146"
        assert "query=990009748710204146" in body["primo_url"]
        assert "primo.exlibrisgroup.com" in body["primo_url"]

    def test_url_structure(self, client):
        resp = client.get("/metadata/records/990001234560204146/primo")
        url = resp.json()["primo_url"]
        assert "tab=TAU" in url
        assert "search_scope=TAU" in url
        assert "query=990001234560204146" in url
        assert "vid=" in url
