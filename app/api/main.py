"""FastAPI application for conversational chatbot interface.

This module provides the HTTP API layer that:
- Receives natural language queries via /chat endpoint
- Routes queries through M4 query pipeline (compile + execute)
- Manages multi-turn conversation sessions
- Returns structured responses with evidence

Two-Phase Conversation Support:
- Phase 1 (Query Definition): Intent interpretation with confidence scoring
- Phase 2 (Corpus Exploration): Analysis of defined subgroups (future)
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.diagnostics import router as diagnostics_router
from app.api.metadata import router as metadata_router
from app.api.models import ChatRequest, ChatResponseAPI, HealthExtendedResponse, HealthResponse
from scripts.chat.models import (
    ChatResponse,
    Message,
    ConversationPhase,
    ActiveSubgroup,
)
from scripts.chat.session_store import SessionStore
# Scholar pipeline (3-stage: interpret -> execute -> narrate)
from scripts.chat.interpreter import interpret
from scripts.chat.executor import execute_plan as execute_scholar_plan
from scripts.chat.narrator import narrate
from scripts.chat.plan_models import (
    InterpretationPlan,
    ScholarResponse,
    SessionContext,
    GroundingData,
)

# DEPRECATED: removed in scholar pipeline migration (cleanup in Task 8)
from scripts.chat.formatter import (  # noqa: F401
    format_for_chat, format_teaching_note, format_citations,
    generate_followups, format_exhibit_response,
)
from scripts.chat.curator import score_candidates, select_diverse  # noqa: F401
from scripts.chat.thematic_context import get_thematic_context  # noqa: F401
from scripts.chat.clarification import (  # noqa: F401
    should_ask_for_clarification,
    generate_clarification_message,
    detect_ambiguous_query,
    is_execution_blocking,
    get_refinement_suggestions_for_query,
)
from scripts.chat.intent_agent import (  # noqa: F401
    interpret_query,
    generate_clarification_prompt,
    format_interpretation_for_user,
)
from scripts.chat.exploration_agent import (
    interpret_exploration_request,
    format_aggregation_response,
    format_metadata_response,
    format_refinement_response,
    ExplorationIntent,
)
from scripts.chat.aggregation import (
    execute_aggregation,
    execute_aggregation_full_collection,
    execute_count_query,
    apply_refinement,
    execute_comparison_enhanced,
    is_overview_query,
    get_collection_overview,
    format_collection_overview,
)
from scripts.chat.cross_reference import find_connections, find_network_neighbors  # noqa: F401
from scripts.chat.analytical_router import detect_analytical_query, AnalyticalIntent  # noqa: F401
from scripts.chat.curation_engine import (  # noqa: F401
    select_curated_items,
    format_curation_response,
)
from scripts.chat.narrative_agent import generate_analytical_narrative  # noqa: F401
from scripts.query import QueryService, QueryOptions, QueryCompilationError  # noqa: F401
from scripts.query.compile import compile_query  # noqa: F401
from scripts.utils.logger import LoggerManager
from scripts.enrichment import EnrichmentService, EntityType as EnrichmentEntityType
from scripts.metadata.interaction_logger import interaction_logger

# Initialize logger
logger = LoggerManager.get_logger(__name__)

# Initialize rate limiter (10 requests per minute per session)
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])

# Global state (initialized during lifespan startup)
session_store: Optional[SessionStore] = None
db_path: Optional[Path] = None
enrichment_service: Optional[EnrichmentService] = None
query_service: Optional[QueryService] = None


@asynccontextmanager
async def lifespan(app):
    """Manage application startup and shutdown lifecycle."""
    global session_store, db_path, enrichment_service, query_service

    # --- Startup ---
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

    # Initialize query service
    query_service = QueryService(bib_db)

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

# Add CORS middleware (allow all origins for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                # Summarize body — don't log huge payloads
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


# Register metadata quality router
app.include_router(metadata_router)

# Register diagnostics router
app.include_router(diagnostics_router)


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


def get_query_service() -> QueryService:
    """Get query service instance.

    Returns:
        QueryService instance

    Raises:
        HTTPException: If query service not initialized
    """
    if query_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Query service not initialized",
        )
    return query_service



async def handle_analytical_query(
    analytical_result,
    query_text: str,
    session_id: str,
    bib_db: Path,
) -> ChatResponseAPI:
    """Handle an analytical query (distribution or curation) and return ChatResponseAPI.

    For distribution intents: calls execute_aggregation_full_collection with the
    appropriate field, applying implied_filters if present.
    For CURATION intent: fetches candidate records and runs the curation engine.
    Generates a narrative summary via generate_analytical_narrative.

    Args:
        analytical_result: AnalyticalQueryResult from detect_analytical_query.
        query_text: Original user query text.
        session_id: Current session ID.
        bib_db: Path to the bibliographic database.

    Returns:
        ChatResponseAPI with phase=CORPUS_EXPLORATION and visualization_hint.
    """
    intent = analytical_result.intent
    implied_filters = analytical_result.implied_filters or []

    if intent == AnalyticalIntent.CURATION:
        # Curation flow: fetch candidates from DB, score, select
        try:
            import sqlite3
            conn = sqlite3.connect(str(bib_db))
            cursor = conn.execute(
                "SELECT r.mms_id, i.date_start, i.place_norm, i.publisher_norm "
                "FROM records r LEFT JOIN imprints i ON r.id = i.record_id "
                "LIMIT 500"
            )
            rows = cursor.fetchall()
            conn.close()

            candidates = []
            for row in rows:
                candidates.append({
                    "record_id": row[0],
                    "date_start": row[1],
                    "place_norm": row[2],
                    "publisher": row[3],
                    "title": None,
                    "subjects": [],
                    "author": None,
                    "description": None,
                })

            scored_items = select_curated_items(candidates, n=10)
            curation_data = format_curation_response(scored_items)

            narrative = None
            try:
                narrative = f"**Curated Selection**\n\n{curation_data['header']}\n"
                for item in curation_data["items"]:
                    rec_id = item.get('record_id', 'Unknown')
                    sc = item.get('score', 0)
                    sig = item.get('significance', '')
                    narrative += f"\n- **{rec_id}** (score: {sc:.2f}): {sig}"
            except Exception:
                narrative = curation_data.get("header", "Curated selection")

            response = ChatResponse(
                message=narrative or "Curated selection generated.",
                candidate_set=None,
                suggested_followups=[
                    "Show chronological distribution",
                    "Show geographic distribution",
                    "Start a new search",
                ],
                session_id=session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=analytical_result.confidence,
                metadata={
                    "visualization_hint": "curated_list",
                    "data": curation_data,
                    "analytical_intent": intent.value,
                },
            )
            return ChatResponseAPI(success=True, response=response, error=None)

        except Exception as e:
            logger.error("Curation engine failed: %s", e, exc_info=True)
            response = ChatResponse(
                message=f"Could not generate curated selection: {e}",
                candidate_set=None,
                session_id=session_id,
                phase=ConversationPhase.QUERY_DEFINITION,
            )
            return ChatResponseAPI(success=True, response=response, error=None)

    else:
        # Distribution flow: aggregate over the full collection (or filtered subset)
        field = analytical_result.aggregation_field or "date_decade"
        filters = implied_filters if implied_filters else None

        try:
            aggregation_result = execute_aggregation_full_collection(
                db_path=bib_db,
                field=field,
                filters=filters,
                limit=20,
            )

            agg_data = {
                "field": aggregation_result.field,
                "results": aggregation_result.results,
                "total_in_subgroup": aggregation_result.total_in_subgroup,
                "query_description": aggregation_result.query_description,
            }

            # Generate narrative summary
            narrative = generate_analytical_narrative(
                agg_data, query_text, analytical_mode=True
            )

            # Determine visualization hint
            viz_map = {
                "date_decade": "bar_chart",
                "date_century": "bar_chart",
                "place": "bar_chart",
                "publisher": "bar_chart",
                "language": "pie_chart",
                "subject": "bar_chart",
            }
            viz_hint = viz_map.get(field, "table")

            response = ChatResponse(
                message=narrative or f"Aggregation on {field} complete.",
                candidate_set=None,
                suggested_followups=[
                    "Show publisher distribution",
                    "Show language breakdown",
                    "Start a new search",
                ],
                session_id=session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=analytical_result.confidence,
                metadata={
                    "visualization_hint": viz_hint,
                    "data": agg_data,
                    "analytical_intent": intent.value,
                },
            )
            return ChatResponseAPI(success=True, response=response, error=None)

        except Exception as e:
            logger.error("Aggregation failed: %s", e, exc_info=True)
            response = ChatResponse(
                message=f"Could not execute analytical query: {e}",
                candidate_set=None,
                session_id=session_id,
                phase=ConversationPhase.QUERY_DEFINITION,
            )
            return ChatResponseAPI(success=True, response=response, error=None)


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
async def health_extended():
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


@app.post("/chat", response_model=ChatResponseAPI)
@limiter.limit("10/minute")
async def chat(request: Request, chat_request: ChatRequest):
    """Chat endpoint with two-phase conversation support.

    Phase 1 (Query Definition):
    - Interprets query with confidence scoring
    - If confidence < 0.85: Returns clarification request
    - If confidence >= 0.85: Executes query, transitions to Phase 2

    Phase 2 (Corpus Exploration):
    - Handles exploration of the defined subgroup
    - Supports aggregation, enrichment, recommendations (future)

    Rate limited to 10 requests per minute per IP address.

    Args:
        request: FastAPI Request object (for rate limiting)
        chat_request: ChatRequest with message and optional session_id

    Returns:
        ChatResponseAPI with response message and results

    Raises:
        HTTPException: On API errors
    """
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
            # Create new session
            session = store.create_session()
            logger.info(
                "Created new session for chat request",
                extra={"session_id": session.session_id},
            )

        # Update context if provided
        if chat_request.context:
            store.update_context(session.session_id, chat_request.context)

        # Add user message to session
        user_message = Message(role="user", content=chat_request.message)
        store.add_message(session.session_id, user_message)

        # Get current conversation phase
        current_phase = store.get_phase(session.session_id)
        if current_phase is None:
            current_phase = ConversationPhase.QUERY_DEFINITION

        # Route based on phase
        if current_phase == ConversationPhase.QUERY_DEFINITION:
            return await handle_query_definition_phase(
                chat_request, session, store, bib_db
            )
        else:
            # Phase 2: Corpus Exploration
            return await handle_corpus_exploration_phase(
                chat_request, session, store, bib_db
            )

    except HTTPException:
        raise
    except Exception as e:
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


async def handle_query_definition_phase(
    chat_request: ChatRequest,
    session,
    store: SessionStore,
    bib_db: Path
) -> ChatResponseAPI:
    """Handle Phase 1: Three-stage scholar pipeline.

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
    scholar_response = await narrate(chat_request.message, execution_result)

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


