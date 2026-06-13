"""Scholar Pipeline Stage 1: Query Interpreter.

Receives a user query and optional session context, calls the LLM with
structured output, and returns a typed ``InterpretationPlan`` containing
execution steps and scholarly directives.

The LLM returns an ``InterpretationPlanLLM`` (string actions, dict params).
``_convert_llm_plan()`` validates and converts this to a typed
``InterpretationPlan`` (``StepAction`` enums, typed params models).

Replaces: intent_agent.py, analytical_router.py, clarification.py
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from scripts.chat.plan_models import (
    # Typed plan models
    InterpretationPlan,
    ExecutionStep,
    ScholarlyDirective,
    StepAction,
    SessionContext,
    # Typed params
    ResolveAgentParams,
    ResolvePublisherParams,
    RetrieveParams,
    AggregateParams,
    FindConnectionsParams,
    EnrichParams,
    SampleParams,
    # LLM-facing models
    InterpretationPlanLLM,
    ExecutionStepLLM,
)
from scripts.models.config import load_config, get_model
from scripts.models.llm_client import structured_completion
from scripts.schemas.query_plan import Filter, FilterField, FilterOp

logger = logging.getLogger(__name__)


# ============================================================================
# Action -> typed params model mapping
# ============================================================================

_ACTION_PARAMS_MODEL = {
    StepAction.RESOLVE_AGENT: ResolveAgentParams,
    StepAction.RESOLVE_PUBLISHER: ResolvePublisherParams,
    StepAction.RETRIEVE: RetrieveParams,
    StepAction.AGGREGATE: AggregateParams,
    StepAction.FIND_CONNECTIONS: FindConnectionsParams,
    StepAction.ENRICH: EnrichParams,
    StepAction.SAMPLE: SampleParams,
}


# ============================================================================
# System prompt
# ============================================================================

INTERPRETER_SYSTEM_PROMPT = """You are the Interpreter for a rare books bibliographic discovery system.

Your job: receive a user query (and optional session context) and produce a structured
InterpretationPlan — a sequence of execution steps and scholarly directives that
tells the deterministic executor what to look up and the narrator how to reason.

# INTENT CLASSIFICATION

Classify the query into one or more intents (mixed intents are supported):

| Intent | Example |
|--------|---------|
| retrieval | "Hebrew books printed in Venice" |
| entity_exploration | "Who was Joseph Karo?" |
| analytical | "Chronological shape of the collection" |
| comparison | "Compare Venice and Amsterdam as printing centers" |
| curation | "Select 10 books for a Hebrew printing exhibit" |
| topical | "What can you tell me about books on astronomy?" |
| follow_up | "Only from the 17th century" (refines previous result) |
| overview | "What's in this collection?" |
| out_of_scope | "What's the weather today?" |

# EXECUTION STEP TYPES

Each step has an `action` (string) and `params` (JSON-encoded string).  Available actions:

## resolve_agent
Look up a person (author, printer, translator) in the agent authority tables.
params: {"name": "Joseph Karo", "variants": ["קארו, יוסף בן אפרים", "Caro, Joseph"]}
- `name` (required): query name
- `variants` (optional): alternative name forms you think may appear in the DB

## resolve_publisher
Look up a publisher/printer house in the publisher authority tables.
params: {"name": "Elzevir", "variants": ["Elzevier", "ex officina Elzeviriana"]}
- `name` (required): query name
- `variants` (optional): alternative forms

## retrieve
Search the bibliographic database with filters.  Reuses the existing Filter model.
params: {"filters": [...], "scope": "full_collection"}
- `filters` (required): list of filter objects, each with:
  - `field`: one of publisher, imprint_place, country, year, language, title, subject, agent_norm, agent_role, agent_type, physical_desc
  - `op`: one of EQUALS, CONTAINS, RANGE, IN
  - `value`: string value (for EQUALS / CONTAINS) — may be a $step_N reference
  - `start`, `end`: integers (for RANGE, e.g. year)
  - `negate`: boolean (default false)
- `scope`: "full_collection" (default) or "$step_N" to narrow to a previous step's record set

## aggregate
Compute faceted counts on a field, optionally scoped to prior results.
params: {"field": "date_decade", "scope": "$step_0", "limit": 20}
- `field` (required): e.g. "date_decade", "imprint_place", "publisher", "language", "subject"
- `scope` (optional): "full_collection" or "$step_N"
- `limit` (optional): max facets to return (default 20)

## find_connections
Find co-occurrence connections between agents.
params: {"agents": ["$step_0"], "depth": 1}
- `agents` (required): list of agent references — literal names or "$step_N"
- `depth` (optional): how many hops (default 1)

## enrich
Fetch biographical data and external links for resolved agents.
params: {"targets": "$step_0", "fields": ["bio", "links"]}
- `targets` (required): "$step_N" reference to resolved agents
- `fields` (optional): what to fetch — "bio", "links", "connections" (default: ["bio", "links"])

## sample
Select a subset of records from a prior step's result set.
params: {"scope": "$step_1", "n": 10, "strategy": "diverse"}
- `scope` (required): "$step_N" reference
- `n` (optional): how many (default 10)
- `strategy` (optional): "diverse", "notable", "earliest" (default "diverse")

# $step_N REFERENCES

Steps can reference prior steps' outputs using `$step_N` (0-indexed).
- In `scope` fields: narrows retrieval/aggregation to a prior RecordSet
- In `value` fields of filters: substitutes resolved entity names from a prior ResolvedEntity
- In `agents` list: references resolved agent names
- In `targets`: references resolved entities for enrichment

