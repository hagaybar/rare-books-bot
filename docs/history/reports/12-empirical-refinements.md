# Report 12: Empirical Refinements to UI Redesign

**Date:** 2026-03-23
**Status:** Post-verification corrections and amendments
**Scope:** Corrections, additions, and caveats for Reports 00, 06, and 07 based on empirical verification (Reports 08-11)
**Method:** Cross-referencing the proposed 9-screen architecture against actual database contents, pipeline behavior, and API response shapes

---

## 1. Summary of Confirmed Assumptions

The following assumptions from the original reports were validated by empirical testing:

1. **Candidate object has all required fields for result cards.** `title`, `author`, `date_start`, `date_end`, `place_norm`, `place_raw`, `publisher`, `subjects`, `description` are all present and populated on `Candidate` objects.

2. **Evidence structure supports the proposed display.** Evidence objects have `field`, `value`, `operator`, `matched_against`, `source`, `confidence` -- sufficient to build evidence panels with MARC field citations.

3. **`suggested_followups` is populated.** `ChatResponse.suggested_followups` returns an array of strings suitable for follow-up chips.

4. **Agent Chat API is well-structured.** `POST /metadata/agent/chat` returns proposals with `raw_value`, `canonical_value`, `confidence`, `reasoning`, `evidence_sources`, and clusters with `priority_score`. The screen can be built as specified.

5. **Correction Review API supports core features.** `GET /metadata/corrections/history` returns paginated entries with `timestamp`, `field`, `raw_value`, `canonical_value`, `evidence`, `source`, `action`. Filtering by `field` is supported.

6. **Corrections API supports single and batch operations.** Both `POST /metadata/corrections` and `POST /metadata/corrections/batch` work and return `records_affected` counts.

7. **Publisher authorities API returns rich data.** `GET /metadata/publishers` returns authorities with `variant_count`, `imprint_count`, `variants[]`, enrichment IDs, type filtering. Read operations are confirmed.

8. **Session management works.** Create, retrieve, and expire sessions via API. `GET /sessions/{session_id}` returns full message history with embedded `query_plan` and `candidate_set`.

9. **Coverage API provides per-field breakdown.** Confidence distribution (10 bands), method distribution, and flagged items per field are all returned by `GET /metadata/coverage`.

10. **Two-phase flow exists in HTTP API.** Phase 1 (intent interpretation with confidence, clarification prompts) and Phase 2 (exploration with aggregation, refinement, comparison, enrichment) work correctly via `POST /chat`.

11. **Place, date, and language queries are reliable.** Correct results with proper evidence across all tested queries.

12. **Multi-filter AND composition works.** Hebrew + Amsterdam + 17th century correctly composes three filters.

---

## 2. Summary of Contradicted or Missing Assumptions

### 2.1 Critical Misalignments (5)

**C1. WebSocket has NO two-phase support.**

- **What was assumed:** WebSocket streaming (`WS /ws/chat`) supports the same two-phase flow as HTTP, with phase transitions, interpretation confidence, and facet data.
- **What is actually true:** WebSocket uses the old single-phase `compile_query()` path. It does NOT use the intent agent, does NOT compute facets, does NOT set `phase` or `confidence` on the response, and uses a different text formatter. Choosing WebSocket means losing all Phase 1/2 capabilities.
- **Impact:** The Chat screen spec calls for streaming + phase visualization. These are currently mutually exclusive. Either WebSocket must be upgraded (significant backend work) or Chat must launch with HTTP-only (losing streaming progress indicators).

**C2. ALL `/diagnostics/*` API endpoints are missing.**

- **What was assumed:** Diagnostic endpoints (`/diagnostics/query-runs`, `/diagnostics/labels`, `/diagnostics/gold-set`, `/diagnostics/tables`) either exist or are minor additions.
- **What is actually true:** Zero diagnostic endpoints have been implemented. The QA database (`data/qa/qa.db`) has tables for labels and gold sets but no HTTP layer exposes them. Query plan access requires fetching the full session.
- **Impact:** Screens 6 (Query Debugger) and 7 (Database Explorer) cannot be built without significant new backend work. Phase 2 of the migration plan must explicitly account for this as a blocking prerequisite.

