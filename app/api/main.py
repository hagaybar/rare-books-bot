"""FastAPI application for conversational chatbot interface.

This module provides the HTTP API layer that:
- Receives natural language queries via /chat endpoint
- Routes queries through the scholar pipeline (interpret -> execute -> narrate)
- Manages multi-turn conversation sessions
- Returns structured responses with evidence
"""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.auth_deps import require_role
from app.api.auth_routes import router as auth_router
from app.api.diagnostics import router as diagnostics_router
from app.api.metadata import router as metadata_router
from app.api.network import router as network_router
from app.api.models import ChatRequest, ChatResponseAPI, HealthExtendedResponse, HealthResponse
from app.api.security import (
    is_chat_enabled,
    validate_input,
    check_quota,
    mask_pii,
    check_moderation,
    validate_output,
    record_token_usage,
)
from scripts.chat.models import (
    ChatResponse,
    Message,
    ConversationPhase,
)
from scripts.chat.session_store import SessionStore
# Scholar pipeline (3-stage: interpret -> execute -> narrate)
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan as execute_scholar_plan
from scripts.chat.narrator import narrate, narrate_streaming, describe_filters
from scripts.chat.plan_models import (
    SessionContext,
)

from scripts.utils.logger import LoggerManager
from scripts.utils.llm_logger import token_accumulator
from scripts.enrichment import EnrichmentService
from scripts.metadata.interaction_logger import interaction_logger

# Initialize logger
logger = LoggerManager.get_logger(__name__)

# Initialize rate limiter (30 requests per minute per IP)
limiter = Limiter(key_func=get_remote_address)

# Global state (initialized during lifespan startup)
session_store: Optional[SessionStore] = None
db_path: Optional[Path] = None
enrichment_service: Optional[EnrichmentService] = None


@asynccontextmanager
async def lifespan(app):
    """Manage application startup and shutdown lifecycle."""
    global session_store, db_path, enrichment_service

    # --- Startup ---
    # Initialize auth database
    from app.api.auth_db import init_auth_db
    init_auth_db()

    # Get paths from environment or use defaults
    sessions_db = Path(os.getenv("SESSIONS_DB_PATH", "data/chat/sessions.db"))
    bib_db = Path(os.getenv("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db"))
    enrichment_db = Path(os.getenv("ENRICHMENT_DB_PATH", "data/enrichment/cache.db"))

    # Ensure directories exist
    sessions_db.parent.mkdir(parents=True, exist_ok=True)
    enrichment_db.parent.mkdir(parents=True, exist_ok=True)

    # Initialize session store
    session_store = SessionStore(sessions_db)
    db_path = bib_db

    # Initialize enrichment service
    enrichment_service = EnrichmentService(cache_db_path=enrichment_db)

    logger.info(
        "API started",
        extra={
            "sessions_db": str(sessions_db),
            "bibliographic_db": str(bib_db),
            "enrichment_db": str(enrichment_db),
        },
    )

    yield

    # --- Shutdown ---
    if session_store is not None:
        session_store.close()
    if enrichment_service is not None:
        enrichment_service.close()
    logger.info("API shutdown")


# Initialize FastAPI app
app = FastAPI(
    title="Rare Books Discovery API",
    description="Conversational interface for bibliographic discovery over MARC records",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware (configurable via CORS_ORIGIN env var)
# Never use "*" with allow_credentials=True — enumerate allowed origins explicitly
_cors_origins = os.getenv("CORS_ORIGIN", "http://localhost:5173,http://localhost:5174").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security response headers middleware (N1)
# Added AFTER CORS middleware so it does not overwrite CORS headers.
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # Content-Security-Policy: allow self + OpenFreeMap tiles + Wikidata/Wikipedia images
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://*.wikimedia.org https://*.wikipedia.org https://tiles.openfreemap.org https://*.openstreetmap.org; "
        "connect-src 'self' ws: wss: https://api.openai.com https://tiles.openfreemap.org https://*.openfreemap.org; "
        "font-src 'self'; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'"
    )
    return response


