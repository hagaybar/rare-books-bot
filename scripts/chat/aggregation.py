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

from scripts.chat.models import ActiveSubgroup
from scripts.chat.exploration_agent import AggregationResult, ExplorationRequest
from scripts.utils.logger import LoggerManager

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
