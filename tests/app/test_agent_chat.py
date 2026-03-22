"""Tests for POST /metadata/agent/chat endpoint.

Tests cover:
- Analysis route (empty message and "analyze")
- Date field analysis
- Invalid field validation (422)
- Message routing (analyze vs propose vs cluster vs free-form)
- Graceful handling when OPENAI_API_KEY is not set

Strategy: Monkeypatch the agent creation to return mock agents with known
return values, so we test endpoint wiring, routing, and serialization
without needing a real database or LLM.
"""

from dataclasses import dataclass, field as dc_field
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from scripts.metadata.agent_harness import GapRecord, ProposedMapping
from scripts.metadata.clustering import Cluster, ClusterValue


# ---------------------------------------------------------------------------
# Helpers: mock analysis dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MockPlaceAnalysis:
    total_places: int = 200
    high_confidence_count: int = 150
    medium_confidence_count: int = 30
    low_confidence_count: int = 20
    unmapped_count: int = 15
    clusters: list = dc_field(default_factory=list)
    top_gaps: list = dc_field(default_factory=list)


@dataclass
class MockDateAnalysis:
    total_dates: int = 300
    parsed_count: int = 250
    unparsed_count: int = 50
    by_method: dict = dc_field(default_factory=lambda: {"exact": 200, "circa": 50})
    by_pattern: dict = dc_field(default_factory=dict)
    clusters: list = dc_field(default_factory=list)
    top_unparsed: list = dc_field(default_factory=list)


@dataclass
class MockPublisherAnalysis:
    total_publishers: int = 100
    mapped_count: int = 70
    unmapped_count: int = 20
    missing_count: int = 10
    clusters: list = dc_field(default_factory=list)
    top_gaps: list = dc_field(default_factory=list)


@dataclass
class MockAgentAnalysis:
    total_agents: int = 80
    with_authority: int = 50
    without_authority: int = 30
    low_confidence_count: int = 15
    missing_role_count: int = 5
    top_gaps: list = dc_field(default_factory=list)


def _make_cluster(
    cluster_id: str = "cluster_0",
    cluster_type: str = "near_match",
    field: str = "place",
) -> Cluster:
    """Build a Cluster with known test data."""
    return Cluster(
        cluster_id=cluster_id,
        field=field,
        cluster_type=cluster_type,
        values=[
            ClusterValue(
                raw_value="paris :",
                frequency=10,
                confidence=0.5,
                method="base_clean",
            ),
            ClusterValue(
                raw_value="pariz",
                frequency=3,
                confidence=0.4,
                method="base_clean",
            ),
        ],
        proposed_canonical="paris",
        evidence={"note": "test cluster"},
        priority_score=13.0,
        total_records_affected=13,
    )


