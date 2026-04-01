# Consolidated Executive Report: UI Evaluation and Redesign
# Rare Books Bot

**Date:** 2026-03-23
**Status:** Final consolidated report
**Scope:** Full evaluation of all UI surfaces, alignment assessment, redundancy analysis, and migration plan for the Rare Books Bot project
**Author:** Technical Writer and Product Strategist (synthesized from section reports 01-07)

---

## 1. Executive Summary

The Rare Books Bot project is a conversational discovery system that enables scholars and librarians to query a rare book collection using natural language and receive deterministic, evidence-backed answers traceable to specific MARC XML fields. The project has accumulated **five distinct user-facing interfaces** across three technology stacks (React, Streamlit, Typer CLI), plus a shared FastAPI backend. This fragmentation is the single most important architectural issue facing the project today.

The evaluation reveals a critical **investment inversion**: the highest-quality technical implementation -- a polished React SPA with 3,160 lines of TypeScript -- was built for an internal metadata operations tool (the Metadata Co-pilot Workbench), while the actual product -- the conversational discovery chatbot -- received only a 449-line Streamlit prototype. The backend powering the chatbot is sophisticated (two-phase conversation model, intent agent with confidence scoring, corpus exploration with aggregation and enrichment), but the frontend surface does not expose these capabilities. Scholars and librarians, the project's primary users, are the least well-served persona.

The recommended path forward is to consolidate all UI surfaces into a **single React application** organized into four tiers: (1) the conversational discovery bot as the landing page and centerpiece, (2) operator observability screens for metadata quality monitoring and correction, (3) diagnostic screens for query pipeline testing and debugging, and (4) administrative screens for authority management and system health. The existing React Workbench code becomes the foundation -- its component architecture, API patterns, and design system are production-grade and extensible. The two Streamlit applications (Chat UI and QA Tool) are retired after their functionality is rebuilt in React with significant enhancements, most notably WebSocket streaming and two-phase conversation visualization.

The migration is estimated at **7 weeks across 6 phases**, with the Chat screen (Phase 1) and Query Debugger (Phase 2) as the highest-impact deliverables. The existing React code (TanStack Query/Table patterns, Tailwind design system, typed API layer) carries forward intact into the new routing structure. At completion, the project will have a single React application serving 9 screens, a single CLI for developer operations, and a single FastAPI backend -- down from the current 5 UI surfaces with 3 technology stacks.

---

## 2. Inventory of Existing UIs

| # | UI | Location | Tech Stack | Port | LOC | Target User | API Dependency | Status |
|---|-----|----------|-----------|------|-----|-------------|----------------|--------|
| 1 | Metadata Co-pilot Workbench | `frontend/` | React 19 + Vite 8 + Tailwind + TS | 5173 | ~3,160 | Librarians / Metadata curators | HTTP to FastAPI :8000 (`/metadata/*`) | Active |
| 2 | QA Tool | `app/ui_qa/` | Streamlit (multi-page) | 8501 | ~3,530 | Developers / QA testers | In-process (direct library calls) | Active |
| 3 | Chat UI | `app/ui_chat/` | Streamlit (single-page) | 8501 | ~450 | Scholars / Researchers | HTTP to FastAPI :8000 (`/chat`) | Active |
| 4 | CLI | `app/cli.py` | Typer | N/A | ~520 | Developers / Operators | In-process | Active |
| 5 | QA Regression Runner | `app/qa.py` | Typer | N/A | ~190 | CI/CD pipelines | In-process | Active |
| 6 | FastAPI Backend (shared) | `app/api/` | FastAPI + Pydantic | 8000 | ~3,220 | All frontend clients | N/A (is the API) | Active |

**Technology stack fragmentation:** Three distinct UI frameworks (React, Streamlit, Typer) across two languages (TypeScript, Python) with two build systems, two dependency trees, and no shared component library.

**API dependency map:**
```
                          FastAPI Backend (:8000)
                         /        |        \
                        /         |         \
    React Workbench (:5173)  Chat UI (:8501)  Swagger/ReDoc (:8000/docs)
    [HTTP: /metadata/*]    [HTTP: /chat]     [auto-generated]

    QA Tool (:8501)         CLI
    [in-process, no API]    [in-process, no API]
```

---

## 3. Per-UI Evaluation

### 3.1 Metadata Co-pilot Workbench (React SPA)

**Rating: VALUABLE** | UX: High | Maintainability: High | Technical Quality: High

**Strengths:**
- The strongest UI in the project. Production-grade React with TanStack Table/Query, proper TypeScript generics, composable hooks, skeleton loading states, and error boundaries.
- Four well-designed pages: Dashboard (coverage overview with pie charts, confidence bands), Workbench (issue triage with inline editing, batch corrections, cluster view), Agent Chat (conversational HITL with proposal review), Review (audit trail with filtering and export).
- Clean separation of concerns: API layer, custom hooks, type definitions, presentation components.

**Weaknesses:**
- Serves internal metadata curators, not the primary user persona (scholars/researchers).
- No connection to the chatbot -- a curator cannot see which bot queries would improve with a given fix.
- Primo URL hardcoded to NLI (`primo.nli.org.il`), inconsistent with Chat UI's TAU configuration.
- No undo/rollback for corrections.

