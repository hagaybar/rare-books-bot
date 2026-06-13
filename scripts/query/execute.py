"""Query executor - QueryPlan → SQL → CandidateSet with Evidence.

Executes validated QueryPlan against M3 database and generates
CandidateSet with per-record evidence and match rationale.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from scripts.schemas import QueryPlan, CandidateSet, Candidate, Evidence, FilterField, FilterOp
from scripts.query.db_adapter import build_full_query, get_connection, fetch_candidates
from scripts.query.compile import compute_plan_hash
from scripts.query.subject_hints import get_top_subjects
from scripts.query.llm_compiler import compile_query_with_subject_hints

logger = logging.getLogger(__name__)


def fetch_display_info(
    conn: sqlite3.Connection,
    mms_ids: List[str]
) -> Dict[str, Dict[str, Any]]:
    """Fetch display metadata for candidates.

    Fetches title, author, date, place, publisher, subjects, and description
    for all candidate records.

    Args:
        conn: Database connection
        mms_ids: List of MMS IDs to fetch info for

    Returns:
        Dict mapping mms_id -> {
            "title": str,
            "author": str,
            "date_start": int,
            "date_end": int,
            "place_norm": str,
            "place_raw": str,
            "publisher": str,
            "subjects": List[str],
            "description": str
        }
    """
    if not mms_ids:
        return {}

    # Initialize result dict with all fields
    result = {}
    for mms_id in mms_ids:
        result[mms_id] = {
            "title": None,
            "author": None,
            "date_start": None,
            "date_end": None,
            "place_norm": None,
            "place_raw": None,
            "publisher": None,
            "subjects": [],
            "description": None,
        }

    placeholders = ",".join("?" * len(mms_ids))

    # Fetch titles (get first/primary title for each record)
    # Note: source is stored as JSON array like '["245$a"]'
    title_sql = f"""
        SELECT r.mms_id, t.value
        FROM records r
        LEFT JOIN titles t ON t.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        AND t.source LIKE '%245%'
        GROUP BY r.mms_id
    """

    try:
        cursor = conn.execute(title_sql, mms_ids)
        for row in cursor.fetchall():
            mms_id = row[0]
            title = row[1]
            if title:
                # Truncate long titles for display
                result[mms_id]["title"] = title[:100] + "..." if len(title) > 100 else title
    except Exception as e:
        logger.warning("fetch_display_info: title query failed: %s", e)

    # Fetch primary author (first agent with author/creator role)
    # Prefer 100 field (main author) or role_norm = 'author'
    author_sql = f"""
        SELECT r.mms_id, a.agent_raw
        FROM records r
        LEFT JOIN agents a ON a.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        AND (a.role_norm = 'author' OR a.provenance_json LIKE '%100%')
        GROUP BY r.mms_id
    """

    try:
        cursor = conn.execute(author_sql, mms_ids)
        for row in cursor.fetchall():
            mms_id = row[0]
            author = row[1]
            if author:
                # Truncate long author names for display
                result[mms_id]["author"] = author[:80] + "..." if len(author) > 80 else author
    except Exception as e:
        logger.warning("fetch_display_info: author query failed: %s", e)

    # Fetch imprint info (date, place, publisher)
    imprint_sql = f"""
        SELECT r.mms_id, i.date_start, i.date_end, i.place_norm, i.place_raw, i.publisher_raw
        FROM records r
        LEFT JOIN imprints i ON i.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        GROUP BY r.mms_id
    """

    try:
        cursor = conn.execute(imprint_sql, mms_ids)
        for row in cursor.fetchall():
            mms_id = row[0]
            if mms_id in result:
                result[mms_id]["date_start"] = row[1]
                result[mms_id]["date_end"] = row[2]
                result[mms_id]["place_norm"] = row[3]
                result[mms_id]["place_raw"] = row[4]
                if row[5]:
                    # Truncate long publisher names
                    pub = row[5]
                    result[mms_id]["publisher"] = (pub[:60] + "...") if len(pub) > 60 else pub
    except Exception as e:
        logger.warning("fetch_display_info: imprint query failed: %s", e)

    # Fetch first 3 subjects per record
    # Use a window function to limit subjects per record
    subjects_sql = f"""
        SELECT r.mms_id, s.value
        FROM records r
        LEFT JOIN subjects s ON s.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        AND s.value IS NOT NULL
    """

    try:
        cursor = conn.execute(subjects_sql, mms_ids)
        # Group subjects by mms_id and take first 3
        subjects_by_mms = {}
        for row in cursor.fetchall():
            mms_id = row[0]
            subject = row[1]
            if mms_id not in subjects_by_mms:
                subjects_by_mms[mms_id] = []
            if len(subjects_by_mms[mms_id]) < 3:
                # Truncate long subject strings
                subj_str = subject[:50] + "..." if len(subject) > 50 else subject
                subjects_by_mms[mms_id].append(subj_str)

        for mms_id, subjects in subjects_by_mms.items():
            if mms_id in result:
                result[mms_id]["subjects"] = subjects
    except Exception as e:
        logger.warning("fetch_display_info: subjects query failed: %s", e)

    # Fetch description from notes (prefer 520 summary, fallback to 500)
    # MARC 520 = Summary note, MARC 500 = General note
    notes_sql = f"""
        SELECT r.mms_id, n.value, n.tag
        FROM records r
        LEFT JOIN notes n ON n.record_id = r.id
        WHERE r.mms_id IN ({placeholders})
        AND n.tag IN ('520', '500')
        ORDER BY r.mms_id, CASE n.tag WHEN '520' THEN 1 ELSE 2 END
    """

    try:
        cursor = conn.execute(notes_sql, mms_ids)
        # Track which records already have descriptions (prefer 520)
        described_records = set()
        for row in cursor.fetchall():
            mms_id = row[0]
            note_value = row[1]
            if mms_id not in described_records and note_value:
                # Truncate long descriptions
                desc = note_value[:200] + "..." if len(note_value) > 200 else note_value
                result[mms_id]["description"] = desc
                described_records.add(mms_id)
    except Exception as e:
        logger.warning("fetch_display_info: notes query failed: %s", e)

    return result


def load_plan_from_file(plan_path: Path) -> QueryPlan:
    """Load and validate QueryPlan from JSON file.

    Args:
        plan_path: Path to plan.json file

    Returns:
        Validated QueryPlan

    Raises:
        FileNotFoundError: If plan file doesn't exist
        ValidationError: If plan JSON is invalid
    """
    with open(plan_path, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    return QueryPlan(**plan_data)


def _marc_source_from_provenance(row, default: str = "unknown") -> str:
    """Derive the MARC source label from the agents provenance JSON.

    The M3 agents table stores provenance as ``[{"source": "100[0]$a"}]`` —
    ``source`` is a string already encoding tag, occurrence, and subfield.
    Older data may carry the dict shape ``{"tag": "700", "occurrence": 1}``;
    both are supported (issue #43).
    """
    if "agent_provenance" not in row.keys() or not row["agent_provenance"]:
        return default
    try:
        provenance = json.loads(row["agent_provenance"])
        first_source = provenance[0].get("source")
        if isinstance(first_source, str) and first_source:
            return first_source
        if isinstance(first_source, dict):
            tag = first_source.get("tag", default)
            occ = first_source.get("occurrence", 0)
            return f"{tag}[{occ}]"
        return default
    except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
        return default


def _first_source_tag(row, default_tag: str) -> str:
    """Return the first MARC tag recorded in the imprint ``source_tags`` JSON.

    ``source_tags`` is stored as a JSON list, e.g. ``["264"]`` or, in older
    data, with the subfield already attached (``["260$b"]``). The first entry
    is returned verbatim; ``default_tag`` is used when the column is absent or
    unparseable.
    """
    if "source_tags" not in row.keys() or not row["source_tags"]:
        return default_tag
    try:
        tags = json.loads(row["source_tags"])
        if isinstance(tags, list) and tags:
            return str(tags[0])
        if isinstance(tags, str) and tags:
            return tags
        return default_tag
    except (json.JSONDecodeError, IndexError, TypeError):
        return default_tag


def _imprint_marc_source(row, subfield: str, default_tag: str) -> str:
    """Build the ``marc:<tag>$<subfield>`` label for an imprint-derived field.

    Subfield precision (issue #51a): place ``$a``, publisher ``$b``, date
    ``$c``. The tag is read from the row's ``source_tags`` (e.g. ``264``); if
    that tag already encodes a subfield (``264$b``) it is used as-is.
    """
    tag = _first_source_tag(row, default_tag)
    if "$" in tag:
        return tag
    return f"{tag}${subfield}"


def _clean_marc_source_string(raw, default: str) -> str:
    """Normalize a per-row MARC source value into a clean label string.

    Sources such as ``languages.source`` / ``subjects.source`` are stored as
    JSON-list strings (``["041$a"]``). Returning that verbatim leaks the list
    into the evidence string (issue #51b: ``marc:["041$a"]``). This collapses
    the value to the first element, accepts a plain string as-is, and falls
    back to ``default`` when empty or unparseable.
    """
    if raw is None or raw == "":
        return default
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list) and parsed:
                    return str(parsed[0])
                return default
            except json.JSONDecodeError:
                return default
        return stripped
    if isinstance(raw, list) and raw:
        return str(raw[0])
    return default


def _reread_fts_value(conn, row, table: str) -> Any:
    """Re-read the matched value for an FTS hit from its base table by mms_id.

    FTS5 filters (title/subject CONTAINS) match via an EXISTS subquery, so the
    matched value is not present on the result row and evidence collapses to
    ``value=None`` (issue #51d). Given the record's ``mms_id``, fetch the first
    base-table value for that record so the evidence carries a real, non-null
    value. Returns ``None`` if no connection/mms_id or no row is found.
    """
    if conn is None or "mms_id" not in row.keys() or not row["mms_id"]:
        return None
    try:
        cur = conn.execute(
            f"SELECT t.value FROM {table} t "
            "JOIN records r ON r.id = t.record_id "
            "WHERE r.mms_id = ? AND t.value IS NOT NULL "
            "ORDER BY t.id LIMIT 1",
            (row["mms_id"],),
        )
        fetched = cur.fetchone()
        if fetched is not None:
            return fetched[0]
    except sqlite3.Error:
        return None
    return None


def extract_evidence_for_filter(
    filter_obj,
    row: sqlite3.Row,
    field_prefix: str = "",
    conn: sqlite3.Connection | None = None,
) -> Evidence:
    """Extract evidence for a single filter from result row.

    Args:
        filter_obj: Filter from QueryPlan
        row: Result row from database
        field_prefix: Optional prefix for field names
        conn: Optional read connection used to re-read FTS-matched values
            (title/subject) from their base tables when the value is not on
            the result row (issue #51d).

    Returns:
        Evidence object
    """
    if filter_obj.field == FilterField.PUBLISHER:
        # Subfield precision (#51a): publisher comes from $b of the imprint tag.
        return Evidence(
            field="publisher_norm",
            value=row["publisher_norm"] if row["publisher_norm"] else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "LIKE",
            matched_against=filter_obj.value,
            source=f"db.imprints.publisher_norm (marc:{_imprint_marc_source(row, 'b', '260')})",
            confidence=row["publisher_confidence"] if "publisher_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.IMPRINT_PLACE:
        # Subfield precision (#51a): place comes from $a of the imprint tag.
        return Evidence(
            field="place_norm",
            value=row["place_norm"] if row["place_norm"] else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "LIKE",
            matched_against=filter_obj.value,
            source=f"db.imprints.place_norm (marc:{_imprint_marc_source(row, 'a', '260')})",
            confidence=row["place_confidence"] if "place_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.YEAR:
        # Subfield precision (#51a): date comes from $c of the imprint tag.
        date_start = row["date_start"] if "date_start" in row.keys() else None
        date_end = row["date_end"] if "date_end" in row.keys() else None

        return Evidence(
            field="date_range",
            value=f"{date_start}-{date_end}" if date_start and date_end else None,
            operator="OVERLAPS",
            matched_against=f"{filter_obj.start}-{filter_obj.end}",
            source=f"db.imprints.date_start/date_end (marc:{_imprint_marc_source(row, 'c', '260')})",
            confidence=row["date_confidence"] if "date_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.LANGUAGE:
        # Clean source string (#51b): language_source is stored as a JSON-list
        # string (["041$a"]); collapse it and default to 008 when absent.
        raw_lang_source = row["language_source"] if "language_source" in row.keys() else None
        lang_source = _clean_marc_source_string(raw_lang_source, "008")
        return Evidence(
            field="language_code",
            value=row["language_code"] if "language_code" in row.keys() else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "IN",
            matched_against=filter_obj.value,
            source=f"db.languages.code (marc:{lang_source})",
            confidence=None
        )

    elif filter_obj.field == FilterField.TITLE:
        # FTS match (#51d): title CONTAINS matches via an EXISTS subquery, so
        # title_value is absent from the row. Re-read it from the base table by
        # mms_id so the evidence value is non-null on a real match.
        title_val = row["title_value"] if "title_value" in row.keys() else None
        if title_val is None:
            title_val = _reread_fts_value(conn, row, "titles")
        return Evidence(
            field="title_value",
            value=title_val,
            operator="MATCH",
            matched_against=filter_obj.value,
            source="db.titles.value (FTS5)",
            confidence=None
        )

    elif filter_obj.field == FilterField.SUBJECT:
        # FTS match (#51d): subject CONTAINS matches via an EXISTS subquery, so
        # subject_value may be absent/null. Re-read it from the base table by
        # mms_id; fall back to the matched search term only as a last resort.
        subject_val = row["subject_value"] if "subject_value" in row.keys() else None
        if subject_val is None:
            subject_val = _reread_fts_value(conn, row, "subjects")
        if subject_val is None:
            subject_val = str(filter_obj.value)
        # Clean source string (#51b): subject_source is also a JSON-list string.
        subject_source = "db.subjects (FTS5)"
        if "subject_source" in row.keys() and row["subject_source"]:
            cleaned = _clean_marc_source_string(row["subject_source"], "")
            if cleaned:
                subject_source = f"db.subjects.value (marc:{cleaned})"
        return Evidence(
            field="subject_value",
            value=subject_val,
            operator="MATCH",
            matched_against=filter_obj.value,
            source=subject_source,
            confidence=None
        )

    elif filter_obj.field == FilterField.AGENT:
        # Derive MARC source tag from agent provenance (100=main entry, 700=added entry)
        agent_marc_source = _marc_source_from_provenance(row, default="100|700")
        # agent_raw is the aliased column name from the query
        agent_val = row["agent_raw"] if "agent_raw" in row.keys() else None
        return Evidence(
            field="agent_value",
            value=agent_val,
            operator="LIKE",
            matched_against=filter_obj.value,
            source=f"db.agents.agent_raw (marc:{agent_marc_source})",
            confidence=row["agent_confidence"] if "agent_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.AGENT_NORM:
        # Stage 5: Extract provenance from agent_provenance JSON
        marc_source = _marc_source_from_provenance(row)

        return Evidence(
            field="agent_norm",
            value=row["agent_norm"] if "agent_norm" in row.keys() else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "LIKE",
            matched_against=filter_obj.value,
            source=f"db.agents.agent_norm (marc:{marc_source})",
            confidence=row["agent_confidence"] if "agent_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.AGENT_ROLE:
        # Stage 5: Role filter evidence
        marc_source = _marc_source_from_provenance(row)

        return Evidence(
            field="role_norm",
            value=row["agent_role_norm"] if "agent_role_norm" in row.keys() else None,
            operator="=",
            matched_against=filter_obj.value,
            source=f"db.agents.role_norm (marc:{marc_source})",
            confidence=row["agent_role_confidence"] if "agent_role_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.AGENT_TYPE:
        # Stage 5: Agent type filter evidence
        marc_source = _marc_source_from_provenance(row)

        return Evidence(
            field="agent_type",
            value=row["agent_type"] if "agent_type" in row.keys() else None,
            operator="=",
            matched_against=filter_obj.value,
            source=f"db.agents.agent_type (marc:{marc_source})",
            confidence=None
        )

    elif filter_obj.field == FilterField.COUNTRY:
        # Real branch (#51c): country of publication derives from MARC 008/15-17.
        country_val = row["country_name"] if "country_name" in row.keys() else None
        return Evidence(
            field="country_name",
            value=country_val,
            operator="=" if filter_obj.op == FilterOp.EQUALS else (
                "IN" if filter_obj.op == FilterOp.IN else "LIKE"
            ),
            matched_against=filter_obj.value,
            source="db.imprints.country_name (marc:008)",
            confidence=None
        )

    elif filter_obj.field == FilterField.PHYSICAL_DESC:
        # Real branch (#51c): physical description is MARC 300. The matching
        # value is found via an EXISTS subquery (no FTS), so the row may not
        # carry it; fall back to the matched search term.
        phys_val = None
        if "physical_desc_value" in row.keys():
            phys_val = row["physical_desc_value"]
        if phys_val is None:
            phys_val = str(filter_obj.value)
        return Evidence(
            field="physical_desc",
            value=phys_val,
            operator="IN" if filter_obj.op == FilterOp.IN else "LIKE",
            matched_against=filter_obj.value,
            source="db.physical_descriptions.value (marc:300)",
            confidence=None
        )

    else:
        # Fallback for unknown filter types
        return Evidence(
            field=str(filter_obj.field),
            value="unknown",
            operator="unknown",
            matched_against=str(filter_obj.value),
            source="unknown"
        )


def build_match_rationale(plan: QueryPlan, row: sqlite3.Row) -> str:
    """Build deterministic match rationale string.

    Args:
        plan: QueryPlan with filters
        row: Result row from database

    Returns:
        Human-readable rationale string
    """
    parts = []

    for filter_obj in plan.filters:
        if filter_obj.field == FilterField.PUBLISHER:
            pub = row["publisher_norm"] if "publisher_norm" in row.keys() else "unknown"
            parts.append(f"publisher_norm='{pub}'")

        elif filter_obj.field == FilterField.IMPRINT_PLACE:
            place = row["place_norm"] if "place_norm" in row.keys() else "unknown"
            parts.append(f"place_norm='{place}'")

        elif filter_obj.field == FilterField.YEAR:
            date_start = row["date_start"] if "date_start" in row.keys() else "?"
            date_end = row["date_end"] if "date_end" in row.keys() else "?"
            parts.append(f"year_range={date_start}-{date_end} overlaps {filter_obj.start}-{filter_obj.end}")

        elif filter_obj.field == FilterField.LANGUAGE:
            lang = row["language_code"] if "language_code" in row.keys() else "unknown"
            parts.append(f"language={lang}")

        elif filter_obj.field == FilterField.TITLE:
            parts.append(f"title matches '{filter_obj.value}'")

        elif filter_obj.field == FilterField.SUBJECT:
            parts.append(f"subject matches '{filter_obj.value}'")

        elif filter_obj.field == FilterField.AGENT:
            agent = row["agent_raw"] if "agent_raw" in row.keys() else "unknown"
            parts.append(f"agent='{agent}'")

        elif filter_obj.field == FilterField.AGENT_NORM:
            agent_norm = row["agent_norm"] if "agent_norm" in row.keys() else "unknown"
            parts.append(f"agent_norm='{agent_norm}'")

        elif filter_obj.field == FilterField.AGENT_ROLE:
            role_norm = row["agent_role_norm"] if "agent_role_norm" in row.keys() else "unknown"
            parts.append(f"role_norm='{role_norm}'")

        elif filter_obj.field == FilterField.AGENT_TYPE:
            agent_type = row["agent_type"] if "agent_type" in row.keys() else "unknown"
            parts.append(f"agent_type='{agent_type}'")

    return " AND ".join(parts) if parts else "matched"


def should_retry_with_subject_hints(plan: QueryPlan, result_count: int) -> bool:
    """Check if query should retry with database subject hints.

    Retry when:
    1. Query returned zero results
    2. Plan has subject filters (in filters or soft_filters)
    3. Haven't already retried (check debug.retry_attempt)

    Args:
        plan: Executed QueryPlan
        result_count: Number of results from query

    Returns:
        True if should retry with subject hints
    """
    # Don't retry if we got results
    if result_count > 0:
        return False

    # Don't retry if already retried
    if plan.debug.get("retry_attempt", False):
        return False

    # Check if plan has subject filters
    has_subject_filter = any(
        f.field == FilterField.SUBJECT
        for f in (plan.filters + plan.soft_filters)
    )

    return has_subject_filter


def execute_plan(
    plan: QueryPlan,
    db_path: Path
) -> CandidateSet:
    """Execute QueryPlan and generate CandidateSet with evidence.

    Automatically retries with database subject hints if initial query with
    subject filters returns zero results.

    Args:
        plan: Validated QueryPlan
        db_path: Path to SQLite database

    Returns:
        CandidateSet with candidates and evidence
    """
    # Build SQL from plan
    sql, params = build_full_query(plan)

    # Connect to database
    conn = get_connection(db_path)

    try:
        # Execute query
        rows = fetch_candidates(conn, sql, params)

        # Check if retry needed
        if should_retry_with_subject_hints(plan, len(rows)):
            print("  ℹ️  No results found. Retrying with database subject hints...")

            # Get top subjects from database
            try:
                subject_hints = get_top_subjects(db_path, limit=100)

                # Retry compilation with hints
                new_plan = compile_query_with_subject_hints(
                    plan.query_text,
                    subject_hints,
                    plan
                )

                # Execute retry
                sql, params = build_full_query(new_plan)
                rows = fetch_candidates(conn, sql, params)

                # Use retried plan for evidence
                plan = new_plan

                if len(rows) > 0:
                    print(f"  ✓ Retry successful: Found {len(rows)} results with adjusted subject mapping")
                else:
                    print("  ⚠ Retry returned zero results")

            except Exception as e:
                # Log retry failure but don't crash
                print(f"  ⚠ Retry failed: {e}")
                # Continue with original zero results

        # Build candidates with evidence
        candidates = []
        for row in rows:
            # Extract evidence for each filter
            evidence_list = []
            for filter_obj in plan.filters:
                try:
                    evidence = extract_evidence_for_filter(filter_obj, row, conn=conn)
                    evidence_list.append(evidence)
                except Exception as e:
                    # Log and mark but don't fail on evidence extraction errors
                    logger.warning(
                        "Failed to extract evidence for %s: %s",
                        filter_obj.field, e,
                    )
                    evidence_list.append(Evidence(
                        field=str(filter_obj.field),
                        value=None,
                        operator="UNKNOWN",
                        matched_against=getattr(filter_obj, "value", None),
                        source="extraction_failed",
                        confidence=None,
                        extraction_error=str(e),
                    ))

            # Build match rationale
            rationale = build_match_rationale(plan, row)

            # Create candidate
            candidate = Candidate(
                record_id=row["mms_id"],
                match_rationale=rationale,
                evidence=evidence_list
            )
            candidates.append(candidate)

        # Fetch display info (all metadata) for all candidates
        if candidates:
            mms_ids = [c.record_id for c in candidates]
            display_info = fetch_display_info(conn, mms_ids)

            # Update candidates with all display fields
            for candidate in candidates:
                info = display_info.get(candidate.record_id, {})
                candidate.title = info.get("title")
                candidate.author = info.get("author")
                candidate.date_start = info.get("date_start")
                candidate.date_end = info.get("date_end")
                candidate.place_norm = info.get("place_norm")
                candidate.place_raw = info.get("place_raw")
                candidate.publisher = info.get("publisher")
                candidate.subjects = info.get("subjects", [])
                candidate.description = info.get("description")

        # Compute plan hash
        plan_hash = compute_plan_hash(plan)

        # Build CandidateSet
        candidate_set = CandidateSet(
            query_text=plan.query_text,
            plan_hash=plan_hash,
            sql=sql,
            sql_parameters=params,
            candidates=candidates,
            total_count=len(candidates)
        )

        return candidate_set

    finally:
        conn.close()


def write_sql_to_file(sql: str, output_path: Path) -> None:
    """Write SQL query to text file.

    Args:
        sql: SQL query string
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(sql)


def write_candidates_to_file(candidate_set: CandidateSet, output_path: Path) -> None:
    """Write CandidateSet to JSON file.

    Args:
        candidate_set: CandidateSet to write
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(candidate_set.model_dump(), f, indent=2, ensure_ascii=False)


def execute_plan_from_file(
    plan_path: Path,
    db_path: Path,
    output_dir: Path
) -> CandidateSet:
    """Execute plan from file and write all outputs.

    Args:
        plan_path: Path to plan.json
        db_path: Path to SQLite database
        output_dir: Directory to write outputs

    Returns:
        CandidateSet
    """
    # Load plan
    plan = load_plan_from_file(plan_path)

    # Execute
    candidate_set = execute_plan(plan, db_path)

    # Build SQL for output
    sql, _ = build_full_query(plan)

    # Write outputs
    write_sql_to_file(sql, output_dir / "sql.txt")
    write_candidates_to_file(candidate_set, output_dir / "candidates.json")

    return candidate_set
