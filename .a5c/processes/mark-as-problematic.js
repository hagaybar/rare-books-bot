/**
 * @process mark-as-problematic
 * @description "Mark as problematic" chat feedback feature: executes the
 *   10-task TDD plan at docs/superpowers/plans/2026-06-12-mark-as-problematic.md
 *   on feature/mark-as-problematic, with independent shell verification and a
 *   fix-retry loop per task, then a full-suite + frontend-build quality gate.
 *   Does NOT merge to dev — leaves the branch ready for review.
 * @inputs { projectRoot: string, branch: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const PLAN = 'docs/superpowers/plans/2026-06-12-mark-as-problematic.md';
const SPEC = 'docs/superpowers/specs/2026-06-12-mark-as-problematic-design.md';
const MAX_FIX_ATTEMPTS = 2;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'feature/mark-as-problematic',
  } = inputs;

  ctx.log('info', `Mark-as-problematic plan execution on branch ${branch}`);

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
      name: 'feedback-schema',
      planSection: 'Task 1: `feedback_reports` schema',
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/feedback/test_report_store.py -q',
    },
    {
      id: 2,
      name: 'report-store',
      planSection: 'Task 2: Report store — payload assembly + persistence',
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/feedback/test_report_store.py -q',
    },
    {
      id: 3,
      name: 'github-client',
      planSection: 'Task 3: GitHub client',
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/feedback/ -q',
    },
    {
      id: 4,
      name: 'message-db-id',
      planSection: 'Task 4: Expose backend message id to the frontend',
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/feedback/test_report_store.py tests/app/test_api.py -q',
    },
    {
      id: 5,
      name: 'post-feedback-route',
      planSection: 'Task 5: POST /feedback route',
      verify: 'PYTHONPATH=. poetry run pytest tests/app/test_feedback_routes.py -q',
    },
    {
      id: 6,
      name: 'admin-endpoints',
      planSection: 'Task 6: Admin endpoints — list + sync',
      verify: 'PYTHONPATH=. poetry run pytest tests/app/test_feedback_routes.py -q',
    },
    {
      id: 7,
      name: 'frontend-api-dialog',
      planSection: 'Task 7: Frontend — API client + FeedbackDialog',
      verify: 'cd frontend && npx tsc --noEmit',
    },
    {
      id: 8,
      name: 'frontend-buttons',
      planSection: 'Task 8: Frontend — flag button per message + header button',
      verify: 'cd frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3',
    },
    {
      id: 9,
      name: 'docs',
      planSection: 'Task 9: Docs',
      verify:
        'grep -qi "feedback" docs/current/chatbot-api.md && ' +
        'grep -q "GITHUB_TOKEN" docs/current/deployment.md && ' +
        'grep -qi "feedback" docs/current/architecture.md && echo docs-updated',
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

  // Final quality gate (plan Task 10): full suite + lint + frontend build.
  const gateVerify =
    'PYTHONPATH=. poetry run pytest -q 2>&1 | tail -3 && ' +
    'poetry run ruff check scripts/feedback app/api/feedback_routes.py tests/scripts/feedback tests/app/test_feedback_routes.py 2>&1 | tail -3 && ' +
    '(cd frontend && npm run build 2>&1 | tail -3)';
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command: `cd ${projectRoot} && ${gateVerify}`,
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate',
      name: 'full-suite-gate',
      planSection: 'Task 10: Final verification (full suite regression, any task)',
      verify: gateVerify,
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
      role: 'Senior full-stack developer executing a written TDD implementation plan',
      task: `Implement "${args.planSection}" from the plan, exactly as written`,
      context: { projectRoot: args.projectRoot, branch: args.branch, plan: PLAN, spec: SPEC },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} is already checked out — do NOT switch branches.`,
        `Read ${PLAN} and execute ONLY the section "${args.planSection}", following its steps in order (failing test first, watch it fail, minimal implementation, watch it pass).`,
        'The plan contains complete code for every step — use it, adjusting where its NOTE blocks tell you to verify names/signatures against existing code (read those files first; the plan cites exact file:line anchors).',
        `The spec at ${SPEC} is the authority on behavior if the plan is ambiguous.`,
        'Run Python tests with `PYTHONPATH=. poetry run pytest` (plain `pytest`/`python` are not on PATH).',
        'Do NOT make any paid LLM API calls. Mock GitHub HTTP calls in all tests — never hit api.github.com.',
        'SECRETS: never read, echo, or log .env files or GITHUB_TOKEN values. Tests must only set dummy tokens via monkeypatch.',
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
      role: 'Senior developer debugging a failing verification',
      task: `The verification for "${args.planSection}" failed — diagnose and fix`,
      context: {
        projectRoot: args.projectRoot,
        branch: args.branch,
        plan: PLAN,
        spec: SPEC,
        failureOutput: String(args.failureOutput || '').slice(-4000),
        verifyCommand: args.verify,
      },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} — do NOT switch branches.`,
        'Read the failure output, find the root cause (read the actual files — never patch blindly), apply the minimal fix consistent with the plan section.',
        'Fix the code unless the test itself contradicts the plan/spec.',
        'Run Python tests with `PYTHONPATH=. poetry run pytest`. No paid LLM API calls. Mock GitHub.',
        'SECRETS: never read, echo, or log .env files or GITHUB_TOKEN values.',
        `Re-run the verification until it passes: ${args.verify}`,
        'Add a commit for the fix (specific files only; never push).',
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
      task: 'Summarize what was implemented for the mark-as-problematic feature',
      context: { projectRoot: args.projectRoot, branch: args.branch, completed: args.completed, plan: PLAN },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only — do not modify or commit anything.`,
        `Run: git log --oneline dev..${args.branch} | head -20 and git diff --stat dev...${args.branch} | tail -5`,
        'Run the feature tests once more and capture summaries: PYTHONPATH=. poetry run pytest tests/scripts/feedback tests/app/test_feedback_routes.py -q 2>&1 | tail -3',
        'Write a concise report: commits on the branch, files changed, test status, which spec sections each commit addresses, manual steps remaining for the user (set GITHUB_TOKEN on the server, manual frontend smoke test, merge decision).',
        'Return JSON: { report: "<markdown report>", commits: [], featureTestsPassed: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'featureTestsPassed'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