**Verdict:** The foundation for the new unified UI. Its architecture, patterns, and design system should be extended, not replaced.

### 3.2 QA Tool (Streamlit Multi-Page App)

**Rating: VALUABLE** | UX: Medium | Maintainability: Medium | Technical Quality: Medium

**Strengths:**
- Only tool for systematically measuring query pipeline accuracy (TP/FP/FN labeling).
- Uniquely valuable pages: Find Missing (false negative search), Gold Set (regression export), DB Explorer.
- Guided wizard workflow with step gating for structured QA sessions.
- 15 pre-defined canonical test queries.

**Weaknesses:**
- Streamlit page-refresh model causes jarring UX; no keyboard shortcuts for power-user labeling.
- Regression runner on Gold Set page duplicates `app/qa.py` logic.
- Direct `sqlite3` usage with inconsistent patterns (some pages bypass `db.py`).
- No test coverage for any QA tool code.
- Tests a different code path than what users experience (bypasses API, intent agent, two-phase flow).

**Verdict:** Valuable logic trapped in the wrong framework. The labeling workflow, gold set export, and false negative search must be preserved in the new UI.

### 3.3 Chat UI (Streamlit Single-Page App)

**Rating: ESSENTIAL (concept) / NICE-TO-HAVE (implementation)** | UX: Medium | Technical Quality: Medium

**Strengths:**
- The only true conversational interface -- this IS the product.
- Thoughtful bibliographic result formatting: smart date display, place canonical+raw, evidence with MARC citations, Primo links.
- Clean architectural coherence: thin client properly delegating to FastAPI.
- Follow-up suggestion buttons reduce typing.

**Weaknesses:**
- Streamlit is fundamentally wrong for a chat interface: full page reloads, no streaming, no WebSocket support.
- Does not use the backend's WebSocket endpoint despite its existence.
- 449 lines vs. the Workbench's 3,160 lines -- a stark investment inversion.
- No observability: cannot inspect query plan, confidence scores, or normalization provenance.
- Results capped at 50 with no pagination.

**Verdict:** The right idea on the wrong platform. Must be rebuilt in React with the same quality bar applied to the Workbench.

### 3.4 CLI (Typer)

**Rating: ESSENTIAL** | UX: Medium | Maintainability: High | Technical Quality: High

**Strengths:**
- Pipeline execution backbone: `parse_marc` (M1), `query` (M4).
- Artifact generation per query run (plan.json, sql.txt, candidates.json).
- Session management for testing without the API.

**Weaknesses:**
- No `index` command despite CLAUDE.md references.
- Query command bypasses the two-phase conversation flow.

**Verdict:** Solid developer tool. Keep and extend with a `regression` subcommand.

### 3.5 QA Regression Runner (Typer)

**Rating: REDUNDANT** | Maintainability: High | Architectural Coherence: High

**Strengths:**
- CI-compatible exit codes (0/1). JSON log output. Standalone executable.

**Weaknesses:**
- Duplicates QA Tool Gold Set page logic almost exactly.
- Should be a subcommand of the main CLI, not a separate Typer app.

**Verdict:** Essential functionality, redundant packaging. Merge into CLI as `regression` subcommand.

### 3.6 FastAPI Backend (Shared API Layer)

**Rating: ESSENTIAL** | Technical Quality: Medium-High | Maintainability: Medium

**Strengths:**
- Central nervous system: two-phase conversation model, intent agent with confidence scoring, corpus exploration.
- Comprehensive metadata quality API (12 endpoints).
- WebSocket streaming with progressive batched results.
- Proper Pydantic contracts, rate limiting, CORS.

**Weaknesses:**
- `main.py` at 1,300 lines combines too many concerns (should decompose).
- WebSocket handler uses old single-phase path, not the two-phase architecture.
- Coverage report regenerated on every request (no caching).
- Global mutable state instead of dependency injection.

**Verdict:** The correct architectural center. Needs decomposition and the WebSocket handler must be upgraded to match the HTTP handler's two-phase flow.

---

## 4. Feature Overlap / Redundancy Analysis

### Exact Duplicates

| ID | Feature | Location 1 | Location 2 | Resolution |
|----|---------|-----------|-----------|------------|
| D1 | Regression test runner | `app/qa.py` (CLI) | `app/ui_qa/pages/4_gold_set.py` (Streamlit) | Keep CLI version; QA Tool calls shared function |
| D2 | Primo URL generation (TAU) | `app/ui_chat/config.py` | `app/api/metadata.py` | Extract to shared module |
| D3 | Query execution pipeline | CLI, API-HTTP, API-WS, QA Tool | 4 separate instantiations | Standardize on `QueryService` |

### Partial Overlaps

| ID | Feature | Difference | Resolution |
|----|---------|-----------|------------|
| O1 | HTTP /chat vs WS /ws/chat | HTTP uses full two-phase flow; WS uses old single-phase path | Upgrade WS or deprecate in favor of SSE |
| O2 | QA Dashboard vs Workbench Dashboard | QA tracks query-level quality; Workbench tracks field-level normalization | Complementary -- unify in single app |
| O3 | QA DB Explorer vs Workbench Issues | Generic browsing vs. correction authoring | Different purposes; keep both in new UI |
| O4 | Primo URLs: TAU vs NLI | Chat UI hardcodes TAU; Workbench hardcodes NLI | Single configurable scheme |
| O5 | Chat sessions vs QA sessions | Different concepts (conversation vs. testing workflow) | No merge; rename QA sessions to "QA workflows" |

