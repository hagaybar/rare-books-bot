# Scholar Pipeline Design

**Date**: 2026-03-25
**Status**: Approved design, pending implementation plan

## Problem

The rare books bot handles user queries through a rigid chain of hardcoded detectors (`is_overview_query` → `detect_analytical_query` → `interpret_query`). Each detector has its own codepath, and anything that doesn't match falls through to an LLM intent agent that can only produce structured filter JSON. This architecture fails on:

- Entity exploration ("Who was Joseph Karo?") — rejected as non-bibliographic
- Comparative queries ("Compare Venice and Amsterdam as printing centers") — no handler
- Mixed-intent queries ("Who was Karo and how does he compare to Maimonides?") — forced into single intent
- Scholarly reasoning ("What's significant about our incunabula?") — no narrative depth

The historian evaluation scored 153/500 (31%) across 20 scholarly queries. Root causes: name form mismatches (6 queries), missing aggregation (3), thin narrative (5), missing cross-references (5), no curation (1).

## Design Principle

> The LLM may be creative in interpretation, but conservative in claims.

Strict evidence boundaries for holdings claims. Permissive scholarly reasoning for context, interpretation, and pedagogy. The LLM never invents holdings or silently changes counts. General scholarly knowledge is allowed but must be naturally distinguishable from collection-grounded claims.

## Architecture: Interpret → Execute → Narrate

Three stages, two LLM calls sandwiching a deterministic layer.

```
User Query
    │
    ▼
┌─────────────────────────────┐
│  Stage 1: INTERPRETER (LLM) │
│  Input: query + session     │
│  Output: InterpretationPlan │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Stage 2: EXECUTOR (code)   │
│  Walks plan steps via SQL   │
│  Output: ExecutionResult    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Stage 3: NARRATOR (LLM)    │
│  Input: query + results     │
│  Output: ScholarResponse    │
└─────────────────────────────┘
```

**Key invariant**: The narrator receives only verified data from the executor. It has no DB access. If a record wasn't found by the executor, the narrator cannot reference it as a holding.

## Stage 1: Interpreter

**Module**: `scripts/chat/interpreter.py` (new, replaces `intent_agent.py`)

### Purpose

Receive a user query and session context. Produce an `InterpretationPlan` — a structured sequence of execution steps and scholarly directives that tells the executor what to look up and the narrator how to reason about the results.

### Intent Classification

The interpreter classifies into one or more intents (mixed intents supported):

| Intent | Example |
|--------|---------|
| `retrieval` | "Hebrew books printed in Venice" |
| `entity_exploration` | "Who was Joseph Karo?" |
| `analytical` | "Chronological shape of the collection" |
| `comparison` | "Compare Venice and Amsterdam as printing centers" |
| `curation` | "Select 10 books for a Hebrew printing exhibit" |
| `topical` | "What can you tell me about books on astronomy?" |
| `follow_up` | "Only from the 17th century" |
| `overview` | "What's in this collection?" |
| `out_of_scope` | "What's the weather today?" |

Intent labels are guidance for the LLM and used for logging/UI hints. The plan steps are what the executor acts on.

### Plan Schema

```python
class InterpretationPlan(BaseModel):
    intents: list[str]                        # One or more intent labels
    reasoning: str                            # Why the LLM interpreted it this way
    execution_steps: list[ExecutionStep]       # Steps for the deterministic executor
    directives: list[ScholarlyDirective]       # Instructions for the narrator
    confidence: float                         # 0.0-1.0
    clarification: str | None = None          # If set, ask this instead of executing

class ExecutionStep(BaseModel):
    action: StepAction                        # Fixed enum of executor actions
    params: ResolveAgentParams | ResolvePublisherParams | RetrieveParams | AggregateParams | FindConnectionsParams | EnrichParams | SampleParams
    label: str                                # Human-readable description
    depends_on: list[int] = []                # Step indices this depends on

class ScholarlyDirective(BaseModel):
    directive: str                            # Free-form directive type
    params: dict                              # Directive-specific context
    label: str                                # Human-readable description
```

### Execution Step Types

Fixed, enumerated action types. Each has a typed params model:

