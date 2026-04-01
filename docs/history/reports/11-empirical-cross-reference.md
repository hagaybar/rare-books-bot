# Report 11: Empirical Cross-Reference -- UI Screens vs. Actual Data

**Date**: 2026-03-23
**Method**: Cross-referencing empirical findings from Reports 08 (DB Probe), 09 (Pipeline Test), and 10 (API Verify) against the 9 proposed UI screens from Report 06 (New UI Definition).

---

## Rating Scale

| Rating | Definition |
|--------|-----------|
| **CONFIRMED** | All major assumptions hold. Screen can be built as specified. |
| **PARTIALLY_ALIGNED** | Core concept is sound but specific features assume data/APIs that don't exist or behave differently. Requires design adjustments. |
| **MISALIGNED** | Fundamental assumptions are wrong. Screen needs significant redesign or re-scoping. |

---

## Screen 1: Chat (Landing Page) -- `/`

**Rating: PARTIALLY_ALIGNED**

### What Was Assumed
1. Two-phase flow visualization (Phase 1: query definition with interpretation confidence; Phase 2: corpus exploration with aggregation/comparison)
2. WebSocket streaming with phase support
3. Per-filter confidence scores displayed to user
4. Execution timing shown in collapsible panel
5. Inline evidence panel per result with MARC citations and confidence
6. Follow-up suggestion chips
7. Primo URLs linked from candidate titles

### What Is Actually True
1. Two-phase flow EXISTS in `POST /chat` (Phase 1 with intent agent, Phase 2 with exploration agent). `ChatResponse` has `phase` and `confidence` fields. Phase 2 supports AGGREGATION, METADATA_QUESTION, REFINEMENT, COMPARISON, ENRICHMENT_REQUEST, and NEW_QUERY intents. `visualization_hint` is provided (bar_chart, pie_chart, table).
2. WebSocket does NOT support two-phase flow. It uses the old single-phase `compile_query()` path. No phase indicator, no confidence, no facets. This is a significant gap for streaming UX.
3. Per-filter confidence is always `null`. The LLM does not set `Filter.confidence`. Only `ChatResponse.confidence` (overall interpretation confidence) is reliably populated.
4. `execution_time_ms` is computed by `QueryService` but NOT exposed in `ChatResponse`. It is logged internally only.
5. Evidence objects are well-structured with `field`, `value`, `operator`, `matched_against`, `source`, `confidence`. However: subject evidence `value` is always `null`; agent evidence `source` shows "marc:unknown" instead of actual MARC tags.
6. `suggested_followups` is populated in `ChatResponse`. Confirmed working.
7. Primo URLs require a separate API call (`GET /metadata/records/{mms_id}/primo` or `POST /metadata/primo-urls`). They are NOT on the `Candidate` object.

### Gaps
- **WebSocket must be updated** to use two-phase flow before streaming can show phase transitions. Currently, using WebSocket means losing all Phase 1/2 features.
- **Per-filter confidence display is empty**: The spec shows "confidence per filter" in the query insight panel but all filters have `confidence: null`. Only overall confidence is available.
- **Execution timing not available**: The spec calls for "Query compilation time, SQL execution time, Total response time" but none of these are exposed to the frontend.
- **Primo URLs not inline**: Each candidate card linking to Primo requires a separate API call for URL construction, adding N+1 request overhead or requiring a batch call.
- **FacetCounts computed but discarded**: POST /chat computes facets (by_place, by_year, by_language, by_publisher, by_century) but does not include them in `ChatResponse`. The aggregation data for Phase 2 bar charts exists but cannot reach the frontend via the current response shape.