def _make_proposals() -> List[ProposedMapping]:
    """Build mock ProposedMapping list."""
    return [
        ProposedMapping(
            raw_value="paris :",
            canonical_value="paris",
            confidence=0.95,
            reasoning="Standard French capital",
            evidence_sources=["alias_map", "country_code"],
            field="place",
        ),
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mock_db_exists(tmp_path, monkeypatch):
    """Ensure the database path check passes (mock Path.exists)."""
    fake_db = tmp_path / "bibliographic.db"
    fake_db.touch()
    monkeypatch.setattr(
        "app.api.metadata._get_db_path",
        lambda: fake_db,
    )


@pytest.fixture
def mock_place_agent():
    """Create a mock PlaceAgent with controlled behavior."""
    agent = MagicMock()
    agent.analyze.return_value = MockPlaceAnalysis(
        clusters=[_make_cluster()],
    )
    agent.get_clusters.return_value = [_make_cluster()]
    agent.propose_mappings.return_value = _make_proposals()
    return agent


@pytest.fixture
def mock_date_agent():
    """Create a mock DateAgent with controlled behavior."""
    agent = MagicMock()
    agent.analyze.return_value = MockDateAnalysis()
    # DateAgent does not have get_clusters or propose_mappings
    del agent.get_clusters
    del agent.propose_mappings
    return agent


@pytest.fixture
def mock_publisher_agent():
    """Create a mock PublisherAgent with controlled behavior."""
    agent = MagicMock()
    agent.analyze.return_value = MockPublisherAnalysis(
        clusters=[_make_cluster(field="publisher", cluster_type="latin_formula")],
    )
    agent.get_clusters.return_value = [
        _make_cluster(field="publisher", cluster_type="latin_formula")
    ]
    agent.propose_mappings.return_value = _make_proposals()
    return agent


@pytest.fixture
def mock_agent_agent():
    """Create a mock NameAgent with controlled behavior."""
    agent = MagicMock()
    agent.analyze.return_value = MockAgentAnalysis()
    del agent.get_clusters
    del agent.propose_mappings
    return agent


# ---------------------------------------------------------------------------
# Tests: Analysis route
# ---------------------------------------------------------------------------


class TestAnalysisRoute:
    """Tests for the analysis route (empty message or 'analyze')."""

    def test_place_analysis_empty_message(self, mock_place_agent):
        """POST with field=place and empty message returns analysis."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ) as mock_harness, patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": ""},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "analysis"
        assert data["field"] == "place"
        assert "Total places: 200" in data["response"]
        assert "High confidence" in data["response"]
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["cluster_id"] == "cluster_0"
        assert data["proposals"] == []

    def test_place_analysis_analyze_keyword(self, mock_place_agent):
        """POST with message='analyze' also triggers analysis."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "analyze"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "analysis"

    def test_date_analysis(self, mock_date_agent):
        """POST with field=date returns date-specific analysis."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_date_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "date"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "analysis"
        assert data["field"] == "date"
        assert "Total dates: 300" in data["response"]
        assert "Parsed" in data["response"]
        assert "Unparsed" in data["response"]

    def test_publisher_analysis(self, mock_publisher_agent):
        """POST with field=publisher returns publisher-specific analysis."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_publisher_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "publisher", "message": ""},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "analysis"
        assert data["field"] == "publisher"
        assert "Total publishers: 100" in data["response"]

    def test_agent_analysis(self, mock_agent_agent):
        """POST with field=agent returns agent-specific analysis."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_agent_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "agent"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "analysis"
        assert data["field"] == "agent"
        assert "Total agents: 80" in data["response"]


# ---------------------------------------------------------------------------
# Tests: Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for request validation."""

    def test_invalid_field_returns_422(self):
        """POST with invalid field returns 422."""
        resp = client.post(
            "/metadata/agent/chat",
            json={"field": "invalid_field", "message": ""},
        )
        assert resp.status_code == 422
        assert "Invalid field" in resp.json()["detail"]

    def test_missing_field_returns_422(self):
        """POST without field returns 422."""
        resp = client.post(
            "/metadata/agent/chat",
            json={"message": "hello"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: Propose route
# ---------------------------------------------------------------------------


class TestProposeRoute:
    """Tests for the propose: message routing."""

    def test_propose_returns_proposals(self, mock_place_agent):
        """POST with 'propose:cluster_0' returns proposals."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ), patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "propose:cluster_0"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "proposals"
        assert len(data["proposals"]) == 1
        assert data["proposals"][0]["raw_value"] == "paris :"
        assert data["proposals"][0]["canonical_value"] == "paris"
        assert data["proposals"][0]["confidence"] == 0.95

    def test_propose_without_api_key(self, mock_place_agent):
        """POST propose: without OPENAI_API_KEY returns empty proposals with note."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ), patch.dict("os.environ", {}, clear=False) as env:
            # Ensure OPENAI_API_KEY is not set
            env.pop("OPENAI_API_KEY", None)
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "propose:cluster_0"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["proposals"] == []
        assert "API key" in data["response"]

    def test_propose_cluster_not_found(self, mock_place_agent):
        """POST propose: with unknown cluster returns not-found message."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ), patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "propose:nonexistent"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "not found" in data["response"]
        assert len(data["clusters"]) >= 1  # returns available clusters

    def test_propose_unsupported_agent(self, mock_date_agent):
        """POST propose: on an agent without propose_mappings returns helpful message."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_date_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "date", "message": "propose:cluster_0"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "does not support" in data["response"]


# ---------------------------------------------------------------------------
# Tests: Cluster route
# ---------------------------------------------------------------------------


class TestClusterRoute:
    """Tests for the cluster: message routing."""

    def test_cluster_details(self, mock_place_agent):
        """POST with 'cluster:cluster_0' returns cluster details."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "cluster:cluster_0"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "answer"
        assert "cluster_0" in data["response"]
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["cluster_id"] == "cluster_0"

    def test_cluster_not_found(self, mock_place_agent):
        """POST cluster: with unknown cluster returns not-found message."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "cluster:nonexistent"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "not found" in data["response"]

    def test_cluster_unsupported_agent(self, mock_date_agent):
        """POST cluster: on agent without get_clusters returns helpful message."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_date_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "date", "message": "cluster:0"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "does not support" in data["response"]


# ---------------------------------------------------------------------------
# Tests: Free-form question route
# ---------------------------------------------------------------------------


class TestFreeFormRoute:
    """Tests for free-form question routing."""

    def test_freeform_returns_grounding_data(self, mock_place_agent):
        """POST with arbitrary message returns grounding summary."""
        mock_harness = MagicMock()
        mock_harness.query_gaps.return_value = [
            GapRecord(
                mms_id="990001",
                field="place",
                raw_value="paris :",
                current_norm=None,
                confidence=0.5,
                method="base_clean",
            ),
            GapRecord(
                mms_id="990002",
                field="place",
                raw_value="paris :",
                current_norm=None,
                confidence=0.5,
                method="base_clean",
            ),
            GapRecord(
                mms_id="990003",
                field="place",
                raw_value="amstrdm",
                current_norm=None,
                confidence=0.4,
                method="base_clean",
            ),
        ]

        with patch(
            "app.api.metadata._create_agent_harness",
            return_value=mock_harness,
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place", "message": "what are the top issues?"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "answer"
        assert data["field"] == "place"
        assert "low-confidence" in data["response"]
        assert "paris :" in data["response"]

    def test_freeform_with_session_id(self, mock_place_agent):
        """POST with session_id is accepted (session_id is optional)."""
        mock_harness = MagicMock()
        mock_harness.query_gaps.return_value = []

        with patch(
            "app.api.metadata._create_agent_harness",
            return_value=mock_harness,
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={
                    "field": "place",
                    "message": "anything",
                    "session_id": "test-session-123",
                },
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: Response structure
# ---------------------------------------------------------------------------


class TestResponseStructure:
    """Tests for response model structure."""

    def test_response_has_required_fields(self, mock_place_agent):
        """Response contains all required fields from AgentChatResponse."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "proposals" in data
        assert "clusters" in data
        assert "field" in data
        assert "action" in data

    def test_cluster_summary_structure(self, mock_place_agent):
        """Cluster summaries have the expected fields."""
        with patch(
            "app.api.metadata._create_agent_harness"
        ), patch(
            "app.api.metadata._create_specialist_agent",
            return_value=mock_place_agent,
        ):
            resp = client.post(
                "/metadata/agent/chat",
                json={"field": "place"},
            )

        data = resp.json()
        assert len(data["clusters"]) > 0
        cluster = data["clusters"][0]
        assert "cluster_id" in cluster
        assert "cluster_type" in cluster
        assert "value_count" in cluster
        assert "total_records" in cluster
        assert "priority_score" in cluster
