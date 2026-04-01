# Report 10: Empirical API Response Shape Verification

Generated: 2026-03-23
Method: Static code tracing of Pydantic models, endpoint implementations, and code paths.

---

## 1. POST /chat

### Request Shape
```json
{
  "message": "string (required, min_length=1)",
  "session_id": "string | null",
  "context": "{} (optional dict)"
}
```

### Response Wrapper: `ChatResponseAPI`
```json
{
  "success": true,
  "response": ChatResponse | null,
  "error": "string | null"
}
```

### Inner `ChatResponse` Shape
```json
{
  "message": "string",
  "candidate_set": CandidateSet | null,
  "suggested_followups": ["string", ...],
  "clarification_needed": "string | null",
  "session_id": "string",
  "phase": "query_definition" | "corpus_exploration" | null,
  "confidence": 0.0-1.0 | null,
  "metadata": {}
}
```

### Two-Phase Flow

**Phase 1 (Query Definition):**
1. Check if query is an "overview" query (e.g., "tell me about the collection"). If so, return collection stats with `phase=query_definition`, `confidence=1.0`, `metadata.overview_stats={...}`.
2. Call `interpret_query()` (LLM-based intent agent, OpenAI gpt-4o). Returns `IntentInterpretation` with `overall_confidence`, `explanation`, `uncertainties[]`, `query_plan`, and computed `proceed_to_execution`.
3. If `proceed_to_execution` is False (confidence < 0.85 AND no valid filters): return clarification. Response has `clarification_needed` set, `candidate_set=null`, `phase=query_definition`, `confidence=<low value>`, `metadata={uncertainties: [...], filters_extracted: N}`.
4. If `proceed_to_execution` is True: execute query via `QueryService.execute_plan()` with `compute_facets=True`. Builds `ChatResponse` with `candidate_set`, `phase=corpus_exploration` (if results > 0), `confidence=<interpretation confidence>`, `metadata={explanation: "...", filters_count: N}`.

**Phase 2 (Corpus Exploration):**
1. Call `interpret_exploration_request()` (LLM-based, classifies intent).
2. Route to handler based on `ExplorationIntent`:
   - `AGGREGATION`: Returns `metadata.visualization_hint` ("bar_chart", "pie_chart", etc.) and `metadata.data` (aggregation results).
   - `METADATA_QUESTION`: Returns answer text.
   - `REFINEMENT`: Returns updated counts, `metadata` contains refinement data.
   - `COMPARISON`: Returns comparison text.
   - `ENRICHMENT_REQUEST`: Calls EnrichmentService, returns Wikidata/VIAF data formatted as markdown.
   - `RECOMMENDATION`: Stub (not yet implemented).
   - `NEW_QUERY`: Transitions back to Phase 1.

### CandidateSet Shape
```json
{
  "query_text": "string",
  "plan_hash": "string (SHA256)",
  "sql": "string (exact SQL executed)",
  "sql_parameters": {},
  "generated_at": "ISO 8601 string",
  "candidates": [Candidate, ...],
  "total_count": 0
}
```

### Candidate Shape
```json
{
  "record_id": "string (MMS ID)",
  "match_rationale": "string (template-generated)",
  "evidence": [Evidence, ...],
  "title": "string | null",
  "author": "string | null",
  "date_start": int | null,
  "date_end": int | null,
  "place_norm": "string | null",
  "place_raw": "string | null",
  "publisher": "string | null",
  "subjects": ["string", ...],
  "description": "string | null"
}
```

### Evidence Shape
```json
{
  "field": "string (e.g., 'publisher_norm', 'date_start')",
  "value": "any (record's matched value, often null per pipeline findings)",
  "operator": "string ('=', 'BETWEEN', 'LIKE', 'OVERLAPS')",
  "matched_against": "any (plan value(s))",
  "source": "string (e.g., 'db.imprints.publisher_norm', 'marc:264$b')",
  "confidence": float | null (0.0-1.0),
  "extraction_error": "string | null"
}
```

