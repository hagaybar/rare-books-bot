# New UI Definition: Rare Books Bot - Beta

**Date:** 2026-03-23
**Status:** Architectural specification
**Author:** Senior Frontend Architect analysis

---

## 1. Executive Summary

The Rare Books Bot needs a single, unified React application that places the conversational discovery bot at the center while providing layered access to operator observability, data diagnostics, and administration. The current state -- three separate UI applications (React Metadata Workbench, Streamlit Chat, Streamlit QA) -- creates a fragmented experience where the best technical implementation (React) serves an internal tool instead of the product. This specification defines the replacement.

**Name:** Rare Books Bot
**Tagline:** Evidence-based bibliographic discovery

---

## 2. Core Design Principles

### 2.1 Bot-Centered Architecture
The conversational interface is the primary surface. Every other screen exists to support, diagnose, or improve the bot's outputs. Users land on the chat. Everything else is reachable from the chat or through deliberate navigation.

### 2.2 Progressive Disclosure of Complexity
Primary users (scholars, librarians) see a clean chat interface with results. Operators see confidence scores, normalization methods, and coverage gaps. Developers see query plans, SQL, and evidence chains. Each layer is opt-in, never forced.

### 2.3 Evidence-First Display
Every result shows its provenance. Confidence scores, MARC field citations, and normalization chains are first-class UI elements, not hidden footnotes. This matches the project's core contract: no narrative without evidence.

### 2.4 Observable by Default
The system's internal reasoning is always visible to those who want it. Query interpretation confidence, filter extraction, phase transitions, and execution timing are displayed in real-time -- not buried in logs.

### 2.5 Single Source of Truth
One Primo URL scheme (configurable per institution), one query execution path (via `/chat` API with two-phase flow), one correction workflow, one session management system.

### 2.6 Composable Over Monolithic
Small, reusable components that can be assembled into different screen layouts. A "CandidateCard" renders the same way in chat results, QA review, and record inspection. A "ConfidenceBadge" is consistent everywhere.

---

## 3. Information Architecture

### Tier 1: Primary User Experience (The Bot)

#### 3.1 Chat (Landing Page) -- `/`

**Purpose:** The product. Natural language bibliographic discovery with two-phase conversation support.

**Key Features:**
- Full-width conversational interface with message history
- Two-phase flow visualization: Phase 1 (query definition) shows interpretation confidence, extracted filters, and clarification prompts; Phase 2 (corpus exploration) shows aggregation results, comparisons, and refinement options
- Inline result cards showing: title (linked to Primo), author, date, place, publisher, subjects, description
- Expandable evidence panel per result: MARC field citations, confidence scores, normalization method
- Suggested follow-up chips (from API `suggested_followups`)
- Collection overview for introductory queries
- Example query shortcuts (sidebar or welcome state)
- Session management: new session, session history, resume previous
- Streaming progress indicators during query execution
- Phase indicator showing current conversation state (defining query vs. exploring results)

**Data Sources:** `POST /chat` (HTTP), `WS /ws/chat` (WebSocket for streaming)

**What changes from current Chat UI (Streamlit):**
- Moves from Streamlit's server-side rendering to client-side React for responsive interactions
- Adds real-time phase visualization (the two-phase model is invisible in Streamlit)
- Adds inline evidence display (currently collapsed in expander, often missed)
- Adds streaming via WebSocket (currently only HTTP with spinner)
- Adds candidate card component with consistent Primo URL handling
- Removes dependency on Streamlit's session state (uses API sessions instead)

#### 3.2 Results Detail Panel -- `/` (slide-over or expandable within chat)

**Purpose:** Deep-dive into a single record from any result set.

**Key Features:**
- Full bibliographic record display (all MARC-derived fields)
- Primo deep link (configurable institution)
- Raw MARC values alongside normalized values with confidence
- Normalization chain: raw -> cleaned -> alias map -> canonical (with method at each step)
- Related records (same publisher, place, date range)

**Not a separate page** -- appears as a slide-over panel when clicking a result in chat or any table.

### Tier 2: Operator Observability

#### 3.3 Coverage Dashboard -- `/operator/coverage`

**Purpose:** Monitor normalization quality across the corpus. Answer: "How healthy is our data?"

