# Query Engine
> Last verified: 2026-04-01
> Source of truth for: Query compilation (NL to SQL), LLM usage rules, query plan schema, execution pipeline, and acceptance tests

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
2. LLM output is validated against Pydantic models via OpenAI Responses API (`client.responses.parse()`).
3. If schema validation fails: return empty plan with error in debug. Never retry.
4. All LLM calls are cached to prevent redundant API usage.

---

## Query Compilation (M4/M5)

### Implementation

**File**: `scripts/query/llm_compiler.py`

The query compiler uses LLM-based parsing via OpenAI's Responses API:

- **Model**: gpt-4o (default, configurable)
- **Schema enforcement**: Pydantic models validated by OpenAI Responses API
- **Caching**: JSONL cache at `data/query_plan_cache.jsonl` (query_text -> QueryPlan)
- **API key**: Set `OPENAI_API_KEY` environment variable

### Usage

```python
from scripts.query.compile import compile_query

# With API key in environment
plan = compile_query("books published by Oxford between 1500 and 1599")

# Or pass explicitly
plan = compile_query("...", api_key="sk-...", model="gpt-4o")
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

12 supported filter fields: `PUBLISHER`, `IMPRINT_PLACE`, `COUNTRY`, `YEAR`, `LANGUAGE`, `TITLE`, `SUBJECT`, `AGENT`, `AGENT_NORM`, `AGENT_ROLE`, `AGENT_TYPE`

### FilterOp (Enum)

4 filter operations: `EQUALS`, `CONTAINS`, `RANGE`, `IN`

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
| `OPENAI_API_KEY` | Yes | Required for query compilation (LLM calls) |
| `BIBLIOGRAPHIC_DB_PATH` | No (default: `data/index/bibliographic.db`) | SQLite database for query execution |
