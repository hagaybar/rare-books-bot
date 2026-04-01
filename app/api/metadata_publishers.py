"""FastAPI router for publisher authority endpoints.

Provides CRUD endpoints for publisher authority records, variant management,
and imprint match preview functionality.
"""

import sqlite3
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from scripts.metadata.publisher_authority import (
        PublisherAuthority,
        PublisherAuthorityStore,
    )

from fastapi import APIRouter, HTTPException, Query, status

from app.api.metadata_common import _get_db_path
from app.api.metadata_models import (
    CreatePublisherRequest,
    CreateVariantRequest,
    DeleteResponse,
    MatchPreviewResponse,
    PublisherAuthorityListResponse,
    PublisherAuthorityResponse,
    PublisherVariantResponse,
    UpdatePublisherRequest,
)

router = APIRouter(prefix="/metadata/publishers", tags=["metadata-publishers"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_VALID_PUB_TYPES = {
    "printing_house",
    "private_press",
    "modern_publisher",
    "bibliophile_society",
    "unknown_marker",
    "unresearched",
}


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
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


@router.post(
    "",
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
    "/{publisher_id}",
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
    "/{publisher_id}",
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
    "/{publisher_id}/variants",
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
    "/{publisher_id}/variants/{variant_id}",
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
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM publisher_variants WHERE id = ? AND authority_id = ?", (variant_id, publisher_id))
            conn.commit()
        finally:
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
# Match preview endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/match-preview",
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
        try:
            # Check if imprints table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='imprints'"
            ).fetchone()
            if not table_check:
                return MatchPreviewResponse(variant_form=variant_form, matching_imprints=0)

            # Use LIKE for flexible matching (case-insensitive by default in SQLite)
            row = conn.execute(
                "SELECT COUNT(*) FROM imprints WHERE publisher_norm LIKE ?",
                (f"%{variant_form.lower()}%",),
            ).fetchone()
            count = row[0] if row else 0
        finally:
            conn.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query imprints: {exc}",
        )

    return MatchPreviewResponse(variant_form=variant_form, matching_imprints=count)
