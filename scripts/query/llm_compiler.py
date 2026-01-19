"""LLM-based Query Compiler - Natural Language → QueryPlan.

Uses OpenAI's Responses API with Pydantic schema enforcement for structured output.
Implements JSONL caching to minimize API calls and cost.
"""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from openai import OpenAI, AuthenticationError, RateLimitError, APITimeoutError, APIError
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from scripts.schemas import QueryPlan, Filter, FilterField, FilterOp
from scripts.query.exceptions import QueryCompilationError
from scripts.utils.llm_logger import log_llm_call


class QueryPlanLLM(BaseModel):
    """QueryPlan model for LLM generation (without debug field).

    This is the model sent to OpenAI's Responses API. The debug field
    is added programmatically after generation, so we exclude it here
    to avoid OpenAI's strict schema validation requirements.
    """
    model_config = ConfigDict(extra='forbid')

    version: str = "1.0"
    query_text: str
    filters: List[Filter] = Field(default_factory=list)
    soft_filters: List[Filter] = Field(default_factory=list)
    limit: Optional[int] = Field(None, gt=0)


# Cache configuration
CACHE_PATH = Path("data/query_plan_cache.jsonl")

# System prompt for QueryPlan generation
SYSTEM_PROMPT = """You are a query parser for a bibliographic rare books database.
Convert natural language queries to structured QueryPlan JSON.

SCHEMA:
- filters: List[Filter] (AND semantics)
  - Filter fields: publisher, imprint_place, country, year, language, title, subject, agent_norm, agent_role
  - Operations: EQUALS, CONTAINS, RANGE, IN
  - RANGE requires start/end (integers)
  - EQUALS/CONTAINS requires value (string)
  - IN requires value (list of strings)

IMPORTANT - COUNTRY vs IMPRINT_PLACE:
- country: Use for COUNTRIES (e.g., "from Germany", "printed in France", "Italian books")
  Maps to MARC 008/15-17 country codes. Use lowercase country name: germany, france, italy, netherlands, england, etc.
- imprint_place: Use for CITIES (e.g., "printed in Venice", "published in London", "from Paris")
  Maps to publication city. Use lowercase city name: venice, london, paris, amsterdam, etc.

NORMALIZATION RULES:
- Publisher/place: lowercase, strip brackets/punctuation, trim
- Language: convert to ISO 639-2 codes (Latin→lat, Hebrew→heb, English→eng, French→fre, German→ger, Italian→ita, Spanish→spa, Greek→gre, Arabic→ara)
- Year: extract explicit years or century ranges (16th century = 1501-1600)
- Agent names: lowercase, preserve spaces
- Titles: lowercase, preserve spaces
- Subjects: Transform to Library of Congress Subject Heading (LCSH) style:
  * Convert adjectives to noun forms: "historical" → "history", "philosophical" → "philosophy", "scientific" → "science"
  * Use proper capitalization: "History" not "history", "Philosophy" not "philosophy"
  * Use standard LCSH subdivisions with dashes: "United States -- History", "World War, 1939-1945"
  * For general topics, prefer broader noun forms over specific adjectives
  * Examples: "biographical works" → "biography", "theological texts" → "theology", "geographical data" → "geography"

OPERATION SELECTION GUIDELINES:
- Title queries: Use CONTAINS by default (partial match) unless user explicitly requests exact match with words like "exact", "exactly", "precisely" or uses quotes around the full title
- Subject queries: Use CONTAINS (keyword search in subject headings)
- Publisher: Use CONTAINS by default (publisher names in records are often verbose, e.g., "Nella Stamparia di Giovanni Battista..."). Use EQUALS only if user explicitly requests exact match.
- Place: Use EQUALS for well-known city names (paris, london, venice). Use CONTAINS if uncertain or for partial names.
- Agent names: Use CONTAINS (partial match on names)

EXAMPLES:
Query: "All books published by Oxford between 1500 and 1599"
Plan: {
  "query_text": "All books published by Oxford between 1500 and 1599",
  "filters": [
    {"field": "publisher", "op": "CONTAINS", "value": "oxford", "notes": "Publisher name (CONTAINS for partial match)"},
    {"field": "year", "op": "RANGE", "start": 1500, "end": 1599, "notes": "Explicit year range"}
  ]
}

Query: "books printed by Aldus in Venice in the 16th century"
Plan: {
  "query_text": "books printed by Aldus in Venice in the 16th century",
  "filters": [
    {"field": "agent_norm", "op": "CONTAINS", "value": "aldus", "notes": "Printer name"},
    {"field": "agent_role", "op": "EQUALS", "value": "printer", "notes": "Role from 'printed by'"},
    {"field": "imprint_place", "op": "EQUALS", "value": "venice", "notes": "Place name"},
    {"field": "year", "op": "RANGE", "start": 1501, "end": 1600, "notes": "16th century"}
  ]
}

Query: "Latin books on astronomy"
Plan: {
  "query_text": "Latin books on astronomy",
  "filters": [
    {"field": "language", "op": "EQUALS", "value": "lat", "notes": "Latin→lat"},
    {"field": "subject", "op": "CONTAINS", "value": "astronomy", "notes": "Subject keyword"}
  ]
}

Query: "books published by Elsevier"
Plan: {
  "query_text": "books published by Elsevier",
  "filters": [
    {"field": "publisher", "op": "CONTAINS", "value": "elsevier", "notes": "Publisher name (CONTAINS for partial match)"}
  ]
}

Query: "Hebrew texts from the 17th century"
Plan: {
  "query_text": "Hebrew texts from the 17th century",
  "filters": [
    {"field": "language", "op": "EQUALS", "value": "heb", "notes": "Hebrew→heb"},
    {"field": "year", "op": "RANGE", "start": 1601, "end": 1700, "notes": "17th century"}
  ]
}

Query: "Does a title The descent of man exist in this collection?"
Plan: {
  "query_text": "Does a title The descent of man exist in this collection?",
  "filters": [
    {"field": "title", "op": "CONTAINS", "value": "the descent of man", "notes": "Use CONTAINS for partial title match - full title may include subtitle"}
  ]
}

Query: "books with 'historia' in the title"
Plan: {
  "query_text": "books with 'historia' in the title",
  "filters": [
    {"field": "title", "op": "CONTAINS", "value": "historia", "notes": "Keyword in title"}
  ]
}

Query: "Historical Books published in London"
Plan: {
  "query_text": "Historical Books published in London",
  "filters": [
    {"field": "imprint_place", "op": "EQUALS", "value": "london", "notes": "Place name"},
    {"field": "subject", "op": "CONTAINS", "value": "History", "notes": "Normalized from 'Historical' (adjective → noun, LCSH style)"}
  ]
}

Query: "philosophical texts in Latin"
Plan: {
  "query_text": "philosophical texts in Latin",
  "filters": [
    {"field": "language", "op": "EQUALS", "value": "lat", "notes": "Latin→lat"},
    {"field": "subject", "op": "CONTAINS", "value": "Philosophy", "notes": "Normalized from 'philosophical' to LCSH noun form"}
  ]
}

Query: "books from Germany"
Plan: {
  "query_text": "books from Germany",
  "filters": [
    {"field": "country", "op": "EQUALS", "value": "germany", "notes": "Country of publication from MARC 008"}
  ]
}

Query: "French books printed in the 16th century"
Plan: {
  "query_text": "French books printed in the 16th century",
  "filters": [
    {"field": "country", "op": "EQUALS", "value": "france", "notes": "Country of publication (French = France)"},
    {"field": "year", "op": "RANGE", "start": 1501, "end": 1600, "notes": "16th century"}
  ]
}

Query: "books printed in Venice"
Plan: {
  "query_text": "books printed in Venice",
  "filters": [
    {"field": "imprint_place", "op": "EQUALS", "value": "venice", "notes": "City name (use imprint_place, not country)"}
  ]
}

Query: "Italian books on theology"
Plan: {
  "query_text": "Italian books on theology",
  "filters": [
    {"field": "country", "op": "EQUALS", "value": "italy", "notes": "Country of publication (Italian = Italy)"},
    {"field": "subject", "op": "CONTAINS", "value": "Theology", "notes": "Subject heading"}
  ]
}

IMPORTANT:
- Always normalize values (lowercase, clean punctuation)
- Include helpful notes for each filter
- If query is ambiguous, extract what you can and add notes about ambiguity
- Empty filters list is OK if no extractable criteria
- For agent queries: "printed by X" → agent_role=printer, "published by X" → use publisher field (not agent)
- For century ranges: 16th century = 1501-1600, 17th century = 1601-1700, etc.
- For title queries: Default to CONTAINS (partial match) unless explicit exact match requested. Rare book titles often have long subtitles that users don't know.
- For subject queries: ALWAYS transform adjectives to LCSH noun forms. Users say "historical books" but MARC subjects use "History". Transform: biographical→Biography, theological→Theology, scientific→Science, etc.
"""


