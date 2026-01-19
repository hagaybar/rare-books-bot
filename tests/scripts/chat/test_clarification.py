"""Tests for clarification flow module.

Verifies ambiguity detection and clarification message generation for
queries that are too vague, have low confidence, or need refinement.
"""

import pytest
from scripts.chat.clarification import (
    detect_ambiguous_query,
    generate_clarification_message,
    suggest_refinements,
    should_ask_for_clarification,
    has_empty_filters,
    has_low_confidence_filters,
    has_overly_broad_date_range,
    has_only_vague_filters,
    is_execution_blocking,
    get_refinement_suggestions_for_query,
)
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp


@pytest.fixture
def empty_plan():
    """QueryPlan with no filters."""
    return QueryPlan(query_text="books", filters=[])


@pytest.fixture
def low_confidence_plan():
    """QueryPlan with low confidence filters."""
    return QueryPlan(
        query_text="books by oxford",
        filters=[
            Filter(
                field=FilterField.PUBLISHER,
                op=FilterOp.EQUALS,
                value="oxford",
                confidence=0.5,  # Low confidence
            )
        ],
    )


@pytest.fixture
def broad_date_plan():
    """QueryPlan with overly broad date range."""
    return QueryPlan(
        query_text="books from 1400 to 1800",
        filters=[
            Filter(
                field=FilterField.YEAR,
                op=FilterOp.RANGE,
                start=1400,
                end=1800,  # 400 years - very broad
            )
        ],
    )


@pytest.fixture
def vague_plan():
    """QueryPlan with only vague single-word filters."""
    return QueryPlan(
        query_text="history",
        filters=[
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="history")
        ],
    )


@pytest.fixture
def specific_plan():
    """QueryPlan with specific, high-confidence filters."""
    return QueryPlan(
        query_text="books published by Oxford between 1500 and 1599",
        filters=[
            Filter(
                field=FilterField.PUBLISHER,
                op=FilterOp.EQUALS,
                value="oxford",
                confidence=0.95,
            ),
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599),
        ],
    )


def test_has_empty_filters(empty_plan, specific_plan):
    """Test detection of empty filter lists."""
    assert has_empty_filters(empty_plan) is True
    assert has_empty_filters(specific_plan) is False


def test_has_low_confidence_filters(low_confidence_plan, specific_plan):
    """Test detection of low confidence filters."""
    has_low, filters = has_low_confidence_filters(low_confidence_plan)
    assert has_low is True
    assert len(filters) == 1
    assert filters[0].confidence == 0.5

    has_low, filters = has_low_confidence_filters(specific_plan)
    assert has_low is False
    assert len(filters) == 0


def test_has_overly_broad_date_range(broad_date_plan, specific_plan):
    """Test detection of overly broad date ranges."""
    is_broad, filter_obj = has_overly_broad_date_range(broad_date_plan)
    assert is_broad is True
    assert filter_obj is not None
    assert filter_obj.end - filter_obj.start == 400

    is_broad, filter_obj = has_overly_broad_date_range(specific_plan)
    assert is_broad is False
    assert filter_obj is None


def test_has_only_vague_filters(vague_plan, specific_plan):
    """Test detection of vague single-word queries."""
    assert has_only_vague_filters(vague_plan) is True
    assert has_only_vague_filters(specific_plan) is False


def test_detect_ambiguous_query_empty_filters(empty_plan):
    """Test ambiguity detection for empty filters."""
    needs_clarification, reason = detect_ambiguous_query(empty_plan)

    assert needs_clarification is True
    assert reason == "empty_filters"


def test_detect_ambiguous_query_low_confidence(low_confidence_plan):
    """Test ambiguity detection for low confidence filters."""
    needs_clarification, reason = detect_ambiguous_query(low_confidence_plan)

    assert needs_clarification is True
    assert reason == "low_confidence"


def test_detect_ambiguous_query_broad_date(broad_date_plan):
    """Test ambiguity detection for broad date ranges."""
    needs_clarification, reason = detect_ambiguous_query(broad_date_plan)

    assert needs_clarification is True
    assert reason == "broad_date"


def test_detect_ambiguous_query_vague(vague_plan):
    """Test ambiguity detection for vague queries."""
    needs_clarification, reason = detect_ambiguous_query(vague_plan)

    assert needs_clarification is True
    assert reason == "vague"


def test_detect_ambiguous_query_zero_results(specific_plan):
    """Test ambiguity detection for zero results."""
    needs_clarification, reason = detect_ambiguous_query(specific_plan, result_count=0)

    assert needs_clarification is True
    assert reason == "zero_results"