**Key Features (KEEP from React Dashboard):**
- Summary stat cards: total records, quality score, fields tracked, issues found
- Per-field coverage bars with confidence band coloring (high/medium/low/very_low)
- Gap summary cards per field (null count + flagged count)
- Method distribution pie charts with field selector
- Confidence legend

**Key Features (ADD):**
- Trend over time (quality score history, requires periodic snapshots)
- Coverage comparison: before/after correction batches
- Drill-through from any coverage metric to the relevant records
- Link from gap cards to Workbench filtered view (currently works, preserve)

**Data Sources:** `GET /metadata/coverage`

#### 3.4 Issues Workbench -- `/operator/workbench`

**Purpose:** Browse and resolve low-confidence normalizations. The HITL correction interface.

**Key Features (KEEP from React Workbench):**
- Field tabs (Date, Place, Publisher, Agent)
- Records view with sortable, paginated TanStack Table
- Confidence slider filter + method dropdown
- Inline editable cells for normalized values
- Row selection with batch toolbar
- Cluster view with expandable cluster cards
- Primo link per record

**Key Features (ADD):**
- Side-by-side raw/normalized comparison view
- Bulk correction preview before submission (matches MEMORY.md requirement: "Always show data fixes for user approval before applying to DB")
- Correction impact estimate: "This will affect N records"
- Undo last correction (within session)
- Integration with Agent Chat: "Ask agent about this cluster" button that opens agent chat pre-filled

**Data Sources:** `GET /metadata/issues`, `POST /metadata/corrections`, `POST /metadata/corrections/batch`, `GET /metadata/clusters`

#### 3.5 Agent Chat -- `/operator/agent`

**Purpose:** Interact with specialist normalization agents to analyze and resolve metadata gaps.

**Key Features (KEEP from React AgentChat):**
- Field-specific agent selection (Place, Date, Publisher, Agent)
- Conversational interface with typing indicators
- Proposal tables with Approve/Reject/Edit per row
- Approve All batch action
- Cluster summary cards with investigate buttons
- Coverage sidebar showing real-time field health
- Quick action buttons (Analyze Gaps, Propose Mappings)

**Key Features (ADD):**
- Correction preview before commit (per MEMORY.md)
- Approved corrections reflected immediately in coverage sidebar (already does query invalidation, but needs visual feedback)
- Agent reasoning expandable (show full evidence sources)
- History of agent interactions per field

**Data Sources:** `POST /metadata/agent/chat`, `POST /metadata/corrections`, `GET /metadata/coverage`

#### 3.6 Correction Audit Trail -- `/operator/review`

**Purpose:** Review all corrections applied to normalization maps.

**Key Features (KEEP from React Review):**
- Summary bar: total corrections, by source, by field
- Filter bar: field, source, search
- Correction table with timestamp, field badge, source badge, raw->canonical mapping, evidence
- CSV/JSON export
- Pagination with smart ellipsis

**Key Features (ADD):**
- Correction diff view (what changed, when, by whom/what)
- Revert capability (with confirmation)
- Filter by date range
- Link to affected records

**Data Sources:** `GET /metadata/corrections/history`

### Tier 3: Diagnostics / QA

#### 3.7 Query Debugger -- `/diagnostics/query`

**Purpose:** Test queries, inspect query plans, label results, and build regression test sets. Replaces the QA Tool (Streamlit).

**Key Features (KEEP from QA Tool):**
- Query input with configurable limit and database path
- Query plan inspector (JSON tree view of filters, confidence per filter)
- Result table with TP/FP/FN/UNK labeling
- Issue tagging per candidate (parser_error, normalization_issue, etc.)
- False negative search: find records that should have matched
- Gold set export (JSON)
- Regression test runner display

**Key Features (ADD):**
- Side-by-side comparison: query plan vs. generated SQL vs. results
- Filter-level confidence visualization (which filter contributed most/least)
- Execution timing breakdown (compile time, SQL time, format time)
- Diff between query runs (same query, different data state)
- Link from QA labels to correction workflow (close the feedback loop)

**What's DROPPED from QA Tool:**
- Separate QA sessions concept (use standard sessions instead)
- Streamlit multi-page navigation (replaced by React routing)
- Wizard page (was an experimental guided workflow, low usage)

