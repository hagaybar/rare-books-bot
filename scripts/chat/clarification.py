"""Clarification flow for ambiguous queries.

This module detects when user queries are ambiguous or too vague and generates
helpful clarification messages to guide users toward more specific queries.

Key functions:
- detect_ambiguous_query: Check if QueryPlan needs clarification
- generate_clarification_message: Create helpful clarification prompt
- suggest_refinements: Provide specific refinement suggestions
"""

from typing import Optional, List, Tuple
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp


# Confidence threshold below which we consider a filter ambiguous
LOW_CONFIDENCE_THRESHOLD = 0.7

# Date range threshold (in years) beyond which we consider it too broad
BROAD_DATE_RANGE_YEARS = 200


def has_empty_filters(plan: QueryPlan) -> bool:
    """Check if query plan has no filters.

    Args:
        plan: QueryPlan to check

    Returns:
        True if filters list is empty
    """
    return len(plan.filters) == 0


def has_low_confidence_filters(plan: QueryPlan) -> Tuple[bool, List[Filter]]:
    """Check if any filters have low confidence scores.

    Args:
        plan: QueryPlan to check

    Returns:
        Tuple of (has_low_confidence, list of low confidence filters)
    """
    low_conf_filters = [
        f for f in plan.filters
        if f.confidence is not None and f.confidence < LOW_CONFIDENCE_THRESHOLD
    ]
    return len(low_conf_filters) > 0, low_conf_filters


def has_overly_broad_date_range(plan: QueryPlan) -> Tuple[bool, Optional[Filter]]:
    """Check if date range filter is too broad (>200 years).

    Args:
        plan: QueryPlan to check

    Returns:
        Tuple of (is_too_broad, the broad filter if found)
    """
    for f in plan.filters:
        if f.field == FilterField.YEAR and f.op == FilterOp.RANGE:
            if f.start is not None and f.end is not None:
                range_years = f.end - f.start
                if range_years > BROAD_DATE_RANGE_YEARS:
                    return True, f
    return False, None


def has_only_vague_filters(plan: QueryPlan) -> bool:
    """Check if query has only very vague filters (single-word subjects/titles).

    Args:
        plan: QueryPlan to check

    Returns:
        True if all filters are vague (single words, very short)
    """
    if len(plan.filters) == 0:
        return False

    # Check if all filters are short subject/title queries
    for f in plan.filters:
        if f.field in [FilterField.SUBJECT, FilterField.TITLE]:
            if f.value and isinstance(f.value, str):
                # If value has more than one word, it's not vague
                if len(f.value.split()) > 1:
                    return False
            else:
                # Non-subject/title filter exists, not vague
                return False
        else:
            # Has non-subject/title filter, not vague
            return False

    # All filters are single-word subject/title queries
    return True


def detect_ambiguous_query(
    plan: QueryPlan,
    result_count: int = 0
) -> Tuple[bool, Optional[str]]:
    """Detect if query needs clarification.

    Args:
        plan: QueryPlan to check
        result_count: Number of results returned (0 may indicate ambiguity)

    Returns:
        Tuple of (needs_clarification, reason_code)
        reason_code can be: "empty_filters", "low_confidence", "broad_date",
                           "vague", "zero_results", or None
    """
    # Check for empty filters
    if has_empty_filters(plan):
        return True, "empty_filters"

    # Check for low confidence filters
    has_low_conf, _ = has_low_confidence_filters(plan)
    if has_low_conf:
        return True, "low_confidence"

    # Check for overly broad date ranges
    is_broad, _ = has_overly_broad_date_range(plan)
    if is_broad:
        return True, "broad_date"

    # Check for vague single-word queries
    if has_only_vague_filters(plan):
        return True, "vague"

    # Check if zero results (might indicate misunderstanding)
    if result_count == 0:
        return True, "zero_results"

    return False, None


def generate_clarification_message(
    plan: QueryPlan,
    reason_code: Optional[str],
    result_count: int = 0
) -> str:
    """Generate helpful clarification message for user.

    Args:
        plan: QueryPlan that needs clarification
        reason_code: Reason why clarification is needed
        result_count: Number of results (if relevant)

    Returns:
        Clarification message string
    """
    if reason_code == "empty_filters":
        return (
            "I need more details to search effectively. Could you specify:\n"
            "• What topic or subject are you interested in?\n"
            "• A specific publisher, author, or printer?\n"
            "• A time period or date range?\n"
            "• A place of publication?"
        )

    elif reason_code == "low_confidence":
        _, low_conf_filters = has_low_confidence_filters(plan)

        # Identify which fields have low confidence
        field_names = [f.field.value for f in low_conf_filters]

        return (
            f"I'm not certain I understood your query correctly, particularly regarding: "
            f"{', '.join(field_names)}. Could you rephrase or provide more specific details?\n\n"
            f"For example:\n"
            f"• Use full names (e.g., 'Oxford University Press' instead of 'Oxford')\n"
            f"• Specify complete place names (e.g., 'Paris, France' instead of 'Paris')\n"
            f"• Use standard date formats (e.g., '1500-1600' or 'between 1500 and 1600')"
        )

    elif reason_code == "broad_date":
        is_broad, broad_filter = has_overly_broad_date_range(plan)
        if is_broad and broad_filter:
            years = broad_filter.end - broad_filter.start
            return (
                f"Your date range ({broad_filter.start}-{broad_filter.end}, {years} years) "
                f"is very broad and may return many results. Consider:\n"
                f"• Narrowing to a specific century (e.g., '16th century' or '1500-1599')\n"
                f"• Focusing on a particular decade or year\n"
                f"• Adding other filters like publisher or place to refine results"
            )

    elif reason_code == "vague":
        return (
            "Your query is quite general. To get more relevant results, try:\n"
            "• Adding more context (e.g., 'books about military history in Italy')\n"
            "• Specifying a time period or publisher\n"
            "• Using more specific terms or multiple keywords"
        )

    elif reason_code == "zero_results":
        return (
            "No books found matching your query. This might mean:\n"
            "• The terms are too specific or spelled differently in the catalog\n"
            "• The combination of filters is too restrictive\n\n"
            "Try:\n"
            "• Broadening your search (fewer filters, wider date ranges)\n"
            "• Checking spelling of names and places\n"
            "• Using more general terms"
        )

    # Default generic clarification
    return (
        "Could you provide more details to help me find what you're looking for? "
        "Consider adding:\n"
        "• A specific subject or topic\n"
        "• Publisher or author information\n"
        "• Time period or date range\n"
        "• Place of publication"
    )