# Middleware: enforce role-based auth on /metadata/* endpoints
@app.middleware("http")
async def metadata_auth_middleware(request: Request, call_next):
    """Apply role-based auth to metadata endpoints.

    /metadata/enrichment/* -> guest (accessible to all authenticated users)
    /metadata/* (everything else) -> full
    """
    path = request.url.path
    if not path.startswith("/metadata/"):
        return await call_next(request)

    from app.api.auth_service import validate_access_token
    from app.api.auth_deps import ROLE_HIERARCHY

    token = request.cookies.get("access_token")
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    payload = validate_access_token(token)
    if not payload:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

    user_level = ROLE_HIERARCHY.get(payload.get("role", ""), 0)

    # Enrichment endpoints are guest-accessible
    if path.startswith("/metadata/enrichment"):
        min_level = ROLE_HIERARCHY["guest"]
    else:
        min_level = ROLE_HIERARCHY["full"]

    if user_level < min_level:
        required = "guest" if path.startswith("/metadata/enrichment") else "full"
        return JSONResponse(
            status_code=403,
            content={"detail": f"Requires {required} role or higher"},
        )

    return await call_next(request)


# Middleware: log all /metadata/* interactions
@app.middleware("http")
async def log_metadata_interactions(request: Request, call_next):
    """Log every /metadata/* request with timing and result status."""
    if not request.url.path.startswith("/metadata"):
        return await call_next(request)

    import time as _time

    start = _time.monotonic()
    body_bytes = None

    # Capture request body for POST endpoints
    if request.method == "POST":
        body_bytes = await request.body()
        # Re-wrap the body so downstream handlers can read it

        async def _receive():
            return {"type": "http.request", "body": body_bytes}

        request = Request(scope=request.scope, receive=_receive)

    error_msg = None
    status_code = 200
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        error_msg = str(exc)
        status_code = 500
        raise
    finally:
        elapsed = (_time.monotonic() - start) * 1000
        params = dict(request.query_params)
        if body_bytes:
            try:
                import json as _json
                body = _json.loads(body_bytes)
                # Summarize body -- don't log huge payloads
                if isinstance(body, dict):
                    params.update({
                        k: v for k, v in body.items()
                        if k in ("field", "message", "source", "raw_value",
                                 "canonical_value", "mms_ids")
                    })
                    if "mms_ids" in params and isinstance(params["mms_ids"], list):
                        params["mms_ids_count"] = len(params["mms_ids"])
                        del params["mms_ids"]
                    if "corrections" in body:
                        params["corrections_count"] = len(body["corrections"])
            except Exception:
                pass

        interaction_logger.log(
            action=f"{request.method} {request.url.path}",
            field=params.get("field"),
            params=params if params else None,
            result_summary={"status_code": status_code},
            duration_ms=elapsed,
            error=error_msg,
        )


# Register auth router (no auth required on auth endpoints themselves)
app.include_router(auth_router)

# Register metadata quality router (auth enforced via middleware above)
app.include_router(metadata_router)

# Register diagnostics router (auth enforced via router-level dependency)
app.include_router(diagnostics_router)

