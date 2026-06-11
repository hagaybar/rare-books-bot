"""Pydantic models for Network Map Explorer API."""
from pydantic import BaseModel, Field


class MapNode(BaseModel):
    agent_norm: str
    display_name: str
    lat: float | None = None
    lon: float | None = None
    place_norm: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    occupations: list[str] = Field(default_factory=list)
    connection_count: int = 0
    filtered_count: int = 0  # edges within the active connection-type filter
    record_count: int = 0  # holdings in this collection
    has_wikipedia: bool = False
    primary_role: str | None = None
    node_type: str = "person"  # 'person' | 'publisher' (issue #27)
    community: str | None = None  # intellectual-community color facet (issue #28)


class MapEdge(BaseModel):
    source: str
    target: str
    type: str
    confidence: float
    relationship: str | None = None
    evidence: str | None = None
    bidirectional: bool = False


class MapMeta(BaseModel):
    total_agents: int
    showing: int
    total_edges: int
    communities: list[str] = Field(default_factory=list)  # legend palette order (issue #28)


class MapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    meta: MapMeta


class AgentConnection(BaseModel):
    agent_norm: str
    display_name: str
    type: str
    relationship: str | None = None
    evidence: str | None = None
    confidence: float


class AgentWork(BaseModel):
    """A book in the collection associated with an agent or place."""
    mms_id: str
    title: str | None = None
    date_label: str | None = None
    place_display: str | None = None
    publisher_display: str | None = None
    role_norm: str | None = None
    primo_url: str | None = None


class AgentDetail(BaseModel):
    agent_norm: str
    display_name: str
    lat: float | None = None
    lon: float | None = None
    place_norm: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    occupations: list[str] = Field(default_factory=list)
    wikipedia_summary: str | None = None
    connections: list[AgentConnection] = Field(default_factory=list)
    record_count: int = 0
    works: list[AgentWork] = Field(default_factory=list)
    primo_url: str | None = None
    external_links: dict[str, str] = Field(default_factory=dict)
    node_type: str = "person"


class PlaceDetail(BaseModel):
    """Books printed in a given place (issue #29)."""
    place_norm: str
    total: int = 0
    works: list[AgentWork] = Field(default_factory=list)
