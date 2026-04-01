# UI Alignment Assessment

**Date:** 2026-03-23
**Assessor:** Product-Design Evaluator
**Project Goal:** Enable scholars and librarians to discover rare books through natural language conversation, backed by a deterministic, evidence-based query engine over MARC XML bibliographic records with full provenance tracking.
**Centerpiece:** The two-phase conversational query engine (intent interpretation with confidence scoring -> corpus exploration with aggregation/refinement), delivered through a chatbot UI.

---

## 1. Metadata Co-pilot Workbench (frontend/)

**Rating: VALUABLE**

### What It Is
A polished React SPA (3,162 lines of TypeScript) with four pages: Dashboard, Workbench, AgentChat, and Review. Uses TanStack Table, Recharts, React Query. Professionally built with skeleton loaders, proper error states, responsive layout, CORS-ready API integration.

### Supports the Goal
- **Data quality directly impacts bot accuracy.** The bot can only return evidence-based results if normalization coverage is high. Every place alias, publisher variant, and date parsed correctly makes the bot more reliable. This workbench is the primary tool for achieving that coverage.
- **Agent Chat page is the feedback loop.** The AI-assisted propose/approve/reject/edit cycle for normalization mappings is exactly the kind of HITL process that scales metadata improvement beyond what manual curation can achieve.
- **Review page provides auditability.** Correction history with source tracking (human vs. agent) and evidence fields supports the project's provenance requirements.
- **Dashboard gives operational visibility.** Quality scores, confidence distributions, and gap summaries help prioritize remediation work.

### Concerns
- **Does not serve the primary users.** Scholars and librarians will never use this tool. It is an internal operations tool for metadata curators. This is fine, but it should be explicitly positioned as such.
- **Competes for development attention.** At 3,162 lines of frontend TypeScript plus 1,484 lines of backend metadata API, this is the largest UI surface area in the project. It risks becoming the focal point of development at the expense of the actual bot.
- **No connection to the chatbot.** There is zero integration between the metadata workbench and the conversational UI. A curator cannot see which bot queries would improve with a given normalization fix, and a bot user cannot flag a result as having a data quality issue that routes back to the workbench.
- **Separate tech stack adds maintenance cost.** React + Vite + TypeScript is a different ecosystem from the Python/Streamlit stack. Two build systems, two dependency trees, two deployment configurations.

### Verdict
Valuable support tool for metadata quality that directly enables the bot to perform better, but it is an internal operations tool, not a user-facing product. Risk: over-investment here starves the bot itself. Opportunity: connect it to the bot via a "flag data issue" workflow.

---

## 2. QA Tool (app/ui_qa/)

**Rating: VALUABLE**

### What It Is
A Streamlit multi-page app (3,531 lines of Python) with 7 pages: Sessions, Run+Review, Find Missing, Dashboard, Gold Set, DB Explorer, and a Wizard. Provides the complete labeling and regression workflow for the M4 query pipeline.

### Supports the Goal
- **Only tool for systematically measuring bot accuracy.** Without TP/FP/FN labeling, there is no way to know whether the query engine actually works. This is the measurement infrastructure for the project's primary success criterion: "deterministically produce the correct CandidateSet."
- **Gold set export enables regression testing.** The export-to-JSON pipeline feeds the CLI regression runner, creating a CI-compatible quality gate.
- **Find Missing (FN search) is uniquely valuable.** The ability to search the database for records that should have been returned but weren't is critical for identifying normalization gaps, parser failures, and query plan issues. No other UI offers this.
- **DB Explorer provides record-level debugging.** When a query returns unexpected results, the ability to inspect raw database tables is essential for diagnosing whether the issue is in parsing (M1), normalization (M2), indexing (M3), or query compilation (M4).
- **Wizard provides structured QA sessions.** Guided step-by-step workflow reduces errors in the labeling process and ensures consistency.

### Concerns
- **Exposes internal pipeline complexity.** Pages reference "M4", query plans, SQL execution, and database tables. This is appropriate for a developer tool but would be confusing if exposed to end users.
- **Streamlit limitations for a developer tool.** State management is fragile (session_state workarounds), no URL routing, no keyboard shortcuts. For a power-user developer tool that requires rapid iteration through many queries, Streamlit is a friction point.
- **Partial overlap with CLI regression runner.** The Gold Set page includes a "Run Regression" button that duplicates the functionality of `app/qa.py`. Both execute the same queries against the same gold set.
- **No link to the bot's conversational UI.** A QA reviewer cannot easily test a query through the bot's two-phase flow (Phase 1 intent interpretation, Phase 2 exploration) -- they test through the lower-level direct query execution. This means QA tests a different code path than what users experience.

### Verdict
Valuable and necessary. The project cannot claim deterministic correctness without measurement infrastructure. The DB Explorer and Find Missing pages are uniquely irreplaceable. However, the tool should evolve to test the bot's full conversational path (two-phase flow), not just raw query execution.

