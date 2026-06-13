/**
 * @process seam-hardening-batch1
 * @description Starter batch from the 2026-06-12 seam audit: #56 op-matrix
 *   cells + contract test, #49 empty-string validation + sine-loco sentinel,
 *   #55 HIGH loud-failure fixes, #58 fix_30 (dry-run only), P0 invariant
 *   battery. TDD per task, fix-retry loops, full-suite gate, merge to dev,
 *   issue closures/comments.
 * @inputs { projectRoot: string, branch: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;
const AUDIT = 'audits/2026-06-12-seam-audit';

const COMMON = [
  'TDD is mandatory: write the failing test, run it to watch it fail, implement minimally, watch it pass, then ruff-check touched files and commit specific files (never git add -A; never push from inside a task).',
  'Run Python tests with `PYTHONPATH=. poetry run pytest` (plain pytest/python are not on PATH).',
  'No paid LLM API calls; mock anything external. Read DBs only via sqlite3 SELECT/PRAGMA; NEVER write to any database in this run.',
  'SECRETS: never read or echo .env files, shell rc files, or token values.',
  'Research before editing: read every file you change first; the audit files under audits/2026-06-12-seam-audit/ are the source of truth for findings (file:line citations inside).',
  'Match surrounding code style; comments only for constraints code cannot show.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'fix/seam-hardening-batch1',
  } = inputs;

  const setup = await ctx.task(shellTask, {
    name: 'setup-branch',
    command:
      `cd ${projectRoot} && ` +
      `(git rev-parse --verify ${branch} >/dev/null 2>&1 && git checkout ${branch} ` +
      `|| git checkout -b ${branch} dev) && git branch --show-current`,
  });
  if (setup.exitCode !== 0) {
    return { success: false, failedAt: 'setup-branch', detail: setup.output };
  }

  const tasks = [
    {
      id: 1,
      name: 'op-matrix-56',
      role: 'Senior Python developer hardening the query IR contract',
      taskText: 'Issue #56: resolve all six raising FilterField×FilterOp cells + parametrized matrix contract test',
      steps: [
        'Read issue #56 (gh issue view 56) and the Seam B section of ' + AUDIT + '/cross-layer-seams.md for the exact six raising cells and the two drift items.',
        'For each raising cell choose the minimal correct resolution, following the #44 precedent (scripts/chat/interpreter.py _convert_filter_dict and scripts/query/db_adapter.py): support in db_adapter where SQL semantics are natural (e.g. subject EQUALS as exact value match), coerce at conversion where a safe equivalent exists (e.g. year IN [a,b] -> per-year ranges or min-max RANGE if contiguous; document choice), otherwise reject loudly in Filter validation with a clear message (never let it reach SQL as a crash).',
        'New contract test file tests/scripts/query/test_field_op_matrix.py: parametrize all 12 FilterField × 4 FilterOp cells; each cell must be classified supported/coerced/rejected-with-ValidationError/never-emitted, and the test must EXECUTE each supported/coerced cell through build_where_clause against a tmp schema (reuse fixtures from tests/scripts/query/test_db_adapter.py) asserting no unhandled ValueError. The never-emitted cells must be asserted as rejected or documented in the test with the reason.',
        'Also fix the two Seam-B drift items from the audit (language param-suffix mismatch in the multi-value SQL rewrite; aggregate country->place alias) if they are small; if either is risky, leave a precise TODO referencing #57 instead.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/query/test_field_op_matrix.py tests/scripts/query/test_db_adapter.py tests/scripts/chat/test_interpreter.py -q',
    },
    {
      id: 2,
      name: 'empty-filter-sentinel-49',
      role: 'Senior Python developer closing a silent-zero planning gap',
      taskText: 'Issue #49: reject empty-string filter values; teach the interpreter the [sine loco] sentinel',
      steps: [
        'Read issue #49 (gh issue view 49). Two parts:',
        'Part A: scripts/schemas/query_plan.py Filter validation — EQUALS/CONTAINS with empty or whitespace-only string value must raise a validation error (test first in tests/scripts/query/test_query_plan.py following its existing style).',
        'Part B: scripts/chat/interpreter.py system prompt — add the sentinel rule: "no place of publication" / ח"מ queries compile to imprint_place EQUALS "[sine loco]" (the DB reifies absence as that sentinel; 41 records). Add a prompt-discipline test in tests/scripts/chat/test_interpreter.py asserting the prompt contains the sentinel mapping (match the existing TestPrompt* class style).',
        'Check _convert_filter_dict: if the LLM emits an empty-string value anyway, the conversion should drop the filter with a logger.warning rather than crash the whole plan (test this).',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/query/test_query_plan.py tests/scripts/chat/test_interpreter.py -q && rg -q "sine loco" scripts/chat/interpreter.py',
    },
    {
      id: 3,
      name: 'loud-failures-55',
      role: 'Senior Python developer converting silent failures to loud ones',
      taskText: 'Issue #55 HIGH cluster: five silent fallbacks become loud, honest failures',
      steps: [
        'Read issue #55 (gh issue view 55) and ' + AUDIT + '/fallback-inventory.md "Top HIGH risks" for exact file:line of the five HIGH items.',
        'Fix 1 — scripts/marc/parse.py whole-file parse failure: per the CLAUDE.md hard rule, log the error to data/runs/ (a timestamped error file) and RAISE (stop) instead of proceeding with zero records. Update any caller that relied on the silent path.',
        'Fix 2 — scripts/query/db_adapter.py alias-expansion: a transient DB error must NOT cache alias expansion as disabled for the process lifetime; log a warning and retry on next call (cache only positive detection).',
        'Fix 3 — scripts/chat/narrator.py meta-extraction failure: never fabricate confidence 0.85; use None plus an explicit reason field/log per the Data Model Rules.',
        'Fix 4 — scripts/metadata/feedback_loop.py correction apply: a DB exception must be raised or returned as a distinct error, never collapsed into the 0-rows-updated return.',
        'Fix 5 — scripts/chat/concept_bridge.py missing/malformed concept map: emit a clear logger.warning once (module-level guard) so disabled expansion is visible in logs.',
        'Tests: put cross-cutting loud-failure tests in tests/scripts/qa/test_loud_failures.py (new file, one test class per fix, TDD each); where a natural home exists (e.g. tests/scripts/marc/), additionally extend there if the file already covers the function.',
        'Do NOT touch MEDIUM/LOW items from #55 — they stay open.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/qa/test_loud_failures.py -q',
    },
    {
      id: 4,
      name: 'fix30-58',
      role: 'Data-repair engineer writing a dry-run-first fix script',
      taskText: 'Issue #58: fix_30 script repairing D1 + D3, reporting D2 + D4 — DRY-RUN ONLY in this run',
      steps: [
        'Read issue #58 (gh issue view 58) and ' + AUDIT + '/derived-invariants.md violation details (D1-D4).',
        'Write scripts/qa/fixes/fix_30_repair_seam_audit_violations.py following the fix_27/fix_29 conventions (curated plan, dry-run default, --apply with .pre-fix30.bak backup, post-apply verification):',
        'D1: the 26 authority-linked mononym agent_norms that lost their alias when fix_29 classified them as collisions against pre-deletion state — plan computes them dynamically (norms with authority whose alias row is missing AND whose absence traces to the collision-order bug), inserts them as primary aliases. Reuse the corrected ordering logic: evaluate collisions AFTER deletions.',
        'D3: delete the 2 same_place_period network edges referencing the merged-away node (the audit names them); derived-table cleanup, regenerable.',
        'D2 (Proops placeholder/variant shadows) and D4 (d\'Alembert wikidata disagreement): REPORT-ONLY sections in the dry-run output flagged "needs curation".',
        'Run ONLY the dry run (no --apply — the user approves after this batch) and capture its output into the script docstring is NOT needed; just verify it executes cleanly. NEVER write to the DB in this run.',
        'Unit-test the planning function against a tmp fixture DB (no live-DB writes) in tests/scripts/qa/test_fix_30.py: seed the fix_29 bug shape, assert the plan finds the missing mononym and the orphan edge.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/qa/test_fix_30.py -q && PYTHONPATH=. poetry run python scripts/qa/fixes/fix_30_repair_seam_audit_violations.py | grep -q "DRY RUN"',
    },
    {
      id: 5,
      name: 'invariant-battery',
      role: 'QA engineer encoding audit invariants as a permanent test battery',
      taskText: 'P0 enforcement: tests/integration/test_derived_invariants.py running the audit\'s SQL invariants against the live DB',
      steps: [
        'Read ' + AUDIT + '/derived-invariants.md: every invariant has a ready SQL SELECT returning a violation count.',
        'Create tests/integration/test_derived_invariants.py: parametrized test over (artifact, invariant description, SQL, issue ref) running each SELECT read-only against data/index/bibliographic.db and asserting count == 0. Skip the whole module cleanly (pytest.mark.skipif) when the DB file is absent (CI without data).',
        'The 4 currently-violating invariants (D1-D4 per #58) get pytest.mark.xfail(strict=False, reason="#58 — pending fix_30 approval") so the battery is green today and flips to strict enforcement when fix_30 lands (leave a TODO to strict-ify).',
        'Also include the FTS rowcount-parity and value_he coverage checks exactly as the audit wrote them.',
        'Keep it deterministic and fast (<5s): single connection, no LLM, no network.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/integration/test_derived_invariants.py -q',
    },
  ];

  const completed = [];
  for (const task of tasks) {
    const result = await runTaskWithVerification(ctx, task, { projectRoot, branch });
    completed.push(result);
    if (!result.verified) {
      return { success: false, failedAt: task.name, completed, detail: result.lastOutput };
    }
  }

  const gateVerify =
    'PYTHONPATH=. poetry run pytest -q -m "not integration" 2>&1 | tail -3 && ' +
    'PYTHONPATH=. poetry run pytest tests/integration/test_derived_invariants.py -q 2>&1 | tail -2 && ' +
    'poetry run ruff check scripts/ app/ tests/ 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command: `cd ${projectRoot} && ${gateVerify}`,
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate', role: 'Senior developer fixing a regression',
      taskText: 'Full-suite gate failed — diagnose and fix the regression', steps: [],
      verify: gateVerify,
    }, gate.output, { projectRoot, branch });
    if (!fixed.verified) {
      return { success: false, failedAt: 'full-suite-gate', completed, detail: fixed.lastOutput };
    }
  }

  const merge = await ctx.task(shellTask, {
    name: 'merge-to-dev',
    command:
      `cd ${projectRoot} && git checkout dev && ` +
      `git merge --no-ff ${branch} -m "Merge ${branch}: seam-hardening batch 1 (#56 #49 #55-HIGH #58-prep)" ` +
      `-m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) {
    return { success: false, failedAt: 'merge-to-dev', completed, detail: merge.output };
  }

  const issues = {
    id: 6,
    name: 'issue-updates',
    role: 'Maintainer closing out the batch in the issue tracker',
    taskText: 'Close #56 and #49 with evidence; comment on #55 and #58',
    steps: [
      'Read the merge commit on dev (git log --oneline -8) for SHAs to cite.',
      'gh issue close 56 with a comment: per-cell resolution table (supported/coerced/rejected), matrix contract test path, commit SHA.',
      'gh issue close 49 with a comment: validation rule, sentinel prompt rule, conversion guard, tests, commit SHA.',
      'gh issue comment 55: the five HIGH items fixed (file:line each, what is now loud), MEDIUM/LOW remain open in this issue.',
      'gh issue comment 58: fix_30 ready at scripts/qa/fixes/fix_30_repair_seam_audit_violations.py, dry-run output summary (paste counts), D2/D4 marked needs-curation, awaiting user approval to --apply.',
      'Do not close #55 or #58.',
    ],
    verify: 'test "$(gh issue view 56 --json state -q .state)" = "CLOSED" && test "$(gh issue view 49 --json state -q .state)" = "CLOSED"',
  };
  const issuesResult = await runTaskWithVerification(ctx, issues, { projectRoot, branch: 'dev' });
  completed.push(issuesResult);
  if (!issuesResult.verified) {
    return { success: false, failedAt: issues.name, completed, detail: issuesResult.lastOutput };
  }

  const report = await ctx.task(reportTask, { projectRoot, completed });
  return { success: true, tasksCompleted: completed.map((c) => c.name), report };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(implementTask, { ...env, ...task });
  let verify = await ctx.task(shellTask, {
    name: `verify-${task.name}`,
    command: `cd ${env.projectRoot} && ${task.verify}`,
  });
  if (verify.exitCode === 0) return { name: task.name, verified: true };
  const fixed = await fixAndReverify(ctx, task, verify.output, env);
  return { name: task.name, verified: fixed.verified, lastOutput: fixed.lastOutput };
}

async function fixAndReverify(ctx, task, failureOutput, env) {
  let lastOutput = failureOutput;
  for (let attempt = 1; attempt <= MAX_FIX_ATTEMPTS; attempt++) {
    await ctx.task(implementTask, {
      ...env, ...task, attempt,
      taskText: `${task.taskText} — previous attempt failed verification; failure output (tail): ${String(lastOutput).slice(-2000)}`,
    });
    const verify = await ctx.task(shellTask, {
      name: `verify-${task.name}-fix${attempt}`,
      command: `cd ${env.projectRoot} && ${task.verify}`,
    });
    if (verify.exitCode === 0) return { verified: true };
    lastOutput = verify.output;
  }
  return { verified: false, lastOutput };
}

const implementTask = defineTask('implement-batch-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.id}: ${args.name}${args.attempt ? ` (retry ${args.attempt})` : ''}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: args.role,
      task: args.taskText,
      context: { projectRoot: args.projectRoot, branch: args.branch, auditDir: AUDIT },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} is checked out — do NOT switch branches.`,
        ...COMMON,
        ...args.steps,
        `Verification command that must pass before you finish: ${args.verify}`,
        'Execute fully; return JSON only: { taskName, status: "done"|"blocked", filesChanged: [], commitSha, notes }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['taskName', 'status'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['implement', args.name],
}));

const shellTask = defineTask('shell-step', (args, taskCtx) => ({
  kind: 'shell',
  title: args.name,
  shell: {
    command: args.command,
    timeout: 600000,
    outputPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['shell', args.name],
}));

const reportTask = defineTask('final-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Final batch report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Tech lead writing a completion report',
      task: 'Summarize the seam-hardening batch for the user',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -10 on dev; PYTHONPATH=. poetry run pytest tests/scripts/qa/test_loud_failures.py tests/scripts/query/test_field_op_matrix.py tests/integration/test_derived_invariants.py -q 2>&1 | tail -2',
        'Report: commits, per-issue outcomes (#56 #49 closed, #55 partial, #58 pending approval with dry-run counts), new test batteries added, and the single remaining user action (approve fix_30).',
        'Return JSON: { report: "<markdown>", batteryTestsPassed: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'batteryTestsPassed'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