# Register network map explorer router (auth enforced via router-level dependency)
app.include_router(network_router)


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


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint.

    Returns:
        HealthResponse with status of database, session store, and executor readiness
    """
    import sqlite3 as _sqlite3

    # Check session store
    session_store_ok = session_store is not None

    # Check database
    database_connected = False
    executor_ready = False
    if db_path is not None and db_path.exists():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.execute("SELECT 1")
            database_connected = True

            # Check executor-required tables exist
            required_tables = {"records", "imprints", "agents", "titles", "languages", "subjects"}
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}
            executor_ready = required_tables.issubset(existing_tables)

            conn.close()
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
        executor_ready=executor_ready,
    )


@app.get("/health/extended", response_model=HealthExtendedResponse)
async def health_extended(_user=Depends(require_role("full"))):
    """Extended health check with database file details.

    Returns file sizes and modification times for the bibliographic
    and QA databases.
    """
    from datetime import datetime, timezone

    bib_db = Path(os.getenv("BIBLIOGRAPHIC_DB_PATH", "data/index/bibliographic.db"))

    db_file_size_bytes = 0
    db_last_modified = None
    if bib_db.exists():
        db_file_size_bytes = os.path.getsize(bib_db)
        mtime = os.path.getmtime(bib_db)
        db_last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    qa_db = Path(os.getenv("QA_DB_PATH", "data/qa/qa.db"))
    qa_db_exists = qa_db.exists()
    qa_db_size_bytes = os.path.getsize(qa_db) if qa_db_exists else 0

    return HealthExtendedResponse(
        db_file_size_bytes=db_file_size_bytes,
        db_last_modified=db_last_modified,
        qa_db_exists=qa_db_exists,
        qa_db_size_bytes=qa_db_size_bytes,
    )


@app.get("/chat/history")
async def chat_history(request: Request, _user=Depends(require_role("limited"))):
    """Return the 5 most recent chat sessions for the current user.

    Each entry includes session_id, title (first user message truncated to
    50 chars), message_count, and last_activity timestamp.

    Requires 'limited' role or higher.
    """
    store = get_session_store()
    user_id = str(_user.get("user_id", ""))
    if not user_id:
        return []

    return store.get_recent_sessions(user_id, limit=5)


@app.post("/chat", response_model=ChatResponseAPI)
@limiter.limit("30/minute")
async def chat(request: Request, chat_request: ChatRequest, _user=Depends(require_role("limited"))):
    """Chat endpoint -- all queries go through the scholar pipeline.

    Three-stage pipeline:
    1. Interpret: LLM produces an InterpretationPlan
    2. Execute: Deterministic executor walks the plan via SQL
    3. Narrate: LLM composes a scholarly response from verified data

    Rate limited to 30 requests per minute per IP address.
    Requires 'limited' role or higher.

    Security checks:
    1. Kill switch (503 if chat disabled)
    2. Input validation (400 if invalid)
    3. Quota check (429 if exceeded)
    4. PII masking before LLM call
    5. Moderation check (400 if flagged)
    6. Output validation after LLM response
    7. Token usage recording
    8. Audit logging

    Args:
        request: FastAPI Request object (for rate limiting)
        chat_request: ChatRequest with message and optional session_id

    Returns:
        ChatResponseAPI with response message and results

    Raises:
        HTTPException: On API errors
    """
    from app.api.auth_service import audit_log

    ip = request.client.host if request.client else "unknown"
    user_id = _user.get("user_id")
    username = _user.get("username", "unknown")

    # --- Security check 1: Kill switch ---
    if not is_chat_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is currently disabled by administrator",
        )

    # --- Security check 2: Input validation ---
    valid, cleaned_or_error = validate_input(chat_request.message)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=cleaned_or_error,
        )
    if cleaned_or_error:
        chat_request.message = cleaned_or_error

    # --- Security check 3: Quota check ---
    allowed, used, limit = check_quota(user_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly token quota exceeded ({used}/{limit})",
        )

    # --- Security check 4: PII masking ---
    chat_request.message = mask_pii(chat_request.message)

    # --- Security check 5: Moderation ---
    safe, category = await check_moderation(chat_request.message)
    if not safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message flagged by content moderation: {category}",
        )

    store = get_session_store()
    bib_db = get_db_path()

    try:
        # Get or create session
        if chat_request.session_id:
            session = store.get_session(chat_request.session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Session {chat_request.session_id} not found",
                )
        else:
            # Create new session with user_id for history tracking
            session = store.create_session(user_id=str(user_id) if user_id else None)
            logger.info(
                "Created new session for chat request",
                extra={"session_id": session.session_id, "user_id": user_id},
            )

        # Update context if provided
        if chat_request.context:
            store.update_context(session.session_id, chat_request.context)

        # Add user message to session
        user_message = Message(role="user", content=chat_request.message)
        store.add_message(session.session_id, user_message)

        # Reset token accumulator before pipeline
        token_accumulator.reset()

        # All queries go through the scholar pipeline
        result = await _run_scholar_pipeline(
            chat_request, session, store, bib_db
        )

        # --- Post-response security checks ---

        # Security check 6: Output validation
        if result.response and result.response.message:
            result.response.message = validate_output(result.response.message)

        # Security check 7: Token recording
        # Read actual token usage accumulated by LLM logger during pipeline
        tokens_used = token_accumulator.get()
        token_breakdown = token_accumulator.get_breakdown()
        if tokens_used > 0:
            record_token_usage(user_id, tokens_used, **token_breakdown)

        # Security check 8: Audit log
        audit_log(
            "chat_query",
            user_id=user_id,
            username=username,
            details=json.dumps({
                "query": chat_request.message[:200],
                "tokens": tokens_used,
                "session_id": session.session_id,
            }),
            ip_address=ip,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Chat error",
            extra={"error": str(e)},
        )
        return ChatResponseAPI(
            success=False,
            response=None,
            error="An internal error occurred. Please try again.",
        )


async def _run_scholar_pipeline(
    chat_request: ChatRequest,
    session,
    store: SessionStore,
    bib_db: Path
) -> ChatResponseAPI:
    """Run the three-stage scholar pipeline.

    Stage 1 (Interpret): LLM produces an InterpretationPlan.
    Stage 2 (Execute): Deterministic executor walks the plan via SQL.
    Stage 3 (Narrate): LLM composes a scholarly response from verified data.

    If the interpreter returns a clarification with confidence < 0.7,
    the pipeline short-circuits and returns the clarification to the user.

    Args:
        chat_request: The chat request
        session: Current session
        store: Session store
        bib_db: Path to bibliographic database

    Returns:
        ChatResponseAPI with response
    """
    # Build session context for follow-ups
    previous_record_ids: list[str] = []
    active_sub = getattr(session, "active_subgroup", None)
    if active_sub and hasattr(active_sub, "record_ids"):
        previous_record_ids = active_sub.record_ids or []

    session_context = SessionContext(
        session_id=session.session_id,
        previous_messages=session.get_recent_messages(5),
        previous_record_ids=previous_record_ids,
    )

    # ---- Stage 1: Interpret ----
    logger.info(
        "Scholar pipeline: interpreting query",
        extra={"session_id": session.session_id, "query": chat_request.message},
    )
    plan = await interpret(chat_request.message, session_context)

    logger.info(
        "Scholar pipeline: interpretation complete",
        extra={
            "session_id": session.session_id,
            "intents": plan.intents,
            "confidence": plan.confidence,
            "steps": len(plan.execution_steps),
            "has_clarification": plan.clarification is not None,
        },
    )

    # ---- Clarification short-circuit ----
    if plan.clarification and plan.confidence < 0.7:
        response = ChatResponse(
            message=plan.clarification,
            candidate_set=None,
            clarification_needed=plan.clarification,
            session_id=session.session_id,
            phase=ConversationPhase.QUERY_DEFINITION,
            confidence=plan.confidence,
            metadata={"intents": plan.intents, "reasoning": plan.reasoning},
        )
        store.add_message(
            session.session_id,
            Message(role="assistant", content=plan.clarification),
        )
        logger.info(
            "Scholar pipeline: returning clarification (confidence < 0.7)",
            extra={"session_id": session.session_id, "confidence": plan.confidence},
        )
        return ChatResponseAPI(success=True, response=response, error=None)

    # ---- Stage 2: Execute ----
    logger.info(
        "Scholar pipeline: executing plan",
        extra={"session_id": session.session_id, "steps": len(plan.execution_steps)},
    )
    execution_result = execute_scholar_plan(
        plan, bib_db, session_context, original_query=chat_request.message
    )

    logger.info(
        "Scholar pipeline: execution complete",
        extra={
            "session_id": session.session_id,
            "steps_completed": len(execution_result.steps_completed),
            "records_grounded": len(execution_result.grounding.records),
            "truncated": execution_result.truncated,
        },
    )

    # ---- Stage 3: Narrate ----
    logger.info(
        "Scholar pipeline: narrating response",
        extra={"session_id": session.session_id},
    )
    scholar_response = await narrate(
        chat_request.message, execution_result,
        token_saving=chat_request.token_saving,
    )

    logger.info(
        "Scholar pipeline: narration complete",
        extra={
            "session_id": session.session_id,
            "narrative_len": len(scholar_response.narrative),
            "confidence": scholar_response.confidence,
        },
    )

    # ---- Map ScholarResponse -> ChatResponse for API compatibility ----
    response = ChatResponse(
        message=scholar_response.narrative,
        candidate_set=None,  # Grounding replaces candidate_set in the new pipeline
        suggested_followups=scholar_response.suggested_followups,
        clarification_needed=None,
        session_id=session.session_id,
        phase=ConversationPhase.QUERY_DEFINITION,
        confidence=scholar_response.confidence,
        metadata={
            "intents": plan.intents,
            "grounding": scholar_response.grounding.model_dump(),
            **scholar_response.metadata,
        },
    )

    # Store assistant message in session
    store.add_message(
        session.session_id,
        Message(role="assistant", content=scholar_response.narrative),
    )

    return ChatResponseAPI(success=True, response=response, error=None)


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, user=Depends(require_role("limited"))):
    """Get session details.

    Requires 'limited' role or higher. Users can only access their own sessions
    (admins can access any session).

    Args:
        session_id: Session identifier
        user: Authenticated user from JWT

    Returns:
        Session object with message history

    Raises:
        HTTPException: If session not found or access denied
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Ownership check: user can only access their own sessions (admin can access any)
    if str(session.user_id) != str(user["user_id"]) and user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return session.model_dump()


