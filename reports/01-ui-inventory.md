# UI Inventory Report

**Date:** 2026-03-23
**Scope:** Full audit of all user-facing interfaces in rare-books-bot
**Auditor:** Claude (automated inventory)

---

## Executive Summary

The project has **5 distinct user-facing interfaces** plus **1 shared API backend** that serves as the bridge layer. The interfaces span three technology stacks (React, Streamlit, Typer CLI) and serve three different user personas (librarians, developers/QA, end-users). There is **no overlap in functionality** between the UIs -- each serves a distinct purpose -- but all three web-facing UIs depend on the same FastAPI backend.

| # | UI | Tech | Status | Lines of Code |
|---|-----|------|--------|---------------|
| 1 | Metadata Co-pilot Workbench | React 19 + Vite + Tailwind | Active | ~3,160 |
| 2 | QA Tool | Streamlit (multi-page) | Active | ~3,530 |
| 3 | Chat UI | Streamlit (single-page) | Active | ~450 |
| 4 | CLI | Typer | Active | ~520 |
| 5 | QA Regression Runner (CLI) | Typer | Active | ~190 |
| 6 | FastAPI Backend (shared) | FastAPI + Pydantic | Active | ~3,220 |

No Jupyter notebooks, Gradio apps, Dash apps, or other hidden UI layers were found. No legacy/abandoned UIs were discovered.

---

## 1. Metadata Co-pilot Workbench (React SPA)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `frontend/` |
| **Purpose** | Agent-driven HITL system for improving bibliographic metadata quality |
| **Target Users** | Librarians, metadata specialists |
| **Tech Stack** | React 19, TypeScript, Vite 8, Tailwind CSS 4, TanStack Query 5, TanStack Table 8, Recharts 3, React Router 7 |
| **Entry Point** | `cd frontend && npm run dev` (dev server at `http://localhost:5173`) |
| **API Dependency** | Proxies `/metadata/*` and `/health` to FastAPI at `http://localhost:8000` |
| **Build** | Pre-built dist exists at `frontend/dist/` (458 B HTML + 692 KB JS + 29 KB CSS) |
| **Status** | **Active** -- most recently modified 2026-03-22 |

### Pages (4 routes)

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `Dashboard.tsx` (13.4 KB) | Coverage overview with pie charts per field (date, place, publisher, agent_name), confidence band distribution, navigation to workbench |
| `/workbench` | `Workbench.tsx` (22.2 KB) | Issue triage table with sortable/paginated records, inline editable cells, cluster view, batch corrections, agent chat integration, Primo catalog links |
| `/agent` | `AgentChat.tsx` (27.9 KB) | Conversational interface to specialist agents (Place, Date, Publisher, Agent), proposal review with approve/reject/edit, coverage sidebar |
| `/review` | `Review.tsx` (17.9 KB) | Correction audit trail with filtering by field/source, pagination, timestamps |

### Supporting Code

| File | Purpose |
|------|---------|
| `src/components/Layout.tsx` | Shell layout with sidebar navigation |
| `src/components/Sidebar.tsx` | Navigation sidebar with 4 nav items, version label (v0.1.0) |
| `src/components/workbench/EditableCell.tsx` | Inline cell editing for corrections |
| `src/components/workbench/BatchToolbar.tsx` | Bulk correction actions |
| `src/components/workbench/ClusterCard.tsx` | Gap cluster display card |
| `src/api/metadata.ts` | API client functions (6 endpoints) |
| `src/hooks/useMetadata.ts` | React Query hooks wrapping API calls |
| `src/types/metadata.ts` | TypeScript interfaces for API responses (14 types) |

### Notes

- The frontend does **not** get served by FastAPI (no StaticFiles mount). It runs as a separate Vite dev server.
- A production build exists in `frontend/dist/` but there is no deployment configuration to serve it.
- The `package.json` name is generic (`"frontend"`) and the HTML title is also `"frontend"` -- neither is branded.

---

## 2. QA Tool (Streamlit Multi-Page App)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `app/ui_qa/` |
| **Purpose** | Quality assurance for M4 query pipeline -- test queries, label results (TP/FP/FN), track issues, export gold sets for regression |
| **Target Users** | Developers, QA testers |
| **Tech Stack** | Streamlit 1.52+, Pandas, SQLite |
| **Entry Point** | `poetry run streamlit run app/ui_qa/main.py` (at `http://localhost:8501`) |
| **API Dependency** | Direct -- calls `scripts.query.QueryService` in-process (no HTTP dependency on FastAPI) |
| **Database** | Own QA database at `data/qa/qa.db` (separate from production) |
| **Status** | **Active** -- documented in CLAUDE.md and has its own README + USAGE guide |

### Pages (7 files, 6 visible pages + 1 hidden wizard)

