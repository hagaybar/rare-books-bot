"""Database adapter for M4 query system.

Maps M4 filter fields to M3 database schema and generates SQL.
Handles JOIN strategy, normalization, and evidence field extraction.
"""

import sqlite3
import re
from pathlib import Path
from typing import Tuple, Dict, List, Optional

from scripts.schemas import QueryPlan, FilterField, FilterOp


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get database connection with row_factory for dict-like access.

    Args:
        db_path: Path to SQLite database

    Returns:
        Connection with row_factory configured
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def normalize_filter_value(field: FilterField, raw_value: str) -> str:
    """Normalize filter values using M2 normalization rules.

    For publisher/place: casefold, strip punctuation, remove brackets.
    This matches the normalization in scripts/marc/normalize.py.

    Args:
        field: Filter field type
        raw_value: Raw input value

    Returns:
        Normalized value
    """
    if field in [FilterField.PUBLISHER, FilterField.IMPRINT_PLACE]:
        # M2 normalization: casefold, strip brackets, remove punctuation
        value = raw_value.casefold()
        # Remove brackets
        value = re.sub(r'[\[\]]', '', value)
        # Remove punctuation except spaces and hyphens
        value = re.sub(r'[^\w\s\-]', '', value)
        # Collapse multiple spaces
        value = re.sub(r'\s+', ' ', value)
        # Strip leading/trailing whitespace
        value = value.strip()
        return value
    elif field == FilterField.LANGUAGE:
        # Languages are ISO 639-2 codes, lowercase
        return raw_value.lower()
    elif field == FilterField.TITLE or field == FilterField.SUBJECT:
        # FTS5 queries are case-insensitive, but we normalize for consistency
        return raw_value.lower()
    elif field == FilterField.AGENT:
        # Agents use substring match, casefold for consistency
        return raw_value.casefold()
    else:
        # For other fields (like YEAR), return as-is
        return raw_value


def build_where_clause(plan: QueryPlan) -> Tuple[str, Dict[str, any], List[str]]:
    """Build SQL WHERE clause from QueryPlan.

    Maps each filter to SQL condition and determines necessary JOINs.

    Args:
        plan: Validated QueryPlan

    Returns:
        Tuple of (WHERE clause, parameters dict, needed JOIN tables)
    """
    if not plan.filters:
        return "1=1", {}, []

    conditions = []
    params = {}
    needed_joins = set()  # Track which tables need to be joined

    for idx, filter in enumerate(plan.filters):
        # Generate unique parameter names for this filter
        param_prefix = f"filter_{idx}"

        if filter.field == FilterField.PUBLISHER:
            needed_joins.add("imprints")
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_publisher"
                condition = f"LOWER(i.publisher_norm) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_publisher"
                condition = f"LOWER(i.publisher_norm) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for publisher")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.IMPRINT_PLACE:
            needed_joins.add("imprints")
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_place"
                condition = f"LOWER(i.place_norm) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_place"
                condition = f"LOWER(i.place_norm) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for imprint_place")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.YEAR:
            needed_joins.add("imprints")
            if filter.op == FilterOp.RANGE:
                # Overlap match: record's date range overlaps with query range
                start_param = f"{param_prefix}_year_start"
                end_param = f"{param_prefix}_year_end"
                condition = f"(i.date_end >= :{start_param} AND i.date_start <= :{end_param})"
                params[start_param] = filter.start
                params[end_param] = filter.end
            else:
                raise ValueError(f"Unsupported operation {filter.op} for year")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.LANGUAGE:
            needed_joins.add("languages")
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_lang"
                condition = f"l.code = :{param_name}"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.IN:
                # Generate multiple parameters for IN clause
                lang_params = []
                for lang_idx, lang in enumerate(filter.value):
                    param_name = f"{param_prefix}_lang_{lang_idx}"
                    lang_params.append(f":{param_name}")
                    params[param_name] = normalize_filter_value(filter.field, lang)
                condition = f"l.code IN ({', '.join(lang_params)})"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for language")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.TITLE:
            needed_joins.add("titles")
            if filter.op == FilterOp.CONTAINS:
                # Use FTS5 for full-text search
                param_name = f"{param_prefix}_title"
                # FTS5 MATCH query
                condition = f"EXISTS (SELECT 1 FROM titles_fts WHERE titles_fts.mms_id = r.mms_id AND titles_fts MATCH :{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for title")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.SUBJECT:
            needed_joins.add("subjects")
            if filter.op == FilterOp.CONTAINS:
                # Use FTS5 for full-text search
                param_name = f"{param_prefix}_subject"
                condition = f"EXISTS (SELECT 1 FROM subjects_fts WHERE subjects_fts.mms_id = r.mms_id AND subjects_fts MATCH :{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for subject")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.AGENT:
            needed_joins.add("agents")
            if filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_agent"
                condition = f"LOWER(a.value) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for agent")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

    where_clause = " AND ".join(conditions)
    return where_clause, params, list(needed_joins)


