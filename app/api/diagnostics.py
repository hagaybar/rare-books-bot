"""FastAPI router for diagnostic API endpoints (B5-B12).

Provides endpoints for the Query Debugger and Database Explorer screens:
- Query execution and run storage (B5)
- Query run history (B6)
- Candidate labeling (B7-B8)
- Gold set export and regression testing (B9-B10)
- Database table inspection (B11-B12)
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth_deps import require_role

from app.api.diagnostics_models import (
    ColumnInfo,
    GoldSetResponse,
    LabelDetail,
    LabelsRequest,
    LabelsResponse,
    QueryRunCandidate,
    QueryRunRequest,
    QueryRunResponse,
    QueryRunsResponse,
    QueryRunSummary,
    RegressionQueryResult,
    RegressionResponse,
    RunLabelsResponse,
    TableInfo,
    TableRowsResponse,
    TablesResponse,
)

router = APIRouter(
    prefix="/diagnostics",
    tags=["diagnostics"],
    dependencies=[Depends(require_role("full"))],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_TABLES = [
    "records",
    "imprints",
    "titles",
    "subjects",
    "agents",
    "languages",
    "notes",
    "physical_descriptions",
    "publisher_authorities",
    "publisher_variants",
    "authority_enrichment",
    "agent_authorities",
    "agent_aliases",
    "wikipedia_cache",
    "wikipedia_connections",
    "network_edges",
    "network_agents",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_bib_db_path() -> Path:
    """Resolve the bibliographic database path from environment."""
    return Path(
        os.environ.get("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db")
    )


def _get_qa_db_path() -> Path:
    """Resolve the QA database path."""
    return Path(os.environ.get("QA_DB_PATH", "data/qa/qa.db"))


def _ensure_qa_db(qa_path: Path) -> None:
    """Ensure the QA database exists with the required schema."""
    from scripts.qa.db import init_db
    init_db()


def _get_gold_set_path() -> Path:
    """Resolve the gold set JSON path."""
    return Path(os.environ.get("GOLD_SET_PATH", "data/qa/gold.json"))


# ---------------------------------------------------------------------------
# B5: POST /diagnostics/query-run
# ---------------------------------------------------------------------------


@router.post("/query-run", response_model=QueryRunResponse)
def run_query(request: QueryRunRequest):
    """Execute a query, store the run in QA DB, and return results.

    This endpoint:
    1. Executes the query via QueryService against bibliographic.db
    2. Stores the run metadata in the QA database (data/qa/qa.db)
    3. Returns the run ID, plan, SQL, candidates, and timing
    """
    from scripts.query import QueryService, QueryOptions

    bib_db = _get_bib_db_path()
    if not bib_db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bibliographic database not found: {bib_db}",
        )

    # Execute query
    try:
        service = QueryService(bib_db)
        options = QueryOptions(limit=request.limit)
        result = service.execute(request.query_text, options=options)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {exc}",
        )

    # Store run in QA DB
    _ensure_qa_db(_get_qa_db_path())
    from scripts.qa.db import insert_query_run

    try:
        run_id = insert_query_run(
            query_text=request.query_text,
            plan=result.query_plan,
            result=result.candidate_set,
            db_path=str(bib_db),
            status="OK",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store query run: {exc}",
        )

    # Build candidate list for response
    candidates = []
    for c in result.candidate_set.candidates:
        candidates.append(
            QueryRunCandidate(
                record_id=c.record_id,
                title=c.title,
                author=c.author,
                match_rationale=c.match_rationale,
                date_start=c.date_start,
                date_end=c.date_end,
                place_norm=c.place_norm,
                publisher=c.publisher,
                evidence=[e.model_dump() for e in c.evidence],
            )
        )

    return QueryRunResponse(
        run_id=run_id,
        query_text=request.query_text,
        plan=result.query_plan.model_dump(),
        sql=result.sql,
        candidates=candidates,
        total_count=result.candidate_set.total_count,
        execution_time_ms=result.execution_time_ms,
    )


# ---------------------------------------------------------------------------
# B6: GET /diagnostics/query-runs
# ---------------------------------------------------------------------------


@router.get("/query-runs", response_model=QueryRunsResponse)
def list_query_runs(
    limit: int = Query(20, ge=1, le=100, description="Max runs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List recent query runs from the QA database, paginated."""
    qa_path = _get_qa_db_path()
    if not qa_path.exists():
        return QueryRunsResponse(total=0, items=[])

    conn = sqlite3.connect(str(qa_path))
    conn.row_factory = sqlite3.Row

    try:
        # Get total count
        total_row = conn.execute("SELECT COUNT(*) as cnt FROM qa_queries").fetchone()
        total = total_row["cnt"] if total_row else 0

        # Get paginated runs
        cursor = conn.execute(
            """
            SELECT id, query_text, created_at, total_candidates
            FROM qa_queries
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        items = [
            QueryRunSummary(
                run_id=row["id"],
                query_text=row["query_text"],
                created_at=row["created_at"],
                candidate_count=row["total_candidates"],
            )
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()

    return QueryRunsResponse(total=total, items=items)


# ---------------------------------------------------------------------------
# B7: POST /diagnostics/labels
# ---------------------------------------------------------------------------


@router.post("/labels", response_model=LabelsResponse)
def save_labels(request: LabelsRequest):
    """Save TP/FP/FN/UNK labels for candidates in a query run."""
    _ensure_qa_db(_get_qa_db_path())
    from scripts.qa.db import upsert_label, get_query_by_id

    # Verify run exists
    run = get_query_by_id(request.run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Query run {request.run_id} not found",
        )

    saved = 0
    for item in request.labels:
        upsert_label(
            query_id=request.run_id,
            record_id=item.record_id,
            label=item.label,
            issue_tags=item.issue_tags if item.issue_tags else None,
        )
        saved += 1

    return LabelsResponse(saved_count=saved)


# ---------------------------------------------------------------------------
# B8: GET /diagnostics/labels/{run_id}
# ---------------------------------------------------------------------------


@router.get("/labels/{run_id}", response_model=RunLabelsResponse)
def get_labels(run_id: int):
    """Return all labels for a specific query run."""
    qa_path = _get_qa_db_path()
    if not qa_path.exists():
        return RunLabelsResponse(labels=[])

    from scripts.qa.db import get_labels_for_query

    raw_labels = get_labels_for_query(run_id)
    labels = []
    for lbl in raw_labels:
        issue_tags_raw = lbl.get("issue_tags")
        if isinstance(issue_tags_raw, str):
            try:
                issue_tags = json.loads(issue_tags_raw)
            except (json.JSONDecodeError, TypeError):
                issue_tags = []
        elif isinstance(issue_tags_raw, list):
            issue_tags = issue_tags_raw
        else:
            issue_tags = []

        labels.append(
            LabelDetail(
                record_id=lbl["record_id"],
                label=lbl["label"],
                issue_tags=issue_tags,
                created_at=lbl["created_at"],
            )
        )

    return RunLabelsResponse(labels=labels)


# ---------------------------------------------------------------------------
# B9: GET /diagnostics/gold-set/export
# ---------------------------------------------------------------------------


@router.get("/gold-set/export", response_model=GoldSetResponse)
def export_gold_set():
    """Export the current gold set as JSON.

    Reads from data/qa/gold.json if it exists, otherwise builds
    from the qa_query_gold table in the QA database.
    """
    gold_path = _get_gold_set_path()

    # Try reading from file first
    if gold_path.exists():
        try:
            data = json.loads(gold_path.read_text())
            return GoldSetResponse(
                version=data.get("version", "1.0"),
                exported_at=data.get("exported_at", ""),
                queries=data.get("queries", []),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse gold.json: {exc}",
            )

    # Fall back to building from QA DB
    qa_path = _get_qa_db_path()
    if not qa_path.exists():
        return GoldSetResponse(
            version="1.0",
            exported_at=datetime.now().isoformat(),
            queries=[],
        )

    from scripts.qa.db import export_gold_set as db_export_gold_set

    gold_data = db_export_gold_set()
    return GoldSetResponse(
        version=gold_data.get("version", "1.0"),
        exported_at=gold_data.get("exported_at", ""),
        queries=gold_data.get("queries", []),
    )


# ---------------------------------------------------------------------------
# B10: POST /diagnostics/gold-set/regression
# ---------------------------------------------------------------------------


@router.post("/gold-set/regression", response_model=RegressionResponse)
def run_regression():
    """Run regression tests against the gold set.

    Loads the gold set, executes each query against bibliographic.db,
    and compares results to expected includes/excludes.
    """
    bib_db = _get_bib_db_path()
    if not bib_db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bibliographic database not found: {bib_db}",
        )

    # Load gold set
    gold_path = _get_gold_set_path()
    if not gold_path.exists():
        # Try building from QA DB
        qa_path = _get_qa_db_path()
        if not qa_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No gold set found (neither gold.json nor QA database)",
            )
        from scripts.qa.db import export_gold_set as db_export_gold_set
        gold_data = db_export_gold_set()
    else:
        try:
            gold_data = json.loads(gold_path.read_text())
        except (json.JSONDecodeError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to parse gold.json: {exc}",
            )

    queries = gold_data.get("queries", [])
    if not queries:
        return RegressionResponse(
            total_queries=0, passed=0, failed=0, results=[]
        )

    from scripts.query.compile import compile_query
    from scripts.query.execute import execute_plan

    passed = 0
    failed = 0
    results: List[RegressionQueryResult] = []

    for query_spec in queries:
        query_text = query_spec.get("query_text", "")
        expected_includes = set(query_spec.get("expected_includes", []))
        expected_excludes = set(query_spec.get("expected_excludes", []))

        try:
            plan = compile_query(query_text)
            result = execute_plan(plan, bib_db)
            actual_ids = {c.record_id for c in result.candidates}

            missing = list(expected_includes - actual_ids)
            unexpected = list(expected_excludes & actual_ids)

            if missing or unexpected:
                query_status = "fail"
                failed += 1
            else:
                query_status = "pass"
                passed += 1

            results.append(
                RegressionQueryResult(
                    query_text=query_text,
                    status=query_status,
                    expected_includes=list(expected_includes),
                    actual_includes=list(actual_ids),
                    missing=missing,
                    unexpected=unexpected,
                )
            )
        except Exception as exc:
            failed += 1
            results.append(
                RegressionQueryResult(
                    query_text=query_text,
                    status="error",
                    expected_includes=list(expected_includes),
                    error=str(exc),
                )
            )

    return RegressionResponse(
        total_queries=len(queries),
        passed=passed,
        failed=failed,
        results=results,
    )


# ---------------------------------------------------------------------------
# B11: GET /diagnostics/tables
# ---------------------------------------------------------------------------


@router.get("/tables", response_model=TablesResponse)
def list_tables():
    """List all tables in bibliographic.db with row counts and column info."""
    bib_db = _get_bib_db_path()
    if not bib_db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bibliographic database not found: {bib_db}",
        )

    conn = sqlite3.connect(str(bib_db))
    try:
        # Get table names
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        # Filter out FTS internal tables and sqlite internals
        FTS_SUFFIXES = ("_fts", "_fts_config", "_fts_data", "_fts_docsize", "_fts_idx")
        SKIP_TABLES = {"sqlite_sequence"}
        table_names = [
            row[0]
            for row in cursor.fetchall()
            if not any(row[0].endswith(s) for s in FTS_SUFFIXES)
            and row[0] not in SKIP_TABLES
        ]

        tables = []
        for name in table_names:
            # Get row count
            count_row = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
            row_count = count_row[0] if count_row else 0

            # Get column info via PRAGMA
            col_cursor = conn.execute(f'PRAGMA table_info("{name}")')
            columns = [
                ColumnInfo(name=col[1], type=col[2] or "TEXT")
                for col in col_cursor.fetchall()
            ]

            tables.append(
                TableInfo(name=name, row_count=row_count, columns=columns)
            )
    finally:
        conn.close()

    return TablesResponse(tables=tables)


# ---------------------------------------------------------------------------
# B12: GET /diagnostics/tables/{table_name}/rows
# ---------------------------------------------------------------------------


@router.get("/tables/{table_name}/rows", response_model=TableRowsResponse)
def get_table_rows(
    table_name: str,
    limit: int = Query(50, ge=1, le=500, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    search: str = Query("", description="Search term to filter rows"),
):
    """Paginated row browsing with optional text search.

    IMPORTANT: table_name is validated against an allowlist to prevent
    SQL injection.
    """
    # SQL injection prevention: validate table name against allowlist
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Table '{table_name}' is not allowed. "
                f"Allowed tables: {', '.join(ALLOWED_TABLES)}"
            ),
        )

    bib_db = _get_bib_db_path()
    if not bib_db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Bibliographic database not found: {bib_db}",
        )

    conn = sqlite3.connect(str(bib_db))
    conn.row_factory = sqlite3.Row

    try:
        # Get column info to identify text columns for search
        col_cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
        columns = col_cursor.fetchall()
        text_columns = [
            col[1]
            for col in columns
            if (col[2] or "").upper() in ("TEXT", "VARCHAR", "CHAR", "CLOB", "")
        ]

        if search and text_columns:
            # Build WHERE clause: search across all text columns
            conditions = " OR ".join(
                f'"{col}" LIKE ?' for col in text_columns
            )
            search_param = f"%{search}%"
            params = [search_param] * len(text_columns)

            # Total count with search
            count_sql = f'SELECT COUNT(*) FROM "{table_name}" WHERE {conditions}'
            total_row = conn.execute(count_sql, params).fetchone()
            total = total_row[0] if total_row else 0

            # Paginated rows with search
            rows_sql = (
                f'SELECT * FROM "{table_name}" WHERE {conditions} '
                f"LIMIT ? OFFSET ?"
            )
            cursor = conn.execute(rows_sql, params + [limit, offset])
        else:
            # No search: simple pagination
            total_row = conn.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()
            total = total_row[0] if total_row else 0

            cursor = conn.execute(
                f'SELECT * FROM "{table_name}" LIMIT ? OFFSET ?',
                (limit, offset),
            )

        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    return TableRowsResponse(
        table_name=table_name,
        total=total,
        limit=limit,
        offset=offset,
        rows=rows,
    )
