# Migration & Decommissioning Plan: Unified Rare Books Bot UI

**Date:** 2026-03-23
**Status:** Approved plan, ready for execution
**Scope:** Consolidate 5 UI surfaces into one React SPA; retire Streamlit apps; restructure backend

---

## 1. Current State Summary

| Surface | Tech | Lines | Status |
|---------|------|-------|--------|
| Metadata Workbench | React 19 / Vite 8 / TS | ~2,845 TSX + hooks/types/api | **Foundation** -- keep and extend |
| Chat UI | Streamlit | ~449 Python | **Replace** -- thin HTTP wrapper, no streaming |
| QA Tool | Streamlit (6 pages) | ~3,531 Python | **Replace** -- valuable logic, wrong framework |
| CLI | Typer | ~200+ Python | **Keep** -- add `regression` subcommand |
| QA Regression Runner | Typer | 187 Python | **Consolidate** -- merge into CLI |
| FastAPI Backend | FastAPI | ~3,219 Python | **Keep** -- add diagnostic endpoints |

**Key constraint:** The React Workbench is the only UI with real engineering investment (TanStack Query/Table, typed API layer, proper loading/error states). Everything else is either a thin wrapper (Chat UI) or trapped in Streamlit's limitations (QA Tool). The migration is primarily about building forward on the React foundation, not porting Streamlit code.

---

## 2. Phased Plan

### Phase 0: Foundation & Scaffolding (1 week)

**Goal:** Restructure the existing React app for the 9-screen architecture without breaking current functionality.

**Deliverables:**
1. Restructure `frontend/src/` to tiered route layout:
   ```
   pages/
     Chat.tsx                    # new, placeholder
     operator/
       Coverage.tsx              # renamed from Dashboard.tsx
       Workbench.tsx             # moved
       AgentChat.tsx             # moved
       Review.tsx                # moved
     diagnostics/
       QueryDebugger.tsx         # new, placeholder
       DatabaseExplorer.tsx      # new, placeholder
     admin/
       Publishers.tsx            # new, placeholder
       Health.tsx                # new, placeholder
   ```
2. Update `App.tsx` routing to new URL structure (`/operator/coverage`, etc.)
3. Replace `Sidebar.tsx` with tiered navigation (Chat, Operator section, Diagnostics section, Admin section)
4. Add `zustand` store for UI state (sidebar collapse, active field tab)
5. Add shared design tokens file (confidence colors, spacing, typography constants)
6. Set up Vite proxy for all new API paths (`/chat`, `/health`, `/diagnostics/*`, `/admin/*`)
7. Redirect old routes (`/` -> `/operator/coverage`, `/workbench` -> `/operator/workbench`, etc.) for backward compatibility during transition

**Criteria to exit:** All 4 existing Workbench pages render at their new URLs. Placeholder pages exist for all 5 new screens. No functionality lost.

**Risk:** Route changes break bookmarks. **Mitigation:** Temporary redirects from old paths.

---

### Phase 1: Chat Screen (2 weeks)

**Goal:** Build the primary user-facing screen. This is the highest-impact deliverable -- it replaces the Streamlit Chat UI and becomes the product's landing page.

**Deliverables:**
1. `Chat.tsx` -- full conversational interface:
   - Message input with send button
   - Message history display (user messages + bot responses)
   - Session management (create new, resume existing via URL param)
   - Integration with `POST /chat` endpoint
   - Two-phase flow visualization (Phase 1: query definition, Phase 2: exploration)
   - Interpretation confidence display (extracted filters with per-filter confidence)
   - Clarification prompt rendering
2. `CandidateCard.tsx` -- reusable result card component:
   - Title (linked to Primo), author, date, place, publisher, subjects
   - Expandable evidence panel (MARC field citations, confidence scores)
   - Smart date display (single year vs range)
   - Place display (canonical + raw with deduplication)
   - Primo URL generation (configurable institution, consolidate TAU/NLI schemes)
3. `useWebSocket.ts` hook for streaming via `WS /ws/chat`:
   - Connection lifecycle management
   - Progress message rendering (compile, execute, format stages)
   - Batch result accumulation
   - Reconnection on disconnect
4. Follow-up suggestion chips (from API `suggested_followups`)
5. Example query shortcuts (welcome state when no messages)
6. Collection overview rendering for introductory queries
7. Phase indicator in UI (defining query vs. exploring results)

