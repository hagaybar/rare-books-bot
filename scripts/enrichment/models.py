"""Pydantic models for enrichment pipeline.

Defines data structures for:
- Enrichment requests and results
- Entity types and sources
- Cache entries
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class EntityType(str, Enum):
    """Types of entities that can be enriched."""
    AGENT = "agent"           # Person, organization, meeting
    PLACE = "place"           # Geographic location
    PUBLISHER = "publisher"   # Publisher/printer
    SUBJECT = "subject"       # Subject heading
    WORK = "work"             # Work/title


class EnrichmentSource(str, Enum):
    """External sources for enrichment data."""
    NLI = "nli"               # National Library of Israel authority
    WIKIDATA = "wikidata"     # Wikidata SPARQL
    VIAF = "viaf"             # Virtual International Authority File
    LOC = "loc"               # Library of Congress
    ISNI = "isni"             # International Standard Name Identifier
    CACHE = "cache"           # Local cache (not an external source)


class ExternalIdentifier(BaseModel):
    """An external identifier for an entity."""
    model_config = ConfigDict(extra='forbid')

    source: EnrichmentSource
    identifier: str
    url: Optional[str] = None


class EnrichmentRequest(BaseModel):
    """Request to enrich an entity.

    Can be initiated from:
    - Agent exploration ("tell me about Aldus Manutius")
    - MARC authority URI in $0 subfield
    - Manual enrichment request
    """
    model_config = ConfigDict(extra='forbid')

    entity_type: EntityType
    entity_value: str  # Name or identifier to look up
    nli_authority_id: Optional[str] = None  # NLI authority ID if available
    nli_authority_uri: Optional[str] = None  # Full URI from $0 subfield
    preferred_sources: List[EnrichmentSource] = Field(
        default_factory=lambda: [EnrichmentSource.WIKIDATA, EnrichmentSource.VIAF]
    )
    priority: int = Field(default=0, ge=0, le=10)  # For queue ordering

    def extract_nli_id_from_uri(self) -> Optional[str]:
        """Extract NLI ID from authority URI.

        Example:
        https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld
        -> 987007261327805171
        """
        if self.nli_authority_id:
            return self.nli_authority_id

        if self.nli_authority_uri:
            # Extract ID from URI pattern
            uri = self.nli_authority_uri
            if "/authorities/" in uri:
                # Get part after /authorities/ and before .jsonld
                part = uri.split("/authorities/")[-1]
                if part.endswith(".jsonld"):
                    return part[:-7]
                return part.split(".")[0]

        return None


class PersonInfo(BaseModel):
    """Biographical information for a person."""
    model_config = ConfigDict(extra='forbid')

    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    birth_place: Optional[str] = None
    death_place: Optional[str] = None
    nationality: Optional[str] = None
    occupations: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class PlaceInfo(BaseModel):
    """Geographic information for a place."""
    model_config = ConfigDict(extra='forbid')

    country: Optional[str] = None
    coordinates: Optional[Dict[str, float]] = None  # {"lat": 41.9, "lon": 12.5}
    modern_name: Optional[str] = None
    historical_names: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class EnrichmentResult(BaseModel):
    """Result of enrichment lookup.

    Contains data from one or more external sources.
    """
    model_config = ConfigDict(
        extra='forbid',
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    entity_type: EntityType
    entity_value: str
    normalized_key: str  # Normalized lookup key

    # External identifiers found
    external_ids: List[ExternalIdentifier] = Field(default_factory=list)

    # Primary identifiers
    wikidata_id: Optional[str] = None
    viaf_id: Optional[str] = None
    isni_id: Optional[str] = None
    loc_id: Optional[str] = None
    nli_id: Optional[str] = None

    # Entity-specific info
    person_info: Optional[PersonInfo] = None
    place_info: Optional[PlaceInfo] = None

    # General fields
    label: Optional[str] = None  # Display label
    description: Optional[str] = None
    image_url: Optional[str] = None
    wikipedia_url: Optional[str] = None
    external_links: Dict[str, str] = Field(default_factory=dict)

    # Metadata
    sources_used: List[EnrichmentSource] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data: Optional[Dict[str, Any]] = None  # For debugging


class NLIAuthorityIdentifiers(BaseModel):
    """Identifiers extracted from NLI authority or Wikidata.

    Primary method is now Wikidata SPARQL query using P8189 (NLI J9U ID).
    """
    model_config = ConfigDict(extra='forbid')

    nli_id: str
    nli_uri: Optional[str] = None  # Full JSONLD URI
    wikidata_id: Optional[str] = None
    viaf_id: Optional[str] = None
    isni_id: Optional[str] = None
    loc_id: Optional[str] = None
    other_ids: Dict[str, str] = Field(default_factory=dict)

    # Metadata
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fetch_method: str = "unknown"  # "wikidata_sparql", "manual_mapping", "jsonld"


class CacheEntry(BaseModel):
    """Cache entry for enrichment data."""
    model_config = ConfigDict(
        extra='forbid',
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    entity_type: EntityType
    normalized_key: str
    source: EnrichmentSource
    data: Dict[str, Any]
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fetched_at: datetime
    expires_at: Optional[datetime] = None
