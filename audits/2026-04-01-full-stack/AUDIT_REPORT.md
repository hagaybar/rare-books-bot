# Full-Stack Audit Report — Rare Books Bot

**Date:** 2026-04-01
**Scope:** Security, performance, code health, architecture
**Codebase:** 80+ Python files, 40+ TypeScript files, 1,433 tests

---

## Executive Summary

**Overall Health: 6.5 / 10**

The project is a functional bibliographic discovery system with a solid 3-stage query pipeline (interpret → execute → narrate), a React SPA frontend, and Docker-based deployment. The architecture is well-conceived with clear separation between MARC parsing, normalization, query execution, and LLM narration.

**Critical areas requiring immediate attention:**
1. SQL injection vulnerabilities in the executor (string interpolation in WHERE clauses)
2. Path traversal in SPA file serving
3. Database connection leaks in error paths (21 instances in metadata.py)
4. N+1 query pattern in grounding collection (5 queries × N records)

**Strengths:** Good test coverage (1,433 tests), proper JWT auth with refresh tokens, evidence-based LLM grounding, deterministic query execution, and well-structured MARC pipeline.

---

## 1. Inferred Project Model

### Core Responsibilities
- Parse MARC XML bibliographic records into a queryable SQLite database
- Accept natural language queries and compile them to SQL via LLM-assisted interpretation
- Execute queries deterministically and produce evidence-backed scholarly responses
- Provide a metadata quality workbench for human-in-the-loop correction
- Visualize scholarly networks on an interactive map

### Primary Workflows
1. **Ingestion:** MARC XML → M1 Parse → M2 Normalize → M3 Index → Enrichment → Network tables
2. **Query:** User query → LLM interpreter → SQL executor → LLM narrator → Streamed response
3. **Metadata QA:** Coverage audit → Issue detection → Correction → Re-normalization

### Non-Goals (Explicit)
- Not a general RAG platform — no embedding-based retrieval
- No destructive normalization — raw MARC values always preserved
- LLM is planner/explainer, not the authority

---

## 2. Architecture Map

```
Frontend (React SPA)                    Backend (FastAPI)
┌──────────────────┐                   ┌──────────────────────────┐
│ Chat.tsx         │──WebSocket/HTTP──>│ main.py (1060 lines)     │
│ Network.tsx      │                   │  ├─ /chat, /ws/chat      │
│ Enrichment.tsx   │                   │  ├─ /metadata/*          │
│ Coverage.tsx     │                   │  ├─ /network/*           │
│ DB Explorer      │                   │  └─ /diagnostics/*       │
└──────────────────┘                   └──────────┬───────────────┘
                                                  │
                                       ┌──────────▼───────────────┐
                                       │ Scholar Pipeline          │
                                       │  interpreter.py (886 ln) │
                                       │  executor.py (1408 ln)   │
                                       │  narrator.py (981 ln)    │
                                       └──────────┬───────────────┘
                                                  │
                                       ┌──────────▼───────────────┐
                                       │ SQLite: bibliographic.db │
                                       │  records, imprints,      │
                                       │  agents, subjects,       │
                                       │  network_*, wikipedia_*  │
                                       └──────────────────────────┘
```

### Key File Sizes (Risk Indicators)
| File | Lines | Concern |
|------|-------|---------|
| `app/api/metadata.py` | 2,186 | Extreme — 40+ endpoints, mixed concerns |
| `scripts/chat/executor.py` | 1,408 | Large — 30+ handler functions |
| `app/api/main.py` | 1,060 | Large — app setup + pipeline + middleware |
| `scripts/chat/narrator.py` | 981 | Moderate — prompt building + streaming |
| `scripts/chat/interpreter.py` | 886 | Moderate — acceptable for complexity |

### Hotspots (Most Changed Files)
| File | Changes | Risk |
|------|---------|------|
| `app/api/main.py` | 29 commits | High churn, regression risk |
| `CLAUDE.md` | 19 commits | Documentation keeping pace — good |
| `scripts/query/db_adapter.py` | 13 commits | Stabilizing |
| `frontend/src/pages/Chat.tsx` | 11 commits | Active development |
| `scripts/chat/narrator.py` | 8 commits | Recent token-saving changes |

---

## 3. Critical Findings — Security

### SEC-001: SQL Injection in Executor (CRITICAL)
**File:** `scripts/chat/executor.py:657,677`
```python
# Line 677 — MMS IDs concatenated directly
placeholders = ",".join(f"'{mms}'" for mms in scope_ids)
scope_clause = f" AND r.mms_id IN ({placeholders})"

# Line 657 — Filter values in WHERE clause
values_sql = ", ".join(f"LOWER('{v}')" for v in all_values)
```
**Risk:** If filter values contain `'`, SQL injection is possible. Even though values currently come from the LLM interpreter (not direct user input), the LLM can be manipulated via prompt injection.
**Fix:** Use parameterized queries with `?` placeholders.

### SEC-002: Path Traversal in SPA Serving (HIGH)
**File:** `app/api/main.py:1054-1060`
```python
file_path = _frontend_dir / full_path
if file_path.is_file():
    return FileResponse(file_path)
```
**Risk:** `../` sequences can read files outside `frontend/dist/`.
**Fix:** `file_path.resolve()` and verify it starts with `_frontend_dir.resolve()`.