**Dependencies:** Phase 0 complete.

**Criteria to exit:**
- Can send a natural language query and see formatted results with evidence
- WebSocket streaming shows progress indicators
- Two-phase conversation flow works (define query -> explore subgroup)
- Clarification prompts render for ambiguous queries
- Session persists across page reloads (via session_id in URL or localStorage)
- Primo links work for all results

**What this enables:** The Streamlit Chat UI (`app/ui_chat/`) can be marked deprecated. Both UIs run in parallel during Phase 1, but all new chat testing happens in React.

---

### Phase 2: Query Debugger (2 weeks)

**Goal:** Replace the QA Tool's core functionality (query testing, labeling, regression) in React. This is the second-highest impact because it unblocks retiring the largest Streamlit surface.

**Prerequisite backend work (first 2-3 days of this phase):**
Add diagnostic API endpoints to FastAPI:
- `POST /diagnostics/query-run` -- execute query, return plan + SQL + results + timing
- `GET /diagnostics/query-runs` -- list past query runs (replaces QA sessions)
- `POST /diagnostics/labels` -- save TP/FP/FN/UNK labels for candidates
- `GET /diagnostics/labels/{run_id}` -- retrieve labels for a run
- `POST /diagnostics/gold-set/export` -- export labeled queries as gold.json
- `POST /diagnostics/gold-set/regression` -- run regression, return pass/fail results
- `GET /diagnostics/tables` -- list bibliographic DB tables with row counts
- `GET /diagnostics/tables/{name}/rows` -- paginated read-only table browser

**Deliverables:**
1. `QueryDebugger.tsx`:
   - Query input with configurable limit
   - Three-panel layout: Query Plan (JSON tree) | SQL | Results
   - Execution timing breakdown (compile time, SQL time, total)
   - Result table with TP/FP/FN/UNK label buttons per row
   - Issue tagging dropdown per candidate (parser_error, normalization_issue, missing_alias, etc.)
   - False negative search: text input to find records that should have matched
   - Gold set management: export labeled queries, run regression, display results
   - Query run history (list of past runs with status)
2. `DatabaseExplorer.tsx`:
   - Table selector (records, imprints, titles, subjects, languages, agents)
   - Schema display per table
   - Row count per table
   - Paginated data browser with column sorting and search
   - Quick jump by MMS ID across all tables
3. CLI consolidation: merge `app/qa.py` regression logic into `app/cli.py` as a `regression` subcommand

**Dependencies:** Phase 0 complete. Phase 1 running in parallel is fine.

**Criteria to exit:**
- Can run a query, see plan + SQL + results side by side
- Can label results as TP/FP/FN/UNK and tag issues
- Can search for false negatives
- Can export gold set and run regression tests
- DB Explorer shows all 6 tables with pagination and filtering
- CLI `regression` subcommand works and `app/qa.py` is deprecated
- QA tool pages 0-5 functionality fully covered

**What this enables:** The Streamlit QA Tool (`app/ui_qa/`) can be marked deprecated.

---

### Phase 3: Admin Screens (1 week)

**Goal:** Build Publisher Authorities and System Health pages. Lower risk, lower complexity.

**Deliverables:**
1. `Publishers.tsx`:
   - Authority list table (TanStack Table) with variant counts, imprint counts
   - Filter by type (printing_house, unresearched, etc.)
   - Expandable row showing all variant forms
   - Links to affected imprints
2. `Health.tsx`:
   - API health status (from `GET /health`)
   - Database connectivity indicator
   - Database file sizes and last-modified timestamps
   - Health indicator in top navigation bar (green/red dot, always visible)

**Dependencies:** Phase 0 complete.

**Criteria to exit:** Both pages render with real data. Health indicator visible in nav bar across all screens.

---

### Phase 4: Polish, Integration & Testing (1-2 weeks)

**Goal:** Cross-screen integration, shared components, testing, and production readiness.

**Deliverables:**
1. **Cross-screen integration:**
   - From Chat results: "Flag data issue" button -> opens Workbench filtered to that record
   - From Workbench cluster: "Ask agent about this" -> opens Agent Chat pre-filled
   - From Query Debugger FN: link to Workbench for normalization fix
   - Health indicator in nav bar connected to real health endpoint