def suggest_refinements(plan: QueryPlan) -> List[str]:
    """Generate specific refinement suggestions based on current query.

    Args:
        plan: QueryPlan to analyze

    Returns:
        List of refinement suggestion strings
    """
    suggestions = []

    # Check what filters are missing
    filter_fields = {f.field for f in plan.filters}

    if FilterField.YEAR not in filter_fields:
        suggestions.append("Add a date range (e.g., 'between 1500 and 1600')")

    if FilterField.PUBLISHER not in filter_fields:
        suggestions.append("Specify a publisher (e.g., 'published by Oxford')")

    if FilterField.IMPRINT_PLACE not in filter_fields:
        suggestions.append("Add a place of publication (e.g., 'printed in Paris')")

    if FilterField.SUBJECT not in filter_fields:
        suggestions.append("Include a subject or topic (e.g., 'about History')")

    # If we have date but it's broad, suggest narrowing
    is_broad, _ = has_overly_broad_date_range(plan)
    if is_broad:
        suggestions.insert(0, "Narrow the date range to a specific century or decade")

    # If we have vague terms, suggest specificity
    if has_only_vague_filters(plan):
        suggestions.insert(0, "Use more specific or multiple keywords")

    # Limit to 5 suggestions
    return suggestions[:5]


def is_execution_blocking(reason_code: Optional[str]) -> bool:
    """Check if the ambiguity reason should block execution.

    Only "empty_filters" blocks execution. Other reasons (low_confidence,
    broad_date, vague) become post-execution suggestions instead of blockers.

    This implements the "Execute First" philosophy: if we have any extractable
    filters, execute the query and show results. Users get results faster,
    and refinements become helpful suggestions rather than blockers.

    Args:
        reason_code: The ambiguity reason code

    Returns:
        True only for "empty_filters"
    """
    return reason_code == "empty_filters"


def should_ask_for_clarification(
    plan: QueryPlan,
    result_count: int,
    enable_zero_result_clarification: bool = True
) -> bool:
    """Determine if we should ask user for clarification.

    This is the main entry point for clarification logic in the API layer.
    Post-execution, this only suggests clarification for zero results
    (if enabled) - other ambiguities are handled as suggestions.

    Args:
        plan: QueryPlan from query compilation
        result_count: Number of results from query execution
        enable_zero_result_clarification: Whether to ask for clarification on zero results

    Returns:
        True if clarification is recommended (only for zero results post-execution)
    """
    # Post-execution: only zero results triggers clarification
    if result_count == 0 and enable_zero_result_clarification:
        return True

    return False


def get_refinement_suggestions_for_query(plan: QueryPlan, result_count: int) -> Optional[str]:
    """Generate optional refinement suggestions for the response.

    Called after successful query execution. Returns suggestions to help users
    refine their search, but does NOT block results.

    Args:
        plan: QueryPlan that was executed
        result_count: Number of results returned

    Returns:
        Optional suggestion string, or None if no suggestions needed
    """
    # Don't add suggestions for zero results (handled separately)
    if result_count == 0:
        return None

    # Check for conditions that warrant suggestions
    _, reason = detect_ambiguous_query(plan, result_count)

    # No ambiguity detected - no suggestions needed
    if reason is None:
        return None

    # Generate helpful suggestions based on reason
    if reason == "broad_date":
        is_broad, broad_filter = has_overly_broad_date_range(plan)
        if is_broad and broad_filter:
            years = broad_filter.end - broad_filter.start
            return (
                f"💡 **Tip:** Your date range covers {years} years. "
                f"You might get more focused results by narrowing to a specific century."
            )

    elif reason == "vague":
        return (
            "💡 **Tip:** You could refine these results by adding more specific terms, "
            "a date range, or a place of publication."
        )

    elif reason == "low_confidence":
        return (
            "💡 **Tip:** Some search terms were interpreted with lower confidence. "
            "If results don't match what you expected, try rephrasing with more specific terms."
        )

    return None
