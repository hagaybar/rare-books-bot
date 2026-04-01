# Action Plan — Full-Stack Audit 2026-04-01

## Phase 1: Critical Security & Stability (P0)

### 1.1 Fix SQL injection in executor.py
- **Finding:** SEC-001
- **Files:** `scripts/chat/executor.py:657,677`
- **Action:** Replace all f-string SQL with parameterized `?` placeholders
- **Verify:** `rg "f['\"].*SELECT|f['\"].*WHERE|f['\"].*INSERT" scripts/` returns zero hits with user-influenced values
- **Rollback:** Revert commit; no data migration needed

### 1.2 Fix path traversal in SPA serving
- **Finding:** SEC-002
- **Files:** `app/api/main.py:1054-1060`
- **Action:** Add `resolve()` + prefix validation before serving files
- **Verify:** `curl https://site/../../etc/passwd` returns 404
- **Rollback:** Revert commit

### 1.3 Fix connection leaks in metadata.py
- **Finding:** PERF-002
- **Files:** `app/api/metadata.py` (21 instances)
- **Action:** Wrap all `sqlite3.connect()` usage in `try/finally` with `conn.close()`
- **Verify:** `grep -A5 "sqlite3.connect" app/api/metadata.py` shows all have finally blocks
- **Rollback:** Revert commit

---

## Phase 2: High-Priority Fixes (P1)

### 2.1 Batch grounding queries
- **Finding:** PERF-001
- **Files:** `scripts/chat/executor.py:1219-1277`
- **Action:** Replace per-record loop with batch JOIN query
- **Verify:** Chat response time with 30 results < 2 seconds
- **Rollback:** Keep old function behind feature flag

### 2.2 WebSocket session ownership
- **Finding:** SEC-003
- **Files:** `app/api/main.py:864-879`
- **Action:** Add ownership check matching REST endpoint pattern
- **Verify:** WebSocket with foreign session_id gets 4003 close code

### 2.3 Tighten CORS
- **Finding:** SEC-004
- **Files:** `app/api/main.py:128-136`
- **Action:** Replace `"*"` with explicit method/header lists
- **Verify:** Preflight OPTIONS returns only listed methods

---

## Phase 3: Medium-Priority (P2)

### 3.1 Remove unsafe-eval from CSP
### 3.2 Fix async blocking in health endpoints
### 3.3 Add frontend code splitting for MapLibre

---

## Phase 4: Technical Debt (P3)

### 4.1 Refactor metadata.py into focused modules
### 4.2 Consolidate Pydantic model definitions
### 4.3 Extract confidence threshold constants