**C3. FacetCounts are computed then DISCARDED.**

- **What was assumed:** Phase 2 aggregation charts (bar charts, pie charts) have a data source in the API response.
- **What is actually true:** `QueryService.execute_plan()` computes facets when `compute_facets=True` (which POST /chat enables), but the resulting `FacetCounts` object is NOT serialized into `ChatResponse`. It remains inside `QueryResult` which is not forwarded to the frontend. The aggregation data (by_place, by_year, by_language, by_publisher, by_century) exists but is inaccessible.
- **Impact:** Phase 2 aggregation visualizations in the Chat screen are unbuildable without a backend change to forward facets in `ChatResponse.metadata`.

**C4. Per-filter confidence is always null.**

- **What was assumed:** Each filter in the QueryPlan has a confidence score that can be visualized to show "which filter the LLM is most/least sure about."
- **What is actually true:** The LLM is not asked to produce per-filter confidence scores. All `Filter.confidence` values are `null` in every tested query. Only `ChatResponse.confidence` (overall interpretation confidence) is reliably populated.
- **Impact:** The per-filter confidence visualization proposed for the Chat query insight panel and Query Debugger is unbuildable with current data. Must be dropped or replaced with a heuristic alternative.

**C5. Confidence distribution is binary, not graduated.**

- **What was assumed:** Coverage Dashboard shows a meaningful four-band distribution (high >= 0.95, medium 0.8-0.95, low 0.5-0.8, very_low < 0.5) with records distributed across all bands.
- **What is actually true:**
  - Place: 19 records at < 0.5, then 2,754 at >= 0.95. The 0.5-0.95 range is EMPTY.
  - Publisher: 33 at < 0.5, then 2,740 at >= 0.95. The 0.5-0.95 range is EMPTY.
  - Date: 69 at < 0.5, 1,306 at 0.8-0.95, 1,398 at 0.95-1.0. No records in 0.5-0.8.
  - Agent: Not applicable (100% base_clean at 0.80).
- **Impact:** Four-band visualization for place and publisher is misleading -- it shows 99%+ green and a tiny red sliver. The "medium" and "low" bands will be completely empty.

### 2.2 Data Reality Contradictions (4)

**D1. Only 121 low-confidence records total.**

- **What was assumed:** The Issues Workbench handles a substantial volume of issues requiring triage.
- **What is actually true:** 69 low-confidence dates + 19 places + 33 publishers = 121 total. The workbench will be nearly empty for three of four fields.
- **Impact:** The workbench framing should shift from "issue triage" to "improvement opportunities" encompassing broader gaps.

**D2. The real gaps are not captured by low-confidence scores.**

The actual improvement opportunities are:
- 553 Hebrew-script publishers (20.2% of publishers) -- technically 0.95 confidence but NOT normalized for cross-lingual search
- 4,366 un-normalized agents (100% base_clean method, no alias mapping)
- 202 unresearched publisher authorities (89% of all authorities are stubs)
- 44.1% of agent roles categorized as "other"

These are all high-confidence records that are functionally incomplete. None show up as "issues" in the current low-confidence framing.

**D3. Publisher variant matching fails for historical name forms.**

- Query "books published by Elsevier" matched only 1 of 16 Elzevir-family records. The publisher authority system maps many historical forms to "house of elzevir" but the CONTAINS filter `LIKE '%elsevier%'` only matches the modern spelling. This is a known pipeline gap that affects Chat result quality.

**D4. Subject retry causes false broadening.**

- Query "books about quantum physics" should return 0 results. Instead, the retry mechanism remapped it to "Philosophy", returning 67 unrelated records. This is a precision problem that the Chat screen must handle gracefully (display a warning, not silent broadening).

