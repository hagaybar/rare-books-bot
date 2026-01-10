"""Query compiler - Natural Language → QueryPlan.

Uses heuristic regex patterns for common query types (M4).
LLM-based compilation can be added in M5 with --llm flag.
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime

from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.db_adapter import normalize_filter_value


# Regex patterns for heuristic parsing
PATTERNS = {
    # Publisher patterns (ordered by specificity)
    "publisher": [
        r"(?:published|printed)\s+by\s+([\w\[\]]+(?:\s+[\w\[\]]+)*?)(?:\s+(?:in|between|from|printed|published)|\s*$)",
        r"by\s+([\w\[\]]+(?:\s+[\w\[\]]+)*?)(?:\s+(?:in|between|from|printed|published)|\s*$)",
    ],
    # Year range patterns
    "year_range": [
        r"between\s+(\d{4})\s+and\s+(\d{4})",
        r"from\s+(\d{4})\s+to\s+(\d{4})",
        r"(\d{4})-(\d{4})",
        r"(?:in|from)\s+the\s+(\d{2})(?:th|st|nd|rd)\s+century",  # "in the 16th century"
    ],
    # Place patterns (ordered by specificity)
    "place": [
        r"(?:printed|published)\s+in\s+([\w\[\]]+(?:\s+[\w\[\]]+)*?)(?:\s+(?:between|from|by)|\s*$)",
        r"from\s+([\w\[\]]+(?:\s+[\w\[\]]+)*?)(?:\s+(?:between|from)|\s*$)",
    ],
    # Language patterns (expandable)
    "language": [
        r"in\s+(Latin|Hebrew|English|French|German|Italian|Spanish|Greek|Arabic)",
        r"(Latin|Hebrew|English|French|German|Italian|Spanish|Greek|Arabic)\s+(?:books|texts)",
    ],
}


def parse_publisher(query_text: str) -> Optional[str]:
    """Extract publisher name from query.

    Args:
        query_text: Natural language query

    Returns:
        Publisher name or None
    """
    for pattern in PATTERNS["publisher"]:
        match = re.search(pattern, query_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_year_range(query_text: str) -> Optional[Tuple[int, int]]:
    """Extract year range from query.

    Args:
        query_text: Natural language query

    Returns:
        Tuple of (start_year, end_year) or None
    """
    # Try explicit range patterns first
    for pattern in PATTERNS["year_range"][:3]:  # First 3 are explicit ranges
        match = re.search(pattern, query_text, re.IGNORECASE)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            return (start, end)

    # Try century pattern (e.g., "16th century")
    century_pattern = PATTERNS["year_range"][3]
    match = re.search(century_pattern, query_text, re.IGNORECASE)
    if match:
        century = int(match.group(1))
        start = (century - 1) * 100 + 1
        end = century * 100
        return (start, end)

    return None


def parse_place(query_text: str) -> Optional[str]:
    """Extract place name from query.

    Args:
        query_text: Natural language query

    Returns:
        Place name or None
    """
    for pattern in PATTERNS["place"]:
        match = re.search(pattern, query_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_language(query_text: str) -> Optional[str]:
    """Extract language from query.

    Args:
        query_text: Natural language query

    Returns:
        Language name (full name, not code) or None
    """
    for pattern in PATTERNS["language"]:
        match = re.search(pattern, query_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def language_name_to_code(language_name: str) -> str:
    """Convert language name to ISO 639-2 code.

    Args:
        language_name: Full language name (e.g., "Latin")

    Returns:
        ISO 639-2 code (e.g., "lat")
    """
    mapping = {
        "latin": "lat",
        "hebrew": "heb",
        "english": "eng",
        "french": "fre",
        "german": "ger",
        "italian": "ita",
        "spanish": "spa",
        "greek": "gre",
        "arabic": "ara",
    }
    return mapping.get(language_name.lower(), language_name.lower())


def compile_query(
    query_text: str,
    limit: Optional[int] = None
) -> QueryPlan:
    """Compile natural language query to QueryPlan using heuristics.

    Args:
        query_text: Natural language query
        limit: Optional result limit

    Returns:
        Validated QueryPlan
    """
    filters = []
    patterns_matched = []

    # Parse publisher
    publisher = parse_publisher(query_text)
    if publisher:
        # Normalize using M2 rules
        normalized_publisher = normalize_filter_value(FilterField.PUBLISHER, publisher)
        filters.append(Filter(
            field=FilterField.PUBLISHER,
            op=FilterOp.EQUALS,
            value=normalized_publisher,
            notes=f"Parsed from query: '{publisher}'"
        ))
        patterns_matched.append("publisher")

    # Parse year range
    year_range = parse_year_range(query_text)
    if year_range:
        start, end = year_range
        filters.append(Filter(
            field=FilterField.YEAR,
            op=FilterOp.RANGE,
            start=start,
            end=end,
            notes=f"Parsed year range: {start}-{end}"
        ))
        patterns_matched.append("year_range")

    # Parse place
    place = parse_place(query_text)
    if place:
        # Normalize using M2 rules
        normalized_place = normalize_filter_value(FilterField.IMPRINT_PLACE, place)
        filters.append(Filter(
            field=FilterField.IMPRINT_PLACE,
            op=FilterOp.EQUALS,
            value=normalized_place,
            notes=f"Parsed from query: '{place}'"
        ))
        patterns_matched.append("place")

    # Parse language
    language = parse_language(query_text)
    if language:
        language_code = language_name_to_code(language)
        filters.append(Filter(
            field=FilterField.LANGUAGE,
            op=FilterOp.EQUALS,
            value=language_code,
            notes=f"Parsed language: {language} → {language_code}"
        ))
        patterns_matched.append("language")

    # Build QueryPlan
    plan = QueryPlan(
        query_text=query_text,
        filters=filters,
        limit=limit,
        debug={
            "parser": "heuristic",
            "patterns_matched": patterns_matched,
            "filters_count": len(filters)
        }
    )

    return plan


def write_plan_to_file(plan: QueryPlan, output_path: Path) -> None:
    """Write QueryPlan to JSON file.

    Args:
        plan: Validated QueryPlan
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(plan.model_dump(), f, indent=2, ensure_ascii=False)


def compute_plan_hash(plan: QueryPlan) -> str:
    """Compute SHA256 hash of canonicalized plan.

    Args:
        plan: QueryPlan

    Returns:
        Hex digest of SHA256 hash
    """
    # Serialize to JSON with sorted keys for canonical representation
    plan_json = json.dumps(plan.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(plan_json.encode('utf-8')).hexdigest()