### SEC-003: WebSocket Session Ownership Not Validated (MEDIUM)
**File:** `app/api/main.py:864-879`
**Risk:** A user can access another user's chat session by providing their session_id in the WebSocket message. The REST endpoint checks ownership; WebSocket doesn't.

### SEC-004: CORS Allows All Methods and Headers (MEDIUM-HIGH)
**File:** `app/api/main.py:128-136`
```python
allow_methods=["*"], allow_headers=["*"], allow_credentials=True
```
**Fix:** Restrict to `["GET", "POST", "DELETE", "OPTIONS"]` and `["Content-Type"]`.

### SEC-005: CSP Allows unsafe-eval (MEDIUM)
**File:** `app/api/main.py:152`
**Fix:** Remove `'unsafe-eval'` from script-src. Vite production builds don't need it.

---

## 4. Critical Findings — Performance

### PERF-001: N+1 Queries in Grounding Collection (HIGH)
**File:** `scripts/chat/executor.py:1219-1277`
For each MMS ID, 5 separate queries run (title, imprint, language, agents, subjects). With 30 records = 150 queries per chat request.
**Fix:** Single batch query with JOINs and GROUP_CONCAT.

### PERF-002: Database Connection Leaks (HIGH)
**File:** `app/api/metadata.py` — 21 instances
Connections opened with `sqlite3.connect()` not closed in error paths. Missing `try/finally` pattern.
**Fix:** Wrap all connection usage in `try/finally` blocks.

### PERF-003: Synchronous Blocking in Async Endpoints (MEDIUM)
**File:** `app/api/main.py:315-360`
Health check endpoints are `async def` but perform synchronous SQLite I/O, blocking the event loop.
**Fix:** Use `loop.run_in_executor()` or make them sync `def`.

### PERF-004: No Connection Pooling (MEDIUM)
Each request opens a new SQLite connection. Under concurrent load, the write lock becomes a bottleneck.

---

## 5. Code Health & Technical Debt

### HEALTH-001: metadata.py Violates SRP (2,186 lines)
Acts as HTTP router, database query layer, business logic, file I/O manager, alias map manager, correction handler, publisher authority manager, enrichment aggregator, and agent chat orchestrator.
**Recommendation:** Split into 4-5 focused modules.

### HEALTH-002: 8 Pydantic Model Files Without Clear Boundaries
Models spread across: `scripts/chat/models.py`, `plan_models.py`, `scripts/schemas/query_plan.py`, `app/api/models.py`, `auth_models.py`, `metadata_models.py`, `scripts/enrichment/models.py`, `scripts/query/models.py`.
**Risk:** Schema drift, duplicate definitions.

### HEALTH-003: Hardcoded Confidence Thresholds
Values like 0.95, 0.90, 0.80, 0.70 appear as magic numbers in 5+ locations across executor.py and metadata.py.
**Fix:** Extract to module-level constants.

### HEALTH-004: Frontend Bundle Not Code-Split
Vite produces a single 1.7MB JS bundle. MapLibre GL (~1MB) should be lazy-loaded since it's only used on the Network page.

---

## 6. Test Effectiveness

| Area | Coverage | Assessment |
|------|----------|------------|
| MARC parsing | Strong | Good edge case coverage |
| Normalization | Strong | Date, place, publisher well tested |
| Query pipeline | Moderate | Unit tests present; integration tests require API key |
| API endpoints | Moderate | 13 test files in tests/app/ |
| Frontend | Weak | No test files found |
| Security | Moderate | Auth/injection tested in security audit |
| WebSocket streaming | Weak | Only 4 WebSocket tests |

**Gap:** No frontend tests (React components, streaming, session management). The most bug-prone area (Chat.tsx) has zero automated tests.

---

## 7. Positive Findings

1. **Evidence-grounded architecture** — narrator can only cite records from verified grounding data
2. **Deterministic execution** — SQL-based query execution is reproducible and inspectable
3. **Raw data preservation** — MARC values always preserved alongside normalizations
4. **Comprehensive CLAUDE.md** — 700+ lines of accurate, maintained documentation
5. **Good test count** — 1,433 tests covering core pipeline
6. **Proper JWT auth** — refresh tokens, bcrypt hashing, rate limiting on login
7. **Audit logging** — all auth and chat actions logged
8. **Token tracking** — input/output/cost breakdown per model
9. **Fallback design** — narrator falls back to deterministic response on LLM failure
10. **Session persistence** — localStorage + backend for cross-refresh continuity

---

## 8. Priority Action Plan

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| **P0** | SEC-001: Fix SQL injection in executor | 4h | Critical security |
| **P0** | SEC-002: Fix path traversal in SPA serving | 30m | High security |
| **P0** | PERF-002: Fix connection leaks in metadata.py | 2h | Stability |
| **P1** | PERF-001: Fix N+1 grounding queries | 4h | Performance |
| **P1** | SEC-003: Add WebSocket session ownership check | 30m | Security |
| **P1** | SEC-004: Tighten CORS config | 15m | Security |
| **P2** | SEC-005: Remove unsafe-eval from CSP | 15m | Security |
| **P2** | PERF-003: Fix async blocking calls | 1h | Performance |
| **P2** | HEALTH-004: Frontend code splitting | 2h | Performance |
| **P3** | HEALTH-001: Refactor metadata.py | 8h | Maintainability |
| **P3** | HEALTH-002: Consolidate model files | 4h | Maintainability |
| **P3** | HEALTH-003: Extract confidence constants | 1h | Maintainability |
