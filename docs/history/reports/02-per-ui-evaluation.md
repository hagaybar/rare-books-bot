# Per-UI Deep Evaluation Report

Generated: 2026-03-23

---

## 1. Metadata Co-pilot Workbench (frontend/)

**Technology:** React 18 + TypeScript, React Router, TanStack Query, TanStack Table, Recharts, Tailwind CSS
**Size:** ~3,160 lines across 12 source files
**Routes:** 4 pages (Dashboard, Workbench, Agent Chat, Review)

### 1.1 Workflows

| Workflow | User Interactions |
|----------|------------------|
| **Coverage Overview** | Land on Dashboard -> view stat cards (total records, quality score, fields tracked, issues found) -> inspect per-field coverage bars (color-coded confidence bands) -> drill into gap summary cards -> view method distribution pie charts per field -> click a field bar to navigate to Workbench with field pre-selected |
| **Issue Triage** | Navigate to Workbench -> select field tab (date/place/publisher/agent) -> adjust confidence slider and method filter -> browse sortable, paginated issue table -> click into a record row -> inline-edit the normalized value -> save correction via API |
| **Batch Correction** | On Workbench -> select multiple rows via checkboxes -> use BatchToolbar to apply a single canonical value to all selected records -> corrections fire sequentially via mutation |
| **Cluster Review** | On Workbench -> toggle to "Clusters" view -> view cluster cards with priority scores -> click "Propose Mappings" to send message to agent -> view agent response with proposals inline |
| **Agent-Assisted Normalization** | Navigate to Agent Chat -> select field tab -> click "Start Analysis" or type free-form message -> agent returns cluster summaries and/or proposals -> approve/reject/edit individual proposals inline -> "Approve All" for batch -> coverage sidebar updates in real-time after corrections |
| **Correction Audit** | Navigate to Review -> view summary bar (total corrections, by source, by field) -> filter by field, source, or text search -> paginated correction history table -> export as CSV or JSON |

### 1.2 Core Features

- Coverage dashboard with weighted quality score calculation
- Per-field confidence distribution visualization (stacked bars)
- Method distribution pie charts (Recharts)
- Low-confidence issue browsing with sortable/paginated TanStack Table
- Inline editable cells for corrections
- Row selection with batch correction toolbar
- Gap clustering with priority scoring
- Agent chat interface with structured response rendering (proposals, clusters)
- Proposal review workflow (approve/reject/edit/approve-all)
- Real-time coverage sidebar during agent interactions
- Correction history with filtering, search, pagination, and export (CSV/JSON)
- Primo catalog links per record (hardcoded NLI base URL)
- Skeleton loading states and error boundaries
- React Query cache invalidation after mutations

### 1.3 Overlapping Features (with other UIs)

| Feature | Also In |
|---------|---------|
| Coverage statistics display | QA Tool Dashboard (3_dashboard.py) shows analogous label stats |
| Database record browsing | QA Tool DB Explorer (5_db_explorer.py) |
| Correction/mapping submission | CLI feedback_loop.py (same alias maps) |
| Agent interaction | Agent endpoints also accessible via CLI/curl |
| Primo URL generation | Chat UI (different base URL: TAU vs NLI) |

### 1.4 Unique Features

- Inline editable table cells for immediate correction
- Weighted quality score computation (date 30%, place 30%, publisher 20%, agent 20%)
- Cluster-based review with priority scoring
- Agent proposal table with approve/reject/edit lifecycle
- Coverage sidebar context during agent chat
- CSV/JSON export of correction history
- Confidence band color coding across all views

### 1.5 Missing Features

- No record detail view (cannot see full MARC record or all imprints)
- No undo/rollback for corrections (alias map changes are permanent)
- No user authentication or audit trail per user
- No comparison view (before/after normalization)
- No bulk import of corrections (only single or small-batch)
- No notification system for when re-normalization is needed after alias map changes
- No date field correction support (date corrections use a different pipeline, not alias maps)
- No keyboard shortcuts for power-user workflows
- Primo URL uses NLI base URL but Chat UI uses TAU -- inconsistent and neither is configurable

### 1.6 UX Quality: **High**

The React SPA demonstrates strong UX craft:
- Clean, consistent Tailwind CSS design with proper spacing and typography
- Skeleton loading states for all data-dependent views
- Error boundaries with readable error messages
- Responsive grid layouts
- Intuitive navigation via sidebar with active state highlighting
- Smart URL parameter sync (field tabs persist in URL)
- Smooth transitions and hover states
- Proper color semantics (green=good, red=bad, yellow=warning)

Weaknesses:
- Agent chat "How it works" section uses emoji (magnifying glass icon)
- BatchToolbar and ClusterCard are separate components but never shown; need to infer behavior
- No empty state guidance beyond initial "click to start"