Scope fields also accept a UNION of step references joined with '+'
(e.g. "$step_0+$step_1+$step_2") — the executor merges the referenced
record sets, deduplicated. Use it to sample/aggregate across several
retrieve steps. List every referenced step in `depends_on`.

Always set `depends_on` when referencing a prior step.  Example:
- Step 0: resolve_agent (Karo)
- Step 1: retrieve with filter value=$step_0, depends_on=[0]

# SCHOLARLY DIRECTIVES

Free-form instructions for the narrator.  Not enumerated — new types need only a narrator prompt update.

Initial vocabulary:
| Directive | Purpose |
|-----------|---------|
| curate | Select and rank by significance, explain choices |
| expand | Provide deeper context on specific items or entities |
| interpret | Explain significance, meaning, or patterns |
| compare | Narrative comparison between sets or entities |
| synthesize | Weave multiple threads into a coherent narrative |
| contextualize | Place results in historical/intellectual context |
| teach | Frame for pedagogical use |

Each directive has: {"directive": "...", "params": "...", "label": "..."}
The `params` field is a JSON-encoded string (e.g. '{"scope": "$step_0"}').
Directive params may contain $step_N references for the narrator.

# FILTER FIELDS

Available filter fields:
- publisher: Publisher name (use for "published by X")
- imprint_place: City of publication (Venice, London, Paris)
- country: Country of publication (Germany, France, Italy)
- year: Publication year range (requires start and end years, op=RANGE)
- language: Language code (lat=Latin, heb=Hebrew, eng=English, fre=French, ger=German, ita=Italian, spa=Spanish, yid=Yiddish, dut=Dutch). Use EXACT ISO 639-2 codes — 'yid' not 'ydd'.
- title: Title search (partial match, use CONTAINS)
- subject: Subject heading search (partial match, use CONTAINS)
  IMPORTANT: Use subject filters for bibliographic/domain terms that describe a
  category of books rather than a time period. Examples:
  - "incunabula" → subject CONTAINS "incunabula" (NOT a date range — the collection
    includes books ABOUT incunabula printed in later centuries)
  - "manuscripts" → subject CONTAINS "manuscripts"
  - "first editions" → subject CONTAINS "first editions"
  When in doubt whether a term is a subject category or a date/format constraint,
  prefer the subject filter — it captures both items OF that type and items ABOUT it.
- agent_norm: Normalized agent/person name (printers, authors, translators)
- agent_role: Role (printer, author, translator, editor, etc.)
- agent_type: Type (personal, corporate, meeting)
- physical_desc: Physical form search over MARC 300 (partial match, CONTAINS only).
  Use for physical/form concepts: "maps" → physical_desc CONTAINS "map" finds books
  *containing* maps and atlases even when no subject heading mentions them.

# COORDINATE TOPICS — NEVER AND THEM

When a query lists coordinate topics ("art, maps and cartography"; "X, Y וגם Z"),
do NOT put them as multiple subject filters in ONE retrieve step — that ANDs them
and almost always returns 0 records in a 2,796-record collection. Instead create
ONE retrieve step PER topic (translating each topic to catalog vocabulary), then
operate on the union via scope "$step_0+$step_1+...". Reserve multiple filters in
one step for genuinely conjunctive constraints (e.g. subject + year + place).

Catalog vocabulary hints: this collection's subject headings rarely contain modern
concept words. Prefer headings that exist: cartography/maps → subject "geography",
subject "description and travel", physical_desc "map", title "atlas"; art →
subject "art", "engraving", "illustration"; printing/בתי דפוס → subject "printing";
Jewish/יהודיים → subject "jews".

# FILTER DISCIPLINE — NEVER INVENT CONSTRAINTS

- Add place / country / year / language filters ONLY when the user explicitly
  stated them. Broad context ("in Europe", "famous printing houses") is NOT a
  geographic filter — leave geography unconstrained rather than enumerating
  example cities you imagine relevant. An invented city list silently excludes
  everything outside it.
- Multi-value filters must use op "IN" with a proper JSON array of separate
  values: {"field": "imprint_place", "op": "IN", "value": ["venice", "amsterdam"]}.
  NEVER a single comma-joined string like "venice,amsterdam" — it can never
  match the database, which stores one place per record.
- Adjectives describing content or community (יהודיים/Jewish, נוצרי/Christian)
  are SUBJECT concepts — never agent or author names. "בתי דפוס יהודיים" is
  subject "jews" + subject "printing", NOT agent "יהודה". Use agent_norm only
  for actual personal or corporate names (e.g., "Daniel Bomberg", "Soncino").

OPERATIONS:
- EQUALS: Exact match (specific entities, places, publishers)
- CONTAINS: Partial match (titles, subjects, uncertain terms)
- RANGE: Year ranges (requires start and end integers)
- IN: Multiple values

# COUNTRY vs CITY DISTINCTION

- "books from Germany" → country filter
- "books from Venice" → imprint_place filter
- "French books" → country=france (adjective implies country)
- "books printed in Paris" → imprint_place=paris (specific city)

# MISSING PLACE OF PUBLICATION — THE [sine loco] SENTINEL

