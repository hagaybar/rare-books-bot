# M4 Query QA Tool

**Status:** Development tool for M4 quality assurance (maintained in-repo)

A Streamlit-based QA tool for testing the M4 query pipeline, labeling results, and creating regression test sets. This tool supports M4 development by providing systematic query labeling, issue tracking, and regression testing capabilities.

**For production query execution**, use the CLI: `python -m app.cli query "<query>"`

## Quick Start

### Launch the UI

```bash
poetry run streamlit run app/ui_qa/main.py
```

The app will open in your browser at `http://localhost:8501`

### Run Regression Tests (CLI)

```bash
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db
```

## Features

### Page 1: Run + Review

- Execute natural language queries against the M4 pipeline
- View QueryPlan (JSON), generated SQL, and results
- Label candidates as TP (True Positive), FP (False Positive), FN (False Negative), or UNK (Unknown)
- Add issue tags (PARSER_MISSED_FILTER, NORM_PLACE_BAD, etc.)
- Add notes for each label
- Bulk actions: Mark all as TP/FP, clear labels

### Page 2: Find Missing

- Search for False Negatives (records that should have matched but didn't)
- Simple database search by year range, place, publisher
- Shows whether records are already in results
- Mark records as FN with issue tags

### Page 3: Dashboard

- Aggregate statistics: queries reviewed, TP/FP/FN counts
- Top issue tags analysis with bar chart
- "Worst queries" sorted by FP+FN count
- Query drill-down: view plan, SQL, labels, notes

### Page 4: Gold Set & Regression

- Export labeled queries to `gold.json`
- Run regression tests from UI
- Validates expected_includes/expected_excludes
- Shows pass/fail status with detailed results
- CLI command for CI integration

## Workflow

1. **Run a query** (Page 1)
   - Enter query text: `"books by Oxford between 1500 and 1599"`
   - Click "Run Query"
   - View results

2. **Label results** (Page 1)
   - Click on a candidate row to open detail pane
   - Select label: TP/FP/FN/UNK
   - Add issue tags if FP or FN
   - Add notes (optional)
   - Click "Save Label"

3. **Find missing results** (Page 2)
   - Select the query
   - Search database by year/place/publisher
   - Mark any missing records as FN

4. **Analyze issues** (Page 3)
   - Review statistics
   - Identify common issue tags
   - Drill down into problem queries

5. **Export gold set** (Page 4)
   - Click "Export Gold Set"
   - Downloads to `data/qa/gold.json`

6. **Run regression** (Page 4 or CLI)
   - UI: Click "Run Regression"
   - CLI: `poetry run python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db`

## Database Schema

The QA tool uses `data/qa/qa.db` (SQLite) with 3 tables:

### qa_queries
Stores each query run with plan/SQL snapshots.

### qa_candidate_labels
Stores labels (TP/FP/FN/UNK) per (query_id, record_id).

### qa_query_gold
Optional metadata for gold set queries.

## Issue Tags

Predefined tags for categorizing problems:

- `PARSER_MISSED_FILTER` - Heuristic parser failed to extract a filter
- `PARSER_WRONG_FILTER` - Parser extracted wrong value/field
- `NORM_PLACE_BAD` - Place normalization incorrect
- `NORM_PUBLISHER_BAD` - Publisher normalization incorrect
- `DATE_PARSE_BAD` - Date parsing error
- `SQL_LOGIC_BAD` - SQL query logic issue
- `EVIDENCE_INSUFFICIENT` - Evidence doesn't justify match
- `OTHER` - Custom issue

## Gold Set Format

```json
{
  "version": "1.0",
  "exported_at": "2026-01-10T10:00:00Z",
  "queries": [
    {
      "query_text": "books by Oxford between 1500 and 1599",
      "plan_hash": "abc123...",
      "expected_includes": ["990001", "990004"],
      "expected_excludes": ["990003"],
      "min_expected": 2
    }
  ]
}
```

## CLI Options

```bash
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \       # Required: path to gold set
  --db data/index/bibliographic.db \ # Required: path to database
  --verbose \                      # Optional: show detailed output
  --log-file regress.json          # Optional: write results to file
```

Exit codes:
- `0`: All tests passed
- `1`: One or more tests failed

## CI Integration

Add to `.github/workflows/test.yml`:

```yaml
- name: Run M4 Regression Tests
  run: |
    poetry install
    poetry run python -m app.qa regress \
      --gold data/qa/gold.json \
      --db data/index/bibliographic.db \
      --log-file test-results/regress.json
```

## Troubleshooting

**"No queries found"**
- Run a query on Page 1 first

**"Database not found"**
- Ensure M3 indexing is complete
- Check path: `data/index/bibliographic.db`

**Streamlit port already in use**
- Stop other Streamlit instances
- Or use: `poetry run streamlit run app/ui_qa/main.py --server.port 8502`

**Labels not persisting**
- Check `data/qa/qa.db` exists and is writable
- Check no errors in sidebar after clicking "Save Label"

## Architecture

```
Streamlit UI (app/ui_qa/main.py)
    ↓
    ├─ scripts/query/compile.py::compile_query()
    ├─ scripts/query/execute.py::execute_plan()
    ├─ app/ui_qa/db.py (QA database operations)
    └─ data/qa/qa.db (SQLite)

CLI Regression Runner (app/qa.py)
    ↓
    ├─ Loads gold.json
    ├─ Runs queries via compile_query() + execute_plan()
    └─ Validates expected_includes/expected_excludes
```

## Files

```
app/ui_qa/
├── main.py                    # Streamlit entry point
├── config.py                  # Configuration (paths, issue tags)
├── db.py                      # QA database operations
├── README.md                  # This file
└── pages/
    ├── 1_run_review.py        # Run + Review page
    ├── 2_find_missing.py      # Find Missing page
    ├── 3_dashboard.py         # Issues Dashboard page
    └── 4_gold_set.py          # Gold Set + Regression page

app/qa.py                      # CLI regression runner

data/qa/
├── qa.db                      # QA database (generated)
└── gold.json                  # Gold set export (generated)
```

## Next Steps

1. **Run QA on existing queries** - Label 50-100 query results
2. **Analyze common issues** - Identify parser/normalization problems
3. **Improve M4 heuristics** - Fix parser patterns based on FP/FN
4. **Expand gold set** - Add more query types to regression
5. **CI Integration** - Add regression check to GitHub Actions
