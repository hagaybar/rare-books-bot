/**
 * @process active-subgroup-scoping
 * @description Wire the dormant `active_subgroup` held-set machinery end to end
 *   (issue #60 part 2). Implements the bite-sized TDD plan at
 *   docs/superpowers/plans/2026-06-13-active-subgroup-scoping.md: ChatSession
 *   field + get_session load, a pure subgroup_policy lifecycle module, REST+WS
 *   write/surfacing, a reset endpoint, interpreter three-intent prompt, narrator
 *   disclosure, and the frontend held-set chip. Reuses the existing
 *   `$previous_results` scope keyword and `set_active_subgroup(None)` clear — no
 *   new primitives. Deterministic verification (no live LLM), full-suite gate,
 *   merge to dev, issue closure.
 * @inputs { projectRoot: string, branch: string, planPath: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;

const PLAN = 'docs/superpowers/plans/2026-06-13-active-subgroup-scoping.md';

const COMMON = [
  `The authoritative spec is docs/superpowers/specs/2026-06-13-active-subgroup-scoping-design.md and the implementation plan is ${PLAN}. READ the plan section(s) for your assigned task FIRST — they contain exact file paths, complete code, and the exact test code. Implement them faithfully; the plan already resolved the key design decisions (reuse the existing "$previous_results" scope keyword and set_active_subgroup(None) clear — do NOT add a new "active_subgroup" scope keyword or a clear_active_subgroup method).`,
  'TDD is mandatory: write the failing test first, run it to watch it fail, implement minimally, watch it pass, then ruff-check touched Python files (or tsc/eslint for frontend) and commit specific files (never git add -A; never push from inside a task).',
  'Run Python tests with `PYTHONPATH=. poetry run pytest` (plain pytest/python are not on PATH). Run frontend checks from the frontend/ dir.',
  'No paid LLM API calls — ALL tests must be deterministic (construct InterpretationPlan/CandidateSet/Filter objects directly or use a tmp fixture DB; never call the interpreter/narrator LLM). The interpreter/narrator changes are prompt-string + prompt-discipline assertions only.',
  'The plan flags some test helper/fixture names as "read the existing test file and use the real name" (e.g. the system-prompt accessor, the narrator prompt builder, the API auth fixture). Honor that: open the referenced existing test file, find the real accessor/fixture, and use it — do not invent a name.',
  'No bibliographic.db writes. This feature writes only to the chat sessions DB and tmp test DBs. SECRETS: never read or echo .env files or token values.',
  'Research before editing: read every file you change first (bounded reads per CLAUDE.md — rg/grep then small excerpts). Match surrounding code style.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'fix/active-subgroup-scoping',
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
      name: 'models-and-load',
      role: 'Senior Python developer wiring a Pydantic field + a session-store load path',
      taskText: 'Plan Tasks 1 & 2: add ChatSession.active_subgroup and have SessionStore.get_session populate it via the existing get_active_subgroup',
      steps: [
        `Implement Plan Task 1 then Plan Task 2 from ${planPath} exactly (the plan has the complete code and tests).`,
        'Task 1: add `active_subgroup: Optional[ActiveSubgroup] = None` to ChatSession in scripts/chat/models.py (ActiveSubgroup + Optional already in the file). Tests in tests/scripts/chat/test_models.py.',
        'Task 2: in scripts/chat/session_store.py get_session, after attaching messages, add `session.active_subgroup = self.get_active_subgroup(session_id)` and return. Tests in tests/scripts/chat/test_session_store.py — reuse that file\'s existing store fixture / create_session convention (read it first; match the real fixture/method names).',
        'Commit each plan task separately with the plan\'s commit messages.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_models.py tests/scripts/chat/test_session_store.py -q 2>&1 | tail -5',
    },
    {
      id: 2,
      name: 'policy-module',
      role: 'Senior Python developer building a pure, LLM-free policy module',
      taskText: 'Plan Task 3: create scripts/chat/subgroup_policy.py (build_subgroup_update / summarize_filters / subgroup_summary / was_scoped_to_held_set) with full unit tests',
      steps: [
        `Implement Plan Task 3 from ${planPath} exactly — the plan contains the complete module code and 11 unit tests in tests/scripts/chat/test_subgroup_policy.py.`,
        'Before running, verify the import surface the tests rely on: confirm Candidate, CandidateSet, Filter, FilterField, FilterOp are importable from scripts.schemas (test_models.py imports several of these from there); if Candidate is not exported there, import it from its real module and adjust the test import. Confirm InterpretationPlan/ExecutionStep/RetrieveParams/AggregateParams/StepAction field names against scripts/chat/plan_models.py and fix the test constructors if any required field differs.',
        'Watch the tests fail (ModuleNotFoundError), implement the module, watch them pass. ruff check + ruff format the new module.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -5 && poetry run ruff check scripts/chat/subgroup_policy.py 2>&1 | tail -3',
    },
    {
      id: 3,
      name: 'api-wiring',
      role: 'Senior backend developer wiring the held-set lifecycle into both chat handlers + a reset endpoint',
      taskText: 'Plan Tasks 4, 5 & 6: REST handler write/surfacing, WS handler write/surfacing, and the DELETE /sessions/{id}/subgroup reset endpoint — all in app/api/main.py',
      steps: [
        `Implement Plan Tasks 4, 5, and 6 from ${planPath} exactly. All three edit app/api/main.py; do them in one pass so the file stays coherent.`,
        'Task 4 (REST ~675-793): import build_subgroup_update/subgroup_summary/was_scoped_to_held_set; add held-set summary to the clarification metadata; after the assistant add_message, write/keep the held set (build_subgroup_update -> set_active_subgroup), set phase=CORPUS_EXPLORATION when was_scoped_to_held_set, and put subgroup_summary(held) in response.metadata["active_subgroup"].',
        'Task 5 (WS ~1012-1144): mirror the same after the WS add_message try/except. CONFIRM which session local exists in the WS scope (read ~1000-1020) and reuse it for the unchanged-case held read — do NOT add a redundant get_session if `session` is already in scope. Make set_active_subgroup failure-tolerant (try/except + logger.exception). Add the summary to the WS clarification metadata too.',
        'Task 6: add the DELETE /sessions/{session_id}/subgroup route after expire_session (~893), modeled on expire_session\'s auth+ownership; it calls store.set_active_subgroup(session_id, None) and returns success (200 no-op when none, 404 unknown session). Test in tests/api/test_subgroup_reset.py — reuse the existing API test auth fixture/TestClient (read an existing tests/api test that hits /sessions/{id}; if none, replicate the require_role override the suite already uses).',
        'After all three: `python -c "import app.api.main"` must exit 0. Commit each plan task separately with the plan\'s messages.',
      ],
      verify:
        'cd ${PROJECT} && PYTHONPATH=. python -c "import app.api.main" && PYTHONPATH=. poetry run pytest tests/api/test_subgroup_reset.py -q 2>&1 | tail -5',
    },
    {
      id: 4,
      name: 'interpreter-prompt',
      role: 'Senior developer refining an LLM system prompt + a prompt-discipline test',
      taskText: 'Plan Task 7: teach the interpreter the three-intent held-set model (new search / explore-in-set / refine-in-set) mapped to full_collection vs $previous_results',
      steps: [
        `Implement Plan Task 7 from ${planPath} exactly. This is prompt-string text + a prompt-discipline test only (no LLM call).`,
        'Replace the # FOLLOW-UP QUERIES block in scripts/chat/interpreter.py (~310-315) with the three-intent block from the plan; reword the held-set hint in the user-prompt builder (~514-524). The optional previous_defining_query SessionContext enrichment is OPTIONAL — skip unless trivial.',
        'Tests in tests/scripts/chat/test_interpreter.py: reuse the file\'s real system-prompt accessor and user-prompt builder names (the builder contains lines ~505-533). Assert "$previous_results" and the new-search/explore/refine vocabulary are present, and that a held set\'s count reaches the user prompt. If an existing prompt test asserts the OLD "PREVIOUS RESULT SET"/"narrow to these records" wording, update that assertion to the new wording.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_interpreter.py -q 2>&1 | tail -5',
    },
    {
      id: 5,
      name: 'narrator-disclosure',
      role: 'Senior developer adding a disclosure section to the narrator prompt',
      taskText: 'Plan Task 8: narrator discloses held-set scoping ("Among the N you\'re exploring, ...")',
      steps: [
        `Implement Plan Task 8 from ${planPath} exactly. Add the held-set disclosure block right after the "# --- Session context ---" block in scripts/chat/narrator.py (~827-832), before the final "Compose a scholarly response" append. It reads result.session_context.previous_record_ids (already threaded through ExecutionResult).`,
        'Test in the narrator test file: reuse its real prompt-builder function name (the builder whose tail is ~837-842) and its ExecutionResult construction; attach a SessionContext with previous_record_ids if the existing tests don\'t. Assert "exploring" + the count appear in the prompt.',
      ],
      verify:
        'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_narrator.py -q 2>&1 | tail -5',
    },
    {
      id: 6,
      name: 'frontend-chip',
      role: 'Frontend engineer (React/TS/Tailwind) adding a held-set chip + reset',
      taskText: 'Plan Task 9: ActiveSubgroupSummary type, PhaseIndicator held-set chip with "Search all" reset, Chat.tsx wiring + DELETE call',
      steps: [
        `Implement Plan Task 9 from ${planPath} exactly. Add ActiveSubgroupSummary to frontend/src/types/chat.ts; replace PhaseIndicator.tsx with the chip+reset version from the plan (<bdi> guards Hebrew defining queries); wire heldSet + onReset in frontend/src/pages/Chat.tsx.`,
        'In Chat.tsx, MATCH the file\'s existing conventions: read it first to find the local holding the latest ChatResponse, the session-id local, and the API base / fetch (or API-client) pattern used for other authenticated calls (cookie credentials). Use those exact names/patterns; the plan\'s snippets are illustrative.',
        'No FE test infra — verify with tsc + eslint on the touched files only.',
      ],
      verify:
        'cd ${PROJECT}/frontend && npx tsc --noEmit 2>&1 | tail -5 && npx eslint src/components/chat/PhaseIndicator.tsx src/pages/Chat.tsx src/types/chat.ts 2>&1 | tail -10',
    },
    {
      id: 7,
      name: 'docs',
      role: 'Maintainer updating current docs + the in-app Help page',
      taskText: 'Plan Task 10: document the wired held-set feature in chatbot-api.md, architecture.md, Help.tsx §16, and the testing guide',
      steps: [
        `Implement Plan Task 10 from ${planPath} exactly. chatbot-api.md: three-intent model + $previous_results scoping + metadata.active_subgroup {defining_query,count} + phase semantics + DELETE /sessions/{id}/subgroup. architecture.md: active_subgroup now wired + load path + scripts/chat/subgroup_policy.py. Set Last verified: 2026-06-13 in both headers.`,
        'Help.tsx §16: tighten the follow-up claim to "scoped to exactly these records" in humanities-scholar plain language (<bdi> any Hebrew). docs/testing guide: add the search -> chip -> explore-keeps -> refine-narrows -> "Search all"-clears manual scenario.',
        'After editing Help.tsx run `cd frontend && npx tsc --noEmit` to confirm no TS break.',
      ],
      verify:
        'cd ${PROJECT}/frontend && npx tsc --noEmit 2>&1 | tail -3 && cd ${PROJECT} && grep -q "active_subgroup" docs/current/chatbot-api.md && grep -q "2026-06-13" docs/current/architecture.md && echo DOCS_OK',
    },
  ];

  const completed = [];
  for (const task of tasks) {
    // Allow ${PROJECT} substitution inside verify commands.
    task.verify = task.verify.split('${PROJECT}').join(projectRoot);
    const result = await runTaskWithVerification(ctx, task, { projectRoot, branch, planPath });
    completed.push(result);
    if (!result.verified) {
      return { success: false, failedAt: task.name, completed, detail: result.lastOutput };
    }
  }

  // ---- Full verification gate (Plan Task 11) ----
  const gateVerify =
    'PYTHONPATH=. poetry run pytest -q -m "not integration" 2>&1 | tail -4 && ' +
    'PYTHONPATH=. poetry run pytest -q -m integration 2>&1 | tail -3 && ' +
    'poetry run ruff check scripts/chat/subgroup_policy.py scripts/chat/models.py scripts/chat/session_store.py scripts/chat/interpreter.py scripts/chat/narrator.py app/api/main.py 2>&1 | tail -4 && ' +
    'cd frontend && npx tsc --noEmit 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, {
    name: 'full-suite-gate',
    command: `cd ${projectRoot} && ${gateVerify}`,
  });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate',
      role: 'Senior developer fixing a regression caught by the full-suite gate',
      taskText: 'Full-suite / ruff / tsc gate failed — diagnose from the failure tail and fix, staying within the active_subgroup feature scope', steps: [
        'Only touch files this feature created/modified. If a failure is in a pre-existing/unrelated file, confirm via git and leave it (note it).',
      ],
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
      `git merge --no-ff ${branch} -m "Merge ${branch}: wire active_subgroup held-set scoping (#60 part 2)" ` +
      `-m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) {
    return { success: false, failedAt: 'merge-to-dev', completed, detail: merge.output };
  }

  // ---- Issue update ----
  const issues = {
    id: 8,
    name: 'issue-update',
    role: 'Maintainer recording the batch in the issue tracker',
    taskText: 'Update issue #60 with evidence that part 2 (held-set wiring) is complete',
    steps: [
      'Run git log --oneline -12 on dev for SHAs.',
      'Comment on #60: part 2 done — held set now written after retrieve turns and loaded onto ChatSession; deterministic lifecycle in scripts/chat/subgroup_policy.py (new-search/refine replace, explore unchanged); reuses the existing $previous_results scope keyword; reset via DELETE /sessions/{id}/subgroup; interpreter three-intent prompt; narrator disclosure; frontend "Exploring N <query> · Search all" chip. List the merge SHAs and the new test files (test_subgroup_policy.py, test_subgroup_reset.py).',
      'Close #60 ONLY if its scope is fully addressed by parts 1 + 2. If any part-2 sub-item turned out partial or deferred, comment honestly and leave it open.',
      'Note in the comment that deploy to prod is pending user decision (this run did not deploy).',
    ],
    verify: 'gh issue view 60 --json comments -q ".comments | length" | grep -qE "[0-9]+" && echo ISSUE_OK',
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

const implementTask = defineTask('implement-subgroup-task', (args, taskCtx) => ({
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
      task: 'Summarize the active_subgroup held-set wiring batch',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -14; PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py tests/api/test_subgroup_reset.py -q 2>&1 | tail -3',
        'Report (markdown): the five touchpoints delivered (write, load+attach, scope reuse, interpreter, surface+reset), the new files (scripts/chat/subgroup_policy.py + the two new test files), the merge SHAs, #60 status, and the explicit note that deploy to prod is pending the user decision (not done in this run). Flag any deferred/partial sub-item honestly.',
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