async def handle_corpus_exploration_phase(
    chat_request: ChatRequest,
    session,
    store: SessionStore,
    bib_db: Path
) -> ChatResponseAPI:
    """Handle Phase 2: Corpus exploration with the active subgroup.

    Interprets exploration requests and routes to appropriate handlers:
    - AGGREGATION: Run aggregation query and return results
    - METADATA_QUESTION: Answer count/existence questions
    - REFINEMENT: Narrow the subgroup with additional filters
    - COMPARISON: Multi-faceted comparison of subsets within the subgroup
    - CROSS_REFERENCE: Discover agent relationships (teacher/student, co-publication, networks)
    - NEW_QUERY: Transition back to Phase 1
    - ENRICHMENT_REQUEST: Fetch external data about an entity
    - RECOMMENDATION: (Future) Recommend items

    Args:
        chat_request: The chat request
        session: Current session
        store: Session store
        bib_db: Path to bibliographic database

    Returns:
        ChatResponseAPI with response
    """
    try:
        # Get active subgroup
        active_subgroup = store.get_active_subgroup(session.session_id)
        if not active_subgroup:
            # No active subgroup - transition back to Phase 1
            logger.warning(
                "No active subgroup in exploration phase, transitioning to Phase 1",
                extra={"session_id": session.session_id}
            )
            store.update_phase(session.session_id, ConversationPhase.QUERY_DEFINITION)
            return await handle_query_definition_phase(
                chat_request, session, store, bib_db
            )

        # Interpret the exploration request
        exploration_request = await interpret_exploration_request(
            query_text=chat_request.message,
            active_subgroup=active_subgroup,
            conversation_history=session.get_recent_messages(5),
        )

        logger.info(
            "Interpreted exploration request",
            extra={
                "session_id": session.session_id,
                "intent": exploration_request.intent.value,
                "confidence": exploration_request.confidence,
            }
        )

        # Route based on intent
        if exploration_request.intent == ExplorationIntent.NEW_QUERY:
            # Transition back to Phase 1
            store.set_active_subgroup(session.session_id, None)
            store.update_phase(session.session_id, ConversationPhase.QUERY_DEFINITION)

            # If new query text provided, process it
            if exploration_request.new_query_text:
                # Create new request with the new query
                new_request = ChatRequest(
                    message=exploration_request.new_query_text,
                    session_id=session.session_id
                )
                return await handle_query_definition_phase(
                    new_request, session, store, bib_db
                )
            else:
                response = ChatResponse(
                    message="Let's start a new search. What would you like to find?",
                    session_id=session.session_id,
                    phase=ConversationPhase.QUERY_DEFINITION,
                )
                assistant_message = Message(
                    role="assistant",
                    content=response.message,
                )
                store.add_message(session.session_id, assistant_message)
                return ChatResponseAPI(success=True, response=response)

        elif exploration_request.intent == ExplorationIntent.AGGREGATION:
            # Execute aggregation query
            field = exploration_request.aggregation_field or "publisher"
            limit = exploration_request.aggregation_limit or 10

            aggregation_result = execute_aggregation(
                db_path=bib_db,
                record_ids=active_subgroup.record_ids,
                field=field,
                limit=limit
            )

            exploration_response = format_aggregation_response(
                aggregation_result, exploration_request
            )

            response = ChatResponse(
                message=exploration_response.message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=exploration_response.suggested_followups,
                metadata={
                    "visualization_hint": exploration_response.visualization_hint,
                    "data": exploration_response.data,
                }
            )

        elif exploration_request.intent == ExplorationIntent.METADATA_QUESTION:
            # Answer metadata question
            # Try to parse common questions
            question = exploration_request.metadata_question or chat_request.message
            question_lower = question.lower()

            count = None
            answer = ""

            if "latin" in question_lower:
                count = execute_count_query(bib_db, active_subgroup.record_ids, "count_language", "lat")
                total = len(active_subgroup.record_ids)
                answer = f"There are {count or 0} books in Latin in this collection of {total} books."
            elif "hebrew" in question_lower:
                count = execute_count_query(bib_db, active_subgroup.record_ids, "count_language", "heb")
                answer = f"There are {count or 0} books in Hebrew in this collection."
            elif "earliest" in question_lower or "oldest" in question_lower:
                earliest = execute_count_query(bib_db, active_subgroup.record_ids, "earliest_date")
                answer = (
                    f"The earliest book in this collection is from {earliest}."
                    if earliest else "No date information available."
                )
            elif any(w in question_lower for w in ("latest", "newest", "most recent")):
                latest = execute_count_query(bib_db, active_subgroup.record_ids, "latest_date")
                answer = (
                    f"The most recent book in this collection is from {latest}."
                    if latest else "No date information available."
                )
            elif "how many" in question_lower or "count" in question_lower:
                answer = f"There are {len(active_subgroup.record_ids)} books in this collection."
                count = len(active_subgroup.record_ids)
            else:
                n_books = len(active_subgroup.record_ids)
                answer = f"This collection contains {n_books} books. {exploration_request.explanation}"

            exploration_response = format_metadata_response(answer, count, exploration_request)

            response = ChatResponse(
                message=exploration_response.message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=exploration_response.suggested_followups,
            )

        elif exploration_request.intent == ExplorationIntent.REFINEMENT:
            # Apply refinement filters
            if exploration_request.refinement_filters:
                old_count = len(active_subgroup.record_ids)
                new_record_ids = active_subgroup.record_ids

                for f in exploration_request.refinement_filters:
                    new_record_ids = apply_refinement(
                        db_path=bib_db,
                        record_ids=new_record_ids,
                        field=f.field,
                        op=f.op,
                        value=f.value,
                        start=f.start,
                        end=f.end
                    )

                new_count = len(new_record_ids)

                if new_count > 0:
                    # Update active subgroup
                    new_subgroup = ActiveSubgroup(
                        candidate_set=active_subgroup.candidate_set,  # Keep original for reference
                        defining_query=f"{active_subgroup.defining_query} + refinement",
                        filter_summary=f"{active_subgroup.filter_summary}, refined",
                        record_ids=new_record_ids,
                    )
                    store.set_active_subgroup(session.session_id, new_subgroup)

                filter_desc = ", ".join(
                    f"{f.field}={f.value or f'{f.start}-{f.end}'}"
                    for f in exploration_request.refinement_filters
                )
                exploration_response = format_refinement_response(new_count, old_count, filter_desc)
            else:
                exploration_response = format_refinement_response(
                    len(active_subgroup.record_ids),
                    len(active_subgroup.record_ids),
                    "no filters applied"
                )

            response = ChatResponse(
                message=exploration_response.message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=exploration_response.suggested_followups,
                metadata=exploration_response.data,
            )

        elif exploration_request.intent == ExplorationIntent.COMPARISON:
            # Execute enhanced multi-faceted comparison
            if exploration_request.comparison_field and exploration_request.comparison_values:
                comparison_result = execute_comparison_enhanced(
                    db_path=bib_db,
                    record_ids=active_subgroup.record_ids,
                    field=exploration_request.comparison_field,
                    values=exploration_request.comparison_values,
                )

                # Format comparison message with facets
                n_books = len(active_subgroup.record_ids)
                field_name = exploration_request.comparison_field
                facets = comparison_result.facets
                parts = [f"Comparison of {field_name} in this collection of {n_books} books:"]
                parts.append("")

                # Counts
                for value, count in sorted(facets.counts.items(), key=lambda x: -x[1]):
                    pct = (count / n_books * 100) if n_books > 0 else 0
                    parts.append(f"- {value}: {count} books ({pct:.1f}%)")

                # Date ranges
                if facets.date_ranges:
                    parts.append("")
                    parts.append("Date ranges:")
                    for value, dr in facets.date_ranges.items():
                        if dr:
                            if isinstance(dr, (list, tuple)):
                                min_yr = dr[0] if dr[0] else None
                                max_yr = dr[1] if len(dr) > 1 and dr[1] else None
                            elif isinstance(dr, dict):
                                min_yr = dr.get("min")
                                max_yr = dr.get("max")
                            else:
                                min_yr = None
                                max_yr = None
                            if min_yr and max_yr:
                                parts.append(f"  - {value}: {min_yr}-{max_yr}")

                # Shared agents
                if facets.shared_agents:
                    parts.append("")
                    parts.append(f"Shared agents: {', '.join(facets.shared_agents[:5])}")

                # Subject overlap
                if facets.subject_overlap:
                    parts.append("")
                    parts.append(f"Shared subjects: {', '.join(facets.subject_overlap[:5])}")

                message = "\n".join(parts)
                comparison_data = comparison_result.model_dump()
                followups = [
                    f"Tell me about {exploration_request.comparison_values[0]}",
                    "Show top publishers",
                    "What are the most common subjects?",
                ]
            else:
                message = "I need specific values to compare. For example: 'Compare Paris vs London'"
                comparison_data = None
                followups = ["Show top publishers", "What are the most common subjects?"]

            response = ChatResponse(
                message=message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=followups,
                metadata={"comparison": comparison_data} if comparison_data else {},
            )

        elif exploration_request.intent == ExplorationIntent.CROSS_REFERENCE:
            # Cross-reference: discover agent relationships
            entity = exploration_request.cross_reference_entity
            scope = exploration_request.cross_reference_scope or "connections"

            if entity and scope == "network":
                # Network neighbor traversal for a specific entity
                network_connections = find_network_neighbors(
                    db=bib_db,
                    agent_norm=entity.lower(),
                )
                if network_connections:
                    parts = [f"Network for **{entity}** ({len(network_connections)} connections):"]
                    parts.append("")
                    for conn in network_connections:
                        parts.append(
                            f"- {conn.agent_a} -> {conn.agent_b} "
                            f"({conn.relationship_type}, confidence: {conn.confidence:.0%})"
                        )
                        parts.append(f"  Evidence: {conn.evidence}")
                    message = "\n".join(parts)
                    connections_data = [c.model_dump() for c in network_connections]
                else:
                    message = (
                        f"No network connections found for '{entity}'. "
                        f"This agent may not have teacher/student relationships "
                        f"in the enrichment data."
                    )
                    connections_data = []
            else:
                # Pairwise connections: either for a specific entity or all agents in subgroup
                if entity:
                    agent_norms_list = [entity.lower()]
                else:
                    # Collect all agent_norms from the active subgroup
                    agent_norms_set: set = set()
                    try:
                        import sqlite3
                        conn_db = sqlite3.connect(str(bib_db))
                        placeholders = ",".join("?" * len(active_subgroup.record_ids))
                        rows = conn_db.execute(
                            f"SELECT DISTINCT agent_norm FROM agents WHERE record_id IN "
                            f"(SELECT id FROM records WHERE mms_id IN ({placeholders}))",
                            active_subgroup.record_ids,
                        ).fetchall()
                        agent_norms_set = {r[0] for r in rows if r[0]}
                        conn_db.close()
                    except Exception:
                        pass
                    agent_norms_list = list(agent_norms_set)

                pairwise_connections = find_connections(
                    db=bib_db,
                    agent_norms=agent_norms_list,
                    max_results=20,
                )
                if pairwise_connections:
                    header = (
                        f"connections for **{entity}**"
                        if entity
                        else "connections between agents in this collection"
                    )
                    parts = [f"Found {len(pairwise_connections)} {header}:"]
                    parts.append("")
                    for conn in pairwise_connections:
                        parts.append(
                            f"- {conn.agent_a} <-> {conn.agent_b} "
                            f"({conn.relationship_type}, confidence: {conn.confidence:.0%})"
                        )
                        parts.append(f"  Evidence: {conn.evidence}")
                    message = "\n".join(parts)
                    connections_data = [c.model_dump() for c in pairwise_connections]
                else:
                    target = f"'{entity}'" if entity else "agents in this collection"
                    message = (
                        f"No connections found for {target}. "
                        f"Connections are discovered from teacher/student relationships, "
                        f"co-publications, and shared locations/periods."
                    )
                    connections_data = []

            suggested = []
            if entity:
                suggested.append(f"Tell me about {entity}")
                suggested.append(f"Show {entity} network" if scope != "network" else f"Show {entity} connections")
            suggested.append("Show top publishers")

            response = ChatResponse(
                message=message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=suggested,
                metadata={"connections": connections_data},
            )

        elif exploration_request.intent == ExplorationIntent.ENRICHMENT_REQUEST:
            # Enrichment - fetch external data about an entity
            entity = exploration_request.entity_value or "this entity"
            entity_type_str = exploration_request.entity_type or "agent"

            # Map entity type string to EnrichmentEntityType
            entity_type_map = {
                "agent": EnrichmentEntityType.AGENT,
                "place": EnrichmentEntityType.PLACE,
                "publisher": EnrichmentEntityType.PUBLISHER,
            }
            entity_type = entity_type_map.get(entity_type_str, EnrichmentEntityType.AGENT)

            # Try to fetch enrichment
            enrichment_result = None
            if enrichment_service and entity:
                try:
                    enrichment_result = await enrichment_service.enrich_entity(
                        entity_type=entity_type,
                        entity_value=entity,
                    )
                except Exception as e:
                    logger.warning(f"Enrichment failed for {entity}: {e}")

            if enrichment_result:
                # Format enrichment result
                parts = [f"Here's what I found about **{enrichment_result.label or entity}**:"]

                if enrichment_result.description:
                    parts.append(f"\n{enrichment_result.description}")

                if enrichment_result.person_info:
                    info = enrichment_result.person_info
                    if info.birth_year or info.death_year:
                        dates = f"{info.birth_year or '?'} - {info.death_year or '?'}"
                        parts.append(f"\n**Dates:** {dates}")
                    if info.birth_place:
                        parts.append(f"**Born in:** {info.birth_place}")
                    if info.occupations:
                        parts.append(f"**Occupations:** {', '.join(info.occupations[:5])}")
                    if info.nationality:
                        parts.append(f"**Nationality:** {info.nationality}")

                if enrichment_result.place_info:
                    info = enrichment_result.place_info
                    if info.country:
                        parts.append(f"\n**Country:** {info.country}")
                    if info.coordinates:
                        parts.append(f"**Coordinates:** {info.coordinates['lat']:.2f}, {info.coordinates['lon']:.2f}")

                # Add external links
                links = []
                if enrichment_result.wikidata_id:
                    links.append(f"[Wikidata](https://www.wikidata.org/wiki/{enrichment_result.wikidata_id})")
                if enrichment_result.viaf_id:
                    links.append(f"[VIAF](https://viaf.org/viaf/{enrichment_result.viaf_id})")
                if enrichment_result.wikipedia_url:
                    links.append(f"[Wikipedia]({enrichment_result.wikipedia_url})")

                if links:
                    parts.append(f"\n**External links:** {' | '.join(links)}")

                source = (
                    enrichment_result.sources_used[0].value
                    if enrichment_result.sources_used else "unknown"
                )
                conf = enrichment_result.confidence
                parts.append(f"\n\n*Source: {source} (confidence: {conf:.0%})*")

                message = "\n".join(parts)
                suggested_followups = [
                    f"Show books related to {entity}",
                    "Show top publishers",
                    "What's the date distribution?",
                ]
            else:
                message = (
                    f"I couldn't find external information about '{entity}'. "
                    f"This might be because:\n"
                    f"- The name spelling differs from authority records\n"
                    f"- No Wikidata entry exists for this entity\n"
                    f"- The entity type ('{entity_type_str}') might be incorrect\n\n"
                    f"Try rephrasing or asking about a different entity."
                )
                suggested_followups = ["Show top publishers", "Show top places"]

            response = ChatResponse(
                message=message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=suggested_followups,
            )

        elif exploration_request.intent == ExplorationIntent.RECOMMENDATION:
            # Intelligent recommendation / exhibit curation (E5)
            candidates = active_subgroup.record_ids
            count = exploration_request.recommendation_count or 10
            count = max(1, min(50, count))

            if not candidates:
                message = (
                    "There are no candidates in the current subgroup to recommend from. "
                    "Try defining a new search first."
                )
                response = ChatResponse(
                    message=message,
                    session_id=session.session_id,
                    phase=ConversationPhase.CORPUS_EXPLORATION,
                    confidence=exploration_request.confidence,
                    suggested_followups=["Start a new search", "Show collection overview"],
                )
            else:
                scored = score_candidates(candidates, bib_db)
                curation_result = select_diverse(scored, n=count)
                message = format_exhibit_response(curation_result)

                curation_metadata = {
                    "total_scored": curation_result.total_scored,
                    "selected_count": len(curation_result.selected),
                    "dimension_coverage": curation_result.dimension_coverage,
                    "selection_method": curation_result.selection_method,
                }
                if exploration_request.recommendation_criteria:
                    curation_metadata["criteria"] = exploration_request.recommendation_criteria

                suggested_followups = [
                    "Show more items",
                    "Refine criteria",
                    "Show the subject distribution",
                ]
                if len(curation_result.selected) < curation_result.total_scored:
                    suggested_followups.insert(
                        0,
                        f"Show {min(count + 10, 50)} items",
                    )

                response = ChatResponse(
                    message=message,
                    session_id=session.session_id,
                    phase=ConversationPhase.CORPUS_EXPLORATION,
                    confidence=exploration_request.confidence,
                    suggested_followups=suggested_followups,
                    metadata={"curation": curation_metadata},
                )

        else:
            # Unknown intent - provide helpful response
            response = ChatResponse(
                message=f"I'm not sure how to help with that. {exploration_request.explanation}\n\n"
                        f"You can ask me to:\n"
                        f"- Show top publishers, places, or languages\n"
                        f"- Filter to specific criteria (e.g., 'only Latin books')\n"
                        f"- Start a new search",
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                suggested_followups=["Show top publishers", "What languages are represented?", "Start a new search"],
            )

        # Add assistant message to session
        assistant_message = Message(
            role="assistant",
            content=response.message,
        )
        store.add_message(session.session_id, assistant_message)

        return ChatResponseAPI(success=True, response=response)

    except QueryCompilationError as e:
        # API error in exploration agent
        _error_msg = f"Error processing exploration request: {str(e)}"
        response = ChatResponse(
            message="I had trouble understanding that request. Could you rephrase?",
            session_id=session.session_id,
            phase=ConversationPhase.CORPUS_EXPLORATION,
            suggested_followups=["Show top publishers", "Start a new search"],
        )
        assistant_message = Message(
            role="assistant",
            content=response.message,
        )
        store.add_message(session.session_id, assistant_message)
        return ChatResponseAPI(success=True, response=response)


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
    _bib_db = get_db_path()  # retained for potential future use

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

        # ---- Stage 1: Interpret ----
        await websocket.send_json({
            "type": "progress",
            "message": "Interpreting your query..."
        })

        plan = await interpret(message, ws_session_context)

        await websocket.send_json({
            "type": "progress",
            "message": f"Understood: {', '.join(plan.intents)} (confidence: {plan.confidence:.0%})"
        })

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
        await websocket.send_json({
            "type": "progress",
            "message": f"Executing {len(plan.execution_steps)} plan steps..."
        })

        execution_result = execute_scholar_plan(
            plan, _bib_db, ws_session_context, original_query=message
        )

        records_found = len(execution_result.grounding.records)
        await websocket.send_json({
            "type": "progress",
            "message": f"Found {records_found} records. Composing scholarly response..."
        })

        # ---- Stage 3: Narrate ----
        scholar_response = await narrate(message, execution_result)

        # ---- Map to ChatResponse ----
        response = ChatResponse(
            message=scholar_response.narrative,
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
            Message(role="assistant", content=scholar_response.narrative),
        )

        await websocket.send_json({
            "type": "complete",
            "response": response.model_dump()
        })

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
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Internal error: {str(e)}"
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