**Data Sources:** `POST /chat` (or direct `QueryService` via new API endpoint), QA database operations (need new API endpoints: `/diagnostics/query-runs`, `/diagnostics/labels`, `/diagnostics/gold-set`)

#### 3.8 Database Explorer -- `/diagnostics/db`

**Purpose:** Read-only inspection of bibliographic database tables.

**Key Features (KEEP from QA DB Explorer):**
- Table selector (records, imprints, titles, subjects, languages, agents)
- Schema display
- Row count per table
- Paginated data browser with column search
- Sample data preview

**Key Features (ADD):**
- Quick filter by MMS ID (jump to specific record across tables)
- Full-text search within table
- Column statistics (distinct values, null counts)

**Data Sources:** New read-only API endpoints: `GET /diagnostics/tables`, `GET /diagnostics/tables/{name}/rows`

### Tier 4: Admin / Configuration

#### 3.9 Publisher Authorities -- `/admin/publishers`

**Purpose:** Manage publisher authority records and variant forms.

**Key Features:**
- Authority list with variant counts and imprint counts
- Filter by type (printing_house, unresearched, etc.)
- Expandable authority detail showing all variants
- Add/edit authority records
- Add/edit variant forms
- Match preview: "Adding this variant would match N additional imprints"

**Data Sources:** `GET /metadata/publishers`, new CRUD endpoints

#### 3.10 System Health -- `/admin/health`

**Purpose:** System operational status.

**Key Features:**
- API health status (database connectivity, session store)
- Database size and last modification
- Recent error log (tail of structured JSON logs)
- Interaction log viewer (from `interaction_logger`)
- API request rate and response time charts

**Data Sources:** `GET /health`, new admin endpoints

---

## 4. Features to Keep

From the React Metadata Workbench (all carried forward with enhancements):
1. **TanStack Table implementation** -- sortable, paginated, row-selectable tables in Workbench
2. **Coverage Dashboard** -- stat cards, coverage bars, gap cards, method distribution charts
3. **Agent Chat** -- conversational HITL with proposal tables, coverage sidebar
4. **Correction Review** -- audit trail with filters, badges, pagination, export
5. **Editable cells** -- inline edit for normalized values
6. **Batch toolbar** -- multi-select and batch operations
7. **Cluster cards** -- expandable cluster visualization
8. **TanStack Query patterns** -- query invalidation on mutations, stale time management
9. **Tailwind CSS design system** -- consistent color palette, spacing, typography
10. **Confidence visualization** -- color-coded bands (green/yellow/orange/red)

From the Streamlit Chat UI:
11. **Candidate card layout** -- title (Primo link), author, date, place, publisher, subjects, description
12. **Smart date display** -- single year vs range formatting
13. **Place display** -- canonical + raw form with smart deduplication
14. **Evidence display** -- field labels with friendly names, confidence badges
15. **Follow-up suggestion buttons**
16. **Example query shortcuts**
17. **Primo URL generation** -- configurable per institution (TAU scheme)

From the Streamlit QA Tool:
18. **TP/FP/FN/UNK labeling workflow** -- core QA capability
19. **Issue tagging** -- predefined categories for systematic issue tracking
20. **False negative search** -- database search for missing results
21. **Gold set export** -- JSON export for regression testing
22. **Regression runner integration** -- display pass/fail results
23. **Query plan inspection** -- JSON view of compiled query

From the API layer:
24. **Two-phase conversation model** -- Phase 1 (query definition with confidence) and Phase 2 (corpus exploration)
25. **Intent interpretation with confidence scoring** -- the 0.85 threshold
26. **Clarification flow** -- ambiguity detection and guidance
27. **Collection overview queries** -- introductory statistics
28. **Aggregation responses** -- top-N publishers/places/dates within subgroup
29. **WebSocket streaming** -- progressive result delivery with progress messages

---

## 5. Features to Drop

1. **Streamlit Chat UI (`app/ui_chat/`)** -- Entire application replaced by React Chat screen. Streamlit's server-side rendering model is wrong for a responsive chat interface.

2. **Streamlit QA Tool (`app/ui_qa/`)** -- Entire application replaced by React Query Debugger. The 6-page Streamlit app with its own session management, database, and navigation is unnecessary overhead when these features live in the unified React app.

