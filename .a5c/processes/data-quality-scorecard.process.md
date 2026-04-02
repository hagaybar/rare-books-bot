# Data Quality Scorecard & Remediation Process

## Overview
Comprehensive data quality assessment and remediation for bibliographic.db (2,796 rare book records). Implements the approved spec at `docs/superpowers/specs/2026-04-02-data-quality-scorecard-design.md`.

## Phases

### Phase 1: Build Automated Checks Script
Creates `scripts/qa/data_quality_checks.py` — a reusable Python script implementing all Tier 1 and Tier 2 checks from the spec. Outputs JSON quality report.

### Phase 2: Run Baseline Checks
Executes the checks script to establish baseline quality scores before any fixes.

### Phase 3: Build Quick-Win Fix Scripts (Fixes 1-7)
Seven scripts in `scripts/qa/fixes/`:
- Role trailing periods, Hebrew role terms, missing MARC relators
- Subject scheme normalization
- Calendar confusion dates, place-country mismatches, country-as-place

### Phase 4: Approval Gate — Quick Wins
User reviews and approves quick-win fixes before DB modification.

### Phase 5: Apply Quick-Win Fixes
Archives originals, applies fixes, appends to fix log.

### Phase 6: Build Medium Fix Scripts (Fixes 8-11)
Multi-script agent merging, bare "rené" investigation, country_name population, publisher research priorities.

### Phase 7: Approval Gate — Medium Fixes
User reviews and approves.

### Phase 8: Apply Medium Fixes

### Phase 9: Build Larger Fix Scripts (Fixes 12-16)
Missing publisher authorities, unmatched agent bridging, scope boundary, Wikidata role inference expansion, subjectless record investigation.

### Phase 10: Approval Gate — Larger Fixes
User reviews and approves.

### Phase 11: Apply Larger Fixes

### Phase 12: Sampling & External Verification
30 stratified records × 5 fields = 150 verification points against NLI Primo.

### Phase 13: Final Quality Report
Re-runs automated checks post-fixes, combines with sampling results, produces before/after comparison.

### Phase 14: Process Documentation
Creates `docs/current/data-quality.md` and updates CLAUDE.md Topic Registry.

## Breakpoints
- After quick-win scripts built (Phase 4)
- After medium scripts built (Phase 7)
- After larger scripts built (Phase 10)

All breakpoints require user approval before DB modifications. Original data archived before every change.

## Output Artifacts
- `data/qa/data-quality-report.json` — Quality scorecard
- `data/qa/sampling-verification.csv` — External verification results
- `data/qa/fix-log.jsonl` — All fixes applied
- `data/archive/data-quality-2026-04-02/` — Archived original values
- `scripts/qa/data_quality_checks.py` — Reusable checks script
- `scripts/qa/fixes/` — All fix scripts
- `docs/current/data-quality.md` — Process documentation
