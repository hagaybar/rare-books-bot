"""Intent Agent for Query Interpretation with Confidence Scoring.

This module provides the first phase of the two-phase conversational assistant:
- Interprets user queries with overall confidence scoring
- Returns natural language explanation of what was understood
- Identifies specific uncertainties when confidence is low
- Determines whether to proceed to execution (confidence >= 0.85)

The intent agent uses OpenAI's Responses API with Pydantic schema enforcement.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIError
from pydantic import BaseModel, Field, ConfigDict

from scripts.schemas.query_plan import QueryPlan, Filter, FilterField, FilterOp
from scripts.chat.models import Message
from scripts.query.exceptions import QueryCompilationError
from scripts.utils.llm_logger import log_llm_call


# Confidence threshold for proceeding to execution
CONFIDENCE_THRESHOLD = 0.85

# Cache configuration
INTENT_CACHE_PATH = Path("data/intent_cache.jsonl")


# =============================================================================
# LLM-Specific Models for OpenAI Responses API
# These must have extra='forbid' and no Dict[str, Any] fields
# =============================================================================


class FilterLLM(BaseModel):
    """LLM-compatible filter model for OpenAI strict schema.

    Must use string literals for field and op to satisfy additionalProperties: false.
    """
    model_config = ConfigDict(extra='forbid')

    field: str = Field(
        ...,
        description="Filter field: publisher, imprint_place, country, year, language, title, subject, agent_norm, agent_role"
    )
    op: str = Field(
        ...,
        description="Operation: EQUALS, CONTAINS, RANGE, IN"
    )
    value: Optional[str] = Field(
        None,
        description="Value for EQUALS/CONTAINS operations"
    )
    start: Optional[int] = Field(
        None,
        description="Start year for RANGE operation"
    )
    end: Optional[int] = Field(
        None,
        description="End year for RANGE operation"
    )
    negate: bool = Field(
        False,
        description="Negate the filter (NOT)"
    )
    confidence: Optional[float] = Field(
        None,
        description="Confidence in this filter (0.0-1.0)"
    )
    notes: Optional[str] = Field(
        None,
        description="Notes about this filter interpretation"
    )


class QueryPlanLLM(BaseModel):
    """LLM-compatible QueryPlan model for OpenAI strict schema.

    Excludes the 'debug' field which uses Dict[str, Any].
    """
    model_config = ConfigDict(extra='forbid')

    version: str = Field(
        "1.0",
        description="Schema version"
    )
    query_text: str = Field(
        ...,
        description="Original query text"
    )
    filters: List[FilterLLM] = Field(
        default_factory=list,
        description="List of filter conditions (AND semantics)"
    )
    soft_filters: List[FilterLLM] = Field(
        default_factory=list,
        description="Optional filters that can be relaxed"
    )
    limit: Optional[int] = Field(
        None,
        description="Maximum number of results"
    )


class IntentInterpretationLLM(BaseModel):
    """Model for LLM output (without computed fields).

    This is sent to OpenAI's Responses API with strict schema validation.
    """
    model_config = ConfigDict(extra='forbid')

    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence in understanding the user's intent (0.0-1.0)"
    )
    explanation: str = Field(
        ...,
        description="Natural language explanation of what was understood"
    )
    uncertainties: List[str] = Field(
        default_factory=list,
        description="Specific areas of uncertainty if confidence < 0.85"
    )
    query_plan: QueryPlanLLM = Field(
        ...,
        description="Structured QueryPlan for execution"
    )


class IntentInterpretation(BaseModel):
    """Result of intent analysis.

    Attributes:
        overall_confidence: Single confidence score for the entire interpretation
        explanation: Natural language explanation of what was understood
        uncertainties: List of specific uncertainties if confidence is low
        query_plan: The compiled QueryPlan for execution
        proceed_to_execution: Whether to execute (confidence >= threshold OR has valid filters)
    """
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    uncertainties: List[str] = Field(default_factory=list)
    query_plan: QueryPlan
    proceed_to_execution: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        # Compute proceed_to_execution based on:
        # 1. High confidence (>= threshold), OR
        # 2. At least one valid filter exists (execute first, suggest refinements later)
        #
        # Philosophy: If we have extractable filters, execute immediately rather than
        # asking for clarification. Users get results faster, and refinements become
        # helpful suggestions rather than blockers.
        has_valid_filters = len(self.query_plan.filters) > 0
        proceed = self.overall_confidence >= CONFIDENCE_THRESHOLD or has_valid_filters
        object.__setattr__(self, 'proceed_to_execution', proceed)


# System prompt for intent interpretation
INTENT_AGENT_SYSTEM_PROMPT = """You are an intent interpreter for a rare books bibliographic search system.

