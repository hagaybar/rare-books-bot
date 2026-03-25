"""Pydantic response models for metadata quality endpoints.

These models define the API contract for the /metadata/* routes,
serializing audit and clustering data structures for JSON responses.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Coverage response models
# ---------------------------------------------------------------------------


class ConfidenceBandResponse(BaseModel):
    """A single confidence band with its record count."""

    band_label: str = Field(..., description="Band label, e.g. '0.00', '0.80'")
    lower: float = Field(..., description="Inclusive lower bound")
    upper: float = Field(..., description="Exclusive upper bound (except last band)")
    count: int = Field(..., description="Number of records in this band")


class MethodBreakdownResponse(BaseModel):
    """Count of records by normalization method."""

    method: str = Field(..., description="Normalization method name")
    count: int = Field(..., description="Number of records using this method")


class FlaggedItemResponse(BaseModel):
    """A single low-confidence/flagged value with its frequency."""

    raw_value: str = Field(..., description="Original raw value from MARC data")
    norm_value: Optional[str] = Field(None, description="Normalized value (if any)")
    confidence: float = Field(..., description="Confidence score")
    method: Optional[str] = Field(None, description="Normalization method used")
    frequency: int = Field(..., description="Number of records with this value")


class FieldCoverageResponse(BaseModel):
    """Coverage statistics for a single normalized field."""

    total_records: int = Field(..., description="Total records in the table")
    non_null_count: int = Field(..., description="Records with non-null confidence")
    null_count: int = Field(..., description="Records with null confidence")
    confidence_distribution: List[ConfidenceBandResponse] = Field(
        ..., description="Distribution of records across confidence bands"
    )
    method_distribution: List[MethodBreakdownResponse] = Field(
        ..., description="Distribution of normalization methods used"
    )
    flagged_items: List[FlaggedItemResponse] = Field(
        ..., description="Low-confidence or problematic values"
    )


class CoverageResponse(BaseModel):
    """Full normalization coverage report across all fields."""

    date_coverage: FieldCoverageResponse
    place_coverage: FieldCoverageResponse
    publisher_coverage: FieldCoverageResponse
    agent_name_coverage: FieldCoverageResponse
    agent_role_coverage: FieldCoverageResponse
    total_imprint_rows: int = Field(..., description="Total rows in imprints table")
    total_agent_rows: int = Field(..., description="Total rows in agents table")


# ---------------------------------------------------------------------------
# Issues response models
# ---------------------------------------------------------------------------


class IssueRecord(BaseModel):
    """A single record with a low-confidence normalization."""

    mms_id: str = Field(..., description="Record MMS identifier")
    raw_value: str = Field(..., description="Original raw value")
    norm_value: Optional[str] = Field(None, description="Normalized value")
    confidence: float = Field(..., description="Confidence score")
    method: Optional[str] = Field(None, description="Normalization method used")


class IssuesResponse(BaseModel):
    """Paginated list of low-confidence issue records."""

    field: str = Field(..., description="Field name queried")
    max_confidence: float = Field(..., description="Confidence threshold used")
    total: int = Field(..., description="Total matching records")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")
    items: List[IssueRecord] = Field(..., description="Issue records in this page")


# ---------------------------------------------------------------------------
# Unmapped response models
# ---------------------------------------------------------------------------


class UnmappedValue(BaseModel):
    """A raw value that does not map to any canonical form."""

    raw_value: str = Field(..., description="Original raw value")
    frequency: int = Field(..., description="Number of records with this value")
    confidence: float = Field(..., description="Confidence score")
    method: Optional[str] = Field(None, description="Normalization method used")


# ---------------------------------------------------------------------------
# Methods distribution response models
# ---------------------------------------------------------------------------


class MethodDistribution(BaseModel):
    """Distribution entry for a normalization method."""

    method: str = Field(..., description="Method name")
    count: int = Field(..., description="Number of records using this method")
    percentage: float = Field(..., description="Percentage of total records")


# ---------------------------------------------------------------------------
# Cluster response models
# ---------------------------------------------------------------------------


class ClusterValueResponse(BaseModel):
    """A single value within a cluster."""

    raw_value: str = Field(..., description="Original raw value")
    frequency: int = Field(..., description="Occurrence count")
    confidence: float = Field(..., description="Confidence score")
    method: str = Field(..., description="Normalization method used")


class ClusterResponse(BaseModel):
    """A group of related low-confidence/unmapped values."""

    cluster_id: str = Field(..., description="Unique cluster identifier")
    field: str = Field(..., description="Metadata field (date, place, publisher, agent)")
    cluster_type: str = Field(..., description="Type of clustering applied")
    values: List[ClusterValueResponse] = Field(..., description="Values in this cluster")
    proposed_canonical: Optional[str] = Field(
        None, description="Proposed canonical form (if determinable)"
    )
    evidence: Dict[str, Any] = Field(
        default_factory=dict, description="Supporting evidence for the cluster"
    )
    priority_score: float = Field(..., description="Priority score (sum of frequencies)")
    total_records_affected: int = Field(
        ..., description="Total records affected by this cluster"
    )


# ---------------------------------------------------------------------------
# Correction request/response models
# ---------------------------------------------------------------------------


class CorrectionRequest(BaseModel):
    """Request body for submitting a single normalization correction."""

    field: str = Field(
        ..., description="Metadata field: 'place', 'publisher', or 'agent'"
    )
    raw_value: str = Field(..., description="Raw value to map")
    canonical_value: str = Field(..., description="Canonical normalized value")
    evidence: str = Field("", description="Evidence or justification for the mapping")
    source: str = Field(
        "human", description="Source of correction: 'human' or 'agent'"
    )


class CorrectionResponse(BaseModel):
    """Response after applying a single correction."""

    success: bool = Field(..., description="Whether the correction was applied")
    alias_map_updated: str = Field(
        ..., description="Path to the alias map file that was updated"
    )
    records_affected: int = Field(
        ..., description="Number of database records affected by this correction"
    )


class CorrectionHistoryEntry(BaseModel):
    """A single entry in the correction review log."""

    timestamp: str = Field(..., description="ISO 8601 timestamp of the correction")
    field: str = Field(..., description="Metadata field corrected")
    raw_value: str = Field(..., description="Raw value that was mapped")
    canonical_value: str = Field(..., description="Canonical value assigned")
    evidence: str = Field("", description="Evidence or justification")
    source: str = Field("human", description="Source: 'human' or 'agent'")
    action: str = Field("approved", description="Action taken")


class CorrectionHistoryResponse(BaseModel):
    """Paginated list of correction history entries."""

    total: int = Field(..., description="Total number of entries")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Page offset")
    entries: List[CorrectionHistoryEntry] = Field(
        ..., description="History entries in this page"
    )


class BatchCorrectionRequest(BaseModel):
    """Request body for submitting multiple corrections at once."""

    corrections: List[CorrectionRequest] = Field(
        ..., description="List of corrections to apply"
    )


class BatchCorrectionResult(BaseModel):
    """Result for a single correction within a batch."""

    raw_value: str = Field(..., description="Raw value that was mapped")
    canonical_value: str = Field(..., description="Canonical value assigned")
    success: bool = Field(..., description="Whether this correction was applied")
    records_affected: int = Field(
        0, description="Number of database records affected"
    )
    error: Optional[str] = Field(None, description="Error message if not successful")


class BatchCorrectionResponse(BaseModel):
    """Response after applying a batch of corrections."""

    total_applied: int = Field(..., description="Number of corrections applied")
    total_skipped: int = Field(..., description="Number of corrections skipped")
    total_records_affected: int = Field(
        ..., description="Total database records affected across all corrections"
    )
    results: List[BatchCorrectionResult] = Field(
        ..., description="Per-correction results"
    )


# ---------------------------------------------------------------------------
# Primo URL models
# ---------------------------------------------------------------------------


class PrimoUrlRequest(BaseModel):
    """Request body for generating Primo URLs from MMS IDs."""

    mms_ids: List[str] = Field(..., description="List of MMS IDs to generate URLs for")
    base_url: Optional[str] = Field(
        None, description="Override Primo base URL (uses PRIMO_BASE_URL env var if omitted)"
    )


class PrimoUrlEntry(BaseModel):
    """A single MMS ID to Primo URL mapping."""

    mms_id: str = Field(..., description="The MMS ID")
    primo_url: str = Field(..., description="Generated Primo discovery URL")


class PrimoUrlResponse(BaseModel):
    """Response containing generated Primo URLs."""

    urls: List[PrimoUrlEntry] = Field(..., description="List of MMS ID to Primo URL mappings")


# ---------------------------------------------------------------------------
# Agent chat models
# ---------------------------------------------------------------------------


class AgentChatRequest(BaseModel):
    """Request body for agent chat endpoint."""

    field: str = Field(
        ..., description="Metadata field: 'place', 'date', 'publisher', or 'agent'"
    )
    message: str = Field(
        "", description="User message. Empty or 'analyze' triggers analysis."
    )
    session_id: Optional[str] = Field(
        None, description="Optional session ID for conversation continuity"
    )


class AgentProposal(BaseModel):
    """A single LLM-proposed canonical mapping."""

    raw_value: str = Field(..., description="Original raw value")
    canonical_value: str = Field(..., description="Proposed canonical form")
    confidence: float = Field(..., description="Confidence score of the proposal")
    reasoning: str = Field(..., description="LLM reasoning for the mapping")
    evidence_sources: List[str] = Field(
        default_factory=list, description="Sources of evidence used"
    )


class AgentClusterSummary(BaseModel):
    """Summary of a single cluster for the chat response."""

    cluster_id: str = Field(..., description="Unique cluster identifier")
    cluster_type: str = Field(..., description="Type of clustering applied")
    value_count: int = Field(..., description="Number of values in the cluster")
    total_records: int = Field(
        ..., description="Total records affected by this cluster"
    )
    priority_score: float = Field(..., description="Priority score for review ordering")


class AgentChatResponse(BaseModel):
    """Response from the agent chat endpoint."""

    response: str = Field(..., description="Natural language response text")
    proposals: List[AgentProposal] = Field(
        default_factory=list, description="LLM-proposed mappings (if any)"
    )
    clusters: List[AgentClusterSummary] = Field(
        default_factory=list, description="Cluster summaries (if any)"
    )
    field: str = Field(..., description="Metadata field that was queried")
    action: str = Field(
        ..., description="Action performed: 'analysis', 'proposals', or 'answer'"
    )


# ---------------------------------------------------------------------------
# Publisher authority response models
# ---------------------------------------------------------------------------


class PublisherVariantResponse(BaseModel):
    """A single name variant for a publisher authority."""

    id: Optional[int] = Field(None, description="Variant record ID")
    variant_form: str = Field(..., description="The name form as it appears in records")
    script: str = Field(..., description="Script type: latin, hebrew, arabic, other")
    language: Optional[str] = Field(None, description="ISO 639 language code")
    is_primary: bool = Field(..., description="Whether this is the primary display form")


class PublisherAuthorityResponse(BaseModel):
    """A canonical publisher identity with metadata summary."""

    id: int = Field(..., description="Authority record ID")
    canonical_name: str = Field(..., description="Canonical English name")
    type: str = Field(
        ...,
        description="Publisher type: printing_house, private_press, "
        "modern_publisher, bibliophile_society, unknown_marker, unresearched",
    )
    confidence: float = Field(..., description="Confidence score (0.0-1.0)")
    dates_active: Optional[str] = Field(None, description="Active date range string")
    location: Optional[str] = Field(None, description="Primary location")
    is_missing_marker: bool = Field(
        ..., description="True if this represents 'publisher unknown'"
    )
    variant_count: int = Field(..., description="Number of name variants")
    imprint_count: int = Field(..., description="Number of linked imprints")
    variants: List[PublisherVariantResponse] = Field(
        default_factory=list, description="Name variants for this authority"
    )
    viaf_id: Optional[str] = Field(None, description="VIAF authority ID")
    wikidata_id: Optional[str] = Field(None, description="Wikidata Q-number")
    cerl_id: Optional[str] = Field(None, description="CERL Thesaurus ID")


class PublisherAuthorityListResponse(BaseModel):
    """Paginated list of publisher authorities."""

    total: int = Field(..., description="Total number of matching authorities")
    items: List[PublisherAuthorityResponse] = Field(
        ..., description="Publisher authority records"
    )


# ---------------------------------------------------------------------------
# Publisher CRUD request/response models
# ---------------------------------------------------------------------------


class CreatePublisherRequest(BaseModel):
    """Request body for creating a new publisher authority."""

    canonical_name: str = Field(..., min_length=1, description="Canonical name")
    type: str = Field(
        "unresearched",
        description="Publisher type: printing_house, private_press, "
        "modern_publisher, bibliophile_society, unknown_marker, unresearched",
    )
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confidence score")
    location: Optional[str] = Field(None, description="Primary location")
    dates_active: Optional[str] = Field(None, description="Active date range string")
    notes: Optional[str] = Field(None, description="Notes")


class UpdatePublisherRequest(BaseModel):
    """Request body for updating a publisher authority."""

    canonical_name: Optional[str] = Field(None, min_length=1, description="Canonical name")
    type: Optional[str] = Field(None, description="Publisher type")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score")
    location: Optional[str] = Field(None, description="Primary location")
    dates_active: Optional[str] = Field(None, description="Active date range string")
    notes: Optional[str] = Field(None, description="Notes")


class CreateVariantRequest(BaseModel):
    """Request body for adding a variant to a publisher authority."""

    variant_form: str = Field(..., min_length=1, description="Variant name form")
    script: str = Field("latin", description="Script type: latin, hebrew, arabic, other")
    language: Optional[str] = Field(None, description="ISO 639 language code")


class MatchPreviewResponse(BaseModel):
    """Response for match preview endpoint."""

    variant_form: str = Field(..., description="The variant form queried")
    matching_imprints: int = Field(..., description="Number of matching imprint rows")


class DeleteResponse(BaseModel):
    """Generic deletion confirmation."""

    success: bool = Field(..., description="Whether the deletion succeeded")
    message: str = Field(..., description="Human-readable result message")
