# QA Framework
> Last verified: 2026-04-01
> Source of truth for: Quality assurance infrastructure -- query debugger, diagnostics API, candidate labeling, gold set management, and regression testing

## Overview

The QA framework provides systematic labeling, issue tracking, and regression testing capabilities for the M4 query pipeline. It is integrated into the unified React UI and diagnostics API.

**Status**: Fully integrated into the unified React frontend and FastAPI backend.

**Purpose**: Ensure query quality by enabling operators to label results (true positive, false positive, false negative), build gold sets, and run regression tests to prevent quality regressions.

---

## Components

### React Query Debugger (`/diagnostics/query`)

Interactive query testing and labeling via the unified React UI:

- **Session management** for organizing QA work
- **Visual result inspection** with evidence and confidence scores
- **Issue tagging** with predefined categories:
  - Parser errors
  - Normalization issues
  - Missing records
  - Incorrect evidence
  - Other

### Diagnostics API (`app/api/diagnostics.py`)

REST endpoints for query execution, run storage, labeling, gold set export, and regression testing.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/diagnostics/query-run` | Execute a query and store the run |
| GET | `/diagnostics/query-runs` | List stored query runs |
| POST | `/diagnostics/labels` | Submit candidate labels (TP/FP/FN/UNK) |
| GET | `/diagnostics/labels/{run_id}` | Get labels for a specific run |
| GET | `/diagnostics/gold-set/export` | Export gold set as JSON |
| POST | `/diagnostics/gold-set/regression` | Run regression test against gold set |
| GET | `/diagnostics/tables` | List database tables (for DB Explorer) |
| GET | `/diagnostics/tables/{table_name}/rows` | Browse table rows (for DB Explorer) |

### Database Explorer (`/diagnostics/db`)

Interactive table browser for inspecting `bibliographic.db` tables. Useful for:
- Finding missing records (false negatives) by browsing raw data
- Verifying normalization values in the database
- Inspecting imprint, agent, and subject data

### QA Database (`data/qa/qa.db`)

Separate SQLite database, isolated from the production `bibliographic.db`.

**Tables**:

| Table | Purpose |
|-------|---------|
| `qa_queries` | Stored query runs with query text, plan, SQL, results, timestamps |
| `qa_candidate_labels` | Candidate labels: TP (true positive), FP (false positive), FN (false negative), UNK (unknown) |
| `qa_query_gold` | Gold set metadata: expected includes and excludes per query |

**Database operations**: `scripts/qa/db.py`

### Regression Framework

- **Gold set**: `data/qa/gold.json` -- expected includes/excludes per query
- **CLI runner**: `python -m app.cli regression --gold data/qa/gold.json --db data/index/bibliographic.db`
- **Exit codes**: 0 = pass, 1 = fail (CI-friendly)

---

## Workflow

### 1. Run Query in Debugger

Open the React Query Debugger at `/diagnostics/query`. Enter a natural language query. Review the results including:
- Matched records (CandidateSet)
- Evidence for each match (MARC fields, confidence scores)
- SQL query used
- QueryPlan JSON

### 2. Label Candidates

For each candidate in the result set, assign a label:

| Label | Meaning |
|-------|---------|
| **TP** (True Positive) | Correctly included -- this record should match |
| **FP** (False Positive) | Incorrectly included -- this record should not match |
| **FN** (False Negative) | Missing -- this record should have matched but was not found |
| **UNK** (Unknown) | Uncertain -- needs further investigation |

Tag issues with predefined categories to track systemic problems.

### 3. Find Missing Records (FN)

Use the Database Explorer (`/diagnostics/db`) to browse `bibliographic.db` tables and identify records that should have matched but were missed. Add these as FN labels.

### 4. Export Gold Set

Once queries are fully labeled and validated, export the gold set:

```bash
# Via API
GET /diagnostics/gold-set/export

# Output: data/qa/gold.json
```

The gold set contains expected includes and excludes for each validated query.

### 5. Run Regression Tests

Run regression tests to prevent quality regressions:

```bash
poetry run python -m app.cli regression \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db
```

- **Exit code 0**: All assertions pass
- **Exit code 1**: Regression detected (missing expected records or unexpected records included)

This can be integrated into CI pipelines for automated quality gates.

---

## Key Files

| File | Purpose |
|------|---------|
| `app/api/diagnostics.py` | REST API for QA operations |
| `scripts/qa/db.py` | QA database operations (CRUD for runs, labels, gold set) |
| `data/qa/qa.db` | QA SQLite database |
| `data/qa/gold.json` | Exported gold set for regression testing |
| `frontend/src/pages/QueryDebugger.tsx` | React query debugger UI |
| `frontend/src/pages/DbExplorer.tsx` | React database explorer UI |

---

## Usage

### CLI

```bash
# Run regression tests
poetry run python -m app.cli regression \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db
```

### API

```bash
# Execute a query run
curl -X POST http://localhost:8000/diagnostics/query-run \
  -H "Content-Type: application/json" \
  -d '{"query": "books by Oxford"}'

# List query runs
curl http://localhost:8000/diagnostics/query-runs

# Submit labels
curl -X POST http://localhost:8000/diagnostics/labels \
  -H "Content-Type: application/json" \
  -d '{"run_id": "...", "labels": [{"mms_id": "990001234", "label": "TP"}]}'

# Export gold set
curl http://localhost:8000/diagnostics/gold-set/export

# Run regression via API
curl -X POST http://localhost:8000/diagnostics/gold-set/regression
```
