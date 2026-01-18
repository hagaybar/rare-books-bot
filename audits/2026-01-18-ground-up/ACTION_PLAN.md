# Action Plan: Ground-Up Audit Remediation

**Date:** 2026-01-18
**Based On:** FINDINGS.yaml from same audit

---

## Priority Order

Actions ordered by: P0 first, then P1, then P2. Within each priority, ordered by estimated impact.

---

## Phase 1: Critical Fixes (P0)

### Action 1.1: Fix FTS5 Quoting Issue

**Finding:** DET-001
**Estimated Effort:** 2-3 hours
**Risk:** Medium (changes query behavior)

**Steps:**
1. Modify `normalize_filter_value()` to accept operation parameter:
   ```python
   def normalize_filter_value(field: FilterField, raw_value: str, op: FilterOp = None) -> str:
   ```

2. Only apply FTS5 quoting when `op == FilterOp.CONTAINS`:
   ```python
   elif field == FilterField.TITLE or field == FilterField.SUBJECT:
       value = raw_value.lower()
       # Only quote for FTS5 CONTAINS operations
       if op == FilterOp.CONTAINS and ' ' in value:
           value = value.replace('"', '""')
           value = f'"{value}"'
       return value
   ```

3. Update all call sites in `build_where_clause()` to pass operation:
   ```python
   params[param_name] = normalize_filter_value(filter.field, filter.value, filter.op)
   ```

4. Run tests:
   ```bash
   poetry run pytest tests/scripts/query/test_db_adapter.py -v
   poetry run pytest tests/scripts/query/ -v
   ```

**Verification:**
```bash
poetry run pytest tests/scripts/query/test_db_adapter.py::TestNormalizeFilterValue -v
# All tests should pass
```

**Rollback:** Revert changes to `db_adapter.py`

---

### Action 1.2: Fix Remaining Test Failures

**Finding:** DET-002
**Estimated Effort:** 1-2 hours (after Action 1.1)
**Risk:** Low

**Steps:**
1. Run full test suite:
   ```bash
   poetry run pytest tests/ -v --tb=short 2>&1 | tee test_results.txt
   ```

2. Categorize remaining failures:
   - FTS5-related (should be fixed by 1.1)
   - API key handling (test environment issue)
   - Relator code mapping (data issue)
   - Other

3. Fix each category:
   - API key tests: Ensure proper mocking
   - Relator codes: Update test expectations OR fix mapping
   - Other: Case-by-case

**Verification:**
```bash
poetry run pytest tests/ -q --tb=no
# Expected: 0 failed
```

**Rollback:** Revert individual fixes

---

## Phase 2: Data Integrity (P1)

### Action 2.1: Expand Country Code Mapping

**Finding:** DATA-001
**Estimated Effort:** 1-2 hours
**Risk:** Low

**Steps:**
1. Download full MARC country code list:
   - Source: https://www.loc.gov/marc/countries/countries_code.html

2. Update mapping file:
   ```bash
   # Edit data/normalization/marc_country_codes.json
   # Add all missing codes
   ```

3. Rebuild database:
   ```bash
   # Backup first
   cp data/index/bibliographic.db data/index/bibliographic.db.pre-country-fix

   # Rebuild
   poetry run python -m scripts.marc.m3_index \
     data/m2/records_m1m2.jsonl \
     data/index/bibliographic.db \
     scripts/marc/m3_schema.sql
   ```

4. Verify:
   ```bash
   poetry run python -c "
   import sqlite3
   conn = sqlite3.connect('data/index/bibliographic.db')
   c = conn.cursor()
   c.execute('SELECT COUNT(*) FROM imprints WHERE country_name IS NULL AND country_code IS NOT NULL')
   print('Unmapped codes:', c.fetchone()[0])
   "
   # Expected: 0 or very few
   ```

**Rollback:** Restore from backup

---

### Action 2.2: Fix datetime.utcnow() Deprecation

