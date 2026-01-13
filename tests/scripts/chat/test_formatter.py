"""Tests for chat response formatter.

Verifies that CandidateSet results are properly formatted into natural
language responses suitable for conversational interfaces.
"""

import pytest
from scripts.chat.formatter import (
    format_for_chat,
    format_summary,
    format_evidence,
    format_single_candidate,
    generate_followups,
)
from scripts.schemas import CandidateSet, Candidate, Evidence


@pytest.fixture
def sample_evidence():
    """Create sample evidence list for testing."""
    return [
        Evidence(
            field="publisher_norm",
            value="oxford",
            operator="=",
            matched_against="oxford",
            source="db.imprints.publisher_norm (marc:264$b[0])",
            confidence=0.95,
        ),
        Evidence(
            field="date_start",
            value=1550,
            operator="OVERLAPS",
            matched_against="1500-1599",
            source="db.imprints.date_start (marc:264$c[0])",
            confidence=0.99,
        ),
    ]


@pytest.fixture
def sample_candidate(sample_evidence):
    """Create sample candidate for testing."""
    return Candidate(
        record_id="990001234",
        match_rationale="publisher_norm='oxford' AND year_range overlaps 1500-1599",
        evidence=sample_evidence,
    )


@pytest.fixture
def sample_candidate_set(sample_candidate):
    """Create sample CandidateSet with multiple candidates."""
    candidates = [
        sample_candidate,
        Candidate(
            record_id="990005678",
            match_rationale="publisher_norm='oxford'",
            evidence=[
                Evidence(
                    field="publisher_norm",
                    value="oxford",
                    operator="=",
                    matched_against="oxford",
                    source="db.imprints.publisher_norm",
                    confidence=0.95,
                )
            ],
        ),
    ]

    return CandidateSet(
        query_text="books published by Oxford between 1500 and 1599",
        plan_hash="abc123",
        sql="SELECT * FROM records...",
        candidates=candidates,
        total_count=len(candidates),
    )


@pytest.fixture
def empty_candidate_set():
    """Create empty CandidateSet for zero results testing."""
    return CandidateSet(
        query_text="books about nonexistent topic",
        plan_hash="def456",
        sql="SELECT * FROM records...",
        candidates=[],
        total_count=0,
    )


def test_format_evidence_basic(sample_evidence):
    """Test basic evidence formatting."""
    result = format_evidence(sample_evidence)

    assert "publisher_norm matches 'oxford'" in result
    assert "confidence: 95%" in result
    assert "date_start" in result
    assert "marc:264$b[0]" in result


def test_format_evidence_empty():
    """Test formatting empty evidence list."""
    result = format_evidence([])

    assert "No evidence available" in result


def test_format_evidence_no_confidence():
    """Test formatting evidence without confidence scores."""
    evidence = [
        Evidence(
            field="title_value",
            value="Historia",
            operator="CONTAINS",
            matched_against="historia",
            source="db.titles.value",
            confidence=None,
        )
    ]

    result = format_evidence(evidence)

    assert "title_value contains 'historia'" in result
    assert "confidence" not in result


def test_format_single_candidate(sample_candidate):
    """Test formatting single candidate with evidence."""
    result = format_single_candidate(sample_candidate, 1)

    assert "1. Record: 990001234" in result
    assert "Match:" in result
    assert "Evidence:" in result
    assert "publisher_norm" in result


def test_format_for_chat_with_results(sample_candidate_set):
    """Test formatting CandidateSet with results."""
    result = format_for_chat(sample_candidate_set)

    # Check summary
    assert "Found 2 books matching your query" in result
    assert "books published by Oxford between 1500 and 1599" in result

    # Check candidates are included
    assert "990001234" in result
    assert "990005678" in result

    # Check evidence is included
    assert "Evidence:" in result
    assert "publisher_norm" in result


def test_format_for_chat_zero_results(empty_candidate_set):
    """Test formatting with zero results."""
    result = format_for_chat(empty_candidate_set)

    assert "couldn't find any books" in result
    assert "Suggestions:" in result
    assert "Try broadening your search" in result


def test_format_for_chat_max_candidates():
    """Test limiting number of candidates displayed."""
    # Create 15 candidates
    candidates = [
        Candidate(
            record_id=f"99000{i:04d}",
            match_rationale="test match",
            evidence=[],
        )
        for i in range(15)
    ]

    candidate_set = CandidateSet(
        query_text="test query",
        plan_hash="test123",
        sql="SELECT...",
        candidates=candidates,
        total_count=15,
    )

    result = format_for_chat(candidate_set, max_candidates=5)

    # Should show 5 candidates
    assert "Showing details for 5 of 15 results" in result

    # Should indicate more results exist
    assert "and 10 more results" in result