2. **Shared component library finalization:**
   - `ConfidenceBadge` -- consistent everywhere (chat, workbench, debugger)
   - `CandidateCard` -- used in chat, query debugger, and DB explorer
   - `PrimoLink` -- single configurable component (institution via env var)
   - `FieldBadge` -- date/place/publisher/agent badges consistent
3. **Testing:**
   - Vitest unit tests for utility functions (Primo URL, date formatting, confidence colors)
   - React Testing Library tests for CandidateCard, ConfidenceBadge, Chat message flow
   - Playwright E2E: send query -> see results -> follow-up; submit correction -> verify update
   - MSW mocks for all API endpoints
4. **Build & deployment:**
   - Production build validation (`npm run build` succeeds, no TypeScript errors)
   - Vite configuration for production API URL
   - Update `CLAUDE.md` with new screen inventory and URLs

**Dependencies:** Phases 1, 2, 3 complete.

**Criteria to exit:** All 9 screens functional. E2E tests pass. No cross-screen broken links. Production build succeeds.

---

### Phase 5: Retirement & Cleanup (1 week)

**Goal:** Remove deprecated code, update documentation, archive artifacts.

**Deliverables:**
1. **Delete Streamlit Chat UI:**
   - Remove `app/ui_chat/` directory (449 lines)
   - Remove Streamlit dependency from `pyproject.toml` (if no other Streamlit consumers remain)
   - Remove `poetry run streamlit run app/ui_chat/main.py` from docs
2. **Delete Streamlit QA Tool:**
   - Remove `app/ui_qa/` directory (3,531 lines)
   - Remove QA Tool launch commands from docs
   - Keep `data/qa/qa.db` (historical QA data) -- do not delete
   - Keep `data/qa/gold.json` -- still used by CLI regression subcommand
3. **Delete standalone QA runner:**
   - Remove `app/qa.py` (187 lines)
   - Update `CLAUDE.md` to reference `python -m app.cli regression` instead
4. **Archive Streamlit code:**
   - Move deleted files to `archive/retired_streamlit/` with a README noting retirement date and replacement location
   - Tag git commit as `ui-migration-complete`
5. **Documentation updates:**
   - Update `CLAUDE.md`: remove all Streamlit references, update UI section, update QA Tool section
   - Update `app/ui_qa/README.md` -> redirect to Query Debugger docs
   - Update API docs in `CLAUDE.md` with new diagnostic endpoints
6. **Dependency cleanup:**
   - Remove `streamlit` from `pyproject.toml` if fully unused
   - Remove any QA-specific Streamlit deps
   - Run `poetry lock` to clean lockfile

**Dependencies:** Phase 4 complete. All functionality validated in React.

**Criteria to exit:**
- `app/ui_chat/` directory does not exist
- `app/ui_qa/` directory does not exist
- `app/qa.py` does not exist
- `streamlit` not in `pyproject.toml` (if fully unused)
- All tests pass
- `CLAUDE.md` has no references to retired UIs
- Archive directory has retired code with README

---

## 3. Deletion Criteria

A Streamlit UI is safe to delete when ALL of the following are true:

1. **Feature parity:** Every user-facing feature of the Streamlit UI has a working equivalent in the React app. Verified by a feature checklist comparison (see section 4).
2. **Data continuity:** Any persistent data (QA labels, gold sets, session history) is either migrated, accessible via new UI, or explicitly archived.
3. **No active users:** No one is actively using the Streamlit UI for daily work. Confirmed by asking the team.
4. **Tests pass:** The React replacement passes equivalent test coverage (E2E for critical paths, component tests for interactive elements).
5. **Documentation updated:** All references in `CLAUDE.md`, READMEs, and inline comments point to the new UI.
6. **Archived:** The code is preserved in `archive/retired_streamlit/` before deletion from active tree.

---

## 4. Feature Parity Checklists

### Chat UI -> React Chat Screen

| Feature | Streamlit Chat UI | React Chat | Status |
|---------|-------------------|------------|--------|
| Send NL query | Yes | Phase 1 | - |
| Display formatted results | Yes | Phase 1 | - |
| Primo links | Yes (TAU) | Phase 1 (configurable) | - |
| Follow-up suggestions | Yes | Phase 1 | - |
| Session management | Yes (via API) | Phase 1 | - |
| Evidence display | Yes (expander) | Phase 1 (inline) | - |
| Streaming progress | No (HTTP only) | Phase 1 (WebSocket) | Upgrade |
| Two-phase flow vis | No | Phase 1 | Upgrade |
| Interpretation confidence | No | Phase 1 | Upgrade |