def test_detect_ambiguous_query_specific(specific_plan):
    """Test that specific queries are not flagged as ambiguous."""
    needs_clarification, reason = detect_ambiguous_query(
        specific_plan, result_count=10
    )

    assert needs_clarification is False
    assert reason is None


def test_generate_clarification_message_empty_filters(empty_plan):
    """Test clarification message for empty filters."""
    message = generate_clarification_message(empty_plan, "empty_filters")

    assert "more details" in message.lower()
    assert "topic" in message.lower() or "subject" in message.lower()
    assert "publisher" in message.lower()


def test_generate_clarification_message_low_confidence(low_confidence_plan):
    """Test clarification message for low confidence."""
    message = generate_clarification_message(low_confidence_plan, "low_confidence")

    assert "not certain" in message.lower()
    assert "publisher" in message.lower()
    assert "rephrase" in message.lower() or "specific" in message.lower()


def test_generate_clarification_message_broad_date(broad_date_plan):
    """Test clarification message for broad date range."""
    message = generate_clarification_message(broad_date_plan, "broad_date")

    assert "1400-1800" in message or "1400" in message
    assert "broad" in message.lower()
    assert "century" in message.lower()


def test_generate_clarification_message_vague(vague_plan):
    """Test clarification message for vague query."""
    message = generate_clarification_message(vague_plan, "vague")

    assert "general" in message.lower() or "vague" in message.lower()
    assert "context" in message.lower() or "specific" in message.lower()


def test_generate_clarification_message_zero_results(specific_plan):
    """Test clarification message for zero results."""
    message = generate_clarification_message(specific_plan, "zero_results", 0)

    assert "no books found" in message.lower()
    assert "broaden" in message.lower() or "fewer filters" in message.lower()


def test_generate_clarification_message_default():
    """Test default clarification message."""
    plan = QueryPlan(query_text="test", filters=[])
    message = generate_clarification_message(plan, None)

    assert "details" in message.lower()
    assert "subject" in message.lower() or "topic" in message.lower()


def test_suggest_refinements_missing_filters(empty_plan):
    """Test refinement suggestions for plan with no filters."""
    suggestions = suggest_refinements(empty_plan)

    assert len(suggestions) > 0
    assert any("date" in s.lower() for s in suggestions)
    assert any("publisher" in s.lower() for s in suggestions)
    assert any("place" in s.lower() for s in suggestions)


def test_suggest_refinements_partial_filters():
    """Test refinement suggestions for plan with some filters."""
    plan = QueryPlan(
        query_text="books by oxford",
        filters=[
            Filter(field=FilterField.PUBLISHER, op=FilterOp.EQUALS, value="oxford")
        ],
    )

    suggestions = suggest_refinements(plan)

    # Should suggest date, place, subject (not publisher since it's present)
    assert any("date" in s.lower() for s in suggestions)
    assert any("place" in s.lower() for s in suggestions)
    assert not any("publisher" in s.lower() for s in suggestions)


def test_suggest_refinements_broad_date(broad_date_plan):
    """Test refinement suggestions for broad date range."""
    suggestions = suggest_refinements(broad_date_plan)

    # Should prioritize narrowing date range
    assert len(suggestions) > 0
    assert "narrow" in suggestions[0].lower() and "date" in suggestions[0].lower()


def test_suggest_refinements_vague(vague_plan):
    """Test refinement suggestions for vague query."""
    suggestions = suggest_refinements(vague_plan)

    # Should prioritize specificity
    assert len(suggestions) > 0
    assert "specific" in suggestions[0].lower() or "keywords" in suggestions[0].lower()


def test_suggest_refinements_complete_plan(specific_plan):
    """Test refinement suggestions for complete plan."""
    suggestions = suggest_refinements(specific_plan)

    # Should suggest missing filters (place, subject)
    assert len(suggestions) > 0
    # Should not suggest what's already there (publisher, year)
    assert not any("publisher" in s.lower() for s in suggestions)


def test_should_ask_for_clarification_empty_filters(empty_plan):
    """Test should_ask_for_clarification with empty filters."""
    assert should_ask_for_clarification(empty_plan, result_count=0) is True


def test_should_ask_for_clarification_low_confidence(low_confidence_plan):
    """Test should_ask_for_clarification with low confidence.

    With the "Execute First" philosophy, low confidence is NOT a reason to ask
    for clarification post-execution. If results were found, show them to the user
    and provide refinement suggestions instead of blocking.
    """
    # Low confidence with results does NOT trigger clarification
    # (results are shown with optional refinement tips instead)
    assert should_ask_for_clarification(low_confidence_plan, result_count=10) is False