### QueryPlan Shape (stored in session messages, NOT directly in ChatResponse)
```json
{
  "version": "1.0",
  "query_text": "string",
  "filters": [Filter, ...],
  "soft_filters": [Filter, ...],
  "limit": int | null,
  "debug": {}
}
```

### Filter Shape
```json
{
  "field": "publisher|imprint_place|country|year|language|title|subject|agent|agent_norm|agent_role|agent_type",
  "op": "EQUALS|CONTAINS|RANGE|IN",
  "value": "string | [string] | null",
  "start": int | null,
  "end": int | null,
  "negate": false,
  "confidence": float | null,
  "notes": "string | null"
}
```

**Key finding:** Filter `confidence` is present in the schema but the prior pipeline probe confirmed it is always `null` in practice (LLM does not reliably set it).

---

## 2. WS /ws/chat

### Message Types

**session_created:**
```json
{"type": "session_created", "session_id": "uuid"}
```

**progress:**
```json
{"type": "progress", "message": "Compiling query..."}
{"type": "progress", "message": "Executing query with N filters..."}
{"type": "progress", "message": "Found X results. Formatting response..."}
```

**batch:**
```json
{
  "type": "batch",
  "candidates": [Candidate.model_dump(), ...],
  "batch_num": 1,
  "total_batches": 3,
  "start_idx": 0,
  "end_idx": 10
}
```

**complete:**
```json
{
  "type": "complete",
  "response": ChatResponse.model_dump()
}
```

**error:**
```json
{"type": "error", "message": "string"}
```

**Important difference from POST /chat:**
- WebSocket does NOT use the intent agent (Phase 1/2 architecture). It uses the simpler `compile_query()` path directly.
- WebSocket does NOT compute facets (`compute_facets=False`).
- WebSocket does NOT set `phase` or `confidence` on the ChatResponse.
- WebSocket uses the `format_for_chat()` text formatter for the `message` field.
- POST /chat uses `format_interpretation_for_user()` for the `message` field.

---

## 3. GET /health

```json
{
  "status": "healthy|degraded|unhealthy",
  "database_connected": true|false,
  "session_store_ok": true|false
}
```

---

## 4. GET /metadata/coverage

```json
{
  "date_coverage": FieldCoverageResponse,
  "place_coverage": FieldCoverageResponse,
  "publisher_coverage": FieldCoverageResponse,
  "agent_name_coverage": FieldCoverageResponse,
  "agent_role_coverage": FieldCoverageResponse,
  "total_imprint_rows": int,
  "total_agent_rows": int
}
```

Each `FieldCoverageResponse`:
```json
{
  "total_records": int,
  "non_null_count": int,
  "null_count": int,
  "confidence_distribution": [
    {"band_label": "0.00", "lower": 0.0, "upper": 0.1, "count": int},
    ...
  ],
  "method_distribution": [
    {"method": "string", "count": int},
    ...
  ],
  "flagged_items": [
    {
      "raw_value": "string",
      "norm_value": "string|null",
      "confidence": float,
      "method": "string|null",
      "frequency": int
    },
    ...
  ]
}
```

---

## 5. GET /metadata/issues

Query params: `field` (required: date|place|publisher|agent), `max_confidence` (default 0.8), `limit` (default 50), `offset` (default 0).

```json
{
  "field": "string",
  "max_confidence": float,
  "total": int,
  "limit": int,
  "offset": int,
  "items": [
    {
      "mms_id": "string",
      "raw_value": "string",
      "norm_value": "string|null",
      "confidence": float,
      "method": "string|null"
    },
    ...
  ]
}
```

---

## 6. GET /metadata/unmapped

Query params: `field` (required), `sort` (default "frequency").

Returns: `List[UnmappedValue]` (bare array, not paginated)
```json
[
  {
    "raw_value": "string",
    "frequency": int,
    "confidence": float,
    "method": "string|null"
  },
  ...
]
```

---

## 7. GET /metadata/methods

Query params: `field` (required).

Returns: `List[MethodDistribution]` (bare array)
```json
[
  {"method": "string", "count": int, "percentage": float},
  ...
]
```

---