### 1.7 Maintainability: **High**

- Well-organized file structure (pages/, components/, hooks/, api/, types/)
- Clean separation of concerns: API layer, custom hooks, type definitions, presentation
- Consistent patterns across all 4 pages (loading/error/data states)
- TypeScript throughout with proper interface definitions
- Custom hooks encapsulate React Query logic
- Components are composable (StatCard, CoverageBar, GapCard, etc.)

### 1.8 Technical Quality: **High**

- Modern React patterns (functional components, hooks, memoization)
- TanStack Table for efficient large table rendering with sorting and pagination
- TanStack Query for server state management with cache invalidation
- Proper use of useCallback and useMemo to prevent unnecessary re-renders
- URL search params synced with component state
- Type-safe API client layer
- No prop drilling (data flows through hooks)

Minor issues:
- eslint-disable comment for exhaustive-deps in Workbench (line 248)
- Batch correction fires sequential mutations instead of using batch endpoint
- No debouncing on confidence slider changes

### 1.9 Architectural Coherence: **High**

The frontend is purpose-built for the metadata co-pilot use case. Every page serves a clear function in the HITL metadata improvement workflow:
1. Dashboard: Identify where quality is lowest
2. Workbench: Triage and fix individual issues
3. Agent Chat: Get AI assistance for bulk fixes
4. Review: Audit what was changed

This is the most architecturally coherent UI in the project.

### 1.10 Backend Coupling: **Moderate**

- Talks exclusively to `/metadata/*` endpoints on the FastAPI backend
- Uses relative URLs (`/metadata/...`) requiring proxy or same-origin deployment
- Does not call `/chat` or any query endpoints
- Types mirror backend Pydantic models but are independently defined (no code generation)
- Could break if backend response shapes change

### 1.11 Dead/Experimental Features

- **Primo link in Workbench**: Uses `https://primo.nli.org.il/permalink/972NNL_INST/` as base URL, but Chat UI uses `https://tau.primo.exlibrisgroup.com`. One of these is wrong or they serve different institutions -- potential dead feature if the URL is incorrect.
- **Version label "v0.1.0"** in sidebar footer: Static, not dynamically sourced.

### 1.12 Features That Should NOT Survive

- Hardcoded Primo base URL (should be configurable)
- Emoji in the AgentChat page title area (per project code style)
- Sequential mutation firing for batch corrections (should use batch endpoint)

### 1.13 Verdict

**The strongest UI in the project.** Well-architected, purposeful, and production-quality. It should be the foundation for the unified UI, extended with query/discovery capabilities from the Chat UI and QA Tool.

---

## 2. QA Tool (app/ui_qa/)

**Technology:** Streamlit (multi-page), Python
**Size:** ~3,530 lines across 9 files (main.py, config.py, db.py, wizard_components.py, 7 page files)
**Pages:** 7 (main landing, QA Sessions, Run+Review, Find Missing, Dashboard, Gold Set, DB Explorer, Wizard)

### 2.1 Workflows

| Workflow | User Interactions |
|----------|------------------|
| **Ad-hoc Query Testing** | Go to "Run + Review" -> enter NL query -> click Run -> view plan + SQL + candidates -> label each candidate as TP/FP/FN/UNK in sidebar detail pane -> attach issue tags to FP/FN labels |
| **Guided QA Session (SMOKE)** | Go to "QA Sessions" -> click "Start SMOKE" -> Wizard opens -> Step 1: enter query or select canonical -> Step 2: execute + review plan -> Step 3: label 10+ candidates -> Step 4: evidence spot check -> Step 5: write summary + verdict |
| **Guided QA Session (RECALL)** | Same as SMOKE but Step 4 is "Find Missing" (FN hunt) instead of evidence spot check |
| **False Negative Discovery** | Go to "Find Missing" -> select a prior query -> search DB by year range/place/publisher -> browse results -> mark records as FN with issue tags |
| **Issue Analytics** | Go to "Dashboard" -> view aggregate label stats (TP/FP/FN/UNK counts) -> bar chart of issue tag frequency -> table of worst queries ranked by FP+FN count -> drill into query detail with label breakdown |
| **Gold Set Export** | Go to "Gold Set" -> view queries with labels -> delete unwanted queries -> export gold.json -> download -> run regression test inline (with progress bar) -> view pass/fail results |
| **Database Exploration** | Go to "DB Explorer" -> select table -> view schema -> set column filters + text search -> apply -> view paginated results -> download CSV |

### 2.2 Core Features

