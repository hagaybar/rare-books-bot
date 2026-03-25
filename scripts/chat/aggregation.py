"""Aggregation Engine for Corpus Exploration.

This module generates and executes aggregation queries over a defined subgroup.
Uses deterministic SQL generation (not LLM) for reliability and safety.

Supports aggregations over:
- publisher: Top publishers in subgroup
- place: Top places of publication
- country: Top countries
- language: Language distribution
- date_decade: Books by decade
- date_century: Books by century
- subject: Top subjects
- agent: Top agents (printers, authors, etc.)
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from scripts.chat.models import ComparisonFacets, ComparisonResult
from scripts.utils.logger import LoggerManager


class AggregationResult(BaseModel):
    """Result of an aggregation query."""

    field: str
    results: List[Dict[str, Any]]  # e.g., [{"value": "Oxford", "count": 42}, ...]
    total_in_subgroup: int
    query_description: str

logger = LoggerManager.get_logger(__name__)


# =============================================================================
# Aggregation Query Definitions
# =============================================================================

# Pre-defined aggregation queries for each field
# These use parameterized queries for safety
AGGREGATION_QUERIES = {
    "publisher": """
        SELECT publisher_norm as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND publisher_norm IS NOT NULL
          AND publisher_norm != ''
        GROUP BY publisher_norm
        ORDER BY count DESC
        LIMIT ?
    """,

    "place": """
        SELECT place_norm as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND place_norm IS NOT NULL
          AND place_norm != ''
        GROUP BY place_norm
        ORDER BY count DESC
        LIMIT ?
    """,

    "country": """
        SELECT country_name as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND country_name IS NOT NULL
          AND country_name != ''
        GROUP BY country_name
        ORDER BY count DESC
        LIMIT ?
    """,

    "language": """
        SELECT l.code as value, COUNT(DISTINCT l.record_id) as count
        FROM languages l
        JOIN records r ON l.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        GROUP BY l.code
        ORDER BY count DESC
        LIMIT ?
    """,

    "date_decade": """
        SELECT
            (date_start / 10 * 10) as decade_start,
            CAST((date_start / 10 * 10) AS TEXT) || 's' as value,
            COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND date_start IS NOT NULL
        GROUP BY decade_start
        ORDER BY decade_start ASC
        LIMIT ?
    """,

    "date_century": """
        SELECT
            ((date_start - 1) / 100 + 1) as century_num,
            CASE
                WHEN (date_start - 1) / 100 + 1 = 15 THEN '15th century'
                WHEN (date_start - 1) / 100 + 1 = 16 THEN '16th century'
                WHEN (date_start - 1) / 100 + 1 = 17 THEN '17th century'
                WHEN (date_start - 1) / 100 + 1 = 18 THEN '18th century'
                WHEN (date_start - 1) / 100 + 1 = 19 THEN '19th century'
                ELSE CAST((date_start - 1) / 100 + 1 AS TEXT) || 'th century'
            END as value,
            COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND date_start IS NOT NULL
        GROUP BY century_num
        ORDER BY century_num ASC
        LIMIT ?
    """,

    "subject": """
        SELECT s.value as value, COUNT(DISTINCT s.record_id) as count
        FROM subjects s
        JOIN records r ON s.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        GROUP BY s.value
        ORDER BY count DESC
        LIMIT ?
    """,

    "agent": """
        SELECT a.agent_norm as value, COUNT(DISTINCT a.record_id) as count
        FROM agents a
        JOIN records r ON a.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        GROUP BY a.agent_norm
        ORDER BY count DESC
        LIMIT ?
    """,

    "agent_role": """
        SELECT
            a.agent_norm || ' (' || a.role_norm || ')' as value,
            COUNT(DISTINCT a.record_id) as count
        FROM agents a
        JOIN records r ON a.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        GROUP BY a.agent_norm, a.role_norm
        ORDER BY count DESC
        LIMIT ?
    """
}


# =============================================================================
# Metadata Question Queries
# =============================================================================

METADATA_QUERIES = {
    "count_language": """
        SELECT COUNT(DISTINCT l.record_id) as count
        FROM languages l
        JOIN records r ON l.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
          AND l.code = ?
    """,

    "count_place": """
        SELECT COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND place_norm = ?
    """,

    "count_country": """
        SELECT COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND country_name = ?
    """,

    "count_publisher": """
        SELECT COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND publisher_norm = ?
    """,

    "earliest_date": """
        SELECT MIN(date_start) as earliest
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND date_start IS NOT NULL
    """,

    "latest_date": """
        SELECT MAX(date_start) as latest
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND date_start IS NOT NULL
    """,

    "date_range": """
        SELECT MIN(date_start) as earliest, MAX(date_start) as latest
        FROM imprints
        WHERE record_id IN (SELECT id FROM records WHERE mms_id IN ({placeholders}))
          AND date_start IS NOT NULL
    """
}


# =============================================================================
# Aggregation Execution
# =============================================================================


def execute_aggregation(
    db_path: Path,
    record_ids: List[str],
    field: str,
    limit: int = 10
) -> AggregationResult:
    """Execute an aggregation query over a subgroup.

    Args:
        db_path: Path to bibliographic database
        record_ids: List of MMS IDs in the subgroup
        field: Field to aggregate (publisher, place, etc.)
        limit: Maximum results to return

    Returns:
        AggregationResult with grouped data

    Raises:
        ValueError: If field is not supported
    """
    if field not in AGGREGATION_QUERIES:
        raise ValueError(f"Unsupported aggregation field: {field}. "
                        f"Supported: {list(AGGREGATION_QUERIES.keys())}")

    if not record_ids:
        return AggregationResult(
            field=field,
            results=[],
            total_in_subgroup=0,
            query_description=f"Aggregation on {field} (empty subgroup)"
        )

    # Build query with placeholders
    placeholders = ",".join("?" * len(record_ids))
    query = AGGREGATION_QUERIES[field].format(placeholders=placeholders)

    # Execute query
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(query, [*record_ids, limit])
        rows = cursor.fetchall()

        # Get column names
        columns = [desc[0] for desc in cursor.description]

        # Build results
        results = []
        for row in rows:
            result = dict(zip(columns, row))
            # Ensure we have 'value' and 'count' keys
            if "value" not in result:
                # For date queries, use the formatted value
                result["value"] = str(row[1]) if len(row) > 1 else str(row[0])
            if "count" not in result:
                result["count"] = row[-1]
            results.append({"value": result["value"], "count": result["count"]})

        logger.info(
            "Executed aggregation",
            extra={
                "field": field,
                "subgroup_size": len(record_ids),
                "results_count": len(results)
            }
        )

        return AggregationResult(
            field=field,
            results=results,
            total_in_subgroup=len(record_ids),
            query_description=f"Top {limit} {field} values in {len(record_ids)} books"
        )

    finally:
        conn.close()


def execute_count_query(
    db_path: Path,
    record_ids: List[str],
    query_type: str,
    filter_value: Optional[str] = None
) -> Optional[int]:
    """Execute a count/metadata query.

    Args:
        db_path: Path to bibliographic database
        record_ids: List of MMS IDs in the subgroup
        query_type: Type of query (count_language, earliest_date, etc.)
        filter_value: Value to filter by (for count queries)

    Returns:
        Count or value, None if not found
    """
    if query_type not in METADATA_QUERIES:
        return None

    if not record_ids:
        return 0

    placeholders = ",".join("?" * len(record_ids))
    query = METADATA_QUERIES[query_type].format(placeholders=placeholders)

    conn = sqlite3.connect(str(db_path))
    try:
        if filter_value:
            cursor = conn.execute(query, [*record_ids, filter_value.lower()])
        else:
            cursor = conn.execute(query, record_ids)

        row = cursor.fetchone()
        return row[0] if row else None

    finally:
        conn.close()


# =============================================================================
# Refinement Queries
# =============================================================================


def apply_refinement(
    db_path: Path,
    record_ids: List[str],
    field: str,
    op: str,
    value: Optional[str] = None,
    start: Optional[int] = None,
    end: Optional[int] = None
) -> List[str]:
    """Apply a refinement filter to narrow the subgroup.

    Args:
        db_path: Path to bibliographic database
        record_ids: Current list of MMS IDs
        field: Field to filter (place, publisher, language, etc.)
        op: Operation (EQUALS, CONTAINS, RANGE)
        value: Value for EQUALS/CONTAINS
        start: Start value for RANGE
        end: End value for RANGE

    Returns:
        Filtered list of MMS IDs
    """
    if not record_ids:
        return []

    placeholders = ",".join("?" * len(record_ids))

    # Build refinement query based on field and operation
    if field == "language":
        if op == "EQUALS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN languages l ON r.id = l.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(l.code) = LOWER(?)
            """
            params = [*record_ids, value]
        else:
            return record_ids  # Only EQUALS supported for language

    elif field == "place":
        if op == "EQUALS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(i.place_norm) = LOWER(?)
            """
            params = [*record_ids, value]
        elif op == "CONTAINS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(i.place_norm) LIKE LOWER(?)
            """
            params = [*record_ids, f"%{value}%"]
        else:
            return record_ids

    elif field == "country":
        if op == "EQUALS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(i.country_name) = LOWER(?)
            """
            params = [*record_ids, value]
        else:
            return record_ids

    elif field == "publisher":
        if op == "EQUALS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(i.publisher_norm) = LOWER(?)
            """
            params = [*record_ids, value]
        elif op == "CONTAINS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(i.publisher_norm) LIKE LOWER(?)
            """
            params = [*record_ids, f"%{value}%"]
        else:
            return record_ids

    elif field == "year":
        if op == "RANGE" and start is not None and end is not None:
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN imprints i ON r.id = i.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND i.date_start >= ?
                  AND i.date_start <= ?
            """
            params = [*record_ids, start, end]
        else:
            return record_ids

    elif field == "subject":
        if op == "CONTAINS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN subjects s ON r.id = s.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(s.value) LIKE LOWER(?)
            """
            params = [*record_ids, f"%{value}%"]
        else:
            return record_ids

    elif field == "agent":
        if op == "EQUALS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN agents a ON r.id = a.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(a.agent_norm) = LOWER(?)
            """
            params = [*record_ids, value]
        elif op == "CONTAINS":
            query = f"""
                SELECT DISTINCT r.mms_id
                FROM records r
                JOIN agents a ON r.id = a.record_id
                WHERE r.mms_id IN ({placeholders})
                  AND LOWER(a.agent_norm) LIKE LOWER(?)
            """
            params = [*record_ids, f"%{value}%"]
        else:
            return record_ids

    else:
        # Unsupported field
        logger.warning(f"Unsupported refinement field: {field}")
        return record_ids

    # Execute query
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(query, params)
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


