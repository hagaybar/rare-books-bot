/**
 * @process held-set-correctness
 * @description Fix the three held-set defects a live two-turn prod test surfaced
 *   in the #60 active_subgroup feature: B1 held set captured the truncated display
 *   (30) not the full result (74); B2 counting questions misclassified as refine
 *   (narrow) instead of explore (aggregate); B3 disclosure conflated held-set size
 *   with the answer count (also folds in #61, full-builder parity). Executes the
 *   pre-approved TDD plan docs/superpowers/plans/2026-06-13-held-set-correctness-fixes.md.
 *   Deterministic verification (no live LLM), full-suite gate, merge to dev, issue
 *   tracking. Deploy is left to the user.
 * @inputs { projectRoot: string, branch: string, planPath: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;

const PLAN = 'docs/superpowers/plans/2026-06-13-held-set-correctness-fixes.md';

const COMMON = [
  `The implementation plan is ${PLAN} and the spec is docs/superpowers/specs/2026-06-13-held-set-correctness-fixes-design.md. READ the plan section(s) for your assigned task FIRST — they contain exact file paths, complete code, and exact test code. Implement them faithfully.`,
  'TDD is mandatory: write/adjust the failing test first, run it to watch it fail, implement minimally, watch it pass, then ruff-check touched Python files and commit specific files (never git add -A; never push from inside a task).',
  'Run Python with `PYTHONPATH=. poetry run python ...` and tests with `PYTHONPATH=. poetry run pytest ...` (bare `python`/`pytest` are NOT on PATH — always go through `poetry run`).',
  'No paid LLM API calls — ALL tests are deterministic (construct ExecutionResult/StepResult/RecordSet/InterpretationPlan objects directly, or assert on prompt strings). Never call the interpreter/narrator LLM.',
  'The plan flags a few names as "read the existing file and use the real name" (the narrator full builder _build_narrator_prompt, the lean builder build_lean_narrator_prompt, the INTERPRETER_SYSTEM_PROMPT constant, the _make_execution_result test helper). Honor that — open the file, use the real name.',
  'No bibliographic.db writes. SECRETS: never read or echo .env files or token values.',
  'Research before editing: read every file you change first (bounded reads — rg/grep then small excerpts). Match surrounding code style. Before finishing Task 1, grep for all callers of build_subgroup_update to ensure none are missed.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'fix/held-set-correctness',
    planPath = PLAN,
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
      name: 'b1-full-held-set',
      role: 'Senior Python developer fixing a deterministic data-capture bug',
      taskText: 'Plan Task 1 (B1): held set must capture the FULL retrieve result, not the truncated 30-record display',
      steps: [
        `Implement Plan Task 1 from ${planPath} exactly. Add held_record_ids(execution_result) to scripts/chat/subgroup_policy.py (deduped order-preserving union of retrieve steps RecordSet.mms_ids); change build_subgroup_update to take the ExecutionResult (not the CandidateSet) and set record_ids = held_record_ids(result), candidate_set=None. Update BOTH call sites in app/api/main.py (REST + WS) to pass execution_result.`,
        'TDD: add the new tests incl. test_build_subgroup_update_uses_full_set_not_truncated_display (the 74-vs-30 regression). CRITICAL: the existing #60 policy tests pass a CandidateSet as the 2nd arg — UPDATE them to build an ExecutionResult via the new _exec_result helper and pass that, preserving their intent (new-search/refine -> replace; explore/empty/no-retrieve -> None). The plan gives the _exec_result helper verbatim; StepResult fields are step_index/action/label/status/data, GroundingData fields all default, RecordSet needs mms_ids/total_count/filters_applied.',
        'grep -rn build_subgroup_update across the repo to confirm only the two handler sites + tests call it; update all.',
        'After: PYTHONPATH=. poetry run python -c "import app.api.main" must exit 0. ruff check the two source files. Commit with the plan message.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -6 && PYTHONPATH=. poetry run python -c "import app.api.main" && echo IMPORT_OK && poetry run ruff check scripts/chat/subgroup_policy.py 2>&1 | tail -2',
    },
    {
      id: 2,
      name: 'b2-explore-vs-refine',
      role: 'Senior developer refining an LLM system prompt + prompt-discipline test',
      taskText: 'Plan Task 2 (B2): teach the interpreter that counting questions over the held set are EXPLORE (aggregate over $previous_results), never refine (narrow)',
      steps: [
        `Implement Plan Task 2 from ${planPath} exactly. Add the "EXPLORE vs REFINE — the critical distinction" rule + the two-example few-shot ("how many are in Hebrew?" -> single aggregate scope=$previous_results; "only the Hebrew ones" -> retrieve scope=$previous_results) into the three-intent section of the interpreter system prompt in scripts/chat/interpreter.py (the # FOLLOW-UP QUERIES AND THE HELD RESULT SET block).`,
        'TDD: add test_system_prompt_steers_counting_questions_to_aggregate to tests/scripts/chat/test_interpreter.py (reuse the INTERPRETER_SYSTEM_PROMPT accessor the existing TestPromptThreeIntentHeldSet tests use). Watch fail, edit prompt, watch pass.',
        'If an existing prompt test asserts wording this insertion shifts, update that assertion. Prompt-string change only — no LLM call.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_interpreter.py -q 2>&1 | tail -5',
    },
    {
      id: 3,
      name: 'b3-disclosure-parity',
      role: 'Senior developer hardening the narrator disclosure across both builders',
      taskText: 'Plan Task 3 (B3 + #61): disclose held-set size distinctly from the answer count, in BOTH narrator builders',
      steps: [
        `Implement Plan Task 3 from ${planPath} exactly. Replace the lean-builder held-set disclosure block (build_lean_narrator_prompt) with the tightened version that states the held-set size as a number DISTINCT from the answer ("Of the N you're exploring, X are ...", "never reuse one number for both"), and add the SAME block to the full builder _build_narrator_prompt (closes #61). If both builders share the sections[] idiom, a shared _held_set_disclosure(result) helper is cleaner than duplicating — verify first.`,
        'TDD: add test_lean_builder_discloses_held_set_size_distinctly and test_full_builder_also_discloses_held_set to tests/scripts/chat/test_narrator.py (reuse _make_execution_result + SessionContext, previous_record_ids of 74). Confirm the full builder real name/signature by reading the file. Watch fail, implement, watch pass.',
        'Update the #60 test_narrator_prompt_discloses_held_set_when_scoped if the new wording conflicts (keep the exploring+count checks).',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_narrator.py -q 2>&1 | tail -5',
    },
    {
      id: 4,
      name: 'docs',
      role: 'Maintainer updating current docs',
      taskText: 'Plan Task 4: doc updates for the held-set correctness fixes',
      steps: [
        `Implement Plan Task 4 from ${planPath}. chatbot-api.md: held set is the FULL match set (not the displayed subset); explore (aggregate, unchanged) vs refine (retrieve, replaces); disclosure phrases size and answer as DISTINCT numbers. architecture.md: note subgroup_policy.held_record_ids sources the full retrieve union. Set Last verified: 2026-06-13 in both headers.`,
      ],
      verify:
        'cd ${PROJECT} && grep -q "full" docs/current/chatbot-api.md && grep -q "2026-06-13" docs/current/architecture.md && grep -q "held_record_ids" docs/current/architecture.md && echo DOCS_OK',
    },
  ];

  const completed = [];
  for (const task of tasks) {
    task.verify = task.verify.split('${PROJECT}').join(projectRoot);
    const result = await runTaskWithVerification(ctx, task, { projectRoot, branch, planPath });
    completed.push(result);
    if (!result.verified) {
      return { success: false, failedAt: task.name, completed, detail: result.lastOutput };
    }
  }

  // ---- Full verification gate (Plan Task 5) ----
  const gateVerify =
    'PYTHONPATH=. poetry run pytest -q -m "not integration" 2>&1 | tail -4 && ' +
    'PYTHONPATH=. poetry run pytest -q -m integration 2>&1 | tail -3 && ' +
    'poetry run ruff check scripts/chat/subgroup_policy.py scripts/chat/interpreter.py scripts/chat/narrator.py app/api/main.py 2>&1 | tail -4 && ' +
    'cd frontend && npx tsc --noEmit 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command: `cd ${projectRoot} && ${gateVerify}`,
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate',
      role: 'Senior developer fixing a regression caught by the full-suite gate',
      taskText: 'Full-suite / ruff / tsc gate failed — diagnose from the failure tail and fix, within the held-set-correctness scope',
      steps: ['Only touch files this batch created/modified. If a failure is pre-existing/unrelated, confirm via git and leave it (note it).'],
      verify: gateVerify,
    }, gate.output, { projectRoot, branch, planPath });
    if (!fixed.verified) {
      return { success: false, failedAt: 'full-suite-gate', completed, detail: fixed.lastOutput };
    }
  }

  // ---- Merge to dev ----
  const merge = await ctx.task(shellTask, {
    name: 'merge-to-dev',
    command:
      `cd ${projectRoot} && git checkout dev && ` +
      `git merge --no-ff ${branch} -m "Merge ${branch}: held-set correctness fixes (B1 full set, B2 explore-vs-refine, B3 disclosure + #61)" ` +
      `-m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) {
    return { success: false, failedAt: 'merge-to-dev', completed, detail: merge.output };
  }

  // ---- Issue tracking ----
  const issues = {
    id: 5,
    name: 'issue-update',
    role: 'Maintainer recording the batch in the issue tracker',
    taskText: 'Open a tracking issue for B1/B2/B3 and close it with evidence; close #61',
    steps: [
      'Run git log --oneline -12 on dev for SHAs and the merge SHA.',
      'Open ONE issue titled "Held-set correctness: B1 truncated set / B2 explore-vs-refine / B3 disclosure (live-test findings)" documenting the three defects from the 2026-06-13 two-turn prod test (Venice 74 -> "among the 9, all 9 Hebrew"), then CLOSE it with a comment giving the fix per defect (file:line), the merge SHA, and the new regression test test_build_subgroup_update_uses_full_set_not_truncated_display. Note B2 quality is re-validated manually after deploy.',
      'Close #61 with a comment: held-set disclosure now in both narrator builders (full-builder parity), shipped in this batch; give the merge SHA.',
      'Note in both comments that deploy to prod + the re-run of the two-turn scenario are pending the user decision (this run did not deploy).',
    ],
    verify: 'test "$(gh issue view 61 --json state -q .state)" = "CLOSED" && echo ISSUE61_CLOSED',
  };
  const issuesResult = await runTaskWithVerification(ctx, issues, { projectRoot, branch: 'dev', planPath });
  completed.push(issuesResult);
  if (!issuesResult.verified) {
    return { success: false, failedAt: issues.name, completed, detail: issuesResult.lastOutput };
  }

  const report = await ctx.task(reportTask, { projectRoot, completed });
  return { success: true, tasksCompleted: completed.map((c) => c.name), report };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(implementTask, { ...env, ...task });
  const verify = await ctx.task(shellTask, {
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

const implementTask = defineTask('implement-heldset-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.id}: ${args.name}${args.attempt ? ` (retry ${args.attempt})` : ''}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: args.role,
      task: args.taskText,
      context: { projectRoot: args.projectRoot, branch: args.branch, planPath: args.planPath },
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
      task: 'Summarize the held-set correctness batch',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -12; PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -3',
        'Report (markdown): B1 (held set now full set — cite the 74-vs-30 regression test), B2 (counting -> aggregate prompt rule), B3+#61 (disclosure size-vs-answer + full-builder parity), merge SHA, issue states, and the explicit note that deploy to prod + re-running the two-turn scenario are PENDING the user decision (not done this run).',
        'Return JSON: { report: "<markdown>", allTestsPassed: boolean, deployPending: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'allTestsPassed'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
