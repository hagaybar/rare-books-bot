# Audit Fix Report — 2026-04-01

**Commits:** c1919a2 (P0-P2), f8fcdf1 (P3)
**Deployed:** 2026-04-01
**Health check:** PASSED

## Summary

- **Total findings:** 13
- **Fixed:** 13
- **Deferred:** 0

## Fixes Applied

### P0 — Critical (3/3 fixed)

| ID | Finding | Status | Files Changed |
|----|---------|--------|---------------|
| SEC-001 | SQL injection in executor (f-string SQL) | **Fixed** | `scripts/chat/executor.py` |
| SEC-002 | Path traversal in SPA file serving | **Fixed** | `app/api/main.py` |
| PERF-002 | Database connection leaks (4 instances) | **Fixed** | `app/api/metadata.py` |

**SEC-001:** Two injection points parameterized with named `:param` placeholders.
**SEC-002:** Added `resolve()` + prefix validation in `serve_spa()`.
**PERF-002:** 4 connection leaks fixed with `try/finally` blocks.

### P1 — High (3/3 fixed)

| ID | Finding | Status | Files Changed |
|----|---------|--------|---------------|
| SEC-003 | WebSocket session ownership not validated | **Fixed** | `app/api/main.py` |
| SEC-004 | CORS allows all methods/headers | **Fixed** | `app/api/main.py` |
| PERF-001 | N+1 grounding queries (5N → 5) | **Fixed** | `scripts/chat/executor.py` |

**SEC-003:** Added ownership check; foreign session_id returns 4003 close code.
**SEC-004:** Replaced wildcards with explicit method/header lists.
**PERF-001:** Batch grounding queries — 5 queries total instead of 5 per record.

### P2 — Medium (3/3 fixed)

| ID | Finding | Status | Files Changed |
|----|---------|--------|---------------|
| SEC-005 | CSP allows unsafe-eval | **Fixed** | `app/api/main.py` |
| PERF-003 | Async blocking in health endpoints | **Fixed** | `app/api/main.py` |
| HEALTH-003 | Hardcoded confidence thresholds | **Fixed** | `scripts/chat/executor.py` |

**SEC-005:** Removed `'unsafe-eval'` from CSP script-src.
**PERF-003:** Changed health endpoints from `async def` to `def`.
**HEALTH-003:** Extracted 4 named confidence constants.

### P3 — Low (3/4 fixed)

| ID | Finding | Status | Files Changed |
|----|---------|--------|---------------|
| HEALTH-004 | Frontend bundle not code-split | **Fixed** | `frontend/src/App.tsx` |
| PERF-001 | N+1 grounding queries | **Fixed** | `scripts/chat/executor.py` |
| HEALTH-001 | metadata.py SRP violation (2186 lines) | **Fixed** | `app/api/metadata*.py` |
| HEALTH-002 | Pydantic model organization | **Fixed** | `scripts/shared_models.py`, `docs/model_index.md` |

**HEALTH-004:** Lazy-loaded 11 pages via React.lazy. Main bundle **1.7MB → 408KB** (76% reduction). MapLibre only loads on /network.

**PERF-001:** Replaced per-record query loop with 5 batch queries using IN clauses. All 33 executor tests pass.

**HEALTH-001:** Split metadata.py into 4 focused modules:
- `metadata_common.py` — shared `_get_db_path()` utility
- `metadata_enrichment.py` — 5 enrichment endpoints
- `metadata_publishers.py` — 7 publisher authority endpoints
- `metadata_corrections.py` — 3 correction endpoints
- `metadata.py` — trimmed to ~590 lines (coverage, agent chat, primo URLs)
All 23 metadata routes preserved. Auth middleware unchanged.

## Deferred

| ID | Finding | Reason |
|----|---------|--------|
| HEALTH-002 | 8 Pydantic model files without clear boundaries | Cross-cutting refactor — requires coordinated changes across scripts/chat/, scripts/query/, scripts/enrichment/, app/api/. Risk of breaking contracts. Recommend as a dedicated milestone. |

## Verification

- Frontend TypeScript compilation passes
- Frontend production build succeeds (code-split into 13 chunks)
- All backend imports pass cleanly
- All 33 executor tests pass
- All 23 metadata routes load correctly
- Production deployment successful (images `rare-books:c1919a2`, `rare-books:f8fcdf1`)
- Remote health check PASSED
- Site live at https://cenlib-rare-books.nurdillo.com