def test_should_ask_for_clarification_zero_results_enabled(specific_plan):
    """Test should_ask_for_clarification with zero results (enabled)."""
    assert (
        should_ask_for_clarification(
            specific_plan, result_count=0, enable_zero_result_clarification=True
        )
        is True
    )


def test_should_ask_for_clarification_zero_results_disabled(specific_plan):
    """Test should_ask_for_clarification with zero results (disabled)."""
    assert (
        should_ask_for_clarification(
            specific_plan, result_count=0, enable_zero_result_clarification=False
        )
        is False
    )


def test_should_ask_for_clarification_specific_with_results(specific_plan):
    """Test should_ask_for_clarification with good plan and results."""
    assert should_ask_for_clarification(specific_plan, result_count=10) is False


def test_multi_word_subject_not_vague():
    """Test that multi-word subject queries are not considered vague."""
    plan = QueryPlan(
        query_text="military history",
        filters=[
            Filter(
                field=FilterField.SUBJECT,
                op=FilterOp.CONTAINS,
                value="military history",
            )
        ],
    )

    assert has_only_vague_filters(plan) is False
    needs_clarification, reason = detect_ambiguous_query(plan, result_count=10)
    assert needs_clarification is False


def test_reasonable_date_range_not_broad():
    """Test that reasonable date ranges (<=200 years) are not flagged."""
    plan = QueryPlan(
        query_text="books from 16th century",
        filters=[
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1500, end=1599)
        ],
    )

    is_broad, _ = has_overly_broad_date_range(plan)
    assert is_broad is False


def test_high_confidence_not_flagged():
    """Test that high confidence filters are not flagged."""
    plan = QueryPlan(
        query_text="books by oxford",
        filters=[
            Filter(
                field=FilterField.PUBLISHER,
                op=FilterOp.EQUALS,
                value="oxford",
                confidence=0.95,  # High confidence
            )
        ],
    )

    has_low, _ = has_low_confidence_filters(plan)
    assert has_low is False


# =============================================================================
# Tests for "Execute First" Philosophy Functions
# =============================================================================


def test_is_execution_blocking_empty_filters():
    """Test that only empty_filters is execution-blocking."""
    assert is_execution_blocking("empty_filters") is True


def test_is_execution_blocking_other_reasons():
    """Test that other reasons are NOT execution-blocking."""
    # Low confidence should not block execution
    assert is_execution_blocking("low_confidence") is False
    # Broad date should not block execution
    assert is_execution_blocking("broad_date") is False
    # Vague query should not block execution
    assert is_execution_blocking("vague") is False
    # Zero results is handled separately post-execution
    assert is_execution_blocking("zero_results") is False
    # None means no ambiguity
    assert is_execution_blocking(None) is False


def test_get_refinement_suggestions_zero_results(specific_plan):
    """Test that zero results returns None (handled separately)."""
    suggestion = get_refinement_suggestions_for_query(specific_plan, result_count=0)
    assert suggestion is None


def test_get_refinement_suggestions_good_query(specific_plan):
    """Test that good queries with results return None (no suggestions needed)."""
    suggestion = get_refinement_suggestions_for_query(specific_plan, result_count=10)
    assert suggestion is None


def test_get_refinement_suggestions_broad_date():
    """Test that broad date range returns a helpful tip."""
    plan = QueryPlan(
        query_text="old books",
        filters=[
            Filter(field=FilterField.YEAR, op=FilterOp.RANGE, start=1400, end=1800)
        ],
    )
    suggestion = get_refinement_suggestions_for_query(plan, result_count=100)
    assert suggestion is not None
    assert "400 years" in suggestion  # Should mention the range size
    assert "Tip" in suggestion


def test_get_refinement_suggestions_vague():
    """Test that vague single-word queries return a helpful tip."""
    plan = QueryPlan(
        query_text="history",
        filters=[
            Filter(field=FilterField.SUBJECT, op=FilterOp.CONTAINS, value="history")
        ],
    )
    suggestion = get_refinement_suggestions_for_query(plan, result_count=500)
    assert suggestion is not None
    assert "refine" in suggestion.lower() or "tip" in suggestion.lower()


def test_get_refinement_suggestions_low_confidence(low_confidence_plan):
    """Test that low confidence queries return a helpful tip."""
    suggestion = get_refinement_suggestions_for_query(low_confidence_plan, result_count=10)
    assert suggestion is not None
    assert "confidence" in suggestion.lower() or "tip" in suggestion.lower()