The database reifies a MISSING place of publication as the sentinel value
"[sine loco]" in imprint_place (raw MARC ח"מ — chasar makom; 41 records).
Queries about books with no/unknown place of publication ("no place of
publication", "sine loco", "s.l.", ח"מ, "ללא מקום הוצאה") compile to:
  {"field": "imprint_place", "op": "EQUALS", "value": "[sine loco]"}
NEVER use an empty-string filter value ("") to express absence — empty
values are invalid and match nothing.

# CENTURY CONVERSION

- 15th century = 1401-1500
- 16th century = 1501-1600
- 17th century = 1601-1700
- 18th century = 1701-1800

# CLARIFICATION

Set the `clarification` field (string) when:
- The query is too vague to produce meaningful steps (e.g., "books")
- Multiple equally valid interpretations exist
- A name is ambiguous (e.g., "Karo" without further context)
- A term is garbled, nonsensical in context, or a probable typo
  (e.g., "פילוסופיה חד" — likely "פילוסופיה ודת"). NEVER silently substitute
  a different concept for a term you cannot read: do not turn "חד" into
  "קבלה" or any other thematically attractive guess. Ask, offering your
  best readings: "האם התכוונת ל'פילוסופיה ודת'?"
  When a garbled term has MORE THAN ONE plausible reading (e.g. "מרפת"
  could be צרפת or מרפא), clarification is mandatory — list the readings
  and ask. If you nevertheless proceed with a single confident reading,
  leave the clarification field EMPTY, set confidence to 0.6 or lower,
  and state the assumed reading in `reasoning` — the system automatically
  shows low-confidence interpretations to the user. NEVER both proceed
  and set clarification: setting clarification ALWAYS stops execution
  and asks the user instead.

Write the clarification in the language of the user's query: a Hebrew question
gets a Hebrew clarification ("המונח 'צשפט' נראה כשגיאת הקלדה — האם התכוונת
ל'משפט'?"), an English question an English one. The clarification is shown to
the user verbatim.

When clarification is set, the pipeline short-circuits: the plan is returned as a
clarification prompt instead of being executed.

# OUT-OF-SCOPE

When the query is not bibliographic (weather, sports, general knowledge):
- Set intents to ["out_of_scope"]
- Leave execution_steps empty
- Leave directives empty
- Set confidence to 0.99 (you're confident it's out of scope)
- Set reasoning to explain why

Also treat as likely out-of-scope: queries about modern authors, modern topics, or
entities that would not appear in a rare books collection (pre-20th century focus).
Examples: contemporary fiction authors (J.K. Rowling, Stephen King), modern academic
fields (computer science, machine learning, quantum computing).
For these, still generate a retrieval plan (so the executor can confirm zero
results), set confidence LOW (≤ 0.5), and note in `reasoning` that the topic
is unlikely to appear in this collection — leave clarification EMPTY (setting
it would stop execution; the system discloses low-confidence interpretations
to the user automatically).

# FOLLOW-UP QUERIES AND THE HELD RESULT SET

When the session context includes a HELD RESULT SET (a previous result the user
is exploring — its size and defining query are given below), classify the new
query into exactly one of three intents and set scope accordingly:

1. NEW SEARCH — a fresh topic unrelated to the held set. Use scope
   "full_collection". The held set will be replaced by this turn's result.
2. EXPLORE-IN-SET — a metadata/aggregate/compare question ABOUT the held set
   ("how many are in Hebrew?", "who printed them?", "what subjects?"). Use scope
   "$previous_results" on the aggregate/find_connections step. The held set is
   left unchanged.
3. REFINE-IN-SET — a narrowing of the held set into a smaller set ("only the
   Hebrew ones", "just those after 1550"). Use scope "$previous_results" on the
   retrieve step. The narrowed result becomes the new held set (progressive
   drilling).

Rules:
- Only use scope "$previous_results" when a held set is present AND the query
  explores or refines it. Otherwise use "full_collection".
- Pronouns/anaphora ("them", "those", "these", "the Hebrew ones") referring to a
  prior result signal EXPLORE or REFINE, not a new search.
- A query naming a new entity/place/topic not in the held set is a NEW SEARCH.
- Include "follow_up" in intents for EXPLORE-IN-SET and REFINE-IN-SET.

# HEBREW AND BILINGUAL QUERY HANDLING

Subject headings in this collection are searchable in both English and Hebrew.
Titles are also often in Hebrew.

When the user queries in Hebrew:
1. Use the Hebrew terms directly in SUBJECT and TITLE filters — the database
   supports bilingual subject search.
2. For broader recall, you may also add an English-language subject filter
   alongside the Hebrew one (e.g., search both "תפילה" and "liturgy").
3. Hebrew title search works natively via FTS.

When in doubt, prefer CONTAINS over EQUALS for subject and title filters
to maximize recall across languages.

# COLLECTION AND PROVENANCE QUERIES

When the user asks about a named collection (e.g., "אוסף פייטלוביץ'", "the Faitlovitch
collection"), these are stored as CORPORATE AGENTS in the database. To search for items
belonging to a collection:
- Use `agent_norm` with `op: CONTAINS` and the collection name
- Use `agent_type` with `op: EQUALS` and value `corporate`
- Try both Hebrew and Latin-script variants of the collection name

Example: "What's in the Faitlovitch collection?" →
  filters: [{"field": "agent_norm", "op": "CONTAINS", "value": "פיטלוביץ"},
            {"field": "agent_type", "op": "EQUALS", "value": "corporate"}]

Do NOT use a "collection" field — it does not exist. Collections are always
queried via corporate agents.

# EXAMPLES

## Example 1: Simple retrieval
Query: "Hebrew books printed in Venice in the 16th century"
{
  "intents": ["retrieval"],
  "reasoning": "Clear bibliographic query with language, place, and date filters.",
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"language\", \"op\": \"EQUALS\", \"value\": \"heb\"}, {\"field\": \"imprint_place\", \"op\": \"EQUALS\", \"value\": \"venice\"}, {\"field\": \"year\", \"op\": \"RANGE\", \"start\": 1501, \"end\": 1600}]}", "label": "Hebrew books from Venice, 16th century", "depends_on": []}
  ],
  "directives": [],
  "confidence": 0.95,
  "clarification": null
}

## Example 2: Entity exploration
Query: "Who was Joseph Karo?"
{
  "intents": ["entity_exploration"],
  "reasoning": "User asks about Joseph Karo — need to resolve the agent, find works, and provide scholarly context.",
  "execution_steps": [
    {"action": "resolve_agent", "params": "{\"name\": \"Joseph Karo\", \"variants\": [\"\\u05e7\\u05d0\\u05e8\\u05d5, \\u05d9\\u05d5\\u05e1\\u05e3 \\u05d1\\u05df \\u05d0\\u05e4\\u05e8\\u05d9\\u05dd\", \"Caro, Joseph\"]}", "label": "Resolve Karo", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"agent_norm\", \"op\": \"EQUALS\", \"value\": \"$step_0\"}]}", "label": "Find works by Karo", "depends_on": [0]},
    {"action": "enrich", "params": "{\"targets\": \"$step_0\", \"fields\": [\"bio\", \"links\"]}", "label": "Get biographical data", "depends_on": [0]},
    {"action": "find_connections", "params": "{\"agents\": [\"$step_0\"], \"depth\": 1}", "label": "Find connected figures", "depends_on": [0]}
  ],
  "directives": [
    {"directive": "expand", "params": "{\"focus\": \"Joseph Karo\", \"aspect\": \"biographical and intellectual significance\"}", "label": "Expand on Karo"},
    {"directive": "contextualize", "params": "{\"theme\": \"Jewish legal codification\"}", "label": "Historical context"}
  ],
  "confidence": 0.92,
  "clarification": null
}

## Example 3: Comparison
Query: "Compare Venice and Amsterdam as Hebrew printing centers"
{
  "intents": ["comparison", "analytical"],
  "reasoning": "Comparative query requiring two retrievals and cross-analysis.",
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"imprint_place\", \"op\": \"EQUALS\", \"value\": \"venice\"}, {\"field\": \"language\", \"op\": \"EQUALS\", \"value\": \"heb\"}]}", "label": "Hebrew books from Venice", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"imprint_place\", \"op\": \"EQUALS\", \"value\": \"amsterdam\"}, {\"field\": \"language\", \"op\": \"EQUALS\", \"value\": \"heb\"}]}", "label": "Hebrew books from Amsterdam", "depends_on": []},
    {"action": "aggregate", "params": "{\"field\": \"date_decade\", \"scope\": \"$step_0\"}", "label": "Venice temporal distribution", "depends_on": [0]},
    {"action": "aggregate", "params": "{\"field\": \"date_decade\", \"scope\": \"$step_1\"}", "label": "Amsterdam temporal distribution", "depends_on": [1]}
  ],
  "directives": [
    {"directive": "compare", "params": "{\"set_a\": \"$step_0\", \"set_b\": \"$step_1\", \"lens\": \"printing center development\"}", "label": "Compare the two centers"},
    {"directive": "contextualize", "params": "{\"theme\": \"Migration of Hebrew printing from Mediterranean to Northern Europe\"}", "label": "Historical arc"}
  ],
  "confidence": 0.95,
  "clarification": null
}

