"""Pydantic models for chat session management.

This module defines the core data structures for multi-turn conversations:
- Message: Individual conversation turn with optional QueryPlan/CandidateSet
- ChatSession: Conversation session with message history and context
- ChatResponse: Response from chatbot to user

Two-Phase Conversation Support:
- ConversationPhase: Tracks whether in query definition or corpus exploration
- ActiveSubgroup: The currently defined CandidateSet being explored
- ExplorationIntent: Types of exploration requests in Phase 2
- UserGoal: Elicited user goals for corpus exploration
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

from scripts.schemas import CandidateSet, QueryPlan


# =============================================================================
# Two-Phase Conversation Enums and Models
# =============================================================================

class ConversationPhase(str, Enum):
    """Current phase of the conversation.

    QUERY_DEFINITION: User is defining their search criteria (Phase 1)
    CORPUS_EXPLORATION: User is exploring a defined subgroup (Phase 2)
    """
    QUERY_DEFINITION = "query_definition"
    CORPUS_EXPLORATION = "corpus_exploration"


class ExplorationIntent(str, Enum):
    """Types of exploration intents in Phase 2.

    These classify what the user wants to do with the active subgroup.
    """
    METADATA_QUESTION = "metadata_question"    # "How many books are in Latin?"
    AGGREGATION = "aggregation"                # "Top 10 publishers"
    ENRICHMENT_REQUEST = "enrichment_request"  # "Tell me about Aldus Manutius"
    RECOMMENDATION = "recommendation"          # "Most relevant for astronomy"
    COMPARISON = "comparison"                  # "Compare Paris vs London"
    REFINEMENT = "refinement"                  # "Only Latin books"
    CROSS_REFERENCE = "cross_reference"          # "Show connections between agents"
    CURATION = "curation"                      # "Curated selection for exhibit"
    NEW_QUERY = "new_query"                    # "Let's search for something else"


class ActiveSubgroup(BaseModel):
    """The currently defined subgroup (CandidateSet) being explored.

    Created when transitioning from Phase 1 to Phase 2. Contains the
    CandidateSet and metadata about how it was defined.

    Attributes:
        candidate_set: The CandidateSet with matched records
        defining_query: The original query that defined this subgroup
        filter_summary: Natural language summary of the filters
        record_ids: List of MMS IDs in this subgroup (for efficient queries)
        created_at: When this subgroup was defined
    """
    candidate_set: CandidateSet
    defining_query: str
    filter_summary: str
    record_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    def __init__(self, **data):
        super().__init__(**data)
        # Extract record_ids from candidate_set if not provided
        if not self.record_ids and self.candidate_set:
            object.__setattr__(
                self,
                'record_ids',
                [c.record_id for c in self.candidate_set.candidates]
            )


class UserGoal(BaseModel):
    """Elicited user goal for corpus exploration.

    Captured when the user expresses what they want to achieve with
    the corpus (e.g., "find books for my thesis on astronomy").

    Attributes:
        goal_type: Category of goal (find_specific, analyze, compare, discover)
        description: Natural language description of the goal
        elicited_at: When this goal was captured
    """
    goal_type: str  # "find_specific", "analyze_corpus", "compare", "discover"
    description: str
    elicited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


# =============================================================================
# Core Chat Models
# =============================================================================


class Message(BaseModel):
    """Single message in a conversation.

    Attributes:
        role: Who sent the message (user, assistant, system)
        content: Text content of the message
        query_plan: Optional QueryPlan if this was a search query
        candidate_set: Optional results if this message has search results
        timestamp: When the message was created
    """

    role: Literal["user", "assistant", "system"]
    content: str
    query_plan: Optional[QueryPlan] = None
    candidate_set: Optional[CandidateSet] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )


class ChatSession(BaseModel):
    """Conversation session with message history and context.

    Attributes:
        session_id: Unique identifier (UUID)
        user_id: Optional user identifier for multi-user support
        created_at: Session creation timestamp
        updated_at: Last activity timestamp
        messages: Chronologically ordered conversation history
        context: Carry-forward state for multi-turn conversations
        metadata: Extensible metadata (tags, client info, etc.)
    """

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()}
    )

    def add_message(self, message: Message) -> None:
        """Add message and update timestamp.

        Args:
            message: Message to add to conversation history
        """
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

    def get_recent_messages(self, n: int = 5) -> List[Message]:
        """Get last N messages.

        Args:
            n: Number of recent messages to retrieve

        Returns:
            List of most recent messages (up to n)
        """
        return self.messages[-n:] if len(self.messages) > n else self.messages


class ChatResponse(BaseModel):
    """Response from chatbot to user.

    Attributes:
        message: Natural language response text
        candidate_set: Optional search results
        suggested_followups: Suggested next queries
        clarification_needed: Request for user clarification if query ambiguous
        session_id: Session identifier for multi-turn tracking
        phase: Current conversation phase (query_definition or corpus_exploration)
        confidence: Confidence score from intent interpretation (0.0-1.0)
        metadata: Additional response metadata (visualization hints, etc.)
    """

    message: str
    candidate_set: Optional[CandidateSet] = None
    suggested_followups: List[str] = Field(default_factory=list)
    clarification_needed: Optional[str] = None
    session_id: str
    phase: Optional[ConversationPhase] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    thematic_context: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Cross-Reference and Comparison Models (E3)
# =============================================================================


class Connection(BaseModel):
    """A discovered relationship between two agents.

    Represents an edge in the agent relationship graph, with evidence
    and confidence indicating how the relationship was determined.

    Attributes:
        agent_a: Display label for first agent
        agent_b: Display label for second agent
        relationship_type: One of teacher_of, student_of, co_publication,
                          same_place_period, network_neighbor
        evidence: Human-readable description with source citation
        confidence: Confidence score (teacher_of=0.90, co_publication=0.85,
                   same_place_period=0.70)
        agent_a_wikidata_id: Optional Wikidata ID for agent A
        agent_b_wikidata_id: Optional Wikidata ID for agent B
    """

    agent_a: str
    agent_b: str
    relationship_type: str
    evidence: str
    confidence: float
    agent_a_wikidata_id: Optional[str] = None
    agent_b_wikidata_id: Optional[str] = None


class AgentNode(BaseModel):
    """A node in the agent relationship graph.

    Built from authority_enrichment.person_info, representing a single
    agent with their biographical data and connections.

    Attributes:
        label: Display name (from enrichment label)
        agent_norm: Normalized agent name (from agents table)
        authority_uri: NLI or other authority URI
        wikidata_id: Wikidata entity ID
        birth_year: Year of birth (if known)
        death_year: Year of death (if known)
        birth_place: Place of birth (if known)
        occupations: List of occupations
        teachers: List of teacher names (from person_info)
        students: List of student names (from person_info)
        notable_works: List of notable works
        record_count: Number of records this agent appears in
    """

    label: str
    agent_norm: str
    authority_uri: Optional[str] = None
    wikidata_id: Optional[str] = None
    birth_year: Optional[int] = None
    death_year: Optional[int] = None
    birth_place: Optional[str] = None
    occupations: List[str] = Field(default_factory=list)
    teachers: List[str] = Field(default_factory=list)
    students: List[str] = Field(default_factory=list)
    notable_works: List[str] = Field(default_factory=list)
    record_count: int = 0


class ComparisonFacets(BaseModel):
    """Multi-faceted comparison data for side-by-side analysis.

    Attributes:
        counts: Record counts per compared value
        date_ranges: Date ranges per compared value
        language_distribution: Language counts per compared value
        top_agents: Top agents per compared value
        top_subjects: Top subjects per compared value
        shared_agents: Agents appearing in multiple compared values
        subject_overlap: Subjects appearing in multiple compared values
    """

    counts: Dict[str, int] = Field(default_factory=dict)
    date_ranges: Dict[str, Any] = Field(default_factory=dict)
    language_distribution: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    top_agents: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    top_subjects: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    shared_agents: List[str] = Field(default_factory=list)
    subject_overlap: List[str] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    """Result of a multi-faceted comparison between field values.

    Attributes:
        field: The field being compared (e.g., 'place_norm', 'publisher_norm')
        values: The values being compared (e.g., ['venice', 'amsterdam'])
        facets: Multi-faceted comparison data
        total_in_subgroup: Total records across all compared values
    """

    field: str
    values: List[str]
    facets: ComparisonFacets
    total_in_subgroup: int = 0
