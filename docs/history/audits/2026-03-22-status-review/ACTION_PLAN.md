# Action Plan
**Date**: 2026-03-22
**Based on**: AUDIT_REPORT.md findings

---

## Phase 1: Fix Broken State (Immediate)

### 1.1 Fix 13 Failing Tests
**Findings**: FINDING-01, FINDING-05, FINDING-06

| Fix | File | Effort |
|-----|------|--------|
| Add `record_id` column to TestGetIssues fixture | `tests/app/test_metadata_api.py` | Small |
| Fix `detect_script()` tie-breaking logic | `scripts/metadata/clustering.py` | Small |
| Remove `subjects` from outer JOIN in FTS5 path | `scripts/query/db_adapter.py` | Small |

**Acceptance**: `pytest` reports 0 failures

### 1.2 Auto-Fix Lint Errors
**Finding**: FINDING-04

```bash
ruff check --fix .
# Then manually address remaining ~414 errors
```

**Acceptance**: `ruff check .` exits 0

---

## Phase 2: Strengthen Contracts (Short-Term)

### 2.1 Evidence Extraction Fail-Closed
**Finding**: FINDING-02

- Replace `print()` warning in `execute.py:560-562` with proper error handling
- Options: (a) raise `QueryExecutionError`, (b) mark evidence as "extraction_failed" with explicit flag
- Add test for evidence extraction failure path

### 2.2 CandidateSet Validators
**Finding**: FINDING-11

- Add `@model_validator` to `Candidate` ensuring evidence list non-empty
- Add validation that evidence sources reference valid MARC fields
- Add test coverage for validator rejection

### 2.3 M3 Schema Runtime Validation
- On first DB connection, verify table/column existence matches `m3_contract.py`
- Fail fast with clear error if schema has drifted

---

## Phase 3: Improve Date Coverage (Medium-Term)

### 3.1 Analyze Unparsed Date Patterns
**Finding**: FINDING-03

```sql
-- Find most common unparsed date patterns
SELECT date_raw, date_method, COUNT(*) as cnt
FROM imprints
WHERE date_confidence < 0.90
GROUP BY date_raw, date_method
ORDER BY cnt DESC
LIMIT 30;
```

### 3.2 Expand Date Normalization Rules
- Identify top unparsed patterns from 3.1
- Add new deterministic rules for Hebrew calendar dates, abbreviated forms
- Consider DateAgent-assisted proposals for complex cases
- Target: reduce low-confidence from 881 → <280 (10% threshold)

---

## Phase 4: Code Health (Medium-Term)

### 4.1 Migrate Deprecated APIs
**Findings**: FINDING-08, FINDING-09

- `scripts/marc/models.py`: Replace `class Config` with `model_config = ConfigDict(...)`
- `app/api/main.py`: Replace `@app.on_event("shutdown")` with lifespan handler

### 4.2 Split Large API Files
**Finding**: FINDING-07

Proposed structure:
```
app/api/
├── main.py          (app setup, health, chat endpoints)
├── metadata/
│   ├── __init__.py  (router)
│   ├── coverage.py  (coverage, methods, clusters)
│   ├── issues.py    (issues, unmapped)
│   ├── corrections.py (corrections, feedback)
│   ├── agents.py    (agent chat)
│   └── publishers.py (publisher authorities)
```

---

## Phase 5: Production Readiness (Longer-Term)

### 5.1 Frontend Tests
**Finding**: FINDING-10
- Add Vitest + React Testing Library
- Smoke tests for Dashboard, Workbench, AgentChat, Review pages

### 5.2 End-to-End Answer Contract Test
- Integration test that runs a known query through full pipeline
- Validates: QueryPlan present, CandidateSet non-empty, Evidence per candidate, raw+normalized pairs

---

## Priority Summary

| Phase | Items | Impact | Effort |
|-------|-------|--------|--------|
| 1. Fix broken state | Fix tests, lint | Unblocks CI/QA | **Small** |
| 2. Strengthen contracts | Evidence, validators, schema check | Data integrity | **Medium** |
| 3. Date coverage | Analyze + expand rules | 31.8% gap → <10% | **Medium-Large** |
| 4. Code health | Deprecations, split files | Maintainability | **Medium** |
| 5. Production readiness | Frontend tests, E2E test | Release confidence | **Large** |