### Experience Fragmentation

- **NL query is available in 4 places** (CLI, Chat UI, QA Tool, API directly) with different post-query capabilities in each.
- **Correction workflows split across UIs**: QA Tool identifies query-level issues but cannot submit corrections; users must switch to the Workbench.
- **Three code paths for query execution**: HTTP (full two-phase), WebSocket (single-phase), CLI/QA (direct library call) -- QA regression tests a different path than what users experience.

---

## 5. Inferred Core Project Goal

**Rare Books Bot is a conversational discovery system that lets scholars and librarians query a rare book collection using natural language and receive deterministic, evidence-backed answers traceable to specific MARC XML fields.**

The distinguishing characteristic is that this is NOT a search engine or a RAG system. It is an **evidence-first query engine with a conversational surface**. The contract is: every answer must show exactly which MARC fields caused each record to appear.

### Primary Users (in priority order)

1. **Bibliographic Researchers / Scholars** -- The person who types "books printed in Venice in the 16th century" and needs to trust the answer. They care about complete recall, evidence, and exploratory analysis.
2. **Metadata Librarians / Catalogers** -- The person who maintains data quality. They care about normalization coverage, authority files, and correction audit trails.
3. **Developers / QA Testers** -- The person who validates pipeline correctness. They care about labeling, regression testing, and query plan inspection.

### Core Use Cases (tiered)

| Tier | Use Case | Description |
|------|----------|-------------|
| **1: Core Discovery** | Natural language query | Deterministic result sets with MARC field evidence |
| **1: Core Discovery** | Two-phase exploration | Define result set (Phase 1) then aggregate/refine/enrich (Phase 2) |
| **1: Core Discovery** | Multi-turn refinement | Narrow or redirect within a session |
| **2: Data Quality** | Normalization improvement | HITL corrections via specialist agents |
| **2: Data Quality** | Authority maintenance | Publisher, place, date mapping tables |
| **3: Validation** | Query pipeline QA | Label results, build gold sets, regression testing |

### The Centerpiece

The **two-phase conversational query engine** is the center of the product:
1. Intent Agent -- interprets natural language with confidence scoring
2. Query Pipeline -- compiles QueryPlan via LLM, generates SQL, extracts evidence
3. Exploration Agent -- classifies follow-up intents (aggregation, refinement, comparison, enrichment)
4. Aggregation Engine -- deterministic SQL aggregations over result sets
5. Session Management -- multi-turn state with phase tracking

This is approximately 5,000+ lines of well-structured Python implementing a genuine conversational research assistant.

---

## 6. Assessment of Current UIs vs. Project Goal

### Alignment Ratings

| UI | Rating | Rationale |
|----|--------|-----------|
| Chat UI (Streamlit) | **ESSENTIAL concept / NICE-TO-HAVE implementation** | IS the product, but a thin prototype that does not surface the backend's capabilities |
| Metadata Workbench (React) | **VALUABLE** | Directly enables bot accuracy through data quality, but serves a different persona |
| QA Tool (Streamlit) | **VALUABLE** | Necessary measurement infrastructure, but tests a different code path than users experience |
| CLI (Typer) | **ESSENTIAL** | Pipeline execution backbone for developers |
| QA Regression Runner (Typer) | **REDUNDANT** | Essential functionality, redundant packaging |
| FastAPI Backend | **ESSENTIAL** | Central nervous system; the two-phase model is the project's most sophisticated component |

### Key Alignment Gaps

1. **Investment inversion.** The highest-quality technical implementation (React, 3,160 lines) serves an internal tool. The actual product (Chat UI, 449 lines of Streamlit) is a prototype. This is the single most important alignment issue.

2. **Code path divergence.** Three different code paths for query execution means QA regression tests validate a different path than what users experience. Bugs in the intent agent, exploration agent, or session management are not caught.

3. **Missing observability bridge.** No UI traces the full chain: user asked X -> intent agent parsed as Y with confidence Z -> SQL returned N records -> record R matched because MARC field 264$b contained value V.

4. **User persona gap.** Three personas exist but only metadata curators are well-served. Scholars/librarians (the primary users) have the weakest interface.

---

## 7. Principles for the New Integrated UI

| # | Principle | Description |
|---|-----------|-------------|
| 1 | **Bot-Centered Architecture** | The conversational interface is the primary surface. Every other screen exists to support, diagnose, or improve the bot's outputs. Users land on the chat. |
| 2 | **Progressive Disclosure** | Scholars see a clean chat. Operators see confidence scores and coverage gaps. Developers see query plans and SQL. Each layer is opt-in, never forced. |
| 3 | **Evidence-First Display** | Confidence scores, MARC field citations, and normalization chains are first-class UI elements -- not hidden footnotes. |
| 4 | **Observable by Default** | Query interpretation confidence, filter extraction, phase transitions, and execution timing are displayed in real-time, not buried in logs. |
| 5 | **Single Source of Truth** | One Primo URL scheme (configurable), one query execution path (via `/chat`), one correction workflow, one session system. |
| 6 | **Composable Over Monolithic** | Small, reusable components: a `CandidateCard` renders the same way in chat results, QA review, and record inspection. A `ConfidenceBadge` is consistent everywhere. |