3. **QA Sessions page (`0_qa_sessions.py`)** -- Overly complex guided workflow management. Standard sessions suffice.

4. **QA Wizard (`_wizard.py`)** -- 808 lines of experimental guided labeling. The standard Run+Review flow covers the same ground more simply.

5. **WebSocket endpoint (`/ws/chat`) old single-phase path** -- The WebSocket handler still uses the old single-phase query path. Either update it to use the two-phase flow or deprecate in favor of HTTP + SSE for streaming.

6. **Dual Primo URL schemes** -- The Workbench hardcodes NLI (`972NNL_INST`), the Chat UI hardcodes TAU (`972TAU_INST`), the API defaults to TAU but is env-configurable. Consolidate to a single configurable scheme.

7. **`app/qa.py` regression runner** -- Redundant standalone module. Consolidate into CLI (`app/cli.py`) as a `regression` subcommand and surface results in the Query Debugger UI.

8. **Separate QA database (`data/qa/qa.db`)** -- Merge labeling/gold-set tables into the main database or keep separate but expose through a unified API.

9. **Recharts library** -- Currently used only for pie charts on the Dashboard. Replace with a more capable charting library (see tech stack recommendation) that can also handle time series, bar charts, and other visualization needs.

---

## 6. Framework Recommendation: React

### Decision: React (continue with existing stack)

### Justification

**1. Existing investment is substantial and high-quality.**
The React Metadata Workbench represents ~3,160 lines of well-structured TypeScript across 4 pages, 3 components, a typed API layer, and custom hooks with TanStack Query. The code quality is production-grade: proper TypeScript generics, composable hooks, consistent error/loading states, accessible markup. Discarding this to switch to Angular would be wasteful.

**2. The team has demonstrated React competence.**
The existing code shows fluency with React 19, modern hooks patterns (`useCallback`, `useMemo`, `useRef`), TanStack Query mutations with optimistic updates, TanStack Table with row selection and sorting, and Tailwind CSS utility patterns. This is not boilerplate -- it reflects real architectural decisions.

**3. React is better suited to the chat-centric UX.**
The primary surface is a real-time conversational interface. React's component model (particularly with hooks and effects) maps naturally to WebSocket message handling, streaming state updates, and the complex local state management needed for proposal tables with approve/reject/edit flows. Angular's two-way binding and change detection model adds ceremony without benefit here.

**4. Bundle size and performance.**
React 19 + Vite 8 produces smaller bundles than Angular's full framework. For a tool that may run on library workstations or be embedded in other systems, this matters.

**5. Ecosystem alignment.**
TanStack Query and TanStack Table (already in use) are React-first libraries. The React ecosystem for chat UIs, markdown rendering, and real-time data visualization is deeper than Angular's.

**6. Angular would add migration cost without compensating benefit.**
Angular's strengths (dependency injection, opinionated structure, built-in forms/routing) provide value for large enterprise teams with varying skill levels. This is a single-team project where those constraints add friction rather than guardrails.

---

## 7. Full Tech Stack Recommendation

### 7.1 Core Framework
- **React 19** (current) -- Latest stable, concurrent rendering support
- **TypeScript 5.9** (current) -- Strict mode, no `any` types
- **Vite 8** (current) -- Fast HMR, tree-shaking, proxy configuration

### 7.2 State Management
- **TanStack Query v5** (current) -- Server state management, caching, invalidation, optimistic updates. Handles all API data fetching. Already well-implemented in existing hooks.
- **Zustand** (new) -- Lightweight client-side state for UI state that doesn't belong in server state: current conversation phase, selected field tab, sidebar open/closed, theme preferences. Zustand over Redux because the state needs are simple and local. Zustand over React Context because it avoids provider nesting and re-render cascading.
- **React `useState`/`useReducer`** -- Component-local state (form inputs, ephemeral UI toggles). Already the pattern used throughout.

### 7.3 Routing
- **React Router v7** (current) -- File-system-friendly route configuration. Add nested routing for the tiered information architecture:
  ```
  /                           -- Chat (primary)
  /operator/coverage          -- Coverage Dashboard
  /operator/workbench         -- Issues Workbench
  /operator/agent             -- Agent Chat
  /operator/review            -- Correction Review
  /diagnostics/query          -- Query Debugger
  /diagnostics/db             -- Database Explorer
  /admin/publishers           -- Publisher Authorities
  /admin/health               -- System Health
  ```

