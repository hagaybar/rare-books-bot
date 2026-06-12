# Query Engine
> Last verified: 2026-06-12
> Source of truth for: Query compilation (NL to SQL), LLM usage rules, query plan schema, execution pipeline, relaxation ladder, concept bridge, FTS5 sanitization, bilingual search, and acceptance tests

## Overview

The query engine converts natural language bibliographic queries into structured SQL against the SQLite bibliographic database. It follows a strict pipeline: natural language -> QueryPlan (JSON) -> SQL -> CandidateSet + Evidence.

### Core Principle

The LLM is a **planner/explainer**, not the authority. LLM output must be validated against a JSON schema. If schema validation fails, the system returns an empty plan with an error in debug -- it does not retry (fail-closed pattern).

---

## Stable Interfaces (Contracts)

```python
parse_marc_xml(path: Path) -> Iterable[CanonicalRecord]
normalize_record(record: CanonicalRecord) -> NormalizedRecord  # raw + norm + confidence
compile_query(nl_query: str) -> QueryPlan  # JSON schema validated
execute_plan(plan: QueryPlan, sqlite_db: Path) -> CandidateSet + Evidence
```

These interfaces are the stable boundary between pipeline stages. Implementations may change; signatures must not.

---

## LLM Usage Rules

1. LLM is used **only** for query planning (converting natural language to structured QueryPlan). It is not used during normalization (M2) or execution.
2. LLM output is validated against Pydantic models via litellm's `structured_completion()` wrapper.
3. If schema validation fails: return empty plan with error in debug. Never retry.
4. All LLM calls are cached to prevent redundant API usage.

---

## Query Compilation (M4/M5)

### Implementation

**File**: `scripts/query/llm_compiler.py`

The query compiler uses LLM-based parsing via litellm's `structured_completion()`:

- **Model**: Configurable via `scripts/models/config.py` (any litellm-supported model)
- **Schema enforcement**: Pydantic models validated by litellm structured output
- **Caching**: JSONL cache at `data/query_plan_cache.jsonl` (query_text -> QueryPlan)
- **API key**: Set `OPENAI_API_KEY` environment variable (used by litellm)

> **Note**: This compiler is deprecated in favour of the scholar pipeline (`scripts/chat/interpreter.py`). It remains functional for the legacy CLI path and subject-hint retry logic.

### Usage

```python
from scripts.query.compile import compile_query

# With API key in environment
plan = compile_query("books published by Oxford between 1500 and 1599")

# Or pass explicitly (any litellm-supported model string)
plan = compile_query("...", api_key="sk-...", model="gpt-4.1-mini")
```

### Cache Behavior

- Cache hits return immediately (no API call)
- Cache misses call LLM and write to cache
- Cache is append-only JSONL for inspection and debugging
- Cache file: `data/query_plan_cache.jsonl`

---

## Query Plan Schema

Defined in `scripts/schemas/query_plan.py`:

### FilterField (Enum)

12 supported filter fields: `PUBLISHER`, `IMPRINT_PLACE`, `COUNTRY`, `YEAR`, `LANGUAGE`, `TITLE`, `SUBJECT`, `PHYSICAL_DESC`, `AGENT`, `AGENT_NORM`, `AGENT_ROLE`, `AGENT_TYPE`

`PHYSICAL_DESC` (MARC 300, physical description -- "maps", "plates", "engravings") supports **CONTAINS only**. The SQL is an `EXISTS` subquery against the `physical_descriptions` table using a case-insensitive `LIKE` substring match -- there is **no FTS table** for physical descriptions (the table is small), so FTS5 sanitization does not apply to this field (`scripts/query/db_adapter.py`).

### FilterOp (Enum)

4 filter operations: `EQUALS`, `CONTAINS`, `RANGE`, `IN`

**Per-field support is not uniform**: `year` supports only `RANGE` in the SQL adapter. The chat interpreter's `_convert_filter_dict` repairs common LLM shape mistakes at the conversion boundary: `IN` with a bare string is wrapped in a list, `EQUALS`/`CONTAINS` with a list is promoted to `IN`, and `year EQUALS <v>` with a parseable year is coerced to the degenerate `RANGE(start=v, end=v)` (issue #44 — previously crashed the retrieve step). `$step_N` references and unparseable values pass through untouched.

### Filter (BaseModel)

Single filter condition: field, op, value/start/end, negate, confidence, notes.

### QueryPlan (BaseModel)

Structured query plan: filters, soft_filters, limit, debug. This is the intermediate representation between natural language and SQL.

---

## Candidate Set Schema

Defined in `scripts/schemas/candidate_set.py`:

### Evidence (BaseModel)

Why a record matched: field, value, operator, matched_against, source (MARC path), confidence.

### Candidate (BaseModel)

Single matched record with rationale and evidence list, plus display fields.

### CandidateSet (BaseModel)

Complete query result: query text, plan hash, SQL query used, candidates list, total count.

---

## FTS5 Sanitization

