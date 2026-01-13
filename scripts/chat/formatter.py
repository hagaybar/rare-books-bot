"""Response formatting for conversational chatbot interface.

This module transforms CandidateSet results from M4 query execution into
natural language responses suitable for chat interfaces.

Key functions:
- format_for_chat: Main entry point for formatting responses
- format_evidence: Convert evidence list to readable bullet points
- generate_followups: Context-aware follow-up question suggestions
"""

from typing import List, Optional
from scripts.schemas import CandidateSet, Candidate, Evidence


def format_evidence(evidence_list: List[Evidence]) -> str:
    """Format evidence list as readable bullet points.

    Args:
        evidence_list: List of Evidence objects for a candidate

    Returns:
        Formatted evidence string with bullet points
    """
    if not evidence_list:
        return "  No evidence available"

    lines = []
    for ev in evidence_list:
        # Format the evidence line
        if ev.confidence is not None:
            confidence_pct = int(ev.confidence * 100)
            confidence_str = f" (confidence: {confidence_pct}%)"
        else:
            confidence_str = ""

        # Create human-readable description
        if ev.operator == "=":
            description = f"{ev.field} matches '{ev.matched_against}'"
        elif ev.operator == "LIKE" or ev.operator == "CONTAINS":
            description = f"{ev.field} contains '{ev.matched_against}'"
        elif ev.operator == "BETWEEN" or ev.operator == "OVERLAPS":
            description = f"{ev.field} is {ev.value} (matches range)"
        else:
            description = f"{ev.field} {ev.operator} '{ev.matched_against}'"

        # Format source reference
        source_ref = f"[{ev.source}]" if ev.source else ""

        lines.append(f"  • {description}{confidence_str} {source_ref}")

    return "\n".join(lines)


def format_single_candidate(candidate: Candidate, index: int) -> str:
    """Format a single candidate with evidence.

    Args:
        candidate: Candidate object to format
        index: 1-based index for display

    Returns:
        Formatted candidate string
    """
    lines = []

    # Header with record ID
    lines.append(f"\n{index}. Record: {candidate.record_id}")

    # Match rationale
    if candidate.match_rationale:
        lines.append(f"   Match: {candidate.match_rationale}")

    # Evidence
    if candidate.evidence:
        lines.append("   Evidence:")
        lines.append(format_evidence(candidate.evidence))

    return "\n".join(lines)


def generate_followups(
    candidate_set: CandidateSet,
    query_text: str
) -> List[str]:
    """Generate context-aware follow-up question suggestions.

    Analyzes the query and results to suggest relevant refinements.

    Args:
        candidate_set: Query results
        query_text: Original user query

    Returns:
        List of suggested follow-up queries (3-5 suggestions)
    """
    followups = []

    # If results exist, suggest refinements
    if candidate_set.count > 0:
        # Analyze what filters were used (from evidence)
        has_year_filter = any(
            any(e.field in ["date_start", "date_end"] for e in c.evidence)
            for c in candidate_set.candidates
        )
        has_place_filter = any(
            any(e.field == "place_norm" for e in c.evidence)
            for c in candidate_set.candidates
        )
        has_publisher_filter = any(
            any(e.field == "publisher_norm" for e in c.evidence)
            for c in candidate_set.candidates
        )

        # Suggest adding filters that weren't used
        if not has_year_filter:
            followups.append("Refine by adding a date range (e.g., 'between 1500 and 1600')")

        if not has_place_filter:
            followups.append("Filter by place of publication (e.g., 'printed in Paris')")

        if not has_publisher_filter:
            followups.append("Filter by publisher (e.g., 'published by Oxford')")

        # Suggest narrowing if many results
        if candidate_set.count > 20:
            followups.append("Narrow your search with more specific criteria")

        # Suggest subject search if not already used
        has_subject_filter = any(
            any(e.field == "subject_value" for e in c.evidence)
            for c in candidate_set.candidates
        )
        if not has_subject_filter:
            followups.append("Search by subject (e.g., 'books about History')")

    else:
        # Zero results - suggest broadening or alternatives
        followups = [
            "Try broadening your search with more general terms",
            "Check the spelling of names and places",
            "Remove some filters to see more results",
            "Try searching by subject instead of publisher/place",
            "Use different date ranges or remove date constraints"
        ]

    # Return at most 5 suggestions
    return followups[:5]


def format_for_chat(
    candidate_set: CandidateSet,
    max_candidates: int = 10,
    include_evidence: bool = True
) -> str:
    """Format CandidateSet into natural language response for chat.

    This is the main entry point for response formatting.

    Args:
        candidate_set: Query results from M4 pipeline
        max_candidates: Maximum number of candidates to include in detail
        include_evidence: Whether to include evidence details

    Returns:
        Natural language response string
    """
    count = candidate_set.count

    # Zero results case
    if count == 0:
        return (
            "I couldn't find any books matching your query.\n\n"
            "Suggestions:\n"
            "• Try broadening your search with more general terms\n"
            "• Check spelling of names and places\n"
            "• Use different date ranges or remove constraints\n"
            "• Search by subject instead (e.g., 'books about History')"
        )

    # Build response
    lines = []

    # Summary line
    if count == 1:
        lines.append("Found 1 book matching your query.")
    else:
        lines.append(f"Found {count} books matching your query.")

    # Add query text reminder
    lines.append(f'Query: "{candidate_set.query_text}"')
    lines.append("")

    # Show detailed results (up to max_candidates)
    display_count = min(count, max_candidates)

    if include_evidence:
        lines.append(f"Showing details for {display_count} of {count} results:")

        for i, candidate in enumerate(candidate_set.candidates[:max_candidates], start=1):
            lines.append(format_single_candidate(candidate, i))

        # Note if there are more results
        if count > max_candidates:
            lines.append(f"\n... and {count - max_candidates} more results.")
            lines.append("Refine your query to see more specific results.")
    else:
        # Compact format: just list record IDs
        lines.append("Record IDs:")
        for i, candidate in enumerate(candidate_set.candidates[:max_candidates], start=1):
            lines.append(f"  {i}. {candidate.record_id}")

        if count > max_candidates:
            lines.append(f"  ... and {count - max_candidates} more")

    return "\n".join(lines)


def format_summary(candidate_set: CandidateSet) -> str:
    """Generate a brief summary without full evidence details.

    Useful for quick status updates or when user wants just the count.

    Args:
        candidate_set: Query results

    Returns:
        One-line summary string
    """
    count = candidate_set.count

    if count == 0:
        return "No books found matching your query."
    elif count == 1:
        return "Found 1 book matching your query."
    else:
        return f"Found {count} books matching your query."