---

## 8. Recommended Information Architecture / Main Screens

### 9 Screens in 4 Tiers

```
Tier 1: Primary User Experience
  /                           Chat (Landing Page)

Tier 2: Operator Observability
  /operator/coverage          Coverage Dashboard
  /operator/workbench         Issues Workbench
  /operator/agent             Agent Chat
  /operator/review            Correction Audit Trail

Tier 3: Diagnostics / QA
  /diagnostics/query          Query Debugger
  /diagnostics/db             Database Explorer

Tier 4: Admin / Configuration
  /admin/publishers           Publisher Authorities
  /admin/health               System Health
```

### Screen Descriptions

| # | Screen | Route | Purpose | Source |
|---|--------|-------|---------|--------|
| 1 | **Chat** | `/` | Full-width conversational interface with two-phase flow visualization, inline result cards with evidence, WebSocket streaming, follow-up chips, session management. THE PRODUCT. | New (replaces Streamlit Chat UI) |
| 2 | **Coverage Dashboard** | `/operator/coverage` | Per-field coverage bars, confidence band distribution, gap summary cards, method distribution charts, quality score trending. | Existing React Dashboard (enhanced) |
| 3 | **Issues Workbench** | `/operator/workbench` | Low-confidence record triage with sortable/paginated TanStack Table, inline editable cells, batch corrections, cluster view, correction impact preview. | Existing React Workbench (enhanced) |
| 4 | **Agent Chat** | `/operator/agent` | Specialist normalization agents with proposal tables (approve/reject/edit), coverage sidebar, quick action buttons, correction preview before commit. | Existing React AgentChat (enhanced) |
| 5 | **Correction Audit Trail** | `/operator/review` | Correction history with field/source/date filtering, diff view, revert capability, CSV/JSON export. | Existing React Review (enhanced) |
| 6 | **Query Debugger** | `/diagnostics/query` | Query plan inspector (JSON tree), SQL viewer, result labeling (TP/FP/FN/UNK), issue tagging, false negative search, gold set export, regression runner display, execution timing. | New (replaces Streamlit QA Tool) |
| 7 | **Database Explorer** | `/diagnostics/db` | Read-only table browser with schema display, column search, pagination, MMS ID jump, column statistics. | New (replaces QA DB Explorer) |
| 8 | **Publisher Authorities** | `/admin/publishers` | Authority list with variant counts, type filtering, expandable variant detail, match preview. | New |
| 9 | **System Health** | `/admin/health` | API health status, database connectivity, error log, interaction log viewer, request rate charts. | New |

### Navigation Model

```
+------------------------------------------------------------------+
|  Rare Books Bot                                    [Health: o]    |
|                                                    [User v]       |
+------------------------------------------------------------------+
|                                                                   |
|  [ Chat ]                                                         |
|                                                                   |
|  Operator                                                         |
|    [ Coverage Dashboard ]                                         |
|    [ Issues Workbench ]                                           |
|    [ Agent Chat ]                                                 |
|    [ Correction Review ]                                          |
|                                                                   |
|  Diagnostics                                                      |
|    [ Query Debugger ]                                             |
|    [ Database Explorer ]                                          |
|                                                                   |
|  Admin                                                            |
|    [ Publisher Authorities ]                                       |
|    [ System Health ]                                              |
|                                                                   |
+------------------------------------------------------------------+
```

The sidebar collapses to icons on narrow viewports. The Chat page uses full viewport width (sidebar hidden by default, accessible via hamburger). Operator/Diagnostics/Admin pages show the sidebar.

---

## 9. Observability and Debugging Capabilities

### Must-Have (Ship in Phase 1-2)

| # | Capability | Where | Description |
|---|-----------|-------|-------------|
| 1 | Query Interpretation Transparency | Chat | Show extracted filters with per-filter confidence, overall interpretation score, what the bot "understood" before executing |
| 2 | Conversation Phase Indicator | Chat | Visual indicator showing Phase 1 (Defining Query) vs Phase 2 (Exploring Results) |
| 3 | Execution Metrics | Chat (collapsible) | Query compilation time, SQL execution time, total response time, result count |
| 4 | Evidence Chain | Chat + Query Debugger | Per result: which filters matched, which MARC fields provided evidence, confidence per item, normalization provenance (raw -> canonical with method) |
| 5 | Data Quality Indicators | Coverage Dashboard + Chat | Coverage health per field; warnings on results with low-confidence normalizations |
| 6 | Session State Visibility | Chat sidebar | Session ID, active subgroup size, conversation history, phase transition log |
| 7 | Correction Impact Tracking | Workbench + Agent Chat | Before/after counts, records affected, coverage delta |
| 8 | API Health Status | Navigation bar (all screens) | Green/red dot for database connectivity |

### Nice-to-Have (Phase 4+)