# =============================================================================
# Comparison Queries
# =============================================================================


# =============================================================================
# Collection Overview (for general/introductory queries)
# =============================================================================


def get_collection_overview(db_path: Path, top_n: int = 5) -> Dict[str, Any]:
    """Get an overview of the entire collection.

    Used when users ask general questions like "what can you tell me about
    the collection?" instead of asking for clarification.

    Args:
        db_path: Path to bibliographic database
        top_n: Number of top items to show for each category

    Returns:
        Dict with collection statistics:
        - total_records: Total number of books
        - date_range: (earliest, latest) years
        - top_languages: List of (code, count)
        - top_places: List of (place, count)
        - top_publishers: List of (publisher, count)
        - top_subjects: List of (subject, count)
        - century_distribution: List of (century, count)
    """
    conn = sqlite3.connect(str(db_path))
    try:
        result = {}

        # Total records
        cursor = conn.execute("SELECT COUNT(*) FROM records")
        result["total_records"] = cursor.fetchone()[0]

        # Date range (filter out Hebrew calendar dates > 2100)
        cursor = conn.execute("""
            SELECT MIN(date_start), MAX(date_start)
            FROM imprints
            WHERE date_start IS NOT NULL
              AND date_start <= 2100
        """)
        row = cursor.fetchone()
        result["date_range"] = (row[0], row[1]) if row else (None, None)

        # Top languages
        cursor = conn.execute("""
            SELECT l.code, COUNT(DISTINCT l.record_id) as cnt
            FROM languages l
            GROUP BY l.code
            ORDER BY cnt DESC
            LIMIT ?
        """, (top_n,))
        result["top_languages"] = [(row[0], row[1]) for row in cursor.fetchall()]

        # Top places
        cursor = conn.execute("""
            SELECT place_norm, COUNT(DISTINCT record_id) as cnt
            FROM imprints
            WHERE place_norm IS NOT NULL AND place_norm != ''
            GROUP BY place_norm
            ORDER BY cnt DESC
            LIMIT ?
        """, (top_n,))
        result["top_places"] = [(row[0], row[1]) for row in cursor.fetchall()]

        # Top publishers
        cursor = conn.execute("""
            SELECT publisher_norm, COUNT(DISTINCT record_id) as cnt
            FROM imprints
            WHERE publisher_norm IS NOT NULL AND publisher_norm != ''
            GROUP BY publisher_norm
            ORDER BY cnt DESC
            LIMIT ?
        """, (top_n,))
        result["top_publishers"] = [(row[0], row[1]) for row in cursor.fetchall()]

        # Top subjects
        cursor = conn.execute("""
            SELECT value, COUNT(DISTINCT record_id) as cnt
            FROM subjects
            GROUP BY value
            ORDER BY cnt DESC
            LIMIT ?
        """, (top_n,))
        result["top_subjects"] = [(row[0], row[1]) for row in cursor.fetchall()]

        # Century distribution (filter out Hebrew calendar dates > 2100)
        cursor = conn.execute("""
            SELECT
                CASE
                    WHEN (date_start - 1) / 100 + 1 = 15 THEN '15th century'
                    WHEN (date_start - 1) / 100 + 1 = 16 THEN '16th century'
                    WHEN (date_start - 1) / 100 + 1 = 17 THEN '17th century'
                    WHEN (date_start - 1) / 100 + 1 = 18 THEN '18th century'
                    WHEN (date_start - 1) / 100 + 1 = 19 THEN '19th century'
                    WHEN (date_start - 1) / 100 + 1 = 20 THEN '20th century'
                    WHEN (date_start - 1) / 100 + 1 = 21 THEN '21st century'
                    ELSE CAST((date_start - 1) / 100 + 1 AS TEXT) || 'th century'
                END as century,
                COUNT(DISTINCT record_id) as cnt
            FROM imprints
            WHERE date_start IS NOT NULL
              AND date_start <= 2100
            GROUP BY (date_start - 1) / 100 + 1
            ORDER BY (date_start - 1) / 100 + 1
        """)
        result["century_distribution"] = [(row[0], row[1]) for row in cursor.fetchall()]

        logger.info(
            "Generated collection overview",
            extra={"total_records": result["total_records"]}
        )

        return result

    finally:
        conn.close()