### QA Tool -> React Query Debugger + DB Explorer

| Feature | Streamlit QA Tool | React Replacement | Status |
|---------|-------------------|-------------------|--------|
| Query execution + plan view | Pages 0-1 | Query Debugger (Phase 2) | - |
| TP/FP/FN/UNK labeling | Page 1 | Query Debugger (Phase 2) | - |
| Issue tagging | Page 1 | Query Debugger (Phase 2) | - |
| False negative search | Page 2 | Query Debugger (Phase 2) | - |
| Coverage dashboard | Page 3 | Coverage Dashboard (existing) | Already done |
| Gold set export | Page 4 | Query Debugger (Phase 2) | - |
| Regression runner | Page 4 + `app/qa.py` | CLI subcommand + Debugger display (Phase 2) | - |
| DB Explorer | Page 5 | DB Explorer (Phase 2) | - |
| QA Sessions | Page 0 | Query run history (Phase 2) | Simplified |
| Wizard | `_wizard.py` (808 lines) | **Dropped** | Archive only |

### QA Regression Runner -> CLI Subcommand

| Feature | `app/qa.py` | `app/cli.py regression` | Status |
|---------|-------------|-------------------------|--------|
| Run gold set regression | Yes | Phase 2 | - |
| Verbose output | Yes | Phase 2 | - |
| Log file output | Yes | Phase 2 | - |
| Exit code for CI | Yes | Phase 2 | - |

---

## 5. Temporary Compatibility

During the transition (Phases 1-4), the following temporary accommodations are needed:

1. **Both Chat UIs run simultaneously.** The Streamlit Chat UI continues to work at its existing URL (`streamlit run app/ui_chat/main.py`). The React Chat screen is available at `localhost:5173/` (Vite dev server). Users can choose which to use. No migration of chat sessions needed (both use the same API sessions).

2. **Both QA tools run simultaneously.** The Streamlit QA Tool continues to work during Phase 2 development. QA work in progress can be completed in Streamlit. New QA work should start in React once Phase 2 is complete.

3. **Old routes redirect.** After Phase 0, the React app redirects `/` to `/operator/coverage`, `/workbench` to `/operator/workbench`, `/agent` to `/operator/agent`, `/review` to `/operator/review`. These redirects are removed in Phase 4 when Chat becomes the landing page at `/`.

4. **`app/qa.py` remains alongside CLI subcommand.** During Phase 2, both the standalone `app/qa.py` and the new `app/cli.py regression` subcommand work. The standalone file is removed in Phase 5.

5. **Dual Primo URL configuration.** During Phases 1-4, the React app reads Primo institution from `VITE_PRIMO_INSTITUTION` env var (defaulting to TAU). The Streamlit Chat UI retains its hardcoded TAU scheme. Consolidated in Phase 5.

---

## 6. What Gets Archived vs Deleted

### Archive (move to `archive/retired_streamlit/`)

| Item | Reason to Archive |
|------|-------------------|
| `app/ui_chat/main.py`, `config.py` | Reference for Primo URL generation logic, candidate card formatting |
| `app/ui_qa/pages/_wizard.py` | 808-line experimental workflow, not migrated but may inform future guided flows |
| `app/ui_qa/wizard_components.py` | Associated wizard components |
| `app/ui_qa/db.py` | QA database schema reference |
| `app/qa.py` | Regression runner logic reference |

### Delete (no archive needed, logic fully captured in React)

| Item | Reason |
|------|--------|
| `app/ui_qa/pages/0_qa_sessions.py` through `5_db_explorer.py` | Logic replicated in React Query Debugger |
| `app/ui_qa/main.py`, `config.py`, `__init__.py` | Streamlit entry points, no unique logic |
| `app/ui_chat/__init__.py` | Empty init file |

### Keep (not part of migration)

| Item | Reason |
|------|--------|
| `data/qa/qa.db` | Historical QA data, may be useful for analysis |
| `data/qa/gold.json` | Active regression test data, used by CLI |
| `app/ui_qa/README.md`, `USAGE.md` | Update to redirect to new docs, then archive |

---