| # | Capability | Where |
|---|-----------|-------|
| 1 | Quality Score Trending | Coverage Dashboard |
| 2 | Query Analytics (common patterns, confidence averages, zero-result rate) | System Health |
| 3 | Performance Dashboard (p50/p95/p99 response times, cache hit rate) | System Health |
| 4 | Interaction Heatmap (most common corrections, agent acceptance rate) | Coverage Dashboard |
| 5 | Diff View (before/after corrections, query plan comparison) | Workbench + Query Debugger |
| 6 | Full Session Export (messages, plans, results) | Chat |

---

## 10. Recommended Frontend Technology: React

### Decision: **React** (continue with existing stack)

### Justification

| Factor | React (Continue) | Angular (Switch) | Verdict |
|--------|------------------|-------------------|---------|
| Existing investment | 3,160 lines of production-grade TypeScript | Would discard all existing code | React wins |
| Team competence | Demonstrated fluency with React 19, hooks, TanStack, Tailwind | Unknown | React wins |
| Chat UX fit | Component model maps naturally to WebSocket streaming and complex local state | Two-way binding adds ceremony without benefit | React wins |
| Bundle size | React 19 + Vite 8 produces smaller bundles | Angular full framework is heavier | React wins |
| Ecosystem | TanStack (already in use) is React-first; deeper chat UI ecosystem | Smaller ecosystem for this domain | React wins |
| Migration cost | Zero (extend existing code) | Full rewrite of 3,160+ lines | React wins |

### Full Tech Stack

| Layer | Technology | Status | Rationale |
|-------|-----------|--------|-----------|
| **Core** | React 19 + TypeScript 5.9 + Vite 8 | Current | Latest stable, concurrent rendering, fast HMR |
| **Server State** | TanStack Query v5 | Current | Already well-implemented with cache invalidation patterns |
| **Client State** | Zustand | New | Lightweight UI state (sidebar, phase, preferences); avoids provider nesting |
| **Tables** | TanStack Table v8 | Current | Sorting, pagination, row selection already implemented |
| **Routing** | React Router v7 | Current | Nested routes for tiered architecture |
| **CSS** | Tailwind CSS v4 | Current | Utility-first, consistent with existing design |
| **Primitives** | Radix UI | New | Accessible headless components (modals, tabs, slide-overs) |
| **Charts** | Recharts v3 | Current | Adequate for current needs; add Nivo/Observable Plot when complex charts needed |
| **Testing** | Vitest + React Testing Library + Playwright + MSW | New | Unit + component + E2E + API mocking |
| **Chat streaming** | Native WebSocket + custom `useWebSocket` hook | New | Real-time progress and batch results |
| **Additional** | react-markdown, cmdk (command palette), @tanstack/react-virtual, sonner (toasts) | New | As needed |

**No full UI component library** (no Material UI, no Ant Design). The existing Tailwind + custom components approach produces a cleaner, more intentional design.

---

## 11. Migration / Decommission Plan

### 6 Phases, 7 Weeks

```
Week 1:     Phase 0 -- Foundation & Scaffolding
Weeks 2-3:  Phase 1 -- Chat Screen  [HIGHEST IMPACT]
Weeks 2-4:  Phase 2 -- Query Debugger + DB Explorer  [overlaps Phase 1]
Week 4:     Phase 3 -- Admin Screens  [overlaps Phase 2]
Weeks 5-6:  Phase 4 -- Polish, Integration, Testing
Week 7:     Phase 5 -- Retirement & Cleanup
```

#### Phase 0: Foundation & Scaffolding (Week 1)

**Goal:** Restructure the existing React app for 9-screen architecture without breaking current functionality.

**Key deliverables:**
- Restructure `frontend/src/pages/` to tiered layout (operator/, diagnostics/, admin/)
- Update `App.tsx` routing to new URL structure
- Replace `Sidebar.tsx` with tiered navigation
- Add Zustand store, shared design tokens, extended Vite proxy
- Temporary redirects from old routes for backward compatibility

**Exit criteria:** All 4 existing Workbench pages render at new URLs. Placeholder pages exist for 5 new screens.

#### Phase 1: Chat Screen (Weeks 2-3) -- HIGHEST IMPACT

**Goal:** Build the primary user-facing screen, replacing the Streamlit Chat UI.

**Key deliverables:**
- `Chat.tsx` -- full conversational interface with two-phase flow visualization
- `CandidateCard.tsx` -- reusable result card with Primo links, evidence panel
- `useWebSocket.ts` -- streaming with progress indicators
- Follow-up chips, example queries, phase indicator, session management

**Exit criteria:** Can send query, see formatted results with evidence, WebSocket streaming shows progress, two-phase flow works, Primo links functional.

**Enables:** Streamlit Chat UI (`app/ui_chat/`) marked deprecated.

#### Phase 2: Query Debugger (Weeks 2-4, overlaps Phase 1)

**Goal:** Replace QA Tool's core functionality in React.

**Backend prerequisite (first 2-3 days):** Add diagnostic API endpoints:
- `POST /diagnostics/query-run` -- execute + return plan/SQL/results/timing
- `POST /diagnostics/labels` -- save TP/FP/FN/UNK labels
- `POST /diagnostics/gold-set/export` -- export gold.json
- `POST /diagnostics/gold-set/regression` -- run regression
- `GET /diagnostics/tables/{name}/rows` -- paginated DB browser

