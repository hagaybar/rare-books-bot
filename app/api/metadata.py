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
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from scripts.metadata.publisher_authority import (
        PublisherAuthority,
        PublisherAuthorityStore,
    )

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
    CreatePublisherRequest,
    CreateVariantRequest,
    DeleteResponse,
    FieldCoverageResponse,
    FlaggedItemResponse,
    IssueRecord,
    IssuesResponse,
    MatchPreviewResponse,
    MethodBreakdownResponse,
    MethodDistribution,
    PrimoUrlEntry,
    PrimoUrlRequest,
    PrimoUrlResponse,
    PublisherAuthorityListResponse,
    PublisherAuthorityResponse,
    PublisherVariantResponse,
    UnmappedValue,
    UpdatePublisherRequest,
)
from scripts.metadata.audit import (
    CoverageReport,
    FieldCoverage,
    generate_coverage_report,
)
from scripts.metadata.agent_harness import AgentHarness
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
# Primo URL helpers — delegated to scripts/utils/primo.py
# ---------------------------------------------------------------------------

from scripts.utils.primo import generate_primo_url as _generate_primo_url  # noqa: E402


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
        items.append(_authority_to_response(store, auth))

    return PublisherAuthorityListResponse(total=len(items), items=items)


# ---------------------------------------------------------------------------
# B13: Publisher CRUD endpoints
# ---------------------------------------------------------------------------


def _authority_to_response(
    store: "PublisherAuthorityStore", auth: "PublisherAuthority"
) -> PublisherAuthorityResponse:
    """Convert a PublisherAuthority to its API response model."""
    imprint_count = store.link_to_imprints(auth.id)
    return PublisherAuthorityResponse(
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
                id=v.id,
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


_VALID_PUB_TYPES = {
    "printing_house",
    "private_press",
    "modern_publisher",
    "bibliophile_society",
    "unknown_marker",
    "unresearched",
}


@router.post(
    "/publishers",
    response_model=PublisherAuthorityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a publisher authority",
)
def create_publisher_authority(req: CreatePublisherRequest):
    """Create a new publisher authority record."""
    from scripts.metadata.publisher_authority import (
        PublisherAuthority,
        PublisherAuthorityStore,
    )

    if req.type not in _VALID_PUB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type '{req.type}'. Must be one of: {sorted(_VALID_PUB_TYPES)}",
        )

    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    store = PublisherAuthorityStore(db)
    authority = PublisherAuthority(
        canonical_name=req.canonical_name,
        type=req.type,
        confidence=req.confidence,
        location=req.location,
        dates_active=req.dates_active,
        notes=req.notes,
    )

    try:
        auth_id = store.create(authority)
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Publisher '{req.canonical_name}' already exists",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create publisher: {exc}",
        )

    created = store.get_by_id(auth_id)
    return _authority_to_response(store, created)


@router.put(
    "/publishers/{publisher_id}",
    response_model=PublisherAuthorityResponse,
    summary="Update a publisher authority",
)
def update_publisher_authority(publisher_id: int, req: UpdatePublisherRequest):
    """Update fields of an existing publisher authority."""
    from scripts.metadata.publisher_authority import PublisherAuthorityStore

    if req.type is not None and req.type not in _VALID_PUB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid type '{req.type}'. Must be one of: {sorted(_VALID_PUB_TYPES)}",
        )

    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    store = PublisherAuthorityStore(db)
    existing = store.get_by_id(publisher_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publisher authority {publisher_id} not found",
        )

    # Apply only the fields that were provided
    if req.canonical_name is not None:
        existing.canonical_name = req.canonical_name
    if req.type is not None:
        existing.type = req.type
    if req.confidence is not None:
        existing.confidence = req.confidence
    if req.location is not None:
        existing.location = req.location
    if req.dates_active is not None:
        existing.dates_active = req.dates_active
    if req.notes is not None:
        existing.notes = req.notes

    try:
        store.update(existing)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update publisher: {exc}",
        )

    updated = store.get_by_id(publisher_id)
    return _authority_to_response(store, updated)


