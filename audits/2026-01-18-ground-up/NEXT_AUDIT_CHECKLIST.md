# Next Audit Checklist

**Purpose:** Reusable playbook for future ground-up audits of this codebase.

---

## Pre-Audit Setup

### 1. Gather Inputs

```bash
# Git status and recent history
git status
git log --oneline -20

# Directory structure
find . -type d -not -path './.venv/*' -not -path './.git/*' | head -30

# File counts by type
find . -name "*.py" -not -path "./.venv/*" | wc -l
find . -name "*.sql" -not -path "./.venv/*" | wc -l
find . -name "*.json" -not -path "./.venv/*" | wc -l
```

### 2. Check Data Artifacts

```bash
# Database existence and size
ls -lh data/index/bibliographic.db
ls -lh data/chat/sessions.db

# Record counts
poetry run python -c "
import sqlite3
conn = sqlite3.connect('data/index/bibliographic.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM records')
print('Records:', c.fetchone()[0])
c.execute('SELECT COUNT(*) FROM imprints')
print('Imprints:', c.fetchone()[0])
"

# Cache file sizes
wc -l data/query_plan_cache.jsonl
wc -l data/intent_cache.jsonl
```

### 3. Run Test Suite

```bash
# Full test run with summary
poetry run pytest tests/ -q --tb=no 2>&1 | tail -10

# Save detailed results
poetry run pytest tests/ -v --tb=short > audit_test_results.txt 2>&1
```

---

## Audit Phases

### Phase 0: Repository Reconnaissance

**Checklist:**
- [ ] Map directory structure (top 2-3 levels)
- [ ] Identify entry points (CLI, API, UI)
- [ ] List persistent state stores (DBs, JSON, cache files)
- [ ] Check recent git commits for context

**Commands:**
```bash
# Entry points
grep -r "def main\|app = \|@app\." app/ scripts/ --include="*.py" | head -20

# Imports graph (key modules)
grep -r "^from scripts\." scripts/ --include="*.py" | cut -d: -f2 | sort | uniq -c | sort -rn | head -20
```

### Phase 1: Data Flow Reconstruction

**Checklist:**
- [ ] Trace MARC XML → Canonical JSONL
- [ ] Trace Canonical → Normalized
- [ ] Trace Normalized → SQLite
- [ ] Document what is preserved/discarded at each step

**Commands:**
```bash
# Sample canonical record
head -1 data/canonical/records.jsonl | python -m json.tool | head -50

# Sample normalized record
head -1 data/m2/records_m1m2.jsonl | python -m json.tool | head -50

# Database schema
poetry run python -c "
import sqlite3
conn = sqlite3.connect('data/index/bibliographic.db')
c = conn.cursor()
c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
for t in c.fetchall(): print(t[0])
"
```

### Phase 2: Query & Execution Path

**Checklist:**
- [ ] Trace NL query → QueryPlan (LLM)
- [ ] Trace QueryPlan → SQL
- [ ] Trace SQL → CandidateSet
- [ ] Document evidence attachment

**Commands:**
```bash
# Sample query plan from cache
tail -1 data/query_plan_cache.jsonl | python -m json.tool

# Check db_adapter for SQL generation
grep "def build_" scripts/query/db_adapter.py
```

### Phase 3: Determinism Analysis

**Checklist:**
- [ ] Identify all LLM call points
- [ ] Check for caching mechanisms
- [ ] Find random/time-dependent code
- [ ] Document failure modes

**Commands:**
```bash
# LLM usage
grep -r "OpenAI\|client\." scripts/ --include="*.py" | grep -v "test"

# Randomness/time
grep -r "random\|datetime.now\|uuid\|time.time" scripts/ --include="*.py"

# Cache files
ls -la data/*.jsonl
```

### Phase 4: Validation Runs

**Checklist:**
- [ ] Run test suite
- [ ] Execute sample CLI commands
- [ ] Test API endpoints (if running)
- [ ] Capture outputs

**Commands:**
```bash
# Test suite
poetry run pytest tests/ -v --tb=short 2>&1 | tee audit_tests.txt

# CLI query (requires OPENAI_API_KEY)
poetry run python -m app.cli query "books from Venice" --db data/index/bibliographic.db

# API health (if running)
curl http://localhost:8000/health
```

### Phase 5: Gap & Drift Analysis

**Checklist:**
- [ ] Compare plan.mf to actual implementation
- [ ] Check for abandoned features
- [ ] Identify misleading documentation
- [ ] Note schema drift

**Commands:**
```bash
# Check plan.mf status markers
grep -E "✅|⏸️|🚧|❌" plan.mf

# Find TODOs/FIXMEs
grep -r "TODO\|FIXME\|XXX\|HACK" scripts/ app/ --include="*.py"

# Check for dead imports
poetry run python -c "
import ast
import sys
# ... import analysis script
"
```

---

## Comparison with Previous Audit

### Metrics to Compare

| Metric | Previous | Current | Delta |
|--------|----------|---------|-------|
| Record count | | | |
| Test pass rate | | | |
| P0 findings | | | |
| P1 findings | | | |
| Deprecation warnings | | | |

### Commands

```bash
# Test comparison
diff -u audits/YYYY-MM-DD-previous/test_results.txt audit_test_results.txt | head -50

# Finding comparison
diff audits/YYYY-MM-DD-previous/FINDINGS.yaml audits/$(date +%Y-%m-%d)-*/FINDINGS.yaml
```

---

## Output Artifacts

After completing audit, ensure these files exist:

1. `AUDIT_REPORT.md` - Main findings document
2. `FINDINGS.yaml` - Machine-readable findings
3. `ACTION_PLAN.md` - Prioritized remediation
4. `NEXT_AUDIT_CHECKLIST.md` - This file (update if needed)

---

## Quick Health Check (5-minute version)

```bash
# 1. Tests passing?
poetry run pytest tests/ -q --tb=no 2>&1 | tail -5

# 2. Database accessible?
poetry run python -c "
import sqlite3
conn = sqlite3.connect('data/index/bibliographic.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM records')
print('DB OK, records:', c.fetchone()[0])
"

# 3. Recent commits?
git log --oneline -5

# 4. Any deprecation warnings?
poetry run pytest tests/ 2>&1 | grep -c "deprecated"
```
