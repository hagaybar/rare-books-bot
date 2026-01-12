"""M2 normalization models.

These models represent normalized/enriched fields appended to M1 canonical records.
All normalization is deterministic, reversible, confidence-scored, and method-tagged.
"""

from typing import List, Optional, Tuple
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


class AgentNormalization(BaseModel):
    """Normalized agent with confidence tracking.

    Represents the canonical form of an agent name for faceting and search.
    Raw value is preserved in the corresponding M1 AgentData.
    """

    agent_raw: str = Field(..., description="Original agent name from M1 (for traceability)")
    agent_norm: str = Field(..., description="Normalized canonical name (lowercase, no punctuation)")
    agent_confidence: float = Field(..., ge=0.0, le=1.0, description="Normalization confidence (0-1)")
    agent_method: str = Field(..., description="Normalization method: 'base_clean', 'alias_map', or 'ambiguous'")
    agent_notes: Optional[str] = Field(None, description="Warnings or ambiguity flags")


class RoleNormalization(BaseModel):
    """Normalized role with confidence tracking.

    Maps raw MARC relator codes/terms to controlled vocabulary for querying.
    """

    role_raw: Optional[str] = Field(None, description="Original role string from M1 (may be None)")
    role_norm: str = Field(..., description="Normalized role from controlled vocabulary")
    role_confidence: float = Field(..., ge=0.0, le=1.0, description="Role mapping confidence (0-1)")
    role_method: str = Field(..., description="Normalization method: 'relator_code', 'relator_term', 'inferred', or 'manual_map'")


class M2Enrichment(BaseModel):
    """M2 enrichment object appended to M1 canonical records."""

    imprints_norm: List[ImprintNormalization] = Field(
        default_factory=list,
        description="Normalized imprint data (parallel to M1 imprints array)"
    )

    agents_norm: List[Tuple[int, "AgentNormalization", "RoleNormalization"]] = Field(
        default_factory=list,
        description="Normalized agent data: List[(agent_index, AgentNormalization, RoleNormalization)]"
    )