- NL query execution via QueryService (full M4 pipeline)
- Candidate labeling (TP/FP/FN/UNK) with issue tags
- Bulk labeling actions (mark all TP, mark all FP, clear all)
- Query plan and SQL inspection
- Candidate evidence inspection in sidebar
- Guided session workflow with step-by-step wizard (5 steps)
- Session management (create, resume, abort, delete)
- Canonical query library (15 predefined queries)
- False negative discovery via direct DB search
- Issue tag analytics with bar charts
- Problem query ranking (by FP+FN count)
- Gold set export to JSON
- In-UI regression test execution with progress bar
- Database explorer with read-only access
- Session-scoped label tracking

### 2.3 Overlapping Features (with other UIs)

| Feature | Also In |
|---------|---------|
| NL query execution | CLI `query` command, Chat UI, FastAPI `/chat` endpoint |
| Query plan/SQL viewing | CLI `query` outputs plan.json + sql.txt |
| Database browsing | Metadata Workbench (different tables/columns) |
| Regression testing | QA Regression Runner (app/qa.py) -- near-identical logic |
| Session management | FastAPI session management (different DB, different schema) |

### 2.4 Unique Features

- Guided wizard workflow with step gating (cannot skip ahead without meeting requirements)
- SMOKE vs RECALL session types with different step sequences
- Issue tag taxonomy (PARSER_MISSED_FILTER, NORM_PLACE_BAD, etc.)
- Problem query ranking by error count
- In-UI regression runner (not just CLI)
- Canonical query library for consistent testing
- Evidence spot-check step (random sampling of labeled candidates)
- Session resume capability (close browser, come back later)

### 2.5 Missing Features

- No comparison with previous runs (no before/after when pipeline changes)
- No precision/recall calculation (has all the data but does not compute metrics)
- No export of labeled data in standard ML evaluation formats
- No integration with the Metadata Workbench (issues found here do not flow to corrections)
- No Primo links to verify records against the catalog
- No collaboration features (single-user tool)
- No way to attach screenshots or external evidence to labels
- No automatic re-running of gold set when code changes (no CI hook from UI)

### 2.6 UX Quality: **Medium**

Strengths:
- Guided wizard provides structured workflow for non-technical QA testers
- Clear step-by-step instructions with progress indicators
- Good use of Streamlit metrics and expanders
- Consistent layout patterns across pages

Weaknesses:
- Streamlit's page-refresh model causes jarring UX (full page reloads on every interaction)
- Sidebar candidate detail pane in Run+Review is cramped and requires scrolling
- FN discovery page uses a per-row button pattern that generates many dynamic keys
- Emoji-heavy headers (every page title uses emoji)
- No keyboard-driven labeling (must click buttons for each candidate)
- The wizard and ad-hoc query pages have significant overlap, creating confusion about which to use

### 2.7 Maintainability: **Medium**

Strengths:
- Separate db.py for all database operations
- Config file with constants
- Wizard components extracted to wizard_components.py
- Each page is self-contained

Weaknesses:
- sys.path manipulation at the top of every page file (fragile)
- Direct sqlite3 usage throughout (no ORM, no connection pooling)
- Streamlit session_state used as a semi-global store (hard to test)
- Inline SQL queries in db.py with no parameterization abstraction
- Some pages import sqlite3 directly instead of going through db.py (3_dashboard.py)
- No test coverage for any QA tool code

### 2.8 Technical Quality: **Medium**

Strengths:
- Clean SQL schema with proper foreign keys and constraints
- ON CONFLICT upsert for label deduplication
- Gold set export logic is correct (TP+FN = expected_includes, FP = expected_excludes)
- Session migration code handles schema evolution

Weaknesses:
- Connection management: opens and closes connections on every DB call (no connection reuse)
- No transaction management (batch operations are not atomic)
- 3_dashboard.py bypasses db.py and does raw sqlite3 queries directly
- Regression runner in gold_set.py duplicates logic from app/qa.py almost exactly
- No input validation on search fields (SQL injection risk mitigated only by parameterized queries)

### 2.9 Architectural Coherence: **Medium**

The QA Tool serves a clear purpose (query pipeline testing and labeling) and its pages form a logical workflow. However:
- The relationship between ad-hoc "Run + Review" and the guided "QA Sessions" wizard is unclear -- they overlap significantly
- The DB Explorer feels bolted-on (general-purpose browser that does not contribute to QA workflow)
- The regression runner duplicates the CLI tool

### 2.10 Backend Coupling: **Loose (direct DB access)**

The QA Tool does NOT go through the FastAPI backend. It:
- Imports `scripts.query.QueryService` directly
- Opens sqlite3 connections to `data/qa/qa.db` and `data/index/bibliographic.db` directly
- Has its own session/state management via Streamlit session_state and its own SQLite tables
- Is completely independent of the FastAPI layer

