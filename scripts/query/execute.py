"""Query executor - QueryPlan → SQL → CandidateSet with Evidence.

Executes validated QueryPlan against M3 database and generates
CandidateSet with per-record evidence and match rationale.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from scripts.schemas import QueryPlan, CandidateSet, Candidate, Evidence, FilterField, FilterOp
from scripts.query.db_adapter import build_full_query, get_connection, fetch_candidates
from scripts.query.compile import compute_plan_hash
from scripts.query.subject_hints import get_top_subjects
from scripts.query.llm_compiler import compile_query_with_subject_hints


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


def extract_evidence_for_filter(
    filter_obj,
    row: sqlite3.Row,
    field_prefix: str = ""
) -> Evidence:
    """Extract evidence for a single filter from result row.

    Args:
        filter_obj: Filter from QueryPlan
        row: Result row from database
        field_prefix: Optional prefix for field names

    Returns:
        Evidence object
    """
    if filter_obj.field == FilterField.PUBLISHER:
        # Parse source tags if available
        source_tags = "unknown"
        if "source_tags" in row.keys() and row["source_tags"]:
            try:
                tags = json.loads(row["source_tags"])
                source_tags = tags[0] if tags else "unknown"
            except (json.JSONDecodeError, IndexError, TypeError):
                source_tags = "unknown"

        return Evidence(
            field="publisher_norm",
            value=row["publisher_norm"] if row["publisher_norm"] else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "LIKE",
            matched_against=filter_obj.value,
            source=f"db.imprints.publisher_norm (marc:{source_tags})",
            confidence=row["publisher_confidence"] if "publisher_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.IMPRINT_PLACE:
        source_tags = "unknown"
        if "source_tags" in row.keys() and row["source_tags"]:
            try:
                tags = json.loads(row["source_tags"])
                source_tags = tags[0] if tags else "unknown"
            except (json.JSONDecodeError, IndexError, TypeError):
                source_tags = "unknown"

        return Evidence(
            field="place_norm",
            value=row["place_norm"] if row["place_norm"] else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "LIKE",
            matched_against=filter_obj.value,
            source=f"db.imprints.place_norm (marc:{source_tags})",
            confidence=row["place_confidence"] if "place_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.YEAR:
        source_tags = "unknown"
        if "source_tags" in row.keys() and row["source_tags"]:
            try:
                tags = json.loads(row["source_tags"])
                source_tags = tags[0] if tags else "unknown"
            except (json.JSONDecodeError, IndexError, TypeError):
                source_tags = "unknown"

        date_start = row["date_start"] if "date_start" in row.keys() else None
        date_end = row["date_end"] if "date_end" in row.keys() else None

        return Evidence(
            field="date_range",
            value=f"{date_start}-{date_end}" if date_start and date_end else None,
            operator="OVERLAPS",
            matched_against=f"{filter_obj.start}-{filter_obj.end}",
            source=f"db.imprints.date_start/date_end (marc:{source_tags})",
            confidence=row["date_confidence"] if "date_confidence" in row.keys() else None
        )

    elif filter_obj.field == FilterField.LANGUAGE:
        lang_source = row["language_source"] if "language_source" in row.keys() else "unknown"
        return Evidence(
            field="language_code",
            value=row["language_code"] if "language_code" in row.keys() else None,
            operator="=" if filter_obj.op == FilterOp.EQUALS else "IN",
            matched_against=filter_obj.value,
            source=f"db.languages.code (marc:{lang_source})",
            confidence=None
        )

    elif filter_obj.field == FilterField.TITLE:
        return Evidence(
            field="title_value",
            value=row["title_value"] if "title_value" in row.keys() else None,
            operator="MATCH",
            matched_against=filter_obj.value,
            source=f"db.titles.value (FTS5)",
            confidence=None
        )

    elif filter_obj.field == FilterField.SUBJECT:
        return Evidence(
            field="subject_value",
            value=row["subject_value"] if "subject_value" in row.keys() else None,
            operator="MATCH",
            matched_against=filter_obj.value,
            source=f"db.subjects.value (FTS5)",
            confidence=None
        )

    elif filter_obj.field == FilterField.AGENT:
        return Evidence(
            field="agent_value",
            value=row["agent_value"] if "agent_value" in row.keys() else None,
            operator="LIKE",
            matched_against=filter_obj.value,
            source=f"db.agents.value",
            confidence=None
        )

    elif filter_obj.field == FilterField.AGENT_NORM:
        # Stage 5: Extract provenance from agent_provenance JSON
        marc_source = "unknown"
        if "agent_provenance" in row.keys() and row["agent_provenance"]:
            try:
                provenance = json.loads(row["agent_provenance"])
                if provenance and len(provenance) > 0:
                    # Get first source from provenance array
                    first_source = provenance[0].get("source", {})
                    tag = first_source.get("tag", "unknown")
                    occ = first_source.get("occurrence", 0)
                    marc_source = f"{tag}[{occ}]"
            except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
                marc_source = "unknown"

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
        marc_source = "unknown"
        if "agent_provenance" in row.keys() and row["agent_provenance"]:
            try:
                provenance = json.loads(row["agent_provenance"])
                if provenance and len(provenance) > 0:
                    first_source = provenance[0].get("source", {})
                    tag = first_source.get("tag", "unknown")
                    occ = first_source.get("occurrence", 0)
                    marc_source = f"{tag}[{occ}]"
            except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
                marc_source = "unknown"

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
        marc_source = "unknown"
        if "agent_provenance" in row.keys() and row["agent_provenance"]:
            try:
                provenance = json.loads(row["agent_provenance"])
                if provenance and len(provenance) > 0:
                    first_source = provenance[0].get("source", {})
                    tag = first_source.get("tag", "unknown")
                    occ = first_source.get("occurrence", 0)
                    marc_source = f"{tag}[{occ}]"
            except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
                marc_source = "unknown"

        return Evidence(
            field="agent_type",
            value=row["agent_type"] if "agent_type" in row.keys() else None,
            operator="=",
            matched_against=filter_obj.value,
            source=f"db.agents.agent_type (marc:{marc_source})",
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
            agent = row["agent_value"] if "agent_value" in row.keys() else "unknown"
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
                    evidence = extract_evidence_for_filter(filter_obj, row)
                    evidence_list.append(evidence)
                except Exception as e:
                    # Log but don't fail on evidence extraction errors
                    print(f"Warning: Failed to extract evidence for {filter_obj.field}: {e}")

            # Build match rationale
            rationale = build_match_rationale(plan, row)

            # Create candidate
            candidate = Candidate(
                record_id=row["mms_id"],
                match_rationale=rationale,
                evidence=evidence_list
            )
            candidates.append(candidate)

        # Compute plan hash
        plan_hash = compute_plan_hash(plan)

        # Build CandidateSet
        candidate_set = CandidateSet(
            query_text=plan.query_text,
            plan_hash=plan_hash,
            sql=sql,
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
