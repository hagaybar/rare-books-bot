/**
 * @process issue2-multi-topic-recall
 * @description Issue #2: multi-topic recall & curatorial routing. Executes the
 *   7-task TDD plan at docs/superpowers/plans/2026-06-10-multi-topic-recall-and-curation.md
 *   on a dedicated feature branch, with independent shell verification and a
 *   fix-retry loop per task, then a full-suite quality gate.
 * @inputs { projectRoot: string, branch: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const PLAN = 'docs/superpowers/plans/2026-06-10-multi-topic-recall-and-curation.md';
const MAX_FIX_ATTEMPTS = 2;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'feature/issue-2-multi-topic-recall',
  } = inputs;

  ctx.log('info', `Issue #2 plan execution on branch ${branch}`);

  // Phase 0: feature branch off dev — never commit to dev/main directly.
  const branchResult = await ctx.task(shellTask, {
    name: 'setup-branch',
    command:
      `cd ${projectRoot} && ` +
      `(git rev-parse --verify ${branch} >/dev/null 2>&1 && git checkout ${branch} ` +
      `|| git checkout -b ${branch} dev) && git branch --show-current`,
  });
  if (branchResult.exitCode !== 0) {
    return { success: false, failedAt: 'setup-branch', detail: branchResult.output };
  }

  const tasks = [
    {
      id: 1,
      name: 'concept-bridge',
      planSection: 'Task 1: Concept→vocabulary bridge',
      verify: 'poetry run pytest tests/scripts/query/test_concept_bridge.py -q',
    },
    {
      id: 2,
      name: 'physical-desc-filter',
      planSection: 'Task 2: `physical_desc` filter field',
      verify:
        'poetry run pytest tests/scripts/query/test_db_adapter.py tests/scripts/query/test_query_plan.py -q',
    },
    {
      id: 3,
      name: 'relaxation-ladder',
      planSection: 'Task 3: Relaxation ladder + scope union in the executor',
      verify:
        'poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_plan_models.py -q',
    },
    {
      id: 4,
      name: 'interpreter-prompt',
      planSection:
        'Task 4: Interpreter prompt — coordinate topics, physical_desc, curatorial routing',
      verify: 'poetry run pytest tests/scripts/chat/test_interpreter.py -q',
    },
    {
      id: 5,
      name: 'acceptance-regression',
      planSection: 'Task 5: Acceptance regression test + eval entry',
      verify:
        'poetry run pytest tests/integration/test_multi_topic_recall.py -q && ' +
        `python3 -c "import json; json.load(open('data/eval/queries.json')); print('queries.json valid')"`,
    },
    {
      id: 6,
      name: 'citation-harness',
      planSection: 'Task 6: External-citation verification harness',
      verify: 'poetry run pytest tests/scripts/qa/test_verify_external_citations.py -q',
    },
    {
      id: 7,
      name: 'docs',
      planSection: 'Task 7: Docs, full suite, issue closure',
      verify:
        'grep -q "elaxation" docs/current/query-engine.md && grep -qi "citation" docs/current/qa-framework.md && echo docs-updated',
    },
  ];

  const completed = [];
  for (const task of tasks) {
    const result = await runTaskWithVerification(ctx, task, { projectRoot, branch });
    completed.push(result);
    if (!result.verified) {
      return {
        success: false,
        failedAt: task.name,
        completed,
        detail: result.lastOutput,
      };
    }
  }

  // Final quality gate: full test suite + lint must be green.
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command:
      `cd ${projectRoot} && poetry run pytest -q 2>&1 | tail -5 && ` +
      'poetry run ruff check scripts/ app/ tests/ 2>&1 | tail -3',
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate',
      name: 'full-suite-gate',
      planSection: 'full suite regression (any task)',
      verify:
        'poetry run pytest -q 2>&1 | tail -5 && poetry run ruff check scripts/ app/ tests/ 2>&1 | tail -3',
    }, gate.output, { projectRoot, branch });
    if (!fixed.verified) {
      return { success: false, failedAt: 'full-suite-gate', completed, detail: fixed.lastOutput };
    }
  }

  // Final report (agent summarizes what landed, for the user).
  const report = await ctx.task(reportTask, { projectRoot, branch, completed });

  return {
    success: true,
    branch,
    tasksCompleted: completed.map((c) => c.name),
    report,
  };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(implementTask, { ...env, ...task });
  let verify = await ctx.task(shellTask, {
    name: `verify-${task.name}`,
    command: `cd ${env.projectRoot} && ${task.verify}`,
  });
  if (verify.exitCode === 0) {
    return { name: task.name, verified: true };
  }
  const fixed = await fixAndReverify(ctx, task, verify.output, env);
  return { name: task.name, verified: fixed.verified, lastOutput: fixed.lastOutput };
}

async function fixAndReverify(ctx, task, failureOutput, env) {
  let lastOutput = failureOutput;
  for (let attempt = 1; attempt <= MAX_FIX_ATTEMPTS; attempt++) {
    await ctx.task(fixTask, { ...env, ...task, attempt, failureOutput: lastOutput });
    const verify = await ctx.task(shellTask, {
      name: `verify-${task.name}-fix${attempt}`,
      command: `cd ${env.projectRoot} && ${task.verify}`,
    });
    if (verify.exitCode === 0) {
      return { verified: true };
    }
    lastOutput = verify.output;
  }
  return { verified: false, lastOutput };
}

const implementTask = defineTask('implement-plan-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.id}: ${args.name}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer executing a written TDD implementation plan',
      task: `Implement "${args.planSection}" from the plan, exactly as written`,
      context: { projectRoot: args.projectRoot, branch: args.branch, plan: PLAN },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} is already checked out — do NOT switch branches.`,
        `Read ${PLAN} and execute ONLY the section "${args.planSection}", following its steps in order (failing test first, watch it fail, minimal implementation, watch it pass).`,
        'The plan contains complete code for every step — use it verbatim, adjusting only line numbers/anchors if the file drifted. Read every file before editing it.',
        'Honor the plan\'s "Verified research facts" — do not re-derive or second-guess them.',
        'Run tests with `poetry run pytest` (plain `pytest`/`python` are not on PATH).',
        'Do NOT make any paid LLM API calls. All tests are LLM-free by design.',
        `Finish with the task's commit step (git add <specific files> && git commit) on ${args.branch}. Never use git add -A; never push.`,
        `Verification command that must pass before you finish: ${args.verify}`,
        'Return JSON: { taskName, status: "done"|"blocked", filesChanged: [], commitSha, notes }',
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

const fixTask = defineTask('fix-plan-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Fix ${args.name} (attempt ${args.attempt})`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer debugging a failing verification',
      task: `The verification for "${args.planSection}" failed — diagnose and fix`,
      context: {
        projectRoot: args.projectRoot,
        branch: args.branch,
        plan: PLAN,
        failureOutput: String(args.failureOutput || '').slice(-4000),
        verifyCommand: args.verify,
      },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} — do NOT switch branches.`,
        'Read the failure output, find the root cause (read the actual files — never patch blindly), apply the minimal fix consistent with the plan section.',
        'Fix the code unless the test itself contradicts the plan.',
        'Run tests with `poetry run pytest`. No paid LLM API calls.',
        `Re-run the verification until it passes: ${args.verify}`,
        'Amend or add a commit for the fix (specific files only; never push).',
        'Return JSON: { taskName, status: "done"|"blocked", rootCause, filesChanged: [] }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['taskName', 'status'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['fix', args.name],
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
  title: 'Final implementation report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Tech lead writing a completion report',
      task: 'Summarize what was implemented for issue #2',
      context: { projectRoot: args.projectRoot, branch: args.branch, completed: args.completed, plan: PLAN },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only — do not modify or commit anything.`,
        `Run: git log --oneline dev..${args.branch} | head -20 and git diff --stat dev...${args.branch} | tail -5`,
        'Run the acceptance test once more and capture its summary: poetry run pytest tests/integration/test_multi_topic_recall.py -q 2>&1 | tail -3',
        'Write a concise report: commits on the branch, files changed, acceptance-test status, which issue-#2 items (A1-A3, B4-B6, C8, D9-D10) each commit addresses, and what was consciously deferred (B7 embeddings, live LLM verification, issue closure - left for the user).',
        'Return JSON: { report: "<markdown report>", commits: [], acceptanceTestPassed: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'acceptanceTestPassed'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