## 8. GET /metadata/clusters

Query params: `field` (optional; omit for all fields).

Returns: `List[ClusterResponse]` (bare array)
```json
[
  {
    "cluster_id": "string",
    "field": "string",
    "cluster_type": "string",
    "values": [
      {"raw_value": "string", "frequency": int, "confidence": float, "method": "string"},
      ...
    ],
    "proposed_canonical": "string|null",
    "evidence": {},
    "priority_score": float,
    "total_records_affected": int
  },
  ...
]
```

---

## 9. POST /metadata/corrections

Request:
```json
{
  "field": "place|publisher|agent",
  "raw_value": "string",
  "canonical_value": "string",
  "evidence": "" (optional),
  "source": "human" (default)
}
```

Response:
```json
{
  "success": true,
  "alias_map_updated": "data/normalization/.../map.json",
  "records_affected": int
}
```

---

## 10. POST /metadata/corrections/batch

Request:
```json
{
  "corrections": [CorrectionRequest, ...]
}
```

Response:
```json
{
  "total_applied": int,
  "total_skipped": int,
  "total_records_affected": int,
  "results": [
    {
      "raw_value": "string",
      "canonical_value": "string",
      "success": true|false,
      "records_affected": int,
      "error": "string|null"
    },
    ...
  ]
}
```

---

## 11. GET /metadata/corrections/history

Query params: `field` (optional), `limit` (default 100), `offset` (default 0).

```json
{
  "total": int,
  "limit": int,
  "offset": int,
  "entries": [
    {
      "timestamp": "ISO 8601",
      "field": "string",
      "raw_value": "string",
      "canonical_value": "string",
      "evidence": "string",
      "source": "human|agent",
      "action": "approved"
    },
    ...
  ]
}
```

---

## 12. POST /metadata/agent/chat

Request:
```json
{
  "field": "place|date|publisher|agent",
  "message": "string (empty or 'analyze' triggers analysis)",
  "session_id": "string|null"
}
```

Response:
```json
{
  "response": "string (natural language)",
  "proposals": [
    {
      "raw_value": "string",
      "canonical_value": "string",
      "confidence": float,
      "reasoning": "string",
      "evidence_sources": ["string", ...]
    },
    ...
  ],
  "clusters": [
    {
      "cluster_id": "string",
      "cluster_type": "string",
      "value_count": int,
      "total_records": int,
      "priority_score": float
    },
    ...
  ],
  "field": "string",
  "action": "analysis|proposals|answer"
}
```

Routing logic:
- Empty message or "analyze" -> `action: "analysis"` with clusters summary
- "propose:<cluster_ref>" -> `action: "proposals"` with LLM-generated proposals
- "cluster:<cluster_ref>" -> `action: "answer"` with cluster detail
- Any other text -> `action: "answer"` with grounding-based gap summary

---

## 13. GET /metadata/publishers

Query params: `type` (optional: printing_house|private_press|modern_publisher|bibliophile_society|unknown_marker|unresearched).

```json
{
  "total": int,
  "items": [
    {
      "id": int,
      "canonical_name": "string",
      "type": "string",
      "confidence": float,
      "dates_active": "string|null",
      "location": "string|null",
      "is_missing_marker": true|false,
      "variant_count": int,
      "imprint_count": int,
      "variants": [
        {
          "variant_form": "string",
          "script": "latin|hebrew|arabic|other",
          "language": "string|null",
          "is_primary": true|false
        },
        ...
      ],
      "viaf_id": "string|null",
      "wikidata_id": "string|null",
      "cerl_id": "string|null"
    },
    ...
  ]
}
```

---

## 14. POST /metadata/primo-urls

Request:
```json
{
  "mms_ids": ["string", ...],
  "base_url": "string|null"
}
```

Response:
```json
{
  "urls": [
    {"mms_id": "string", "primo_url": "string"},
    ...
  ]
}
```

---

## 15. GET /metadata/records/{mms_id}/primo

Response:
```json
{
  "mms_id": "string",
  "primo_url": "string"
}
```

---

## 16. GET /sessions/{session_id}