def format_collection_overview(overview: Dict[str, Any]) -> str:
    """Format collection overview as a natural language response.

    Args:
        overview: Dict from get_collection_overview()

    Returns:
        Formatted markdown string
    """
    parts = []

    # Header
    total = overview.get("total_records", 0)
    parts.append(f"This collection contains **{total:,} rare books**.")
    parts.append("")

    # Date range
    date_range = overview.get("date_range", (None, None))
    if date_range[0] and date_range[1]:
        parts.append(f"**Time period:** {date_range[0]} - {date_range[1]}")
        parts.append("")

    # Century distribution
    centuries = overview.get("century_distribution", [])
    if centuries:
        parts.append("**Distribution by century:**")
        for century, count in centuries:
            pct = (count / total * 100) if total else 0
            parts.append(f"- {century}: {count:,} books ({pct:.1f}%)")
        parts.append("")

    # Languages
    languages = overview.get("top_languages", [])
    if languages:
        lang_names = {
            "lat": "Latin", "heb": "Hebrew", "eng": "English",
            "fre": "French", "ger": "German", "ita": "Italian",
            "spa": "Spanish", "dut": "Dutch", "gre": "Greek",
            "ara": "Arabic", "por": "Portuguese"
        }
        parts.append("**Top languages:**")
        for code, count in languages:
            name = lang_names.get(code, code)
            parts.append(f"- {name}: {count:,} books")
        parts.append("")

    # Places
    places = overview.get("top_places", [])
    if places:
        parts.append("**Top places of publication:**")
        for place, count in places:
            parts.append(f"- {place.title()}: {count:,} books")
        parts.append("")

    # Subjects (if any)
    subjects = overview.get("top_subjects", [])
    if subjects:
        parts.append("**Common subjects:**")
        for subject, count in subjects[:5]:
            # Truncate long subjects
            display = subject[:50] + "..." if len(subject) > 50 else subject
            parts.append(f"- {display}: {count:,} books")
        parts.append("")

    # Suggestions for next steps
    parts.append("---")
    parts.append("**What would you like to explore?**")
    parts.append("- Search by time period (e.g., '16th century books')")
    parts.append("- Search by place (e.g., 'books printed in Venice')")
    parts.append("- Search by language (e.g., 'Hebrew books')")
    parts.append("- Search by subject (e.g., 'books about astronomy')")

    return "\n".join(parts)


