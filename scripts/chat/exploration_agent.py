"""Exploration Agent for Corpus Analysis (Phase 2).

This module provides the second phase of the two-phase conversational assistant:
- Interprets user requests for corpus exploration
- Classifies intent (aggregation, metadata question, enrichment, etc.)
- Routes to appropriate handlers for each intent type
- Handles transitions back to Phase 1 (new query) or refinements

The exploration agent uses OpenAI's Responses API with Pydantic schema enforcement.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIError
from pydantic import BaseModel, Field, ConfigDict

from scripts.chat.models import (
    Message,
    ActiveSubgroup,
    ExplorationIntent,
    ConversationPhase,
)
from scripts.schemas.query_plan import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.exceptions import QueryCompilationError


# =============================================================================
# Exploration Request/Response Models
# =============================================================================


class RefinementFilter(BaseModel):
    """A filter to narrow the current subgroup."""
    model_config = ConfigDict(extra='forbid')

    field: str = Field(..., description="Field to filter on: publisher, place, country, language, year, subject, agent")
    op: str = Field(..., description="Operation: EQUALS, CONTAINS, RANGE")
    value: Optional[str] = Field(None, description="Value for EQUALS/CONTAINS")
    start: Optional[int] = Field(None, description="Start year for RANGE")
    end: Optional[int] = Field(None, description="End year for RANGE")


class ExplorationRequestLLM(BaseModel):
    """LLM output for exploration request classification.

    Used with OpenAI's Responses API for strict schema validation.
    """
    model_config = ConfigDict(extra='forbid')

    intent: str = Field(
        ...,
        description="One of: metadata_question, aggregation, enrichment_request, recommendation, comparison, refinement, new_query"
    )
    explanation: str = Field(
        ...,
        description="Natural language explanation of what the user wants"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in intent classification"
    )

    # For AGGREGATION intent
    aggregation_field: Optional[str] = Field(
        None,
        description="Field to aggregate: publisher, place, country, language, date_decade, date_century, subject, agent"
    )
    aggregation_limit: Optional[int] = Field(
        None,
        description="Number of top results to return (e.g., 10 for 'top 10 publishers')"
    )

    # For METADATA_QUESTION intent
    metadata_question: Optional[str] = Field(
        None,
        description="The specific metadata question to answer"
    )

    # For ENRICHMENT_REQUEST intent
    entity_type: Optional[str] = Field(
        None,
        description="Type of entity: agent, place, publisher"
    )
    entity_value: Optional[str] = Field(
        None,
        description="The entity to enrich (e.g., 'Aldus Manutius')"
    )

    # For COMPARISON intent
    comparison_field: Optional[str] = Field(
        None,
        description="Field to compare: place, publisher, country, language"
    )
    comparison_values: Optional[List[str]] = Field(
        None,
        description="Values to compare (e.g., ['Paris', 'London'])"
    )

    # For REFINEMENT intent
    refinement_filters: Optional[List[RefinementFilter]] = Field(
        None,
        description="Filters to apply for refinement"
    )

    # For NEW_QUERY intent
    new_query_text: Optional[str] = Field(
        None,
        description="The new query to execute (if intent is new_query)"
    )


class ExplorationRequest(BaseModel):
    """Parsed exploration request with typed intent."""

    intent: ExplorationIntent
    explanation: str
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Intent-specific fields
    aggregation_field: Optional[str] = None
    aggregation_limit: Optional[int] = None
    metadata_question: Optional[str] = None
    entity_type: Optional[str] = None
    entity_value: Optional[str] = None
    comparison_field: Optional[str] = None
    comparison_values: Optional[List[str]] = None
    refinement_filters: Optional[List[RefinementFilter]] = None
    new_query_text: Optional[str] = None


class AggregationResult(BaseModel):
    """Result of an aggregation query."""

    field: str
    results: List[Dict[str, Any]]  # e.g., [{"value": "Oxford", "count": 42}, ...]
    total_in_subgroup: int
    query_description: str


class ExplorationResponse(BaseModel):
    """Response from exploration request."""

    intent: ExplorationIntent
    message: str  # Natural language response
    data: Optional[Dict[str, Any]] = None  # Structured data (aggregation results, etc.)
    visualization_hint: Optional[str] = None  # "bar_chart", "pie_chart", "table", etc.
    suggested_followups: List[str] = Field(default_factory=list)

    # For phase transitions
    new_phase: Optional[ConversationPhase] = None
    new_query_plan: Optional[QueryPlan] = None


# =============================================================================
# System Prompt for Exploration Intent Classification
# =============================================================================

EXPLORATION_AGENT_SYSTEM_PROMPT = """You are a research assistant helping analyze a corpus of rare books.