### 2.3 API Gaps (8)

| # | Gap | Screens Affected | Severity |
|---|-----|-------------------|----------|
| A1 | `execution_time_ms` not exposed in `ChatResponse` | Chat, Query Debugger | Medium |
| A2 | `QueryWarning[]` not forwarded to frontend | Chat, Query Debugger | Medium |
| A3 | No CRUD endpoints for publisher authorities | Publisher Authorities | High (blocks editing) |
| A4 | No diagnostics endpoints (zero exist) | Query Debugger, DB Explorer | Critical (blocks screens) |
| A5 | Primo URLs not on Candidate objects | Chat | Low (workaround exists) |
| A6 | `ChatResponse.metadata` is polymorphic (untyped dict) | Chat | Low (frontend must handle) |
| A7 | No revert endpoint for corrections | Correction Review | Medium |
| A8 | No date range or search filter on corrections history | Correction Review | Low |

### 2.4 Evidence Quality Issues (3)

| # | Issue | Affected Display |
|---|-------|------------------|
| E1 | Subject evidence `value` is always null | Evidence panel shows "matched against X" but not what actually matched in the DB |
| E2 | Agent evidence `source` shows "marc:unknown" | Evidence panel cannot show MARC tag provenance for agents |
| E3 | `QueryWarning[]` includes important information (e.g., EMPTY_FILTERS, SUBJECT_RETRY) but is not forwarded to the frontend | Chat warnings and Query Debugger issue tracking |

---

## 3. Screen-by-Screen Changes

### Screen 1: Chat (`/`) -- PARTIALLY_ALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Launch with HTTP-only** | Architecture | Use `POST /chat` for full two-phase flow. Defer WebSocket streaming to a later iteration once the WebSocket handler is upgraded to use the intent agent and two-phase architecture. The HTTP endpoint already provides the complete experience. |
| **Drop per-filter confidence display** | Remove feature | Replace the "confidence per filter" panel with overall interpretation confidence only (`ChatResponse.confidence`). Do not show per-filter confidence bars since all values are null. |
| **Add execution timing (requires backend)** | Backend prerequisite | Add `execution_time_ms` to `ChatResponse.metadata` (small API change). Until then, show only the result count without timing. |
| **Add facets forwarding (requires backend)** | Backend prerequisite | Add `FacetCounts` to `ChatResponse.metadata` when available. Until then, Phase 2 aggregation charts cannot be rendered. Aggregation text responses still work. |
| **Batch Primo URL resolution** | Implementation detail | Primo URLs are not on `Candidate` objects. Use `POST /metadata/primo-urls` to batch-resolve URLs for all candidates in a result set, rather than N+1 single calls. Cache results client-side. |
| **Handle subject retry warning** | New feature | If `QueryWarning` with type `SUBJECT_RETRY` is present (requires backend forwarding), display a warning: "No exact subject match found. Showing results for closest match: [remapped subject]." Let user accept or reject the broadening. |
| **Handle polymorphic metadata** | Implementation detail | `ChatResponse.metadata` contains different shapes depending on phase and intent. Frontend must use type guards to extract `overview_stats`, `explanation`, `visualization_hint`, `data`, etc. |
| **Show query plan via session fetch** | Workaround | `QueryPlan` is not in `ChatResponse` directly, but is in the session messages. For "observable by default" features, fetch `GET /sessions/{session_id}` and extract the query plan from the most recent assistant message. |