## 7. Early Retirements

These can be retired before the full migration is complete:

1. **Streamlit Chat UI (`app/ui_chat/`)** -- Retire after Phase 1. It is only 449 lines and the thinnest wrapper. The React Chat screen is strictly superior (streaming, two-phase visualization, evidence display). No unique logic to preserve except Primo URL generation, which is ported in Phase 1.

2. **`app/qa.py` standalone regression runner** -- Retire after Phase 2 CLI consolidation. The 187-line file is straightforward to merge into `app/cli.py`. No users depend on it independently.

3. **QA Wizard (`_wizard.py`)** -- Archive immediately, do not migrate. 808 lines of experimental guided workflow that is not in active use. The standard Query Debugger labeling flow replaces it.

---

## 8. Risks and Mitigations

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | WebSocket implementation in React is more complex than expected (reconnection, error handling, state sync) | Delays Phase 1 by 3-5 days | Medium | Start with HTTP-only chat (works today), add WebSocket streaming as enhancement. The Chat screen is fully functional with just `POST /chat`. |
| 2 | Query Debugger scope creep -- temptation to build more than the QA Tool offers | Delays Phase 2 by 1+ week | High | Strict feature parity checklist. "ADD" features (side-by-side comparison, timing breakdown, diff view) are Phase 4 or later. Phase 2 is parity only. |
| 3 | Diagnostic API endpoints take longer than estimated (especially regression runner endpoint) | Blocks Phase 2 frontend work | Medium | Start frontend with MSW mocks from day 1. Backend and frontend can develop in parallel. |
| 4 | QA data migration -- existing labels in `data/qa/qa.db` need to be accessible from new UI | Data loss or inaccessible history | Low | The QA database is a separate SQLite file. The new diagnostic API can read from it directly. No schema migration needed -- just point the endpoint at the existing file. |
| 5 | Two React apps running in dev mode confuse developers | Developer friction | Low | There is only one React app (the Workbench, extended). The "old" Workbench routes redirect to new paths. Clear dev setup docs in Phase 0. |
| 6 | Streamlit retirement breaks a workflow someone depends on | Lost capability | Medium | Enforce deletion criteria (section 3): every feature has a working replacement, verified by checklist, before any code is removed. Keep archive for 3 months. |
| 7 | Performance regression -- React app grows large enough to impact load time | Slower initial page load | Low | Vite code splitting by route is automatic. The Chat screen bundle stays separate from Workbench, Debugger, etc. Monitor build output size. |
| 8 | Landing page change from Coverage Dashboard to Chat confuses existing Workbench users | User confusion | Low | Phase 0 preserves `/operator/coverage` as the landing page. Chat becomes `/` only in Phase 4 when it is fully functional. Clear communication to the team. |

---

## 9. Timeline Summary

```
Week 1:     Phase 0 -- Foundation & Scaffolding
Weeks 2-3:  Phase 1 -- Chat Screen
Weeks 2-4:  Phase 2 -- Query Debugger + DB Explorer (overlaps with Phase 1)
Week 4:     Phase 3 -- Admin Screens (overlaps with Phase 2)
Weeks 5-6:  Phase 4 -- Polish, Integration, Testing
Week 7:     Phase 5 -- Retirement & Cleanup
```

**Total: 7 weeks** to unified UI with all old surfaces retired.

**Parallelism:** Phases 1 and 2 can overlap because they touch different screens and different API endpoints. Phase 3 can start as soon as Phase 0 is done and run alongside Phase 2. The critical path is Phase 0 -> Phase 1 -> Phase 4 -> Phase 5.

**Early wins:**
- End of Week 1: Restructured React app with 9-screen skeleton
- End of Week 3: Working Chat screen (Streamlit Chat can be retired)
- End of Week 4: Working Query Debugger (QA Tool can be retired)
- End of Week 7: All old UIs removed, single unified app

---

## 10. Definition of Done (Full Migration)

The migration is complete when:

1. A single React application at `frontend/` serves all 9 screens
2. `app/ui_chat/` directory does not exist in the active codebase
3. `app/ui_qa/` directory does not exist in the active codebase
4. `app/qa.py` does not exist in the active codebase
5. `streamlit` is not a dependency in `pyproject.toml`
6. `CLAUDE.md` references only the React UI and CLI for user-facing interfaces
7. All feature parity checklists (section 4) are 100% complete
8. E2E tests pass for: chat query flow, correction workflow, QA labeling, regression testing
9. Retired code is archived in `archive/retired_streamlit/` with a README
10. Git tagged as `ui-migration-complete`