| Page | File | Purpose |
|------|------|---------|
| Landing | `main.py` (59 lines) | Welcome page with instructions |
| 0 - QA Sessions | `pages/0_qa_sessions.py` (13.2 KB) | Guided testing session management (create, resume, abort sessions) |
| 1 - Run + Review | `pages/1_run_review.py` (9.0 KB) | Execute queries, view QueryPlan/SQL, label candidates |
| 2 - Find Missing | `pages/2_find_missing.py` (9.2 KB) | Search for false negatives via database queries |
| 3 - Dashboard | `pages/3_dashboard.py` (6.3 KB) | Analytics: label stats, worst queries, issue tag analysis |
| 4 - Gold Set | `pages/4_gold_set.py` (12.0 KB) | Export gold.json, manage queries, run regression |
| 5 - DB Explorer | `pages/5_db_explorer.py` (8.4 KB) | Read-only database table browser (records, imprints, titles, subjects, languages, agents) |
| Wizard (hidden) | `pages/_wizard.py` (26.1 KB) | Step-by-step guided QA workflow (underscore prefix prevents auto-discovery) |

### Supporting Code

| File | Purpose |
|------|---------|
| `config.py` | Database paths, issue tags, label types, 15 canonical test queries |
| `db.py` (17.5 KB) | Full SQLite data access layer for QA operations |
| `wizard_components.py` (10.9 KB) | Reusable Streamlit components for the wizard flow |

### Notes

- This is the only UI with a dedicated USAGE guide (`app/ui_qa/USAGE.md`).
- Contains 15 pre-defined canonical queries for systematic testing.
- The wizard page is intentionally hidden from Streamlit's auto-nav (prefixed with `_`) and is launched via `st.switch_page()`.
- The DB Explorer page (page 5) was not mentioned in the original design spec (which listed 5 pages) -- it was added later.

---

## 3. Chat UI (Streamlit Single-Page App)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `app/ui_chat/` |
| **Purpose** | Conversational discovery interface for searching the rare books collection |
| **Target Users** | End-users, researchers, librarians |
| **Tech Stack** | Streamlit 1.52+, Requests |
| **Entry Point** | `poetry run streamlit run app/ui_chat/main.py` or `./run_chat_ui.sh` |
| **API Dependency** | HTTP calls to FastAPI backend at `http://localhost:8000` (`POST /chat`, `GET /health`) |
| **Status** | **Active** -- has a dedicated launcher script (`run_chat_ui.sh`) |

### Features

- Chat-style interface with message history
- Session management (creates/resumes sessions via API)
- Clickable follow-up suggestions
- Expandable candidate result details with:
  - Clickable Primo catalog links (configured for Tel Aviv University: `tau.primo.exlibrisgroup.com`)
  - Author, date, place, publisher, subjects, description display
  - Evidence display from query filters
- Example queries in sidebar
- API health check with retry button
- Clarification display for ambiguous queries

### Supporting Code

| File | Purpose |
|------|---------|
| `config.py` | Primo URL generation (TAU-specific configuration) |
| `__init__.py` | Module marker |

### Launcher Script

`run_chat_ui.sh` (104 lines) -- a convenience wrapper that:
1. Kills existing API/Streamlit processes
2. Starts the FastAPI server in background
3. Waits for API readiness (health check polling)
4. Launches Streamlit with headless mode
5. Cleans up both processes on exit

### Notes

- The Primo URL configuration is hardcoded for Tel Aviv University, while the NLI Primo base URL appears in the Workbench (`Workbench.tsx` line 37). These are two different institutional configurations.
- Unlike the QA UI, this one requires the FastAPI backend to be running (remote HTTP calls, not in-process).

---

## 4. CLI (Typer)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `app/cli.py` |
| **Purpose** | Command-line interface for MARC pipeline operations and query execution |
| **Target Users** | Developers, system operators |
| **Tech Stack** | Typer |
| **Entry Point** | `python -m app.cli <command>` |
| **API Dependency** | None (calls scripts directly in-process) |
| **Status** | **Active** |

### Commands (5)

| Command | Purpose |
|---------|---------|
| `parse-marc` | Parse MARC XML to JSONL (M1 pipeline) |
| `chat-init` | Create a new chat session |
| `chat-history` | View session message history |
| `chat-cleanup` | Expire old sessions |
| `query` | Execute natural language queries against the bibliographic database (M4 pipeline) |

### Notes

- The `app/README.md` is stale -- it documents legacy RAG commands (`ingest`, `embed`, `retrieve`, `config`, `ask`) that no longer exist in `cli.py`. The actual CLI only has 5 MARC-specific commands.
- There is no `index` command in the CLI despite references to `python -m app.cli index` in CLAUDE.md and the metadata workbench docs. Indexing is done via `python -m scripts.marc.m3_index` directly.

---

## 5. QA Regression Runner (CLI)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `app/qa.py` |
| **Purpose** | Automated regression testing against gold set expectations |
| **Target Users** | Developers, CI/CD pipelines |
| **Tech Stack** | Typer |
| **Entry Point** | `python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db` |
| **API Dependency** | None (calls query pipeline directly) |
| **Status** | **Active** |

### Notes

- Uses exit code 0 (pass) or 1 (fail) for CI integration.
- Companion to the QA Tool UI -- the QA Tool exports gold.json, this runner validates against it.

---

## 6. FastAPI Backend (Shared API Layer)

### Overview

