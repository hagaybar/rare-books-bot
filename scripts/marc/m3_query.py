"""Query functions for M3 bibliographic index (low-level API).

This module provides direct SQL query functions for the M3 index layer.
Used primarily for:
- Testing M3 index functionality (see tests/scripts/marc/test_m3_index.py)
- Debugging and exploratory queries
- Direct database access without QueryPlan

For production queries, use the M4 query system instead:
- scripts/query/db_adapter.py - QueryPlan → SQL generation
- scripts/query/execute.py - Full query execution with evidence
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class Evidence:
    """Evidence for why a record was included in CandidateSet."""
    mms_id: str
    field: str  # Field name (e.g., 'imprints.place_norm', 'subjects.value')
    value: Any  # Matched value
    source: List[str]  # MARC sources (e.g., ['260[0]$a'])
    confidence: Optional[float] = None  # Confidence score if from M2


@dataclass
class CandidateSet:
    """Set of candidate records with evidence."""
    mms_ids: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    total_count: int = 0
    query_sql: str = ""  # SQL query used


def connect_db(db_path: Path) -> sqlite3.Connection:
    """Connect to SQLite bibliographic database.

    Args:
        db_path: Path to SQLite database

    Returns:
        Database connection with row_factory set
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def query_by_publisher_and_date_range(
    db_path: Path,
    publisher_norm: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    min_confidence: float = 0.0
) -> CandidateSet:
    """Query books by normalized publisher name and optional date range.

    Args:
        db_path: Path to SQLite database
        publisher_norm: Normalized publisher name (casefolded)
        start_year: Start year (inclusive), None for no lower bound
        end_year: End year (inclusive), None for no upper bound
        min_confidence: Minimum confidence score for M2 normalization

    Returns:
        CandidateSet with matching records and evidence

    Example:
        >>> query_by_publisher_and_date_range(
        ...     db_path,
        ...     publisher_norm="c. fosset",
        ...     start_year=1500,
        ...     end_year=1599
        ... )
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    # Build SQL query with optional date range
    sql_conditions = ["i.publisher_norm = ?"]
    params = [publisher_norm]

    if start_year is not None:
        sql_conditions.append("i.date_end >= ?")
        params.append(start_year)

    if end_year is not None:
        sql_conditions.append("i.date_start <= ?")
        params.append(end_year)

    if min_confidence > 0.0:
        sql_conditions.append("i.publisher_confidence >= ?")
        params.append(min_confidence)

    sql = f"""
        SELECT DISTINCT
            r.mms_id,
            i.publisher_norm,
            i.publisher_display,
            i.publisher_confidence,
            i.publisher_method,
            i.date_start,
            i.date_end,
            i.date_label,
            i.date_confidence,
            i.source_tags
        FROM records r
        JOIN imprints i ON r.id = i.record_id
        WHERE {' AND '.join(sql_conditions)}
        ORDER BY r.mms_id
    """

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CandidateSet
    candidate_set = CandidateSet(query_sql=sql)
    seen_mms_ids = set()

    for row in rows:
        mms_id = row['mms_id']

        if mms_id not in seen_mms_ids:
            candidate_set.mms_ids.append(mms_id)
            seen_mms_ids.add(mms_id)

        # Parse source_tags as MARC sources
        source_tags = json.loads(row['source_tags'])

        # Add publisher evidence
        candidate_set.evidence.append(Evidence(
            mms_id=mms_id,
            field='imprints.publisher_norm',
            value=row['publisher_norm'],
            source=source_tags,
            confidence=row['publisher_confidence']
        ))

        # Add date evidence if date range was specified
        if start_year is not None or end_year is not None:
            candidate_set.evidence.append(Evidence(
                mms_id=mms_id,
                field='imprints.date_range',
                value=f"{row['date_start']}-{row['date_end']}" if row['date_start'] else row['date_label'],
                source=source_tags,
                confidence=row['date_confidence']
            ))

    candidate_set.total_count = len(candidate_set.mms_ids)

    conn.close()
    return candidate_set


def query_by_place_and_date_range(
    db_path: Path,
    place_norm: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    min_confidence: float = 0.0
) -> CandidateSet:
    """Query books by normalized place name and optional date range.

    Args:
        db_path: Path to SQLite database
        place_norm: Normalized place name (casefolded)
        start_year: Start year (inclusive), None for no lower bound
        end_year: End year (inclusive), None for no upper bound
        min_confidence: Minimum confidence score for M2 normalization

    Returns:
        CandidateSet with matching records and evidence

    Example:
        >>> query_by_place_and_date_range(
        ...     db_path,
        ...     place_norm="paris",
        ...     start_year=1500,
        ...     end_year=1599
        ... )
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    # Build SQL query with optional date range
    sql_conditions = ["i.place_norm = ?"]
    params = [place_norm]

    if start_year is not None:
        sql_conditions.append("i.date_end >= ?")
        params.append(start_year)

    if end_year is not None:
        sql_conditions.append("i.date_start <= ?")
        params.append(end_year)

    if min_confidence > 0.0:
        sql_conditions.append("i.place_confidence >= ?")
        params.append(min_confidence)

    sql = f"""
        SELECT DISTINCT
            r.mms_id,
            i.place_norm,
            i.place_display,
            i.place_confidence,
            i.place_method,
            i.date_start,
            i.date_end,
            i.date_label,
            i.date_confidence,
            i.source_tags
        FROM records r
        JOIN imprints i ON r.id = i.record_id
        WHERE {' AND '.join(sql_conditions)}
        ORDER BY r.mms_id
    """

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CandidateSet
    candidate_set = CandidateSet(query_sql=sql)
    seen_mms_ids = set()

    for row in rows:
        mms_id = row['mms_id']

        if mms_id not in seen_mms_ids:
            candidate_set.mms_ids.append(mms_id)
            seen_mms_ids.add(mms_id)

        # Parse source_tags as MARC sources
        source_tags = json.loads(row['source_tags'])

        # Add place evidence
        candidate_set.evidence.append(Evidence(
            mms_id=mms_id,
            field='imprints.place_norm',
            value=row['place_norm'],
            source=source_tags,
            confidence=row['place_confidence']
        ))

        # Add date evidence if date range was specified
        if start_year is not None or end_year is not None:
            candidate_set.evidence.append(Evidence(
                mms_id=mms_id,
                field='imprints.date_range',
                value=f"{row['date_start']}-{row['date_end']}" if row['date_start'] else row['date_label'],
                source=source_tags,
                confidence=row['date_confidence']
            ))

    candidate_set.total_count = len(candidate_set.mms_ids)

    conn.close()
    return candidate_set