def is_overview_query(query_text: str) -> bool:
    """Check if a query is asking for collection overview.

    This function distinguishes between:
    - General overview requests: "What can you tell me about the collection?"
    - Specific search queries: "Tell me about Hebrew books" (NOT an overview)

    Args:
        query_text: User's query text

    Returns:
        True ONLY if this is a genuinely generic collection overview request,
        not a search query with specific criteria.
    """
    query_lower = query_text.lower().strip()

    # Search criteria indicators - if ANY of these are present, it's NOT an overview
    # The user is asking about something specific
    search_criteria = [
        # Languages
        "hebrew", "latin", "english", "french", "german", "italian",
        "spanish", "dutch", "greek", "arabic",
        # Places
        "venice", "paris", "amsterdam", "london", "rome", "berlin",
        "jerusalem", "frankfurt", "vienna", "antwerp", "leiden",
        "italy", "france", "germany", "england", "netherlands",
        # Time periods
        "century", "1400", "1500", "1600", "1700", "1800", "1900",
        "15th", "16th", "17th", "18th", "19th", "20th",
        "medieval", "renaissance", "early modern",
        # Subjects
        "astronomy", "theology", "medicine", "law", "philosophy",
        "mathematics", "history", "poetry", "grammar", "bible",
        "talmud", "kabbalah", "liturgy",
        # Entities
        "printed by", "published by", "written by", "author",
        "printer", "publisher",
        # Question indicators suggesting specific search
        "where were", "when were", "who printed", "how many",
    ]

    # If query contains specific search criteria, it's NOT an overview request
    for criterion in search_criteria:
        if criterion in query_lower:
            return False

    # Exact matches for very general/greeting queries
    exact_matches = [
        "hi", "hello", "help", "?", "start",
        "what do you have", "what's in the collection",
        "show me the collection", "tell me about the collection",
    ]
    if query_lower in exact_matches:
        return True

    # Collection-specific indicators (makes overview more likely)
    collection_indicators = [
        "collection", "catalog", "library", "database",
        "your books", "this system", "available here",
    ]
    has_collection_ref = any(c in query_lower for c in collection_indicators)

    # Overview patterns - but ONLY if no search criteria present
    overview_patterns = [
        "what can you tell me",
        "tell me about",
        "what is this",
        "what's this",
        "describe the collection",
        "overview",
        "introduction",
        "what kind of books",
        "what types of books",
        "what do you have",
        "what's available",
        "general information",
        "about the collection",
        "collection overview",
    ]

    has_overview_pattern = any(p in query_lower for p in overview_patterns)

    # Require EITHER:
    # 1. Overview pattern + collection reference, OR
    # 2. Overview pattern + very short query (< 40 chars, likely just "tell me about this")
    if has_overview_pattern:
        if has_collection_ref:
            return True
        if len(query_lower) < 40:
            return True

    return False