def build_select_columns(needed_joins: List[str]) -> str:
    """Build SELECT column list based on needed tables.

    Args:
        needed_joins: List of tables that will be joined

    Returns:
        SELECT column list
    """
    # Always include record ID
    columns = ["DISTINCT r.mms_id"]

    # Add columns from joined tables for evidence
    if "imprints" in needed_joins:
        columns.extend([
            "i.publisher_norm", "i.publisher_confidence", "i.publisher_raw",
            "i.place_norm", "i.place_confidence", "i.place_raw",
            "i.date_start", "i.date_end", "i.date_confidence",
            "i.source_tags"
        ])

    if "languages" in needed_joins:
        columns.extend(["l.code AS language_code", "l.source AS language_source"])

    if "titles" in needed_joins:
        columns.extend(["t.value AS title_value", "t.source AS title_source"])

    if "subjects" in needed_joins:
        columns.extend(["s.value AS subject_value", "s.source AS subject_source"])

    if "agents" in needed_joins:
        columns.extend(["a.value AS agent_value", "a.role AS agent_role", "a.source AS agent_source"])

    return ", ".join(columns)


def build_join_clauses(needed_joins: List[str]) -> str:
    """Build JOIN clauses based on needed tables.

    Args:
        needed_joins: List of tables that need to be joined

    Returns:
        JOIN clauses
    """
    joins = []

    # Imprints is the most common join
    if "imprints" in needed_joins:
        joins.append("JOIN imprints i ON r.id = i.record_id")

    if "languages" in needed_joins:
        joins.append("LEFT JOIN languages l ON r.id = l.record_id")

    if "titles" in needed_joins:
        joins.append("LEFT JOIN titles t ON r.id = t.record_id")

    if "subjects" in needed_joins:
        joins.append("LEFT JOIN subjects s ON r.id = s.record_id")

    if "agents" in needed_joins:
        joins.append("LEFT JOIN agents a ON r.id = a.record_id")

    return "\n".join(joins)


def build_full_query(plan: QueryPlan) -> Tuple[str, Dict[str, any]]:
    """Build complete SQL query from QueryPlan.

    Args:
        plan: Validated QueryPlan

    Returns:
        Tuple of (SQL query, parameters dict)
    """
    where_clause, params, needed_joins = build_where_clause(plan)
    select_columns = build_select_columns(needed_joins)
    join_clauses = build_join_clauses(needed_joins)

    sql_parts = [
        f"SELECT {select_columns}",
        "FROM records r",
        join_clauses,
        f"WHERE {where_clause}",
        "ORDER BY r.mms_id"
    ]

    if plan.limit:
        sql_parts.append(f"LIMIT {plan.limit}")

    sql = "\n".join(part for part in sql_parts if part)
    return sql, params


def fetch_candidates(
    conn: sqlite3.Connection,
    sql: str,
    params: Dict[str, any]
) -> List[sqlite3.Row]:
    """Execute query and return rows.

    Args:
        conn: Database connection
        sql: SQL query
        params: Query parameters

    Returns:
        List of result rows
    """
    cursor = conn.execute(sql, params)
    return cursor.fetchall()