### Screen 2: Coverage Dashboard (`/operator/coverage`) -- PARTIALLY_ALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Replace four-band with binary visualization** for place/publisher | Redesign | Use a simple "resolved / unresolved" split (green / red) instead of four bands. The medium and low bands are empty for place and publisher. Keep graduated bands only for dates (where 0.8-0.95 segment has 1,306 records). |
| **Lead with agent normalization gaps** | Reprioritize | Agent coverage (100% base_clean, 0% alias-mapped) is the largest gap. Make it the lead story, not a secondary metric. Show "0% normalized (4,366 agents)" prominently. |
| **Add Hebrew-script publisher indicator** | New metric | Surface the 553 Hebrew-script publishers as a distinct coverage gap category. They are technically 0.95 confidence but functionally un-normalized for cross-lingual search. |
| **Drop "trend over time"** from initial scope | Defer | No snapshot mechanism exists. Either add a periodic snapshot job first or defer entirely to a later phase. |
| **Drop "before/after correction" comparison** | Defer | No tracking infrastructure exists for this. |
| **Reframe gap cards** | Rewrite | Instead of "19 null places" (which is accurate but tiny), show "19 unresolvable places, 553 Hebrew-only publishers, 202 unresearched authorities" -- the full picture of improvement opportunities. |

### Screen 3: Issues Workbench (`/operator/workbench`) -- PARTIALLY_ALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Reframe from "issues" to "improvement opportunities"** | Conceptual | Only 121 records have low confidence. The real work is: Hebrew-script publisher transliteration (553), agent alias mapping (4,366), publisher authority research (202 stubs), agent role categorization (44.1% "other"). These are not "low confidence" items -- they are normalization upgrade opportunities. |
| **Add method-based filtering** | New feature | Replace or supplement the confidence slider with method-based filters: "base_clean only" vs "alias_map" vs "publisher_authority". This surfaces the 4,366 base_clean agents and 553 Hebrew-script publishers that the confidence slider misses. |
| **Acknowledge confidence slider gap** | Design note | Moving the slider from 0.5 to 0.95 returns 0 results for place and publisher. Only values < 0.5 or >= 0.95 exist. The slider provides no value for these fields. Replace with checkboxes: "Show unresolved only" (< 0.5) or "Show all." |
| **Note: date corrections not supported** | Constraint | `CorrectionRequest.field` accepts only `place`, `publisher`, `agent`. Date corrections need a different mechanism or the API must be extended. |
| **Add "Hebrew publishers" tab** | New feature | Dedicated tab showing the 553 un-transliterated Hebrew-script publishers with their frequency and imprint counts. These need human or agent review but are not surfaced by the existing "low confidence" filter. |

### Screen 4: Agent Chat (`/operator/agent`) -- CONFIRMED

| Change | Type | Description |
|--------|------|-------------|
| **Note limited publisher authority context** | Documentation | 89% of publisher authorities are "unresearched" stubs with no enrichment data (VIAF, Wikidata, CERL all null). Publisher agent proposals will have limited authority context until authorities are researched. |
| **Note empty authority_enrichment table** | Documentation | The `authority_enrichment` table has 0 rows. Agent proposals citing authority data will have nothing to reference. |
| No structural changes needed | -- | API and data align well for this screen. |

### Screen 5: Correction Review (`/operator/review`) -- CONFIRMED

| Change | Type | Description |
|--------|------|-------------|
| **Defer revert capability** | Defer | No revert API endpoint exists. Build the screen without revert; add when the endpoint is built. |
| **Defer date range and search filters** | Defer | Corrections history API only supports `field` filter. Client-side filtering can approximate date range and search until API params are added. |
| **Client-side export** | Implementation note | No server-side export endpoint exists. Build CSV/JSON export as client-side download from the fetched data. |
| No structural changes needed | -- | Core screen design is sound. |