**File**: `scripts/query/db_adapter.py` (`sanitize_fts5_query()`)

FTS5 full-text search queries must be sanitized before execution. The `sanitize_fts5_query()` function strips characters that are FTS5 syntax metacharacters:

- **Apostrophes/single quotes** — primary cause of FTS5 crashes (including Hebrew geresh)
- **Parentheses, caret, colon, curly braces, plus/minus** — FTS5 operators

This function is called automatically for `TITLE` and `SUBJECT` filters using the `CONTAINS` operation. A parallel implementation exists in `scripts/marc/m3_query.py` for the M3 indexing path.

---

## Bilingual Subject Search

Subject headings are searchable in both English and Hebrew. Fix 19 (`scripts/qa/fixes/fix_19_add_hebrew_subjects.py`) added a `value_he` column to the subjects table with 3,094+ Hebrew translations, and rebuilt the `subjects_fts` FTS5 index to include both languages.

The interpreter (`scripts/chat/interpreter.py`) handles bilingual queries by:
- Using Hebrew terms directly in SUBJECT and TITLE filters
- Optionally adding parallel English-language filters for broader recall
- Preferring `CONTAINS` over `EQUALS` for cross-language matching

### Collection Queries

Named collections (e.g., "the Faitlovitch collection") are stored as **corporate agents**. The interpreter queries them via:
- `agent_norm` with `op: CONTAINS` and the collection name
- `agent_type` with `op: EQUALS` and value `corporate`
- Both Hebrew and Latin-script variants of the collection name

---

## Execution Pipeline

The full execution flow:

1. **Compile**: Natural language query -> `QueryPlan` (via LLM with schema validation)
2. **Generate SQL**: `QueryPlan` filters -> parameterized SQL against `bibliographic.db`
3. **Execute**: Run SQL, collect matching records
4. **Evidence**: For each matched record, collect which MARC fields/values caused inclusion
5. **Return**: `CandidateSet` with candidates, evidence, SQL used, and total count

### Query Execution Models

Defined in `scripts/query/models.py`:

| Model | Description |
|-------|-------------|
| `QueryWarning` | Warning from execution: code, message, field, confidence |
| `FacetCounts` | Facet aggregations: by place, year, language, publisher, century |
| `QueryOptions` | Execution options: compute_facets, facet_limit, include_warnings, limit |
| `QueryResult` | Unified result: plan, SQL, params, candidate_set, facets, warnings |

---

## Unresolved Entity Recovery (issues #3, #4)

When a `resolve_agent`/`resolve_publisher` step finds nothing, the dependent retrieve must never query the literal `$step_N` string. Instead (`scripts/chat/executor.py`):

1. **Token probes**: CONTAINS probes built from the resolve step's `query_name` and its planner-supplied variants (`ResolvedEntity.query_variants`) — a Hebrew name ("דפוס פלנטין") typically carries its only Latin-script token in the variants ("Plantin"). Generic trade words (דפוס, press, officina…) are stoplisted.
2. **Twin-field probes**: publisher↔agent_norm cross-probes (printers are catalogued as both — "Daniel Bomberg" the agent vs "daniel bomberg, venice" the publisher).
3. **Union, not first hit**: all probe hits are unioned (hard filters stay ANDed inside each probe), so a 1-record accidental match can't block a 12-record recovery.
4. **Last resort**: drop the probe, keep remaining hard filters; honest empty if nothing remains.