**Key deliverables:**
- `QueryDebugger.tsx` -- three-panel layout (plan | SQL | results), labeling, issue tagging, FN search, gold set management
- `DatabaseExplorer.tsx` -- table browser with schema display, column search, MMS ID jump
- CLI consolidation: merge `app/qa.py` into `app/cli.py` as `regression` subcommand

**Exit criteria:** Feature parity with QA Tool pages 0-5. CLI `regression` works.

**Enables:** Streamlit QA Tool (`app/ui_qa/`) marked deprecated.

#### Phase 3: Admin Screens (Week 4)

**Goal:** Publisher Authorities and System Health pages.

**Key deliverables:**
- `Publishers.tsx` -- authority list, variant forms, type filtering
- `Health.tsx` -- API status, DB connectivity, health indicator in nav bar

#### Phase 4: Polish, Integration & Testing (Weeks 5-6)

**Goal:** Cross-screen integration, shared components, testing, production readiness.

**Key deliverables:**
- Cross-screen links: "Flag data issue" (Chat -> Workbench), "Ask agent" (Workbench -> Agent Chat), FN -> correction link (Debugger -> Workbench)
- Shared component finalization: `ConfidenceBadge`, `CandidateCard`, `PrimoLink`, `FieldBadge`
- Testing: Vitest unit tests, RTL component tests, Playwright E2E, MSW mocks
- Production build validation, CLAUDE.md update

#### Phase 5: Retirement & Cleanup (Week 7)

**Goal:** Remove deprecated code, update documentation, archive artifacts.

**Deletions:**
- `app/ui_chat/` (449 lines)
- `app/ui_qa/` (3,531 lines)
- `app/qa.py` (187 lines)
- `streamlit` from `pyproject.toml`

**Archives:** Wizard code, QA DB schema reference, regression runner reference -> `archive/retired_streamlit/`

**Preservation:** `data/qa/qa.db` (historical), `data/qa/gold.json` (active, used by CLI)

**Exit criteria:** Single React app at `frontend/` serves all 9 screens. No Streamlit dependencies. CLAUDE.md references only React UI and CLI. Git tagged `ui-migration-complete`.

---

## 12. Risks, Unknowns, and Open Questions

### Risks

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| 1 | WebSocket implementation complexity (reconnection, error handling, state sync) | Delays Phase 1 by 3-5 days | Medium | Start with HTTP-only chat (works today); add WebSocket as enhancement |
| 2 | Query Debugger scope creep | Delays Phase 2 by 1+ week | High | Strict feature parity checklist; "ADD" features are Phase 4+ |
| 3 | Diagnostic API endpoints take longer than estimated | Blocks Phase 2 frontend | Medium | Start frontend with MSW mocks; backend and frontend develop in parallel |
| 4 | QA data migration -- existing labels in `qa.db` need accessibility | Data loss or inaccessible history | Low | New diagnostic API reads from existing `qa.db` directly |
| 5 | Streamlit retirement breaks active workflows | Lost capability | Medium | Enforce deletion criteria: every feature has working replacement before code removal |
| 6 | Performance regression as React app grows | Slower initial page load | Low | Vite code splitting by route is automatic; monitor build output |
| 7 | Landing page change confuses Workbench users | User confusion | Low | Phase 0 preserves `/operator/coverage` as landing; Chat becomes `/` only in Phase 4 |
| 8 | WebSocket endpoint still using old single-phase path | Degraded streaming experience | Medium | Upgrade WS handler to use two-phase flow, or implement SSE on HTTP |

### Unknowns

1. **Primo institution configuration.** TAU or NLI? Both are hardcoded in different places. Needs a definitive decision before Phase 1.
2. **QA session data migration.** Are existing labels in `data/qa/qa.db` valuable enough to migrate, or is starting fresh acceptable?
3. **WebSocket vs SSE for streaming.** The WebSocket endpoint exists but uses the old code path. Should it be upgraded to two-phase, or should streaming move to SSE on the HTTP endpoint?
4. **Authentication timeline.** Explicitly postponed, but the 9-screen architecture implies different access levels (admin vs operator vs user). When does this become necessary?
5. **Deployment model.** No Docker, no deployment configuration exists. How will the unified React app be served in production? Static files from FastAPI, separate Nginx, or CDN?

### Open Questions

1. Should the CLI gain an `index` command (M3 indexing) to complete the pipeline execution surface?
2. Should the QA Wizard concept (guided step-by-step workflow) be preserved as a feature in the Query Debugger, or is it expendable?
3. What is the target for quality score trending -- periodic snapshots stored where?
4. Should the enrichment pipeline (Wikidata, NLI authorities) get its own admin screen, or is it sufficiently covered by the Agent Chat?

---

## FINAL RECOMMENDATIONS

### 1. The Single New UI

Build a **single React application** called "Rare Books Bot" with the tagline "Evidence-based bibliographic discovery." The conversational discovery bot is the landing page and centerpiece. Metadata quality, diagnostics, and administration are accessed through tiered navigation. The existing React Metadata Workbench is the code foundation -- its 3,160 lines of production-grade TypeScript (TanStack Query/Table, Tailwind, typed API layer) carry forward and are extended with 5 new screens.

