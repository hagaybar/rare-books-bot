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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.models import ChatRequest, ChatResponseAPI, HealthResponse
from scripts.chat.models import (
    ChatResponse,
    Message,
    ConversationPhase,
    ActiveSubgroup,
)
from scripts.chat.session_store import SessionStore
from scripts.chat.formatter import format_for_chat, generate_followups
from scripts.chat.clarification import (
    should_ask_for_clarification,
    generate_clarification_message,
    detect_ambiguous_query,
    is_execution_blocking,
    get_refinement_suggestions_for_query,
)
from scripts.chat.intent_agent import (
    interpret_query,
    generate_clarification_prompt,
    format_interpretation_for_user,
    CONFIDENCE_THRESHOLD,
)
from scripts.chat.exploration_agent import (
    interpret_exploration_request,
    format_aggregation_response,
    format_metadata_response,
    format_refinement_response,
    format_new_query_response,
    ExplorationIntent,
    ExplorationRequest,
    ExplorationResponse,
)
from scripts.chat.aggregation import (
    execute_aggregation,
    execute_count_query,
    apply_refinement,
    execute_comparison,
    is_overview_query,
    get_collection_overview,
    format_collection_overview,
)
from scripts.query import QueryService, QueryOptions, QueryCompilationError
from scripts.query.compile import compile_query
from scripts.query.execute import execute_plan
from scripts.utils.logger import LoggerManager
from scripts.enrichment import EnrichmentService, EntityType as EnrichmentEntityType

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
enrichment_service: Optional[EnrichmentService] = None
query_service: Optional[QueryService] = None


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