def execute_comparison(
    db_path: Path,
    record_ids: List[str],
    field: str,
    values: List[str]
) -> Dict[str, int]:
    """Execute a comparison query to count records for each value.

    Args:
        db_path: Path to bibliographic database
        record_ids: List of MMS IDs in the subgroup
        field: Field to compare (place, publisher, etc.)
        values: Values to compare

    Returns:
        Dict mapping each value to its count
    """
    results = {}

    for value in values:
        if field == "place":
            count = execute_count_query(db_path, record_ids, "count_place", value)
        elif field == "country":
            count = execute_count_query(db_path, record_ids, "count_country", value)
        elif field == "publisher":
            count = execute_count_query(db_path, record_ids, "count_publisher", value)
        elif field == "language":
            count = execute_count_query(db_path, record_ids, "count_language", value)
        else:
            count = 0

        results[value] = count or 0

    return results


def execute_comparison_enhanced(
    db_path: Path,
    record_ids: List[str],
    field: str,
    values: List[str],
) -> ComparisonResult:
    """Execute a multi-faceted comparison between field values.

    For each value, queries: record counts, date ranges (MIN/MAX),
    language distribution, top agents, and top subjects.
    Cross-value queries: shared agents and subject overlap.

    Args:
        db_path: Path to bibliographic database.
        record_ids: List of MMS IDs in the subgroup.
        field: Field to compare (place, publisher, language, country).
        values: Values to compare (e.g., ["venice", "amsterdam"]).

    Returns:
        ComparisonResult with ComparisonFacets populated.
    """
    if not values:
        return ComparisonResult(
            field=field,
            values=values,
            facets=ComparisonFacets(),
            total_in_subgroup=len(record_ids),
        )

    # Map field to the column used for filtering
    field_column_map = {
        "place": ("imprints", "place_norm"),
        "country": ("imprints", "country_name"),
        "publisher": ("imprints", "publisher_norm"),
        "language": ("languages", "code"),
    }

    table, column = field_column_map.get(field, ("imprints", "place_norm"))

    conn = sqlite3.connect(str(db_path))
    try:
        placeholders = ",".join("?" * len(record_ids))

        counts: Dict[str, int] = {}
        date_ranges: Dict[str, Any] = {}
        language_dist: Dict[str, Dict[str, int]] = {}
        top_agents: Dict[str, List[Dict[str, Any]]] = {}
        top_subjects: Dict[str, List[Dict[str, Any]]] = {}

        # Per-value queries
        for value in values:
            value_lower = value.lower()

            if table == "languages":
                # Language-based filtering
                rec_filter = f"""
                    SELECT DISTINCT r.id FROM records r
                    JOIN languages l ON r.id = l.record_id
                    WHERE r.mms_id IN ({placeholders})
                      AND LOWER(l.code) = LOWER(?)
                """
                rec_params: list = [*record_ids, value_lower]
            else:
                # Imprints-based filtering
                rec_filter = f"""
                    SELECT DISTINCT r.id FROM records r
                    JOIN imprints i ON r.id = i.record_id
                    WHERE r.mms_id IN ({placeholders})
                      AND LOWER(i.{column}) = LOWER(?)
                """
                rec_params = [*record_ids, value_lower]

            # 1. Count
            count_sql = f"SELECT COUNT(*) FROM ({rec_filter})"
            row = conn.execute(count_sql, rec_params).fetchone()
            counts[value] = row[0] if row else 0

            # 2. Date range
            date_sql = f"""
                SELECT MIN(i2.date_start), MAX(i2.date_start)
                FROM imprints i2
                WHERE i2.record_id IN ({rec_filter})
                  AND i2.date_start IS NOT NULL
            """
            row = conn.execute(date_sql, rec_params).fetchone()
            date_ranges[value] = (row[0], row[1]) if row else (None, None)

            # 3. Language distribution
            lang_sql = f"""
                SELECT l2.code, COUNT(DISTINCT l2.record_id)
                FROM languages l2
                WHERE l2.record_id IN ({rec_filter})
                GROUP BY l2.code
                ORDER BY COUNT(DISTINCT l2.record_id) DESC
            """
            lang_rows = conn.execute(lang_sql, rec_params).fetchall()
            language_dist[value] = {r[0]: r[1] for r in lang_rows}

            # 4. Top agents
            agent_sql = f"""
                SELECT a.agent_norm, COUNT(DISTINCT a.record_id)
                FROM agents a
                WHERE a.record_id IN ({rec_filter})
                GROUP BY a.agent_norm
                ORDER BY COUNT(DISTINCT a.record_id) DESC
                LIMIT 5
            """
            agent_rows = conn.execute(agent_sql, rec_params).fetchall()
            top_agents[value] = [
                {"agent": r[0], "count": r[1]} for r in agent_rows
            ]

            # 5. Top subjects
            subj_sql = f"""
                SELECT s.value, COUNT(DISTINCT s.record_id)
                FROM subjects s
                WHERE s.record_id IN ({rec_filter})
                GROUP BY s.value
                ORDER BY COUNT(DISTINCT s.record_id) DESC
                LIMIT 5
            """
            subj_rows = conn.execute(subj_sql, rec_params).fetchall()
            top_subjects[value] = [
                {"subject": r[0], "count": r[1]} for r in subj_rows
            ]

        # Cross-value queries (only if >=2 values)
        shared_agents: List[str] = []
        subject_overlap: List[str] = []

        if len(values) >= 2:
            # Shared agents: agents appearing in records from ALL compared values
            # Build record filter per value, then find intersection
            agent_sets: List[set] = []
            for value in values:
                value_lower = value.lower()
                if table == "languages":
                    rec_filter = f"""
                        SELECT DISTINCT r.id FROM records r
                        JOIN languages l ON r.id = l.record_id
                        WHERE r.mms_id IN ({placeholders})
                          AND LOWER(l.code) = LOWER(?)
                    """
                    params: list = [*record_ids, value_lower]
                else:
                    rec_filter = f"""
                        SELECT DISTINCT r.id FROM records r
                        JOIN imprints i ON r.id = i.record_id
                        WHERE r.mms_id IN ({placeholders})
                          AND LOWER(i.{column}) = LOWER(?)
                    """
                    params = [*record_ids, value_lower]

                agents_sql = f"""
                    SELECT DISTINCT a.agent_norm
                    FROM agents a
                    WHERE a.record_id IN ({rec_filter})
                """
                rows = conn.execute(agents_sql, params).fetchall()
                agent_sets.append({r[0] for r in rows})

            if agent_sets:
                common_agents = agent_sets[0]
                for s in agent_sets[1:]:
                    common_agents = common_agents & s
                shared_agents = sorted(common_agents)

            # Subject overlap
            subject_sets: List[set] = []
            for value in values:
                value_lower = value.lower()
                if table == "languages":
                    rec_filter = f"""
                        SELECT DISTINCT r.id FROM records r
                        JOIN languages l ON r.id = l.record_id
                        WHERE r.mms_id IN ({placeholders})
                          AND LOWER(l.code) = LOWER(?)
                    """
                    params = [*record_ids, value_lower]
                else:
                    rec_filter = f"""
                        SELECT DISTINCT r.id FROM records r
                        JOIN imprints i ON r.id = i.record_id
                        WHERE r.mms_id IN ({placeholders})
                          AND LOWER(i.{column}) = LOWER(?)
                    """
                    params = [*record_ids, value_lower]

                subj_sql = f"""
                    SELECT DISTINCT s.value
                    FROM subjects s
                    WHERE s.record_id IN ({rec_filter})
                """
                rows = conn.execute(subj_sql, params).fetchall()
                subject_sets.append({r[0] for r in rows})

            if subject_sets:
                common_subjects = subject_sets[0]
                for s in subject_sets[1:]:
                    common_subjects = common_subjects & s
                subject_overlap = sorted(common_subjects)

        total = sum(counts.values())

        return ComparisonResult(
            field=field,
            values=values,
            facets=ComparisonFacets(
                counts=counts,
                date_ranges=date_ranges,
                language_distribution=language_dist,
                top_agents=top_agents,
                top_subjects=top_subjects,
                shared_agents=shared_agents,
                subject_overlap=subject_overlap,
            ),
            total_in_subgroup=total,
        )

    finally:
        conn.close()


