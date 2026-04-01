# Report 09: Empirical Pipeline Test

**Date**: 2026-03-23
**Phase**: 2 -- End-to-end query pipeline execution with real data
**Method**: Executed 9 real queries via CLI (`python -m app.cli query`) and Python API (`QueryService.execute`)

---

## 1. Test Environment

| Property | Value |
|----------|-------|
| Database | `data/index/bibliographic.db` (2,796 records) |
| Query compiler | gpt-4o via OpenAI Responses API |
| Cache | `data/query_plan_cache.jsonl` (6 entries pre-test, 15 post-test) |
| Artifacts | 3 files per run: `plan.json`, `sql.txt`, `candidates.json` |

---

## 2. Core Query Results

### Query 1: "books published in Amsterdam"
- **Result count**: 196 (matches expected from DB probe)
- **Filters**: 1 -- `imprint_place EQUALS "amsterdam"`
- **SQL**: `WHERE LOWER(i.place_norm) = LOWER(:filter_0_place)`
- **Evidence per candidate**: 1 evidence object with `field=place_norm, operator="=", confidence=0.95`
- **Execution time**: 3,397ms (includes LLM compilation)
- **Issues**: None

### Query 2: "books from the 16th century"
- **Result count**: 217
- **Filters**: 1 -- `year RANGE 1501-1600`
- **SQL**: `WHERE (i.date_end >= :filter_0_year_start AND i.date_start <= :filter_0_year_end)`
- **Evidence per candidate**: 1 evidence object with overlap rationale (e.g., `year_range=1590-1590 overlaps 1501-1600`)
- **Execution time**: 3,139ms
- **Issues**: None

### Query 3: "Hebrew books printed in Venice"
- **Result count**: 100
- **Filters**: 2 -- `language EQUALS "heb"` + `imprint_place EQUALS "venice"`
- **SQL**: Joins `records`, `imprints`, `languages` with `WHERE l.code = :filter_0_lang AND LOWER(i.place_norm) = LOWER(:filter_1_place)`
- **Evidence per candidate**: 2 evidence objects (language + place)
- **Execution time**: 3,720ms
- **Issues**: None