### 7.4 UI Framework / Design System
- **Tailwind CSS v4** (current) -- Utility-first CSS. Already in use with consistent color palette. Continue the current approach.
- **Headless UI** or **Radix UI** (new) -- Accessible, unstyled primitive components (modals, dropdowns, tabs, slide-overs, command palettes). Avoids importing a full component library while getting accessibility for free.
- **No full component library** (no Material UI, no Ant Design) -- The existing code demonstrates that Tailwind utilities + custom components produce a cleaner, more intentional design than framework components. Keep this approach.
- **Custom design tokens** -- Codify the existing color system (indigo-600 accent, gray-900/50/200 backgrounds, green/yellow/orange/red confidence bands) into a shared constants file.

### 7.5 Charting / Visualization
- **Recharts v3** (current, retain for simple charts) -- Already used for Dashboard pie charts. Adequate for pie charts and simple bar charts.
- **Observable Plot** or **Nivo** (evaluate for addition) -- For more complex visualizations needed in the Query Debugger and Coverage Dashboard: time series (quality score over time), stacked bar charts (confidence distribution evolution), treemaps (subject/publisher distribution). Observable Plot is lighter; Nivo is more React-native. Either works. Decision point: add when first complex chart is needed, not upfront.

### 7.6 Testing Strategy
- **Vitest** -- Unit tests for utility functions, hooks, and state logic. Pairs naturally with Vite.
- **React Testing Library** -- Component tests for interactive behaviors (form submissions, button clicks, table operations). Test user-visible behavior, not implementation details.
- **Playwright** -- End-to-end tests for critical paths: send a chat query and verify results appear; submit a correction and verify the table updates; label a result and export gold set.
- **MSW (Mock Service Worker)** -- API mocking for component tests. Intercept fetch/WebSocket calls and return controlled responses. Already needed because TanStack Query hooks are the primary data access layer.
- **Test priorities:**
  1. E2E: Chat query -> results displayed -> follow-up works
  2. E2E: Correction workflow -> proposal review -> approve -> coverage updates
  3. Component: Candidate card renders all fields correctly
  4. Component: Query Debugger labeling persists
  5. Unit: Primo URL generation, date formatting, confidence color mapping

### 7.7 API Integration
- **TanStack Query v5** (current) -- For all REST endpoints. Keep the existing pattern of typed API functions + custom hooks.
- **Native WebSocket API** with custom hook -- For streaming chat results. Wrap in a `useWebSocket` hook that handles connection lifecycle, reconnection, and message parsing. Consider a lightweight library like `reconnecting-websocket` for reliability.
- **Shared API types** -- Generate TypeScript types from the FastAPI Pydantic models. Either:
  - Manual sync (current approach, works at this scale)
  - `openapi-typescript` to auto-generate types from FastAPI's OpenAPI schema (recommended when endpoint count exceeds ~15)
- **API base URL** -- Environment variable (`VITE_API_BASE_URL`), defaulting to `/` with Vite proxy in development (current pattern, but extend proxy to cover `/chat`, `/health`, `/diagnostics`, `/admin`).
- **Error handling** -- Standardize on the existing `handleResponse<T>` pattern. Add a global error boundary with retry capability.

### 7.8 Additional Libraries
- **react-markdown** + **remark-gfm** -- For rendering bot responses that include markdown formatting (tables, lists, code blocks in evidence)
- **cmdk** or **kbar** -- Command palette for power users: quick navigation between screens, quick query execution, record lookup by MMS ID
- **@tanstack/react-virtual** -- Virtual scrolling for large result sets (>100 candidates) and long tables
- **date-fns** -- Date formatting (used in correction timestamps, session display). Lightweight alternative to moment/dayjs.
- **sonner** or **react-hot-toast** -- Toast notifications for correction submissions, errors, and success feedback

---

## 8. Observability Capabilities

### 8.1 Must-Have

1. **Query Interpretation Transparency**
   - Show the extracted filters from natural language query (field, operator, value, confidence per filter)
   - Display overall interpretation confidence score with visual indicator
   - Show what the bot "understood" before executing (the explanation text)
   - Visual indicator of current conversation phase (Phase 1: Defining Query, Phase 2: Exploring Results)