@router.delete(
    "/publishers/{publisher_id}",
    response_model=DeleteResponse,
    summary="Delete a publisher authority",
)
def delete_publisher_authority(publisher_id: int):
    """Delete a publisher authority and cascade-delete its variants."""
    from scripts.metadata.publisher_authority import PublisherAuthorityStore

    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    store = PublisherAuthorityStore(db)
    existing = store.get_by_id(publisher_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publisher authority {publisher_id} not found",
        )

    try:
        store.delete(publisher_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete publisher: {exc}",
        )

    return DeleteResponse(
        success=True,
        message=f"Publisher authority {publisher_id} ('{existing.canonical_name}') deleted",
    )


@router.post(
    "/publishers/{publisher_id}/variants",
    response_model=PublisherAuthorityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a variant to a publisher authority",
)
def add_publisher_variant(publisher_id: int, req: CreateVariantRequest):
    """Add a name variant to an existing publisher authority."""
    from scripts.metadata.publisher_authority import (
        PublisherAuthorityStore,
        PublisherVariant,
    )

    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    store = PublisherAuthorityStore(db)
    existing = store.get_by_id(publisher_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publisher authority {publisher_id} not found",
        )

    variant = PublisherVariant(
        variant_form=req.variant_form,
        script=req.script,
        language=req.language,
    )

    try:
        store.add_variant(publisher_id, variant)
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Variant '{req.variant_form}' already exists",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add variant: {exc}",
        )

    updated = store.get_by_id(publisher_id)
    return _authority_to_response(store, updated)


@router.delete(
    "/publishers/{publisher_id}/variants/{variant_id}",
    response_model=DeleteResponse,
    summary="Remove a variant from a publisher authority",
)
def delete_publisher_variant(publisher_id: int, variant_id: int):
    """Remove a specific variant from a publisher authority."""
    from scripts.metadata.publisher_authority import PublisherAuthorityStore

    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    store = PublisherAuthorityStore(db)
    existing = store.get_by_id(publisher_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Publisher authority {publisher_id} not found",
        )

    # Find the variant to delete
    variant_found = any(v.id == variant_id for v in existing.variants)
    if not variant_found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Variant {variant_id} not found on authority {publisher_id}",
        )

    try:
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM publisher_variants WHERE id = ? AND authority_id = ?", (variant_id, publisher_id))
        conn.commit()
        conn.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete variant: {exc}",
        )

    return DeleteResponse(
        success=True,
        message=f"Variant {variant_id} removed from authority {publisher_id}",
    )


# ---------------------------------------------------------------------------
# B14: Match preview endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/publishers/match-preview",
    response_model=MatchPreviewResponse,
    summary="Preview imprint matches for a variant form",
)
def match_preview(
    variant_form: str = Query(..., min_length=1, description="Variant form to match against imprints"),
):
    """Count imprints where publisher_norm matches the given variant form."""
    db = _get_db_path()
    if not db.exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bibliographic database not available",
        )

    try:
        conn = sqlite3.connect(str(db))
        # Check if imprints table exists
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='imprints'"
        ).fetchone()
        if not table_check:
            conn.close()
            return MatchPreviewResponse(variant_form=variant_form, matching_imprints=0)

        # Use LIKE for flexible matching (case-insensitive by default in SQLite)
        row = conn.execute(
            "SELECT COUNT(*) FROM imprints WHERE publisher_norm LIKE ?",
            (f"%{variant_form.lower()}%",),
        ).fetchone()
        count = row[0] if row else 0
        conn.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query imprints: {exc}",
        )

    return MatchPreviewResponse(variant_form=variant_form, matching_imprints=count)


# ---------------------------------------------------------------------------
# Entity Enrichment endpoints
# ---------------------------------------------------------------------------


