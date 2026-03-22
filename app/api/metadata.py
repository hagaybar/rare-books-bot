"""FastAPI router for metadata quality endpoints.

Provides endpoints for inspecting normalization coverage, identifying
low-confidence records, viewing unmapped values, method distributions,
and gap clusters across bibliographic metadata fields.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status

from app.api.metadata_models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentClusterSummary,
    AgentProposal,
    BatchCorrectionRequest,
    BatchCorrectionResponse,
    BatchCorrectionResult,
    ClusterResponse,
    ClusterValueResponse,
    CorrectionHistoryEntry,
    CorrectionHistoryResponse,
    CorrectionRequest,
    CorrectionResponse,
    CoverageResponse,
    ConfidenceBandResponse,
    FieldCoverageResponse,
    FlaggedItemResponse,
    IssueRecord,
    IssuesResponse,
    MethodBreakdownResponse,
    MethodDistribution,
    PrimoUrlEntry,
    PrimoUrlRequest,
    PrimoUrlResponse,
    PublisherAuthorityListResponse,
    PublisherAuthorityResponse,
    PublisherVariantResponse,
    UnmappedValue,
)
from scripts.metadata.audit import (
    CoverageReport,
    FieldCoverage,
    generate_coverage_report,
)
from scripts.metadata.agent_harness import AgentHarness, ProposedMapping
from scripts.metadata.agents.date_agent import DateAgent
from scripts.metadata.agents.name_agent import NameAgent
from scripts.metadata.agents.place_agent import PlaceAgent
from scripts.metadata.agents.publisher_agent import PublisherAgent
from scripts.metadata.clustering import (
    Cluster,
    cluster_all_gaps,
    cluster_field_gaps,
)
from scripts.metadata.interaction_logger import interaction_logger

router = APIRouter(prefix="/metadata", tags=["metadata"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MetadataField(str, Enum):
    """Allowed metadata field names for query parameters."""

    date = "date"
    place = "place"
    publisher = "publisher"
    agent = "agent"


def _get_db_path() -> Path:
    """Resolve the bibliographic database path from environment."""
    return Path(
        os.environ.get("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db")
    )


def _field_coverage_to_response(fc: FieldCoverage) -> FieldCoverageResponse:
    """Convert a dataclass FieldCoverage to its Pydantic response model."""
    return FieldCoverageResponse(
        total_records=fc.total_records,
        non_null_count=fc.non_null_count,
        null_count=fc.null_count,
        confidence_distribution=[
            ConfidenceBandResponse(
                band_label=b.band_label,
                lower=b.lower,
                upper=b.upper,
                count=b.count,
            )
            for b in fc.confidence_distribution
        ],
        method_distribution=[
            MethodBreakdownResponse(method=m.method, count=m.count)
            for m in fc.method_distribution
        ],
        flagged_items=[
            FlaggedItemResponse(
                raw_value=item.raw_value,
                norm_value=item.norm_value,
                confidence=item.confidence,
                method=item.method,
                frequency=item.frequency,
            )
            for item in fc.flagged_items
        ],
    )


def _report_to_response(report: CoverageReport) -> CoverageResponse:
    """Convert the full CoverageReport dataclass to a Pydantic response."""
    return CoverageResponse(
        date_coverage=_field_coverage_to_response(report.date_coverage),
        place_coverage=_field_coverage_to_response(report.place_coverage),
        publisher_coverage=_field_coverage_to_response(report.publisher_coverage),
        agent_name_coverage=_field_coverage_to_response(
            report.agent_name_coverage
        ),
        agent_role_coverage=_field_coverage_to_response(
            report.agent_role_coverage
        ),
        total_imprint_rows=report.total_imprint_rows,
        total_agent_rows=report.total_agent_rows,
    )


def _cluster_to_response(cluster: Cluster) -> ClusterResponse:
    """Convert a dataclass Cluster to its Pydantic response model."""
    return ClusterResponse(
        cluster_id=cluster.cluster_id,
        field=cluster.field,
        cluster_type=cluster.cluster_type,
        values=[
            ClusterValueResponse(
                raw_value=v.raw_value,
                frequency=v.frequency,
                confidence=v.confidence,
                method=v.method,
            )
            for v in cluster.values
        ],
        proposed_canonical=cluster.proposed_canonical,
        evidence=cluster.evidence,
        priority_score=cluster.priority_score,
        total_records_affected=cluster.total_records_affected,
    )


# SQL column mappings per field for the issues endpoint.
# Each entry: (table, raw_col, norm_col, confidence_col, method_col)
_FIELD_COLUMN_MAP = {
    "date": (
        "imprints", "date_raw",
        "date_start", "date_confidence", "date_method",
    ),
    "place": (
        "imprints", "place_raw",
        "place_norm", "place_confidence", "place_method",
    ),
    "publisher": (
        "imprints", "publisher_raw",
        "publisher_norm", "publisher_confidence", "publisher_method",
    ),
    "agent": (
        "agents", "agent_raw",
        "agent_norm", "agent_confidence", "agent_method",
    ),
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/coverage",
    response_model=CoverageResponse,
    summary="Overall coverage stats per field",
)
async def get_coverage() -> CoverageResponse:
    """Return overall normalization coverage statistics per field."""
    db = _get_db_path()
    try:
        report = generate_coverage_report(db)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db}",
        )
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error generating coverage report: {exc}",
        )

    return _report_to_response(report)


@router.get(
    "/issues",
    response_model=IssuesResponse,
    summary="Records with low-confidence normalizations",
)
async def get_issues(
    field: MetadataField = Query(..., description="Metadata field to inspect"),
    max_confidence: float = Query(
        0.8, ge=0.0, le=1.0, description="Maximum confidence threshold"
    ),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> IssuesResponse:
    """Return records whose normalization confidence is at or below the threshold.

    Results are paginated and include the raw value, normalized value,
    confidence score, normalization method, and MMS ID.
    """
    field_str = field.value
    if field_str not in _FIELD_COLUMN_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown field: {field_str}",
        )

    table, raw_col, norm_col, conf_col, method_col = _FIELD_COLUMN_MAP[field_str]
    db = _get_db_path()

    try:
        conn = sqlite3.connect(str(db))

        # Total count for pagination metadata
        count_sql = (
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {conf_col} IS NOT NULL AND {conf_col} <= ?"
        )
        total = conn.execute(count_sql, (max_confidence,)).fetchone()[0]

        # Fetch the page — JOIN with records to get mms_id
        data_sql = (
            f"SELECT r.mms_id, t.{raw_col}, t.{norm_col}, t.{conf_col}, t.{method_col} "
            f"FROM {table} t "
            f"JOIN records r ON t.record_id = r.id "
            f"WHERE t.{conf_col} IS NOT NULL AND t.{conf_col} <= ? "
            f"ORDER BY t.{conf_col} ASC "
            f"LIMIT ? OFFSET ?"
        )
        rows = conn.execute(data_sql, (max_confidence, limit, offset)).fetchall()
        conn.close()
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db}",
        )
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error querying issues: {exc}",
        )

    items = [
        IssueRecord(
            mms_id=str(row[0]) if row[0] is not None else "",
            raw_value=str(row[1]) if row[1] is not None else "",
            norm_value=str(row[2]) if row[2] is not None else None,
            confidence=float(row[3]) if row[3] is not None else 0.0,
            method=str(row[4]) if row[4] is not None else None,
        )
        for row in rows
    ]

    return IssuesResponse(
        field=field_str,
        max_confidence=max_confidence,
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )


@router.get(
    "/unmapped",
    response_model=List[UnmappedValue],
    summary="Raw values without canonical mappings",
)
async def get_unmapped(
    field: MetadataField = Query(..., description="Metadata field to inspect"),
    sort: str = Query("frequency", description="Sort order (frequency)"),
) -> List[UnmappedValue]:
    """Return raw values that do not map to any canonical form.

    Uses the flagged_items from the audit module's coverage report
    for the specified field. Values are sorted by frequency (descending).
    """
    db = _get_db_path()
    try:
        report = generate_coverage_report(db)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db}",
        )
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error fetching unmapped values: {exc}",
        )

    field_str = field.value
    coverage_map = {
        "date": report.date_coverage,
        "place": report.place_coverage,
        "publisher": report.publisher_coverage,
        "agent": report.agent_name_coverage,
    }
    fc = coverage_map.get(field_str)
    if fc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown field: {field_str}",
        )

    items = [
        UnmappedValue(
            raw_value=item.raw_value,
            frequency=item.frequency,
            confidence=item.confidence,
            method=item.method,
        )
        for item in fc.flagged_items
    ]

    # Sort by frequency descending (default and only supported sort)
    items.sort(key=lambda v: v.frequency, reverse=True)

    return items


@router.get(
    "/methods",
    response_model=List[MethodDistribution],
    summary="Distribution of normalization methods",
)
async def get_methods(
    field: MetadataField = Query(..., description="Metadata field to inspect"),
) -> List[MethodDistribution]:
    """Return the distribution of normalization methods for a field.

    Shows each method name, its count, and percentage of total records.
    """
    db = _get_db_path()
    try:
        report = generate_coverage_report(db)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db}",
        )
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error fetching method distribution: {exc}",
        )

    field_str = field.value
    coverage_map = {
        "date": report.date_coverage,
        "place": report.place_coverage,
        "publisher": report.publisher_coverage,
        "agent": report.agent_name_coverage,
    }
    fc = coverage_map.get(field_str)
    if fc is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown field: {field_str}",
        )

    total = fc.total_records if fc.total_records > 0 else 1  # avoid division by zero

    return [
        MethodDistribution(
            method=m.method,
            count=m.count,
            percentage=round(m.count / total * 100, 2),
        )
        for m in fc.method_distribution
    ]


@router.get(
    "/clusters",
    response_model=List[ClusterResponse],
    summary="Gap clusters for review",
)
async def get_clusters(
    field: Optional[MetadataField] = Query(
        None, description="Metadata field (omit for all fields)"
    ),
) -> List[ClusterResponse]:
    """Return gap clusters from the clustering module.

    Clusters group related low-confidence or unmapped values for batch review.
    If ``field`` is omitted, clusters for all fields are returned.
    Results are sorted by priority_score (descending).
    """
    db = _get_db_path()
    try:
        report = generate_coverage_report(db)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db}",
        )
    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error generating clusters: {exc}",
        )

    if field is not None:
        # Single field
        field_str = field.value
        coverage_map = {
            "date": report.date_coverage,
            "place": report.place_coverage,
            "publisher": report.publisher_coverage,
            "agent": report.agent_name_coverage,
        }
        fc = coverage_map.get(field_str)
        if fc is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown field: {field_str}",
            )
        # For agent, combine name and role flagged items
        if field_str == "agent":
            flagged = (
                report.agent_name_coverage.flagged_items
                + report.agent_role_coverage.flagged_items
            )
        else:
            flagged = fc.flagged_items

        clusters = cluster_field_gaps(
            field=field_str,
            flagged_items=flagged,
        )
    else:
        # All fields
        all_clusters_map = cluster_all_gaps(report=report)
        clusters = []
        for field_clusters in all_clusters_map.values():
            clusters.extend(field_clusters)
        # Sort combined results by priority
        clusters.sort(key=lambda c: c.priority_score, reverse=True)

    return [_cluster_to_response(c) for c in clusters]


# ---------------------------------------------------------------------------
# Correction helpers
# ---------------------------------------------------------------------------

# Alias map file paths per field, relative to project root.
_ALIAS_MAP_PATHS = {
    "place": Path("data/normalization/place_aliases/place_alias_map.json"),
    "publisher": Path("data/normalization/publisher_aliases/publisher_alias_map.json"),
    "agent": Path("data/normalization/agent_aliases/agent_alias_map.json"),
}

# Review log path.
_REVIEW_LOG_PATH = Path("data/metadata/review_log.jsonl")

# SQL query templates for counting affected records per field.
# Each maps to (table, raw_col, confidence_col).
_AFFECTED_QUERY_MAP = {
    "place": ("imprints", "place_raw", "place_confidence"),
    "publisher": ("imprints", "publisher_raw", "publisher_confidence"),
    "agent": ("agents", "agent_raw", "agent_confidence"),
}


def _load_alias_map(path: Path) -> dict:
    """Load an alias map JSON file, returning empty dict if missing."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_alias_map_atomic(path: Path, alias_map: dict) -> None:
    """Write alias map to disk atomically (write .tmp then os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(alias_map, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)


def _count_affected_records(field: str, raw_value: str, db_path: Path) -> int:
    """Count records affected by a correction (low-confidence matches)."""
    if field not in _AFFECTED_QUERY_MAP:
        return 0
    table, raw_col, conf_col = _AFFECTED_QUERY_MAP[field]
    try:
        conn = sqlite3.connect(str(db_path))
        sql = (
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {raw_col} = ? AND ({conf_col} IS NULL OR {conf_col} <= 0.80)"
        )
        count = conn.execute(sql, (raw_value,)).fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _append_review_log(entry: dict) -> None:
    """Append a single entry to the review log JSONL file."""
    _REVIEW_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_REVIEW_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _apply_single_correction(
    req: CorrectionRequest, db_path: Path
) -> tuple:
    """Apply a single correction. Returns (success, records_affected, error_msg)."""
    field = req.field
    if field not in _ALIAS_MAP_PATHS:
        return False, 0, f"Unknown field: {field}. Must be one of: place, publisher, agent"

    alias_path = _ALIAS_MAP_PATHS[field]
    alias_map = _load_alias_map(alias_path)

    # Check for conflicts
    if req.raw_value in alias_map:
        existing = alias_map[req.raw_value]
        if existing != req.canonical_value:
            return (
                False,
                0,
                f"Conflict: raw_value '{req.raw_value}' already maps to "
                f"'{existing}', cannot remap to '{req.canonical_value}'",
            )
        # Same mapping already exists - treat as success, no-op
        records_affected = _count_affected_records(field, req.raw_value, db_path)
        return True, records_affected, None

    # Add the mapping
    alias_map[req.raw_value] = req.canonical_value
    _save_alias_map_atomic(alias_path, alias_map)

    # Count affected records
    records_affected = _count_affected_records(field, req.raw_value, db_path)

    # Append to review log
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "field": field,
        "raw_value": req.raw_value,
        "canonical_value": req.canonical_value,
        "evidence": req.evidence,
        "source": req.source,
        "action": "approved",
    }
    _append_review_log(log_entry)

    return True, records_affected, None


# ---------------------------------------------------------------------------
# Correction endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/corrections",
    response_model=CorrectionResponse,
    summary="Submit a single normalization correction",
)
async def post_correction(req: CorrectionRequest) -> CorrectionResponse:
    """Submit a correction that maps a raw value to a canonical form.

    Updates the alias map for the specified field, counts affected records
    in the database, and logs the correction to the review log.
    """
    if req.field not in _ALIAS_MAP_PATHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown field: {req.field}. Must be one of: place, publisher, agent",
        )

    db_path = _get_db_path()
    alias_path = _ALIAS_MAP_PATHS[req.field]
    alias_map = _load_alias_map(alias_path)

    # Check for conflicts
    if req.raw_value in alias_map:
        existing = alias_map[req.raw_value]
        if existing != req.canonical_value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Conflict: raw_value '{req.raw_value}' already maps to "
                    f"'{existing}', cannot remap to '{req.canonical_value}'"
                ),
            )
        # Same mapping already exists - return success
        records_affected = _count_affected_records(req.field, req.raw_value, db_path)
        return CorrectionResponse(
            success=True,
            alias_map_updated=str(alias_path),
            records_affected=records_affected,
        )

    # Add the mapping
    alias_map[req.raw_value] = req.canonical_value

    try:
        _save_alias_map_atomic(alias_path, alias_map)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write alias map: {exc}",
        )

    # Count affected records
    records_affected = _count_affected_records(req.field, req.raw_value, db_path)

    # Log the correction
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "field": req.field,
        "raw_value": req.raw_value,
        "canonical_value": req.canonical_value,
        "evidence": req.evidence,
        "source": req.source,
        "action": "approved",
    }
    _append_review_log(log_entry)

    # Detailed interaction log for corrections
    interaction_logger.log(
        action="correction_applied",
        field=req.field,
        params={
            "raw_value": req.raw_value,
            "canonical_value": req.canonical_value,
            "source": req.source,
        },
        result_summary={"records_affected": records_affected},
    )

    return CorrectionResponse(
        success=True,
        alias_map_updated=str(alias_path),
        records_affected=records_affected,
    )


@router.get(
    "/corrections/history",
    response_model=CorrectionHistoryResponse,
    summary="View correction history",
)
async def get_correction_history(
    field: Optional[str] = Query(None, description="Filter by field name"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> CorrectionHistoryResponse:
    """Return paginated correction history from the review log.

    Optionally filter by field name. Entries are returned in file order
    (chronological).
    """
    entries: List[CorrectionHistoryEntry] = []

    if _REVIEW_LOG_PATH.exists():
        with open(_REVIEW_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Apply field filter
                if field is not None and data.get("field") != field:
                    continue
                entries.append(
                    CorrectionHistoryEntry(
                        timestamp=data.get("timestamp", ""),
                        field=data.get("field", ""),
                        raw_value=data.get("raw_value", ""),
                        canonical_value=data.get("canonical_value", ""),
                        evidence=data.get("evidence", ""),
                        source=data.get("source", "human"),
                        action=data.get("action", "approved"),
                    )
                )

    total = len(entries)
    page = entries[offset : offset + limit]

    return CorrectionHistoryResponse(
        total=total,
        limit=limit,
        offset=offset,
        entries=page,
    )


@router.post(
    "/corrections/batch",
    response_model=BatchCorrectionResponse,
    summary="Submit multiple corrections at once",
)
async def post_batch_corrections(
    req: BatchCorrectionRequest,
) -> BatchCorrectionResponse:
    """Apply multiple corrections in a batch.

    All corrections for the same field are grouped and written in a single
    alias map update for efficiency. Each correction is validated independently.
    """
    if not req.corrections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No corrections provided",
        )

    db_path = _get_db_path()
    results: List[BatchCorrectionResult] = []
    total_applied = 0
    total_skipped = 0
    total_records_affected = 0

    # Group corrections by field to minimize file I/O
    by_field: dict = {}
    for corr in req.corrections:
        by_field.setdefault(corr.field, []).append(corr)

    for field, corrections in by_field.items():
        if field not in _ALIAS_MAP_PATHS:
            for corr in corrections:
                results.append(
                    BatchCorrectionResult(
                        raw_value=corr.raw_value,
                        canonical_value=corr.canonical_value,
                        success=False,
                        records_affected=0,
                        error=f"Unknown field: {field}. Must be one of: place, publisher, agent",
                    )
                )
                total_skipped += 1
            continue

        alias_path = _ALIAS_MAP_PATHS[field]
        alias_map = _load_alias_map(alias_path)
        map_modified = False
        log_entries = []

        for corr in corrections:
            # Check for conflicts
            if corr.raw_value in alias_map:
                existing = alias_map[corr.raw_value]
                if existing != corr.canonical_value:
                    results.append(
                        BatchCorrectionResult(
                            raw_value=corr.raw_value,
                            canonical_value=corr.canonical_value,
                            success=False,
                            records_affected=0,
                            error=(
                                f"Conflict: raw_value '{corr.raw_value}' already maps to "
                                f"'{existing}', cannot remap to '{corr.canonical_value}'"
                            ),
                        )
                    )
                    total_skipped += 1
                    continue
                else:
                    # Same mapping already exists - success, no-op
                    affected = _count_affected_records(field, corr.raw_value, db_path)
                    results.append(
                        BatchCorrectionResult(
                            raw_value=corr.raw_value,
                            canonical_value=corr.canonical_value,
                            success=True,
                            records_affected=affected,
                        )
                    )
                    total_applied += 1
                    total_records_affected += affected
                    continue

            # Add the mapping
            alias_map[corr.raw_value] = corr.canonical_value
            map_modified = True

            affected = _count_affected_records(field, corr.raw_value, db_path)
            results.append(
                BatchCorrectionResult(
                    raw_value=corr.raw_value,
                    canonical_value=corr.canonical_value,
                    success=True,
                    records_affected=affected,
                )
            )
            total_applied += 1
            total_records_affected += affected

            log_entries.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "field": field,
                    "raw_value": corr.raw_value,
                    "canonical_value": corr.canonical_value,
                    "evidence": corr.evidence,
                    "source": corr.source,
                    "action": "approved",
                }
            )

        # Write alias map once per field (if modified)
        if map_modified:
            try:
                _save_alias_map_atomic(alias_path, alias_map)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to write alias map for {field}: {exc}",
                )

        # Append all log entries
        for entry in log_entries:
            _append_review_log(entry)

    return BatchCorrectionResponse(
        total_applied=total_applied,
        total_skipped=total_skipped,
        total_records_affected=total_records_affected,
        results=results,
    )


# ---------------------------------------------------------------------------
# Primo URL helpers
# ---------------------------------------------------------------------------

# Default Primo configuration (matches app/ui_chat/config.py)
_PRIMO_DEFAULT_BASE_URL = "https://tau.primo.exlibrisgroup.com/nde/fulldisplay"
_PRIMO_VID = "972TAU_INST:NDE"
_PRIMO_TAB = "TAU"
_PRIMO_SEARCH_SCOPE = "TAU"


def _generate_primo_url(mms_id: str, base_url: Optional[str] = None) -> str:
    """Generate a Primo discovery URL for the given MMS ID.

    Uses the same URL pattern as app/ui_chat/config.py.

    Args:
        mms_id: The MMS ID (e.g. "990009748710204146").
        base_url: Optional override for the Primo base URL. Falls back to
                  the PRIMO_BASE_URL env var, then the built-in default.

    Returns:
        Full Primo URL to the record.
    """
    resolved_base = (
        base_url
        or os.environ.get("PRIMO_BASE_URL", "")
        or _PRIMO_DEFAULT_BASE_URL
    )

    params = {
        "query": f"{mms_id} ",  # trailing space is intentional (matches UI)
        "tab": _PRIMO_TAB,
        "search_scope": _PRIMO_SEARCH_SCOPE,
        "searchInFulltext": "true",
        "vid": _PRIMO_VID,
        "docid": f"alma{mms_id}",
        "adaptor": "Local Search Engine",
        "context": "L",
        "isFrbr": "false",
        "isHighlightedRecord": "false",
        "state": "",
    }

    query_parts = []
    for key, value in params.items():
        query_parts.append(f"{key}={quote(str(value), safe='')}")

    return f"{resolved_base}?{'&'.join(query_parts)}"


# ---------------------------------------------------------------------------
# Primo URL endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/primo-urls",
    response_model=PrimoUrlResponse,
    summary="Generate Primo URLs for a list of MMS IDs",
)
async def post_primo_urls(req: PrimoUrlRequest) -> PrimoUrlResponse:
    """Generate Primo discovery system URLs for one or more MMS IDs.

    Uses the same URL pattern as the Streamlit Chat UI.  An optional
    ``base_url`` in the request body overrides the ``PRIMO_BASE_URL``
    environment variable and the built-in default.
    """
    entries = [
        PrimoUrlEntry(
            mms_id=mms_id,
            primo_url=_generate_primo_url(mms_id, base_url=req.base_url),
        )
        for mms_id in req.mms_ids
    ]
    return PrimoUrlResponse(urls=entries)


@router.get(
    "/records/{mms_id}/primo",
    response_model=PrimoUrlEntry,
    summary="Get Primo URL for a single MMS ID",
)
async def get_primo_url(mms_id: str) -> PrimoUrlEntry:
    """Return the Primo discovery URL for a single MMS ID."""
    return PrimoUrlEntry(
        mms_id=mms_id,
        primo_url=_generate_primo_url(mms_id),
    )


# ---------------------------------------------------------------------------
# Agent chat helpers
# ---------------------------------------------------------------------------

_VALID_AGENT_FIELDS = {"place", "date", "publisher", "agent"}

_ALIAS_MAP_DIR = Path(
    os.environ.get("ALIAS_MAP_DIR", "data/normalization")
)


def _create_agent_harness(db_path: Path) -> AgentHarness:
    """Create an AgentHarness with default settings."""
    api_key = os.environ.get("OPENAI_API_KEY")
    return AgentHarness(
        db_path=db_path,
        alias_map_dir=_ALIAS_MAP_DIR,
        api_key=api_key,
    )


def _create_specialist_agent(field: str, harness: AgentHarness):
    """Create the appropriate specialist agent for the given field.

    Args:
        field: One of "place", "date", "publisher", "agent".
        harness: AgentHarness instance.

    Returns:
        The specialist agent instance.

    Raises:
        ValueError: If field is not recognized.
    """
    agents = {
        "place": PlaceAgent,
        "date": DateAgent,
        "publisher": PublisherAgent,
        "agent": NameAgent,
    }
    agent_cls = agents.get(field)
    if agent_cls is None:
        raise ValueError(
            f"Unknown field '{field}'. Must be one of: {', '.join(sorted(agents))}"
        )
    return agent_cls(harness)


def _format_analysis_response(field: str, analysis) -> str:
    """Format an analysis dataclass into natural language text."""
    lines = [f"Analysis for '{field}' normalization:"]

    if field == "place":
        lines.append(f"  Total places: {analysis.total_places}")
        lines.append(f"  High confidence (>=0.95): {analysis.high_confidence_count}")
        lines.append(f"  Medium confidence (0.80-0.95): {analysis.medium_confidence_count}")
        lines.append(f"  Low confidence (<0.80): {analysis.low_confidence_count}")
        lines.append(f"  Unmapped: {analysis.unmapped_count}")
        lines.append(f"  Clusters found: {len(analysis.clusters)}")
        lines.append(f"  Top gaps: {len(analysis.top_gaps)}")
    elif field == "date":
        lines.append(f"  Total dates: {analysis.total_dates}")
        lines.append(f"  Parsed (>=0.8): {analysis.parsed_count}")
        lines.append(f"  Unparsed (<0.8): {analysis.unparsed_count}")
        if analysis.by_method:
            lines.append("  By method:")
            for method, count in sorted(analysis.by_method.items(), key=lambda x: -x[1]):
                lines.append(f"    {method}: {count}")
        lines.append(f"  Clusters found: {len(analysis.clusters)}")
        lines.append(f"  Top unparsed: {len(analysis.top_unparsed)}")
    elif field == "publisher":
        lines.append(f"  Total publishers: {analysis.total_publishers}")
        lines.append(f"  Mapped (>=0.95): {analysis.mapped_count}")
        lines.append(f"  Unmapped (<=0.80): {analysis.unmapped_count}")
        lines.append(f"  Missing: {analysis.missing_count}")
        lines.append(f"  Clusters found: {len(analysis.clusters)}")
        lines.append(f"  Top gaps: {len(analysis.top_gaps)}")
    elif field == "agent":
        lines.append(f"  Total agents: {analysis.total_agents}")
        lines.append(f"  With authority: {analysis.with_authority}")
        lines.append(f"  Without authority: {analysis.without_authority}")
        lines.append(f"  Low confidence (<0.8): {analysis.low_confidence_count}")
        lines.append(f"  Missing role: {analysis.missing_role_count}")
        lines.append(f"  Top gaps: {len(analysis.top_gaps)}")

    return "\n".join(lines)


def _clusters_to_summaries(clusters) -> list:
    """Convert Cluster dataclass list to AgentClusterSummary list."""
    return [
        AgentClusterSummary(
            cluster_id=c.cluster_id,
            cluster_type=c.cluster_type,
            value_count=len(c.values),
            total_records=c.total_records_affected,
            priority_score=c.priority_score,
        )
        for c in clusters
    ]


def _proposals_to_api(proposals: list) -> list:
    """Convert ProposedMapping list to AgentProposal list."""
    return [
        AgentProposal(
            raw_value=p.raw_value,
            canonical_value=p.canonical_value,
            confidence=p.confidence,
            reasoning=p.reasoning,
            evidence_sources=p.evidence_sources,
        )
        for p in proposals
    ]


# ---------------------------------------------------------------------------
# Agent chat endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="Chat with a specialist metadata agent",
)
async def agent_chat(req: AgentChatRequest) -> AgentChatResponse:
    """Interact with a specialist metadata agent via chat."""
    import time as _time

    _chat_start = _time.monotonic()
    field = req.field
    if field not in _VALID_AGENT_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid field '{field}'. "
                f"Must be one of: {', '.join(sorted(_VALID_AGENT_FIELDS))}"
            ),
        )

    db_path = _get_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database not found: {db_path}",
        )

    try:
        harness = _create_agent_harness(db_path)
        agent = _create_specialist_agent(field, harness)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize agent: {exc}",
        )

    message = req.message.strip()

    # --- Route: analysis (empty message or "analyze") ---
    if not message or message.lower() == "analyze":
        try:
            analysis = agent.analyze()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Analysis failed: {exc}",
            )

        response_text = _format_analysis_response(field, analysis)

        # Extract clusters from the analysis if available
        clusters_raw = getattr(analysis, "clusters", [])
        cluster_summaries = _clusters_to_summaries(clusters_raw)

        result = AgentChatResponse(
            response=response_text,
            proposals=[],
            clusters=cluster_summaries,
            field=field,
            action="analysis",
        )
        interaction_logger.log(
            action="agent_chat",
            field=field,
            params={"message": message[:200]},
            result_summary={
                "action": "analysis",
                "clusters_count": len(cluster_summaries),
            },
            duration_ms=(_time.monotonic() - _chat_start) * 1000,
        )
        return result

    # --- Route: propose mappings for a cluster ---
    if message.lower().startswith("propose:"):
        cluster_ref = message[len("propose:"):].strip()

        # Check if agent has get_clusters and propose_mappings
        if not hasattr(agent, "get_clusters") or not hasattr(agent, "propose_mappings"):
            return AgentChatResponse(
                response=(
                    f"The '{field}' agent does not support propose_mappings. "
                    f"Only place and publisher agents support cluster-based proposals."
                ),
                proposals=[],
                clusters=[],
                field=field,
                action="answer",
            )

        # Check for API key
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return AgentChatResponse(
                response=(
                    "Proposal generation requires an OpenAI API key. "
                    "Set the OPENAI_API_KEY environment variable to enable "
                    "LLM-assisted mapping proposals."
                ),
                proposals=[],
                clusters=[],
                field=field,
                action="proposals",
            )

        try:
            clusters = agent.get_clusters()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get clusters: {exc}",
            )

        # Find the cluster by ID or index
        target_cluster = None
        for c in clusters:
            if c.cluster_id == cluster_ref:
                target_cluster = c
                break

        # Try numeric index if not found by ID
        if target_cluster is None:
            try:
                idx = int(cluster_ref)
                if 0 <= idx < len(clusters):
                    target_cluster = clusters[idx]
            except (ValueError, IndexError):
                pass

        if target_cluster is None:
            available = [c.cluster_id for c in clusters[:10]]
            return AgentChatResponse(
                response=(
                    f"Cluster '{cluster_ref}' not found. "
                    f"Available clusters (first 10): {', '.join(available)}"
                ),
                proposals=[],
                clusters=_clusters_to_summaries(clusters),
                field=field,
                action="proposals",
            )

        try:
            proposals = agent.propose_mappings(target_cluster)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Proposal generation failed: {exc}",
            )

        result = AgentChatResponse(
            response=(
                f"Generated {len(proposals)} proposals for cluster "
                f"'{target_cluster.cluster_id}'."
            ),
            proposals=_proposals_to_api(proposals),
            clusters=[],
            field=field,
            action="proposals",
        )
        interaction_logger.log(
            action="agent_chat",
            field=field,
            params={"message": message[:200], "cluster": target_cluster.cluster_id},
            result_summary={
                "action": "proposals",
                "proposals_count": len(proposals),
                "cluster_type": target_cluster.cluster_type,
            },
            duration_ms=(_time.monotonic() - _chat_start) * 1000,
        )
        return result

    # --- Route: get cluster details ---
    if message.lower().startswith("cluster:"):
        cluster_ref = message[len("cluster:"):].strip()

        if not hasattr(agent, "get_clusters"):
            return AgentChatResponse(
                response=(
                    f"The '{field}' agent does not support cluster listing."
                ),
                proposals=[],
                clusters=[],
                field=field,
                action="answer",
            )

        try:
            clusters = agent.get_clusters()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get clusters: {exc}",
            )

        # Find target cluster
        target_cluster = None
        for c in clusters:
            if c.cluster_id == cluster_ref:
                target_cluster = c
                break

        if target_cluster is None:
            try:
                idx = int(cluster_ref)
                if 0 <= idx < len(clusters):
                    target_cluster = clusters[idx]
            except (ValueError, IndexError):
                pass

        if target_cluster is None:
            return AgentChatResponse(
                response=(
                    f"Cluster '{cluster_ref}' not found. "
                    f"Found {len(clusters)} clusters total."
                ),
                proposals=[],
                clusters=_clusters_to_summaries(clusters),
                field=field,
                action="answer",
            )

        # Format cluster details
        values_text = ", ".join(
            f"'{v.raw_value}' (freq={v.frequency})"
            for v in target_cluster.values[:10]
        )
        response_text = (
            f"Cluster '{target_cluster.cluster_id}' "
            f"(type={target_cluster.cluster_type}):\n"
            f"  Values ({len(target_cluster.values)}): {values_text}\n"
            f"  Total records affected: {target_cluster.total_records_affected}\n"
            f"  Priority score: {target_cluster.priority_score}"
        )

        return AgentChatResponse(
            response=response_text,
            proposals=[],
            clusters=[
                AgentClusterSummary(
                    cluster_id=target_cluster.cluster_id,
                    cluster_type=target_cluster.cluster_type,
                    value_count=len(target_cluster.values),
                    total_records=target_cluster.total_records_affected,
                    priority_score=target_cluster.priority_score,
                )
            ],
            field=field,
            action="answer",
        )

    # --- Route: free-form question (grounding-based) ---
    try:
        gaps = harness.query_gaps(field, max_confidence=0.8)
        gap_count = len(gaps)

        # Provide summary of gaps
        unique_values = {}
        for g in gaps:
            if g.raw_value not in unique_values:
                unique_values[g.raw_value] = 0
            unique_values[g.raw_value] += 1

        top_values = sorted(unique_values.items(), key=lambda x: -x[1])[:10]
        top_text = "\n".join(
            f"  - '{v}' ({count} records)" for v, count in top_values
        )

        response_text = (
            f"For '{field}' field regarding your question: \"{message}\"\n\n"
            f"Current grounding data:\n"
            f"  Total low-confidence records: {gap_count}\n"
            f"  Unique values needing attention: {len(unique_values)}\n\n"
            f"Top values by frequency:\n{top_text}"
        )
    except Exception as exc:
        response_text = (
            f"Unable to retrieve grounding data for '{field}': {exc}"
        )

    result = AgentChatResponse(
        response=response_text,
        proposals=[],
        clusters=[],
        field=field,
        action="answer",
    )
    interaction_logger.log(
        action="agent_chat",
        field=field,
        params={"message": req.message[:200] if req.message else ""},
        result_summary={
            "action": result.action,
            "proposals_count": len(result.proposals),
            "clusters_count": len(result.clusters),
        },
        duration_ms=(_time.monotonic() - _chat_start) * 1000,
    )
    return result


# ---------------------------------------------------------------------------
# Publisher authority endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/publishers",
    response_model=PublisherAuthorityListResponse,
    summary="List publisher authority records",
    description=(
        "Returns publisher authorities with variant counts and imprint counts. "
        "Optionally filter by publisher type."
    ),
)
def list_publisher_authorities(
    type: Optional[str] = Query(
        None,
        description=(
            "Filter by publisher type: printing_house, private_press, "
            "modern_publisher, bibliophile_society, unknown_marker, unresearched"
        ),
    ),
):
    """Return publisher authority records with variant and imprint counts."""
    from scripts.metadata.publisher_authority import PublisherAuthorityStore

    db_path = _get_db_path()
    if not db_path.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    valid_types = {
        "printing_house",
        "private_press",
        "modern_publisher",
        "bibliophile_society",
        "unknown_marker",
        "unresearched",
    }
    if type is not None and type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type '{type}'. Must be one of: {sorted(valid_types)}",
        )

    store = PublisherAuthorityStore(db_path)
    authorities = store.list_all(type_filter=type)

    items = []
    for auth in authorities:
        imprint_count = store.link_to_imprints(auth.id)
        items.append(
            PublisherAuthorityResponse(
                id=auth.id,
                canonical_name=auth.canonical_name,
                type=auth.type,
                confidence=auth.confidence,
                dates_active=auth.dates_active,
                location=auth.location,
                is_missing_marker=auth.is_missing_marker,
                variant_count=len(auth.variants),
                imprint_count=imprint_count,
                variants=[
                    PublisherVariantResponse(
                        variant_form=v.variant_form,
                        script=v.script,
                        language=v.language,
                        is_primary=v.is_primary,
                    )
                    for v in auth.variants
                ],
                viaf_id=auth.viaf_id,
                wikidata_id=auth.wikidata_id,
                cerl_id=auth.cerl_id,
            )
        )

    return PublisherAuthorityListResponse(total=len(items), items=items)


# TODO: Add WebSocket endpoint /ws/metadata/agent for streaming responses
