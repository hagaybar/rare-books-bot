/**
 * @process seam-hardening-batch2
 * @description Recall-correctness batch from the gold-suite re-run: #45
 *   (selectivity ceiling on the unresolved-entity probe union — kill the
 *   "Jacob" 119-record over-broadening) and #48 (singular/plural stemming in
 *   the relaxation ladder so a singular subject term still finds the plural
 *   heading). TDD per task, deterministic verification (no live LLM), full
 *   suite gate, merge to dev, issue closures.
 * @inputs { projectRoot: string, branch: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;

const COMMON = [
  'TDD is mandatory: write the failing test first, run it to watch it fail, implement minimally, watch it pass, then ruff-check touched files and commit specific files (never git add -A; never push from inside a task).',
  'Run Python tests with `PYTHONPATH=. poetry run pytest` (plain pytest/python are not on PATH).',
  'No paid LLM API calls — ALL tests must be deterministic (construct plans/filters directly or use a tmp fixture DB; never call the interpreter/LLM).',
  'DBs read-only except none — this batch writes no DB. SECRETS: never read or echo .env files or token values.',
  'Research before editing: read every file you change first. Match surrounding code style.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'fix/seam-hardening-batch2',
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
      name: 'selectivity-cap-45',
      role: 'Senior Python developer fixing a recall-precision bug in the executor',
      taskText: 'Issue #45: add a selectivity ceiling to the unresolved-entity probe union so non-selective tokens (e.g. a common given name) cannot flood the result set',
      steps: [
        'Read `gh issue view 45` and the unresolved-entity recovery rung in scripts/chat/executor.py: the probe-union loop inside _handle_retrieve (search for "fallback_indices" and "recovered {len(ids)} records"), plus _fallback_tokens and _unresolved_ref_fallback. The bug: when entity resolution fails, every candidate token is probed via CONTAINS and ALL matching record sets are UNIONed — so "Jacob ibn Habib" unresolved -> token "Jacob" CONTAINS matches 119 agents and floods the set (diagnostic TEST-AUTH-04: 234 historically, 119 now; expected <=3).',
        'Fix: introduce a selectivity ceiling for the unresolved-entity probe union ONLY (do NOT touch the separate _relax_and_retry topical OR-union ladder). Compute the ceiling relative to collection size: define a module constant or helper, e.g. ceiling = max(20, round(0.01 * total_records)) (~28 for the 2,796-record collection). A probe whose result count EXCEEDS the ceiling is rejected as non-selective: it is NOT unioned in, and a relaxation note is recorded (e.g. "probe agent_norm CONTAINS \'Jacob\' matched N records (> ceiling C); rejected as non-selective"). Selective probes (e.g. \'חביב\'=6, \'Habib\'=2) are still unioned. If ALL probes are rejected and nothing else recovered, fall through to the existing honest-empty path (resolution-failure note already present). The collection size should be read once (SELECT COUNT(*) FROM records) and passed into the loop.',
        'TDD in tests/scripts/chat/test_executor.py (extend; follow its tmp-DB fixture style): seed a fixture where an unresolved agent_norm ref has tokens that include a COMMON token (matches many rows, > ceiling) and a RARE token (matches few). Assert: the rare token\'s records ARE returned, the common token\'s flood is NOT, and a "rejected as non-selective" relaxation note is recorded. Use a small fixture with a deliberately low effective ceiling (e.g. parametrize/inject the ceiling, or size the fixture so the math works) — keep it deterministic, no LLM.',
        'Make the ceiling injectable for testing if needed (default computed from collection), but keep production behavior unchanged for resolved/selective cases.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py -q',
    },
    {
      id: 2,
      name: 'subject-stemming-48',
      role: 'Senior Python developer closing a subject-recall gap',
      taskText: 'Issue #48: singular/plural stemming in the relaxation ladder so a singular subject/title term still finds the plural heading before declaring empty',
      steps: [
        'Read `gh issue view 48` and _relax_and_retry + the topical-CONTAINS handling in scripts/chat/executor.py. The gap: FTS5 has no stemming, so subject CONTAINS "limited edition" (singular) returns 0 even though the heading "Limited editions" (plural, 103 records) exists. Currently recall depends on the LLM happening to emit the plural.',
        'Fix: in the relaxation ladder, for each topical (SUBJECT/TITLE/PHYSICAL_DESC) CONTAINS term that yields 0, before honest-empty try a simple morphological variant: toggle a trailing "s" (singular<->plural; also handle "es" minimally if cheap). Probe the variant; if it recovers records, union them and record a relaxation note (e.g. "no match for subject \'limited edition\'; matched plural \'limited editions\' (103 records)"). Keep it conservative (ASCII trailing-s toggle only; do not stem Hebrew). This must compose with the existing concept_bridge expansion, not replace it.',
        'TDD in tests/scripts/chat/test_executor.py: seed a fixture with a subject heading "limited editions" and assert a retrieve with subject CONTAINS "limited edition" (singular) recovers it via the stemming relaxation, with the relaxation note recorded. Also assert a term with no variant match still returns honest-empty. Deterministic, no LLM.',
        'Optional (only if trivial and safe): rebuild-free — do NOT change the FTS tokenizer (that needs an index rebuild); keep this purely in the ladder.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py -q',
    },
    {
      id: 3,
      name: 'deterministic-replay',
      role: 'QA engineer proving the fixes on the real saved query plans (no LLM)',
      taskText: 'Add a deterministic regression test replaying the saved AUTH-04 plan + a singular-subject plan through the executor against the live DB',
      steps: [
        'Create tests/integration/test_recall_regression.py (mark `integration`; skipif data/index/bibliographic.db absent; read-only DB). It must NOT call the interpreter/LLM — construct InterpretationPlan objects directly (or load the saved plan JSON from data/runs/diagnostic_suite_20260613/TEST-AUTH-04.json if present, else build the equivalent plan inline) and run scripts.chat.executor.execute_plan against the live DB.',
        'Test 1 (#45): replay the AUTH-04 plan (resolve_agent "Jacob ibn Habib" that fails to resolve + retrieve agent_norm EQUALS $step_0). Assert the executed total is now well under the old flood — e.g. <= 30 (was 119/234) — AND that if any records return they came via a selective probe (check the relaxations mention rejection of the non-selective token OR that no >ceiling probe was unioned). Keep the bound generous but firmly below 119.',
        'Test 2 (#48): build a plan with a single retrieve, subject CONTAINS "limited edition" (singular), scope full_collection. Assert execute_plan recovers the 103-record "Limited editions" heading via the stemming relaxation (total == 103, or >= 100 to be robust), and the relaxation note is present.',
        'If the saved AUTH-04 JSON is unavailable, construct the plan inline from the documented shape; do not depend on the run artifacts existing.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/integration/test_recall_regression.py -q',
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
    'PYTHONPATH=. poetry run pytest tests/integration/test_derived_invariants.py tests/integration/test_recall_regression.py -q 2>&1 | tail -2 && ' +
    'poetry run ruff check scripts/chat/executor.py tests/scripts/chat/test_executor.py tests/integration/test_recall_regression.py 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command: `cd ${projectRoot} && ${gateVerify}`,
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate', role: 'Senior developer fixing a regression',
      taskText: 'Full-suite gate failed — diagnose and fix', steps: [],
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
      `git merge --no-ff ${branch} -m "Merge ${branch}: recall-correctness batch (#45 selectivity cap, #48 subject stemming)" ` +
      `-m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) {
    return { success: false, failedAt: 'merge-to-dev', completed, detail: merge.output };
  }

  const issues = {
    id: 4,
    name: 'issue-updates',
    role: 'Maintainer closing the batch in the issue tracker',
    taskText: 'Close #45 and #48 with evidence',
    steps: [
      'Run git log --oneline -6 on dev for SHAs.',
      'gh issue close 45 with a comment: the selectivity-ceiling fix (file:line), the ceiling formula, the deterministic replay result (AUTH-04 total dropped from 119 to <bound>), commit SHA.',
      'gh issue close 48 with a comment: the singular/plural stemming relaxation (file:line), the replay result (singular "limited edition" now recovers the 103-record plural heading), commit SHA.',
      'If either fix turned out to be only partial, comment honestly and leave the issue open instead of closing.',
    ],
    verify: 'test "$(gh issue view 45 --json state -q .state)" = "CLOSED" && test "$(gh issue view 48 --json state -q .state)" = "CLOSED"',
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
      taskText: `${task.taskText} — previous attempt failed verification; failure tail: ${String(lastOutput).slice(-2000)}`,
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

const implementTask = defineTask('implement-batch2-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.id}: ${args.name}${args.attempt ? ` (retry ${args.attempt})` : ''}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: args.role,
      task: args.taskText,
      context: { projectRoot: args.projectRoot, branch: args.branch },
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
      task: 'Summarize recall-correctness batch 2',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -8; PYTHONPATH=. poetry run pytest tests/integration/test_recall_regression.py -q 2>&1 | tail -2',
        'Report: commits, #45 outcome (AUTH-04 flood killed — give the before/after number), #48 outcome (singular subject now recovers plural), new regression test, and any residual recall items deferred (e.g. #47 expansion transparency).',
        'Return JSON: { report: "<markdown>", regressionTestsPassed: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'regressionTestsPassed'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