```python
class StepAction(str, Enum):
    RESOLVE_AGENT     = "resolve_agent"
    RESOLVE_PUBLISHER = "resolve_publisher"
    RETRIEVE          = "retrieve"
    AGGREGATE         = "aggregate"
    FIND_CONNECTIONS  = "find_connections"
    ENRICH            = "enrich"
    SAMPLE            = "sample"

class ResolveAgentParams(BaseModel):
    name: str                                 # Query name (e.g., "Joseph Karo")
    variants: list[str] = []                  # LLM-proposed alternative forms

class ResolvePublisherParams(BaseModel):
    name: str
    variants: list[str] = []

class RetrieveParams(BaseModel):
    filters: list[Filter]                     # Reuses existing Filter model from scripts.schemas.query_plan
    scope: str = "full_collection"            # "full_collection" or "$step_N"

class AggregateParams(BaseModel):
    field: str                                # e.g., "date_decade", "place", "publisher"
    scope: str = "full_collection"            # "full_collection" or "$step_N"
    limit: int = 20

class FindConnectionsParams(BaseModel):
    agents: list[str]                         # Agent refs: literal names or "$step_N"
    depth: int = 1

class EnrichParams(BaseModel):
    targets: str                              # "$step_N" reference to resolved agents
    fields: list[str] = ["bio", "links"]      # What to fetch

class SampleParams(BaseModel):
    scope: str                                # "$step_N" reference
    n: int = 10
    strategy: str = "diverse"                 # "diverse", "notable", "earliest"
```

### Step Output Types

Each executor step produces a typed output stored in `StepResult.data`:

```python
class ResolvedEntity(BaseModel):
    """Output of resolve_agent / resolve_publisher."""
    query_name: str                           # Original name from the plan
    matched_values: list[str]                 # Canonical DB values matched (e.g., ["קארו, יוסף בן אפרים"])
    match_method: str                         # "alias_exact", "alias_fuzzy", "order_insensitive", "none"
    confidence: float

class RecordSet(BaseModel):
    """Output of retrieve / sample."""
    mms_ids: list[str]                        # Record identifiers
    total_count: int                          # Total matches (may exceed len(mms_ids) if truncated)
    filters_applied: list[dict]               # Echo of filters for audit trail

class AggregationResult(BaseModel):
    """Output of aggregate."""
    field: str                                # What was aggregated
    facets: list[dict]                        # [{"value": "venice", "count": 42}, ...]
    total_records: int                        # Records in scope

class ConnectionGraph(BaseModel):
    """Output of find_connections."""
    connections: list[dict]                   # [{"agent_a": "...", "agent_b": "...", "shared_records": 3, "shared_mms_ids": [...]}]
    isolated: list[str]                       # Agents with no connections found

class EnrichmentBundle(BaseModel):
    """Output of enrich."""
    agents: list[AgentSummary]                # Full agent profiles with links
```

### `$step_N` Resolution — Type Semantics

Each executor step produces a typed output. When a downstream step references `$step_N`, the executor resolves it based on the producing step's output type:

| Producing Step | Output Type | What `$step_N` Resolves To |
|----------------|------------|---------------------------|
| `resolve_agent` | `ResolvedEntity` | List of canonical agent_norm values matched in DB |
| `resolve_publisher` | `ResolvedEntity` | List of canonical publisher_norm values matched in DB |
| `retrieve` | `RecordSet` | List of MMS IDs (record identifiers) |
| `aggregate` | `AggregationResult` | Dict of facet counts |
| `find_connections` | `ConnectionGraph` | Agent pairs with shared records |
| `enrich` | `EnrichmentBundle` | Agent profiles with bio, links |
| `sample` | `RecordSet` | Subset of MMS IDs |

The executor validates type compatibility at resolution time based on the consuming param field:
- `scope` → expects `RecordSet` (narrows SQL to those MMS IDs via `WHERE mms_id IN (...)`)
- `value` in filters → expects `ResolvedEntity` (substitutes matched_values into filter)
- `agents` → expects `ResolvedEntity` (canonical agent names)
- `targets` → expects `ResolvedEntity` or `RecordSet` (entities to enrich)

The special scope `"$previous_results"` resolves to the `RecordSet` from the previous conversation turn (via `SessionContext.previous_record_ids`). This enables follow-up refinements.

### `$step_N` in Scholarly Directives

Directive params may contain `$step_N` references (e.g., `"set_a": "$step_0"` in a `compare` directive). The executor does **not** resolve these — they are passed through as-is to the narrator prompt, where the corresponding `StepResult` data is rendered inline. The narrator sees both the directive and the step results, so it can interpret the reference contextually.

### `retrieve` Step Filter Handling

The `retrieve` step reuses the existing `Filter` model from `scripts.schemas.query_plan`. The executor converts `RetrieveParams.filters` into a `QueryPlan` object and passes it to `db_adapter.build_where_clause()`. Before conversion, the executor resolves any `$step_N` references in filter values to their concrete resolved names.

### Scholarly Directives

Free-form instructions passed through to the narrator. The `directive` field is not an enum — new directive types require only a narrator prompt update, no code change.

Initial vocabulary:

| Directive | Purpose |
|-----------|---------|
| `curate` | Select and rank by significance, explain choices |
| `expand` | Provide deeper context on specific items or entities |
| `interpret` | Explain significance, meaning, or patterns |
| `compare` | Narrative comparison between sets or entities |
| `synthesize` | Weave multiple threads into a coherent narrative |
| `contextualize` | Place results in historical/intellectual context |
| `teach` | Frame for pedagogical use |