@app.delete("/sessions/{session_id}")
async def expire_session(session_id: str, user=Depends(require_role("limited"))):
    """Expire a session.

    Requires 'limited' role or higher. Users can only expire their own sessions
    (admins can expire any session).

    Args:
        session_id: Session identifier
        user: Authenticated user from JWT

    Returns:
        Success message

    Raises:
        HTTPException: If session not found or access denied
    """
    store = get_session_store()
    session = store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Ownership check: user can only expire their own sessions (admin can expire any)
    if str(session.user_id) != str(user["user_id"]) and user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
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

    Requires 'limited' role or higher (JWT validated from cookies at connection time).

    Protocol:
    1. Client connects (JWT validated from cookie)
    2. Client sends JSON: {"message": "query", "session_id": "optional-id"}
    3. Server streams JSON messages:
       - {"type": "progress", "message": "Compiling query..."}
       - {"type": "progress", "message": "Executing SQL..."}
       - {"type": "batch", "candidates": [...], "batch_num": 1, "total_batches": 3}
       - {"type": "complete", "response": ChatResponse}
    4. Connection closes
    """
    # Validate JWT from cookies before accepting connection
    from app.api.auth_service import validate_access_token
    from app.api.auth_deps import ROLE_HIERARCHY

    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="Not authenticated")
        return
    payload = validate_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    user_level = ROLE_HIERARCHY.get(payload.get("role", ""), 0)
    if user_level < ROLE_HIERARCHY["limited"]:
        await websocket.close(code=4003, reason="Requires limited role or higher")
        return

    await websocket.accept()
    store = get_session_store()
    _bib_db = get_db_path()  # retained for potential future use

    try:
        # Receive initial message
        data = await websocket.receive_json()
        message = data.get("message")
        session_id = data.get("session_id")
        token_saving = data.get("token_saving", True)

        if not message:
            await websocket.send_json({"type": "error", "message": "Message is required"})
            await websocket.close()
            return

        # --- WebSocket security checks ---
        ws_user_id = payload.get("user_id")

        # Kill switch
        if not is_chat_enabled():
            await websocket.send_json({"type": "error", "message": "Chat is currently disabled by administrator"})
            await websocket.close()
            return

        # Input validation
        valid, cleaned_or_error = validate_input(message)
        if not valid:
            await websocket.send_json({"type": "error", "message": cleaned_or_error})
            await websocket.close()
            return
        if cleaned_or_error:
            message = cleaned_or_error

        # Quota check
        allowed, used, limit = check_quota(ws_user_id)
        if not allowed:
            await websocket.send_json({"type": "error", "message": f"Monthly token quota exceeded ({used}/{limit})"})
            await websocket.close()
            return

        # PII masking
        message = mask_pii(message)

        # Moderation
        safe, category = await check_moderation(message)
        if not safe:
            await websocket.send_json({"type": "error", "message": f"Message flagged by content moderation: {category}"})
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
            session = store.create_session(user_id=str(ws_user_id) if ws_user_id else None)
            session_id = session.session_id
            await websocket.send_json({
                "type": "session_created",
                "session_id": session_id
            })

        # Add user message
        user_message = Message(role="user", content=message)
        store.add_message(session_id, user_message)

        # Build session context for follow-ups
        previous_record_ids: list[str] = []
        active_sub = getattr(session, "active_subgroup", None)
        if active_sub and hasattr(active_sub, "record_ids"):
            previous_record_ids = active_sub.record_ids or []

        ws_session_context = SessionContext(
            session_id=session_id,
            previous_messages=session.get_recent_messages(5),
            previous_record_ids=previous_record_ids,
        )

        # Reset token accumulator before pipeline
        token_accumulator.reset()

        # ---- Stage 1: Interpret ----
        await websocket.send_json({
            "type": "thinking",
            "text": "Interpreting your query..."
        })

        plan = await interpret(message, ws_session_context)

        # ---- Clarification short-circuit ----
        if plan.clarification and plan.confidence < 0.7:
            response = ChatResponse(
                message=plan.clarification,
                candidate_set=None,
                clarification_needed=plan.clarification,
                session_id=session_id,
                phase=ConversationPhase.QUERY_DEFINITION,
                confidence=plan.confidence,
                metadata={"intents": plan.intents, "reasoning": plan.reasoning},
            )
            store.add_message(
                session_id,
                Message(role="assistant", content=plan.clarification),
            )
            await websocket.send_json({
                "type": "complete",
                "response": response.model_dump()
            })
            return

        # ---- Stage 2: Execute ----
        filter_desc = describe_filters(plan)
        await websocket.send_json({
            "type": "thinking",
            "text": f"Searching for {filter_desc}..."
        })

        execution_result = execute_scholar_plan(
            plan, _bib_db, ws_session_context, original_query=message
        )

        records_found = len(execution_result.grounding.records)
        await websocket.send_json({
            "type": "thinking",
            "text": f"Found {records_found} matching records"
        })

        # ---- Stage 3: Narrate (streaming) ----
        await websocket.send_json({"type": "stream_start"})

        async def _stream_chunk(text: str) -> None:
            """Forward a narrator text chunk to the WebSocket client."""
            await websocket.send_json({
                "type": "stream_chunk",
                "text": text,
            })

        scholar_response = await narrate_streaming(
            message, execution_result, chunk_callback=_stream_chunk,
            token_saving=token_saving,
        )

        # ---- Post-response security: Output validation ----
        narrative = validate_output(scholar_response.narrative)

        # ---- Map to ChatResponse ----
        response = ChatResponse(
            message=narrative,
            candidate_set=None,
            suggested_followups=scholar_response.suggested_followups,
            clarification_needed=None,
            session_id=session_id,
            phase=ConversationPhase.QUERY_DEFINITION,
            confidence=scholar_response.confidence,
            metadata={
                "intents": plan.intents,
                "grounding": scholar_response.grounding.model_dump(),
                **scholar_response.metadata,
            },
        )

        store.add_message(
            session_id,
            Message(role="assistant", content=narrative),
        )

        await websocket.send_json({
            "type": "complete",
            "response": response.model_dump()
        })

        # ---- Post-response security: Token recording + audit ----
        # Read actual token usage accumulated by LLM logger during pipeline
        tokens_used = token_accumulator.get()
        token_breakdown = token_accumulator.get_breakdown()
        if tokens_used > 0:
            record_token_usage(ws_user_id, tokens_used, **token_breakdown)

        from app.api.auth_service import audit_log
        audit_log(
            "chat_query_ws",
            user_id=ws_user_id,
            username=payload.get("username", "unknown"),
            details=json.dumps({
                "query": message[:200],
                "tokens": tokens_used,
                "session_id": session_id,
            }),
        )

        logger.info(
            "WebSocket scholar pipeline completed",
            extra={
                "session_id": session_id,
                "records_found": records_found,
                "confidence": scholar_response.confidence,
            }
        )

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception("WebSocket chat error")
        try:
            await websocket.send_json({
                "type": "error",
                "message": "An internal error occurred. Please try again."
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Static file serving (React SPA) — must be LAST (catch-all)
# ---------------------------------------------------------------------------
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dir / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA — static files if they exist, otherwise index.html."""
        file_path = _frontend_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dir / "index.html")