The user has already defined a subgroup of books through a search query. Now they want to explore this collection.

CURRENT SUBGROUP:
- Original query: {defining_query}
- Filter summary: {filter_summary}
- Record count: {record_count}

YOUR TASK:
Classify the user's request into one of these intent types and extract relevant parameters.

INTENT TYPES:

1. METADATA_QUESTION
   - Simple count/existence questions about the subgroup
   - Examples: "How many are in Latin?", "Are there any from Venice?", "What's the earliest book?"
   - Set metadata_question to the specific question

2. AGGREGATION
   - Requests for grouped statistics
   - Examples: "Top 10 publishers", "Books by decade", "Language breakdown", "Places of publication"
   - Set aggregation_field to one of: publisher, place, country, language, date_decade, date_century, subject, agent
   - Set aggregation_limit for "top N" requests (default 10)

3. ENRICHMENT_REQUEST
   - Requests for external information about an entity
   - Examples: "Tell me about Aldus Manutius", "Who was this printer?", "Information about Venice"
   - Set entity_type (agent, place, publisher) and entity_value

4. RECOMMENDATION
   - Requests for specific recommendations within the subgroup
   - Examples: "Most relevant for astronomy", "Best examples of incunabula"
   - (Future feature - classify but note limited support)

5. COMPARISON
   - Comparing subsets within the subgroup
   - Examples: "Compare Paris vs London", "Latin vs Hebrew books"
   - Set comparison_field and comparison_values

6. REFINEMENT
   - Narrowing the current subgroup with additional filters
   - Examples: "Only Latin books", "Just the 16th century ones", "From Venice only"
   - Set refinement_filters with the new constraints

7. NEW_QUERY
   - User wants to start a completely new search
   - Examples: "Let's search for something else", "New query: books about astronomy"
   - Set new_query_text if they provide the new query

AGGREGATION FIELDS:
- publisher: Group by publisher_norm
- place: Group by place_norm (city)
- country: Group by country_name
- language: Group by language code
- date_decade: Group by decade (1500s, 1510s, etc.)
- date_century: Group by century (16th, 17th, etc.)
- subject: Group by subject heading
- agent: Group by agent_norm (printers, authors, etc.)

EXAMPLES:

User: "What are the top publishers?"
{{
  "intent": "aggregation",
  "explanation": "You want to see the most frequent publishers in this collection.",
  "confidence": 0.95,
  "aggregation_field": "publisher",
  "aggregation_limit": 10
}}

User: "How many books are in Latin?"
{{
  "intent": "metadata_question",
  "explanation": "You want to know the count of Latin books in this collection.",
  "confidence": 0.95,
  "metadata_question": "Count of books in Latin"
}}

User: "Only show me books from Paris"
{{
  "intent": "refinement",
  "explanation": "You want to narrow the collection to only books published in Paris.",
  "confidence": 0.92,
  "refinement_filters": [{{"field": "place", "op": "EQUALS", "value": "paris"}}]
}}