Both executor steps and directives are designed to grow. Adding an executor step means writing one handler function and a typed params model. Adding a scholarly directive means updating the narrator prompt only.

### Example Plan: "Who was Joseph Karo?"

```json
{
  "intents": ["entity_exploration"],
  "reasoning": "User asks about Joseph Karo — need to find his works and provide scholarly context.",
  "execution_steps": [
    {"action": "resolve_agent", "params": {"name": "Joseph Karo", "variants": ["קארו, יוסף בן אפרים", "Caro, Joseph"]}, "label": "Resolve Karo"},
    {"action": "retrieve", "params": {"filters": [{"field": "agent_norm", "op": "EQUALS", "value": "$step_0"}]}, "label": "Find works by Karo"},
    {"action": "retrieve", "params": {"filters": [{"field": "subject", "op": "CONTAINS", "value": "Shulchan Aruch"}]}, "label": "Find related subject works"},
    {"action": "enrich", "params": {"targets": "$step_0", "fields": ["bio", "connections", "links"]}, "label": "Get biographical data"},
    {"action": "find_connections", "params": {"agents": ["$step_0"], "depth": 1}, "label": "Find connected figures"}
  ],
  "directives": [
    {"directive": "expand", "params": {"focus": "Joseph Karo", "aspect": "biographical and intellectual significance"}, "label": "Expand on Karo"},
    {"directive": "contextualize", "params": {"theme": "Jewish legal codification"}, "label": "Historical context"}
  ],
  "confidence": 0.92
}
```

### Example Plan: "Compare Venice and Amsterdam as Hebrew printing centers"

```json
{
  "intents": ["comparison", "analytical"],
  "reasoning": "Comparative query requiring two retrievals and cross-analysis.",
  "execution_steps": [
    {"action": "retrieve", "params": {"filters": [{"field": "imprint_place", "op": "EQUALS", "value": "venice"}, {"field": "language", "op": "EQUALS", "value": "heb"}]}, "label": "Hebrew books from Venice"},
    {"action": "retrieve", "params": {"filters": [{"field": "imprint_place", "op": "EQUALS", "value": "amsterdam"}, {"field": "language", "op": "EQUALS", "value": "heb"}]}, "label": "Hebrew books from Amsterdam"},
    {"action": "aggregate", "params": {"field": "date_decade", "scope": "$step_0"}, "label": "Venice temporal distribution"},
    {"action": "aggregate", "params": {"field": "date_decade", "scope": "$step_1"}, "label": "Amsterdam temporal distribution"}
  ],
  "directives": [
    {"directive": "compare", "params": {"set_a": "$step_0", "set_b": "$step_1", "lens": "printing center development"}, "label": "Compare the two centers"},
    {"directive": "contextualize", "params": {"theme": "Migration of Hebrew printing from Mediterranean to Northern Europe"}, "label": "Historical arc"}
  ],
  "confidence": 0.95
}
```

### Out-of-Scope Handling

When the interpreter classifies a query as `out_of_scope`, it produces an empty `execution_steps` list, no directives, and a `reasoning` field explaining why. The executor is skipped (nothing to execute). The narrator receives the empty result and composes a polite redirect:

> "I'm a specialist in rare books and bibliographic history. I'm not able to help with that question, but I'd be happy to help you explore the collection. For example, you could ask about Hebrew printing in Venice, works by a specific author, or the chronological shape of the collection."

## Stage 2: Executor

**Module**: `scripts/chat/executor.py` (new)

### Purpose

Walk the plan's executor steps in dependency order, run real DB queries, collect grounding links, and produce a verified `ExecutionResult`. Scholarly directives pass through untouched to the narrator.

### Output Schema