### 2. Features/Components to Keep (with source)

| Feature | Source UI | Destination Screen |
|---------|-----------|-------------------|
| TanStack Table implementation (sortable, paginated, row-selectable) | React Workbench | Issues Workbench, Query Debugger, DB Explorer, Publishers |
| Coverage Dashboard (stat cards, coverage bars, gap cards, method charts) | React Workbench | Coverage Dashboard |
| Agent Chat (proposal tables, approve/reject/edit, coverage sidebar) | React Workbench | Agent Chat |
| Correction Review (audit trail, filtering, pagination, export) | React Workbench | Correction Audit Trail |
| Inline editable cells + batch toolbar | React Workbench | Issues Workbench |
| Cluster cards with priority scoring | React Workbench | Issues Workbench |
| TanStack Query patterns (cache invalidation, optimistic updates) | React Workbench | All screens |
| Tailwind CSS design system (confidence color bands) | React Workbench | All screens |
| Candidate card layout (title/author/date/place/publisher/subjects) | Streamlit Chat UI | Chat, Query Debugger |
| Smart date display (single year vs range) | Streamlit Chat UI | Shared component |
| Place display (canonical + raw with deduplication) | Streamlit Chat UI | Shared component |
| Follow-up suggestion buttons | Streamlit Chat UI | Chat |
| Example query shortcuts | Streamlit Chat UI | Chat |
| Primo URL generation (configurable institution) | Streamlit Chat UI + API | Shared `PrimoLink` component |
| TP/FP/FN/UNK labeling workflow | Streamlit QA Tool | Query Debugger |
| Issue tagging (predefined categories) | Streamlit QA Tool | Query Debugger |
| False negative search (database search for missing results) | Streamlit QA Tool | Query Debugger |
| Gold set export + regression runner display | Streamlit QA Tool | Query Debugger |
| Query plan inspection (JSON tree) | Streamlit QA Tool | Query Debugger |
| Read-only DB table browser with column search | Streamlit QA Tool | Database Explorer |
| Two-phase conversation model (Phase 1 + Phase 2) | FastAPI Backend | Chat |
| WebSocket streaming (progressive results, progress messages) | FastAPI Backend | Chat |
| Intent interpretation with confidence scoring | FastAPI Backend | Chat (with visualization) |
| Clarification flow (ambiguity detection) | FastAPI Backend | Chat |

### 3. Features/Components to Drop

| Item | Reason |
|------|--------|
| Streamlit Chat UI (`app/ui_chat/`) entire app | Replaced by React Chat screen with streaming and phase visualization |
| Streamlit QA Tool (`app/ui_qa/`) entire app | Replaced by React Query Debugger + DB Explorer |
| QA Sessions page (guided session management) | Overly complex; standard query run history suffices |
| QA Wizard (`_wizard.py`, 808 lines) | Experimental, low usage; standard labeling flow covers same ground |
| `app/qa.py` standalone regression runner | Merged into CLI as `regression` subcommand |
| Dual Primo URL schemes (TAU hardcoded + NLI hardcoded) | Consolidated to single configurable scheme |
| WebSocket old single-phase path | Either upgrade to two-phase or replace with SSE |
| Separate QA database concept | Expose through unified diagnostic API |
| Hardcoded `localhost:8000` API URL | Environment variable via Vite config |
| Emoji in CLI and QA Tool output | Per project code style |
| RAG template remnants (`chunk_rules.yaml`, `outlook_helper.yaml`, `completer.py`) | Irrelevant to MARC bibliographic records |

### 4. Proposed Screen/Module Structure (9 Screens, 4 Tiers)

```
frontend/src/pages/
  Chat.tsx                        Tier 1: Primary    -- THE PRODUCT
  operator/
    Coverage.tsx                  Tier 2: Operator   -- Data health monitoring
    Workbench.tsx                 Tier 2: Operator   -- Issue triage & correction
    AgentChat.tsx                 Tier 2: Operator   -- AI-assisted normalization
    Review.tsx                    Tier 2: Operator   -- Correction audit trail
  diagnostics/
    QueryDebugger.tsx             Tier 3: Diagnostics -- Query testing & QA
    DbExplorer.tsx                Tier 3: Diagnostics -- Database inspection
  admin/
    Publishers.tsx                Tier 4: Admin      -- Authority management
    Health.tsx                    Tier 4: Admin      -- System monitoring
```

### 5. Recommended Implementation Direction

**Start with Phase 0 + Phase 1 (Chat Screen).** This addresses the investment inversion directly by applying production-grade React engineering to the actual product. The Chat screen is the highest-impact deliverable because it:

1. Replaces the weakest UI (449-line Streamlit prototype) with the strongest technology (React + WebSocket streaming + two-phase visualization).
2. Serves the primary user persona (scholars/researchers) who are currently the least well-served.
3. Surfaces backend capabilities that are already built but invisible (intent confidence, phase transitions, aggregation, enrichment).
4. Establishes the component library (`CandidateCard`, `ConfidenceBadge`, `EvidencePanel`, `PrimoLink`) that all subsequent screens reuse.