### Screen 6: Query Debugger (`/diagnostics/query`) -- MISALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Requires new backend work (blocking)** | Architecture | All diagnostics API endpoints must be built from scratch before this screen can function. This includes: `POST /diagnostics/query-run`, `GET /diagnostics/query-runs`, `POST /diagnostics/labels`, `GET /diagnostics/labels/{run_id}`, `POST /diagnostics/gold-set/export`, `POST /diagnostics/gold-set/regression`. |
| **Drop per-filter confidence visualization** | Remove feature | Filter confidence is always null. Replace with per-filter match contribution: how many records each filter narrowed the result set by (computable from facets or by progressive filter execution). |
| **Drop execution timing breakdown** until backend exposes it | Defer | `execution_time_ms` is not in any API response. Show only result count and filter count initially. |
| **Access query plan via session** | Workaround | `QueryPlan` is stored in session messages, not in `ChatResponse`. The debugger must fetch `GET /sessions/{session_id}` and extract the plan from the most recent assistant message. Or, add the plan to the diagnostics query-run endpoint response. |
| **Reprioritize to after Operator screens** | Schedule | This screen requires the most new backend work. Build after Chat and Operator screens are complete, not in parallel with Chat. |
| **Warn about subject retry behavior** | New feature | Display `SUBJECT_RETRY` warnings prominently so QA testers can identify false broadening (quantum physics -> Philosophy). |

### Screen 7: Database Explorer (`/diagnostics/db`) -- MISALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Requires new backend work (blocking)** | Architecture | `GET /diagnostics/tables` and `GET /diagnostics/tables/{name}/rows` must be built. This is moderate work (generic read-only table browser with parameterized queries, SQL injection protection). |
| **Include additional tables** | Scope expansion | The database has 10 tables (records, imprints, titles, subjects, agents, languages, notes, publisher_authorities, publisher_variants, authority_enrichment), not just the 6 originally listed. |
| **Consider deferring to post-beta** | Schedule | The data is accessible via CLI and direct SQLite tools. This screen adds convenience but is not blocking for any other feature. |

### Screen 8: Publisher Authorities (`/admin/publishers`) -- PARTIALLY_ALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Requires CRUD endpoints (blocking for editing)** | Backend prerequisite | Only `GET /metadata/publishers` exists. POST/PUT/DELETE endpoints for creating, editing, and removing authorities and variants must be built. |
| **Requires match preview endpoint** | Backend prerequisite | The "Adding this variant would match N additional imprints" feature needs a new endpoint that counts imprints matching a proposed variant form. |
| **Reframe for research workflow** | Conceptual | 89% of authorities (202 of 227) are "unresearched" stubs. The screen should emphasize the research workflow: classifying stubs into proper types, adding dates/locations, linking to VIAF/CERL -- not just listing authorities. |
| **Show enrichment fields as "not yet researched"** | Display | VIAF, Wikidata, CERL fields will all be null for most records. Show them but clearly indicate "not yet researched" rather than leaving blank. |
| **Elevate priority** | Schedule | Publisher authority research is one of the three biggest remaining gaps (202 stubs). Elevate from Phase 3 to potentially co-develop with Phase 1 since the read-only view already works. |

### Screen 9: System Health (`/admin/health`) -- PARTIALLY_ALIGNED

| Change | Type | Description |
|--------|------|-------------|
| **Build with basic health only** | Scope reduction | Only `GET /health` exists. Build the nav bar indicator (green/red dot) and a simple health page showing `database_connected`, `session_store_ok`, and status. |
| **Defer log viewer, metrics, interaction viewer** | Defer | No log streaming/querying API, no metrics collection infrastructure, no interaction log API exists. These require infrastructure investment beyond the scope of the UI migration. |
| **Add DB file size (trivial endpoint)** | Backend addition | A simple endpoint returning file size and last-modified timestamp for `bibliographic.db` is trivial to build and adds useful information. |
| **Lowest priority screen** | Schedule | Minimal value for beta. The nav bar health indicator is easy and useful; the full health page can wait. |

---

## 4. Migration Plan Adjustments

### 4.1 Revised Phase Structure

The original plan assumes 7 weeks across 6 phases. Empirical findings require the following adjustments:

**Phase 0: Foundation & Scaffolding (1 week) -- NO CHANGE**
Proceed as specified. No empirical findings affect the scaffolding work.

**Phase 1: Chat Screen (2 weeks) -- MODIFIED**

