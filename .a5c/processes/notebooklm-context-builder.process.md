# NotebookLM Context Builder — Process Description

## Goal

Build a curated knowledge base in NotebookLM that provides deep, navigable understanding of the rare-books-bot repository. Not a file dump — a structured, thematic set of documents that help NotebookLM answer questions about the project's architecture, code, data model, current status, and development workflow.

## Inputs

| Input | Description |
|-------|-------------|
| `notebookUrl` | URL of the target NotebookLM notebook |
| `notebookName` | Display name for the notebook (default: "Rare Books Bot") |
| `repoRoot` | Absolute path to the repository root |
| `outputDir` | Where to write the generated markdown documents |

## Process Phases

### Phase 1: Deep Repository Analysis
**Agent task** — A senior architect agent reads all source code, documentation, schemas, models, git history, and audit reports. Produces a structured JSON analysis covering: modules, dependencies, data flows, API endpoints, test coverage, and project status. Excludes noise (raw data files, archives, dependencies).

### Phase 2: Generate 7 Context Documents
**Agent task** — A technical writer agent uses the analysis to produce 7 focused markdown documents:

| # | Document | Answers |
|---|----------|---------|
| 1 | Project Overview & Architecture | "What is this project?" |
| 2 | Code Map & Module Relationships | "Where is the code for X?" |
| 3 | Data Pipeline (M1-M3) | "How does data flow from XML to DB?" |
| 4 | Query & Chat System (M4-M6) | "How do queries work?" |
| 5 | Metadata Workbench (M7) | "How is metadata quality improved?" |
| 6 | Data Model & Schemas | "What fields does a record have?" |
| 7 | Project Status & Dev Guide | "What's the current state?" |

Each document is 2,000-5,000 words, uses rich markdown structure (headers, tables, code blocks, ASCII diagrams), and cross-references the others.

### Phase 3: Quality Review
**Agent task** — A reviewer agent scores each document on 4 dimensions (completeness, clarity, accuracy, signal-to-noise) out of 25 each. Documents scoring below 70/100 are fixed automatically. Verifies accuracy against actual source code.

### Phase 4: User Review (Breakpoint)
**Breakpoint** — Pauses execution so you can review all 7 documents before they're uploaded. Approve to continue or reject with feedback.

### Phase 5: Upload to NotebookLM
**Agent task** — Uses the notebooklm-connector's Chrome automation to:
1. Rename the notebook to "Rare Books Bot"
2. Upload each document as a "Copied text" source
3. Wait for processing between uploads
4. Verify all 7 sources are present

### Phase 6: Verification
**Agent task** — Queries the notebook with 5 test questions covering different aspects (pipeline, queries, normalization, agents, status). Scores each answer for accuracy, completeness, and specificity. Identifies any coverage gaps.

### Phase 7: Create Update Utility
**Agent task** — Creates `scripts/notebooklm/update_context.py`:
- **Collectors**: Functions that gather current data from the repo (AST parsing, git log, doc reading)
- **Renderers**: Functions that format collected data into the 7 markdown templates
- **CLI**: `--output`, `--only`, `--diff` flags for flexible usage

### Phase 8: Verify Update Utility
**Shell + Agent** — Runs the update script, then compares its output with the original documents. Verifies structural consistency (same headers, similar word counts, key sections present).

### Phase 9: Register Notebook
**Agent task** — Registers the notebook in the notebooklm-connector library under ID `rare-books-bot` for easy future querying.

## Outputs

| Output | Description |
|--------|-------------|
| `documentsGenerated` | Number of markdown documents created (expected: 7) |
| `documentsUploaded` | Number of sources added to NotebookLM |
| `qualityScore` | Average document quality score (0-100) |
| `verificationScore` | Average query answer score (0-60) |
| `updateScriptPath` | Path to the refresh utility |
| `notebookRegistered` | Whether notebook was registered in connector library |

## Noise Filtering Strategy

**Excluded** (noise):
- `data/marc_source/` — raw MARC XML files
- `data/canonical/`, `data/m2/` — thousands of JSONL records
- `data/index/` — binary SQLite database
- `archive/` — leftover template files
- `.venv/`, `node_modules/`, `__pycache__/`
- `poetry.lock`, `package-lock.json`
- Individual test fixtures and cache files

**Included** (signal):
- Architecture diagrams and data flows
- Key function signatures and Pydantic models
- Normalization rules and confidence tiers
- Module purposes and inter-dependencies
- API endpoint definitions
- 1-2 concrete data examples per concept
- Git history themes (not raw commits)
- Audit findings and current gaps

## Future Usage

After the process completes:

```bash
# Refresh context documents from current repo state
python scripts/notebooklm/update_context.py --output data/notebooklm/sources/

# Regenerate only status and code map
python scripts/notebooklm/update_context.py --only status,code_map

# See what changed since last generation
python scripts/notebooklm/update_context.py --diff

# Query the notebook (via notebooklm-connector)
# In Claude Code: "ask rare-books-bot notebook about the query pipeline"
```