# =============================================================================
# Full-Collection Aggregation (no record_id filter)
# =============================================================================

# SQL templates without WHERE record_id IN (...) clause
_FULL_COLLECTION_QUERIES = {
    "publisher": """
        SELECT publisher_norm as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE publisher_norm IS NOT NULL AND publisher_norm != ''
        GROUP BY publisher_norm
        ORDER BY count DESC
        LIMIT ?
    """,
    "place": """
        SELECT place_norm as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE place_norm IS NOT NULL AND place_norm != ''
        GROUP BY place_norm
        ORDER BY count DESC
        LIMIT ?
    """,
    "country": """
        SELECT country_name as value, COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE country_name IS NOT NULL AND country_name != ''
        GROUP BY country_name
        ORDER BY count DESC
        LIMIT ?
    """,
    "language": """
        SELECT l.code as value, COUNT(DISTINCT l.record_id) as count
        FROM languages l
        GROUP BY l.code
        ORDER BY count DESC
        LIMIT ?
    """,
    "date_decade": """
        SELECT
            (date_start / 10 * 10) as decade_start,
            CAST((date_start / 10 * 10) AS TEXT) || 's' as value,
            COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE date_start IS NOT NULL
        GROUP BY decade_start
        ORDER BY decade_start ASC
        LIMIT ?
    """,
    "date_century": """
        SELECT
            ((date_start - 1) / 100 + 1) as century_num,
            CASE
                WHEN (date_start - 1) / 100 + 1 = 15 THEN '15th century'
                WHEN (date_start - 1) / 100 + 1 = 16 THEN '16th century'
                WHEN (date_start - 1) / 100 + 1 = 17 THEN '17th century'
                WHEN (date_start - 1) / 100 + 1 = 18 THEN '18th century'
                WHEN (date_start - 1) / 100 + 1 = 19 THEN '19th century'
                ELSE CAST((date_start - 1) / 100 + 1 AS TEXT) || 'th century'
            END as value,
            COUNT(DISTINCT record_id) as count
        FROM imprints
        WHERE date_start IS NOT NULL
        GROUP BY century_num
        ORDER BY century_num ASC
        LIMIT ?
    """,
    "subject": """
        SELECT s.value as value, COUNT(DISTINCT s.record_id) as count
        FROM subjects s
        GROUP BY s.value
        ORDER BY count DESC
        LIMIT ?
    """,
    "agent": """
        SELECT a.agent_norm as value, COUNT(DISTINCT a.record_id) as count
        FROM agents a
        GROUP BY a.agent_norm
        ORDER BY count DESC
        LIMIT ?
    """,
}


