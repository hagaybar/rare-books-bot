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
    token_saving: bool = Field(
        True, description="Use lean prompt builder to reduce token usage"
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
        executor_ready: Whether required DB tables for the executor exist
    """

    status: str = Field(..., description="Overall health status")
    database_connected: bool = Field(..., description="Database connection status")
    session_store_ok: bool = Field(..., description="Session store operational status")
    executor_ready: bool = Field(False, description="Whether executor required tables exist")


class HealthExtendedResponse(BaseModel):
    """Response from /health/extended endpoint.

    Provides detailed system information about database files and their status.

    Attributes:
        db_file_size_bytes: Size of the bibliographic database in bytes
        db_last_modified: ISO-8601 timestamp of last database modification
        qa_db_exists: Whether the QA database file exists
        qa_db_size_bytes: Size of the QA database in bytes (0 if not present)
    """

    db_file_size_bytes: int = Field(..., description="Bibliographic DB file size in bytes")
    db_last_modified: Optional[str] = Field(None, description="ISO-8601 timestamp of last DB modification")
    qa_db_exists: bool = Field(..., description="Whether QA database exists")
    qa_db_size_bytes: int = Field(0, description="QA database file size in bytes")


class ModelPair(BaseModel):
    """A specific interpreter + narrator model configuration."""
    interpreter: str = Field(..., description="Model for interpreter stage")
    narrator: str = Field(..., description="Model for narrator stage")


class CompareRequest(BaseModel):
    """Request to /chat/compare endpoint."""
    message: str = Field(..., min_length=1, description="User's query")
    configs: list[ModelPair] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Model configurations to compare (max 3)",
    )
    session_id: Optional[str] = Field(None, description="Optional session ID")
    token_saving: bool = Field(True, description="Use lean prompt builder")


class ComparisonMetrics(BaseModel):
    """Metrics for a single comparison result."""
    latency_ms: int
    cost_usd: float
    tokens: Dict[str, int]  # {"input": N, "output": N}


class ComparisonResult(BaseModel):
    """One model configuration's result."""
    config: ModelPair
    response: Optional[ChatResponse]
    metrics: ComparisonMetrics
    error: Optional[str] = None


class CompareResponse(BaseModel):
    """Response from /chat/compare endpoint."""
    comparisons: list[ComparisonResult]