def test_format_for_chat_without_evidence(sample_candidate_set):
    """Test compact formatting without evidence details."""
    result = format_for_chat(sample_candidate_set, include_evidence=False)

    assert "Record IDs:" in result
    assert "990001234" in result
    assert "990005678" in result

    # Evidence should not be included
    assert "Evidence:" not in result
    assert "publisher_norm" not in result


def test_format_summary_zero_results(empty_candidate_set):
    """Test summary formatting with zero results."""
    result = format_summary(empty_candidate_set)

    assert "No books found" in result


def test_format_summary_one_result():
    """Test summary formatting with single result."""
    candidate_set = CandidateSet(
        query_text="test",
        plan_hash="abc",
        sql="SELECT...",
        candidates=[
            Candidate(record_id="990001234", match_rationale="test", evidence=[])
        ],
        total_count=1,
    )

    result = format_summary(candidate_set)

    assert "Found 1 book" in result


def test_format_summary_multiple_results(sample_candidate_set):
    """Test summary formatting with multiple results."""
    result = format_summary(sample_candidate_set)

    assert "Found 2 books" in result


def test_generate_followups_with_results(sample_candidate_set):
    """Test follow-up generation with results."""
    followups = generate_followups(sample_candidate_set, sample_candidate_set.query_text)

    # Should return list of suggestions
    assert isinstance(followups, list)
    assert len(followups) > 0
    assert len(followups) <= 5

    # Should suggest filters that weren't used
    # (sample has publisher and year, should suggest place/subject)
    suggestion_text = " ".join(followups).lower()
    assert "place" in suggestion_text or "subject" in suggestion_text


def test_generate_followups_zero_results(empty_candidate_set):
    """Test follow-up generation with zero results."""
    followups = generate_followups(empty_candidate_set, empty_candidate_set.query_text)

    assert isinstance(followups, list)
    assert len(followups) > 0

    # Should suggest broadening search
    suggestion_text = " ".join(followups).lower()
    assert "broaden" in suggestion_text or "general" in suggestion_text


def test_generate_followups_many_results():
    """Test follow-up generation with many results."""
    # Create 50 candidates
    candidates = [
        Candidate(record_id=f"99000{i:04d}", match_rationale="test", evidence=[])
        for i in range(50)
    ]

    candidate_set = CandidateSet(
        query_text="test",
        plan_hash="abc",
        sql="SELECT...",
        candidates=candidates,
        total_count=50,
    )

    followups = generate_followups(candidate_set, candidate_set.query_text)

    # Should suggest narrowing search
    suggestion_text = " ".join(followups).lower()
    assert "narrow" in suggestion_text or "specific" in suggestion_text


def test_evidence_with_different_operators():
    """Test evidence formatting with various operators."""
    evidence_list = [
        Evidence(
            field="title",
            value="History of Rome",
            operator="CONTAINS",
            matched_against="rome",
            source="db.titles",
            confidence=0.90,
        ),
        Evidence(
            field="year",
            value="1550-1560",
            operator="BETWEEN",
            matched_against="1500-1600",
            source="db.imprints",
            confidence=0.95,
        ),
        Evidence(
            field="exact_field",
            value="value",
            operator="=",
            matched_against="value",
            source="db.table",
            confidence=None,
        ),
    ]

    result = format_evidence(evidence_list)

    assert "contains 'rome'" in result
    assert "matches range" in result
    assert "matches 'value'" in result
    assert "confidence: 90%" in result
    assert "confidence: 95%" in result


def test_format_for_chat_single_result():
    """Test formatting with exactly one result."""
    candidate_set = CandidateSet(
        query_text="specific book query",
        plan_hash="single123",
        sql="SELECT...",
        candidates=[
            Candidate(
                record_id="990001234",
                match_rationale="exact match",
                evidence=[
                    Evidence(
                        field="title",
                        value="Exact Title",
                        operator="=",
                        matched_against="exact title",
                        source="db.titles",
                        confidence=0.99,
                    )
                ],
            )
        ],
        total_count=1,
    )

    result = format_for_chat(candidate_set)

    assert "Found 1 book matching your query" in result
    assert "990001234" in result
    assert "Evidence:" in result
