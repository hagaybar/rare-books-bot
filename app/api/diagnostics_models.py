"""Pydantic request/response models for diagnostic API endpoints (B5-B12).

These models define the API contract for the /diagnostics/* routes,
supporting query debugging, labeling, gold set management, and database
exploration.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# B5: POST /diagnostics/query-run
# ---------------------------------------------------------------------------


class QueryRunRequest(BaseModel):
    """Request body for executing and storing a query run."""

    query_text: str = Field(..., min_length=1, description="Natural language query")
    limit: int = Field(50, ge=1, le=500, description="Max candidates to return")


class QueryRunCandidate(BaseModel):
    """Minimal candidate representation for query run results."""

    record_id: str
    title: Optional[str] = None
    author: Optional[str] = None
    match_rationale: str = ""
    date_start: Optional[int] = None
    date_end: Optional[int] = None
    place_norm: Optional[str] = None
    publisher: Optional[str] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)


class QueryRunResponse(BaseModel):
    """Response from executing and storing a query run."""

    run_id: int = Field(..., description="QA database query ID")
    query_text: str
    plan: Dict[str, Any] = Field(default_factory=dict, description="QueryPlan as dict")
    sql: str = Field("", description="Generated SQL")
    candidates: List[QueryRunCandidate] = Field(default_factory=list)
    total_count: int = 0
    execution_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# B6: GET /diagnostics/query-runs
# ---------------------------------------------------------------------------


class QueryRunSummary(BaseModel):
    """Summary of a stored query run for listing."""

    run_id: int
    query_text: str
    created_at: str
    candidate_count: int


class QueryRunsResponse(BaseModel):
    """Paginated list of query runs."""

    total: int
    items: List[QueryRunSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# B7: POST /diagnostics/labels
# ---------------------------------------------------------------------------


class LabelItem(BaseModel):
    """A single label for a candidate record."""

    record_id: str
    label: str = Field(..., pattern="^(TP|FP|FN|UNK)$", description="TP, FP, FN, or UNK")
    issue_tags: List[str] = Field(default_factory=list)


class LabelsRequest(BaseModel):
    """Request body for saving candidate labels."""

    run_id: int = Field(..., description="QA query run ID")
    labels: List[LabelItem] = Field(..., min_length=1)


class LabelsResponse(BaseModel):
    """Response from saving labels."""

    saved_count: int


# ---------------------------------------------------------------------------
# B8: GET /diagnostics/labels/{run_id}
# ---------------------------------------------------------------------------


class LabelDetail(BaseModel):
    """A single stored label with metadata."""

    record_id: str
    label: str
    issue_tags: List[str] = Field(default_factory=list)
    created_at: str


class RunLabelsResponse(BaseModel):
    """All labels for a specific run."""

    labels: List[LabelDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# B9: GET /diagnostics/gold-set/export
# ---------------------------------------------------------------------------


class GoldSetResponse(BaseModel):
    """Exported gold set."""

    version: str = "1.0"
    exported_at: str = ""
    queries: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# B10: POST /diagnostics/gold-set/regression
# ---------------------------------------------------------------------------


class RegressionQueryResult(BaseModel):
    """Result of a single query in the regression test."""

    query_text: str
    status: str = Field(..., description="pass, fail, or error")
    expected_includes: List[str] = Field(default_factory=list)
    actual_includes: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    unexpected: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class RegressionResponse(BaseModel):
    """Full regression test results."""

    total_queries: int
    passed: int
    failed: int
    results: List[RegressionQueryResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# B11: GET /diagnostics/tables
# ---------------------------------------------------------------------------


class ColumnInfo(BaseModel):
    """Column metadata from PRAGMA table_info."""

    name: str
    type: str


class TableInfo(BaseModel):
    """Metadata about a single database table."""

    name: str
    row_count: int
    columns: List[ColumnInfo] = Field(default_factory=list)


class TablesResponse(BaseModel):
    """List of all tables with metadata."""

    tables: List[TableInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# B12: GET /diagnostics/tables/{table_name}/rows
# ---------------------------------------------------------------------------


class TableRowsResponse(BaseModel):
    """Paginated rows from a database table."""

    table_name: str
    total: int
    limit: int
    offset: int
    rows: List[Dict[str, Any]] = Field(default_factory=list)
