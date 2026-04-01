"""FastAPI router for normalization correction endpoints.

Provides endpoints for submitting single and batch corrections to alias maps,
and for viewing the correction history.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.metadata_common import _get_db_path
from app.api.metadata_models import (
    BatchCorrectionRequest,
    BatchCorrectionResponse,
    BatchCorrectionResult,
    CorrectionHistoryEntry,
    CorrectionHistoryResponse,
    CorrectionRequest,
    CorrectionResponse,
)
from scripts.metadata.interaction_logger import interaction_logger

router = APIRouter(prefix="/metadata", tags=["metadata-corrections"])


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
        try:
            sql = (
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {raw_col} = ? AND ({conf_col} IS NULL OR {conf_col} <= 0.80)"
            )
            count = conn.execute(sql, (raw_value,)).fetchone()[0]
            return count
        finally:
            conn.close()
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
