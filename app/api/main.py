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

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.models import ChatRequest, ChatResponseAPI, HealthResponse
from scripts.chat.models import ChatResponse, Message
from scripts.chat.session_store import SessionStore
from scripts.chat.formatter import format_for_chat, generate_followups
from scripts.chat.clarification import (
    should_ask_for_clarification,
    generate_clarification_message,
    detect_ambiguous_query,
)
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.query.exceptions import QueryCompilationError
from scripts.utils.logger import LoggerManager

# Initialize logger
logger = LoggerManager.get_logger(__name__)

# Initialize rate limiter (10 requests per minute per session)
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])

# Initialize FastAPI app
app = FastAPI(
    title="Rare Books Discovery API",
    description="Conversational interface for bibliographic discovery over MARC records",
    version="0.1.0",
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
@limiter.limit("10/minute")
async def chat(http_request: Request, request: ChatRequest):
    """Chat endpoint - process natural language query.

    Rate limited to 10 requests per minute per IP address.

    Args:
        http_request: FastAPI Request object (for rate limiting)
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

            # Check for ambiguity before executing (CB-004)
            # Note: Don't check zero_results yet since we haven't executed
            needs_clarification_before, reason_before = detect_ambiguous_query(
                query_plan, result_count=1  # Assume non-zero to skip zero_results check
            )

            if needs_clarification_before:
                # Query is ambiguous before execution - ask for clarification
                clarification_msg = generate_clarification_message(
                    query_plan, reason_before, result_count=1
                )

                response = ChatResponse(
                    message="I need some clarification to search effectively.",
                    candidate_set=None,
                    clarification_needed=clarification_msg,
                    session_id=session.session_id,
                )

                # Add assistant clarification request to session
                assistant_message = Message(
                    role="assistant",
                    content=clarification_msg,
                    query_plan=query_plan,
                    candidate_set=None,
                )
                store.add_message(session.session_id, assistant_message)

                logger.info(
                    "Requesting clarification",
                    extra={"session_id": session.session_id, "reason": reason_before},
                )

                return ChatResponseAPI(success=True, response=response, error=None)

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

        # Check for clarification after execution (CB-004)
        # Enable zero_results clarification if no results found
        result_count = len(candidate_set.candidates)
        ask_for_clarification = should_ask_for_clarification(
            query_plan,
            result_count,
            enable_zero_result_clarification=True
        )

        clarification_message = None
        if ask_for_clarification:
            # Generate clarification message
            _, reason = detect_ambiguous_query(query_plan, result_count)
            clarification_message = generate_clarification_message(
                query_plan, reason, result_count
            )
            logger.info(
                "Suggesting clarification",
                extra={"session_id": session.session_id, "reason": reason},
            )

        # Format response using formatter module (CB-003)
        response_message = format_for_chat(candidate_set, max_candidates=10)
        suggested_followups = generate_followups(candidate_set, query_plan.query_text)

        response = ChatResponse(
            message=response_message,
            candidate_set=candidate_set,
            suggested_followups=suggested_followups,
            clarification_needed=clarification_message,
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


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket endpoint for streaming chat responses.

    Provides progressive results with:
    - Progress messages during query execution
    - Batched results (groups of 10 candidates)
    - Real-time streaming for better UX

    Protocol:
    1. Client connects
    2. Client sends JSON: {"message": "query", "session_id": "optional-id"}
    3. Server streams JSON messages:
       - {"type": "progress", "message": "Compiling query..."}
       - {"type": "progress", "message": "Executing SQL..."}
       - {"type": "batch", "candidates": [...], "batch_num": 1, "total_batches": 3}
       - {"type": "complete", "response": ChatResponse}
    4. Connection closes
    """
    await websocket.accept()
    store = get_session_store()
    bib_db = get_db_path()

    try:
        # Receive initial message
        data = await websocket.receive_json()
        message = data.get("message")
        session_id = data.get("session_id")

        if not message:
            await websocket.send_json({"type": "error", "message": "Message is required"})
            await websocket.close()
            return

        # Get or create session
        if session_id:
            session = store.get_session(session_id)
            if not session:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Session {session_id} not found"
                })
                await websocket.close()
                return
        else:
            session = store.create_session()
            session_id = session.session_id
            await websocket.send_json({
                "type": "session_created",
                "session_id": session_id
            })

        # Add user message
        user_message = Message(role="user", content=message)
        store.add_message(session_id, user_message)

        # Progress: Compiling query
        await websocket.send_json({
            "type": "progress",
            "message": "Compiling query..."
        })

        try:
            query_plan = compile_query(message)

            # Check for ambiguity before executing
            needs_clarification_before, reason_before = detect_ambiguous_query(
                query_plan, result_count=1
            )

            if needs_clarification_before:
                clarification_msg = generate_clarification_message(
                    query_plan, reason_before, result_count=1
                )

                response = ChatResponse(
                    message="I need some clarification to search effectively.",
                    candidate_set=None,
                    clarification_needed=clarification_msg,
                    session_id=session_id,
                )

                # Add to session
                assistant_message = Message(
                    role="assistant",
                    content=clarification_msg,
                    query_plan=query_plan,
                    candidate_set=None,
                )
                store.add_message(session_id, assistant_message)

                # Send complete response
                await websocket.send_json({
                    "type": "complete",
                    "response": response.model_dump()
                })
                await websocket.close()
                return

        except QueryCompilationError as e:
            error_msg = f"Could not understand query: {str(e)}"
            response = ChatResponse(
                message=error_msg,
                candidate_set=None,
                clarification_needed=(
                    "Could you rephrase your query? For example: "
                    "'books published by Oxford between 1500 and 1599' or "
                    "'books about History printed in Paris'"
                ),
                session_id=session_id,
            )

            assistant_message = Message(
                role="assistant",
                content=error_msg,
                query_plan=None,
                candidate_set=None,
            )
            store.add_message(session_id, assistant_message)

            await websocket.send_json({
                "type": "complete",
                "response": response.model_dump()
            })
            await websocket.close()
            return

        # Progress: Executing SQL
        await websocket.send_json({
            "type": "progress",
            "message": f"Executing query with {len(query_plan.filters)} filters..."
        })

        # Execute query
        candidate_set = execute_plan(query_plan, bib_db)
        result_count = len(candidate_set.candidates)

        # Progress: Found results
        await websocket.send_json({
            "type": "progress",
            "message": f"Found {result_count} results. Formatting response..."
        })

        # Stream results in batches of 10
        batch_size = 10
        total_batches = (result_count + batch_size - 1) // batch_size if result_count > 0 else 0

        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, result_count)
            batch_candidates = candidate_set.candidates[start_idx:end_idx]

            await websocket.send_json({
                "type": "batch",
                "candidates": [c.model_dump() for c in batch_candidates],
                "batch_num": batch_num + 1,
                "total_batches": total_batches,
                "start_idx": start_idx,
                "end_idx": end_idx
            })

        # Check for clarification after execution
        ask_for_clarification = should_ask_for_clarification(
            query_plan,
            result_count,
            enable_zero_result_clarification=True
        )

        clarification_message = None
        if ask_for_clarification:
            _, reason = detect_ambiguous_query(query_plan, result_count)
            clarification_message = generate_clarification_message(
                query_plan, reason, result_count
            )

        # Format final response
        response_message = format_for_chat(candidate_set, max_candidates=10)
        suggested_followups = generate_followups(candidate_set, query_plan.query_text)

        response = ChatResponse(
            message=response_message,
            candidate_set=candidate_set,
            suggested_followups=suggested_followups,
            clarification_needed=clarification_message,
            session_id=session_id,
        )

        # Add to session
        assistant_message = Message(
            role="assistant",
            content=response_message,
            query_plan=query_plan,
            candidate_set=candidate_set,
        )
        store.add_message(session_id, assistant_message)

        # Send complete response
        await websocket.send_json({
            "type": "complete",
            "response": response.model_dump()
        })

        logger.info(
            "WebSocket chat completed",
            extra={
                "session_id": session_id,
                "result_count": result_count,
                "batches_sent": total_batches
            }
        )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Internal error: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass
