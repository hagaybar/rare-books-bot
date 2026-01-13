"""FastAPI application for conversational chatbot interface.

This module provides the HTTP API layer that:
- Receives natural language queries via /chat endpoint
- Routes queries through M4 query pipeline (compile + execute)
- Manages multi-turn conversation sessions
- Returns structured responses with evidence
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.models import ChatRequest, ChatResponseAPI, HealthResponse
from scripts.chat.models import ChatResponse, Message
from scripts.chat.session_store import SessionStore
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.query.exceptions import QueryCompilationError
from scripts.utils.logger import LoggerManager

# Initialize logger
logger = LoggerManager.get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Rare Books Discovery API",
    description="Conversational interface for bibliographic discovery over MARC records",
    version="0.1.0",
)

# Add CORS middleware (allow all origins for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state (initialized on startup)
session_store: Optional[SessionStore] = None
db_path: Optional[Path] = None


def get_session_store() -> SessionStore:
    """Get session store instance.

    Returns:
        SessionStore instance

    Raises:
        HTTPException: If session store not initialized
    """
    if session_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session store not initialized",
        )
    return session_store


def get_db_path() -> Path:
    """Get bibliographic database path.

    Returns:
        Path to bibliographic.db

    Raises:
        HTTPException: If database path not configured
    """
    if db_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database path not configured",
        )
    return db_path


@app.on_event("startup")
async def startup_event():
    """Initialize application state on startup."""
    global session_store, db_path

    # Get paths from environment or use defaults
    sessions_db = Path(os.getenv("SESSIONS_DB_PATH", "data/chat/sessions.db"))
    bib_db = Path(os.getenv("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db"))

    # Ensure directories exist
    sessions_db.parent.mkdir(parents=True, exist_ok=True)

    # Initialize session store
    session_store = SessionStore(sessions_db)
    db_path = bib_db

    logger.info(
        "API started",
        extra={
            "sessions_db": str(sessions_db),
            "bibliographic_db": str(bib_db),
        },
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if session_store is not None:
        session_store.close()
    logger.info("API shutdown")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        HealthResponse with status of database and session store
    """
    # Check session store
    session_store_ok = session_store is not None

    # Check database
    database_connected = False
    if db_path is not None and db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            conn.close()
            database_connected = True
        except Exception:
            pass

    # Determine overall status
    if session_store_ok and database_connected:
        overall_status = "healthy"
    elif session_store_ok or database_connected:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        database_connected=database_connected,
        session_store_ok=session_store_ok,
    )


@app.post("/chat", response_model=ChatResponseAPI)
async def chat(request: ChatRequest):
    """Chat endpoint - process natural language query.

    Args:
        request: ChatRequest with message and optional session_id

    Returns:
        ChatResponseAPI with response message and results

    Raises:
        HTTPException: On API errors (400 for invalid queries, 500 for internal errors)
    """
    store = get_session_store()
    bib_db = get_db_path()

    try:
        # Get or create session
        if request.session_id:
            session = store.get_session(request.session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {request.session_id} not found",
                )
        else:
            # Create new session
            session = store.create_session()
            logger.info(
                "Created new session for chat request",
                extra={"session_id": session.session_id},
            )

        # Update context if provided
        if request.context:
            store.update_context(session.session_id, request.context)

        # Add user message to session
        user_message = Message(role="user", content=request.message)
        store.add_message(session.session_id, user_message)

        # Compile query using M4 pipeline
        try:
            query_plan = compile_query(request.message)
            logger.info(
                "Compiled query plan",
                extra={
                    "session_id": session.session_id,
                    "filters": len(query_plan.filters),
                },
            )
        except QueryCompilationError as e:
            # Return error response but don't crash
            error_msg = f"Could not understand query: {str(e)}"
            response = ChatResponse(
                message=error_msg,
                candidate_set=None,
                clarification_needed=(
                    "Could you rephrase your query? For example: "
                    "'books published by Oxford between 1500 and 1599' or "
                    "'books about History printed in Paris'"
                ),
                session_id=session.session_id,
            )

            # Add assistant error message to session
            assistant_message = Message(
                role="assistant",
                content=error_msg,
                query_plan=None,
                candidate_set=None,
            )
            store.add_message(session.session_id, assistant_message)

            return ChatResponseAPI(success=True, response=response, error=None)

        # Execute query plan
        candidate_set = execute_plan(query_plan, bib_db)

        logger.info(
            "Executed query",
            extra={
                "session_id": session.session_id,
                "candidates_found": len(candidate_set.candidates),
            },
        )

        # Format response (simple for now, will enhance in CB-003)
        if len(candidate_set.candidates) == 0:
            response_message = "No books found matching your query."
            suggested_followups = [
                "Try broadening your search criteria",
                "Check the spelling of names and places",
                "Use more general terms",
            ]
        else:
            count = len(candidate_set.candidates)
            response_message = (
                f"Found {count} book{'s' if count != 1 else ''} matching your query."
            )
            suggested_followups = [
                "Refine by adding date range",
                "Filter by place of publication",
                "Search by subject",
            ]

        response = ChatResponse(
            message=response_message,
            candidate_set=candidate_set,
            suggested_followups=suggested_followups,
            clarification_needed=None,
            session_id=session.session_id,
        )

        # Add assistant response to session
        assistant_message = Message(
            role="assistant",
            content=response_message,
            query_plan=query_plan,
            candidate_set=candidate_set,
        )
        store.add_message(session.session_id, assistant_message)

        return ChatResponseAPI(success=True, response=response, error=None)

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log and return internal error
        logger.error(
            "Internal error in chat endpoint",
            extra={"error": str(e)},
            exc_info=True,
        )
        return ChatResponseAPI(
            success=False,
            response=None,
            error=f"Internal server error: {str(e)}",
        )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details.

    Args:
        session_id: Session identifier

    Returns:
        Session object with message history

    Raises:
        HTTPException: If session not found
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return session.model_dump()


@app.delete("/sessions/{session_id}")
async def expire_session(session_id: str):
    """Expire a session.

    Args:
        session_id: Session identifier

    Returns:
        Success message

    Raises:
        HTTPException: If session not found
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    store.expire_session(session_id)
    return {"status": "success", "message": f"Session {session_id} expired"}
