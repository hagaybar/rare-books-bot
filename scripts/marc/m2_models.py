"""M2 normalization models.

These models represent normalized/enriched fields appended to M1 canonical records.
All normalization is deterministic, reversible, confidence-scored, and method-tagged.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class DateNormalization(BaseModel):
    """Normalized date with start/end range and provenance."""

    start: Optional[int] = Field(None, description="Start year (inclusive)")
    end: Optional[int] = Field(None, description="End year (inclusive)")
    label: str = Field(..., description="Human-readable date label")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    method: str = Field(..., description="Normalization method/rule ID")
    evidence_paths: List[str] = Field(..., description="M1 JSON paths used as evidence")
    warnings: List[str] = Field(default_factory=list, description="Warnings about normalization")


class PlaceNormalization(BaseModel):
    """Normalized place with normalized key and display value."""

    value: Optional[str] = Field(None, description="Normalized key (casefolded, cleaned)")
    display: str = Field(..., description="Best display form")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    method: str = Field(..., description="Normalization method/rule ID")
    evidence_paths: List[str] = Field(..., description="M1 JSON paths used as evidence")
    warnings: List[str] = Field(default_factory=list, description="Warnings about normalization")


class PublisherNormalization(BaseModel):
    """Normalized publisher with normalized key and display value."""

    value: Optional[str] = Field(None, description="Normalized key (casefolded, cleaned)")
    display: str = Field(..., description="Best display form")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    method: str = Field(..., description="Normalization method/rule ID")
    evidence_paths: List[str] = Field(..., description="M1 JSON paths used as evidence")
    warnings: List[str] = Field(default_factory=list, description="Warnings about normalization")


class ImprintNormalization(BaseModel):
    """Normalized imprint data (corresponds to one M1 imprint)."""

    date_norm: Optional[DateNormalization] = Field(None, description="Normalized date")
    place_norm: Optional[PlaceNormalization] = Field(None, description="Normalized place")
    publisher_norm: Optional[PublisherNormalization] = Field(None, description="Normalized publisher")


class M2Enrichment(BaseModel):
    """M2 enrichment object appended to M1 canonical records."""

    imprints_norm: List[ImprintNormalization] = Field(
        default_factory=list,
        description="Normalized imprint data (parallel to M1 imprints array)"
    )