def build_user_prompt(query_text: str) -> str:
    """Build user prompt from query text.

    Args:
        query_text: Natural language query

    Returns:
        Formatted prompt for LLM
    """
    return f"Parse this query into a QueryPlan:\n\n{query_text}"


def call_model(client: OpenAI, model: str, query_text: str) -> QueryPlan:
    """Call OpenAI Responses API with structured output.

    Args:
        client: OpenAI client instance
        model: Model to use (e.g., "gpt-4o")
        query_text: Natural language query

    Returns:
        Parsed QueryPlan from LLM

    Raises:
        Exception: If API call fails
    """
    user_prompt = build_user_prompt(query_text)
    resp = client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        text_format=QueryPlanLLM,
    )

    # Log the LLM call with full details
    log_llm_call(
        call_type="query_compilation",
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response=resp,
        extra_metadata={"query_text": query_text},
    )

    # Convert QueryPlanLLM to QueryPlan (adds debug field)
    llm_plan = resp.output_parsed
    return QueryPlan(
        version=llm_plan.version,
        query_text=llm_plan.query_text,
        filters=llm_plan.filters,
        soft_filters=llm_plan.soft_filters,
        limit=llm_plan.limit,
        debug={}  # Will be populated by caller
    )


def compile_query_with_subject_hints(
    query_text: str,
    subject_hints: List[str],
    original_plan: QueryPlan,
    api_key: Optional[str] = None,
    model: str = "gpt-4o"
) -> QueryPlan:
    """Retry query compilation with actual database subjects as hints.

    Called when initial query with subject filter returned zero results.
    Provides LLM with actual subject headings from database for semantic matching.

    Args:
        query_text: Original natural language query
        subject_hints: Top N subjects from database (e.g., ["History", "Philosophy", ...])
        original_plan: The plan that returned zero results
        api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        model: Model to use (default: gpt-4o)

    Returns:
        New QueryPlan with subject filter mapped to database subjects

    Raises:
        QueryCompilationError: If API fails or response invalid
    """
    # Build enhanced prompt with subject hints
    subject_list = ", ".join(subject_hints[:50])  # Show first 50 for brevity
    more_count = len(subject_hints) - 50 if len(subject_hints) > 50 else 0

    enhanced_prompt = f"""Original query: {query_text}

IMPORTANT CONTEXT:
The previous query attempt with subject filters returned ZERO results.

Here are the actual subject headings available in this database (top subjects by frequency):
{subject_list}{f' ...and {more_count} more' if more_count > 0 else ''}

TASK:
Re-parse the query and map the user's subject term to the CLOSEST SEMANTIC MATCH from the list above.
- Use CONTAINS operation for flexibility (partial matching)
- If the user's term doesn't match exactly, find the closest related subject
- For example: "historical" → "History", "philosophical" → "Philosophy"
- Preserve all other filters from the original query unchanged

Original filters for reference: {[f.model_dump() for f in original_plan.filters]}
"""

    # Get API key
    api_key_to_use = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key_to_use:
        raise QueryCompilationError.from_missing_api_key()

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key_to_use)

    # Call LLM with enhanced prompt
    try:
        plan = call_model(client, model, enhanced_prompt)
    except (AuthenticationError, RateLimitError, APITimeoutError, APIError) as e:
        raise QueryCompilationError.from_api_error(e)
    except Exception as e:
        raise QueryCompilationError.from_invalid_response(e)

    # Add debug info for retry
    plan.debug.update({
        "parser": "llm",
        "model": model,
        "filters_count": len(plan.filters),
        "cache_hit": False,
        "retry_attempt": True,
        "retry_reason": "subject_filter_zero_results",
        "subject_hints_provided": len(subject_hints)
    })

    return plan


