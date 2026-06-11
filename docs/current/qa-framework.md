# QA Framework
> Last verified: 2026-06-10
> Source of truth for: Quality assurance infrastructure -- query debugger, diagnostics API, candidate labeling, gold set management, regression testing, and external-citation verification

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

### Benchmark-Driven Evaluation Loop

> Added 2026-06-10. Guards against case-by-case patching: every interpreter/
> recall change must hold or improve the whole benchmark, not just the example
> that motivated it.

- **Benchmark**: `data/eval/queries.json` — q01-q31 synthetic + q32-q58 mined
  verbatim from the production audit log (real librarian queries; provenance in
  each entry's `notes`).
- **Run** (interpreter stage, ~58 LLM calls + 58 judge calls):
  `PYTHONPATH=. poetry run python scripts/eval/run_eval.py --models gpt-4.1-mini --stages interpreter --queries data/eval/queries.json --output-dir data/eval/runs/<date-label>`
- **Empirical recall**: every eval entry now executes its plan deterministically
  (no LLM) and records `recall.total_records` / `zero_result` /
  `relaxations_used` — a 5/5-judged plan that retrieves nothing is visible.
- **Compare two runs**:
  `PYTHONPATH=. poetry run python scripts/eval/compare_runs.py <before>/results.json <after>/results.json --out comparison.md`
  Flags per-query regressions (Δ ≤ -1.0) and zero-result changes.
- **Judge**: caps plans at 3/5 when they invent hard constraints the user never
  stated (fabricated city/country lists).
- **Known limitation**: follow-up-intent queries (q15, q16) lack session
  context in single-turn eval and report zero — harness artifact, not a bug.
- 2026-06-10 state: judge avg 4.0/5; 16 retrieval-intent queries return zero
  records (see `data/eval/runs/2026-06-10-postfix/comparison.md`) — the
  primary target for the next quality iteration.

## FTS Parity Gate

> Added 2026-06-11 (issue #9). The FTS triggers are now legal (fix_20 rebuilt
> both tables: titles_fts external-content with 'delete'-command triggers;
> subjects_fts contentless_delete=1), so UPDATE/DELETE on titles/subjects work
> without dropping triggers. Because contentless FTS cannot be content-audited,
> sync is guarded by a deterministic gate:

```bash
poetry run python scripts/qa/fts_parity_check.py [--db PATH] [--sample N]
```

Checks row-count parity (subjects↔subjects_fts, titles↔titles_fts) plus a
stratified round-trip sample (incl. Hebrew value_he rows). **Run after every
QA fix script and before every `deploy.sh --update-db`.** Exit 1 = desync.
Fix scripts must NEVER drop FTS triggers anymore — if a bulk rewrite needs
speed, rebuild via `scripts/qa/fixes/fix_20_rebuild_fts.py --apply` (takes a
backup, verifies a search battery byte-identically, restores on mismatch).
The schema contract is enforced by `tests/integration/test_schema_contract.py`.

## External-Citation Verification (`scripts/qa/verify_external_citations.py`)

**Purpose**: external tools (ChatGPT etc.) may cite works "from our collection" with **fabricated MMS IDs** -- the title is real, the ID is invented. This harness cross-checks each claimed (title, mms_id) pair against `bibliographic.db` and flags fabrications deterministically (no LLM).

**Usage**:

```bash
poetry run python scripts/qa/verify_external_citations.py \
  --claims data/qa/external_claims/2026-06-10-chatgpt-cartography.json \
  --db data/index/bibliographic.db \
  [--out report.json]
```

**Claims file format** -- a JSON array of claimed pairs:

```json
[
  {"title": "Hadriani Relandi Palaestina ex monumentis veteribus illustrata", "mms_id": "9933433384704146"}
]
```

**The four statuses** (per claim):

| Status | Meaning |
|--------|---------|
| `verified` | The mms_id exists AND one of its titles matches the claimed title |
| `id_fabricated_title_real` | The title exists in the collection but under different mms_id(s); the claimed id does not match it (fabricated or wrong) -- the report lists the real id(s) |
| `id_real_title_mismatch` | The mms_id exists but none of its titles match the claimed title |
| `not_found` | Neither the id nor the title is in the collection |

Title matching is a case-insensitive substring probe on the first 40 whitespace-collapsed characters of the claimed title (LIKE-escaped), against the `titles` table. The report (stdout, and JSON via `--out`) includes per-claim results plus a status-count summary.

**First example** -- the 2026-06-10 ChatGPT cartography report (issue #2), stored at `data/qa/external_claims/2026-06-10-chatgpt-cartography.json` with its report alongside (`.report.json`). Summary: `total=13, verified=7, id_fabricated_title_real=2, not_found=3, id_real_title_mismatch=1`. The two fabricated-ID claims (Reland's *Palaestina* and the *Survey of Western Palestine*) are real works in the collection under different MMS IDs -- exactly the failure mode this harness exists to catch.

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
| `scripts/qa/verify_external_citations.py` | External-citation verification harness (claimed title/mms_id pairs vs DB) |
| `data/qa/external_claims/` | Claims files + verification reports from external tools |
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