---

## 3. Chat UI (app/ui_chat/)

**Rating: ESSENTIAL (concept) / NICE-TO-HAVE (current implementation)**

### What It Is
A single-page Streamlit chat interface (449 lines of Python) that wraps the FastAPI `/chat` endpoint. Features example queries, session management, follow-up suggestions as buttons, Primo URL links, and an expandable candidate details view.

### Supports the Goal
- **This IS the product.** The entire project goal is "natural language conversation" for bibliographic discovery. This UI is the only place where a scholar or librarian can actually interact with the bot.
- **Demonstrates the two-phase flow.** The backend's `handle_query_definition_phase` and `handle_corpus_exploration_phase` implement the centerpiece architecture. This UI is the window into that architecture.
- **Follow-up suggestions guide exploration.** The clickable follow-up buttons connect to Phase 2's exploration capabilities (aggregation, refinement, enrichment).
- **Record display with Primo links.** Shows title, author, date, place, publisher, subjects, description, and evidence -- all linked to the institutional catalog. This is the evidence-based provenance the project promises.

### Concerns
- **Streamlit is wrong for conversational UI.** Every user interaction causes a full page re-render. The chat history is rebuilt from session_state on every action. Buttons inside chat messages have state issues (noted in code comments). There is no streaming support despite the backend offering WebSocket streaming. The UX feels sluggish and unpolished compared to what users expect from a modern chat interface.
- **Does not use the WebSocket endpoint.** The backend has a fully implemented WebSocket handler (`/ws/chat`) with progressive streaming, batch results, and progress messages. The Streamlit UI uses synchronous HTTP POST instead, wasting the best UX feature available.
- **Single page with no navigation.** No way to browse past sessions, no settings, no help page. Compare this to the Metadata Workbench's 4-page React SPA with sidebar navigation, loading states, and error handling.
- **The strongest technical implementation went to the wrong UI.** The Metadata Workbench (React, 3,162 lines) got the professional treatment. The Chat UI (Streamlit, 449 lines) -- the actual product -- got a minimal prototype. This is an inversion of priorities.
- **No observability.** No way to inspect the query plan, see which MARC fields matched, understand confidence scores, or diagnose why a result appeared or didn't appear. The evidence display is minimal (3 evidence items, truncated). For a scholarly tool, this lack of transparency undermines trust.

### Verdict
The concept is essential -- it IS the product. The current implementation is a nice-to-have prototype that demonstrates the flow but is not suitable as the user-facing experience. The primary recommendation: invest in this UI with the same quality bar applied to the Metadata Workbench. Use React, consume WebSocket streaming, and build proper observability (query plan visualization, evidence drill-down, confidence indicators).

---

## 4. CLI (app/cli.py)

**Rating: ESSENTIAL**

### What It Is
A Typer-based CLI (334 lines) with 5 commands: `parse_marc`, `query`, `chat-init`, `chat-history`, `chat-cleanup`.

### Supports the Goal
- **Pipeline execution backbone.** `parse_marc` runs M1 (MARC XML to JSONL). `query` runs the full M4 pipeline (compile + execute + evidence). These are the deterministic, scriptable entry points for the entire system.
- **Artifact generation for debugging.** `query` writes plan.json, sql.txt, and candidates.json to timestamped run directories. This is the evidence trail the project requires.
- **Session management for testing.** `chat-init`, `chat-history`, and `chat-cleanup` provide session lifecycle management without needing the API server running. Useful for development and scripting.
- **CI/CD integration.** CLI commands are scriptable and testable, unlike GUI tools.

### Concerns
- **No index command visible.** The CLAUDE.md mentions `python -m app.cli index <canonical_dir>` but the current CLI only has `parse_marc`, `query`, and chat commands. The M3 indexing step appears to use a separate script (`scripts.marc.m3_index`), not the CLI.
- **Query command doesn't test the two-phase flow.** It calls `QueryService.execute()` directly, bypassing the intent interpretation, confidence scoring, and exploration phases. This means the CLI tests a different code path than the bot.

### Verdict
Essential developer tool. Well-implemented, focused, and necessary. The pipeline cannot run without it.

---

## 5. QA Regression Runner (app/qa.py)

**Rating: REDUNDANT**

### What It Is
A standalone Typer CLI (187 lines) with a single `regress` command that runs gold set queries and validates expected includes/excludes.

### Supports the Goal
- **Regression testing is essential.** The ability to run `python -m app.qa regress --gold gold.json --db bibliographic.db` as a CI gate is critical for preventing quality regressions.
- **Exit codes for CI integration.** Returns 0 for pass, 1 for fail -- standard CI behavior.
- **Log file output for forensics.** `--log-file` writes detailed JSON results.