```python
class ExecutionResult(BaseModel):
    steps_completed: list[StepResult]     # One per executor step
    directives: list[ScholarlyDirective]  # Passed through from plan
    grounding: GroundingData              # Links, record IDs, sources
    original_query: str                   # Echo back for narrator context
    session_context: SessionContext | None # Follow-up context
    truncated: bool = False               # True if records were capped at 30

class StepResult(BaseModel):
    step_index: int
    action: str
    label: str
    status: str                           # "ok", "empty", "partial", "error"
    data: ResolvedEntity | RecordSet | AggregationResult | ConnectionGraph | EnrichmentBundle
    record_count: int | None
    error_message: str | None = None      # If status is "error"

class RecordSummary(BaseModel):
    """Summary of a bibliographic record for narrator consumption."""
    mms_id: str                           # Record identifier
    title: str                            # Title from records table
    date_display: str | None              # Human-readable date (e.g., "Venice, 1565")
    place: str | None                     # Normalized place
    publisher: str | None                 # Normalized publisher
    language: str | None                  # Language code
    agents: list[str]                     # Agent names associated with this record
    subjects: list[str]                   # Subject headings
    primo_url: str                        # Catalog link
    source_steps: list[int]               # Which retrieve steps found this record

class AgentSummary(BaseModel):
    """Enriched agent profile for narrator consumption."""
    canonical_name: str                   # Primary name form
    variants: list[str]                   # Known name forms (including cross-script)
    birth_year: int | None
    death_year: int | None
    occupations: list[str]
    description: str | None               # Wikidata description
    record_count: int                     # How many records in collection
    links: list[GroundingLink]            # Wikipedia, Wikidata, NLI, VIAF

class GroundingData(BaseModel):
    records: list[RecordSummary]          # Deduplicated across all retrieve steps
    agents: list[AgentSummary]            # Enriched agent profiles
    aggregations: dict[str, list]         # Named aggregation results (step_label -> facets)
    links: list[GroundingLink]            # All links collected

class GroundingLink(BaseModel):
    entity_type: str                      # "record", "agent", "publisher"
    entity_id: str                        # MMS ID or authority URI
    label: str                            # Display name
    url: str                              # The actual link
    source: str                           # "primo", "wikipedia", "wikidata", "viaf", "nli"
```

### Record Deduplication

When the same record appears in multiple `retrieve` steps (e.g., a record matching both "works by Karo" and "Shulchan Aruch subject"), it appears once in `GroundingData.records` with `source_steps` listing all steps that found it. This preserves the evidence trail (the narrator can say "this record matches both as an author work and by subject").

### Step Handlers

Each executor step maps to a handler reusing existing modules:

| Step | Handler Uses |
|------|-------------|
| `resolve_agent` | `agent_authority.py` alias lookup + order-insensitive fallback |
| `resolve_publisher` | `publisher_authority.py` variant lookup |
| `retrieve` | `db_adapter.py` → `build_where_clause()` → SQL |
| `aggregate` | `aggregation.py` → `compute_aggregation()` |
| `find_connections` | `cross_reference.py` → `find_connections()` |
| `enrich` | Direct query on `authority_enrichment` table |
| `sample` | Strategy-based: `ORDER BY` + `LIMIT`, or diversity sampling, or `curation_engine.py` scoring for `notable` |

### Dependency Resolution

Steps declare `depends_on: [step_indices]`. The executor topologically sorts and runs in order, substituting `$step_N` references with actual results. If a step returns empty, dependent steps still run on an empty set. The `status` field records what happened.

**Validation rules** (applied before execution):
- Circular dependencies → reject plan, return error to narrator ("Plan contained circular dependencies")
- Out-of-range `$step_N` references → reject plan
- Self-references → reject plan
- Unknown `action` values → skip step, mark `status: "error"` with message "Unknown action type"

These are LLM output errors. The executor logs them and continues with remaining valid steps. The narrator is informed of skipped steps and can acknowledge limitations.

### Narrator Token Budget

For large result sets (>30 records), the executor includes:
- Full `RecordSummary` for the first 30 records (sorted by relevance or date)
- Total count and aggregation summaries for the full set
- A `truncated: true` flag on the `ExecutionResult`

The narrator works with the 30 detailed records but can reference the total count accurately. This keeps the narrator prompt within ~4K tokens of record data while preserving exact counts for claims.

### Link Collection

After all steps complete, the executor sweeps through all records and agents found and collects every available link:

| Entity | Link Source |
|--------|------------|
| Record | Primo URL via `_generate_primo_url(mms_id)` |
| Agent | `authority_enrichment.wikipedia_url` |
| Agent | `authority_enrichment.wikidata_id` → `https://www.wikidata.org/wiki/{id}` |
| Agent | `authority_enrichment.nli_id` → NLI authority URL |
| Agent | `authority_enrichment.viaf_id` → VIAF URL |

No new data sources needed.

## Stage 3: Narrator

**Module**: `scripts/chat/narrator.py` (new)

### Purpose

Receive the verified `ExecutionResult` and compose a scholarly response. The narrator is an LLM call with a rich persona prompt. It can only reference data present in the `ExecutionResult`.

### Persona Prompt (Core Rules)

```
You are a scholar of Jewish book history and early modern print culture,
serving as the voice of a rare books collection discovery system.

You have deep knowledge of Hebrew printing, intellectual networks,
and bibliographic traditions. You speak with authority and nuance.

EVIDENCE RULES (non-negotiable):
1. When citing holdings, use ONLY records from the provided data.
   State exact counts — never approximate when exact data is available.
2. You MAY use general scholarly knowledge for context, interpretation,
   and historical framing.
3. When stating something from general knowledge, never imply it comes
   from the collection.
4. If the collection holds nothing relevant, say so clearly. You may still
   provide scholarly context and suggest related holdings that WERE found.
5. Every record you mention by specifics (title, date, printer) must appear
   in the provided grounding data.
6. When links are available (Primo, Wikipedia, Wikidata), weave them
   naturally into the response as references.
```