| Original | Revised |
|----------|---------|
| Build with WebSocket streaming from day 1 | Launch with HTTP-only (`POST /chat`). WebSocket streaming is deferred until the WebSocket handler is upgraded to support two-phase flow. |
| Per-filter confidence in query insight panel | Drop. Show only overall `ChatResponse.confidence`. |
| Execution timing in collapsible panel | Defer until `execution_time_ms` is added to `ChatResponse.metadata` (backend task, can be done early in Phase 1). |
| Aggregation chart rendering in Phase 2 | Defer chart rendering until `FacetCounts` are forwarded in `ChatResponse.metadata` (backend task). Aggregation text responses work immediately. |
| Inline Primo links on candidate titles | Use batch `POST /metadata/primo-urls` call after results load. Cache URLs client-side. |

**New: Backend micro-tasks for Phase 1** (first 2-3 days):
1. Add `execution_time_ms` to `ChatResponse.metadata` (small change)
2. Forward `FacetCounts` to `ChatResponse.metadata` when computed (small change)
3. Forward `QueryWarning[]` to `ChatResponse.metadata` (small change)
4. Add `primo_url` to `Candidate` model OR accept the batch-resolve approach

These are small API changes that unblock frontend features. They are NOT the large-scale diagnostic endpoint work.

**Phase 2: Query Debugger + DB Explorer (2 weeks) -- MODIFIED**

| Original | Revised |
|----------|---------|
| Backend prerequisite: 2-3 days | Backend prerequisite: 4-5 days minimum. All diagnostic endpoints must be designed and implemented from scratch. Include SQL injection protection for table browser. |
| Per-filter confidence visualization | Drop entirely. Replace with per-filter match contribution if feasible (requires facet data per filter, which is a non-trivial computation). |
| Execution timing breakdown | Available only after Phase 1 backend micro-tasks complete. |
| Can overlap with Phase 1 | Should start AFTER Phase 1, not in parallel. The backend work for diagnostics is substantial and should not compete with Phase 1 backend micro-tasks. |

**Phase 3: Admin Screens (1 week) -- MODIFIED**

| Original | Revised |
|----------|---------|
| Publisher Authorities as simple list | Reframe as research workflow tool. Read-only view is buildable immediately; editing requires CRUD endpoints (backend work). |
| System Health with rich features | Scope down to basic health page + nav bar indicator. Defer log viewer, metrics, interaction viewer. |
| One week for both screens | Split: read-only publishers view in parallel with Phase 1 (1-2 days since API exists). Full CRUD and System Health in original Phase 3 slot. |

**Phase 4: Polish, Integration & Testing (1-2 weeks) -- MODIFIED**

Add the following tasks:
- WebSocket upgrade to two-phase flow (if prioritized for streaming UX)
- Corrections API extension: add `date` to `CorrectionRequest.field`
- Corrections history API: add `search`, `source`, date range params
- Revert endpoint for corrections
- Confidence slider replacement with method-based filtering

**Phase 5: Retirement & Cleanup (1 week) -- NO CHANGE**
Proceed as specified.

### 4.2 Revised Timeline

```
Week 1:     Phase 0 -- Foundation & Scaffolding
            Phase 1 backend micro-tasks (execution_time, facets, warnings)
Weeks 2-3:  Phase 1 -- Chat Screen (HTTP-only, no WebSocket streaming)
            Phase 3a -- Publisher Authorities read-only view (in parallel, 1-2 days)
Week 4:     Phase 2 backend -- Diagnostics API endpoints (4-5 days)
Weeks 4-5:  Phase 2 frontend -- Query Debugger + DB Explorer
Week 5:     Phase 3b -- Publisher CRUD endpoints + System Health basic
Weeks 6-7:  Phase 4 -- Polish, Integration, Testing, WebSocket upgrade
Week 8:     Phase 5 -- Retirement & Cleanup
```

**Total: 8 weeks** (was 7 weeks). The extra week accounts for the larger-than-expected backend work for diagnostic endpoints and the sequential (not parallel) relationship between Phases 1 and 2.