2. **Execution Metrics**
   - Query compilation time (NL -> QueryPlan)
   - SQL execution time
   - Total response time
   - Result count
   - All displayed per query in the chat interface (collapsible)

3. **Evidence Chain**
   - Per result: which filters matched, which MARC fields provided the evidence
   - Confidence score per evidence item
   - Normalization provenance: raw -> intermediate -> canonical (with method tag)

4. **Data Quality Indicators**
   - Coverage health per field on Dashboard (already implemented)
   - Coverage badges visible when results contain low-confidence records
   - "Data quality warning" on results where evidence relies on low-confidence normalizations

5. **Session State Visibility**
   - Current session ID
   - Active subgroup size (in Phase 2)
   - Conversation history accessible in sidebar
   - Phase transition logged and visible

6. **Correction Impact Tracking**
   - Before/after correction counts
   - Records affected by each correction
   - Coverage delta after correction batch

7. **API Health Status**
   - Database connectivity indicator in navigation (green dot / red dot)
   - Error states with actionable messages (not just "something went wrong")

### 8.2 Nice-to-Have

1. **Quality Score Trending**
   - Historical quality score chart (requires periodic snapshots)
   - Coverage change over time per field

2. **Query Analytics**
   - Most common query patterns
   - Average confidence scores
   - Clarification rate (what % of queries need clarification)
   - Zero-result rate

3. **Performance Dashboard**
   - API response time percentiles (p50, p95, p99)
   - Concurrent session count
   - Cache hit rate for query plans

4. **Interaction Heatmap**
   - Which corrections are most frequently made
   - Which agent proposals have highest acceptance rate
   - Which fields generate most QA issues

5. **Diff View**
   - Before/after for any correction
   - Query plan comparison across runs
   - Gold set evolution over time

6. **Export/Audit Trail**
   - Full session export (all messages, plans, results)
   - Correction audit log export (already exists, enhance with more context)
   - Query performance report generation

---

## 9. Navigation Model