@router.get("/enrichment/stats", summary="Enrichment statistics")
async def get_enrichment_stats():
    """Return summary statistics about entity enrichment coverage."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        stats = {}
        stats["total"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment"
        ).fetchone()[0]
        stats["with_wikidata"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE wikidata_id IS NOT NULL"
        ).fetchone()[0]
        stats["with_viaf"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE viaf_id IS NOT NULL"
        ).fetchone()[0]
        stats["with_person_info"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE person_info IS NOT NULL"
        ).fetchone()[0]
        stats["with_image"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE image_url IS NOT NULL"
        ).fetchone()[0]
        stats["with_wikipedia"] = conn.execute(
            "SELECT count(*) FROM authority_enrichment WHERE wikipedia_url IS NOT NULL"
        ).fetchone()[0]
        stats["agents_linked"] = conn.execute(
            "SELECT count(DISTINCT a.agent_norm) FROM agents a "
            "JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri"
        ).fetchone()[0]
        stats["total_agents"] = conn.execute(
            "SELECT count(DISTINCT agent_norm) FROM agents"
        ).fetchone()[0]
        return stats
    finally:
        conn.close()


@router.get("/enrichment/facets", summary="Enrichment facets for filtering")
async def get_enrichment_facets(
    search: str = "",
    occupation: str = "",
    century: str = "",
    role: str = "",
    has_bio: bool = False,
    has_image: bool = False,
):
    """Return facet values scoped to active filters (standard faceted search).

    Each facet's counts are computed with all OTHER active filters applied,
    but NOT the facet's own filter. This shows how many results each option
    would produce if selected.
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Roles: apply all filters EXCEPT role
        role_where, role_params = _build_enrichment_where(
            search=search, occupation=occupation, century=century,
            has_bio=has_bio, has_image=has_image,
        )
        roles = [
            {"value": r[0] or "(none)", "count": r[1]}
            for r in conn.execute(
                f"SELECT a.role_raw, count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) "
                f"FROM agents a JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri "
                f"WHERE {role_where} "
                f"GROUP BY a.role_raw ORDER BY count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) DESC LIMIT 15",
                role_params,
            ).fetchall()
        ]

        # Occupations: apply all filters EXCEPT occupation
        occ_where, occ_params = _build_enrichment_where(
            search=search, century=century, role=role,
            has_bio=has_bio, has_image=has_image,
        )
        occupations = [
            {"value": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT value, count(*) as cnt FROM ("
                f"  SELECT json_each.value as value "
                f"  FROM authority_enrichment ae "
                f"  JOIN agents a ON a.authority_uri = ae.authority_uri "
                f"  , json_each(json_extract(ae.person_info, '$.occupations')) "
                f"  WHERE {occ_where}"
                f") GROUP BY value ORDER BY cnt DESC LIMIT 25",
                occ_params,
            ).fetchall()
        ]

        # Centuries: apply all filters EXCEPT century
        cent_where, cent_params = _build_enrichment_where(
            search=search, occupation=occupation, role=role,
            has_bio=has_bio, has_image=has_image,
        )
        centuries = [
            {"value": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT "
                f"  CASE "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1400 THEN 'before 1400' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1500 THEN '15th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1600 THEN '16th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1700 THEN '17th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1800 THEN '18th century' "
                f"    WHEN json_extract(ae.person_info, '$.birth_year') < 1900 THEN '19th century' "
                f"    ELSE '20th century+' "
                f"  END as century_label, "
                f"  count(*) as cnt "
                f"FROM authority_enrichment ae "
                f"JOIN agents a ON a.authority_uri = ae.authority_uri "
                f"WHERE {cent_where} AND ae.person_info IS NOT NULL "
                f"  AND json_extract(ae.person_info, '$.birth_year') IS NOT NULL "
                f"GROUP BY century_label ORDER BY century_label",
                cent_params,
            ).fetchall()
        ]

        return {"roles": roles, "occupations": occupations, "centuries": centuries}
    finally:
        conn.close()


def _build_enrichment_where(
    *,
    search: str = "",
    occupation: str = "",
    century: str = "",
    role: str = "",
    has_bio: bool = False,
    has_image: bool = False,
) -> tuple[str, list]:
    """Build WHERE clause for enrichment queries. Returns (where_sql, params)."""
    where_clauses = ["ae.authority_uri IS NOT NULL"]
    params: list = []

    if has_bio:
        where_clauses.append("ae.person_info IS NOT NULL")
    if has_image:
        where_clauses.append("ae.image_url IS NOT NULL")
    if search:
        where_clauses.append(
            "(a.agent_raw LIKE ? OR a.agent_norm LIKE ? OR ae.label LIKE ? OR ae.description LIKE ?)"
        )
        term = f"%{search}%"
        params.extend([term, term, term, term])
    if role:
        if role == "(none)":
            where_clauses.append("(a.role_raw IS NULL OR a.role_raw = '')")
        else:
            where_clauses.append("a.role_raw = ?")
            params.append(role)
    if occupation:
        where_clauses.append(
            "ae.authority_uri IN ("
            "  SELECT ae2.authority_uri FROM authority_enrichment ae2, "
            "  json_each(json_extract(ae2.person_info, '$.occupations')) "
            "  WHERE json_each.value = ?)"
        )
        params.append(occupation)
    if century:
        century_ranges = {
            "before 1400": (None, 1400),
            "15th century": (1400, 1500),
            "16th century": (1500, 1600),
            "17th century": (1600, 1700),
            "18th century": (1700, 1800),
            "19th century": (1800, 1900),
            "20th century+": (1900, 2100),
        }
        rng = century_ranges.get(century)
        if rng:
            lo, hi = rng
            if lo is None:
                where_clauses.append("json_extract(ae.person_info, '$.birth_year') < ?")
                params.append(hi)
            else:
                where_clauses.append(
                    "json_extract(ae.person_info, '$.birth_year') >= ? AND "
                    "json_extract(ae.person_info, '$.birth_year') < ?"
                )
                params.extend([lo, hi])

    return " AND ".join(where_clauses), params


@router.get("/enrichment/agents", summary="Enriched agents list")
async def get_enriched_agents(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    has_bio: bool = False,
    role: str = "",
    occupation: str = "",
    century: str = "",
    has_image: bool = False,
):
    """List agents with their enrichment data from Wikidata.

    Args:
        limit: Max results (default 50)
        offset: Pagination offset
        search: Search in agent name or enrichment label
        has_bio: If true, only return agents with person_info
        role: Filter by agent role (e.g. 'author', 'printer')
        occupation: Filter by Wikidata occupation (e.g. 'rabbi', 'theologian')
        century: Filter by birth century (e.g. '16th century')
        has_image: If true, only return agents with an image
    """
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        where_sql, params = _build_enrichment_where(
            search=search, occupation=occupation, century=century,
            role=role, has_bio=has_bio, has_image=has_image,
        )

        # Count total (deduplicated by wikidata_id to merge Hebrew/Latin name variants)
        total = conn.execute(
            f"SELECT count(DISTINCT COALESCE(ae.wikidata_id, a.agent_norm)) FROM agents a "
            f"JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri "
            f"WHERE {where_sql}",
            params,
        ).fetchone()[0]

        # Fetch agents with enrichment (deduplicated by wikidata_id to merge
        # Hebrew/Latin variants of the same person into a single card)
        rows = conn.execute(
            f"""
            SELECT
                MIN(a.agent_norm) as agent_norm,
                GROUP_CONCAT(DISTINCT a.agent_raw) as agent_raw,
                a.agent_type,
                GROUP_CONCAT(DISTINCT a.role_raw) as role_raw,
                a.authority_uri,
                ae.nli_id,
                ae.wikidata_id,
                ae.viaf_id,
                ae.isni_id,
                ae.loc_id,
                ae.label,
                ae.description,
                ae.person_info,
                ae.image_url,
                ae.wikipedia_url,
                ae.confidence,
                count(DISTINCT a.record_id) as record_count
            FROM agents a
            JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
            WHERE {where_sql}
            GROUP BY COALESCE(ae.wikidata_id, a.agent_norm)
            ORDER BY record_count DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            # Parse person_info JSON
            if item.get("person_info"):
                try:
                    item["person_info"] = json.loads(item["person_info"])
                except (json.JSONDecodeError, TypeError):
                    pass
            items.append(item)

        return {"total": total, "limit": limit, "offset": offset, "items": items}
    finally:
        conn.close()


@router.get(
    "/enrichment/agent/{agent_norm}",
    summary="Get enrichment for a specific agent",
)
async def get_agent_enrichment(agent_norm: str):
    """Get full enrichment data for a specific agent by normalized name."""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                a.agent_norm, a.agent_raw, a.agent_type, a.role_raw, a.authority_uri,
                ae.nli_id, ae.wikidata_id, ae.viaf_id, ae.isni_id, ae.loc_id,
                ae.label, ae.description, ae.person_info,
                ae.image_url, ae.wikipedia_url, ae.confidence
            FROM agents a
            JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
            WHERE a.agent_norm = ?
            LIMIT 1
            """,
            (agent_norm,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_norm}' not found or not enriched")

        item = dict(row)
        if item.get("person_info"):
            try:
                item["person_info"] = json.loads(item["person_info"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Also get all records this agent appears in
        records = conn.execute(
            """
            SELECT DISTINCT r.mms_id, t.value as title, a.role_raw
            FROM agents a
            JOIN records r ON a.record_id = r.id
            LEFT JOIN titles t ON r.id = t.record_id AND t.title_type = 'main'
            WHERE a.agent_norm = ?
            ORDER BY t.value
            """,
            (agent_norm,),
        ).fetchall()

        item["records"] = [dict(r) for r in records]
        return item
    finally:
        conn.close()


@router.get("/enrichment/agent-records", summary="Records for an enriched agent")
async def get_agent_records(
    wikidata_id: str = Query("", description="Wikidata ID (e.g., Q319902)"),
    agent_norm: str = Query("", description="Agent norm (fallback if no wikidata_id)"),
):
    """Get bibliographic records where this agent appears."""
    if not wikidata_id and not agent_norm:
        raise HTTPException(400, "Provide either wikidata_id or agent_norm")
    if wikidata_id and agent_norm:
        raise HTTPException(400, "Provide only one of wikidata_id or agent_norm")

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Find all agent_norms for this entity
        if wikidata_id:
            norms = [r[0] for r in conn.execute(
                """SELECT DISTINCT a.agent_norm FROM agents a
                   JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
                   WHERE ae.wikidata_id = ?""",
                (wikidata_id,),
            ).fetchall()]
            # Get display name from enrichment
            label_row = conn.execute(
                "SELECT label FROM authority_enrichment WHERE wikidata_id = ? LIMIT 1",
                (wikidata_id,),
            ).fetchone()
            display_name = label_row["label"] if label_row else (norms[0] if norms else "Unknown")
        else:
            norms = [agent_norm]
            label_row = conn.execute(
                """SELECT ae.label FROM authority_enrichment ae
                   JOIN agents a ON a.authority_uri = ae.authority_uri
                   WHERE a.agent_norm = ? LIMIT 1""",
                (agent_norm,),
            ).fetchone()
            display_name = label_row["label"] if label_row else agent_norm

        if not norms:
            raise HTTPException(404, f"Agent not found: {wikidata_id or agent_norm}")

        placeholders = ",".join("?" for _ in norms)
        rows = conn.execute(
            f"""SELECT DISTINCT
                    r.mms_id,
                    t.value as title,
                    i.date_raw,
                    i.date_start,
                    i.place_norm,
                    i.publisher_norm,
                    a.role_raw as role
                FROM agents a
                JOIN records r ON a.record_id = r.id
                LEFT JOIN titles t ON t.record_id = r.id AND t.title_type = 'main'
                LEFT JOIN imprints i ON i.record_id = r.id
                WHERE a.agent_norm IN ({placeholders})
                ORDER BY i.date_start ASC NULLS LAST""",
            norms,
        ).fetchall()

        records = []
        seen_mms = set()
        for row in rows:
            mms = row["mms_id"]
            if mms in seen_mms:
                continue
            seen_mms.add(mms)
            records.append({
                "mms_id": mms,
                "title": row["title"],
                "date_raw": row["date_raw"],
                "date_start": row["date_start"],
                "place_norm": row["place_norm"],
                "publisher_norm": row["publisher_norm"],
                "role": row["role"],
                "primo_url": _generate_primo_url(mms) if mms else None,
            })

        return {
            "display_name": display_name,
            "record_count": len(records),
            "records": records,
        }
    finally:
        conn.close()