### Recommendations
1. Expose `execution_time_ms` in `ChatResponse.metadata` (small API change).
2. Forward `FacetCounts` in `ChatResponse.metadata` when available.
3. Update WebSocket handler to use intent agent + two-phase flow, or document that WebSocket is streaming-only for Phase 1 initial results, with HTTP for Phase 2 exploration.
4. Remove per-filter confidence from the UI design or compute it heuristically (the LLM won't reliably provide it).
5. Add `primo_url` field to `Candidate` model to avoid N+1 requests, or batch-resolve on the frontend.

---

## Screen 2: Coverage Dashboard -- `/operator/coverage`

**Rating: PARTIALLY_ALIGNED**

### What Was Assumed
1. Per-field coverage bars with confidence band coloring (high/medium/low/very_low)
2. Four confidence bands with meaningful distribution across them
3. Gap summary cards per field showing null count + flagged count (implying significant numbers)
4. Method distribution pie charts with field selector
5. Trend over time (quality score history)
6. Coverage comparison before/after correction batches
7. Drill-through from any coverage metric to relevant records

### What Is Actually True
1. `GET /metadata/coverage` returns `FieldCoverageResponse` for each of 5 fields (date, place, publisher, agent_name, agent_role), with `confidence_distribution` (10 bands from 0.0-1.0 in 0.1 increments), `method_distribution`, and `flagged_items`.
2. **Confidence is BINARY, not graduated.** Place: 19 records at <0.5, 2,754 at >=0.95. Publisher: 33 at <0.5, 2,740 at >=0.95. The "medium" and "low" confidence bands (0.5-0.95) are EMPTY for place and publisher. Date has records in 0.8-0.95 (gematria, embedded) and 0.95-1.0, but still nothing in 0.5-0.8.
3. Issues count is very small: 69 dates + 19 places + 33 publishers = 121 total low-confidence records. The "Issues Workbench" will have very few items to show. Gap cards will display small numbers.
4. Method distribution is extremely skewed: Place has only 2 methods (place_alias_map 99.3%, missing 0.7%). Publisher similarly dominated. Date has 12 methods but is well-distributed.
5. No historical snapshot mechanism exists. Trend over time requires infrastructure that doesn't exist.
6. No before/after correction tracking API exists.
7. Drill-through requires linking to the Issues Workbench with filter parameters. The workbench endpoint (`GET /metadata/issues`) supports `field` and `max_confidence` params, so this is feasible.

### Gaps
- **Four-band confidence visualization is misleading**: The dashboard design assumes a graduated distribution (green/yellow/orange/red). In reality, for place and publisher, the bars will show 99%+ green and a tiny red sliver. The "medium" and "low" bands will be empty. This doesn't add visual value and may make the dashboard look unfinished.
- **Trend over time is not buildable**: No snapshot history exists in the database.
- **Agent coverage is the real problem area**: 100% of agents use base_clean only, 44.1% of roles are "other". This should be the LEAD story on the dashboard, not date/place/publisher which are already >97% covered.

### Recommendations
1. Redesign confidence visualization for binary reality: use a simple "resolved/unresolved" split instead of four bands for place and publisher. Keep graduated bands only for dates (where there IS a 0.8-0.95 segment).
2. Highlight agent normalization as the primary gap (0% alias-mapped, 44.1% uncategorized roles).
3. Feature the 553 Hebrew-script publishers as a distinct coverage gap category (technically 0.95 confidence but functionally unnormalized for cross-lingual search).
4. Drop "trend over time" from initial scope or add a periodic snapshot job first.

---

## Screen 3: Issues Workbench -- `/operator/workbench`

**Rating: PARTIALLY_ALIGNED**

### What Was Assumed
1. Substantial number of issues to browse and resolve
2. Confidence slider filter + method dropdown
3. Inline editable cells for normalized values
4. Batch correction with preview
5. Cluster view with expandable cluster cards
6. Side-by-side raw/normalized comparison
7. Integration with Agent Chat

### What Is Actually True
1. **Very few actual "issues"**: 69 low-confidence dates + 19 places + 33 publishers = 121 total. The workbench will be nearly empty for three fields.
2. API supports `max_confidence` filter and `method` via `GET /metadata/issues`. Confidence slider will work but the range 0.5-0.95 is empty -- sliding to any value in that range returns 0 results.
3. Corrections API (`POST /metadata/corrections`, `POST /metadata/corrections/batch`) exists and works.
4. `GET /metadata/clusters` returns clusters with `priority_score` and `total_records_affected`.
5. `IssueRecord` has `mms_id`, `raw_value`, `norm_value`, `confidence`, `method` -- supports side-by-side display.

### Gaps
- **The real issue isn't low confidence -- it's MISSING normalization types.** The 553 Hebrew-script publishers have 0.95 confidence but are NOT actually normalized for cross-lingual querying. The 4,366 agents with base_clean only are a massive gap. Neither shows up as "issues" because they don't have low confidence scores.
- **Confidence slider is deceptive**: Moving it from 0.5 to 0.95 will show 0 results for place and publisher. Only values <0.5 or >=0.95 exist.
- **Correction for "date" field isn't supported**: `CorrectionRequest.field` accepts only `place|publisher|agent`. Date corrections need a different mechanism.

### Recommendations
1. Add a "Hebrew-script publishers" filter or tab that surfaces the 553 un-transliterated publishers regardless of confidence score.
2. Add an "Agent normalization" tab that highlights the 4,366 agents with base_clean method as an upgrade opportunity.
3. Replace or supplement the confidence slider with a method-based filter (e.g., "base_clean only" vs "alias_map").
4. Consider whether the workbench should reframe from "issues" (low confidence) to "improvement opportunities" (un-normalized, Hebrew-script, uncategorized roles).

---

## Screen 4: Agent Chat -- `/operator/agent`

**Rating: CONFIRMED**

### What Was Assumed
1. Field-specific agent selection (Place, Date, Publisher, Agent)
2. Conversational interface with proposals
3. Proposal tables with Approve/Reject/Edit
4. Cluster summary cards
5. Coverage sidebar showing real-time field health
6. Correction preview before commit

### What Is Actually True
1. `POST /metadata/agent/chat` accepts `field` (place|date|publisher|agent) and routes to the correct specialist agent.
2. Response includes `response` (natural language), `proposals[]`, `clusters[]`, `field`, `action`.
3. Each proposal has `raw_value`, `canonical_value`, `confidence`, `reasoning`, `evidence_sources`.
4. Clusters have `cluster_id`, `cluster_type`, `value_count`, `total_records`, `priority_score`.
5. Coverage is available via `GET /metadata/coverage` -- can be queried in sidebar.
6. Corrections go through `POST /metadata/corrections` which returns `records_affected`.

### Gaps
- Minor: The specialist agents work against the database directly, not against a cached representation. For the agent tab, 89% of publisher authorities are "unresearched" stubs, so the PublisherAgent may not have rich authority data to reference.
- The `authority_enrichment` table is empty (0 rows), so agent proposals for publishers won't have VIAF/CERL enrichment data to cite.

### Recommendations
- No major changes needed. Screen can be built as specified.
- Note that agent proposals for publishers will have limited authority context until publisher authorities are researched (89% are stubs).

---

## Screen 5: Correction Audit Trail -- `/operator/review`

**Rating: CONFIRMED**

### What Was Assumed
1. Summary bar: total corrections, by source, by field
2. Filter bar: field, source, search
3. Correction table with timestamp, field badge, source badge, raw->canonical mapping, evidence
4. CSV/JSON export
5. Revert capability
6. Link to affected records

### What Is Actually True
1. `GET /metadata/corrections/history` returns `CorrectionHistoryResponse` with `total`, `limit`, `offset`, and `entries[]`.
2. Each entry has `timestamp`, `field`, `raw_value`, `canonical_value`, `evidence`, `source` (human|agent), `action`.
3. Pagination is supported via `limit`/`offset`. Filtering by `field` is supported.

### Gaps
- **No revert endpoint exists.** The spec proposes "Revert capability (with confirmation)" but no API endpoint for reverting a correction has been built.
- **No date range filter** on corrections history API.
- **No search filter** on corrections history API.
- **Export** must be done client-side (no server-side export endpoint).
- **"Link to affected records"** requires cross-referencing `raw_value` against the issues endpoint, which is feasible but not a single API call.

### Recommendations
- Build revert endpoint if revert capability is required.
- Add `search`, `source`, and date range query params to `/metadata/corrections/history`.
- These are minor API additions, not architectural changes. Screen design is sound.

---

## Screen 6: Query Debugger -- `/diagnostics/query`

**Rating: MISALIGNED**

### What Was Assumed
1. Query plan inspector with confidence per filter
2. Side-by-side: query plan vs. SQL vs. results
3. TP/FP/FN/UNK labeling per candidate
4. Issue tagging per candidate
5. Gold set export
6. Execution timing breakdown (compile time, SQL time, format time)
7. Filter-level confidence visualization
8. Regression test runner display
9. New API endpoints: `/diagnostics/query-runs`, `/diagnostics/labels`, `/diagnostics/gold-set`

### What Is Actually True
1. The `QueryPlan` is NOT returned in `ChatResponse`. It is stored in session messages and accessible via `GET /sessions/{session_id}`, but the debugger would need to fetch the session to get the plan, or a new endpoint is needed.
2. SQL is available via `CandidateSet.sql`. Plan is available via session.
3. **No diagnostics API endpoints exist.** Zero `/diagnostics/*` endpoints have been implemented. No `/diagnostics/query-runs`, no `/diagnostics/labels`, no `/diagnostics/gold-set`.
4. The QA database (`data/qa/qa.db`) has tables for `qa_queries`, `qa_candidate_labels`, `qa_query_gold`, but NO API layer exposes them.
5. Filter-level confidence is always `null` -- the "which filter contributed most/least" visualization cannot be built.
6. Execution timing is computed internally but not exposed in any API response.
7. The regression runner (`app/qa.py`) exists as a CLI tool but has no API surface.

### Gaps
- **CRITICAL: All diagnostics API endpoints need to be built from scratch.** The spec assumes 3+ new endpoints that don't exist.
- **QA database operations have no HTTP interface.** Labeling, gold set management, and regression testing are CLI-only.
- **Per-filter confidence visualization is unbuildable** because filter confidence is always null.
- **Execution timing breakdown is not available** in any API response.
- **Query plan access requires session ID lookup**, not a direct field on the chat response.

### Recommendations
1. Build the diagnostics API layer before this screen (significant backend work).
2. Expose query plan and execution timing in the chat response or via dedicated endpoints.
3. Drop per-filter confidence visualization or redefine it as per-filter match contribution (count of records each filter narrowed).
4. Prioritize this screen AFTER Chat and Operator screens since it requires the most new backend work.

---

## Screen 7: Database Explorer -- `/diagnostics/db`

**Rating: MISALIGNED**

### What Was Assumed
1. Table selector (records, imprints, titles, subjects, languages, agents)
2. Schema display, row count per table
3. Paginated data browser with column search
4. Quick filter by MMS ID
5. Column statistics (distinct values, null counts)
6. New API endpoints: `GET /diagnostics/tables`, `GET /diagnostics/tables/{name}/rows`

### What Is Actually True
1. **No diagnostics API endpoints exist.** Zero `/diagnostics/*` endpoints have been built.
2. The bibliographic database has the tables listed (records, imprints, titles, subjects, languages, agents, notes, publisher_authorities, publisher_variants, authority_enrichment).
3. The data is there (2,796 records, 2,773 imprints, 4,791 titles, etc.) but no HTTP API exposes raw table access.

### Gaps
- **CRITICAL: All required API endpoints need to be built.** `GET /diagnostics/tables` and `GET /diagnostics/tables/{name}/rows` do not exist.
- No schema introspection endpoint exists.
- No column statistics endpoint exists.
- This is entirely new backend work.

### Recommendations
1. Build read-only diagnostics API endpoints. This is moderate backend work (generic table browser with parameterized queries).
2. Add SQL injection protection since this exposes raw table names.
3. Consider whether this screen is necessary for beta or can be deferred. The data is accessible via CLI/direct DB tools.

---

## Screen 8: Publisher Authorities -- `/admin/publishers`

**Rating: PARTIALLY_ALIGNED**

### What Was Assumed
1. Authority list with variant counts and imprint counts
2. Filter by type (printing_house, unresearched, etc.)
3. Expandable authority detail showing all variants
4. Add/edit authority records
5. Add/edit variant forms
6. Match preview: "Adding this variant would match N additional imprints"

### What Is Actually True
1. `GET /metadata/publishers` returns authorities with `variant_count`, `imprint_count`, `variants[]`, and all fields including `viaf_id`, `wikidata_id`, `cerl_id`, `dates_active`, `location`. Filtering by `type` is supported.
2. 227 authorities exist: 202 unresearched (89%), 18 printing houses, 3 bibliophile societies, 2 unknown markers, 1 modern publisher, 1 private press.
3. 265 variants across Latin, Hebrew, and other scripts.
4. Enrichment IDs (`viaf_id`, `wikidata_id`, `cerl_id`) are in the schema but the `authority_enrichment` table is empty (0 rows), so these fields are all null.

### Gaps
- **No CRUD endpoints for authorities.** `GET /metadata/publishers` is read-only. There are no `POST/PUT/DELETE` endpoints for creating, editing, or removing authority records or variants.
- **No match preview endpoint.** The spec proposes "Adding this variant would match N additional imprints" but no API computes this.
- **89% of authorities are unresearched stubs.** The list will show 202 records with `type: "unresearched"`, no `dates_active`, no `location`, no enrichment IDs. The expandable detail view will be mostly empty for these.
- **authority_enrichment table is empty.** All VIAF, Wikidata, CERL fields will be null.

### Recommendations
1. Build CRUD endpoints for authority management (POST/PUT/DELETE).
2. Build a match preview endpoint that counts imprints matching a proposed variant form.
3. Consider whether the publisher authority screen should emphasize the research workflow (classifying the 202 unresearched stubs) rather than just listing authorities.
4. The enrichment fields (VIAF, Wikidata, CERL) should be shown but clearly marked as "not yet researched" when empty.

---

## Screen 9: System Health -- `/admin/health`

**Rating: PARTIALLY_ALIGNED**

### What Was Assumed
1. API health status (database connectivity, session store)
2. Database size and last modification
3. Recent error log (tail of structured JSON logs)
4. Interaction log viewer (from `interaction_logger`)
5. API request rate and response time charts

### What Is Actually True
1. `GET /health` returns `status` (healthy|degraded|unhealthy), `database_connected`, `session_store_ok`. This works.
2. Database size and modification time are filesystem metadata, not exposed via API.
3. No log-viewing endpoint exists. Structured logs go to files but are not queryable via API.
4. `interaction_logger` writes to `data/metadata/interactions.jsonl` (if configured) but no API reads from it.
5. No request rate or response time metrics are collected or exposed via API.

### Gaps
- **Only the basic health check endpoint exists.** All "rich" health features (db size, logs, metrics, interaction viewer) need new API endpoints.
- **No metrics collection infrastructure.** Response time percentiles, request rate, etc. would require middleware (Prometheus, StatsD, or custom).
- **No log streaming/querying endpoint.**

### Recommendations
1. The basic health indicator (green/red dot in nav bar) can be built with the existing `GET /health` endpoint.
2. DB size and modification time require a simple new endpoint (trivial).
3. Defer log viewer and metrics dashboards to a later phase -- these require infrastructure.
4. Consider using a lightweight middleware for request timing (e.g., FastAPI middleware that logs to a table).

---

## Summary Table

| # | Screen | Path | Rating | Key Issue |
|---|--------|------|--------|-----------|
| 1 | Chat | `/` | PARTIALLY_ALIGNED | WebSocket lacks two-phase; filter confidence always null; execution time not exposed; facets discarded |
| 2 | Coverage Dashboard | `/operator/coverage` | PARTIALLY_ALIGNED | Confidence is binary not graduated; agent normalization is the real gap; trend data doesn't exist |
| 3 | Issues Workbench | `/operator/workbench` | PARTIALLY_ALIGNED | Only 121 low-confidence items total; Hebrew publishers & agents are bigger gaps but not surfaced as "issues" |
| 4 | Agent Chat | `/operator/agent` | CONFIRMED | API and data align well; minor gap on authority enrichment being empty |
| 5 | Correction Review | `/operator/review` | CONFIRMED | API supports core features; minor missing filters and no revert endpoint |
| 6 | Query Debugger | `/diagnostics/query` | MISALIGNED | Zero diagnostics API endpoints exist; QA database has no HTTP interface; filter confidence always null |
| 7 | Database Explorer | `/diagnostics/db` | MISALIGNED | Zero diagnostics API endpoints exist; entirely new backend work |
| 8 | Publisher Authorities | `/admin/publishers` | PARTIALLY_ALIGNED | Read-only API only; no CRUD; 89% stubs; enrichment table empty |
| 9 | System Health | `/admin/health` | PARTIALLY_ALIGNED | Only basic health check exists; no metrics, logs, or rich health data |

---

## Critical Misalignments

1. **WebSocket has no two-phase support.** The Chat screen's signature feature (Phase 1/Phase 2 flow with streaming) requires WebSocket to be updated. Currently, choosing WebSocket means losing all two-phase capabilities. This is the most impactful gap for the primary user-facing screen.

2. **All `/diagnostics/*` API endpoints are missing.** Screens 6 (Query Debugger) and 7 (Database Explorer) cannot be built without significant new backend work. The spec assumes these exist.

3. **FacetCounts are computed but never serialized to the frontend.** Phase 2 aggregation visualizations (bar charts, pie charts) are promised in the Chat screen, but the facet data computed by QueryService is discarded before reaching `ChatResponse`.

4. **Per-filter confidence is always null.** Multiple screens assume per-filter confidence visualization (Chat query insight, Query Debugger filter contribution). This data does not exist and the LLM does not produce it.

5. **Confidence distribution is binary, not graduated.** The coverage dashboard assumes a meaningful four-band distribution (high/medium/low/very_low). For place and publisher, only two bands have data (>=0.95 and <0.5). The "medium" and "low" bands are completely empty, making four-band visualization misleading.

---

## Confirmed Assumptions

1. **Candidate objects have all fields needed for result cards.** Title, author, date_start/end, place_norm/raw, publisher, subjects, description -- all present and populated.
2. **Evidence structure supports the proposed display.** Field, value, operator, matched_against, source, confidence -- well-structured for evidence panels.
3. **Suggested follow-ups are populated.** `ChatResponse.suggested_followups` works for follow-up chips.
4. **Agent chat API is well-structured.** Proposals with raw/canonical/confidence/reasoning, clusters with priority scores.
5. **Corrections API supports single and batch operations.** Both with records_affected counts.
6. **Publisher authorities API returns rich data.** Variant counts, imprint counts, variants with script/language.
7. **Session management works.** Create, retrieve, expire sessions via API.
8. **Coverage API provides per-field breakdown.** Confidence bands, method distribution, flagged items.
9. **Two-phase flow exists in HTTP API.** Phase 1 (intent interpretation with confidence) and Phase 2 (exploration with aggregation/refinement/comparison) work via POST /chat.
10. **Place, date, and language queries are reliable.** Correct results with proper evidence in all tests.

---

## Overall Verdict

**5 of 9 screens are PARTIALLY_ALIGNED, 2 are CONFIRMED, 2 are MISALIGNED.** The project's API layer has strong coverage for the Operator tier (screens 3-5) and reasonable foundations for the Chat screen, but significant backend work is needed for Diagnostics and Admin tiers. The most impactful finding is that the primary user experience (Chat) relies on WebSocket streaming for responsiveness but WebSocket currently lacks the two-phase architecture that makes the Chat experience distinctive. The secondary finding is that the data quality story is different than assumed: the collection is already in excellent shape (97-99% coverage), so the "issues workbench" pattern of finding and fixing low-confidence records is nearly completed. The real remaining gaps -- Hebrew-script publisher transliteration, agent alias maps, publisher authority research -- are not well-served by the current "low confidence = issue" framing.

The recommended build order should be adjusted:
1. **Chat (HTTP only first)** -- two-phase flow works via HTTP; defer WebSocket upgrade
2. **Operator screens (port existing)** -- already well-supported by APIs
3. **Publisher Authorities** -- elevate priority since 89% stubs represent the biggest research gap
4. **Diagnostics** -- defer until new backend endpoints are built
5. **System Health** -- minimal value for beta; basic health indicator is easy