### 4.3 Revised Risk Table

| # | Risk | Status After Verification |
|---|------|--------------------------|
| 1 | WebSocket implementation complexity | **ELEVATED.** Now confirmed that WebSocket lacks two-phase support entirely. Recommendation: defer WebSocket, launch HTTP-only. |
| 2 | Query Debugger scope creep | **UNCHANGED.** Still high likelihood. |
| 3 | Diagnostic API endpoints take longer than estimated | **ELEVATED to CRITICAL.** Zero endpoints exist. Was estimated at 2-3 days; revised to 4-5 days minimum. |
| 4 | QA data migration | **UNCHANGED.** Low risk, new API reads from existing `qa.db`. |
| 5 | Streamlit retirement breaks workflows | **UNCHANGED.** Medium risk. |
| 6 | Performance regression | **UNCHANGED.** Low risk. |
| 7 | Landing page change confuses users | **UNCHANGED.** Low risk. |
| 8 | WebSocket uses old single-phase path | **CONFIRMED as real.** Not a risk -- a known fact. Mitigation: launch HTTP-only. |

New risks identified:
| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 9 | Phase 2 aggregation charts unbuildable without backend facets forwarding | Degraded Phase 2 UX | High (confirmed) | Add FacetCounts forwarding in Phase 1 backend micro-tasks |
| 10 | Issues Workbench appears empty/unused with only 121 items | User confusion, perceived low value | High (confirmed) | Reframe as "improvement opportunities" with method-based filtering |
| 11 | Publisher variant matching gap (Elsevier/Elzevir) causes user confusion in Chat | Users miss most historical records for publisher queries | High (confirmed) | Document as known limitation; consider publisher-authority-aware search |
| 12 | Subject retry false broadening produces incorrect results | Users receive misleading results without warning | Medium (confirmed) | Forward QueryWarning to frontend; display retry warning prominently |

---

## 5. Backend Task Inventory

The empirical verification revealed a significant amount of backend work that the original reports treated as trivial or assumed already existed. This inventory captures all required backend changes.

### 5.1 Small Changes (Phase 1, days 1-3)

| # | Task | Effort | Blocks |
|---|------|--------|--------|
| B1 | Add `execution_time_ms` to `ChatResponse.metadata` | 1-2 hours | Chat timing display |
| B2 | Forward `FacetCounts` in `ChatResponse.metadata` | 2-4 hours | Phase 2 aggregation charts |
| B3 | Forward `QueryWarning[]` in `ChatResponse.metadata` | 1-2 hours | Chat warnings, Debugger |
| B4 | Add `primo_url` to Candidate model OR document batch approach | 2-4 hours | Chat Primo links |

### 5.2 Medium Changes (Phase 2-3)

| # | Task | Effort | Blocks |
|---|------|--------|--------|
| B5 | `POST /diagnostics/query-run` | 1 day | Query Debugger |
| B6 | `GET /diagnostics/query-runs` | 0.5 day | Query Debugger history |
| B7 | `POST /diagnostics/labels` | 0.5 day | Query Debugger labeling |
| B8 | `GET /diagnostics/labels/{run_id}` | 0.5 day | Query Debugger labeling |
| B9 | `POST /diagnostics/gold-set/export` | 0.5 day | Gold set management |
| B10 | `POST /diagnostics/gold-set/regression` | 1 day | Regression runner display |
| B11 | `GET /diagnostics/tables` | 0.5 day | DB Explorer |
| B12 | `GET /diagnostics/tables/{name}/rows` | 1 day | DB Explorer (with SQL injection protection) |
| B13 | Publisher authority CRUD (POST/PUT/DELETE) | 1-2 days | Publisher editing |
| B14 | Publisher match preview endpoint | 0.5 day | Match impact display |
| B15 | DB file size/last-modified endpoint | 1 hour | System Health |

### 5.3 Larger Changes (Phase 4 or later)

