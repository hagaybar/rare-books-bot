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
    has_wikipedia: bool = False
    primary_role: str | None = None


class MapEdge(BaseModel):
    source: str
    target: str
    type: str
    confidence: float
    relationship: str | None = None
    bidirectional: bool = False


class MapMeta(BaseModel):
    total_agents: int
    showing: int
    total_edges: int
    category_limited: bool = False
    category_total: int = 0


class MapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    meta: MapMeta


class AgentConnection(BaseModel):
    agent_norm: str
    display_name: str
    type: str
    relationship: str | None = None
    confidence: float


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
    primo_url: str | None = None
    external_links: dict[str, str] = Field(default_factory=dict)