---

## EMPIRICAL VERIFICATION ADDENDUM

**Date:** 2026-03-23
**Source:** Reports 08-11 (DB Probe, Pipeline Test, API Verify, Cross-Reference) and Report 12 (Empirical Refinements)

Empirical verification against the actual database, pipeline, and API revealed significant adjustments needed to the migration plan. The phase structure remains sound, but effort estimates, sequencing, and feature scope require correction.

### Phase 0: Foundation & Scaffolding -- NO CHANGE
Proceed as specified. No empirical findings affect scaffolding work.

### Phase 1: Chat Screen -- MODIFIED

**Changes:**

1. **Defer WebSocket streaming.** Section deliverable "useWebSocket.ts hook for streaming via WS /ws/chat" is blocked. The WebSocket handler uses the old single-phase path without intent interpretation, confidence, facets, or phase transitions. Launch Chat with HTTP-only (`POST /chat`). The full two-phase flow works via HTTP. WebSocket upgrade is a 2-3 day backend task deferred to Phase 4.

2. **Add backend micro-tasks (days 1-3 of Phase 1):**
   - Add `execution_time_ms` to `ChatResponse.metadata` (1-2 hours)
   - Forward `FacetCounts` to `ChatResponse.metadata` (2-4 hours)
   - Forward `QueryWarning[]` to `ChatResponse.metadata` (1-2 hours)
   - Resolve Primo URL approach: add to Candidate model or use batch endpoint (2-4 hours)

3. **Drop "per-filter confidence" from exit criteria.** The criterion "Interpretation confidence display (extracted filters with per-filter confidence)" is unbuildable. Filter.confidence is always null. Replace with: overall interpretation confidence only.

4. **Modify exit criteria for streaming.** Remove "WebSocket streaming shows progress indicators." Replace with: "HTTP requests show loading states and result counts."

5. **Phase 2 aggregation chart rendering** depends on backend micro-task B2 (FacetCounts forwarding). If not completed in Phase 1, aggregation charts are deferred. Aggregation text responses work immediately.

**Revised Phase 1 exit criteria:**
- Can send a natural language query via HTTP and see formatted results with evidence
- Loading states show during query execution (HTTP polling or spinner, not WebSocket streaming)
- Two-phase conversation flow works (define query then explore subgroup)
- Overall interpretation confidence is displayed
- Clarification prompts render for ambiguous queries
- Session persists across page reloads
- Primo links work for all results (via batch resolution)

### Phase 2: Query Debugger + DB Explorer -- MODIFIED

**Changes:**

1. **Do NOT overlap with Phase 1.** Original plan says Phases 1 and 2 can overlap. Revised: Phase 2 backend work is substantial (all diagnostic endpoints from scratch) and should not compete with Phase 1 backend micro-tasks for developer attention. Start Phase 2 after Phase 1 Chat is functional.

2. **Backend prerequisite expanded from 2-3 days to 4-5 days.** All diagnostic endpoints need design and implementation:
   - `POST /diagnostics/query-run` (execute + return plan/SQL/results/timing) -- 1 day
   - `GET /diagnostics/query-runs` (list past runs) -- 0.5 day
   - `POST /diagnostics/labels` + `GET /diagnostics/labels/{run_id}` -- 1 day
   - `POST /diagnostics/gold-set/export` + `POST /diagnostics/gold-set/regression` -- 1.5 days
   - `GET /diagnostics/tables` + `GET /diagnostics/tables/{name}/rows` (with SQL injection protection) -- 1.5 days

3. **Drop per-filter confidence visualization.** Replace with per-filter match count if feasible (how many records each filter narrowed), computed from facets.

4. **DB Explorer scope expanded.** Database has 10 tables (records, imprints, titles, subjects, agents, languages, notes, publisher_authorities, publisher_variants, authority_enrichment), not 6.

5. **Query plan access workaround.** QueryPlan is NOT in ChatResponse. Either the new `/diagnostics/query-run` endpoint must return it directly, or the debugger fetches `GET /sessions/{session_id}` and extracts the plan from the assistant message.

### Phase 3: Admin Screens -- MODIFIED

