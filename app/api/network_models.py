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
    active_start: int | None = None  # earliest imprint year (issue #32)
    active_end: int | None = None  # latest imprint year (issue #32)


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
    year_min: int | None = None  # imprint-date domain for the time slider (issue #32)
    year_max: int | None = None


class MapResponse(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]
    meta: MapMeta


class EgoMeta(BaseModel):
    truncated: bool = False  # neighbours exceeded the cap (issue #31)
    total_neighbors: int = 0
    showing: int = 0


class EgoResponse(BaseModel):
    focal: str
    nodes: list[MapNode]
    edges: list[MapEdge]
    meta: EgoMeta


class PlaceMarker(BaseModel):
    """An aggregated printing city for the place-first map (place redesign)."""
    place_norm: str
    place_display: str | None = None
    lat: float
    lon: float
    record_count: int = 0  # books printed here
    agent_count: int = 0  # people/presses placed here
    year_min: int | None = None
    year_max: int | None = None
    decades: list["DecadeCount"] = Field(default_factory=list)  # time-slider weights


class NetworkPortraitLLM(BaseModel):
    """LLM output schema for the ego-network portrait (creative AI layer)."""
    epithet: str  # e.g. "The man who resurrected the chroniclers" (<= ~8 words)
    reading: str  # 2-3 grounded sentences interpreting the network shape
    next_thread: str  # one concrete suggestion naming a neighbour to explore


class InterpretRequest(BaseModel):
    agent_norm: str
    connection_types: list[str] = Field(default_factory=list)


class NetworkPortrait(BaseModel):
    epithet: str
    reading: str
    next_thread: str
    cached: bool = False


class PathResponse(BaseModel):
    source: str
    target: str
    found: bool = False
    hops: int = 0
    nodes: list[MapNode] = Field(default_factory=list)  # in path order (issue #33)
    edges: list[MapEdge] = Field(default_factory=list)  # one per hop, source→target along the path


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
    name_alt: str | None = None  # name in the opposite script (issue #30)
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


class DecadeCount(BaseModel):
    decade: int
    count: int


class NameCount(BaseModel):
    name: str
    count: int
    agent_norm: str | None = None  # network node (e.g. pub:…) when one exists — enables pivots


class AgentCount(BaseModel):
    agent_norm: str
    display_name: str
    count: int


class SubjectCount(BaseModel):
    subject: str
    count: int


class TopicMarker(BaseModel):
    """One subject bubble in the topic constellation."""
    subject: str  # tidy display form ('Bible — Texts')
    root: str  # first LCSH segment, period-variants merged ('Bible')
    count: int
    peak_decade: int | None = None  # decade with most books — drives era color
    value_he: str | None = None
    kind: str = "topic"  # 'topic' (what books are about) | 'form' (what they are)


class TopicDetail(BaseModel):
    """Topic profile — the subject-axis sibling of PlaceDetail."""
    subject: str
    value_he: str | None = None
    total: int = 0
    decades: list[DecadeCount] = Field(default_factory=list)
    top_places: list[NameCount] = Field(default_factory=list)
    top_agents: list[AgentCount] = Field(default_factory=list)
    works: list[AgentWork] = Field(default_factory=list)


class PlaceDetail(BaseModel):
    """Books printed in a given place (issue #29) + city profile (place redesign)."""
    place_norm: str
    place_display: str | None = None
    total: int = 0
    agent_count: int = 0
    year_min: int | None = None
    year_max: int | None = None
    decades: list[DecadeCount] = Field(default_factory=list)
    top_publishers: list[NameCount] = Field(default_factory=list)
    top_agents: list[AgentCount] = Field(default_factory=list)
    top_subjects: list[SubjectCount] = Field(default_factory=list)
    works: list[AgentWork] = Field(default_factory=list)
