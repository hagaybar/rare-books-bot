"""Pydantic models for chat session management.

This module defines the core data structures for multi-turn conversations:
- Message: Individual conversation turn with optional QueryPlan/CandidateSet
- ChatSession: Conversation session with message history and context
- ChatResponse: Response from chatbot to user
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from scripts.schemas import CandidateSet, QueryPlan


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
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}


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
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: v.isoformat()}

    def add_message(self, message: Message) -> None:
        """Add message and update timestamp.

        Args:
            message: Message to add to conversation history
        """
        self.messages.append(message)
        self.updated_at = datetime.utcnow()

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
    """

    message: str
    candidate_set: Optional[CandidateSet] = None
    suggested_followups: List[str] = Field(default_factory=list)
    clarification_needed: Optional[str] = None
    session_id: str