Your task is to analyze user queries and:
1. Extract search criteria (publisher, date, place, country, subject, language, etc.)
2. Assess your OVERALL CONFIDENCE in understanding the user's intent
3. Explain what you understood in natural language
4. Identify specific uncertainties if confidence is below 0.85

CONFIDENCE SCORING RULES:
- 0.95-1.0: Clear, unambiguous query with specific criteria (dates, names, places)
- 0.85-0.94: Mostly clear, minor ambiguities resolved with reasonable assumptions
- 0.70-0.84: Multiple interpretations possible, needs clarification
- Below 0.70: Query is too vague or unclear to proceed

FILTER FIELDS AVAILABLE:
- publisher: Publisher name (use for "published by X")
- imprint_place: City of publication (use for cities like Venice, London, Paris)
- country: Country of publication (use for countries like Germany, France, Italy)
- year: Publication year range (requires start and end years)
- language: Language code (lat=Latin, heb=Hebrew, eng=English, fre=French, ger=German, ita=Italian)
- title: Title search (partial match)
- subject: Subject heading search (partial match)
- agent_norm: Agent/person name (printers, authors, translators)
- agent_role: Role (printer, author, translator, editor, etc.)

OPERATIONS:
- EQUALS: Exact match (use for specific entities)
- CONTAINS: Partial match (use for titles, subjects, uncertain terms)
- RANGE: For year ranges (requires start and end integers)

COUNTRY vs CITY DISTINCTION:
- "books from Germany" → country filter (country of publication)
- "books from Venice" → imprint_place filter (city of publication)
- "French books" → country=france (adjective implies country)
- "books printed in Paris" → imprint_place=paris (specific city)

CENTURY CONVERSION:
- 15th century = 1401-1500
- 16th century = 1501-1600
- 17th century = 1601-1700
- 18th century = 1701-1800

EXPLANATION GUIDELINES:
- Start with "You're looking for..." or "I understand you want..."
- Be specific about what criteria you extracted
- Mention any assumptions you made
- If uncertain, explain what needs clarification

EXAMPLES:

Query: "books published by Oxford between 1500 and 1599"
{
  "overall_confidence": 0.95,
  "explanation": "You're looking for books published by Oxford (interpreted as Oxford University Press or Oxford-based publisher) during the years 1500-1599.",
  "uncertainties": [],
  "query_plan": {
    "version": "1.0",
    "query_text": "books published by Oxford between 1500 and 1599",
    "filters": [
      {"field": "publisher", "op": "EQUALS", "value": "oxford"},
      {"field": "year", "op": "RANGE", "start": 1500, "end": 1599}
    ],
    "soft_filters": [],
    "limit": null
  }
}

Query: "old books from Paris"
{
  "overall_confidence": 0.60,
  "explanation": "You're looking for books published in Paris, but the timeframe is unclear. 'Old' could mean many different periods.",
  "uncertainties": [
    "What time period does 'old' refer to? (15th century? 16th century? Before 1800?)",
    "Are you interested in books on a specific subject or topic?"
  ],
  "query_plan": {
    "version": "1.0",
    "query_text": "old books from Paris",
    "filters": [
      {"field": "imprint_place", "op": "EQUALS", "value": "paris"}
    ],
    "soft_filters": [],
    "limit": null
  }
}

Query: "books from Germany in the 16th century"
{
  "overall_confidence": 0.92,
  "explanation": "You're looking for books published in Germany during the 16th century (1501-1600).",
  "uncertainties": [],
  "query_plan": {
    "version": "1.0",
    "query_text": "books from Germany in the 16th century",
    "filters": [
      {"field": "country", "op": "EQUALS", "value": "germany"},
      {"field": "year", "op": "RANGE", "start": 1501, "end": 1600}
    ],
    "soft_filters": [],
    "limit": null
  }
}

Query: "Latin texts on astronomy printed in Venice"
{
  "overall_confidence": 0.93,
  "explanation": "You're looking for Latin-language books about astronomy that were printed in Venice.",
  "uncertainties": [],
  "query_plan": {
    "version": "1.0",
    "query_text": "Latin texts on astronomy printed in Venice",
    "filters": [
      {"field": "language", "op": "EQUALS", "value": "lat"},
      {"field": "subject", "op": "CONTAINS", "value": "Astronomy"},
      {"field": "imprint_place", "op": "EQUALS", "value": "venice"}
    ],
    "soft_filters": [],
    "limit": null
  }
}

Query: "books"
{
  "overall_confidence": 0.15,
  "explanation": "This query is too broad to search effectively. I need more specific criteria.",
  "uncertainties": [
    "What subject or topic are you interested in?",
    "What time period or century?",
    "Any specific publisher, printer, or author?",
    "A particular place or country of publication?",
    "A specific language (Latin, Hebrew, etc.)?"
  ],
  "query_plan": {
    "version": "1.0",
    "query_text": "books",
    "filters": [],
    "soft_filters": [],
    "limit": null
  }
}

