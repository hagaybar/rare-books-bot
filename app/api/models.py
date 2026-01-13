"""Request and response models for FastAPI endpoints.

These Pydantic models define the API contract between clients and the server.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from scripts.chat.models import ChatResponse


class ChatRequest(BaseModel):
    """Request to /chat endpoint.

    Attributes:
        message: User's natural language query
        session_id: Optional session ID (creates new session if not provided)
        context: Optional context to merge into session
    """

    message: str = Field(..., min_length=1, description="User's natural language query")
    session_id: Optional[str] = Field(
        None, description="Session ID (creates new if not provided)"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context for the query"
    )


class ChatResponseAPI(BaseModel):
    """Response from /chat endpoint.

    Wraps ChatResponse with additional API metadata.

    Attributes:
        success: Whether the request was successful
        response: ChatResponse object with message and results
        error: Optional error message if success=False
    """

    success: bool = Field(..., description="Whether the request succeeded")
    response: Optional[ChatResponse] = Field(None, description="Chat response object")
    error: Optional[str] = Field(None, description="Error message if failed")


class HealthResponse(BaseModel):
    """Response from /health endpoint.

    Attributes:
        status: Health status (healthy, degraded, unhealthy)
        database_connected: Whether database connection is working
        session_store_ok: Whether session store is operational
    """

    status: str = Field(..., description="Overall health status")
    database_connected: bool = Field(..., description="Database connection status")
    session_store_ok: bool = Field(..., description="Session store operational status")