| Property | Value |
|----------|-------|
| **Location** | `app/api/` |
| **Purpose** | Central HTTP API serving the Chat UI, Metadata Workbench, and exposing auto-generated interactive docs |
| **Target Users** | Frontend clients, developers (via Swagger UI) |
| **Tech Stack** | FastAPI 0.115, Pydantic, Uvicorn, slowapi (rate limiting), CORS middleware |
| **Entry Point** | `uvicorn app.api.main:app --reload` (at `http://localhost:8000`) |
| **Status** | **Active** |

### Endpoints

#### Core Chat Endpoints (in `main.py`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check (DB + session store status) |
| `POST` | `/chat` | Natural language query with session support |
| `GET` | `/sessions/{session_id}` | Get session details and message history |
| `DELETE` | `/sessions/{session_id}` | Expire a session |
| `WebSocket` | `/ws/chat` | Real-time streaming query results |

#### Metadata Endpoints (in `metadata.py`, mounted as `/metadata/*`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/metadata/coverage` | Coverage stats per field |
| `GET` | `/metadata/issues` | Low-confidence records (paginated) |
| `GET` | `/metadata/unmapped` | Unmapped values by frequency |
| `GET` | `/metadata/methods` | Method distribution |
| `GET` | `/metadata/clusters` | Gap clusters |
| `POST` | `/metadata/corrections` | Submit single correction |
| `GET` | `/metadata/corrections/history` | Correction audit trail |
| `POST` | `/metadata/corrections/batch` | Batch corrections |
| `POST` | `/metadata/primo-urls` | Batch Primo URL generation |
| `GET` | `/metadata/records/{mms_id}/primo` | Single Primo URL |
| `POST` | `/metadata/agent/chat` | Agent conversation |
| `GET` | `/metadata/publishers` | Publisher authority records |

#### Auto-Generated UI

FastAPI automatically provides interactive API documentation at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

These are not custom-built but are valuable developer-facing UIs generated from the Pydantic models.

### API Layer Size

| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 1,130 | Core endpoints, lifecycle, CORS, rate limiting, WebSocket |
| `metadata.py` | 1,459 | Metadata quality endpoints (12 routes) |
| `metadata_models.py` | 377 | Pydantic response models for metadata endpoints |
| `models.py` | 58 | Pydantic models for chat endpoints |
| **Total** | **3,024** | |

---

## Cross-Cutting Observations

### Technology Stack Fragmentation

The project uses three UI frameworks:
1. **React 19** (TypeScript, Vite, Tailwind) -- for the Metadata Workbench
2. **Streamlit 1.52** -- for the QA Tool and Chat UI
3. **Typer** -- for CLI commands

### API Dependency Map

```
                          FastAPI Backend (:8000)
                         /        |        \
                        /         |         \
    React Workbench (:5173)  Chat UI (:8501)  Swagger/ReDoc (:8000/docs)
    [HTTP: /metadata/*]    [HTTP: /chat]     [auto-generated]

    QA Tool (:8501)         CLI
    [in-process, no API]    [in-process, no API]
```

### Institutional Configuration Inconsistency

Two different Primo catalog configurations exist:
- **Chat UI** (`app/ui_chat/config.py`): Tel Aviv University (`tau.primo.exlibrisgroup.com`, VID: `972TAU_INST:NDE`)
- **Workbench** (`frontend/src/pages/Workbench.tsx` line 37): NLI (`primo.nli.org.il`, VID: `972NNL_INST`)

### Documentation Gaps

- `app/README.md` is entirely stale (documents RAG commands that no longer exist).
- CLAUDE.md references `python -m app.cli index` but no `index` command exists in `cli.py`.
- The `frontend/index.html` title and `package.json` name are both the generic "frontend" -- not branded.

### Build/Deploy State

- The React frontend has a `dist/` build but no serving mechanism from the backend. In development, it relies on Vite's proxy.
- No Docker, docker-compose, or deployment configuration was found.
- No production WSGI/ASGI server configuration beyond the basic `uvicorn` command.

### No Hidden UIs Found

Scanned for and confirmed absent:
- Jupyter notebooks (`.ipynb`)
- Gradio interfaces
- Dash/Plotly dashboards
- Panel applications
- Scripts importing visualization libraries (matplotlib, plotly)

---

## Summary Table

| UI | Location | Stack | Port | API Dependency | Target User | Status |
|----|----------|-------|------|----------------|-------------|--------|
| Metadata Workbench | `frontend/` | React + Vite | 5173 | HTTP to :8000 | Librarians | Active |
| QA Tool | `app/ui_qa/` | Streamlit | 8501 | In-process | Developers | Active |
| Chat UI | `app/ui_chat/` | Streamlit | 8501 | HTTP to :8000 | End-users | Active |
| CLI | `app/cli.py` | Typer | N/A | In-process | Operators | Active |
| QA Regression | `app/qa.py` | Typer | N/A | In-process | CI/CD | Active |
| API Backend | `app/api/` | FastAPI | 8000 | N/A (is the API) | Frontends | Active |
| Swagger/ReDoc | auto-generated | FastAPI | 8000 | N/A | Developers | Active |