Query: "Hebrew manuscripts from the 17th century"
{
  "overall_confidence": 0.88,
  "explanation": "You're looking for Hebrew-language works from the 17th century (1601-1700). Note: This database contains printed books, not manuscripts, but I'll search for Hebrew printed works from this period.",
  "uncertainties": [
    "This collection contains printed books rather than manuscripts. Should I search for printed Hebrew books instead?"
  ],
  "query_plan": {
    "version": "1.0",
    "query_text": "Hebrew manuscripts from the 17th century",
    "filters": [
      {"field": "language", "op": "EQUALS", "value": "heb"},
      {"field": "year", "op": "RANGE", "start": 1601, "end": 1700}
    ],
    "soft_filters": [],
    "limit": null
  }
}

IMPORTANT:
- Always provide an overall_confidence score
- Always provide a natural language explanation
- List uncertainties if confidence < 0.85
- The query_plan must be valid JSON matching the schema
- Normalize values (lowercase for publisher, place, country)
- Use ISO 639-2 language codes (lat, heb, eng, fre, ger, ita, spa)
"""


def build_user_prompt(
    query_text: str,
    conversation_history: Optional[List[Message]] = None,
    session_context: Optional[Dict[str, Any]] = None
) -> str:
    """Build user prompt with optional conversation context.

    Args:
        query_text: The user's natural language query
        conversation_history: Recent messages for context
        session_context: Session state (may include previous queries)

    Returns:
        Formatted prompt string
    """
    prompt_parts = []

    # Add conversation history if available
    if conversation_history and len(conversation_history) > 0:
        prompt_parts.append("CONVERSATION CONTEXT:")
        for msg in conversation_history[-3:]:  # Last 3 messages
            role = msg.role.upper()
            prompt_parts.append(f"{role}: {msg.content[:200]}")
        prompt_parts.append("")

    # Add session context if available
    if session_context:
        if "last_query" in session_context:
            prompt_parts.append(f"Previous query: {session_context['last_query']}")
        if "active_filters" in session_context:
            prompt_parts.append(f"Active filters: {session_context['active_filters']}")
        prompt_parts.append("")

    prompt_parts.append(f"NEW QUERY: {query_text}")
    prompt_parts.append("")
    prompt_parts.append("Analyze this query and provide your interpretation with confidence score.")

    return "\n".join(prompt_parts)


def load_intent_cache() -> Dict[str, Dict]:
    """Load intent cache from JSONL file.

    Returns:
        Dict mapping query_text → cache entry
    """
    if not INTENT_CACHE_PATH.exists():
        return {}

    cache = {}
    with open(INTENT_CACHE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    cache[entry["query_text"]] = entry
                except (json.JSONDecodeError, KeyError):
                    continue
    return cache


def write_intent_cache_entry(
    query_text: str,
    interpretation: IntentInterpretation,
    model: str
) -> None:
    """Append interpretation to cache file.

    Args:
        query_text: Original query
        interpretation: IntentInterpretation result
        model: Model used
    """
    INTENT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "query_text": query_text,
        "interpretation": {
            "overall_confidence": interpretation.overall_confidence,
            "explanation": interpretation.explanation,
            "uncertainties": interpretation.uncertainties,
            "query_plan": interpretation.query_plan.model_dump(),
            "proceed_to_execution": interpretation.proceed_to_execution
        },
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    with open(INTENT_CACHE_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


async def interpret_query(
    query_text: str,
    session_context: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Message]] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    use_cache: bool = True
) -> IntentInterpretation:
    """Interpret user query and determine confidence.

    This is the main entry point for Phase 1 of the conversational agent.
    It analyzes the user's query and returns an interpretation with:
    - Overall confidence score (0.0-1.0)
    - Natural language explanation
    - List of uncertainties if confidence < 0.85
    - QueryPlan for execution
    - Whether to proceed (confidence >= 0.85)

    Args:
        query_text: User's natural language query
        session_context: Current session context (previous queries, filters)
        conversation_history: Recent messages for context
        api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        model: Model to use (default: gpt-4o)
        use_cache: Whether to use cached interpretations

    Returns:
        IntentInterpretation with confidence score and explanation

    Raises:
        QueryCompilationError: If API call fails or response invalid
    """
    # Check cache first (only for exact query matches without context)
    if use_cache and not conversation_history and not session_context:
        cache = load_intent_cache()
        if query_text in cache:
            try:
                cached = cache[query_text]["interpretation"]
                return IntentInterpretation(
                    overall_confidence=cached["overall_confidence"],
                    explanation=cached["explanation"],
                    uncertainties=cached["uncertainties"],
                    query_plan=QueryPlan(**cached["query_plan"])
                )
            except Exception:
                pass  # Cache entry invalid, proceed to LLM

    # Get API key
    api_key_to_use = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key_to_use:
        raise QueryCompilationError.from_missing_api_key()

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key_to_use)

    # Build prompts
    user_prompt = build_user_prompt(query_text, conversation_history, session_context)

    # Call LLM with structured output
    try:
        resp = client.responses.parse(
            model=model,
            input=[
                {"role": "system", "content": INTENT_AGENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            text_format=IntentInterpretationLLM,
        )

        # Log the LLM call with full details
        log_llm_call(
            call_type="intent_interpretation",
            model=model,
            system_prompt=INTENT_AGENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response=resp,
            extra_metadata={"query_text": query_text},
        )

        llm_output = resp.output_parsed

        # Convert from LLM-specific models to actual QueryPlan
        # Convert filters
        filters = []
        for f in llm_output.query_plan.filters:
            try:
                filters.append(Filter(
                    field=FilterField(f.field),
                    op=FilterOp(f.op),
                    value=f.value,
                    start=f.start,
                    end=f.end,
                    negate=f.negate,
                    confidence=f.confidence,
                    notes=f.notes
                ))
            except ValueError:
                # Skip invalid filter fields/ops
                continue

        # Convert soft_filters
        soft_filters = []
        for f in llm_output.query_plan.soft_filters:
            try:
                soft_filters.append(Filter(
                    field=FilterField(f.field),
                    op=FilterOp(f.op),
                    value=f.value,
                    start=f.start,
                    end=f.end,
                    negate=f.negate,
                    confidence=f.confidence,
                    notes=f.notes
                ))
            except ValueError:
                continue

        # Build QueryPlan
        query_plan = QueryPlan(
            version=llm_output.query_plan.version,
            query_text=llm_output.query_plan.query_text,
            filters=filters,
            soft_filters=soft_filters,
            limit=llm_output.query_plan.limit
        )

        # Build interpretation
        interpretation = IntentInterpretation(
            overall_confidence=llm_output.overall_confidence,
            explanation=llm_output.explanation,
            uncertainties=llm_output.uncertainties,
            query_plan=query_plan
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

    # Cache the result (only if no context was used)
    if use_cache and not conversation_history and not session_context:
        try:
            write_intent_cache_entry(query_text, interpretation, model)
        except Exception:
            pass  # Cache write failure shouldn't block

    return interpretation


def generate_clarification_prompt(interpretation: IntentInterpretation) -> str:
    """Generate a natural language clarification request.

    Called when interpretation.proceed_to_execution is False (confidence < 0.85).
    Creates a helpful message asking the user to clarify their query.

    Args:
        interpretation: IntentInterpretation with low confidence

    Returns:
        Natural language clarification request
    """
    parts = []

    # Start with what we understood
    parts.append(interpretation.explanation)
    parts.append("")

    # Add clarification request
    if interpretation.uncertainties:
        parts.append("To help you better, could you clarify:")
        for uncertainty in interpretation.uncertainties:
            parts.append(f"  - {uncertainty}")
    else:
        # Generic clarification if no specific uncertainties
        parts.append("Could you provide more details about what you're looking for?")
        parts.append("For example:")
        parts.append("  - A specific time period (e.g., '16th century' or '1500-1600')")
        parts.append("  - A place of publication (e.g., 'Venice', 'Paris', or 'Germany')")
        parts.append("  - A subject or topic (e.g., 'astronomy', 'theology')")
        parts.append("  - A language (e.g., 'Latin', 'Hebrew')")

    return "\n".join(parts)


def format_interpretation_for_user(
    interpretation: IntentInterpretation,
    result_count: Optional[int] = None
) -> str:
    """Format interpretation as user-facing message.

    Creates a conversational message explaining results and what was understood.

    Args:
        interpretation: The IntentInterpretation result
        result_count: Number of results found (if query was executed)

    Returns:
        Formatted message for the user
    """
    parts = []

    # Lead with results in a friendly, conversational way
    if result_count is not None:
        if result_count == 0:
            parts.append("I couldn't find any books matching that search.")
            parts.append("")
            parts.append(interpretation.explanation)
        elif result_count == 1:
            parts.append(interpretation.explanation)
            parts.append("")
            parts.append("I found **1 book** matching these criteria.")
        else:
            parts.append(interpretation.explanation)
            parts.append("")
            parts.append(f"I found **{result_count} books** matching these criteria.")
    else:
        # No results yet, just show explanation
        parts.append(interpretation.explanation)

    return "\n".join(parts)
