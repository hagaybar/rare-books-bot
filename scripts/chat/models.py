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
    metadata: Dict[str, Any] = Field(default_factory=dict)
