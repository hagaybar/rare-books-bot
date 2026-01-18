"""Database adapter for M4 query system.

Maps M4 filter fields to M3 database schema and generates SQL.
Handles JOIN strategy, normalization, and evidence field extraction.
"""

import sqlite3
import re
from pathlib import Path
from typing import Tuple, Dict, List, Optional

from scripts.schemas import QueryPlan, FilterField, FilterOp
from scripts.marc.m3_contract import M3Tables, M3Columns, M3Aliases


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


def normalize_filter_value(field: FilterField, raw_value: str, op: FilterOp = None) -> str:
    """Normalize filter values using M2 normalization rules.

    For publisher/place: casefold, strip punctuation, remove brackets.
    This matches the normalization in scripts/marc/normalize.py.

    Args:
        field: Filter field type
        raw_value: Raw input value
        op: Filter operation (used to determine FTS5 quoting for TITLE/SUBJECT)

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
        # Lowercase for consistent matching
        value = raw_value.lower()
        # Only wrap in quotes for FTS5 CONTAINS operations (MATCH syntax)
        # EQUALS operations use direct string comparison and must NOT be quoted
        if op == FilterOp.CONTAINS and ' ' in value:
            # Escape any existing double quotes in the value
            value = value.replace('"', '""')
            value = f'"{value}"'
        return value
    elif field == FilterField.AGENT:
        # Agents use substring match, casefold for consistency
        return raw_value.casefold()
    elif field in [FilterField.AGENT_NORM, FilterField.AGENT_ROLE, FilterField.AGENT_TYPE]:
        # Stage 5: Agent normalization follows same rules as agent_base
        # Casefold, strip brackets, collapse whitespace, remove trailing punctuation
        # ALSO remove commas to enable flexible searching (with or without commas)
        value = raw_value.casefold()
        # Remove brackets
        value = re.sub(r'[\[\]]', '', value)
        # Remove commas for flexible matching
        value = value.replace(',', '')
        # Strip trailing punctuation
        value = value.rstrip('.,;:')
        # Collapse multiple spaces
        value = re.sub(r'\s+', ' ', value)
        # Strip leading/trailing whitespace
        value = value.strip()
        return value
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
            needed_joins.add(M3Tables.IMPRINTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_publisher"
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.PUBLISHER_NORM}) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_publisher"
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.PUBLISHER_NORM}) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for publisher")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.IMPRINT_PLACE:
            needed_joins.add(M3Tables.IMPRINTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_place"
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.PLACE_NORM}) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_place"
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.PLACE_NORM}) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for imprint_place")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.COUNTRY:
            needed_joins.add(M3Tables.IMPRINTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_country"
                # Country names are already normalized (lowercase) in the database
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.COUNTRY_NAME}) = LOWER(:{param_name})"
                params[param_name] = filter.value.lower().strip()
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_country"
                condition = f"LOWER({M3Aliases.IMPRINTS}.{M3Columns.Imprints.COUNTRY_NAME}) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{filter.value.lower().strip()}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for country")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.YEAR:
            needed_joins.add(M3Tables.IMPRINTS)
            if filter.op == FilterOp.RANGE:
                # Overlap match: record's date range overlaps with query range
                start_param = f"{param_prefix}_year_start"
                end_param = f"{param_prefix}_year_end"
                condition = f"({M3Aliases.IMPRINTS}.{M3Columns.Imprints.DATE_END} >= :{start_param} AND {M3Aliases.IMPRINTS}.{M3Columns.Imprints.DATE_START} <= :{end_param})"
                params[start_param] = filter.start
                params[end_param] = filter.end
            else:
                raise ValueError(f"Unsupported operation {filter.op} for year")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.LANGUAGE:
            needed_joins.add(M3Tables.LANGUAGES)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_lang"
                condition = f"{M3Aliases.LANGUAGES}.{M3Columns.Languages.CODE} = :{param_name}"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.IN:
                # Generate multiple parameters for IN clause
                lang_params = []
                for lang_idx, lang in enumerate(filter.value):
                    param_name = f"{param_prefix}_lang_{lang_idx}"
                    lang_params.append(f":{param_name}")
                    params[param_name] = normalize_filter_value(filter.field, lang)
                condition = f"{M3Aliases.LANGUAGES}.{M3Columns.Languages.CODE} IN ({', '.join(lang_params)})"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for language")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.TITLE:
            if filter.op == FilterOp.EQUALS:
                needed_joins.add(M3Tables.TITLES)
                param_name = f"{param_prefix}_title"
                condition = f"LOWER({M3Aliases.TITLES}.{M3Columns.Titles.VALUE}) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value, filter.op)
            elif filter.op == FilterOp.CONTAINS:
                # Use FTS5 for full-text search
                # FTS5 content table is 'titles', so we need to join through titles to records
                param_name = f"{param_prefix}_title"
                condition = f"""EXISTS (
                    SELECT 1
                    FROM {M3Tables.TITLES_FTS}
                    JOIN {M3Tables.TITLES} ON {M3Tables.TITLES_FTS}.rowid = {M3Tables.TITLES}.{M3Columns.Titles.ID}
                    WHERE {M3Tables.TITLES}.{M3Columns.Titles.RECORD_ID} = {M3Aliases.RECORDS}.{M3Columns.Records.ID}
                    AND {M3Tables.TITLES_FTS} MATCH :{param_name}
                )"""
                params[param_name] = normalize_filter_value(filter.field, filter.value, filter.op)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for title")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.SUBJECT:
            if filter.op == FilterOp.CONTAINS:
                # Use FTS5 for full-text search
                # FTS5 content table is 'subjects', so we need to join through subjects to records
                param_name = f"{param_prefix}_subject"
                condition = f"""EXISTS (
                    SELECT 1
                    FROM {M3Tables.SUBJECTS_FTS}
                    JOIN {M3Tables.SUBJECTS} ON {M3Tables.SUBJECTS_FTS}.rowid = {M3Tables.SUBJECTS}.{M3Columns.Subjects.ID}
                    WHERE {M3Tables.SUBJECTS}.{M3Columns.Subjects.RECORD_ID} = {M3Aliases.RECORDS}.{M3Columns.Records.ID}
                    AND {M3Tables.SUBJECTS_FTS} MATCH :{param_name}
                )"""
                params[param_name] = normalize_filter_value(filter.field, filter.value, filter.op)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for subject")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.AGENT:
            needed_joins.add(M3Tables.AGENTS)
            if filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_agent"
                condition = f"LOWER({M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_RAW}) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for agent")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.AGENT_NORM:
            # Stage 5: Query by normalized agent name (comma-insensitive)
            # Use REPLACE to remove commas from both database and search string
            needed_joins.add(M3Tables.AGENTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_agent_norm"
                condition = f"LOWER(REPLACE({M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_NORM}, ',', '')) = LOWER(:{param_name})"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            elif filter.op == FilterOp.CONTAINS:
                param_name = f"{param_prefix}_agent_norm"
                condition = f"LOWER(REPLACE({M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_NORM}, ',', '')) LIKE LOWER(:{param_name})"
                params[param_name] = f"%{normalize_filter_value(filter.field, filter.value)}%"
            else:
                raise ValueError(f"Unsupported operation {filter.op} for agent_norm")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.AGENT_ROLE:
            # Stage 5: Query by role (printer, translator, etc.)
            needed_joins.add(M3Tables.AGENTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_agent_role"
                condition = f"{M3Aliases.AGENTS}.{M3Columns.Agents.ROLE_NORM} = :{param_name}"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for agent_role")

            if filter.negate:
                condition = f"NOT ({condition})"
            conditions.append(condition)

        elif filter.field == FilterField.AGENT_TYPE:
            # Stage 5: Query by type (personal, corporate, meeting)
            needed_joins.add(M3Tables.AGENTS)
            if filter.op == FilterOp.EQUALS:
                param_name = f"{param_prefix}_agent_type"
                condition = f"{M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_TYPE} = :{param_name}"
                params[param_name] = normalize_filter_value(filter.field, filter.value)
            else:
                raise ValueError(f"Unsupported operation {filter.op} for agent_type")

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
    columns = [f"DISTINCT {M3Aliases.RECORDS}.{M3Columns.Records.MMS_ID}"]

    # Add columns from joined tables for evidence
    if M3Tables.IMPRINTS in needed_joins:
        columns.extend([
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PUBLISHER_NORM}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PUBLISHER_CONFIDENCE}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PUBLISHER_RAW}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PLACE_NORM}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PLACE_CONFIDENCE}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.PLACE_RAW}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.DATE_START}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.DATE_END}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.DATE_CONFIDENCE}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.COUNTRY_CODE}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.COUNTRY_NAME}",
            f"{M3Aliases.IMPRINTS}.{M3Columns.Imprints.SOURCE_TAGS}"
        ])

    if M3Tables.LANGUAGES in needed_joins:
        columns.extend([
            f"{M3Aliases.LANGUAGES}.{M3Columns.Languages.CODE} AS language_code",
            f"{M3Aliases.LANGUAGES}.{M3Columns.Languages.SOURCE} AS language_source"
        ])

    if M3Tables.TITLES in needed_joins:
        columns.extend([
            f"{M3Aliases.TITLES}.{M3Columns.Titles.VALUE} AS title_value",
            f"{M3Aliases.TITLES}.{M3Columns.Titles.SOURCE} AS title_source"
        ])

    if M3Tables.SUBJECTS in needed_joins:
        columns.extend([
            f"{M3Aliases.SUBJECTS}.{M3Columns.Subjects.VALUE} AS subject_value",
            f"{M3Aliases.SUBJECTS}.{M3Columns.Subjects.SOURCE} AS subject_source"
        ])

    if M3Tables.AGENTS in needed_joins:
        columns.extend([
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_RAW} AS agent_raw",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_NORM} AS agent_norm",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_CONFIDENCE} AS agent_confidence",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.ROLE_NORM} AS agent_role_norm",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.ROLE_CONFIDENCE} AS agent_role_confidence",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.AGENT_TYPE} AS agent_type",
            f"{M3Aliases.AGENTS}.{M3Columns.Agents.PROVENANCE_JSON} AS agent_provenance"
        ])

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
    if M3Tables.IMPRINTS in needed_joins:
        joins.append(f"JOIN {M3Tables.IMPRINTS} {M3Aliases.IMPRINTS} ON {M3Aliases.RECORDS}.{M3Columns.Records.ID} = {M3Aliases.IMPRINTS}.{M3Columns.Imprints.RECORD_ID}")

    if M3Tables.LANGUAGES in needed_joins:
        joins.append(f"LEFT JOIN {M3Tables.LANGUAGES} {M3Aliases.LANGUAGES} ON {M3Aliases.RECORDS}.{M3Columns.Records.ID} = {M3Aliases.LANGUAGES}.{M3Columns.Languages.RECORD_ID}")

    if M3Tables.TITLES in needed_joins:
        joins.append(f"LEFT JOIN {M3Tables.TITLES} {M3Aliases.TITLES} ON {M3Aliases.RECORDS}.{M3Columns.Records.ID} = {M3Aliases.TITLES}.{M3Columns.Titles.RECORD_ID}")

    if M3Tables.SUBJECTS in needed_joins:
        joins.append(f"LEFT JOIN {M3Tables.SUBJECTS} {M3Aliases.SUBJECTS} ON {M3Aliases.RECORDS}.{M3Columns.Records.ID} = {M3Aliases.SUBJECTS}.{M3Columns.Subjects.RECORD_ID}")

    if M3Tables.AGENTS in needed_joins:
        joins.append(f"LEFT JOIN {M3Tables.AGENTS} {M3Aliases.AGENTS} ON {M3Aliases.RECORDS}.{M3Columns.Records.ID} = {M3Aliases.AGENTS}.{M3Columns.Agents.RECORD_ID}")

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
        f"FROM {M3Tables.RECORDS} {M3Aliases.RECORDS}",
        join_clauses,
        f"WHERE {where_clause}",
        f"ORDER BY {M3Aliases.RECORDS}.{M3Columns.Records.MMS_ID}"
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