This is actually appropriate for a development tool, but it means the tool does not test the actual API that production users would hit.

### 2.11 Dead/Experimental Features

- **"Load Last Run" button** on Run+Review page: declared but no implementation shown for loading previous results
- **`filters` parameter** in `get_label_stats()` and `get_worst_queries()`: accepted but never used
- **Regression runner in gold_set page**: exact duplicate of app/qa.py logic

### 2.12 Features That Should NOT Survive

- Duplicate regression runner (keep only app/qa.py CLI version)
- DB Explorer page (too generic, does not add QA value; should be replaced by record detail in Workbench)
- sys.path manipulation on every page
- Direct sqlite3 in 3_dashboard.py bypassing db.py

### 2.13 Verdict

**Valuable QA infrastructure with significant code quality issues.** The guided wizard concept and labeling workflow are genuinely useful for pipeline development. The gold set / regression testing loop is the right approach. But the implementation suffers from Streamlit limitations, code duplication, and inconsistent DB access patterns. The unique features (wizard, issue tags, canonical queries, gold set export) should be preserved in any consolidation.

---

## 3. Chat UI (app/ui_chat/)

**Technology:** Streamlit (single page), Python
**Size:** ~450 lines across 2 files (main.py, config.py)
**Pages:** 1

### 3.1 Workflows

| Workflow | User Interactions |
|----------|------------------|
| **Bibliographic Query** | Open Chat UI -> type query in chat input -> view formatted response with summary message -> expand "View all N matching records" -> browse results with title, author, date, place, publisher, subjects, description -> click Primo link for any record |
| **Multi-turn Conversation** | Ask initial query -> view results -> click a follow-up suggestion button OR type a refinement -> results update in conversation context -> session persists across messages |
| **Example Query Selection** | Use sidebar "Example Queries" buttons to pre-fill query -> sends immediately |

### 3.2 Core Features

- Streamlit chat interface (st.chat_message, st.chat_input)
- HTTP client to FastAPI `/chat` endpoint
- Session management (creates/reuses sessions via API)
- API health check with retry button
- Formatted candidate display with bibliographic fields (title, author, date range, place with raw form, publisher, subjects, description)
- Primo URL generation (TAU institution)
- Evidence display per candidate
- Follow-up question suggestions as clickable buttons
- Clarification message display
- Sidebar with session info, example queries, API status
- Smart date display (single year vs range)
- Place display showing canonical + raw form

### 3.3 Overlapping Features (with other UIs)

| Feature | Also In |
|---------|---------|
| NL query execution | CLI `query`, QA Tool Run+Review |
| Session management | FastAPI manages sessions; QA Tool has its own sessions |
| Candidate display | QA Tool Run+Review shows candidates (less detail) |
| Primo URL generation | Metadata Workbench (different base URL) |
| Follow-up suggestions | FastAPI generates these; Chat UI just renders them |

### 3.4 Unique Features

- **Conversational chat interface**: The only true conversational UI in the project
- **Primo URL for TAU institution**: Different from the NLI URL in the Metadata Workbench
- **Rich bibliographic formatting**: Title as link, author italicized, publication info line, subjects, description
- **Smart date/place display helpers**: Handles edge cases (single year, range, null fields, canonical+raw form)
- **Follow-up suggestion buttons**: Clickable buttons that auto-send queries
- **Pending message pattern**: Handles button-triggered queries cleanly via session_state

### 3.5 Missing Features

- No WebSocket streaming support (only HTTP; the backend supports WebSocket but this UI does not use it)
- No faceted browsing or result filtering
- No sorting of results
- No export capability
- No record comparison
- Cannot view query plan or SQL (no debug mode)
- No error recovery for partial API failures
- No pagination beyond the 50-item cap
- Clarification messages are appended to response text rather than rendered as a distinct UI element

### 3.6 UX Quality: **Medium**

Strengths:
- Clean chat metaphor that feels natural for bibliographic discovery
- Good use of expanders for result details (does not overwhelm)
- Smart formatting helpers for dates and places
- Follow-up suggestions reduce typing
- Example queries in sidebar help new users get started

Weaknesses:
- Streamlit chat has known issues with button state inside chat messages (acknowledged in code comments)
- Full page reloads on every interaction (Streamlit limitation)
- Results limited to 50 with no pagination
- "Searching..." spinner blocks entire UI
- No streaming/progressive display of results
- API unavailable state shows error banner but no guidance on what went wrong

### 3.7 Maintainability: **High**

- Only 2 files, very focused
- Clean separation between config (Primo URL generation) and main UI
- Well-documented functions with type hints and docstrings
- Simple, linear code flow
- No complex state management

### 3.8 Technical Quality: **Medium**

