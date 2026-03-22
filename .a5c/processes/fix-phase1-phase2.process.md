# Process: Fix Phase 1 + Phase 2

Fixes all issues identified in the 2026-03-22 audit action plan.

## Phase 1A: Fix 3 Bug Groups (Parallel)

Three independent bug fixes run in parallel:

1. **Metadata API tests** - Fix test fixture missing `record_id` column (11 tests)
2. **Script detection** - Fix `detect_script()` tie-breaking logic (1 test)
3. **FTS5 JOIN** - Remove unnecessary subjects JOIN in db_adapter (1 test)

Verification gate: run affected tests, all 13 must pass.

## Phase 1B: Lint Cleanup

Auto-fix lint errors with `ruff check --fix`, then manually fix remaining F401/F841 in production code.

Verification gate: full test suite + lint check.

## Phase 2A: Strengthen Contracts (Parallel)

Three independent contract improvements run in parallel:

1. **Evidence extraction** - Replace silent `print()` with logging + error flag (fail-visible)
2. **CandidateSet validators** - Add warning-level Pydantic validators for empty evidence
3. **M3 schema validation** - Add runtime DB schema check with caching

Verification gate: full test suite pass.

## Final Review

Single breakpoint for human approval before considering the work done.

## Key Design Decisions

- **Warn, don't raise**: All Phase 2 changes use warning-level logging, not exceptions. Partial results are better than no results in a data pipeline.
- **Parallel where possible**: Independent fixes run concurrently to save time.
- **Test after every phase**: Verification gates catch regressions early.
- **Minimal breakpoints**: User profile has `breakpointTolerance: minimal`, so only one breakpoint at final review.