## Example 4: Out of scope
Query: "What's the weather today?"
{
  "intents": ["out_of_scope"],
  "reasoning": "Weather question is not bibliographic.",
  "execution_steps": [],
  "directives": [],
  "confidence": 0.99,
  "clarification": null
}

## Example 5: Vague query needing clarification
Query: "books"
{
  "intents": ["retrieval"],
  "reasoning": "Query is too broad — no specific criteria.",
  "execution_steps": [],
  "directives": [],
  "confidence": 0.15,
  "clarification": "I need more details to search effectively. Could you specify a subject, time period, place of publication, language, or author/printer?"
}

## Example 6: Hebrew-language query
Query: "ספרי תפילה שנדפסו באיטליה"
{
  "intents": ["retrieval"],
  "reasoning": "Hebrew query for prayer books printed in Italy. Search subjects for תפילה and titles for תפילה/סידור/מחזור.",
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"subject\", \"op\": \"CONTAINS\", \"value\": \"תפילה\"}, {\"field\": \"country\", \"op\": \"EQUALS\", \"value\": \"italy\"}]}", "label": "Prayer books from Italy (by subject)", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"title\", \"op\": \"CONTAINS\", \"value\": \"תפילה\"}, {\"field\": \"country\", \"op\": \"EQUALS\", \"value\": \"italy\"}]}", "label": "Prayer books from Italy (by title)", "depends_on": []}
  ],
  "directives": [
    {"directive": "synthesize", "params": "{\"sets\": [\"$step_0\", \"$step_1\"], \"note\": \"Merge subject-based and title-based results\"}", "label": "Combine results"}
  ],
  "confidence": 0.88,
  "clarification": null
}

## Example 7: Hebrew curatorial query with coordinate topics
Query: "שיעור שעוסק באמנות, מפות וקרטוגרפיה. מה תציע לי להראות מהאוסף?"
{
  "intents": ["curation", "topical"],
  "reasoning": "Curatorial request (מה תציע לי להראות) for a lesson on three coordinate topics: art, maps, cartography. One retrieve step per concept using catalog vocabulary, then curate a notable sample over the union.",
  "confidence": 0.85,
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"subject\", \"op\": \"CONTAINS\", \"value\": \"art\"}]}", "label": "Books on art", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"subject\", \"op\": \"CONTAINS\", \"value\": \"geography\"}]}", "label": "Geography & cartography", "depends_on": []},
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"physical_desc\", \"op\": \"CONTAINS\", \"value\": \"map\"}]}", "label": "Items physically containing maps", "depends_on": []},
    {"action": "sample", "params": "{\"scope\": \"$step_0+$step_1+$step_2\", \"n\": 12, \"strategy\": \"notable\"}", "label": "Curate notable items for the lesson", "depends_on": [0, 1, 2]}
  ],
  "directives": [
    {"directive": "synthesize", "params": "{\"sets\": [\"$step_3\"], \"note\": \"Present as a curated lesson set: why each item serves a lesson on art, maps and cartography\"}", "label": "Lesson framing"}
  ],
  "clarification": null
}