def execute_aggregation_full_collection(
    db_path: Path,
    field: str,
    filters: Optional[List[Dict[str, Any]]] = None,
    limit: int = 20,
) -> AggregationResult:
    """Execute an aggregation query over the full collection (or a filtered subset).

    Unlike execute_aggregation(), this does NOT require a pre-computed list
    of record IDs. It runs directly against the full database, optionally
    applying implied filters first.

    Args:
        db_path: Path to bibliographic database.
        field: Field to aggregate (publisher, place, date_decade, etc.).
        filters: Optional implied filters from analytical detection, e.g.
            [{"field": "language", "value": "heb"}].
        limit: Maximum results to return.

    Returns:
        AggregationResult with grouped data.

    Raises:
        ValueError: If field is not supported.
    """
    if filters:
        # Filtered-then-aggregate flow: get matching record IDs first,
        # then delegate to the standard execute_aggregation().
        record_ids = get_all_record_ids(db_path, filters=filters)
        return execute_aggregation(db_path, record_ids, field, limit=limit)

    if field not in _FULL_COLLECTION_QUERIES:
        raise ValueError(
            f"Unsupported aggregation field: {field}. "
            f"Supported: {list(_FULL_COLLECTION_QUERIES.keys())}"
        )

    query = _FULL_COLLECTION_QUERIES[field]

    conn = sqlite3.connect(str(db_path))
    try:
        # Count total records
        total_cursor = conn.execute("SELECT COUNT(*) FROM records")
        total = total_cursor.fetchone()[0]

        cursor = conn.execute(query, [limit])
        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in rows:
            result = dict(zip(columns, row))
            if "value" not in result:
                result["value"] = str(row[1]) if len(row) > 1 else str(row[0])
            if "count" not in result:
                result["count"] = row[-1]
            results.append({"value": result["value"], "count": result["count"]})

        logger.info(
            "Executed full-collection aggregation",
            extra={"field": field, "results_count": len(results)},
        )

        return AggregationResult(
            field=field,
            results=results,
            total_in_subgroup=total,
            query_description=f"Top {limit} {field} values across full collection ({total} books)",
        )
    finally:
        conn.close()