def query_by_subject(
    db_path: Path,
    subject_query: str,
    use_fts: bool = True
) -> CandidateSet:
    """Query books by subject heading.

    Args:
        db_path: Path to SQLite database
        subject_query: Subject query string (exact match or FTS query)
        use_fts: Use full-text search if True, exact match if False

    Returns:
        CandidateSet with matching records and evidence

    Example:
        >>> query_by_subject(db_path, "Catholic Church")
        >>> query_by_subject(db_path, "prayer* devotion*", use_fts=True)
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    if use_fts:
        # Full-text search
        sql = """
            SELECT DISTINCT
                r.mms_id,
                s.value,
                s.source_tag,
                s.scheme,
                s.source
            FROM records r
            JOIN subjects s ON r.id = s.record_id
            JOIN subjects_fts sf ON s.id = sf.rowid
            WHERE subjects_fts MATCH ?
            ORDER BY r.mms_id
        """
        params = [subject_query]
    else:
        # Exact match (case-insensitive)
        sql = """
            SELECT DISTINCT
                r.mms_id,
                s.value,
                s.source_tag,
                s.scheme,
                s.source
            FROM records r
            JOIN subjects s ON r.id = s.record_id
            WHERE LOWER(s.value) = LOWER(?)
            ORDER BY r.mms_id
        """
        params = [subject_query]

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CandidateSet
    candidate_set = CandidateSet(query_sql=sql)
    seen_mms_ids = set()

    for row in rows:
        mms_id = row['mms_id']

        if mms_id not in seen_mms_ids:
            candidate_set.mms_ids.append(mms_id)
            seen_mms_ids.add(mms_id)

        # Parse source as MARC sources
        source = json.loads(row['source'])

        # Add subject evidence
        candidate_set.evidence.append(Evidence(
            mms_id=mms_id,
            field='subjects.value',
            value=row['value'],
            source=source
        ))

    candidate_set.total_count = len(candidate_set.mms_ids)

    conn.close()
    return candidate_set


def query_by_agent(
    db_path: Path,
    agent_name: str,
    role: Optional[str] = None
) -> CandidateSet:
    """Query books by agent (author, contributor, etc.).

    Args:
        db_path: Path to SQLite database
        agent_name: Agent name (case-insensitive partial match)
        role: Optional role filter ('author', 'contributor')

    Returns:
        CandidateSet with matching records and evidence

    Example:
        >>> query_by_agent(db_path, "Shakespeare")
        >>> query_by_agent(db_path, "Shakespeare", role="author")
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    # Build SQL query with optional role filter
    sql_conditions = ["LOWER(a.value) LIKE LOWER(?)"]
    params = [f"%{agent_name}%"]

    if role:
        sql_conditions.append("a.role = ?")
        params.append(role)

    sql = f"""
        SELECT DISTINCT
            r.mms_id,
            a.value,
            a.role,
            a.relator_code,
            a.source
        FROM records r
        JOIN agents a ON r.id = a.record_id
        WHERE {' AND '.join(sql_conditions)}
        ORDER BY r.mms_id
    """

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CandidateSet
    candidate_set = CandidateSet(query_sql=sql)
    seen_mms_ids = set()

    for row in rows:
        mms_id = row['mms_id']

        if mms_id not in seen_mms_ids:
            candidate_set.mms_ids.append(mms_id)
            seen_mms_ids.add(mms_id)

        # Parse source as MARC sources
        source = json.loads(row['source'])

        # Add agent evidence
        candidate_set.evidence.append(Evidence(
            mms_id=mms_id,
            field=f"agents.{row['role']}",
            value=row['value'],
            source=source
        ))

    candidate_set.total_count = len(candidate_set.mms_ids)

    conn.close()
    return candidate_set