### Input

The narrator receives a structured prompt assembled from the `ExecutionResult`:

- Original query text
- Scholarly directives (from the plan)
- Verified records with details
- Agent profiles with enrichment data and links
- Aggregation results
- Empty/failed steps (so it can acknowledge gaps)
- Session context (for follow-up coherence)

### Output Schema

```python
class ScholarResponse(BaseModel):
    narrative: str                          # Scholarly text (markdown)
    suggested_followups: list[str]          # 2-4 contextual next questions
    grounding: GroundingData                # Pass-through from executor
    confidence: float                       # Narrator self-assessed confidence
    metadata: dict                          # Intent labels, step counts, timing
```

### Evidence Presentation

The response uses a hybrid approach:
- **Inline**: Natural scholarly prose with collection facts woven in ("Our collection holds 3 editions...")
- **Structured**: The `grounding` field carries the full evidence (record IDs, links, counts) for the frontend to render independently

Links appear naturally in the narrative text and are also available in the structured `grounding` for UI rendering (record cards, external links section).

### Example Output

For "Who was Joseph Karo?":

> Joseph Karo (1488-1575) was the preeminent legal codifier of the early modern Jewish world. Born in Toledo shortly before the 1492 expulsion, he eventually settled in Safed, which became the center of a remarkable flowering of Jewish mysticism and legal scholarship in the sixteenth century.
>
> Karo's magnum opus was the *Shulchan Aruch* ("Set Table"), a systematic code of Jewish law that became -- especially with the glosses of Moses Isserles for Ashkenazi practice -- the most widely authoritative halakhic reference for subsequent centuries.
>
> **Our collection holds 3 works by Karo**, spanning three printing centers and nearly 150 years:
>
> - *Bet Yosef* (Sabbioneta, 1553) -- printed by Tobias Foa ([catalog](https://...))
> - *Shulchan Aruch* (Venice, 1565) -- a Bragadin press edition ([catalog](https://...))
> - *Shulchan Aruch* (Amsterdam, 1698) -- a Proops edition ([catalog](https://...))
>
> The geographic spread mirrors the broader migration of Hebrew printing after the Counter-Reformation. Notably, our collection includes works by Solomon Alkabetz, Karo's associate in the Safed circle.
>
> [Joseph Karo on Wikipedia](https://...) | [NLI Authority](https://...) | [Wikidata](https://...)

## Integration: API Layer

**Module**: Modified `app/api/main.py`

### Core Flow

The current ~600 lines of routing/formatting logic in `handle_query_definition_phase` collapses to:

```python
async def handle_chat(request, session, store, bib_db):
    plan = await interpret(request.message, session)

    if plan.clarification:
        return clarification_response(plan, session)

    execution_result = execute_plan(plan, bib_db)
    response = await narrate(request.message, execution_result, session)
    store.add_message(session.session_id, response)
    return response
```

### Clarification Flow

The interpreter can set `clarification` instead of (or alongside) generating execution steps. This replaces the old hardcoded `clarification.py` module with LLM-driven ambiguity detection.

**When the interpreter clarifies:**
- Confidence < 0.7 (genuinely ambiguous query)
- Contradictory signals (e.g., "Hebrew books in Latin" — language conflict)
- Ambiguous entity (e.g., "Karo" could be Joseph Karo or another figure)
- Missing critical context (e.g., "compare these" with no prior session)

**What a clarification looks like:**

```json
{
  "intents": ["entity_exploration"],
  "reasoning": "User asks about 'Karo' — could be Joseph Karo (1488-1575, Shulchan Aruch) or another figure.",
  "execution_steps": [],
  "directives": [],
  "confidence": 0.55,
  "clarification": "Could you clarify which Karo you mean? Our collection includes works by Joseph Karo (1488-1575), the author of the Shulchan Aruch. Is that who you're looking for, or someone else?"
}
```

**Key difference from old system:** The LLM generates contextual, helpful clarifications (it knows the collection and can suggest specific options) rather than generic "please be more specific" messages. The clarification is stored in session history, so the user's response ("yes, the Shulchan Aruch author") becomes context for the next interpretation.

**Clarification with partial plan:** The interpreter may set `clarification` AND include execution steps. This means "I'm going to try this interpretation, but I'm not fully confident — here's what I'd like to confirm." The pipeline can choose to either:
- Short-circuit and ask (conservative, default for confidence < 0.7)
- Execute the partial plan and present results with the clarification attached (for confidence 0.7-0.85)

The confidence threshold is configurable: `CLARIFICATION_THRESHOLD = 0.7`.

### Session Follow-Up Mechanics

The interpreter receives session context to handle follow-up queries ("only from the 17th century", "what about Amsterdam?"):

```python
class SessionContext(BaseModel):
    """Context passed to interpreter and narrator for follow-ups."""
    recent_messages: list[Message]          # Last 5 messages (user + assistant)
    previous_plan: InterpretationPlan | None  # Plan from previous turn
    previous_record_ids: list[str] | None   # MMS IDs from previous result set
    previous_query: str | None              # The query that produced those results
```

**How follow-ups work:**

1. The interpreter sees `previous_plan` and `recent_messages`. It can generate a new plan that refines the previous one — e.g., adding a year filter to the previous retrieval's filters.
2. The executor can scope a `retrieve` step to `"$previous_results"` — a special reference that resolves to the MMS IDs from the previous turn. This is a simple `WHERE mms_id IN (...)` clause added to the SQL.
3. The narrator sees the conversation history and can frame the response as a refinement ("Narrowing to the 17th century, 2 of the 3 Karo editions remain...").

**No explicit phase transitions needed.** The interpreter decides whether to start fresh or refine based on context. The `phase` field on `ChatResponse` can remain for frontend UI hints but no longer drives routing logic.

### Relationship to Existing Query Pipeline

The existing `scripts/query/compile.py` (`compile_query`), `scripts/query/llm_compiler.py`, and `scripts/query/execute.py` (`execute_plan`) formed the original NL → QueryPlan → SQL pipeline. Under the new architecture:

- `llm_compiler.py` is superseded by the interpreter (richer output, same LLM call pattern)
- `execute.py` is superseded by the executor (handles more than just SQL retrieval)
- `compile.py` utility functions (e.g., `compute_plan_hash` for caching) may be reused
- `db_adapter.py` is kept — the executor's `retrieve` handler still calls `build_where_clause()`
- `QueryPlan` model is kept as an intermediate — the executor converts `RetrieveParams.filters` into a `QueryPlan` before passing to `db_adapter`

### WebSocket Streaming

Three stages map to progress messages:

```
→ {"type": "progress",  "message": "Understanding your question..."}
→ {"type": "plan",      "summary": "Looking up Joseph Karo, finding works..."}
→ {"type": "progress",  "message": "Searching the collection..."}
→ {"type": "progress",  "message": "Found 3 works. Checking connections..."}
→ {"type": "evidence",  "data": <partial ExecutionResult>}
→ {"type": "progress",  "message": "Composing response..."}
→ {"type": "narrative_chunk", "text": "Joseph Karo (1488-1575)..."}
→ {"type": "complete",  "response": ScholarResponse}
```

Stage 3 can stream token-by-token via the OpenAI streaming API.

### Error Handling

| Failure | Behavior |
|---------|----------|
| Interpreter LLM fails | Return "I'm having trouble understanding that, could you rephrase?" |
| Interpreter sets `clarification` | Short-circuit: return clarification to user, skip executor + narrator |
| Executor step returns empty | Mark `status: "empty"`, continue. Narrator acknowledges absence. |
| Executor step errors | Mark `status: "error"`, continue other steps. Narrator works with what succeeded. |
| Narrator LLM fails | Fall back to structured summary from `ExecutionResult` (no LLM needed) |
| All steps empty | Narrator: "We don't hold works matching X" + scholarly context + redirect to related holdings |

### Cost and Latency

Two LLM calls per query (interpreter + narrator), or one if clarification short-circuits.

**Latency**: ~1-2s interpreter + ~50-200ms executor + ~1-2s narrator = **~2-4s total**. Acceptable given WebSocket streaming shows progress throughout.

**Token budget per query** (at $1.25/M input, $10.00/M output):

| Component | Input Tokens | Output Tokens |
|-----------|-------------|---------------|
| Interpreter system prompt | ~1,000 | — |
| Interpreter context (session, query) | ~300-500 | — |
| Interpreter output (JSON plan) | — | ~400-700 |
| Narrator system prompt | ~600 | — |
| Narrator execution data (up to 30 records) | ~2,000-4,500 | — |
| Narrator output (narrative) | — | ~600-1,500 |
| **Totals** | **~4,000-6,500** | **~1,000-2,200** |

**Cost per query by complexity:**

| Query Type | Input | Output | Cost |
|-----------|-------|--------|------|
| Simple retrieval (<5 results) | ~3,500 | ~800 | ~$0.012 |
| Average query | ~5,250 | ~1,500 | ~$0.022 |
| Complex comparison (30+ records) | ~7,000 | ~2,200 | ~$0.031 |
| Clarification (1 LLM call, no narrator) | ~1,500 | ~400 | ~$0.006 |

**Monthly cost estimates:**

| Usage Level | Queries/Day | Monthly Cost |
|-------------|-------------|-------------|
| Light (research tool) | ~50 | ~$33 |
| Moderate (internal team) | ~200 | ~$132 |
| Heavy (public-facing) | ~1,000 | ~$660 |

**Cost control measures:**
- Clarification short-circuits save the narrator call (~50% cost reduction for ambiguous queries)
- Narrator receives max 30 records (truncated), capping input size
- No retry loops — LLM failures fall back to structured summaries, not re-attempts
- Interpreter plan caching possible for repeated identical queries (via `compute_plan_hash`)

## Module Disposition

### Removed

| Module | Replaced By |
|--------|-------------|
| `scripts/chat/intent_agent.py` | `interpreter.py` |
| `scripts/chat/analytical_router.py` | Interpreter handles intent classification |
| `scripts/chat/formatter.py` | `narrator.py` |
| `scripts/chat/narrative_agent.py` | `narrator.py` |
| `scripts/chat/thematic_context.py` | Narrator uses scholarly knowledge directly |
| `scripts/chat/clarification.py` | Interpreter's `clarification` field replaces hardcoded ambiguity detection |
| `scripts/chat/curator.py` | Narrator + curation_engine scoring |
| `scripts/chat/exploration_agent.py` | Interpreter + executor replace exploration phase routing. Migrate `AggregationResult` model to `aggregation.py` or `plan_models.py` before removing. |
| `scripts/query/llm_compiler.py` | Interpreter replaces LLM query compilation |
| `scripts/query/execute.py` | Executor replaces query execution |

### Kept

| Module | Used By |
|--------|---------|
| `scripts/chat/aggregation.py` | Executor `aggregate` handler. Absorbs `AggregationResult` from `exploration_agent.py`. |
| `scripts/chat/cross_reference.py` | Executor `find_connections` handler |
| `scripts/chat/models.py` | Session models (`ChatSession`, `Message`, `ActiveSubgroup`, etc.) |
| `scripts/chat/session_store.py` | Session persistence |
| `scripts/metadata/agent_authority.py` | Executor `resolve_agent` handler |
| `scripts/metadata/publisher_authority.py` | Executor `resolve_publisher` handler |
| `scripts/query/db_adapter.py` | Executor `retrieve` handler (SQL generation) |
| `scripts/query/compile.py` | Utility functions (`compute_plan_hash`) reused for caching |
| `scripts/query/exceptions.py` | `QueryCompilationError` etc., reused by executor error handling |
| `scripts/query/subject_hints.py` | Subject heading expansion, used by executor `retrieve` handler |
| `scripts/schemas/query_plan.py` | `Filter`, `FilterField`, `FilterOp`, `QueryPlan` models reused by executor |

### Reworked

| Module | Change |
|--------|--------|
| `scripts/chat/curation_engine.py` | Keep scoring heuristics, remove routing wrapper. Called by executor `sample` handler with `strategy: "notable"`. |
| `app/api/main.py` | Replace routing chain with three-stage pipeline. ~600 lines of routing/formatting removed, ~50 lines of pipeline code added. |

## Testing Strategy

### Stage 1: Interpreter Tests

`tests/scripts/chat/test_interpreter.py`

- Schema validation: output must parse into `InterpretationPlan` with valid step types and `$step_N` references
- Snapshot tests: 20 historian queries → assert structural similarity (right step types, right entities)
- Edge cases: empty query, non-English, adversarial input
- Mock LLM for fast execution without API key

### Stage 2: Executor Tests

`tests/scripts/chat/test_executor.py`

- Per-handler unit tests with in-memory SQLite
- Plan walkthrough tests: full `InterpretationPlan` → assert `ExecutionResult` contents
- Dependency resolution: `$step_N` references, empty step propagation
- Grounding completeness: every record gets Primo link, every enriched agent gets Wikipedia/Wikidata links
- No LLM dependency

### Stage 3: Narrator Tests

`tests/scripts/chat/test_narrator.py`

- Grounding compliance: parse narrative, verify every MMS ID / count / date appears in `ExecutionResult`
- No fabrication: for N records input, narrative must not claim N+1 or reference unknown IDs
- Empty results: narrative acknowledges absence, doesn't invent holdings
- Link inclusion: grounding links appear in markdown output
- Mock LLM for speed, select integration tests with real LLM

### Integration Tests

`tests/app/test_chat_pipeline.py`

- End-to-end: 20 historian queries through all three stages against test DB
- WebSocket streaming protocol verification
- Session follow-up coherence

### Test Evidence Reports

`reports/scholar-pipeline/`

All integration test runs that involve LLM interactions are captured as evidence reports:

```
reports/scholar-pipeline/
  <run-id>/
    Q01_bragadin_venice.json
    Q02_amsterdam_hebrew.json
    ...
    Q20_curated_exhibit.json
    summary.md
```

Each JSON file contains the full pipeline trace:

```json
{
  "query": "books printed by Bragadin press in Venice",
  "timestamp": "2026-03-25T...",
  "interpreter": {
    "plan": { "intents": [...], "steps": [...] },
    "latency_ms": 1200
  },
  "executor": {
    "result": { "steps_completed": [...], "grounding": {...} },
    "latency_ms": 85
  },
  "narrator": {
    "response": { "narrative": "...", "suggested_followups": [...] },
    "latency_ms": 1500
  },
  "scores": {
    "accuracy": null,
    "richness": null,
    "cross_ref": null,
    "narrative": null,
    "pedagogical": null
  }
}
```

The `summary.md` file contains aggregate scores and comparison to the baseline historian evaluation. Score fields are null until manually evaluated, supporting iterative quality assessment.

## Expected Impact

| Root Cause | Questions | Current | Expected |
|------------|-----------|---------|----------|
| NAME_FORM_MISMATCH | Q3, Q6, Q7, Q8, Q12, Q19 | 9/150 | ~70/150 |
| NO_AGGREGATION | Q14, Q15 | 2/50 | ~40/50 |
| NO_CURATION | Q20 | 1/25 | ~18/25 |
| THIN_NARRATIVE | Q1, Q4, Q11, Q16, Q18 | 53/125 | ~95/125 |
| MISSING_CROSS_REF | Q2, Q9, Q10, Q13, Q17 | 72/125 | ~100/125 |
| NO_COMPARISON | Q1, Q4, Q5 | 36/75 | ~55/75 |
| **Total** | | **153/500 (31%)** | **~378/500 (76%)** |

## Data Contract: Executor ↔ Database

Each executor handler depends on specific tables and columns. This contract is enforced at startup via a health check and tested in CI.

| Handler | Required Tables | Required Columns | Status |
|---------|----------------|-----------------|--------|
| `resolve_agent` | `agent_authorities`, `agent_aliases` | `canonical_name_lower`, `alias_form_lower`, `alias_type`, `authority_id` | Populated (2,421 authorities, 6,418 aliases) |
| `resolve_publisher` | `publisher_authorities`, `publisher_variants` | `canonical_name_lower`, `variant_form_lower`, `authority_id` | Populated (228 authorities, 265 variants) |
| `retrieve` | `records`, `imprints`, `agents`, `subjects`, `titles` | Standard M1/M2/M3 columns per `m3_contract.py` | Populated (2,796 records) |
| `aggregate` | Same as `retrieve` | Normalized columns: `date_start`, `place_norm`, `publisher_norm`, `country_name` | Populated |
| `find_connections` | `agents` | `record_id`, `agent_norm`, `authority_uri` | Populated (4,366 agent records) |
| `enrich` | `authority_enrichment` | `authority_uri`, `wikidata_id`, `wikipedia_url`, `person_info`, `nli_id`, `viaf_id` | Populated |
| `sample` | Same as `retrieve` | Plus `date_start` for "earliest", scoring fields for "notable" | Populated |
| Link collection | `authority_enrichment` | `wikipedia_url`, `wikidata_id`, `nli_id`, `viaf_id` | Populated |
| Link collection | (computed) | Primo URL via `_generate_primo_url(mms_id)` | Available |

**Startup health check** (`/health` endpoint extension):

The existing health endpoint checks `database_connected`. This is extended to verify:
1. All required tables exist
2. Each table has at least one row (guards against empty migrations)
3. Required columns are present (via `PRAGMA table_info`)

If any check fails, the health endpoint reports `"executor_ready": false` with details on which handler is broken. The API still starts (graceful degradation), but the affected handlers return `status: "error"` with a clear message.

**Contract evolution**: When a new executor handler is added, its table/column requirements must be added to this contract and to the startup health check. The `m3_contract.py` module already defines the M1/M2/M3 schema; this data contract extends it to cover M4+ (query/enrichment) tables.

## Prerequisites

Before implementation begins:

1. **Agent alias tables must exist**: Run `poetry run python -m app.cli seed-agent-authorities` to create and populate `agent_authorities` and `agent_aliases` tables. The executor's `resolve_agent` handler depends on these. **Status: Already populated** (2,421 authorities, 6,418 aliases).

2. **OpenAI API key**: Required for both interpreter and narrator LLM calls. Set `OPENAI_API_KEY` environment variable.

3. **All prerequisite tables populated**: Verify via `curl http://localhost:8000/health` — the extended health check should report `"executor_ready": true`.