def get_all_record_ids(
    db_path: Path,
    filters: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Get all record MMS IDs, optionally filtered.

    Supports implied filters from analytical query detection:
      - {"field": "language", "value": "heb"}
      - {"field": "year", "start": 1500, "end": 1599}
      - {"field": "place", "value": "venice"}

    Args:
        db_path: Path to bibliographic database.
        filters: Optional list of filter dicts.

    Returns:
        List of MMS ID strings.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        if not filters:
            cursor = conn.execute("SELECT mms_id FROM records")
            return [row[0] for row in cursor.fetchall()]

        # Build filtered query with JOINs as needed
        joins = []
        conditions = []
        params: list = []

        for f in filters:
            fld = f.get("field")
            if fld == "language":
                joins.append("JOIN languages l ON r.id = l.record_id")
                conditions.append("LOWER(l.code) = LOWER(?)")
                params.append(f["value"])
            elif fld == "year":
                joins.append("JOIN imprints i_yr ON r.id = i_yr.record_id")
                conditions.append("i_yr.date_start >= ? AND i_yr.date_start <= ?")
                params.extend([f["start"], f["end"]])
            elif fld == "place":
                joins.append("JOIN imprints i_pl ON r.id = i_pl.record_id")
                conditions.append("LOWER(i_pl.place_norm) = LOWER(?)")
                params.append(f["value"])

        join_sql = " ".join(joins)
        where_sql = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT DISTINCT r.mms_id FROM records r {join_sql} WHERE {where_sql}"

        cursor = conn.execute(query, params)
        return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