def load_cache() -> dict[str, dict]:
    """Load cache from JSONL file.

    Returns:
        Dict mapping query_text → cache entry dict
    """
    if not CACHE_PATH.exists():
        return {}

    cache = {}
    with open(CACHE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    entry = json.loads(line)
                    cache[entry["query_text"]] = entry
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed entries
                    continue
    return cache


def write_cache_entry(query_text: str, plan: QueryPlan, model: str) -> None:
    """Append cache entry to JSONL file.

    Args:
        query_text: Query that was parsed
        plan: Generated QueryPlan
        model: Model used for generation
    """
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "query_text": query_text,
        "plan": plan.model_dump(),
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    with open(CACHE_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def compile_query_llm(
    query_text: str,
    limit: Optional[int] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-4o"
) -> QueryPlan:
    """Compile natural language query to QueryPlan using LLM.

    Args:
        query_text: Natural language query
        limit: Optional result limit
        api_key: OpenAI API key (or use OPENAI_API_KEY env var)
        model: Model to use (default: gpt-4o)

    Returns:
        Validated QueryPlan (from cache or LLM)

    Raises:
        QueryCompilationError: If API key is missing, API call fails,
            or response is invalid. Error message includes specific
            guidance for troubleshooting.
    """
    # Check cache first
    cache = load_cache()
    if query_text in cache:
        try:
            cached_plan = QueryPlan(**cache[query_text]["plan"])
            # Update limit if provided
            if limit:
                cached_plan.limit = limit
            # Update debug to indicate cache hit
            cached_plan.debug["cache_hit"] = True
            return cached_plan
        except Exception:
            # Cache entry invalid, fall through to LLM
            pass

    # Get API key
    api_key_to_use = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key_to_use:
        raise QueryCompilationError.from_missing_api_key()

    # Initialize OpenAI client
    client = OpenAI(api_key=api_key_to_use)

    # Call LLM with proper error handling
    try:
        plan = call_model(client, model, query_text)
    except AuthenticationError as e:
        # Invalid or expired API key
        raise QueryCompilationError.from_api_error(e)
    except RateLimitError as e:
        # Rate limiting
        raise QueryCompilationError.from_api_error(e)
    except APITimeoutError as e:
        # Timeout
        raise QueryCompilationError.from_api_error(e)
    except APIError as e:
        # Other OpenAI API errors
        raise QueryCompilationError.from_api_error(e)
    except Exception as e:
        # Unexpected errors (e.g., Pydantic validation failure, JSON parsing)
        raise QueryCompilationError.from_invalid_response(e)

    # Apply limit if provided
    if limit:
        plan.limit = limit

    # Add debug info
    plan.debug.update({
        "parser": "llm",
        "model": model,
        "filters_count": len(plan.filters),
        "cache_hit": False
    })

    # Write to cache
    try:
        write_cache_entry(query_text, plan, model)
    except Exception:
        # Cache write failure shouldn't block query execution
        pass

    return plan