**Finding:** COMPAT-001
**Estimated Effort:** 30 minutes
**Risk:** Very Low

**Steps:**
1. Search and replace in `scripts/chat/session_store.py`:
   ```python
   # Before:
   datetime.utcnow()
   # After:
   datetime.now(timezone.utc)
   ```

2. Add import if needed:
   ```python
   from datetime import datetime, timezone
   ```

3. Apply to all files:
   ```bash
   grep -r "utcnow()" scripts/ --include="*.py"
   # Fix each occurrence
   ```

4. Run tests with deprecation errors:
   ```bash
   poetry run pytest tests/ -W error::DeprecationWarning 2>&1 | head -50
   ```

**Verification:**
```bash
poetry run pytest tests/ 2>&1 | grep -c "utcnow.*deprecated"
# Expected: 0
```

**Rollback:** Revert changes (trivial)

---

## Phase 3: Architecture & Quality (P1-P2)

### Action 3.1: Add Tests for is_overview_query

**Finding:** TEST-001
**Estimated Effort:** 1 hour
**Risk:** None

**Steps:**
1. Create test file:
   ```bash
   touch tests/scripts/chat/test_aggregation.py
   ```

2. Add test cases:
   ```python
   import pytest
   from scripts.chat.aggregation import is_overview_query

   class TestIsOverviewQuery:
       def test_returns_true_for_generic_overview(self):
           assert is_overview_query("tell me about the collection") == True
           assert is_overview_query("what do you have") == True
           assert is_overview_query("hi") == True

       def test_returns_false_for_specific_search(self):
           assert is_overview_query("Hebrew books from Venice") == False
           assert is_overview_query("books about astronomy") == False
           assert is_overview_query("16th century books") == False

       def test_edge_cases(self):
           assert is_overview_query("") == False
           assert is_overview_query("   ") == False
           assert is_overview_query("?") == True
   ```

3. Run tests:
   ```bash
   poetry run pytest tests/scripts/chat/test_aggregation.py -v
   ```

**Verification:** All new tests pass

**Rollback:** Delete test file (no production impact)

---

### Action 3.2: Document or Remove Legacy Code

**Finding:** CODE-001, CODE-002
**Estimated Effort:** 1-2 hours
**Risk:** Low

**Steps:**
1. Check m3_query.py usage:
   ```bash
   grep -r "from scripts.marc.m3_query" scripts/ app/ tests/
   grep -r "m3_query" scripts/ app/ tests/
   ```

2. If unused, remove:
   ```bash
   git rm scripts/marc/m3_query.py
   ```

3. For FilterField.AGENT, add deprecation docstring:
   ```python
   AGENT = "agent"
   """Deprecated: Use AGENT_NORM, AGENT_ROLE, or AGENT_TYPE instead.
   Will be removed in version 2.0."""
   ```

**Verification:**
- Tests pass after removal
- No runtime errors

**Rollback:** `git checkout scripts/marc/m3_query.py`

---

## Summary Checklist

| # | Action | Priority | Effort | Status |
|---|--------|----------|--------|--------|
| 1.1 | Fix FTS5 quoting | P0 | 2-3h | ⬜ |
| 1.2 | Fix remaining tests | P0 | 1-2h | ⬜ |
| 2.1 | Expand country codes | P1 | 1-2h | ⬜ |
| 2.2 | Fix utcnow() deprecation | P1 | 30m | ⬜ |
| 3.1 | Add overview query tests | P2 | 1h | ⬜ |
| 3.2 | Document/remove legacy code | P2 | 1-2h | ⬜ |

**Total Estimated Effort:** 7-11 hours

---

## Success Criteria

After completing all actions:

1. **Tests:** `poetry run pytest tests/ -q` shows 0 failures
2. **Warnings:** No utcnow() deprecation warnings
3. **Data:** `SELECT COUNT(*) FROM imprints WHERE country_name IS NULL` returns 0 or very few
4. **Coverage:** is_overview_query() has unit tests
5. **Code:** No obviously dead code files