Strengths:
- Clean function signatures with type hints
- Proper error handling for API calls
- Session state managed correctly
- Primo URL generation is parameterized and extensible

Weaknesses:
- Uses synchronous `requests` library (blocks the Streamlit event loop)
- Hardcoded API_BASE_URL ("http://localhost:8000")
- No timeout configuration (60s hardcoded)
- Session ID display truncated to 8 chars (fragile display logic)
- No retry logic for failed API calls

### 3.9 Architectural Coherence: **High**

This is a thin client that properly delegates to the FastAPI backend. It does one thing (conversational discovery) and does it cleanly. The architecture is correct: UI -> HTTP -> FastAPI -> QueryService -> DB.

### 3.10 Backend Coupling: **Tight**

- Completely dependent on the FastAPI backend being running
- Health check on startup; shows error if API unavailable
- Sends all queries through `/chat` endpoint
- Relies on backend for session management, query compilation, execution, and response formatting
- Response format assumptions are tightly coupled to ChatResponse model

### 3.11 Dead/Experimental Features

None identified. This is a focused, minimal implementation.

### 3.12 Features That Should NOT Survive

- Streamlit as the delivery platform (should become part of the React SPA)
- Hardcoded localhost API URL
- Synchronous HTTP calls

### 3.13 Verdict

**The right idea, wrong platform.** The conversational discovery workflow is exactly what end users need. The bibliographic result formatting is thoughtful and should be preserved. But Streamlit is the wrong platform for a production chat interface -- the page-reload model, lack of streaming, and limited interactivity make it inferior to what a React implementation could deliver. The formatting logic and Primo URL generation should be migrated to the React SPA.

---

## 4. CLI (app/cli.py)

**Technology:** Typer (Python CLI framework)
**Size:** 334 lines, 5 commands
**Commands:** parse_marc, chat_init, chat_history, chat_cleanup, query

### 4.1 Workflows

| Workflow | User Interactions |
|----------|------------------|
| **MARC Parsing** | `python -m app.cli parse_marc <marc.xml>` -> parses MARC XML -> outputs canonical JSONL + extraction report -> prints coverage summary |
| **Query Execution** | `python -m app.cli query "books by Oxford"` -> compiles NL query -> executes against DB -> writes plan.json, sql.txt, candidates.json to output dir -> prints summary with sample results |
| **Session Management** | `chat-init` -> creates new session and prints ID; `chat-history <id>` -> shows conversation; `chat-cleanup` -> expires old sessions |
| **Session-Aware Query** | `python -m app.cli query "..." --session-id <id>` -> executes query AND saves to session history |

### 4.2 Core Features

- MARC XML parsing with extraction report
- NL query execution with artifact output (plan, SQL, candidates)
- Session creation, history viewing, and cleanup
- Session-aware queries (saves to conversation history)
- Helpful error messages with hints (e.g., "Have you run M3 indexing yet?")
- Automatic timestamped output directories

### 4.3 Overlapping Features

| Feature | Also In |
|---------|---------|
| NL query execution | Chat UI, QA Tool, FastAPI `/chat` |
| Session management | FastAPI endpoints, Chat UI |
| Query plan/SQL output | QA Tool Run+Review |

### 4.4 Unique Features

- **MARC XML parsing command**: The only UI that exposes M1 parsing
- **Artifact file output**: Writes plan.json, sql.txt, candidates.json per query run
- **Session-aware CLI queries**: Bridges CLI usage with session-based conversation

### 4.5 Missing Features

- No `index` command (mentioned in CLAUDE.md but not implemented -- the parse command covers M1 but no M3 indexing command exists)
- No `normalize` command (M2 normalization is only available via scripts)
- No interactive mode
- No output format options (always prints text)
- No color/formatting customization
- No way to list or browse sessions (only view a specific one by ID)
- No batch query execution

### 4.6 UX Quality: **Medium**

Strengths:
- Clear command structure with Typer's built-in help
- Good error messages with actionable hints
- Summary output is well-formatted with clear labels

Weaknesses:
- Uses emoji in output (checkmarks, warning signs) which can render poorly in some terminals
- No progress indication for long-running query compilation (LLM call)
- Sample results only show first 3 with limited detail

### 4.7 Maintainability: **High**

- Simple, linear code in a single file
- Clean Typer patterns with proper type annotations
- Lazy imports to avoid loading heavy modules unnecessarily
- Well-documented options and arguments

### 4.8 Technical Quality: **High**

- Proper error handling with appropriate exit codes
- Uses QueryService (same as other UIs)
- File output is properly structured
- Session integration is clean

### 4.9 Architectural Coherence: **High**

The CLI serves as a developer/ops tool for pipeline testing and session management. Each command maps to a clear pipeline stage.