def query_by_title(
    db_path: Path,
    title_query: str,
    title_type: Optional[str] = None,
    use_fts: bool = True
) -> CandidateSet:
    """Query books by title.

    Args:
        db_path: Path to SQLite database
        title_query: Title query string (exact match or FTS query)
        title_type: Optional title type filter ('main', 'uniform', 'variant')
        use_fts: Use full-text search if True, exact match if False

    Returns:
        CandidateSet with matching records and evidence

    Example:
        >>> query_by_title(db_path, "Holy Week")
        >>> query_by_title(db_path, "office* prayer*", use_fts=True)
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    if use_fts:
        # Full-text search
        sql_conditions = ["titles_fts MATCH ?"]
        params = [title_query]

        if title_type:
            sql_conditions.append("t.title_type = ?")
            params.append(title_type)

        sql = f"""
            SELECT DISTINCT
                r.mms_id,
                t.value,
                t.title_type,
                t.source
            FROM records r
            JOIN titles t ON r.id = t.record_id
            JOIN titles_fts tf ON t.id = tf.rowid
            WHERE {' AND '.join(sql_conditions)}
            ORDER BY r.mms_id
        """
    else:
        # Exact match (case-insensitive)
        sql_conditions = ["LOWER(t.value) = LOWER(?)"]
        params = [title_query]

        if title_type:
            sql_conditions.append("t.title_type = ?")
            params.append(title_type)

        sql = f"""
            SELECT DISTINCT
                r.mms_id,
                t.value,
                t.title_type,
                t.source
            FROM records r
            JOIN titles t ON r.id = t.record_id
            WHERE {' AND '.join(sql_conditions)}
            ORDER BY r.mms_id
        """

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CandidateSet
    candidate_set = CandidateSet(query_sql=sql)
    seen_mms_ids = set()

    for row in rows:
        mms_id = row['mms_id']

        if mms_id not in seen_mms_ids:
            candidate_set.mms_ids.append(mms_id)
            seen_mms_ids.add(mms_id)

        # Parse source as MARC sources
        source = json.loads(row['source'])

        # Add title evidence
        candidate_set.evidence.append(Evidence(
            mms_id=mms_id,
            field=f"titles.{row['title_type']}",
            value=row['value'],
            source=source
        ))

    candidate_set.total_count = len(candidate_set.mms_ids)

    conn.close()
    return candidate_set


def get_record_by_mms_id(db_path: Path, mms_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve full record data by MMS ID.

    Args:
        db_path: Path to SQLite database
        mms_id: MMS ID of record

    Returns:
        Dictionary with all record fields, or None if not found
    """
    conn = connect_db(db_path)
    cursor = conn.cursor()

    # Get basic record info
    cursor.execute("SELECT * FROM records WHERE mms_id = ?", (mms_id,))
    record_row = cursor.fetchone()

    if not record_row:
        conn.close()
        return None

    record_id = record_row['id']
    record = {
        'mms_id': mms_id,
        'source_file': record_row['source_file'],
        'jsonl_line_number': record_row['jsonl_line_number']
    }

    # Get titles
    cursor.execute("SELECT * FROM titles WHERE record_id = ?", (record_id,))
    record['titles'] = [dict(row) for row in cursor.fetchall()]

    # Get imprints
    cursor.execute("SELECT * FROM imprints WHERE record_id = ? ORDER BY occurrence", (record_id,))
    record['imprints'] = [dict(row) for row in cursor.fetchall()]

    # Get subjects
    cursor.execute("SELECT * FROM subjects WHERE record_id = ?", (record_id,))
    record['subjects'] = [dict(row) for row in cursor.fetchall()]

    # Get agents
    cursor.execute("SELECT * FROM agents WHERE record_id = ?", (record_id,))
    record['agents'] = [dict(row) for row in cursor.fetchall()]

    # Get languages
    cursor.execute("SELECT * FROM languages WHERE record_id = ?", (record_id,))
    record['languages'] = [dict(row) for row in cursor.fetchall()]

    # Get notes
    cursor.execute("SELECT * FROM notes WHERE record_id = ?", (record_id,))
    record['notes'] = [dict(row) for row in cursor.fetchall()]

    # Get physical descriptions
    cursor.execute("SELECT * FROM physical_descriptions WHERE record_id = ?", (record_id,))
    record['physical_descriptions'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return record