| # | Task | Effort | Blocks |
|---|------|--------|--------|
| B16 | Upgrade WebSocket handler to two-phase flow | 2-3 days | Chat streaming with phase support |
| B17 | Add `date` to `CorrectionRequest.field` supported values | 0.5 day | Date corrections in Workbench |
| B18 | Add `search`, `source`, date range to corrections history | 0.5 day | Correction Review filters |
| B19 | Corrections revert endpoint | 1 day | Correction Review revert |
| B20 | Fix subject evidence `value` null (populate from DB) | 0.5 day | Evidence panel completeness |
| B21 | Fix agent evidence `source` "marc:unknown" | 0.5 day | Evidence panel MARC provenance |
| B22 | Add subject retry confidence threshold or warning | 1 day | False broadening prevention |

**Total backend effort: approximately 12-15 developer-days** of new work revealed by empirical verification, with B1-B4 being quick wins and B5-B15 being the critical path for Phase 2 and 3.

---

## 6. Revised Screen Ratings

| # | Screen | Original Rating | Revised Rating | Change Reason |
|---|--------|----------------|----------------|---------------|
| 1 | Chat | N/A (new) | PARTIALLY_ALIGNED | WebSocket gap, missing facets, missing timing, per-filter confidence always null |
| 2 | Coverage Dashboard | N/A (existing enhanced) | PARTIALLY_ALIGNED | Binary confidence, agent gaps not highlighted, no trend data |
| 3 | Issues Workbench | N/A (existing enhanced) | PARTIALLY_ALIGNED | Only 121 items, real gaps not surfaced, confidence slider ineffective |
| 4 | Agent Chat | N/A (existing enhanced) | CONFIRMED | API aligns well, minor gaps in authority data |
| 5 | Correction Review | N/A (existing enhanced) | CONFIRMED | Core API works, minor missing filters and no revert |
| 6 | Query Debugger | N/A (new) | MISALIGNED | Zero diagnostic endpoints exist, filter confidence null |
| 7 | Database Explorer | N/A (new) | MISALIGNED | Zero diagnostic endpoints exist |
| 8 | Publisher Authorities | N/A (new) | PARTIALLY_ALIGNED | Read-only only, no CRUD, 89% stubs |
| 9 | System Health | N/A (new) | PARTIALLY_ALIGNED | Only basic health check exists |

---

## 7. Key Recommendations Summary

### Must-Do Before Building

1. **Phase 1 backend micro-tasks** (B1-B4): Add execution_time, facets, warnings, Primo URLs to ChatResponse. These are small changes that unblock major frontend features.
2. **Decide on WebSocket strategy**: Either upgrade to two-phase (2-3 days backend) or launch HTTP-only and add streaming later. Recommendation: launch HTTP-only.
3. **Reframe Issues Workbench** from "low-confidence issues" to "improvement opportunities" with method-based filtering.

### Must-Do Before Phase 2

4. **Build all diagnostic API endpoints** (B5-B12). This is 4-5 days of work and blocks both Query Debugger and DB Explorer.
5. **Do not start Phase 2 frontend** until at least B5, B7, B11, B12 are functional.

### Design Changes (No Backend Required)

6. **Replace four-band confidence visualization** with binary (resolved/unresolved) for place and publisher. Keep graduated for dates.
7. **Drop per-filter confidence** from all screens. Show only overall interpretation confidence.
8. **Lead Coverage Dashboard with agent normalization gaps**, not date/place/publisher (which are 97%+ resolved).
9. **Add Hebrew-script publisher indicator** as a distinct gap category.
10. **Scope down System Health** to basic status + nav bar indicator.

### Accept as Known Limitations

11. Publisher variant matching gap (Elsevier/Elzevir) -- document, do not attempt to solve in UI.
12. Subject retry false broadening -- display warning, let user accept or reject.
13. 89% of publisher authorities are unresearched stubs -- show "not yet researched" prominently.
14. `authority_enrichment` table is empty -- VIAF/Wikidata/CERL data is not available.