### 4.10 Backend Coupling: **Loose (direct library usage)**

- Does NOT go through FastAPI
- Imports and calls library functions directly (parse_marc_xml_file, QueryService, SessionStore)
- Shares the same underlying libraries as the FastAPI backend but bypasses the HTTP layer

### 4.11 Dead/Experimental Features

- **`index` command** referenced in CLAUDE.md does not exist in the CLI
- Chat commands (chat_init, chat_history, chat_cleanup) may be unused if all chat interaction happens via the Chat UI / API

### 4.12 Features That Should NOT Survive

- Emoji in CLI output (should use plain text markers)
- Chat management commands should probably move to a separate admin CLI

### 4.13 Verdict

**Solid developer tool.** The CLI is well-implemented for its purpose. The `parse_marc` and `query` commands are essential pipeline tools. The chat commands are less critical but not harmful. Should be maintained as the developer/ops interface.

---

## 5. QA Regression Runner (app/qa.py)

**Technology:** Typer (Python CLI)
**Size:** 187 lines, 1 command
**Commands:** regress

### 5.1 Workflows

| Workflow | User Interactions |
|----------|------------------|
| **CI Regression Testing** | `python -m app.qa regress --gold gold.json --db bibliographic.db` -> loads gold set -> runs all queries -> compares results against expected includes/excludes -> prints pass/fail summary -> exits with code 0 (pass) or 1 (fail) |

### 5.2 Core Features

- Gold set loading and validation
- Sequential query execution with compile + execute
- Expected includes/excludes comparison
- Pass/fail determination per query
- Color-coded terminal output
- Verbose mode for detailed per-query output
- Optional log file output (JSON)
- CI-compatible exit codes (0/1)

### 5.3 Overlapping Features

| Feature | Also In |
|---------|---------|
| Gold set regression testing | QA Tool Gold Set page (4_gold_set.py) -- **near-identical logic** |
| Query compilation + execution | CLI `query`, QA Tool, Chat UI, FastAPI |

### 5.4 Unique Features

- **CI-compatible exit codes**: Designed for pipeline integration
- **JSON log file output**: Machine-readable results for CI analysis
- **Standalone executable**: Can run without any UI or server

### 5.5 Missing Features

- No parallel query execution (runs sequentially)
- No timeout per query
- No delta comparison (no way to compare against previous run)
- No JUnit/TAP output format for CI tools
- No query-level skip/ignore capability

### 5.6 UX Quality: **Medium**

Appropriate for a CI tool. Clear output with color coding. Verbose mode provides detail when needed.

### 5.7 Maintainability: **High**

Simple, single-purpose file with clean logic.

### 5.8 Technical Quality: **Medium**

- Uses `compile_query` + `execute_plan` directly (low-level) instead of QueryService
- Uses emoji in output (inappropriate for CI log output)
- Error handling catches all exceptions broadly
- No timeout protection for queries

### 5.9 Architectural Coherence: **High**

Single-purpose tool that does exactly what it should.

### 5.10 Backend Coupling: **Loose**

Direct library usage (compile_query, execute_plan). No HTTP dependency.

### 5.11 Dead/Experimental Features

- The **entire tool is duplicated** in the QA Tool's Gold Set page (4_gold_set.py), which runs the same regression logic inline via Streamlit.

### 5.12 Features That Should NOT Survive

- Emoji in CLI output
- The duplicate regression logic in the QA Tool should be removed, keeping only this CLI tool

### 5.13 Verdict

**Essential but duplicated.** This is the canonical regression runner and should be the single source of truth for regression testing. The duplicate in the QA Tool should call this tool or share common regression logic.

---

## 6. FastAPI Backend (app/api/)

**Technology:** FastAPI, Pydantic, SQLite, slowapi (rate limiting), CORS middleware
**Size:** ~3,024 lines across 4 files (main.py, metadata.py, metadata_models.py, models.py)
**Endpoints:** 5 core + 12 metadata + 1 WebSocket = 18 total

### 6.1 Endpoint Inventory

**Core endpoints (main.py):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | /health | Health check (DB + session store) |
| POST | /chat | Two-phase conversational query (with rate limiting) |
| GET | /sessions/{id} | Get session with history |
| DELETE | /sessions/{id} | Expire session |
| WS | /ws/chat | WebSocket streaming chat |