**Changes:**

1. **Split publisher work.** Read-only publisher authorities view can be built in parallel with Phase 1 (API already exists). CRUD functionality requires new backend endpoints (POST/PUT/DELETE) -- build in the Phase 3 slot.

2. **Publisher Authorities reframed.** 89% of authorities are "unresearched" stubs. The screen should emphasize a research workflow (classifying stubs, adding enrichment data) rather than simple CRUD.

3. **System Health scoped down.** Only `GET /health` exists. Build: nav bar green/red dot indicator + simple health page showing database_connected, session_store_ok, status. Defer: log viewer, metrics dashboard, interaction viewer, request rate charts (require infrastructure).

### Phase 4: Polish, Integration & Testing -- MODIFIED

**Additional tasks identified:**

1. **WebSocket two-phase upgrade** (2-3 days): If streaming UX is desired for Chat, the WebSocket handler must be upgraded to use the intent agent and two-phase flow. This is the most impactful Phase 4 addition.
2. **Corrections API extensions**: Add `date` to `CorrectionRequest.field`; add `search`/`source`/date-range params to corrections history; build revert endpoint.
3. **Issues Workbench reframe**: Replace confidence slider with method-based filtering. Add Hebrew-script publisher tab. Add agent normalization tab.
4. **Evidence quality fixes** (backend): Fix subject evidence null value, fix agent evidence "marc:unknown" source.

### Phase 5: Retirement & Cleanup -- NO CHANGE
Proceed as specified.

### Revised Timeline

```
Week 1:     Phase 0 -- Foundation & Scaffolding
            Phase 1 backend micro-tasks (execution_time, facets, warnings)
Weeks 2-3:  Phase 1 -- Chat Screen (HTTP-only)
            Phase 3a -- Publisher Authorities read-only (1-2 days, in parallel)
Week 4:     Phase 2 backend -- Diagnostics API endpoints (4-5 days)
Weeks 4-5:  Phase 2 frontend -- Query Debugger + DB Explorer
Week 5:     Phase 3b -- Publisher CRUD + System Health basic
Weeks 6-7:  Phase 4 -- Polish, Integration, WebSocket upgrade, Testing
Week 8:     Phase 5 -- Retirement & Cleanup
```

**Total: 8 weeks** (was 7). The extra week accounts for diagnostic endpoint backend work being larger than estimated and Phases 1/2 being sequential rather than parallel.

### Section 4 Feature Parity Checklist -- Corrections

**Chat UI -> React Chat Screen:**

| Feature | Status Change |
|---------|---------------|
| Streaming progress | Changed from "Phase 1 (WebSocket)" to "Deferred to Phase 4 (WebSocket upgrade needed)" |
| Two-phase flow vis | Unchanged, works via HTTP |
| Interpretation confidence | Changed from "per-filter" to "overall only (per-filter always null)" |

**QA Tool -> React Query Debugger:**

| Feature | Status Change |
|---------|---------------|
| Query execution + plan view | Requires 4-5 days of new backend work, not 2-3 days |
| Per-filter confidence | DROPPED (always null) |

### Section 8 Risks -- Updates

| # | Risk | Revised Status |
|---|------|---------------|
| 1 | WebSocket complexity | **ELEVATED.** Confirmed: WebSocket lacks two-phase entirely. Mitigation: launch HTTP-only. |
| 3 | Diagnostic API time | **ELEVATED to CRITICAL.** Zero endpoints exist. Revised from 2-3 days to 4-5 days. |
| 8 | WebSocket old code path | **CONFIRMED as fact.** No longer a risk -- it is a known constraint. |

**New risks:**

| # | Risk | Impact | Mitigation |
|---|------|--------|------------|
| 9 | Phase 2 aggregation charts unbuildable without facets forwarding | Degraded Chat Phase 2 UX | Backend micro-task B2 in Phase 1 |
| 10 | Issues Workbench appears empty (121 items) | Perceived low value | Reframe as improvement opportunities |
| 11 | Publisher variant matching gap (1/16 Elzevir match) | Chat users miss records | Document as known limitation |
| 12 | Subject retry false broadening | Misleading results | Forward QueryWarning, display prominently |

**Full detail:** See Report 12 (Empirical Refinements) for complete change tables, backend task inventory (12-15 developer-days of new work), and revised screen ratings.