```
+------------------------------------------------------------------+
|  Rare Books Bot                                    [Health: ●]    |
|                                                    [User ▾]       |
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

The sidebar collapses to icons on narrow viewports. The Chat page uses the full viewport width (no sidebar visible by default, accessible via hamburger menu). Operator/Diagnostics/Admin pages show the sidebar.

---

## 10. Migration Strategy (Summary)

### Phase 1: Chat Screen (highest value)
Build the React Chat page. Connect to existing `/chat` API. This replaces `app/ui_chat/` entirely. Keep Streamlit running in parallel until React chat is validated.

### Phase 2: Operator Screens (already exist)
Move existing React Metadata Workbench pages into the new app shell with updated routing. Minimal code changes -- primarily Layout/Sidebar/routing updates.

### Phase 3: Diagnostics Screens
Build Query Debugger and Database Explorer. These require new API endpoints to expose QA operations. This replaces `app/ui_qa/` entirely.

### Phase 4: Admin Screens
Build Publisher Authorities management and System Health. Lower priority.

### Phase 5: Cleanup
Remove Streamlit applications, consolidate `app/qa.py` into CLI, unify Primo URL configuration.

---

## 11. Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | React (continue) | Existing investment, team competence, chat UX fit |
| CSS | Tailwind (continue) | Utility-first scales well, consistent with existing code |
| Server state | TanStack Query (continue) | Already well-implemented, proven patterns |
| Client state | Zustand (add) | Lightweight, no provider nesting, simple API |
| Component primitives | Radix UI (add) | Accessible headless components, pairs with Tailwind |
| Routing | React Router v7 (continue) | Nested routes for tiered architecture |
| Chat streaming | WebSocket + custom hook | Real-time progress, batch results |
| Testing | Vitest + RTL + Playwright | Unit + component + E2E coverage |
| API types | Manual for now, openapi-typescript later | Right-sized for current endpoint count |
| Full UI library | None (intentional) | Tailwind + Radix gives cleaner, more intentional design |

---

## 12. File Structure (Proposed)

```
frontend/src/
├── api/
│   ├── chat.ts              # Chat and session endpoints
│   ├── metadata.ts          # Coverage, issues, corrections (existing)
│   ├── diagnostics.ts       # QA, query runs, gold set
│   ├── admin.ts             # Publisher authorities, system health
│   └── types/               # Shared API response types
│       ├── chat.ts
│       ├── metadata.ts      # (existing, moved)
│       ├── diagnostics.ts
│       └── admin.ts
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx      # Layout with collapsible sidebar
│   │   ├── Sidebar.tsx       # Tiered navigation
│   │   └── HealthIndicator.tsx
│   ├── chat/
│   │   ├── MessageBubble.tsx
│   │   ├── CandidateCard.tsx # Reusable across chat + QA
│   │   ├── EvidencePanel.tsx
│   │   ├── PhaseIndicator.tsx
│   │   ├── FollowupChips.tsx
│   │   └── QueryInsight.tsx  # Interpretation confidence display
│   ├── metadata/
│   │   ├── CoverageBar.tsx   # (from Dashboard, extracted)
│   │   ├── ConfidenceBadge.tsx
│   │   ├── EditableCell.tsx  # (existing)
│   │   ├── BatchToolbar.tsx  # (existing)
│   │   └── ClusterCard.tsx   # (existing)
│   ├── diagnostics/
│   │   ├── QueryPlanViewer.tsx
│   │   ├── LabelControls.tsx
│   │   └── GoldSetExport.tsx
│   └── shared/
│       ├── StatCard.tsx      # (from Dashboard, extracted)
│       ├── DataTable.tsx     # TanStack Table wrapper
│       ├── FilterBar.tsx
│       ├── Pagination.tsx
│       └── PrimoLink.tsx     # Configurable Primo URL
├── hooks/
│   ├── useChat.ts            # Chat API + WebSocket
│   ├── useMetadata.ts        # (existing)
│   ├── useDiagnostics.ts
│   ├── useAdmin.ts
│   └── useWebSocket.ts       # Generic WebSocket hook
├── pages/
│   ├── Chat.tsx              # Primary: conversational interface
│   ├── operator/
│   │   ├── Coverage.tsx      # (Dashboard, renamed)
│   │   ├── Workbench.tsx     # (existing)
│   │   ├── AgentChat.tsx     # (existing)
│   │   └── Review.tsx        # (existing)
│   ├── diagnostics/
│   │   ├── QueryDebugger.tsx # New: replaces QA Tool
│   │   └── DbExplorer.tsx    # New: replaces QA DB Explorer
│   └── admin/
│       ├── Publishers.tsx    # New
│       └── Health.tsx        # New
├── stores/
│   └── uiStore.ts            # Zustand: sidebar state, theme, preferences
├── lib/
│   ├── primo.ts              # Primo URL generation (configurable)
│   ├── formatters.ts         # Date, place, confidence formatting
│   └── constants.ts          # Colors, labels, configuration
├── App.tsx
├── main.tsx
└── index.css
```

---

## EMPIRICAL VERIFICATION ADDENDUM

**Date:** 2026-03-23
**Source:** Reports 08-11 (DB Probe, Pipeline Test, API Verify, Cross-Reference) and Report 12 (Empirical Refinements)

Empirical verification against the actual database, pipeline, and API revealed that 5 of 9 screens are PARTIALLY_ALIGNED, 2 are CONFIRMED, and 2 are MISALIGNED with the specifications above. The following changes to the UI definition are required:

### Section 3.1 Chat -- Changes Required

1. **Remove WebSocket streaming from initial delivery.** Section 3.1 lists `WS /ws/chat` as a data source. The WebSocket handler does NOT support two-phase flow -- it uses the old single-phase path without intent interpretation, facets, or confidence. Launch with `POST /chat` (HTTP) only. Add a polling-based progress indicator or defer streaming until the WebSocket handler is upgraded (2-3 days backend work, Phase 4).

2. **Remove "per-filter confidence" from Key Features.** The feature "Interpretation confidence display (extracted filters with per-filter confidence)" is unbuildable -- `Filter.confidence` is always null. Replace with: "Interpretation confidence display (overall confidence score from intent agent)."

3. **Add "Execution Metrics" as a backend prerequisite.** `execution_time_ms` is computed but not exposed in ChatResponse. A backend change is needed before the "Execution Metrics" observability item (Section 8.1, item 2) can be built.

4. **Primo URLs require batch resolution.** Section 3.1 implies Primo links are inline on candidates. They are NOT on the Candidate object. Use `POST /metadata/primo-urls` for batch resolution or add `primo_url` to the Candidate model.

5. **Phase 2 aggregation charts require FacetCounts forwarding.** FacetCounts are computed by QueryService but discarded before reaching ChatResponse. A backend change (forwarding in ChatResponse.metadata) is required before Phase 2 bar charts and pie charts can render.

### Section 3.3 Coverage Dashboard -- Changes Required

6. **Redesign confidence bands for binary reality.** Section 3.3 describes "confidence band coloring (high/medium/low/very_low)." For place and publisher, only two bands have data (>= 0.95 and < 0.5). The medium and low bands are empty. Use binary "resolved/unresolved" visualization for place and publisher; keep graduated bands for dates only.

7. **Lead with agent normalization.** Section 3.3 does not mention agents as a primary gap. In reality, agent normalization (100% base_clean, 0% alias-mapped, 4,366 records) is the largest coverage gap. Make it the lead metric.

8. **Drop "Trend over time" from initial scope.** No snapshot mechanism or historical data exists.

### Section 3.4 Issues Workbench -- Changes Required

9. **Reframe from "issues" to "improvement opportunities."** Only 121 low-confidence records exist across all fields. The real work is: 553 Hebrew-script publishers, 4,366 un-normalized agents, 202 unresearched publisher authorities. These are not "low confidence" -- they are normalization upgrade opportunities not captured by the current framing.

10. **Replace confidence slider with method-based filtering.** Moving the slider from 0.5 to 0.95 returns 0 results for place and publisher. Add method-based filters (base_clean / alias_map / publisher_authority) to surface the actual gaps.

11. **Note: date corrections are not supported.** `CorrectionRequest.field` accepts only `place|publisher|agent`. The workbench cannot submit date corrections without an API extension.

### Section 3.7 Query Debugger -- MISALIGNED, Significant Redesign

12. **All diagnostics API endpoints must be built from scratch.** Section 3.7 lists data sources including `/diagnostics/query-runs`, `/diagnostics/labels`, `/diagnostics/gold-set`. Zero of these exist. This is significant backend work (4-5 days) that must precede frontend development.

13. **Drop "Filter-level confidence visualization."** Filter confidence is always null. Cannot show "which filter contributed most/least."

14. **Query plan access requires session fetch.** QueryPlan is not in ChatResponse; it is stored in session messages. The debugger must fetch `GET /sessions/{session_id}` to access the plan, or the diagnostics query-run endpoint must include it.

### Section 3.8 Database Explorer -- MISALIGNED

15. **All required endpoints must be built.** `GET /diagnostics/tables` and `GET /diagnostics/tables/{name}/rows` do not exist. The database has 10 tables (not 6): records, imprints, titles, subjects, agents, languages, notes, publisher_authorities, publisher_variants, authority_enrichment.

### Section 3.9 Publisher Authorities -- Changes Required

16. **No CRUD endpoints exist.** Only `GET /metadata/publishers` (read-only) is available. POST/PUT/DELETE endpoints and the match preview endpoint must be built before editing features work.

17. **89% of authorities are "unresearched" stubs** with null enrichment data. The screen should emphasize the research workflow (classifying stubs) rather than just listing authorities.

### Section 3.10 System Health -- Scope Down

18. **Only `GET /health` exists.** All rich features (DB size, error logs, interaction viewer, request rate charts) require new endpoints and infrastructure. Build basic status page + nav bar indicator only for initial delivery.

### Section 4 Features to Keep -- Caveats

19. **Item 24 (Two-phase conversation model):** Confirmed working via HTTP. NOT available via WebSocket.
20. **Item 29 (WebSocket streaming):** Works but is single-phase only. Cannot stream Phase 1/2 transitions.
21. **Item 25 (Intent interpretation with confidence scoring):** Overall confidence works. Per-filter confidence does not.

### Section 8.1 Observability Must-Haves -- Removals

22. **Item 1:** Remove "confidence per filter" -- always null. Keep "overall interpretation confidence score."
23. **Item 3:** Execution timing requires backend change (not currently exposed).

**Full detail:** See Report 12 (Empirical Refinements) for complete screen-by-screen change tables and backend task inventory.