Every move is recorded in `RecordSet.relaxations`. Multi-value resolved bindings pass `normalize_filter_value` (comma'd canonical names like "bomberg, daniel" match the comma-stripped SQL expression). Acceptance: `tests/integration/test_unresolved_ref_recovery.py` replays the stored 2026-06-10 zero-result plans deterministically.

## Relaxation Ladder & Concept Bridge

Multi-concept queries (e.g., "art, maps and cartography") previously returned 0 records because all filters are ANDed (`scripts/query/db_adapter.py` joins every condition with `AND`) and the catalog's vocabulary rarely matches the user's concept words. Issue #2 fixed this with a **deterministic, LLM-free relaxation ladder** in the scholar-pipeline executor (`scripts/chat/executor.py`).

### Topical vs Hard Filters

`_is_topical_contains()` classifies a filter as **topical** when all of:
- field is `SUBJECT`, `TITLE`, or `PHYSICAL_DESC`
- op is `CONTAINS`
- not negated

Topical filters are *recall* constraints and may be broadened. Everything else (year, place, language, agent, negated filters, EQUALS/RANGE/IN ops) is a **hard** constraint that relaxation **never loosens** -- hard filters stay ANDed into every relaxation probe.

### The 0-Hit Ladder

`_handle_retrieve()` first runs the strict AND query via `_run_filter_query()`. Only when it returns **0 records** does `_relax_and_retry()` run:

1. **Strict AND** (already failed -- that is the trigger).
2. **Per-topic OR-union ∪ concept expansion.** For each topical filter:
   - *Direct probe* (only when there are >= 2 topical filters): run `hard filters AND this one topic` -- hits join the union.
   - *Concept expansion*: look the topic value up in the concept bridge; for each expansion, probe `hard filters AND (expanded field CONTAINS expanded value)` -- hits join the union.
   The union across topics is the result. Expansion runs **inside** this rung (per topic, alongside the direct probe) -- a separate "OR first, expand only if still 0" design would stop at noisy direct hits and never reach the expansion targets.
3. **Honest empty.** If the union is empty, return `([], [])` -- no invented results, per the hard rule on empty CandidateSets.

### `RecordSet.relaxations` -- Recorded Evidence

`RecordSet` (`scripts/chat/plan_models.py`) carries a `relaxations: list[str]` field (default empty). When the ladder fires, every broadening step is recorded as a human-readable note, e.g.:

- `Strict AND of 3 filter(s) returned 0 records; broadened to OR-union with concept expansion across 3 topic(s)`
- `'cartography' expanded to subject CONTAINS 'geography' (18 records)`
- `'art' matched 47 records on its own (OR-union)`

An empty list means no relaxation ran. This keeps the Answer Contract intact: the CandidateSet is still accompanied by evidence of exactly how it was obtained.

### Concept Bridge (`scripts/query/concept_bridge.py`)

Maps user concepts ("cartography", "מפות") to vocabulary that actually exists in this collection ("Geography", "description and travel", physical_desc "map").

- **Map file**: `data/normalization/concept_maps/concept_map.json` -- a *curated* JSON file (canonical term + aliases in English and Hebrew + expansions). No LLM involvement.
- **Validation**: every expansion term must match >= 1 record in `bibliographic.db`; this is enforced by `tests/scripts/query/test_concept_bridge.py`.
- **API**: `expand_concept(term)` does a casefolded lookup; unknown terms return `[]` (caller falls back to the literal term). A missing map file disables the bridge silently (returns `{}`), it is not an error.
- Each `Expansion` is a `(field, value)` probe where field is `subject`, `title`, or `physical_desc`.

### Scope Union (`"$step_0+$step_1"`)

`_resolve_scope()` (`scripts/chat/executor.py`) accepts, in addition to `full_collection`, `$step_N`, and `$previous_results`, a **union of step references** joined by `+`, e.g. `"$step_0+$step_1"`. The referenced steps' mms_ids are merged, deduplicated, with first-seen order preserved. This lets a `sample` (curation) step score over several retrieve steps at once.

### Acceptance Regression

`tests/integration/test_multi_topic_recall.py` is the acceptance regression for issue #2: it runs the deterministic executor (no LLM) against the real DB and asserts that even a worst-case single-step AND plan for the Hebrew query "שיעור שעוסק באמנות, מפות וקרטוגרפיה" recovers the known target records (Reland's *Palaestina* 1714, *Survey of Western Palestine*, *Bilder-Geographie* 1736) via the ladder, with relaxation notes recorded.

---

## Acceptance Tests (POC)

The system must support queries like:

- "All books published by X between 1500 and 1599"
- "All books printed in Paris in the 16th century"
- "Books on topic X" (subject headings / 6XX MARC fields)

Every query output must include:
1. **CandidateSet** -- the record IDs that match
2. **Evidence** -- which MARC fields/subfields caused each record's inclusion
3. **Normalized mapping** -- raw-to-normalized values with confidence scores

**No narrative or interpretation is allowed before the CandidateSet exists.**

---

## CLI Usage

```bash
# Execute a query (requires OPENAI_API_KEY)
python -m app.cli query "books published by Oxford between 1500 and 1599"

# With explicit database path
python -m app.cli query "all books printed in Paris in the 16th century" \
  --db data/index/bibliographic.db
```

---

## Testing

```bash
# Run query-related unit tests (no API key needed for mocked tests)
poetry run python -m pytest tests/ -k "query" -v

# Run integration tests (requires OPENAI_API_KEY)
poetry run python -m pytest tests/ --run-integration -k "query" -v
```

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | Required for query compilation (used by litellm) |
| `BIBLIOGRAPHIC_DB_PATH` | No (default: `data/index/bibliographic.db`) | SQLite database for query execution |


## Publisher resolution & recall (Soncino forensics, issue #40)

Publisher lookups are name-shaped, not controlled vocabulary. The executor
resolves them through a ladder: exact variant → exact canonical → authority
token match (now also collecting the authority's queryable imprint norms) →
**imprint substring** (full phrase, then strongest token — catches Hebrew
presses absent from `publisher_authorities`, e.g. `דפוס אליעזר שונצינו`).
A bare `publisher EQUALS` filter that matches 0 records is broadened to a
substring match as **relaxation rung 0**, recorded in `RecordSet.relaxations`;
weak resolutions (`imprint_substring`/`variant_token`) are likewise surfaced
as relaxation evidence per the Answer Contract. Multi-value EQUALS bindings
carry both normalized and raw forms because `normalize_filter_value` strips
`./&` that real `publisher_norm` values contain.
