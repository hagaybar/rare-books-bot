# Data Quality Scorecard — Process Diagram

```
Phase 1: Build Checks Script
    |
    v
Phase 2: Run Baseline Checks ──> data/qa/data-quality-report.json (baseline)
    |
    v
Phase 3: Build Quick-Win Fix Scripts (7 scripts)
    |
    v
Phase 4: [BREAKPOINT] Approve Quick-Win Fixes
    |
    v
Phase 5: Apply Quick-Win Fixes ──> data/archive/ + fix-log.jsonl
    |
    v
Phase 6: Build Medium Fix Scripts (4 scripts)
    |
    v
Phase 7: [BREAKPOINT] Approve Medium Fixes
    |
    v
Phase 8: Apply Medium Fixes ──> data/archive/ + fix-log.jsonl
    |
    v
Phase 9: Build Larger Fix Scripts (5 scripts)
    |
    v
Phase 10: [BREAKPOINT] Approve Larger Fixes
    |
    v
Phase 11: Apply Larger Fixes ──> data/archive/ + fix-log.jsonl
    |
    v
Phase 12: Sampling & External Verification (30 records × 5 fields)
    |                                        ──> sampling-verification.csv
    v
Phase 13: Final Quality Report (before vs after)
    |                          ──> data-quality-report.json (final)
    v
Phase 14: Process Documentation
    |       ──> docs/current/data-quality.md
    |       ──> CLAUDE.md Topic Registry updated
    v
  DONE
```