User: "Let's look for Hebrew books instead"
{{
  "intent": "new_query",
  "explanation": "You want to start a new search for Hebrew books.",
  "confidence": 0.90,
  "new_query_text": "Hebrew books"
}}

User: "Compare Venice and Rome"
{{
  "intent": "comparison",
  "explanation": "You want to compare books published in Venice vs Rome.",
  "confidence": 0.93,
  "comparison_field": "place",
  "comparison_values": ["venice", "rome"]
}}
"""


# =============================================================================
# Exploration Intent Classification
# =============================================================================


async def interpret_exploration_request(
    query_text: str,
    active_subgroup: ActiveSubgroup,
    conversation_history: Optional[List[Message]] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o"
) -> ExplorationRequest:
    """Classify user's exploration request and extract parameters.

    Args:
        query_text: User's request
        active_subgroup: Current subgroup being explored
        conversation_history: Recent messages for context
        api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        model: Model to use

    Returns:
        ExplorationRequest with classified intent and parameters

    Raises:
        QueryCompilationError: If API call fails
    """
    # Get API key
    api_key_to_use = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key_to_use:
        raise QueryCompilationError.from_missing_api_key()

    # Build system prompt with subgroup context
    system_prompt = EXPLORATION_AGENT_SYSTEM_PROMPT.format(
        defining_query=active_subgroup.defining_query,
        filter_summary=active_subgroup.filter_summary,
        record_count=len(active_subgroup.record_ids)
    )

    # Build user message with conversation context
    user_parts = []
    if conversation_history:
        user_parts.append("Recent conversation:")
        for msg in conversation_history[-3:]:
            user_parts.append(f"  {msg.role}: {msg.content[:200]}")
        user_parts.append("")

    user_parts.append(f"User request: {query_text}")
    user_message = "\n".join(user_parts)

    # Initialize client and call LLM
    client = OpenAI(api_key=api_key_to_use)

    try:
        resp = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            text_format=ExplorationRequestLLM,
        )

        llm_output = resp.output_parsed

        # Convert to ExplorationRequest with typed intent
        try:
            intent = ExplorationIntent(llm_output.intent)
        except ValueError:
            # Default to metadata question if intent not recognized
            intent = ExplorationIntent.METADATA_QUESTION

        # Convert refinement filters if present
        refinement_filters = None
        if llm_output.refinement_filters:
            refinement_filters = [
                RefinementFilter(
                    field=f.field,
                    op=f.op,
                    value=f.value,
                    start=f.start,
                    end=f.end
                )
                for f in llm_output.refinement_filters
            ]

        return ExplorationRequest(
            intent=intent,
            explanation=llm_output.explanation,
            confidence=llm_output.confidence,
            aggregation_field=llm_output.aggregation_field,
            aggregation_limit=llm_output.aggregation_limit,
            metadata_question=llm_output.metadata_question,
            entity_type=llm_output.entity_type,
            entity_value=llm_output.entity_value,
            comparison_field=llm_output.comparison_field,
            comparison_values=llm_output.comparison_values,
            refinement_filters=refinement_filters,
            new_query_text=llm_output.new_query_text,
        )

    except AuthenticationError as e:
        raise QueryCompilationError.from_api_error(e)
    except RateLimitError as e:
        raise QueryCompilationError.from_api_error(e)
    except APITimeoutError as e:
        raise QueryCompilationError.from_api_error(e)
    except APIError as e:
        raise QueryCompilationError.from_api_error(e)
    except Exception as e:
        raise QueryCompilationError.from_invalid_response(e)


# =============================================================================
# Response Formatting Helpers
# =============================================================================


def format_aggregation_response(
    aggregation_result: AggregationResult,
    exploration_request: ExplorationRequest
) -> ExplorationResponse:
    """Format aggregation results as a natural language response.

    Args:
        aggregation_result: The aggregation query result
        exploration_request: Original exploration request

    Returns:
        ExplorationResponse with formatted message and data
    """
    field_display = {
        "publisher": "publishers",
        "place": "places of publication",
        "country": "countries",
        "language": "languages",
        "date_decade": "decades",
        "date_century": "centuries",
        "subject": "subjects",
        "agent": "authors/printers"
    }

    field_name = field_display.get(aggregation_result.field, aggregation_result.field)
    limit = exploration_request.aggregation_limit or 10

    # Build message
    parts = [f"Here are the top {min(limit, len(aggregation_result.results))} {field_name} in this collection of {aggregation_result.total_in_subgroup} books:"]
    parts.append("")

    for i, item in enumerate(aggregation_result.results[:limit], 1):
        value = item.get("value", "Unknown")
        count = item.get("count", 0)
        pct = (count / aggregation_result.total_in_subgroup * 100) if aggregation_result.total_in_subgroup > 0 else 0
        parts.append(f"{i}. {value}: {count} books ({pct:.1f}%)")

    # Suggest follow-ups
    followups = []
    if aggregation_result.results:
        top_value = aggregation_result.results[0].get("value", "")
        if top_value:
            followups.append(f"Tell me more about {top_value}")
            followups.append(f"Show only books from {top_value}")
    followups.append(f"Show {field_name} breakdown as a chart")

    return ExplorationResponse(
        intent=ExplorationIntent.AGGREGATION,
        message="\n".join(parts),
        data={
            "field": aggregation_result.field,
            "results": aggregation_result.results[:limit],
            "total": aggregation_result.total_in_subgroup
        },
        visualization_hint="bar_chart",
        suggested_followups=followups
    )


def format_metadata_response(
    answer: str,
    count: Optional[int] = None,
    exploration_request: ExplorationRequest = None
) -> ExplorationResponse:
    """Format metadata question response.

    Args:
        answer: The answer to the metadata question
        count: Optional count value
        exploration_request: Original request

    Returns:
        ExplorationResponse
    """
    followups = []
    if count and count > 0:
        followups.append("Show me some examples")
        followups.append("What are the most common subjects?")

    return ExplorationResponse(
        intent=ExplorationIntent.METADATA_QUESTION,
        message=answer,
        data={"count": count} if count is not None else None,
        suggested_followups=followups
    )


def format_refinement_response(
    new_count: int,
    old_count: int,
    filter_description: str
) -> ExplorationResponse:
    """Format refinement response.

    Args:
        new_count: Number of records after refinement
        old_count: Number of records before refinement
        filter_description: Description of applied filter

    Returns:
        ExplorationResponse
    """
    if new_count == 0:
        message = f"No books match '{filter_description}' within the current collection. The subgroup remains unchanged with {old_count} books."
        return ExplorationResponse(
            intent=ExplorationIntent.REFINEMENT,
            message=message,
            data={"new_count": new_count, "old_count": old_count, "applied": False},
            suggested_followups=[
                "Show the current collection",
                "Try a different filter",
                "Start a new search"
            ]
        )

    message = f"Narrowed from {old_count} to {new_count} books by filtering to {filter_description}."
    if new_count < old_count:
        message += f"\n\nWhat would you like to know about these {new_count} books?"

    return ExplorationResponse(
        intent=ExplorationIntent.REFINEMENT,
        message=message,
        data={"new_count": new_count, "old_count": old_count, "applied": True},
        suggested_followups=[
            "Show top publishers",
            "What are the most common subjects?",
            "Show the date distribution"
        ]
    )


def format_new_query_response(new_query: str) -> ExplorationResponse:
    """Format response for transitioning to a new query.

    Args:
        new_query: The new query text

    Returns:
        ExplorationResponse with phase transition
    """
    return ExplorationResponse(
        intent=ExplorationIntent.NEW_QUERY,
        message=f"Starting a new search for: {new_query}",
        new_phase=ConversationPhase.QUERY_DEFINITION,
        suggested_followups=[]
    )
