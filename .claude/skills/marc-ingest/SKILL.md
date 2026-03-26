---
name: marc-ingest
description: Rare Books Bot — full MARC XML ingestion pipeline. Rebuild bibliographic.db through 7 phases (parse, normalize, QA audit, authorities, Wikidata, Wikipedia, network tables). Use when the user says /marc-ingest, "rebuild the database", "re-ingest", "run the pipeline", or after a new MARC XML export.
user_invocable: true
---

# Full Ingestion Pipeline

Rebuild `bibliographic.db` from MARC XML source through 7 phases:
parsing, normalization, QA audit, authorities, Wikidata/Wikipedia enrichment, and network tables.

## Arguments

- `--yolo` — Non-interactive mode. Auto-approve all QA fixes and enrichment. No breakpoints.
- `--skip-enrichment` — Skip Wikidata/Wikipedia enrichment (fast core-only rebuild, ~2 min).
- `--xml <path>` — Override MARC XML path (default: `data/marc_source/rare_book_bibs.xml`)

## Execution

Parse the arguments from the user's command, then invoke the babysitter to orchestrate the pipeline.

### Step 1: Prepare inputs

Read the default inputs file and override with any arguments:

```
Default inputs: .a5c/processes/full-ingestion-pipeline-inputs.json
```

If `--xml <path>` is provided, update the `marcXml` field.
If `--skip-enrichment` is provided, set `skipEnrichment: true`.

### Step 2: Check prerequisites

Before running, verify:
1. The MARC XML file exists at the specified path
2. `poetry install` has been run (check `.venv/` exists)
3. The normalization alias maps exist:
   - `data/normalization/place_aliases/place_alias_map.json`
   - `data/normalization/publisher_aliases/publisher_alias_map.json`

### Step 3: Invoke babysitter

If `--yolo` flag is present:
```
/babysitter:yolo Execute .a5c/processes/full-ingestion-pipeline.js with inputs from .a5c/processes/full-ingestion-pipeline-inputs.json
```

Otherwise (interactive mode with QA review breakpoints):
```
/babysitter:call Execute .a5c/processes/full-ingestion-pipeline.js with inputs from .a5c/processes/full-ingestion-pipeline-inputs.json
```

### Step 4: Post-run summary

After the pipeline completes, show the final verification report from Phase 7.

## Process Details

See `.a5c/processes/full-ingestion-pipeline.process.md` for full documentation.
See `.a5c/processes/full-ingestion-pipeline.diagram.md` for flow diagram.

## 7 Phases

1. **Backup + Core Rebuild** (~2 min) — M1 parse, M2 normalize, M3 index
2. **QA Audit & Corrections** (~5-15 min) — scan gaps, categorize, propose fixes, apply
3. **Authority Systems** (~1 min) — agent/publisher authorities and aliases
4. **Wikidata Enrichment** (~10-60 min) — authority URI or name-based lookup
5. **Wikipedia Enrichment** (~1-4 hours) — 3 passes: links, summaries, LLM extraction
6. **Network Tables** (~1 min) — materialize edges and agents for Network Map
7. **Final Verification** — comprehensive coverage report

## Safety

- Auto-backup before overwriting existing DB
- `seed_test_db.py` refuses production DB path
- MARC XML is tracked in git (never lose source data)
- QA fixes are proposed and reviewed before applying (in interactive mode)