### Query 4: "books about medicine"
- **Result count**: 15
- **Filters**: 1 -- `subject CONTAINS "Medicine"`
- **SQL**: Uses FTS5 `subjects_fts MATCH :filter_0_subject`
- **Evidence per candidate**: 1 evidence object -- but **`value` field is `null`** (only `matched_against` is populated)
- **Execution time**: 3,384ms
- **Issues**: Subject evidence missing actual matched value from DB (see Issue #1)

### Query 5: "books published by Elsevier"
- **Result count**: 1
- **Filters**: 1 -- `publisher CONTAINS "elsevier"`
- **SQL**: `WHERE LOWER(i.publisher_norm) LIKE LOWER(:filter_0_publisher)`
- **Evidence**: `publisher_norm="officina j. & d. elsevier"` matched via LIKE
- **Execution time**: 2,157ms
- **Issues**: Only 1 of 16 Elzevir-family records matched (see Issue #2)

### Query 6: "Hebrew books printed in Amsterdam in the 17th century"
- **Result count**: 46
- **Filters**: 3 -- `language EQUALS "heb"` + `imprint_place EQUALS "amsterdam"` + `year RANGE 1601-1700`
- **SQL**: Triple-join with language, place, and date range conditions
- **Evidence per candidate**: 3 evidence objects (language + place + date)
- **Execution time**: 3,378ms
- **Issues**: None -- demonstrates correct multi-filter AND composition

### Query 7: "books by Maimonides"
- **Result count**: 7
- **Filters**: 1 -- `agent_norm CONTAINS "maimonides"`
- **SQL**: `WHERE LOWER(REPLACE(a.agent_norm, ',', '')) LIKE LOWER(:filter_0_agent_norm)`
- **Evidence**: `agent_norm="maimonides, moses"`, confidence=0.80
- **Execution time**: 3,839ms
- **Issues**: Agent evidence source shows `marc:unknown` instead of actual MARC tag (see Issue #3)

---

## 3. Edge Case Results

### Edge Case 1: "books about quantum physics" (expected zero results)
- **Result count**: 67 (NOT zero!)
- **Behavior**: Initial subject filter `"Quantum physics"` returned 0 results. The retry mechanism activated `compile_query_with_subject_hints()`, which re-compiled with top-100 database subjects as hints. The LLM mapped "quantum physics" to "Philosophy", returning 67 philosophy books including Kant's *Critique of Pure Reason*.
- **Issue**: **False broadening** -- the retry remapped an inapplicable subject to a loosely related one. This is a significant precision problem (see Issue #4).

### Edge Case 2: "books" (very broad query)
- **Result count**: 2,796 (all records)
- **Behavior**: LLM correctly produced zero filters. SQL becomes `WHERE 1=1`. All records returned with empty evidence lists.
- **Warning**: `[EMPTY_FILTERS] Query produced no specific filters. Try adding date ranges, places, or subjects.`
- **Issue**: Warning is generated correctly. However, candidates have `match_rationale="matched"` and `evidence=[]`, which violates the project's evidence contract (see Issue #5).

### Edge Case 3: "Venice" (ambiguous single word)
- **Result count**: 164 (matches expected from DB probe)
- **Behavior**: LLM correctly interpreted as `imprint_place EQUALS "venice"`. No ambiguity warning generated despite "Venice" being potentially a subject or title term.
- **Issue**: No warning for ambiguous single-word queries (see Issue #6).

---

## 4. Structure Findings

### CandidateSet Shape
```
CandidateSet (Pydantic BaseModel):
├── query_text: str
├── plan_hash: str (SHA256)
├── sql: str
├── sql_parameters: Dict[str, Any]
├── generated_at: str (ISO 8601)
├── candidates: List[Candidate]
└── total_count: int
```

### Candidate Shape
```
Candidate (Pydantic BaseModel):
├── record_id: str (MMS ID)
├── match_rationale: str (template-generated, e.g., "place_norm='amsterdam'")
├── evidence: List[Evidence]
├── title: Optional[str]
├── author: Optional[str]
├── date_start: Optional[int]
├── date_end: Optional[int]
├── place_norm: Optional[str]
├── place_raw: Optional[str]
├── publisher: Optional[str]
├── subjects: List[str] (first 3)
└── description: Optional[str]
```

### Evidence Shape
```
Evidence (Pydantic BaseModel):
├── field: str (e.g., "place_norm", "publisher_norm", "subject_value")
├── value: Any (actual DB value that matched, or null for subjects)
├── operator: str (e.g., "=", "LIKE", "MATCH", "OVERLAPS")
├── matched_against: Any (filter value from QueryPlan)
├── source: str (e.g., "db.imprints.place_norm (marc:260)")
├── confidence: Optional[float]
└── extraction_error: Optional[str]
```

### QueryPlan Shape
```
QueryPlan (Pydantic BaseModel):
├── version: str
├── query_text: str
├── filters: List[Filter]
│   ├── field: FilterField enum (publisher, imprint_place, year, language, subject, agent_norm, etc.)
│   ├── op: FilterOp enum (EQUALS, CONTAINS, RANGE, IN)
│   ├── value: Optional[str | List[str]]
│   ├── start/end: Optional[int] (for RANGE)
│   ├── negate: bool
│   ├── confidence: Optional[float]
│   └── notes: Optional[str]
├── soft_filters: List[Filter]
├── limit: Optional[int]
└── debug: Dict (parser, model, filters_count, cache_hit)
```

### Artifact Files Per Run
Each query execution creates a directory `data/runs/query_YYYYMMDD_HHMMSS/` containing:
1. **`plan.json`** -- The QueryPlan as JSON (filters, operations, debug metadata)
2. **`sql.txt`** -- The exact SQL query executed (parameterized)
3. **`candidates.json`** -- Full CandidateSet with all candidates, evidence, and metadata

---

## 5. QueryService API (Python)

The `QueryService` class provides a unified interface:

```python
from scripts.query.service import QueryService
from scripts.query.models import QueryOptions, QueryResult

service = QueryService(Path("data/index/bibliographic.db"))
result: QueryResult = service.execute("books in Amsterdam", options=QueryOptions(compute_facets=True))

# QueryResult contains:
# - query_plan: QueryPlan
# - sql: str
# - params: List[Any]
# - candidate_set: CandidateSet
# - facets: Optional[FacetCounts] (by_place, by_year, by_language, by_publisher, by_century)
# - warnings: List[QueryWarning]
# - execution_time_ms: float
```

Facets example for Amsterdam query:
- `by_place`: `{"amsterdam": 196}`
- `by_century`: `{"16th century": 2, "17th century": 82, "18th century": 101, ...}`
- `by_language`: `{"heb": 115, "lat": 38, "dut": 19, "fre": 17, "yid": 12}`

---

## 6. Query Plan Cache

- **File**: `data/query_plan_cache.jsonl`
- **Format**: One JSON object per line with `query_text`, `plan`, `model`, `timestamp`
- **Behavior**: Cache hit returns immediately (no API call). Cache miss calls LLM and appends to file.
- **Pre-test**: 6 entries
- **Post-test**: 15 entries (9 new queries cached)
- **Cache hit observed**: "books published in Amsterdam" on second execution via Python API showed `cache_hit: true`

---

## 7. Issues Found

### Issue #1: Subject evidence `value` is always null
**Severity**: Medium
**Location**: `scripts/query/execute.py` evidence extraction for subject filters
**Description**: When a subject filter matches via FTS5, the Evidence object has `value: null` and only `matched_against` is populated. The actual subject heading from the database that matched is not captured. This weakens the evidence chain.
**Example**: Medicine query evidence shows `{"field": "subject_value", "value": null, "matched_against": "Medicine"}` but doesn't show which specific subject heading matched (e.g., "Medicine, Greek and Roman -- Sources").

### Issue #2: Publisher variant matching misses historical name forms
**Severity**: High
**Location**: Publisher normalization layer / publisher authority system
**Description**: Query "books published by Elsevier" matched only 1 of 16 Elzevir-family records. The database contains:
- `house of elzevir` (9 records) -- pre-normalized via publisher authorities
- `apud danielem elzevirivm` (1 record)
- `ex officina elseviriana` (1 record)
- `typis l. elzevirii` (1 record)
- etc.
The CONTAINS filter `LIKE '%elsevier%'` only matched the one record with the modern spelling "Elsevier" in its `publisher_norm`. The publisher authority system maps many of these to "house of elzevir" but the query doesn't know to search for "elzevir" as well.
**Impact**: Users searching modern publisher names may miss most historical records.

### Issue #3: Agent evidence source shows `marc:unknown`
**Severity**: Low
**Location**: `scripts/query/execute.py` evidence extraction for agent filters
**Description**: Agent evidence objects show `source: "db.agents.agent_norm (marc:unknown)"` instead of the actual MARC tag (100, 700, etc.). The MARC provenance is likely available in the `provenance_json` column but isn't propagated to evidence.

### Issue #4: Subject retry produces false broadening
**Severity**: High
**Location**: `scripts/query/execute.py` `should_retry_with_subject_hints()` + `scripts/query/llm_compiler.py` `compile_query_with_subject_hints()`
**Description**: When a subject filter returns zero results, the system retries by providing the LLM with the top-100 actual subjects from the database and asking it to remap. For "quantum physics", the LLM chose "Philosophy" as the closest match, returning 67 unrelated records. This is a precision-harming false broadening.
**Recommendation**: Either (a) don't retry when no plausible mapping exists, (b) add a confidence threshold to the retry mapping, or (c) return zero results with a suggestion message instead of silently broadening.

### Issue #5: Empty-filter queries produce evidence-less candidates
**Severity**: Low
**Location**: Query execution for plans with zero filters
**Description**: When a query like "books" produces no filters, all 2,796 records are returned with `evidence: []` and `match_rationale: "matched"`. This technically violates the project's evidence contract ("Every candidate must include evidence showing which fields matched").
**Recommendation**: Either return an error/clarification instead of executing, or add a synthetic evidence entry like `{"field": "unfiltered", "value": "all records", ...}`.

### Issue #6: No ambiguity warning for single-word queries
**Severity**: Low
**Location**: `scripts/query/service.py` warning extraction
**Description**: Single-word queries like "Venice" are interpreted without ambiguity warning. The LLM happens to interpret "Venice" as a place, which is reasonable but not certain -- it could refer to books *about* Venice (subject) or books with "Venice" in the title.
**Recommendation**: Add a `VAGUE_QUERY` warning for single-word queries so the user knows the interpretation.

### Issue #7: Confidence field always null in QueryPlan filters
**Severity**: Medium
**Location**: `scripts/query/llm_compiler.py` (LLM system prompt)
**Description**: All filter objects in the QueryPlan have `confidence: null`. The LLM is not being asked to produce confidence scores for its filter interpretations. This means the warning system's `LOW_CONFIDENCE` check can never fire.
**Recommendation**: Update the LLM system prompt to request confidence scores, or compute them heuristically based on query clarity.

---

## 8. Pipeline Performance Summary

| Query | Filters | Results | LLM Time (ms) | SQL Time (ms) | Total (ms) |
|-------|---------|---------|---------------|----------------|------------|
| Amsterdam | 1 (place) | 196 | ~3,000 | ~400 | 3,398 |
| 16th century | 1 (year) | 217 | ~3,000 | ~140 | 3,139 |
| Hebrew + Venice | 2 (lang+place) | 100 | ~3,500 | ~220 | 3,720 |
| Medicine | 1 (subject) | 15 | ~3,000 | ~380 | 3,384 |
| Elsevier | 1 (publisher) | 1 | ~2,000 | ~160 | 2,157 |
| Quantum physics | 1 (subject) | 67 | ~7,000 (retry) | ~580 | 7,576 |
| Books (empty) | 0 | 2,796 | 0 (cache) | ~150 | 152 |
| Venice | 1 (place) | 164 | ~1,500 | ~360 | 1,859 |
| Heb+Ams+17c | 3 (lang+place+year) | 46 | ~3,000 | ~380 | 3,379 |
| Maimonides | 1 (agent) | 7 | ~3,500 | ~340 | 3,839 |

- LLM compilation dominates execution time (2-4 seconds per fresh query)
- Cache hits eliminate LLM time entirely (152ms for cached "books" query)
- SQL execution is consistently fast (<600ms even for full-table scans)

---

## 9. Overall Assessment

**What works well:**
- Place, date, and language filters are reliable and produce correct results
- Multi-filter AND composition works correctly (Hebrew + Amsterdam + 17th century)
- Evidence structure is well-designed and provides MARC field traceability
- Artifact system (plan.json, sql.txt, candidates.json) provides full reproducibility
- Cache system works correctly for repeated queries
- Warning system correctly identifies empty-filter queries
- Facet computation provides useful breakdowns

**What needs improvement:**
- Publisher variant matching is the most significant gap (Elsevier/Elzevir problem)
- Subject retry can produce false broadening (quantum physics -> Philosophy)
- Subject evidence is incomplete (null values)
- Confidence scores are never populated in QueryPlans
- Agent evidence source is not traced to specific MARC tags
