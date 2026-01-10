"""Tests for CandidateSet Pydantic models.

Validates evidence structure, candidate format, and result set schema.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from scripts.schemas import Evidence, Candidate, CandidateSet


class TestEvidence:
    """Tests for Evidence model validation."""

    def test_valid_evidence(self):
        """Valid evidence should validate."""
        e = Evidence(
            field="publisher_norm",
            value="oxford university press",
            operator="=",
            matched_against="oxford",
            source="db.imprints.publisher_norm"
        )
        assert e.field == "publisher_norm"
        assert e.value == "oxford university press"
        assert e.operator == "="
        assert e.matched_against == "oxford"
        assert e.source == "db.imprints.publisher_norm"

    def test_evidence_with_confidence(self):
        """Evidence with confidence should validate."""
        e = Evidence(
            field="publisher_norm",
            value="oxford",
            operator="=",
            matched_against="oxford",
            source="db.imprints.publisher_norm (marc:260$b)",
            confidence=0.95
        )
        assert e.confidence == 0.95

    def test_evidence_with_range_values(self):
        """Evidence with integer values should validate."""
        e = Evidence(
            field="date_range",
            value="1510-1510",
            operator="OVERLAPS",
            matched_against="1500-1599",
            source="db.imprints.date_start/date_end"
        )
        assert e.value == "1510-1510"
        assert e.matched_against == "1500-1599"

    def test_evidence_missing_field_fails(self):
        """Evidence missing required field should fail."""
        with pytest.raises(ValidationError):
            Evidence(
                value="test",
                operator="=",
                matched_against="test",
                source="db.test"
            )

    def test_evidence_with_invalid_confidence_fails(self):
        """Evidence with out-of-range confidence should fail."""
        with pytest.raises(ValidationError):
            Evidence(
                field="test",
                value="test",
                operator="=",
                matched_against="test",
                source="db.test",
                confidence=1.5
            )


class TestCandidate:
    """Tests for Candidate model validation."""

    def test_valid_candidate_minimal(self):
        """Minimal valid candidate should validate."""
        c = Candidate(
            record_id="990011964120204146",
            match_rationale="publisher_norm='oxford'"
        )
        assert c.record_id == "990011964120204146"
        assert c.match_rationale == "publisher_norm='oxford'"
        assert c.evidence == []

    def test_valid_candidate_with_evidence(self):
        """Candidate with evidence should validate."""
        c = Candidate(
            record_id="990011964120204146",
            match_rationale="publisher_norm='oxford' AND year_range=1510-1510 overlaps 1500-1599",
            evidence=[
                Evidence(
                    field="publisher_norm",
                    value="oxford",
                    operator="=",
                    matched_against="oxford",
                    source="db.imprints.publisher_norm"
                ),
                Evidence(
                    field="date_range",
                    value="1510-1510",
                    operator="OVERLAPS",
                    matched_against="1500-1599",
                    source="db.imprints.date_start/date_end"
                )
            ]
        )
        assert len(c.evidence) == 2

    def test_candidate_missing_record_id_fails(self):
        """Candidate missing record_id should fail."""
        with pytest.raises(ValidationError):
            Candidate(match_rationale="test")

    def test_candidate_missing_rationale_fails(self):
        """Candidate missing match_rationale should fail."""
        with pytest.raises(ValidationError):
            Candidate(record_id="990011964120204146")


class TestCandidateSet:
    """Tests for CandidateSet model validation."""

    def test_minimal_valid_candidate_set(self):
        """Minimal valid candidate set should validate."""
        cs = CandidateSet(
            query_text="test query",
            plan_hash="abc123",
            sql="SELECT * FROM records"
        )
        assert cs.query_text == "test query"
        assert cs.plan_hash == "abc123"
        assert cs.sql == "SELECT * FROM records"
        assert cs.candidates == []
        assert cs.total_count == 0
        assert cs.count == 0  # Property
        # generated_at should be set automatically
        assert isinstance(cs.generated_at, str)

    def test_candidate_set_with_candidates(self):
        """Candidate set with candidates should validate."""
        cs = CandidateSet(
            query_text="books by oxford",
            plan_hash="abc123",
            sql="SELECT * FROM records WHERE publisher='oxford'",
            candidates=[
                Candidate(
                    record_id="990011964120204146",
                    match_rationale="publisher_norm='oxford'",
                    evidence=[
                        Evidence(
                            field="publisher_norm",
                            value="oxford",
                            operator="=",
                            matched_against="oxford",
                            source="db.imprints.publisher_norm"
                        )
                    ]
                )
            ],
            total_count=1
        )
        assert len(cs.candidates) == 1
        assert cs.total_count == 1
        assert cs.count == 1

    def test_candidate_set_count_property(self):
        """Count property should return number of candidates."""
        cs = CandidateSet(
            query_text="test",
            plan_hash="abc",
            sql="SELECT * FROM records",
            candidates=[
                Candidate(record_id="1", match_rationale="test1"),
                Candidate(record_id="2", match_rationale="test2"),
            ],
            total_count=2
        )
        assert cs.count == 2
        assert cs.count == len(cs.candidates)

    def test_candidate_set_json_serialization(self):
        """Candidate set should serialize to JSON."""
        cs = CandidateSet(
            query_text="test query",
            plan_hash="abc123",
            sql="SELECT * FROM records",
            candidates=[
                Candidate(
                    record_id="990011964120204146",
                    match_rationale="test",
                    evidence=[
                        Evidence(
                            field="publisher_norm",
                            value="oxford",
                            operator="=",
                            matched_against="oxford",
                            source="db.imprints.publisher_norm"
                        )
                    ]
                )
            ],
            total_count=1
        )
        json_data = cs.model_dump()
        assert json_data["query_text"] == "test query"
        assert json_data["plan_hash"] == "abc123"
        assert len(json_data["candidates"]) == 1
        assert json_data["total_count"] == 1

    def test_candidate_set_from_json(self):
        """Candidate set should deserialize from JSON."""
        json_data = {
            "query_text": "test query",
            "plan_hash": "abc123",
            "sql": "SELECT * FROM records",
            "generated_at": "2025-01-09T20:00:00",
            "candidates": [
                {
                    "record_id": "990011964120204146",
                    "match_rationale": "test",
                    "evidence": []
                }
            ],
            "total_count": 1
        }
        cs = CandidateSet(**json_data)
        assert cs.query_text == "test query"
        assert len(cs.candidates) == 1
        assert cs.candidates[0].record_id == "990011964120204146"

    def test_candidate_set_missing_query_text_fails(self):
        """Candidate set missing query_text should fail."""
        with pytest.raises(ValidationError):
            CandidateSet(
                plan_hash="abc123",
                sql="SELECT * FROM records"
            )

    def test_candidate_set_missing_plan_hash_fails(self):
        """Candidate set missing plan_hash should fail."""
        with pytest.raises(ValidationError):
            CandidateSet(
                query_text="test",
                sql="SELECT * FROM records"
            )

    def test_candidate_set_missing_sql_fails(self):
        """Candidate set missing sql should fail."""
        with pytest.raises(ValidationError):
            CandidateSet(
                query_text="test",
                plan_hash="abc123"
            )