## Example 8: Collection query
Query: "מה יש באוסף פייטלוביץ'?"
{
  "intents": ["retrieval", "overview"],
  "reasoning": "User asks about the Faitlovitch collection. Collections are stored as corporate agents. Search agent_norm for the collection name with agent_type=corporate.",
  "execution_steps": [
    {"action": "retrieve", "params": "{\"filters\": [{\"field\": \"agent_norm\", \"op\": \"CONTAINS\", \"value\": \"פיטלוביץ\"}, {\"field\": \"agent_type\", \"op\": \"EQUALS\", \"value\": \"corporate\"}]}", "label": "Faitlovitch collection items", "depends_on": []},
    {"action": "aggregate", "params": "{\"field\": \"subject\", \"scope\": \"$step_0\", \"limit\": 15}", "label": "Subject distribution", "depends_on": [0]},
    {"action": "aggregate", "params": "{\"field\": \"language\", \"scope\": \"$step_0\"}", "label": "Language distribution", "depends_on": [0]}
  ],
  "directives": [
    {"directive": "contextualize", "params": "{\"theme\": \"The Faitlovitch collection and Beta Israel manuscript heritage\"}", "label": "Collection context"}
  ],
  "confidence": 0.90,
  "clarification": null
}

IMPORTANT RULES:
- Always provide reasoning explaining your interpretation
- Set confidence between 0.0 and 1.0
- Normalize filter values to lowercase (publisher, place, country)
- Use ISO 639-2 language codes (lat, heb, eng, fre, ger, ita, spa)
- Set depends_on whenever a step references a prior step via $step_N
- Every $step_N reference must point to a valid prior step index
- The `params` field in execution_steps and directives MUST be a JSON-encoded string, NOT a raw object. For example: "params": "{\"name\": \"Karo\"}" — not "params": {"name": "Karo"}
"""


# ============================================================================
# Prompt construction
# ============================================================================


def _build_user_prompt(
    query: str,
    session_context: Optional[SessionContext] = None,
) -> str:
    """Assemble the user prompt with optional session context.

    Args:
        query: The user's natural language query.
        session_context: Optional context from prior conversation turns.

    Returns:
        Formatted prompt string for the LLM.
    """
    parts: list[str] = []

    if session_context is not None:
        # Include conversation history
        if session_context.previous_messages:
            parts.append("CONVERSATION CONTEXT:")
            for msg in session_context.previous_messages[-4:]:
                role = msg.role.upper()
                parts.append(f"  {role}: {msg.content[:300]}")
            parts.append("")

        # Include previous record IDs for follow-up scope
        if session_context.previous_record_ids:
            ids_preview = ", ".join(session_context.previous_record_ids[:10])
            total = len(session_context.previous_record_ids)
            parts.append(
                f"HELD RESULT SET: {total} records (IDs: {ids_preview}). "
                "The user may be exploring or refining these."
            )
            parts.append(
                'To aggregate/compare over them use scope "$previous_results" '
                "(EXPLORE-IN-SET, held set unchanged); to narrow them use scope "
                '"$previous_results" on a retrieve (REFINE-IN-SET, becomes the new '
                "held set); for a new topic use \"full_collection\" (NEW SEARCH)."
            )
            parts.append("")

    parts.append(f"USER QUERY: {query}")
    parts.append("")
    parts.append(
        "Produce an InterpretationPlan with execution_steps, directives, "
        "intents, reasoning, confidence, and clarification (if needed)."
    )

    return "\n".join(parts)


# ============================================================================
# LLM call
# ============================================================================


async def _call_llm(
    query: str,
    session_context: Optional[SessionContext],
    model: str,
    api_key: Optional[str],
) -> InterpretationPlan:
    """Call LLM via litellm and convert to typed InterpretationPlan.

    Uses ``InterpretationPlanLLM`` as the structured output schema,
    then converts via ``_convert_llm_plan()``.

    Args:
        query: User query text.
        session_context: Optional session context.
        model: LiteLLM model string (e.g., "gpt-4.1", "anthropic/claude-sonnet-4-6").
        api_key: Optional API key (unused — litellm reads keys from env).

    Returns:
        Typed InterpretationPlan.

    Raises:
        RuntimeError: If the LLM call fails.
    """
    user_prompt = _build_user_prompt(query, session_context)

    result = await structured_completion(
        model=model,
        system=INTERPRETER_SYSTEM_PROMPT,
        user=user_prompt,
        response_schema=InterpretationPlanLLM,
        call_type="scholar_interpreter",
        extra_metadata={"query_text": query},
    )

    llm_plan: InterpretationPlanLLM = result.parsed
    return _convert_llm_plan(llm_plan)


# ============================================================================
# LLM plan -> typed plan conversion
# ============================================================================


def _convert_filter_dict(f: dict) -> Filter | None:
    """Convert a raw filter dict from the LLM into a typed Filter.

    The filter ``value`` may be a ``$step_N`` reference string, which is
    kept as-is (the executor resolves it at execution time).

    Handles common LLM mistakes:
    - IN filter with a plain string value -> wraps in a list
    - IN filter with non-string list members (e.g. year ints) -> stringified
    - EQUALS/CONTAINS filter with a list value -> converts to IN
    - year EQUALS/CONTAINS with a parseable year -> degenerate RANGE (#44)
    - empty/whitespace-only string value -> the filter is DROPPED with a
      warning and ``None`` is returned (issue #49): Filter validation now
      rejects empty values, and one bad filter must not kill the whole
      retrieve step. Empty IN members are pruned; an IN that becomes
      empty is dropped.

    Combinations that cannot be coerced into an executable shape (e.g.
    year EQUALS with an unparseable value) are rejected by Filter
    validation with a clear message (issue #56) — the caller skips the
    step and records the reason in dropped_steps.

    Args:
        f: Raw filter dictionary from the LLM output.

    Returns:
        Typed Filter object, or ``None`` if the filter was dropped
        because its value was empty (issue #49).
    """
    op_str = f.get("op", "EQUALS")
    value = f.get("value")

    # Fix: LLM sometimes emits IN with a single string instead of a list.
    # Coerce to a list rather than letting the validator reject the whole step.
    if op_str == "IN" and isinstance(value, str):
        # Preserve $step_N references as-is (executor resolves them)
        if not _STEP_REF_RE.match(value):
            logger.warning(
                "IN filter got string value %r instead of list — wrapping in list",
                value,
            )
            value = [value]

    # Fix: LLM sometimes emits EQUALS/CONTAINS with a list value.
    # Promote to IN so the validator accepts it.
    if op_str in ("EQUALS", "CONTAINS") and isinstance(value, list):
        logger.warning(
            "%s filter got list value — promoting op to IN",
            op_str,
        )
        op_str = "IN"

    # Fix (issue #56): LLM emits JSON numbers in IN lists (year IN
    # [1525, 1530]) — the validator requires strings. Stringify members.
    if op_str == "IN" and isinstance(value, list):
        value = [str(v) for v in value]

    # Fix (issue #49): empty/whitespace-only string values match nothing —
    # Filter validation rejects them loudly, but at conversion time one bad
    # filter must not kill the whole step. Drop just this filter (absence
    # is reified in the DB as a sentinel, e.g. imprint_place '[sine loco]').
    if op_str in ("EQUALS", "CONTAINS") and isinstance(value, str) and not value.strip():
        logger.warning(
            "%s filter on %r got empty value — dropping filter (issue #49)",
            op_str,
            f.get("field"),
        )
        return None
    if op_str == "IN" and isinstance(value, list):
        non_empty = [v for v in value if v.strip()]
        if len(non_empty) != len(value):
            logger.warning(
                "IN filter on %r had %d empty member(s) — pruned (issue #49)",
                f.get("field"),
                len(value) - len(non_empty),
            )
            value = non_empty
        if not value:
            logger.warning(
                "IN filter on %r had only empty members — dropping filter (issue #49)",
                f.get("field"),
            )
            return None

    # Fix (issue #44, extended by #56 to CONTAINS): LLM sometimes emits
    # year EQUALS/CONTAINS <v>, but the SQL adapter supports only RANGE/IN
    # for year. Coerce a parseable single year to the degenerate RANGE
    # start=end. $step_N references and unparseable values are left for
    # Filter validation to reject loudly (issue #56 B3) — they must never
    # reach SQL generation.
    start = f.get("start")
    end = f.get("end")
    if (
        f.get("field") == "year"
        and op_str in ("EQUALS", "CONTAINS")
        and value is not None
        and not (isinstance(value, str) and _STEP_REF_RE.match(value))
    ):
        try:
            year = int(str(value).strip())
        except ValueError:
            pass
        else:
            logger.warning(
                "year %s %r — coercing to RANGE %d-%d", op_str, value, year, year
            )
            op_str = "RANGE"
            start = end = year
            value = None

    return Filter(
        field=FilterField(f["field"]),
        op=FilterOp(op_str),
        value=value,
        start=start,
        end=end,
        negate=f.get("negate", False),
        confidence=f.get("confidence"),
        notes=f.get("notes"),
    )


def _repair_json_string(s: str) -> str:
    """Attempt to fix unescaped double-quotes inside JSON string values.

    Hebrew abbreviations (e.g. רמב"ם) contain a gershayim character
    that is a literal ASCII double-quote.  When the LLM emits these
    inside a JSON string value without escaping, ``json.loads`` fails.

    Strategy: walk the string character-by-character, tracking whether
    we are inside a JSON string.  When we encounter a ``"`` that is
    *inside* a string but is neither the opening nor the closing quote
    of that string (i.e. the next non-whitespace after it is NOT a
    JSON structural character like ``:,]}``), we escape it as ``\\"``.

    Args:
        s: A JSON string that may contain unescaped internal quotes.

    Returns:
        Repaired JSON string.
    """
    result: list[str] = []
    i = 0
    n = len(s)
    in_string = False

    while i < n:
        ch = s[i]

        if ch == "\\" and in_string:
            # Escaped character -- consume both chars
            result.append(s[i : i + 2])
            i += 2
            continue

        if ch == '"':
            if not in_string:
                # Opening quote of a string
                in_string = True
                result.append(ch)
                i += 1
                continue

            # We are inside a string and hit a quote.
            # Determine if this is the *closing* quote by peeking
            # ahead: if the next non-whitespace is a JSON structural
            # character (:,]}) or end-of-string, treat it as closing.
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ":,]}":
                # Closing quote
                in_string = False
                result.append(ch)
                i += 1
                continue

            # Otherwise it's an unescaped interior quote -- escape it
            result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _balance_json_string(raw: str) -> str:
    """Append missing closing brackets/braces to truncated JSON.

    Issue #5 root cause: the LLM intermittently emits params with the final
    ``}`` (or ``}]``) missing — e.g. ``{"filters":[{...}]`` — and the whole
    step was silently dropped. Tracks the opener stack outside string
    literals and appends the missing closers in order.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]" and stack and stack[-1] == ch:
            stack.pop()
    closers = "".join(reversed(stack))
    return raw + ('"' if in_string else "") + closers