**Metadata endpoints (metadata.py):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | /metadata/coverage | Full coverage report (all fields) |
| GET | /metadata/issues | Low-confidence records (paginated) |
| GET | /metadata/unmapped | Unmapped raw values by frequency |
| GET | /metadata/methods | Method distribution per field |
| GET | /metadata/clusters | Gap clusters for review |
| POST | /metadata/corrections | Submit single correction |
| POST | /metadata/corrections/batch | Batch corrections |
| GET | /metadata/corrections/history | Correction audit trail |
| POST | /metadata/agent/chat | Agent conversation |
| GET | /metadata/publishers | Publisher authority records |
| POST | /metadata/primo-urls | Batch Primo URL generation |
| GET | /metadata/records/{mms_id}/primo | Single Primo URL |

### 6.2 Workflows (from the backend's perspective)

| Workflow | Trigger |
|----------|---------|
| **Two-Phase Chat** | POST /chat -> Phase 1 (query definition with intent agent) -> confidence scoring -> if high: execute + transition to Phase 2 (corpus exploration) -> if low: return clarification -> Phase 2 handles aggregation, enrichment, refinement |
| **Coverage Audit** | GET /coverage -> generate_coverage_report from DB -> convert to response model |
| **Issue Triage** | GET /issues -> SQL query for low-confidence records -> paginated response |
| **Correction Submission** | POST /corrections -> validate -> load alias map -> check conflicts -> update alias map atomically -> count affected records -> log to review_log.jsonl |
| **Agent-Assisted Analysis** | POST /agent/chat -> route to specialist agent (Place/Date/Publisher/Name) -> return proposals + cluster summaries |
| **WebSocket Streaming** | WS /ws/chat -> compile query -> stream progress -> batch results in groups of 10 -> send complete response |

### 6.3 Core Features