Returns raw `ChatSession.model_dump()`:
```json
{
  "session_id": "uuid",
  "user_id": "string|null",
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601",
  "messages": [
    {
      "role": "user|assistant|system",
      "content": "string",
      "query_plan": QueryPlan|null,
      "candidate_set": CandidateSet|null,
      "timestamp": "ISO 8601"
    },
    ...
  ],
  "context": {},
  "metadata": {}
}
```

---

## 17. DELETE /sessions/{session_id}

Response:
```json
{"status": "success", "message": "Session <id> expired"}
```

---

## Critical Analysis

### Does the API provide filter confidence?
**Partially.** The `Filter.confidence` field exists in the schema (Optional[float]) and is passed through from the LLM's `IntentInterpretationLLM` output. However, the prior pipeline probe confirmed LLM almost always returns `null` for per-filter confidence. The overall `IntentInterpretation.overall_confidence` IS reliably populated and passed to `ChatResponse.confidence`.

### Does the API expose execution timing?
**No, not to the frontend.** `QueryResult.execution_time_ms` is computed by `QueryService` but is NOT included in `ChatResponse` or `ChatResponseAPI`. It is only logged internally.

### Does the API return the query plan to the frontend?
**Not directly in the chat response.** The `ChatResponse` model does NOT include a `query_plan` field. However:
- The `CandidateSet.sql` field exposes the exact SQL executed.
- The `Message` objects stored in the session DO contain `query_plan`.
- The `GET /sessions/{session_id}` endpoint returns messages with `query_plan` attached.
- The `ChatResponse.metadata` dict can contain `filters_count` and `explanation`.

### What fields exist on Candidate that the UI could display?
Full list: `record_id`, `match_rationale`, `evidence[]`, `title`, `author`, `date_start`, `date_end`, `place_norm`, `place_raw`, `publisher`, `subjects[]`, `description`.

### Facets
Facets (`FacetCounts`) are computed by `QueryService.execute_plan()` when `compute_facets=True`. In POST /chat, this is enabled. However, facets are NOT passed through to `ChatResponse` -- they remain inside `QueryResult` which is not serialized to the response. The only place facets could surface is if they were added to `ChatResponse.metadata`, which does not happen currently.

### WebSocket vs HTTP parity gap
The WebSocket endpoint is significantly simpler than POST /chat:
- No intent agent (uses `compile_query()` directly)
- No Phase 1/Phase 2 conversation
- No facet computation
- No `confidence` or `phase` in response
- Uses text formatter rather than interpretation formatter

---

## Endpoint Shapes Summary Table

| Endpoint | Response Model | Paginated | Notes |
|----------|---------------|-----------|-------|
| POST /chat | ChatResponseAPI | No | Wraps ChatResponse |
| WS /ws/chat | streaming JSON | N/A | 5 message types |
| GET /health | HealthResponse | No | 3 fields |
| GET /metadata/coverage | CoverageResponse | No | 5 field coverages + totals |
| GET /metadata/issues | IssuesResponse | Yes | limit/offset |
| GET /metadata/unmapped | List[UnmappedValue] | No | Bare array |
| GET /metadata/methods | List[MethodDistribution] | No | Bare array |
| GET /metadata/clusters | List[ClusterResponse] | No | Bare array |
| POST /metadata/corrections | CorrectionResponse | No | Single correction |
| POST /metadata/corrections/batch | BatchCorrectionResponse | No | Batch with per-item results |
| GET /metadata/corrections/history | CorrectionHistoryResponse | Yes | limit/offset |
| POST /metadata/agent/chat | AgentChatResponse | No | Proposals + clusters |
| GET /metadata/publishers | PublisherAuthorityListResponse | No | Has total + items |
| POST /metadata/primo-urls | PrimoUrlResponse | No | Batch URL generation |
| GET /metadata/records/{id}/primo | PrimoUrlEntry | No | Single URL |
| GET /sessions/{id} | ChatSession (raw dict) | No | Full session with messages |
| DELETE /sessions/{id} | dict | No | Ad-hoc JSON |
