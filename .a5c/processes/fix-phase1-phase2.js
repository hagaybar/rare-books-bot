/**
 * @process fix-phase1-phase2
 * @description Fix 13 failing tests (Phase 1) and strengthen contract enforcement (Phase 2)
 *   from the 2026-03-22 project audit.
 *
 * Phase 1 fixes:
 *   - 11 metadata API test fixtures (missing record_id column)
 *   - detect_script() logic bug in clustering.py
 *   - FTS5 subject JOIN tracking bug in db_adapter.py
 *   - Auto-fix lint errors (ruff --fix)
 *
 * Phase 2 fixes:
 *   - Evidence extraction fail-closed (execute.py)
 *   - CandidateSet validators (candidate_set.py)
 *   - M3 schema runtime validation (m3_contract.py)
 *
 * @inputs {
 *   projectRoot: string,
 *   auditDir: string
 * }
 * @outputs {
 *   success: boolean,
 *   phase1: { testsFailed: number, lintErrors: number },
 *   phase2: { contractsAdded: number },
 *   filesModified: array
 * }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    auditDir = 'audits/2026-03-22-status-review',
  } = inputs;

  const artifacts = [];

  ctx.log('info', 'Starting Phase 1 + Phase 2 fix process');

  // ============================================================================
  // PHASE 1A: FIX FAILING TESTS (3 independent bug fixes)
  // ============================================================================

  ctx.log('info', 'Phase 1A: Fix 3 independent bugs causing 13 test failures');

  const [metadataFix, scriptFix, ftsFix] = await ctx.parallel.all([
    () => ctx.task(fixMetadataApiTestsTask, { projectRoot }),
    () => ctx.task(fixDetectScriptTask, { projectRoot }),
    () => ctx.task(fixFtsJoinTask, { projectRoot }),
  ]);

  artifacts.push('tests/app/test_metadata_api.py', 'scripts/metadata/clustering.py', 'scripts/query/db_adapter.py');

  // ============================================================================
  // PHASE 1A VERIFICATION: Run affected tests
  // ============================================================================

  ctx.log('info', 'Phase 1A verify: Run pytest to confirm fixes');

  const phase1aVerify = await ctx.task(runTestsTask, {
    projectRoot,
    scope: 'phase1a',
    command: 'cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/app/test_metadata_api.py tests/scripts/metadata/test_clustering.py tests/scripts/query/test_db_adapter.py -v --tb=short 2>&1 | tail -30',
  });

  // ============================================================================
  // PHASE 1B: AUTO-FIX LINT ERRORS
  // ============================================================================

  ctx.log('info', 'Phase 1B: Auto-fix ruff lint errors');

  const lintFix = await ctx.task(fixLintTask, { projectRoot });

  // ============================================================================
  // PHASE 1 FULL VERIFICATION: Run entire test suite + lint
  // ============================================================================

  ctx.log('info', 'Phase 1 full verify: pytest + ruff');

  const phase1Verify = await ctx.task(fullVerifyTask, {
    projectRoot,
    scope: 'phase1-full',
  });

  // ============================================================================
  // PHASE 2A: STRENGTHEN CONTRACTS (3 independent improvements)
  // ============================================================================

  ctx.log('info', 'Phase 2A: Strengthen contract enforcement');

  const [evidenceFix, validatorFix, schemaCheckFix] = await ctx.parallel.all([
    () => ctx.task(fixEvidenceExtractionTask, { projectRoot }),
    () => ctx.task(addCandidateSetValidatorsTask, { projectRoot }),
    () => ctx.task(addSchemaRuntimeValidationTask, { projectRoot }),
  ]);

  artifacts.push('scripts/query/execute.py', 'scripts/schemas/candidate_set.py', 'scripts/marc/m3_contract.py');

  // ============================================================================
  // PHASE 2 VERIFICATION: Full test suite
  // ============================================================================

  ctx.log('info', 'Phase 2 verify: Run full test suite after contract changes');

  const phase2Verify = await ctx.task(fullVerifyTask, {
    projectRoot,
    scope: 'phase2-full',
  });

  // ============================================================================
  // FINAL REVIEW BREAKPOINT
  // ============================================================================

  await ctx.breakpoint({
    question: 'Phase 1 and Phase 2 fixes complete. Review changes and approve?',
    title: 'Final Review',
    context: {
      runId: ctx.runId,
    },
  });

  return {
    success: true,
    phase1: {
      metadataFix: metadataFix,
      scriptFix: scriptFix,
      ftsFix: ftsFix,
      lintFix: lintFix,
    },
    phase2: {
      evidenceFix: evidenceFix,
      validatorFix: validatorFix,
      schemaCheckFix: schemaCheckFix,
    },
    verification: {
      phase1a: phase1aVerify,
      phase1Full: phase1Verify,
      phase2Full: phase2Verify,
    },
    artifacts,
  };
}

// ============================================================================
// PHASE 1 TASK DEFINITIONS
// ============================================================================

export const fixMetadataApiTestsTask = defineTask('fix-metadata-api-tests', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix 11 metadata API test failures',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer fixing test fixtures',
      task: `Fix the TestGetIssues test class in tests/app/test_metadata_api.py. The test fixture creates an imprints table WITHOUT a record_id column, but the implementation in app/api/metadata.py (around line 259) JOINs on t.record_id. Fix the test fixture to include the record_id column and ensure all 11 TestGetIssues tests pass.

Steps:
1. Read tests/app/test_metadata_api.py, focusing on the issues_db fixture (around line 204-238)
2. Read app/api/metadata.py around line 259 to understand the expected schema
3. Add record_id column to the imprints table creation in the fixture
4. Add record_id values to all INSERT statements in the fixture
5. Ensure the records table is created with matching IDs
6. Run: poetry run pytest tests/app/test_metadata_api.py::TestGetIssues -v --tb=short
7. Fix any remaining issues until all 11 tests pass

IMPORTANT: Only modify the test fixture, not the implementation code. The implementation is correct; the tests are wrong.`,
      context: {
        projectRoot: args.projectRoot,
        file: 'tests/app/test_metadata_api.py',
        implementation: 'app/api/metadata.py',
      },
      instructions: [
        'Read both files before making changes',
        'Only modify the test fixture, not implementation',
        'Run the specific tests to verify the fix',
        'Return summary of changes made',
      ],
      outputFormat: 'JSON with filesModified (array), testsFixed (number), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase1', 'test-fix'],
}));

export const fixDetectScriptTask = defineTask('fix-detect-script', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix detect_script() logic bug',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer fixing a logic bug',
      task: `Fix the detect_script() function in scripts/metadata/clustering.py. The tie-breaking logic at lines 102-103 incorrectly prefers Hebrew even when Latin characters dominate.

The bug: The condition "if hebrew_count > 0 and hebrew_count >= arabic_count" returns "hebrew" even when latin_count >> hebrew_count (e.g., "Amsterdam א" has 9 Latin, 1 Hebrew but returns "hebrew").

The fix: The tie-breaking block (lines 99-106) should only prefer non-Latin scripts when they actually dominate the text. If Latin characters are the majority, return "latin".

Steps:
1. Read scripts/metadata/clustering.py, focus on detect_script() function
2. Fix the tie-breaking logic so the dominant script wins
3. Run: poetry run pytest tests/scripts/metadata/test_clustering.py -v --tb=short
4. Verify test_mixed_latin_majority passes

IMPORTANT: Keep the function's intent of preferring non-Latin scripts in ambiguous cases (true ties), but not when Latin clearly dominates.`,
      context: {
        projectRoot: args.projectRoot,
        file: 'scripts/metadata/clustering.py',
        test: 'tests/scripts/metadata/test_clustering.py',
      },
      instructions: [
        'Read the file and understand the full function logic',
        'Fix the tie-breaking condition',
        'Run the test to verify',
        'Return summary of the change',
      ],
      outputFormat: 'JSON with filesModified (array), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase1', 'bug-fix'],
}));

export const fixFtsJoinTask = defineTask('fix-fts-join', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Fix FTS5 subject JOIN tracking',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer fixing a SQL query builder bug',
      task: `Fix the build_where_clause() function in scripts/query/db_adapter.py. For SUBJECT CONTAINS filters (around line 231), the code incorrectly adds M3Tables.SUBJECTS to needed_joins. The EXISTS subquery is self-contained and handles the join internally, so the outer query should NOT join the subjects table.

Steps:
1. Read scripts/query/db_adapter.py, focus on the SUBJECT CONTAINS handling (around lines 229-249)
2. Remove the line that adds subjects to needed_joins for CONTAINS operations
3. Check if the same issue exists for TITLE CONTAINS (around lines 210-221)
4. Run: poetry run pytest tests/scripts/query/test_db_adapter.py::TestBuildWhereClause::test_subject_contains -v --tb=short
5. Also run the full db_adapter test file to ensure no regressions

IMPORTANT: Only remove the unnecessary JOIN tracking. Do not modify the EXISTS subquery logic itself.`,
      context: {
        projectRoot: args.projectRoot,
        file: 'scripts/query/db_adapter.py',
        test: 'tests/scripts/query/test_db_adapter.py',
      },
      instructions: [
        'Read the implementation and test files',
        'Remove only the unnecessary needed_joins.add() calls for FTS5 CONTAINS',
        'Run tests to verify fix and check for regressions',
        'Return summary of changes',
      ],
      outputFormat: 'JSON with filesModified (array), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase1', 'bug-fix'],
}));

export const runTestsTask = defineTask('run-tests', (args, taskCtx) => ({
  kind: 'shell',
  title: `Run tests: ${args.scope}`,
  shell: {
    command: args.command,
  },
  labels: ['verification', args.scope],
}));

export const fixLintTask = defineTask('fix-lint', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Auto-fix ruff lint errors',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer cleaning up lint errors',
      task: `Fix lint errors in the project using ruff.

Steps:
1. Run: cd /home/hagaybar/projects/rare-books-bot && poetry run ruff check --fix . 2>&1 | tail -10
2. Check remaining errors: poetry run ruff check . 2>&1 | tail -10
3. For remaining errors that can't be auto-fixed, fix the most impactful ones manually:
   - Unused imports (F401): remove them
   - Unused variables (F841): remove or prefix with underscore
   - Only fix errors in files under scripts/ and app/ (not tests/)
4. Run ruff check again to report final count
5. Run: poetry run pytest --tb=short -q 2>&1 | tail -5 to ensure no regressions

IMPORTANT: Do NOT fix errors in test files unless they cause test failures. Focus on production code.`,
      context: {
        projectRoot: args.projectRoot,
      },
      instructions: [
        'Use ruff --fix first for auto-fixable errors',
        'Manually fix remaining F401 and F841 in production code',
        'Verify tests still pass after changes',
        'Return summary with before/after error counts',
      ],
      outputFormat: 'JSON with errorsBeore (number), errorsAfter (number), filesModified (array), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase1', 'lint'],
}));

export const fullVerifyTask = defineTask('full-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Full verification: ${args.scope}`,
  shell: {
    command: `cd /home/hagaybar/projects/rare-books-bot && poetry run pytest --tb=short -q 2>&1 | tail -15`,
  },
  labels: ['verification', args.scope],
}));

// ============================================================================
// PHASE 2 TASK DEFINITIONS
// ============================================================================

export const fixEvidenceExtractionTask = defineTask('fix-evidence-extraction', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Make evidence extraction fail-closed',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer strengthening contract enforcement',
      task: `Fix the evidence extraction error handling in scripts/query/execute.py. Currently at around lines 560-562, extraction failures are silently swallowed with print(). This violates the Answer Contract.

Changes needed:
1. Read scripts/query/execute.py, find the evidence extraction try/except (around line 560)
2. Replace print() with proper logging using Python's logging module
3. Add an "extraction_failed" flag to the Evidence object when extraction fails
4. Ensure the candidate still includes partial evidence (don't raise and abort)
5. Read scripts/schemas/candidate_set.py to understand the Evidence model
6. Add an optional extraction_error field to the Evidence model if needed
7. Write a test in a new or existing test file that verifies:
   - When evidence extraction fails for one filter, the candidate is still returned
   - The failure is logged (not silently swallowed)
   - The evidence list contains an entry marking the failure
8. Run: poetry run pytest tests/scripts/query/ -v --tb=short to verify

IMPORTANT: Do NOT make evidence extraction raise and abort the query. The goal is to make failures visible, not to break queries. Use a fail-visible pattern: log + mark, not fail-closed.`,
      context: {
        projectRoot: args.projectRoot,
        files: ['scripts/query/execute.py', 'scripts/schemas/candidate_set.py'],
      },
      instructions: [
        'Read both files before making changes',
        'Replace print() with logging.warning()',
        'Add extraction_error field to Evidence model',
        'Write test for the failure path',
        'Run tests to verify no regressions',
      ],
      outputFormat: 'JSON with filesModified (array), testsAdded (number), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase2', 'contract'],
}));

export const addCandidateSetValidatorsTask = defineTask('add-candidateset-validators', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Add CandidateSet validators',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer adding Pydantic validators',
      task: `Add validation to the CandidateSet and Candidate models in scripts/schemas/candidate_set.py.

Changes needed:
1. Read scripts/schemas/candidate_set.py to understand current model
2. Add a @model_validator to Candidate that warns (via logging) if evidence list is empty
   - Do NOT raise an error for empty evidence (some edge cases may legitimately have none)
   - Log a warning with the record_id so it's visible
3. Add a @field_validator to CandidateSet.candidates that warns if any candidate has zero evidence
4. Add validation that confidence scores in Evidence are within [0.0, 1.0] when present
5. Write tests in tests/scripts/schemas/ or tests/scripts/query/test_candidate_set.py:
   - Test that a Candidate with empty evidence triggers a warning (use caplog)
   - Test that confidence validation works
   - Test that valid candidates pass without warnings
6. Run: poetry run pytest tests/scripts/query/test_candidate_set.py -v --tb=short (or the appropriate test file)

IMPORTANT: Validators should WARN, not RAISE. The goal is observability, not rejection. This is a data pipeline where partial results are better than no results.`,
      context: {
        projectRoot: args.projectRoot,
        file: 'scripts/schemas/candidate_set.py',
      },
      instructions: [
        'Read current model structure',
        'Add warning-level validators (not error-raising)',
        'Write tests using caplog to verify warnings',
        'Run tests to verify',
      ],
      outputFormat: 'JSON with filesModified (array), validatorsAdded (number), testsAdded (number), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase2', 'contract'],
}));

export const addSchemaRuntimeValidationTask = defineTask('add-schema-runtime-validation', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Add M3 schema runtime validation',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer adding database schema validation',
      task: `Add runtime schema validation to scripts/marc/m3_contract.py that verifies the database matches expected table/column structure.

Changes needed:
1. Read scripts/marc/m3_contract.py to understand current constants
2. Add a validate_schema(db_path: Path) function that:
   - Connects to the SQLite database
   - For each table in M3Tables, checks it exists using sqlite_master
   - For each table, checks expected columns exist using PRAGMA table_info
   - Returns a list of validation errors (empty = valid)
   - Logs warnings for any mismatches
3. Read scripts/query/db_adapter.py to see where the database is opened
4. Add a call to validate_schema() in db_adapter at connection time (first query or init)
   - Cache the result so it only runs once per session
   - Log warnings but do NOT raise errors (fail-visible, not fail-closed)
5. Write tests:
   - Test validate_schema() with a valid in-memory DB that has all expected tables
   - Test validate_schema() with a DB missing a table
   - Test validate_schema() with a DB missing a column
6. Run: poetry run pytest tests/scripts/query/test_db_adapter.py tests/scripts/marc/test_m3_index.py -v --tb=short

IMPORTANT: The validation should WARN, not block queries. A missing column in the DB is important to know about but should not prevent the system from trying to serve queries.`,
      context: {
        projectRoot: args.projectRoot,
        files: ['scripts/marc/m3_contract.py', 'scripts/query/db_adapter.py'],
      },
      instructions: [
        'Read current contract and adapter code',
        'Add validate_schema() function',
        'Integrate into db_adapter with caching',
        'Write comprehensive tests',
        'Run tests to verify',
      ],
      outputFormat: 'JSON with filesModified (array), testsAdded (number), summary (string)',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['phase2', 'contract'],
}));