- Two-phase conversational model (query definition + corpus exploration)
- Intent agent with confidence scoring (>= 0.85 threshold)
- Collection overview detection and response
- Query compilation via OpenAI LLM
- SQL execution against bibliographic DB
- Session management (create, retrieve, expire)
- Conversation phase tracking
- Active subgroup state management
- Exploration intents (aggregation, enrichment, refinement)
- Coverage report generation
- Low-confidence issue querying with pagination
- Unmapped value listing
- Method distribution statistics
- Gap clustering
- Single and batch correction endpoints
- Atomic alias map updates with conflict detection
- Correction history from review log
- Agent harness routing to specialist agents
- Publisher authority records
- Primo URL generation (batch and single)
- Rate limiting (10/min per IP)
- CORS (allow all origins for dev)
- Interaction logging middleware for /metadata/* requests
- Enrichment service integration
- WebSocket streaming with batched results

### 6.4 Overlapping Features

| Feature | Also In |
|---------|---------|
| Query execution | CLI, QA Tool (both bypass this API) |
| Session management | QA Tool has its own session system |
| Coverage statistics | Metadata Workbench (React) consumes this; audit module generates it |
| Correction submission | CLI feedback_loop.py applies corrections to same alias maps |

### 6.5 Unique Features

- **Two-phase conversation model**: Query definition -> corpus exploration transition
- **Intent agent with confidence scoring**: LLM-based query interpretation with uncertainty detection
- **Exploration phase**: Aggregation, enrichment, and refinement of defined subgroups
- **Overview query detection**: Returns collection statistics for introductory questions
- **Interaction logging middleware**: Automatic timing and parameter logging for all /metadata/* requests
- **Atomic alias map updates**: Write-tmp-then-replace pattern prevents corruption
- **Conflict detection**: Prevents overwriting existing alias mappings

### 6.6 Missing Features

- No authentication (explicitly postponed)
- No per-user rate limiting (IP-based only)
- No API versioning
- No request/response compression
- No caching layer (coverage report regenerated on every request)
- No background job system for re-normalization after corrections
- No webhook/notification system
- No OpenAPI schema validation beyond Pydantic
- No database connection pooling (new connections per request)
- Enrichment service initialized but not exposed through a dedicated endpoint
- No pagination on many endpoints (clusters, publishers)

### 6.7 UX Quality: N/A (backend)

The API documentation (via FastAPI's auto-generated /docs) is comprehensive. Response models are well-documented with Pydantic Field descriptions.

### 6.8 Maintainability: **Medium**

Strengths:
- Clean router separation (metadata endpoints in separate file)
- Pydantic models for all request/response contracts
- Consistent error handling patterns
- Lifespan context manager for startup/shutdown

Weaknesses:
- main.py is very long (~1100+ lines) with complex chat logic inline
- handle_query_definition_phase and handle_corpus_exploration_phase are large functions
- Global mutable state (session_store, db_path, etc.) rather than dependency injection
- metadata.py uses inline SQL strings without a query builder
- Coverage report is regenerated from scratch on every /metadata/* call (expensive)
- Multiple helper functions in metadata.py do ad-hoc sqlite3 connections

### 6.9 Technical Quality: **Medium-High**

Strengths:
- Proper use of FastAPI features (lifespan, middleware, WebSocket, rate limiting)
- Pydantic validation on all inputs
- Atomic file operations for alias maps
- Proper HTTP status codes and error responses
- Type hints throughout

Weaknesses:
- No database connection pooling
- Coverage report is expensive and not cached
- Global state pattern is hard to test
- WebSocket handler has complex inline logic
- CORS set to allow all origins (security concern for production)
- No health check for LLM (OpenAI) availability

### 6.10 Architectural Coherence: **Medium**

The backend serves two fundamentally different purposes:
1. **Chat/Discovery API**: For end-user bibliographic queries (POST /chat, WebSocket)
2. **Metadata Quality API**: For the co-pilot workbench (GET/POST /metadata/*)

These are distinct domains that happen to share the same FastAPI application. The chat side has complex phase management and LLM integration. The metadata side is primarily CRUD over SQLite data. They share almost no code paths beyond the database connection. This suggests they could (and perhaps should) be separate services or at least separate routers with cleaner boundaries.

### 6.11 Backend Coupling: N/A (this IS the backend)

- Tightly coupled to: `scripts.query`, `scripts.chat`, `scripts.metadata`, `scripts.enrichment`
- Database coupling: `data/index/bibliographic.db`, `data/chat/sessions.db`, `data/enrichment/cache.db`
- External dependency: OpenAI API for query compilation and intent interpretation

### 6.12 Dead/Experimental Features

- **Enrichment service**: Initialized in lifespan but `enrichment_service` is not directly exposed through any endpoint (used internally by exploration phase but not independently accessible)
- **`_bib_db` in websocket_chat**: Assigned but prefixed with underscore and commented "retained for potential future use"
- **CORS allow_origins=["*"]**: Development configuration that should not reach production
- **Source filter on corrections/history**: Accepts "source" filter parameter but the Review UI passes it -- works correctly but there is no UI for adding source labels (always defaults to "human")

### 6.13 Features That Should NOT Survive

- Global mutable state pattern (should use FastAPI dependency injection)
- CORS allow-all (should be configured per environment)
- Uncached coverage report generation
- Inline SQL in metadata.py (should use a query builder or at least centralized queries)

### 6.14 Verdict

**The correct architectural center of the project, but growing complex.** The FastAPI backend is where all roads should lead. The two-phase conversation model is sophisticated and well-thought-out. The metadata quality endpoints are comprehensive. But the codebase is getting unwieldy -- the chat logic needs decomposition, the coverage report needs caching, and the two API domains (chat + metadata) should be better separated.

---

## Cross-Cutting Observations

### Primo URL Inconsistency

Two different Primo base URLs exist:
- **Metadata Workbench** (Sidebar.tsx line 37): `https://primo.nli.org.il/permalink/972NNL_INST/`
- **Chat UI** (config.py): `https://tau.primo.exlibrisgroup.com/nde/fulldisplay` with `vid=972TAU_INST:NDE`
- **FastAPI metadata** endpoint: Generates URLs server-side (via primo-urls endpoint)

These point to different institutions (NLI vs TAU). This needs to be resolved with a single configurable Primo URL.

### Session Management Fragmentation

Three separate session systems exist:
1. **FastAPI chat sessions**: `data/chat/sessions.db` via `SessionStore`
2. **QA Tool sessions**: `data/qa/qa.db` via `qa_sessions` table
3. **Streamlit session state**: In-memory per-browser-tab state

These serve different purposes but create maintenance burden.

### Regression Test Duplication

Regression testing logic exists in two places:
1. `app/qa.py` (CLI, 187 lines)
2. `app/ui_qa/pages/4_gold_set.py` (Streamlit, inline in page)

Nearly identical logic. Should be consolidated.

### Direct DB Access vs API

- **Chat UI** goes through FastAPI (correct)
- **QA Tool** bypasses FastAPI, accesses DB directly (appropriate for dev tool)
- **CLI** bypasses FastAPI, accesses libraries directly (appropriate for dev tool)
- **Metadata Workbench** goes through FastAPI (correct)

This split is actually reasonable: production UIs use the API, development tools use libraries directly.

---

## Summary Matrix

| UI | UX | Maintainability | Technical | Architectural | Backend Coupling | Purpose Clarity |
|----|-----|-----------------|-----------|---------------|-----------------|-----------------|
| Metadata Workbench | High | High | High | High | Moderate | High |
| QA Tool | Medium | Medium | Medium | Medium | Loose | Medium |
| Chat UI | Medium | High | Medium | High | Tight | High |
| CLI | Medium | High | High | High | Loose | High |
| QA Regression Runner | Medium | High | Medium | High | Loose | High |
| FastAPI Backend | N/A | Medium | Medium-High | Medium | N/A | Medium |
