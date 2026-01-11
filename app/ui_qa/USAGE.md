# M4 QA Tool - Quick Usage Guide

## Installation

The QA tool is already installed as part of the rare-books-bot project. If you just cloned the repo:

```bash
poetry install  # Install dependencies including Streamlit
```

## Launch the UI

From the project root directory:

```bash
poetry run streamlit run app/ui_qa/main.py
```

The app will open at `http://localhost:8501`

## Basic Workflow

### 1. Run a Query (Page 1)

```
Query: "books between 1500 and 1599"
Limit: 50
Database: data/index/bibliographic.db

Click: "Run Query"
```

### 2. Label Results (Page 1)

- Click any row in the results table
- Sidebar opens with candidate details
- Select label: **TP** (correct), **FP** (incorrect), **FN** (missing), **UNK** (unknown)
- For FP/FN: Add issue tags like `PARSER_WRONG_FILTER` or `NORM_PLACE_BAD`
- Add notes (optional)
- Click "Save Label"

**Bulk Actions:**
- "Mark All as TP" - Label all results as True Positive
- "Mark All as FP" - Label all results as False Positive
- "Clear All Labels" - Reset all to Unknown

### 3. Find Missing Records (Page 2)

- Select a query from the dropdown
- Enter search criteria:
  - Year range (e.g., 1500-1600)
  - Place contains (e.g., "oxford")
  - Publisher contains (e.g., "university press")
- Click "Search Database"
- Mark any missing records as FN

### 4. Review Analytics (Page 3)

- View overall stats (queries reviewed, TP/FP/FN counts)
- See top issue tags with bar chart
- Find "worst queries" (most FP+FN)
- Click any query to see details

### 5. Export Gold Set (Page 4)

```
Click: "Export Gold Set"
→ Saves to: data/qa/gold.json
```

### 6. Run Regression (Page 4 or CLI)

**From UI:**
```
Gold Set Path: data/qa/gold.json
Database Path: data/index/bibliographic.db

Click: "Run Regression"
```

**From CLI:**
```bash
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db \
  --verbose
```

## Label Definitions

| Label | Meaning | When to Use |
|-------|---------|-------------|
| **TP** | True Positive | Record correctly matched the query |
| **FP** | False Positive | Record incorrectly matched (shouldn't be in results) |
| **FN** | False Negative | Record should have matched but didn't |
| **UNK** | Unknown | Not yet labeled |

## Issue Tags

Use these tags to categorize problems:

- `PARSER_MISSED_FILTER` - Parser didn't extract a filter from the query
- `PARSER_WRONG_FILTER` - Parser extracted wrong value or field
- `NORM_PLACE_BAD` - Place normalization incorrect
- `NORM_PUBLISHER_BAD` - Publisher normalization incorrect
- `DATE_PARSE_BAD` - Date parsing error
- `SQL_LOGIC_BAD` - SQL query logic issue
- `EVIDENCE_INSUFFICIENT` - Evidence doesn't justify the match
- `OTHER` - Custom issue

## Example Session

```bash
# 1. Launch UI
poetry run streamlit run app/ui_qa/main.py

# 2. In browser:
# - Go to Page 1
# - Enter query: "books published by Oxford between 1500 and 1599"
# - Click "Run Query"
# - Label first 5 results as TP
# - Label 1 result as FP with tag "PARSER_WRONG_FILTER"

# 3. Go to Page 2:
# - Select the query
# - Search for year 1500-1599, publisher "oxford"
# - Mark 2 missing records as FN

# 4. Go to Page 4:
# - Click "Export Gold Set"
# - Downloads to data/qa/gold.json

# 5. Run regression from terminal:
poetry run python -m app.qa regress \
  --gold data/qa/gold.json \
  --db data/index/bibliographic.db \
  --verbose
```

## Tips

**Efficient Labeling:**
- Use bulk actions for obviously correct/incorrect results
- Focus detailed labeling on edge cases
- Add issue tags to help identify patterns

**Finding False Negatives:**
- Start with queries you understand well
- Use Page 2 search with slightly broader criteria than the original query
- Check records with similar dates/places/publishers

**Building Gold Sets:**
- Label at least 10-20 queries before exporting
- Include variety: simple queries, complex queries, edge cases
- Aim for at least 5 TP + 2 FP + 1 FN per query for good coverage

**Regression Testing:**
- Run regression after any parser/normalization changes
- Add to CI pipeline with: `poetry run python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db`
- Exit code 0 = all passed, 1 = failures

## Troubleshooting

**"No queries found"**
→ Run a query on Page 1 first

**Import errors**
→ Make sure you're running from project root
→ Use `poetry run` prefix

**Database not found**
→ Check that M3 indexing completed successfully
→ Verify path: `data/index/bibliographic.db` exists

**Streamlit port in use**
→ Use different port: `poetry run streamlit run app/ui_qa/main.py --server.port 8502`

**Labels not saving**
→ Check sidebar for error messages after clicking "Save Label"
→ Verify `data/qa/qa.db` is writable

## Next Steps

1. **Start Labeling** - Run queries and label 50-100 results
2. **Analyze Patterns** - Use Dashboard to identify common issues
3. **Fix Problems** - Improve parser/normalization based on issue tags
4. **Expand Coverage** - Add more query types to gold set
5. **Automate** - Add regression tests to CI pipeline