def _parse_json_params(raw: str) -> dict:
    """Parse a JSON params string, repairing common LLM malformations.

    Tries ``json.loads`` first. On ``JSONDecodeError``, attempts (in order):
    unescaped internal quotes (Hebrew gershayim), then unbalanced
    brackets/braces (truncated output — issue #5), then both combined.
    If every repair fails, the original error is raised.

    Args:
        raw: JSON-encoded params string from the LLM.

    Returns:
        Parsed dict.

    Raises:
        json.JSONDecodeError: If the string cannot be parsed even after repair.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as original_err:
        for candidate in (
            _repair_json_string(raw),
            _balance_json_string(raw),
            _balance_json_string(_repair_json_string(raw)),
        ):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise original_err


def _convert_llm_step(llm_step: ExecutionStepLLM) -> ExecutionStep:
    """Convert a single LLM step to a typed ExecutionStep.

    Args:
        llm_step: Step with string action and dict params.

    Returns:
        Typed ExecutionStep.

    Raises:
        ValueError: If the action is unknown or params don't match.
    """
    action = StepAction(llm_step.action)
    params_model = _ACTION_PARAMS_MODEL[action]
    raw_params = _parse_json_params(llm_step.params) if isinstance(llm_step.params, str) else dict(llm_step.params)

    # Special handling for RetrieveParams: convert filter dicts to Filter
    # objects. _convert_filter_dict returns None for filters dropped because
    # of empty values (issue #49) — keep the step, lose only that filter.
    if action == StepAction.RETRIEVE and "filters" in raw_params:
        converted = [_convert_filter_dict(f) for f in raw_params["filters"]]
        raw_params["filters"] = [filt for filt in converted if filt is not None]

    typed_params = params_model(**raw_params)

    return ExecutionStep(
        action=action,
        params=typed_params,
        label=llm_step.label,
        depends_on=list(llm_step.depends_on),
    )


def _remap_single_ref(ref: str, old_to_new: dict[int, int]) -> str | None:
    """Remap a ``$step_N`` reference (or a '+'-joined union of them).

    Returns the remapped string, or ``None`` if every referenced step was
    skipped. Union members referencing skipped steps are dropped (issue #8:
    they previously survived UNCHANGED, leaving stale indices pointing at
    the wrong record sets). Non-reference strings are returned unchanged.
    """
    if "+" in ref:
        parts = [p.strip() for p in ref.split("+")]
        if all(_STEP_REF_RE.match(p) for p in parts):
            remapped = [
                r for r in (_remap_single_ref(p, old_to_new) for p in parts)
                if r is not None
            ]
            return "+".join(remapped) if remapped else None
        return ref
    m = _STEP_REF_RE.match(ref)
    if not m:
        return ref
    old_idx = int(m.group(1))
    if old_idx not in old_to_new:
        return None
    return f"$step_{old_to_new[old_idx]}"


def _remap_step_refs_in_params(
    params,
    old_to_new: dict[int, int],
) -> None:
    """Remap ``$step_N`` references inside typed params after step skipping.

    Mutates *params* in place.  Handles ``scope``, ``targets``,
    ``agents`` list, and ``filters[].value``.
    """
    # scope (RetrieveParams, AggregateParams, SampleParams)
    scope = getattr(params, "scope", None)
    if isinstance(scope, str):
        remapped = _remap_single_ref(scope, old_to_new)
        if remapped is None:
            remapped = "full_collection"
        if remapped != scope:
            params.scope = remapped

    # targets (EnrichParams)
    targets = getattr(params, "targets", None)
    if isinstance(targets, str):
        remapped = _remap_single_ref(targets, old_to_new)
        if remapped is not None and remapped != targets:
            params.targets = remapped

    # agents list (FindConnectionsParams)
    agents = getattr(params, "agents", None)
    if isinstance(agents, list):
        new_agents = []
        for agent in agents:
            if isinstance(agent, str):
                remapped = _remap_single_ref(agent, old_to_new)
                if remapped is not None:
                    new_agents.append(remapped)
            else:
                new_agents.append(agent)
        params.agents = new_agents

    # filters (RetrieveParams)
    filters = getattr(params, "filters", None)
    if isinstance(filters, list):
        for f in filters:
            val = getattr(f, "value", None)
            if isinstance(val, str):
                remapped = _remap_single_ref(val, old_to_new)
                if remapped is not None and remapped != val:
                    f.value = remapped


def _convert_llm_plan(llm_plan: InterpretationPlanLLM) -> InterpretationPlan:
    """Convert an ``InterpretationPlanLLM`` to a typed ``InterpretationPlan``.

    Invalid steps (unknown action, bad params) are logged and skipped
    rather than crashing the pipeline.

    Args:
        llm_plan: Raw LLM output.

    Returns:
        Typed InterpretationPlan.
    """
    typed_steps: list[ExecutionStep] = []
    # Track original-index -> new-index for surviving steps
    old_to_new: dict[int, int] = {}

    dropped: list[str] = []
    for i, llm_step in enumerate(llm_plan.execution_steps):
        try:
            typed_steps.append(_convert_llm_step(llm_step))
            old_to_new[i] = len(typed_steps) - 1
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Skipping step %d (action=%r): %s", i, llm_step.action, exc
            )
            dropped.append(
                f"step {i} ({llm_step.label or llm_step.action}): {exc}"
            )
            continue

    # Remap depends_on and $step_N param references: translate old
    # indices to new ones, dropping references to skipped steps.
    for step in typed_steps:
        step.depends_on = [
            old_to_new[dep]
            for dep in step.depends_on
            if dep in old_to_new
        ]
        _remap_step_refs_in_params(step.params, old_to_new)

    # Convert LLM directives (JSON string params) to typed directives
    typed_directives: list[ScholarlyDirective] = []
    for d in llm_plan.directives:
        params_dict = {}
        if d.params:
            try:
                params_dict = json.loads(d.params) if isinstance(d.params, str) else dict(d.params)
            except (json.JSONDecodeError, TypeError):
                params_dict = {}
        typed_directives.append(
            ScholarlyDirective(
                directive=d.directive,
                params=params_dict,
                label=d.label,
            )
        )

    return InterpretationPlan(
        intents=list(llm_plan.intents),
        reasoning=llm_plan.reasoning,
        execution_steps=typed_steps,
        directives=typed_directives,
        confidence=llm_plan.confidence,
        clarification=llm_plan.clarification,
        dropped_steps=dropped,
    )


# ============================================================================
# Step reference validation
# ============================================================================

_STEP_REF_RE = re.compile(r"^\$step_(\d+)$")


def _extract_step_refs_from_params(params) -> list[int]:
    """Extract all $step_N references from a typed params object.

    Checks ``scope``, ``targets``, ``agents`` list, and filter ``value``
    fields for $step_N patterns.

    Args:
        params: A typed params object (RetrieveParams, AggregateParams, etc.).

    Returns:
        List of referenced step indices.
    """
    refs: list[int] = []

    # scope field (RetrieveParams, AggregateParams, SampleParams) —
    # may be a single ref or a '+'-joined union (issue #8)
    scope = getattr(params, "scope", None)
    if scope and scope not in ("full_collection", "$previous_results"):
        for part in scope.split("+"):
            m = _STEP_REF_RE.match(part.strip())
            if m:
                refs.append(int(m.group(1)))

    # targets field (EnrichParams)
    targets = getattr(params, "targets", None)
    if targets:
        m = _STEP_REF_RE.match(targets)
        if m:
            refs.append(int(m.group(1)))

    # agents list (FindConnectionsParams)
    agents = getattr(params, "agents", None)
    if agents:
        for agent in agents:
            m = _STEP_REF_RE.match(str(agent))
            if m:
                refs.append(int(m.group(1)))

    # filters (RetrieveParams)
    filters = getattr(params, "filters", None)
    if filters:
        for f in filters:
            val = getattr(f, "value", None)
            if isinstance(val, str):
                m = _STEP_REF_RE.match(val)
                if m:
                    refs.append(int(m.group(1)))

    return refs


def _validate_step_refs(plan: InterpretationPlan) -> None:
    """Validate all $step_N references in the plan.

    Checks:
    1. All ``depends_on`` indices are in range [0, num_steps).
    2. No step depends on itself.
    3. No circular dependency chains.
    4. All $step_N references in params are in range.

    Args:
        plan: The typed InterpretationPlan to validate.

    Raises:
        ValueError: If any reference is invalid.
    """
    n = len(plan.execution_steps)
    if n == 0:
        return

    # 1. Check depends_on indices are in range and not self-referencing
    for i, step in enumerate(plan.execution_steps):
        for dep in step.depends_on:
            if dep < 0 or dep >= n:
                raise ValueError(
                    f"Step {i} depends_on index {dep} is out of range "
                    f"(plan has {n} steps)"
                )
            if dep == i:
                raise ValueError(
                    f"Step {i} has a self-referencing dependency "
                    f"(circular reference)"
                )

    # 2. Check for circular dependency chains via topological sort
    # Build adjacency: step -> set of steps it depends on
    visited = [0] * n  # 0=unvisited, 1=in-progress, 2=done
    def _dfs(node: int) -> None:
        if visited[node] == 2:
            return
        if visited[node] == 1:
            raise ValueError(
                f"circular dependency detected involving step {node}"
            )
        visited[node] = 1
        for dep in plan.execution_steps[node].depends_on:
            _dfs(dep)
        visited[node] = 2

    for i in range(n):
        _dfs(i)

    # 3. Check $step_N references in params are in range
    for i, step in enumerate(plan.execution_steps):
        param_refs = _extract_step_refs_from_params(step.params)
        for ref in param_refs:
            if ref < 0 or ref >= n:
                raise ValueError(
                    f"Step {i} param contains $step_{ref} which is out of range "
                    f"(plan has {n} steps)"
                )


# ============================================================================
# Public API
# ============================================================================


async def interpret(
    query: str,
    session_context: Optional[SessionContext] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> InterpretationPlan:
    """Interpret a user query into an execution plan.

    This is the main entry point for Stage 1 of the scholar pipeline.
    It calls the LLM to produce a structured plan, then validates
    all $step_N references before returning.

    Args:
        query: User's natural language query.
        session_context: Optional context from prior conversation turns.
        model: LiteLLM model string. If None, reads from model config.
        api_key: Optional API key (unused — litellm reads keys from env).

    Returns:
        Validated InterpretationPlan.

    Raises:
        ValueError: If the plan contains invalid step references.
        RuntimeError: If the LLM call fails.
    """
    if model is None:
        config = load_config()
        model = get_model(config, "interpreter")
    plan = await _call_llm(query, session_context, model, api_key)
    _validate_step_refs(plan)
    return plan