**Phase 2 (Query Debugger) runs in parallel** and is the second priority because it retires the largest Streamlit surface (3,531 lines) and -- critically -- enables QA testing through the actual API path that users experience, closing the code path divergence gap.

By week 3, the Streamlit Chat UI can be retired. By week 4, the QA Tool can be retired. By week 7, the project has a single, unified React application with 9 screens, consistent observability, and no Streamlit dependency.

**The critical path is: Phase 0 -> Phase 1 -> Phase 4 -> Phase 5.**

---

*This report consolidates findings from section reports 01 (UI Inventory), 02 (Per-UI Evaluation), 03 (Project Goal Analysis), 04 (Alignment Assessment), 05 (Redundancy Analysis), 06 (New UI Definition), and 07 (Migration Plan). All recommendations are grounded in codebase analysis, not aspirational documentation.*

---

## EMPIRICAL VERIFICATION ADDENDUM

**Date:** 2026-03-23
**Source:** Reports 08-11 (DB Probe, Pipeline Test, API Verify, Cross-Reference) and Report 12 (Empirical Refinements)

Empirical verification against the actual database, pipeline, and API responses revealed 5 critical misalignments and multiple data reality corrections. The core recommendations of this executive report remain valid, but the following changes are required:

### Critical Corrections

1. **WebSocket streaming is not viable for Phase 1.** The WebSocket handler uses the old single-phase `compile_query()` path -- it does NOT support two-phase flow, intent interpretation, facets, or confidence scoring. **Chat must launch HTTP-only.** WebSocket upgrade is a 2-3 day backend task, deferred to Phase 4. Section 11 Phase 1 deliverable "useWebSocket.ts hook" is deferred.

2. **Diagnostic API endpoints do not exist (zero built).** Section 11 Phase 2 underestimates backend work -- it lists "first 2-3 days" for diagnostic endpoints, but ALL endpoints (`/diagnostics/query-runs`, `/diagnostics/labels`, `/diagnostics/gold-set`, `/diagnostics/tables`) must be designed and implemented from scratch. Revised estimate: 4-5 days. Phase 2 should NOT overlap with Phase 1.

3. **Per-filter confidence visualization is unbuildable.** Section 9 (Observability) item 1 calls for "confidence per filter." Filter.confidence is always null -- the LLM does not populate it. All references to per-filter confidence display (Chat query insight, Query Debugger filter contribution) must be removed or replaced with overall interpretation confidence only.

4. **FacetCounts are computed but discarded.** Phase 2 aggregation charts (bar charts, pie charts for result exploration) are promised but the facet data computed by QueryService never reaches ChatResponse. A small backend change (forwarding facets in ChatResponse.metadata) is required before aggregation visualization can work.

5. **Four-band confidence visualization is misleading for place/publisher.** Section 8 describes "confidence band distribution" for Coverage Dashboard. For place and publisher, 99%+ of records are >= 0.95 and < 1% are < 0.5. The "medium" and "low" bands are completely empty. Redesign as binary (resolved/unresolved) for these fields.

### Data Reality Corrections

6. **Only 121 low-confidence records total** (69 dates + 19 places + 33 publishers). The Issues Workbench will be nearly empty under the current "low-confidence = issue" framing. The real gaps are: 553 Hebrew-script publishers (0.95 confidence but un-transliterated), 4,366 agents with base_clean only (100%, no alias mapping), 202 unresearched publisher authorities (89% of all authorities). The Workbench must be reframed from "issue triage" to "improvement opportunities."

7. **Evidence quality has gaps.** Subject evidence value is always null (only matched_against populated). Agent evidence source shows "marc:unknown" instead of actual MARC tags. These affect the evidence panel display in Chat and Query Debugger.

8. **Publisher variant matching gap is significant.** "Elsevier" query found 1 of 16 Elzevir-family records. The CONTAINS filter misses historical Latin name forms. This is a pipeline limitation that Chat users will encounter.

### Timeline Revision

9. **Total timeline extends from 7 weeks to 8 weeks.** The extra week accounts for: (a) diagnostic endpoint backend work being larger than estimated, (b) Phases 1 and 2 should be sequential not parallel due to competing backend resources.

### Screen Ratings

| Screen | Rating |
|--------|--------|
| Chat | PARTIALLY_ALIGNED (WebSocket gap, missing facets/timing/filter confidence) |
| Coverage Dashboard | PARTIALLY_ALIGNED (binary confidence, agent gaps not highlighted) |
| Issues Workbench | PARTIALLY_ALIGNED (only 121 items, real gaps not surfaced) |
| Agent Chat | CONFIRMED |
| Correction Review | CONFIRMED |
| Query Debugger | MISALIGNED (zero diagnostic endpoints exist) |
| Database Explorer | MISALIGNED (zero diagnostic endpoints exist) |
| Publisher Authorities | PARTIALLY_ALIGNED (read-only only, no CRUD, 89% stubs) |
| System Health | PARTIALLY_ALIGNED (only basic health check exists) |

**Full detail:** See Report 12 (Empirical Refinements) for screen-by-screen change tables, backend task inventory (12-15 developer-days of newly identified work), and revised migration timeline.
