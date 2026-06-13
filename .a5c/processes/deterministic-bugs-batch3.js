/**
 * @process deterministic-bugs-batch3
 * @description Fix all remaining deterministic code bugs from the gold-suite +
 *   seam audit: #51 evidence quality, #50 publisher substring noise, #57
 *   unknown-aggregate silent empty, #59 shape contracts, #47 expansion
 *   transparency. TDD per task (deterministic, no live LLM), full-suite gate,
 *   merge to dev, close issues.
 * @inputs { projectRoot: string, branch: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;

const COMMON = [
  'TDD is mandatory: write the failing test first, run it to watch it fail, implement minimally, watch it pass, then ruff-check touched files and commit specific files (never git add -A; never push from inside a task).',
  'Run Python tests with `PYTHONPATH=. poetry run pytest` (plain pytest/python are not on PATH). Do NOT use `rg` in any shell you run (it is a shell function here, unavailable in subshells) — use grep.',
  'No paid LLM API calls — ALL tests must be deterministic (construct filters/plans/rows directly, or use a tmp fixture DB; never call the interpreter/LLM). Read DBs read-only.',
  'SECRETS: never read or echo .env files or token values.',
  'Research before editing: read the issue (gh issue view N), the cited files, and the audit notes under audits/2026-06-12-seam-audit/ first. Match surrounding code style.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'fix/deterministic-bugs-batch3',
  } = inputs;

  const setup = await ctx.task(shellTask, {
    name: 'setup-branch',
    command:
      `cd ${projectRoot} && ` +
      `(git rev-parse --verify ${branch} >/dev/null 2>&1 && git checkout ${branch} ` +
      `|| git checkout -b ${branch} dev) && git branch --show-current`,
  });
  if (setup.exitCode !== 0) return { success: false, failedAt: 'setup-branch', detail: setup.output };

  const tasks = [
    {
      id: 1,
      name: 'evidence-quality-51',
      role: 'Senior Python developer fixing the M5 evidence-extraction quality cluster',
      taskText: 'Issue #51: fix the evidence-quality cluster in extract_evidence_for_filter',
      steps: [
        'Read `gh issue view 51` and scripts/query/execute.py extract_evidence_for_filter, plus how source_tags / source columns are stored (a real imprint row carries source_tags JSON like ["260$b"] or ["264$a"]; verify against the live DB read-only).',
        'Fix four things: (a) IMPRINT-derived evidence (publisher/place/date) must cite the ACTUAL subfield and tag from the row (e.g. db.imprints.place_norm (marc:264$a) / publisher_norm (marc:264$b) / date (marc:264$c)), read from the row’s source_tags rather than hard-coding "marc:260"; (b) LANGUAGE evidence source must be a clean string (e.g. "db.languages.code (marc:008)" or "marc:041$a"), never a serialized list like marc:["041$a"]; (c) add real extractor branches for COUNTRY and PHYSICAL_DESC (today they fall through to {value:"unknown", source:"unknown"}); (d) FTS matches (TITLE/SUBJECT via FTS5) must not yield Evidence.value=null — re-read the matched value from the base table so value is populated.',
        'TDD in tests/scripts/query/test_execute.py (extend its FakeRow style): one test per fix — assert the correct subfield/tag string, the clean language source, the new country/physical_desc branches, and a non-null FTS value. Keep deterministic (no LLM).',
        'Do not regress the #43 agent-provenance fix (agent evidence already cites marc:100[0]$a via provenance_json).',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/query/test_execute.py -q',
    },
    {
      id: 2,
      name: 'publisher-substring-50',
      role: 'Senior Python developer fixing publisher resolution precision',
      taskText: 'Issue #50: stop the resolve_publisher substring fallback from matching short tokens inside unrelated words',
      steps: [
        'Read `gh issue view 50` and the substring fallback in scripts/chat/executor.py _handle_resolve_publisher (the imprint_substring match path). The bug: a short Latin variant like "rom"/"ram" substring-matches inside "romănia", "jérôme", "lagerstroms".',
        'Fix: word-boundary-anchored matching and/or a minimum-length guard for short Latin variants (e.g. require >=4 chars OR a word-boundary hit) in the substring fallback. Preserve the Hebrew path (it correctly found "האלמנה והאחים ראם").',
        'TDD in tests/scripts/chat/test_executor.py (tmp fixture DB): assert a short Latin token does NOT match inside an unrelated word, a legitimate publisher substring still matches, and a Hebrew form still resolves. Deterministic.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py -q',
    },
    {
      id: 3,
      name: 'aggregate-unknown-57',
      role: 'Senior Python developer closing a silent-empty in aggregation',
      taskText: 'Issue #57 (remaining item): unknown aggregate field must not return a silent empty result',
      steps: [
        'Read `gh issue view 57` and _handle_aggregate in scripts/chat/executor.py: an unsupported aggregate field does `sql_template = field_map.get(normalized_field); if not sql_template: return AggregationResult(field, facets=[], total_records=0)` — a silent empty.',
        'Fix: instead of a silent empty, signal it clearly — return a step result with status "error"/an explicit unsupported-field marker (mirror how other handlers surface errors), so the narrator/user knows the aggregation field was unsupported rather than "0 results". Keep it from raising an unhandled exception.',
        'TDD: a test asserting an unknown aggregate field yields the explicit unsupported signal (not a silent empty AggregationResult). Put it in tests/scripts/chat/test_executor.py or tests/scripts/chat/test_aggregation.py (whichever already covers aggregate). Deterministic.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_aggregation.py -q',
    },
    {
      id: 4,
      name: 'shape-contracts-59',
      role: 'Senior Python developer fixing JSON-shape contract defects',
      taskText: 'Issue #59: active_subgroups load raises by construction; polymorphic filters_applied breaks the evidence audit',
      steps: [
        'Read `gh issue view 59` and audits/2026-06-12-seam-audit/cross-layer-seams.md (Seam C). Two defects:',
        'Defect A: the active_subgroups defensive load branch raises a ValidationError by construction (e.g. ActiveSubgroup.candidate_set required vs the nullable load path; session.active_subgroup never populated). Read scripts/chat/session_store.py get/set_active_subgroup + the ActiveSubgroup model in plan_models.py; make the load path not raise on the real stored shape (or on absence), returning None/empty cleanly.',
        'Defect B: RecordSet.filters_applied is polymorphic — retrieve steps store real filter dicts, sample steps store {strategy, n}. Any consumer that assumes filter dicts (the M5 evidence audit path / scripts/eval/run_diagnostic_suite.py _evidence_pass) breaks on sample steps. Make the consumer(s) robust: skip/guard non-filter entries (no "field" key) rather than crashing. Fix the production consumer if one exists; also harden scripts/eval/run_diagnostic_suite.py.',
        'TDD: a session-store test that a stored subgroup (and an absent one) loads without raising; a test that an evidence/audit consumer tolerates a sample-shaped filters_applied. Deterministic, no LLM.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_session_store.py tests/scripts/chat/test_executor.py -q',
    },
    {
      id: 5,
      name: 'expansion-transparency-47',
      role: 'Senior developer making interpreter-level concept expansion transparent',
      taskText: 'Issue #47: interpreter-level concept fan-out returns broadened results with relaxations=[] (silent broadening)',
      steps: [
        'Read `gh issue view 47`. The case: a query like "cartography" makes the interpreter emit several topical retrieve steps (subject geography, physical_desc maps, title atlas, ...) — broadened results, but each RecordSet.relaxations is empty, so the broadening is invisible (the executor-level ladder honesty mechanism does not cover interpreter-level fan-out).',
        'Fix (bounded, deterministic): when an execution plan contains multiple topical retrieve/sample steps clearly probing related terms for one conceptual query, surface that as a transparency note the narrator can show — e.g. the executor records a grounding/relaxation-style note ("explored related topics: geography, maps, atlas") when >1 topical retrieve step ran, OR add a structured flag the narrator must render. Pick the smallest approach that makes the broadening visible in the ExecutionResult/grounding. Do NOT call the LLM in tests.',
        'TDD in tests/scripts/chat/test_executor.py (or test_plan_models / a narrator-grounding test): construct a plan with multiple topical retrieve steps, run execute_plan against a tmp fixture DB, and assert the broadening is recorded/visible (a note listing the explored terms), not silent. Deterministic.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py -q',
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
    'poetry run ruff check scripts/query/execute.py scripts/chat/executor.py scripts/chat/session_store.py 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, { name: 'full-suite-gate', command: `cd ${projectRoot} && ${gateVerify}` });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate', role: 'Senior developer fixing a regression',
      taskText: 'Full-suite gate failed — diagnose and fix', steps: [], verify: gateVerify,
    }, gate.output, { projectRoot, branch });
    if (!fixed.verified) return { success: false, failedAt: 'full-suite-gate', completed, detail: fixed.lastOutput };
  }

  const merge = await ctx.task(shellTask, {
    name: 'merge-to-dev',
    command:
      `cd ${projectRoot} && git checkout dev && ` +
      `git merge --no-ff ${branch} -m "Merge ${branch}: deterministic bug batch (#51 #50 #57 #59 #47)" ` +
      `-m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) return { success: false, failedAt: 'merge-to-dev', completed, detail: merge.output };

  const issues = {
    id: 6,
    name: 'issue-updates',
    role: 'Maintainer closing the batch in the issue tracker',
    taskText: 'Close the fully-fixed issues with evidence; comment honestly on any partially-fixed one',
    steps: [
      'Run git log --oneline -8 on dev for SHAs.',
      'For EACH of #51 #50 #57 #59 #47: if its tests fully cover the fix, gh issue close <n> with a comment (what changed, file:line, commit SHA, test name). If a fix is only partial, comment honestly with what is done + what remains and leave it OPEN.',
      'Do not close anything not actually fixed.',
    ],
    verify: 'true',
  };
  const issuesResult = await runTaskWithVerification(ctx, issues, { projectRoot, branch: 'dev' });
  completed.push(issuesResult);

  const report = await ctx.task(reportTask, { projectRoot, completed });
  return { success: true, tasksCompleted: completed.map((c) => c.name), report };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(implementTask, { ...env, ...task });
  let verify = await ctx.task(shellTask, { name: `verify-${task.name}`, command: `cd ${env.projectRoot} && ${task.verify}` });
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
    const verify = await ctx.task(shellTask, { name: `verify-${task.name}-fix${attempt}`, command: `cd ${env.projectRoot} && ${task.verify}` });
    if (verify.exitCode === 0) return { verified: true };
    lastOutput = verify.output;
  }
  return { verified: false, lastOutput };
}

const implementTask = defineTask('implement-batch3-task', (args, taskCtx) => ({
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
  io: { inputJsonPath: `tasks/${taskCtx.effectId}/input.json`, outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
  labels: ['implement', args.name],
}));

const shellTask = defineTask('shell-step', (args, taskCtx) => ({
  kind: 'shell',
  title: args.name,
  shell: { command: args.command, timeout: 600000, outputPath: `tasks/${taskCtx.effectId}/output.json` },
  io: { inputJsonPath: `tasks/${taskCtx.effectId}/input.json`, outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
  labels: ['shell', args.name],
}));

const reportTask = defineTask('final-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Final batch report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Tech lead writing a completion report',
      task: 'Summarize the deterministic-bug batch',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -10 on dev.',
        'Report per issue (#51 #50 #57 #59 #47): fixed/partial, what changed, and which issues were closed vs left open. Note any deferred (data/decision) issues are out of scope for this batch.',
        'Return JSON: { report: "<markdown>", allFixed: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report'] },
  },
  io: { inputJsonPath: `tasks/${taskCtx.effectId}/input.json`, outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
  labels: ['report'],
}));