@app.on_event("startup")
async def startup_event():
    """Initialize application state on startup."""
    global session_store, db_path, enrichment_service, query_service

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


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    if session_store is not None:
        session_store.close()
    if enrichment_service is not None:
        enrichment_service.close()
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
    """Handle Phase 1: Query definition with confidence scoring.

    Uses the intent agent to interpret the query with confidence scoring.
    If confidence >= 0.85, executes query and transitions to corpus exploration.
    If confidence < 0.85, asks for clarification.

    Special handling for overview queries (e.g., "what can you tell me about
    the collection?") - returns collection statistics instead of clarification.

    Args:
        chat_request: The chat request
        session: Current session
        store: Session store
        bib_db: Path to bibliographic database

    Returns:
        ChatResponseAPI with response
    """
    try:
        # Check if this is an overview/introductory query
        if is_overview_query(chat_request.message):
            logger.info(
                "Detected overview query, returning collection statistics",
                extra={"session_id": session.session_id}
            )

            # Get and format collection overview
            overview = get_collection_overview(bib_db)
            overview_message = format_collection_overview(overview)

            # Build response
            response = ChatResponse(
                message=overview_message,
                candidate_set=None,
                suggested_followups=[
                    "Show me 16th century books",
                    "Books printed in Venice",
                    "Hebrew books from Amsterdam",
                    "Books about astronomy",
                ],
                clarification_needed=None,
                session_id=session.session_id,
                phase=ConversationPhase.QUERY_DEFINITION,
                confidence=1.0,  # High confidence for overview
                metadata={"overview_stats": overview},
            )

            # Add assistant message to session
            assistant_message = Message(
                role="assistant",
                content=overview_message,
            )
            store.add_message(session.session_id, assistant_message)

            return ChatResponseAPI(success=True, response=response, error=None)

        # Use intent agent for interpretation with confidence scoring
        interpretation = await interpret_query(
            query_text=chat_request.message,
            session_context=session.context,
            conversation_history=session.get_recent_messages(5),
        )

        logger.info(
            "Interpreted query",
            extra={
                "session_id": session.session_id,
                "confidence": interpretation.overall_confidence,
                "proceed": interpretation.proceed_to_execution,
                "filters": len(interpretation.query_plan.filters),
            },
        )

        # Check if we should proceed (confidence >= 0.85)
        if not interpretation.proceed_to_execution:
            # Low confidence - ask for clarification
            clarification_msg = generate_clarification_prompt(interpretation)

            response = ChatResponse(
                message=interpretation.explanation,
                candidate_set=None,
                clarification_needed=clarification_msg,
                session_id=session.session_id,
                phase=ConversationPhase.QUERY_DEFINITION,
                confidence=interpretation.overall_confidence,
                metadata={
                    "uncertainties": interpretation.uncertainties,
                    "filters_extracted": len(interpretation.query_plan.filters),
                },
            )

            # Add assistant clarification to session
            assistant_message = Message(
                role="assistant",
                content=f"{interpretation.explanation}\n\n{clarification_msg}",
                query_plan=interpretation.query_plan,
                candidate_set=None,
            )
            store.add_message(session.session_id, assistant_message)

            logger.info(
                "Requesting clarification (low confidence)",
                extra={
                    "session_id": session.session_id,
                    "confidence": interpretation.overall_confidence,
                },
            )

            return ChatResponseAPI(success=True, response=response, error=None)

        # High confidence - execute query via QueryService
        query_plan = interpretation.query_plan
        service = get_query_service()
        query_result = service.execute_plan(query_plan, options=QueryOptions(compute_facets=True))
        candidate_set = query_result.candidate_set
        result_count = len(candidate_set.candidates)

        logger.info(
            "Executed query",
            extra={
                "session_id": session.session_id,
                "candidates_found": result_count,
            },
        )

        # Check for zero results (may need clarification)
        clarification_message = None
        if result_count == 0:
            clarification_message = (
                "I didn't find any books matching these criteria. "
                "Would you like to:\n"
                "- Broaden your search (e.g., wider date range)?\n"
                "- Try different terms?\n"
                "- Search for a related topic?"
            )

        # Format response with interpretation explanation
        user_explanation = format_interpretation_for_user(interpretation, result_count)

        # Build exploration prompt for Phase 2
        if result_count > 0:
            exploration_prompt = (
                f"\n\nWhat would you like to know about this collection? I can:\n"
                f"- Show top publishers or places of publication\n"
                f"- Analyze the date distribution\n"
                f"- Find books on specific topics within this set\n"
                f"- Tell you about specific printers or authors"
            )
            response_message = user_explanation + exploration_prompt

            # Add optional refinement suggestions (non-blocking)
            # These help users refine broad searches without blocking results
            refinement_tip = get_refinement_suggestions_for_query(query_plan, result_count)
            if refinement_tip:
                response_message += f"\n\n{refinement_tip}"
        else:
            response_message = user_explanation

        # Generate follow-up suggestions
        suggested_followups = generate_followups(candidate_set, query_plan.query_text)

        # Create response
        response = ChatResponse(
            message=response_message,
            candidate_set=candidate_set,
            suggested_followups=suggested_followups,
            clarification_needed=clarification_message,
            session_id=session.session_id,
            phase=ConversationPhase.CORPUS_EXPLORATION if result_count > 0 else ConversationPhase.QUERY_DEFINITION,
            confidence=interpretation.overall_confidence,
            metadata={
                "explanation": interpretation.explanation,
                "filters_count": len(query_plan.filters),
            },
        )

        # Transition to corpus exploration if we have results
        if result_count > 0:
            # Create and store active subgroup
            active_subgroup = ActiveSubgroup(
                candidate_set=candidate_set,
                defining_query=chat_request.message,
                filter_summary=interpretation.explanation,
            )
            store.set_active_subgroup(session.session_id, active_subgroup)
            store.update_phase(session.session_id, ConversationPhase.CORPUS_EXPLORATION)

            logger.info(
                "Transitioned to corpus exploration",
                extra={
                    "session_id": session.session_id,
                    "subgroup_size": result_count,
                },
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

    except QueryCompilationError as e:
        # Fallback to old behavior for compilation errors
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
            phase=ConversationPhase.QUERY_DEFINITION,
        )

        assistant_message = Message(
            role="assistant",
            content=error_msg,
            query_plan=None,
            candidate_set=None,
        )
        store.add_message(session.session_id, assistant_message)

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
    - COMPARISON: Compare subsets within the subgroup
    - NEW_QUERY: Transition back to Phase 1
    - ENRICHMENT_REQUEST: (Future) Fetch external data
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
                answer = f"There are {count or 0} books in Latin in this collection of {len(active_subgroup.record_ids)} books."
            elif "hebrew" in question_lower:
                count = execute_count_query(bib_db, active_subgroup.record_ids, "count_language", "heb")
                answer = f"There are {count or 0} books in Hebrew in this collection."
            elif "earliest" in question_lower or "oldest" in question_lower:
                earliest = execute_count_query(bib_db, active_subgroup.record_ids, "earliest_date")
                answer = f"The earliest book in this collection is from {earliest}." if earliest else "No date information available."
            elif "latest" in question_lower or "newest" in question_lower or "most recent" in question_lower:
                latest = execute_count_query(bib_db, active_subgroup.record_ids, "latest_date")
                answer = f"The most recent book in this collection is from {latest}." if latest else "No date information available."
            elif "how many" in question_lower or "count" in question_lower:
                answer = f"There are {len(active_subgroup.record_ids)} books in this collection."
                count = len(active_subgroup.record_ids)
            else:
                answer = f"This collection contains {len(active_subgroup.record_ids)} books. {exploration_request.explanation}"

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
            # Execute comparison
            if exploration_request.comparison_field and exploration_request.comparison_values:
                comparison_results = execute_comparison(
                    db_path=bib_db,
                    record_ids=active_subgroup.record_ids,
                    field=exploration_request.comparison_field,
                    values=exploration_request.comparison_values
                )

                # Format comparison message
                parts = [f"Comparison of {exploration_request.comparison_field} in this collection of {len(active_subgroup.record_ids)} books:"]
                parts.append("")
                for value, count in sorted(comparison_results.items(), key=lambda x: -x[1]):
                    pct = (count / len(active_subgroup.record_ids) * 100) if active_subgroup.record_ids else 0
                    parts.append(f"- {value}: {count} books ({pct:.1f}%)")

                message = "\n".join(parts)
            else:
                message = "I need specific values to compare. For example: 'Compare Paris vs London'"

            response = ChatResponse(
                message=message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=["Show top publishers", "What are the most common subjects?"],
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

                parts.append(f"\n\n*Source: {enrichment_result.sources_used[0].value if enrichment_result.sources_used else 'unknown'} (confidence: {enrichment_result.confidence:.0%})*")

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
            # Recommendation - future feature
            message = (
                "Recommendations based on your research goals are not yet available. "
                "In the future, I'll be able to suggest the most relevant books based on "
                "your interests and research context."
            )
            response = ChatResponse(
                message=message,
                session_id=session.session_id,
                phase=ConversationPhase.CORPUS_EXPLORATION,
                confidence=exploration_request.confidence,
                suggested_followups=["Show the subject distribution", "What are the most common topics?"],
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
        error_msg = f"Error processing exploration request: {str(e)}"
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

            # Check for execution-blocking ambiguity (only empty_filters blocks)
            # Other ambiguities become suggestions after execution
            _, reason_before = detect_ambiguous_query(query_plan, result_count=1)

            if is_execution_blocking(reason_before):
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

        # Execute query via QueryService
        service = get_query_service()
        query_result = service.execute_plan(query_plan, options=QueryOptions(compute_facets=False))
        candidate_set = query_result.candidate_set
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

        # Add refinement suggestions for broad queries (non-blocking)
        if result_count > 0:
            refinement_tip = get_refinement_suggestions_for_query(query_plan, result_count)
            if refinement_tip:
                response_message += f"\n\n{refinement_tip}"

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