### Concerns
- **Duplicates the QA Tool's Gold Set page.** The Gold Set page (page 4) in the QA Tool includes a "Run Regression" button that does the same thing. Two separate implementations of the same regression logic creates a maintenance burden and a risk of divergence.
- **Should be a subcommand of the main CLI.** Having `app/cli.py` and `app/qa.py` as separate Typer apps is a fragmentation. A `python -m app.cli regress` subcommand would be more discoverable and consistent.
- **Directly calls `compile_query` + `execute_plan`.** Like the main CLI's `query` command, this bypasses the two-phase conversation flow. It tests the M4 query pipeline but not the bot's full behavior.

### Verdict
Redundant as a standalone file. The regression logic should be consolidated -- either as a subcommand of the main CLI or as an importable function called by both the CLI and the QA Tool's UI. The functionality itself is essential, but having it in a separate file that duplicates the QA Tool's capability is not.

---

## 6. FastAPI Backend (app/api/)

**Rating: ESSENTIAL**

### What It Is
A FastAPI application (3,219 lines across 4 files: main.py at 1,300 lines, metadata.py at 1,484 lines, metadata_models.py at 377 lines, models.py at 58 lines). Serves the `/chat` endpoint with two-phase conversation, `/ws/chat` WebSocket streaming, `/health` monitoring, `/sessions/*` management, and the entire `/metadata/*` suite (12 endpoints).

### Supports the Goal
- **Central nervous system of the project.** Every UI (Metadata Workbench, Chat UI, and potentially the QA Tool) depends on this backend. It is the single point of integration for the query pipeline, session management, normalization agents, and metadata quality operations.
- **Two-phase conversation is implemented here.** The `handle_query_definition_phase` and `handle_corpus_exploration_phase` functions implement the project's centerpiece architecture. Intent interpretation, confidence scoring, aggregation, refinement, comparison, enrichment -- all live here.
- **WebSocket streaming for real-time UX.** The `/ws/chat` endpoint with progress messages and batch results is the technical foundation for a responsive chat experience.
- **CORS enabled for cross-origin access.** Properly configured for development with the React frontend.

### Concerns
- **Growing complexity without separation.** `main.py` at 1,300 lines combines HTTP routing, WebSocket handling, two-phase conversation orchestration, session management, enrichment integration, and logging middleware. `metadata.py` at 1,484 lines combines 12 endpoint handlers with database queries, coverage report generation, clustering logic, and agent harness integration. These files are approaching the point where they need decomposition.
- **Two conversation implementations.** The `/chat` HTTP endpoint uses the intent agent + exploration agent (the two-phase flow). The `/ws/chat` WebSocket endpoint uses the old `compile_query` + `execute_plan` path (bypasses intent interpretation). This means the WebSocket path does not benefit from the two-phase architecture -- it has fallen behind the HTTP path.
- **Metadata API is 46% of the backend.** The 1,484-line metadata router is almost as large as the 1,300-line main application. This is appropriate if metadata quality is an ongoing priority, but it means nearly half the backend code serves an internal tool rather than the primary user experience.
- **No API versioning.** Endpoints are at the root level (`/chat`, `/metadata/coverage`). As the API evolves, breaking changes will impact all clients simultaneously.

### Verdict
Essential infrastructure. The backend is well-architected at a conceptual level (two-phase conversation, session management, evidence-based responses), but it needs continued investment in decomposition to remain maintainable. Critical gap: the WebSocket handler should use the same two-phase flow as the HTTP handler.

---

## Cross-Cutting Findings

### 1. Investment Inversion
The highest-quality technical implementation (React SPA, 3,162 lines) was applied to an internal operations tool (Metadata Workbench), while the actual product (Chat UI) received a minimal prototype (449 lines of Streamlit). This is the single most important alignment issue.

### 2. Code Path Divergence
There are at least three different code paths for executing a query:
- **HTTP /chat**: Intent agent -> confidence check -> QueryService -> two-phase flow (most complete)
- **WebSocket /ws/chat**: compile_query -> execute_plan (bypasses intent agent, no Phase 2)
- **CLI query / QA regression**: compile_query -> execute_plan (bypasses entire bot layer)

This means the QA regression suite validates a different code path than what users experience through the bot. Bugs in the intent agent, exploration agent, or session management are not caught by regression tests.

### 3. Missing Observability Bridge
No UI provides end-to-end observability from query to MARC field. The Chat UI shows minimal evidence. The QA Tool tests at the query plan level. The Metadata Workbench operates at the normalization level. Nobody can trace: "user asked X -> intent agent parsed it as Y with confidence Z -> SQL query returned N records -> record R matched because MARC field 264$b contained value V."

### 4. User Persona Gap
Three user personas exist but only one is well-served:
- **Metadata Curators**: Well-served by the Metadata Workbench
- **Developers**: Adequately served by CLI + QA Tool
- **Scholars/Librarians**: Poorly served by the Streamlit Chat UI prototype

### 5. Session/State Fragmentation
Session management exists in three places: FastAPI session store (SQLite), Streamlit session_state (in-memory), and QA Tool qa.db (SQLite). These are isolated systems with no shared state.
