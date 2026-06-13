/**
 * @process semantic-subject-search
 * @description Phase 1 of #63: concept->real-headings semantic subject resolver via
 *   a local multilingual ONNX embedding model (e5-small), wired into the held-set
 *   concept-count so "how many are in philosophy?" returns 11 (cited headings) not 0.
 *   Executes docs/superpowers/plans/2026-06-13-semantic-subject-search.md. Artifact
 *   build (ONNX export + heading embedding) runs as orchestrator shell steps; code is
 *   TDD agent tasks (deterministic, fake-embedder in CI). Merge to dev; deploy is the
 *   user's separate step (model artifact must ship in the build context + DB).
 * @inputs { projectRoot: string, branch: string, planPath: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const MAX_FIX_ATTEMPTS = 2;
const PLAN = 'docs/superpowers/plans/2026-06-13-semantic-subject-search.md';

const COMMON = [
  `The plan is ${PLAN} and the spec is docs/superpowers/specs/2026-06-13-semantic-subject-search-design.md. READ your task's plan section FIRST — it has exact code, signatures, and test code. The validation gate already PASSED (e5-small, threshold ~0.84, evidence transparency required).`,
  'TDD mandatory: failing test first -> watch fail -> minimal impl -> watch pass -> ruff-check touched files -> commit specific files (never git add -A; never push).',
  'Run Python via `PYTHONPATH=. poetry run python ...` / `PYTHONPATH=. poetry run pytest ...` (bare python/pytest are NOT on PATH).',
  'No paid LLM calls. ALL unit tests are deterministic and use a FAKE embedder / fixed vectors — NEVER load the real ONNX model or download anything in a test. The real model is exercised only by the orchestrator shell steps + manual prod validation.',
  'Embeddings expand concept->headings ONLY; records still match EXACTLY on resolved headings (evidence = matched MARC headings). Keep that contract.',
  'No bibliographic.db schema-destruction; the subject_embeddings table is additive. SECRETS: never read/echo .env or tokens. Research before editing — read files (esp. the resolve_agent/resolve_publisher pattern in executor.py) first.',
];

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    branch = 'feat/semantic-subject-search',
    planPath = PLAN,
  } = inputs;

  const setup = await ctx.task(shellTask, {
    name: 'setup-branch',
    command:
      `cd ${projectRoot} && ` +
      `(git rev-parse --verify ${branch} >/dev/null 2>&1 && git checkout ${branch} ` +
      `|| git checkout -b ${branch} dev) && git branch --show-current`,
  });
  if (setup.exitCode !== 0) return { success: false, failedAt: 'setup-branch', detail: setup.output };

  // --- Runtime deps (orchestrator shell) ---
  const deps = await ctx.task(shellTask, {
    name: 'add-runtime-deps',
    command:
      `cd ${projectRoot} && poetry add onnxruntime tokenizers 2>&1 | tail -5 && ` +
      `PYTHONPATH=. poetry run python -c "import onnxruntime, tokenizers; print('deps ok')"`,
  });
  if (deps.exitCode !== 0) return { success: false, failedAt: 'add-runtime-deps', detail: deps.output };

  // --- Task 1: scaffolding (agent) ---
  const t1 = {
    id: 1, name: 'scaffolding',
    role: 'Senior Python engineer scaffolding the embedding pipeline + plan models',
    taskText: 'Plan Task 1 (code only): onnx_embedder.py, export + embed scripts, plan_models additions',
    steps: [
      `Implement the CODE for Plan Task 1 from ${planPath}: scripts/chat/onnx_embedder.py (OnnxEmbedder: onnxruntime + tokenizers, mean-pool + L2-normalize, e5 "query:"/"passage:" prefixes), scripts/index/export_embed_model.py, scripts/index/embed_subjects.py (creates subject_embeddings(heading_value,lang,dim,model_id,vector BLOB), embeds distinct subjects.value + value_he, idempotent by model_id).`,
      'In scripts/chat/plan_models.py add: StepAction.RESOLVE_SUBJECT_CONCEPT="resolve_subject_concept"; ResolveSubjectConceptParams(concept:str, top_k:int=40); a ResolvedHeadings step-output type (headings:list[str], matches:list[dict]). Wire ResolveSubjectConceptParams into the StepParams union and any params-parsing (_convert_llm_plan) like the other actions.',
      'Do NOT run the model here (that is the orchestrator build step). Verify only that everything imports.',
    ],
    verify: 'PYTHONPATH=. poetry run python -c "import scripts.chat.onnx_embedder; import scripts.index.embed_subjects; import scripts.index.export_embed_model; from scripts.chat.plan_models import StepAction, ResolveSubjectConceptParams; print(StepAction.RESOLVE_SUBJECT_CONCEPT)"',
  };
  const c = [];
  let r = await runTaskWithVerification(ctx, t1, { projectRoot, branch, planPath });
  c.push(r);
  if (!r.verified) return { success: false, failedAt: t1.name, completed: c, detail: r.lastOutput };

  // --- Task 2: build + validate the artifact (orchestrator shell) ---
  const build = await ctx.task(shellTask, {
    name: 'build-artifact',
    command:
      `cd ${projectRoot} && bash scripts/index/_build_subject_embeddings.sh 2>&1 | tail -20 && ` +
      `sqlite3 data/index/bibliographic.db "SELECT COUNT(*) FROM subject_embeddings"`,
  });
  if (build.exitCode !== 0) {
    return { success: false, failedAt: 'build-artifact', completed: c,
             detail: 'Artifact build failed — orchestrator must create/run scripts/index/_build_subject_embeddings.sh (scratch venv: optimum export e5-small -> data/models/e5-small-onnx; run embed_subjects -> subject_embeddings; assert OnnxEmbedder vectors ~match sentence-transformers and the resolver recovers the 11 philosophy records). ' + build.output };
  }

  // --- Tasks 3-7: integration code (agents) ---
  const codeTasks = [
    {
      id: 3, name: 'resolver',
      role: 'Senior Python engineer building the deterministic concept->headings resolver',
      taskText: 'Plan Task 2: subject_concept_resolver.py + fake-embedder unit tests',
      steps: [`Implement Plan Task 2 from ${planPath} verbatim: scripts/chat/subject_concept_resolver.py (SubjectConceptResolver + HeadingMatch, cosine>=threshold, top_k, optional cache) and tests/scripts/chat/test_subject_concept_resolver.py using the FakeEmbedder (no real model).`],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subject_concept_resolver.py -q 2>&1 | tail -5 && poetry run ruff check scripts/chat/subject_concept_resolver.py 2>&1 | tail -2',
    },
    {
      id: 4, name: 'executor-action',
      role: 'Senior Python engineer adding the resolve_subject_concept executor action',
      taskText: 'Plan Task 3: _handle_resolve_subject_concept + scoped retrieve on resolved headings + matched-headings evidence',
      steps: [
        `Implement Plan Task 3 from ${planPath}. Read the existing resolve_agent/resolve_publisher handlers in scripts/chat/executor.py and mirror them: _handle_resolve_subject_concept calls the resolver (injected for tests), returns ResolvedHeadings with per-heading record_count; a retrieve referencing $step_N matches subjects.value IN headings, scope honored; matched headings flow into grounding for narrator citation.`,
        'TDD in tests/scripts/chat/test_executor.py over a tmp DB with a FAKE/injected resolver returning known headings; assert correct count + matched-heading evidence + held set unchanged.',
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_executor.py -q 2>&1 | tail -6',
    },
    {
      id: 5, name: 'subgroup-gating',
      role: 'Senior Python engineer gating held-set replacement on intent',
      taskText: 'Plan Task 4: explore-in-set never replaces the held set; refine/new-search do',
      steps: [`Implement Plan Task 4 from ${planPath}: build_subgroup_update gates replacement on plan.intents — explore-in-set returns None (held set unchanged) even with a retrieve; refine-in-set / new-search replace (keep the #62 full held_record_ids source). TDD in tests/scripts/chat/test_subgroup_policy.py.`],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subgroup_policy.py -q 2>&1 | tail -5',
    },
    {
      id: 6, name: 'interpreter-narrator',
      role: 'Senior engineer routing concept-counts + narrator evidence/honesty',
      taskText: 'Plan Tasks 5 & 6: interpreter routes concept-count -> resolve_subject_concept (explore); narrator cites matched headings, never fabricates zero',
      steps: [
        `Implement Plan Task 5 from ${planPath}: interpreter prompt routes "how many are in <topical concept>?" over a held set to [resolve_subject_concept(concept) -> retrieve(subject IN $step) scope=$previous_results], intent explore-in-set; "what subjects?" -> aggregate; "only the <concept> ones" -> refine. Few-shot + prompt-discipline test asserting the resolve_subject_concept keyword/rule.`,
        `Implement Plan Task 6: narrator.py — when the turn used resolve_subject_concept, the prompt cites the matched headings ("counted via: ...") and MUST NOT assert a fabricated zero (disclose threshold-miss instead). Prompt-discipline test.`,
      ],
      verify: 'PYTHONPATH=. poetry run pytest tests/scripts/chat/test_interpreter.py tests/scripts/chat/test_narrator.py -q 2>&1 | tail -6',
    },
    {
      id: 7, name: 'runtime-docker-docs',
      role: 'Senior engineer wiring runtime load + Docker + docs',
      taskText: 'Plan Task 7 + docs: load_subject_resolver factory, app startup load, Dockerfile onnxruntime+model COPY, docs + CLAUDE.md exception',
      steps: [
        `Implement Plan Task 7 from ${planPath}: a load_subject_resolver(db_path, model_dir) factory (headings+vectors from subject_embeddings + OnnxEmbedder + SubjectConceptResolver with a JSON cache at data/normalization/concept_maps/semantic_subject_cache.json), loaded once at app startup (lazy singleton); fail loud if subject_embeddings empty (CLAUDE.md rule).`,
        'Dockerfile: ensure onnxruntime installs (aarch64) and COPY data/models/e5-small-onnx into the image. Confirm `PYTHONPATH=. poetry run python -c "import app.api.main"` exits 0.',
        'Docs: docs/current/chatbot-api.md, architecture.md, ingestion-pipeline.md (embed step), and CLAUDE.md (record the scoped embeddings exception: concept->heading expansion only; record match stays exact/evidential). Last verified: 2026-06-13.',
      ],
      verify: 'cd ${PROJECT} && PYTHONPATH=. poetry run python -c "import app.api.main" && echo IMPORT_OK && grep -q "resolve_subject_concept\\|embedding" docs/current/chatbot-api.md && grep -qi "embedding" CLAUDE.md && echo DOCS_OK',
    },
  ];
  for (const t of codeTasks) {
    t.verify = t.verify.split('${PROJECT}').join(projectRoot);
    r = await runTaskWithVerification(ctx, t, { projectRoot, branch, planPath });
    c.push(r);
    if (!r.verified) return { success: false, failedAt: t.name, completed: c, detail: r.lastOutput };
  }

  // --- Gate (orchestrator shell) ---
  const gateVerify =
    'PYTHONPATH=. poetry run pytest -q -m "not integration" 2>&1 | tail -4 && ' +
    'PYTHONPATH=. poetry run pytest -q -m integration 2>&1 | tail -3 && ' +
    'poetry run ruff check scripts/chat/subject_concept_resolver.py scripts/chat/onnx_embedder.py scripts/chat/executor.py scripts/chat/subgroup_policy.py scripts/chat/interpreter.py scripts/chat/narrator.py app/api/main.py 2>&1 | tail -4 && ' +
    'cd frontend && npx tsc --noEmit 2>&1 | tail -3';
  const gate = await ctx.task(shellTask, { name: 'full-suite-gate', command: `cd ${projectRoot} && ${gateVerify}` });
  if (gate.exitCode !== 0) {
    const fixed = await fixAndReverify(ctx, {
      id: 'gate', name: 'full-suite-gate', role: 'Senior dev fixing a gate regression',
      taskText: 'Gate failed — fix within the semantic-subject-search scope; pre-existing unrelated ruff errors are acceptable (confirm via git).',
      steps: [], verify: gateVerify,
    }, gate.output, { projectRoot, branch, planPath });
    if (!fixed.verified) return { success: false, failedAt: 'full-suite-gate', completed: c, detail: fixed.lastOutput };
  }

  // --- Merge to dev (orchestrator shell) ---
  const merge = await ctx.task(shellTask, {
    name: 'merge-to-dev',
    command:
      `cd ${projectRoot} && git checkout dev && ` +
      `git merge --no-ff ${branch} -m "Merge ${branch}: semantic subject search Phase 1 (#63)" ` +
      `-m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" && ` +
      `git push origin dev 2>&1 | tail -1 && git branch -d ${branch}`,
  });
  if (merge.exitCode !== 0) return { success: false, failedAt: 'merge-to-dev', completed: c, detail: merge.output };

  // --- Issue update (agent) ---
  const issue = {
    id: 8, name: 'issue-update',
    role: 'Maintainer recording progress on #63',
    taskText: 'Comment on #63: Phase 1 merged to dev; deploy + prod re-validation pending',
    steps: [
      'git log --oneline -16 on dev for SHAs + merge SHA.',
      'Comment on #63 (leave OPEN): the resolver + resolve_subject_concept + held-set gating + interpreter/narrator evidence shipped to dev (merge SHA); the subject_embeddings artifact built; full suite green. Note deploy (model in build context + DB ship) + re-running the Venice "how many in philosophy?" scenario are the remaining steps, pending the user.',
    ],
    verify: 'gh issue view 63 --json comments -q ".comments | length" | grep -qE "[1-9]" && echo OK',
  };
  r = await runTaskWithVerification(ctx, issue, { projectRoot, branch: 'dev', planPath });
  c.push(r);
  if (!r.verified) return { success: false, failedAt: issue.name, completed: c, detail: r.lastOutput };

  const report = await ctx.task(reportTask, { projectRoot, completed: c });
  return { success: true, tasksCompleted: c.map((x) => x.name), report };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(implementTask, { ...env, ...task });
  const v = await ctx.task(shellTask, { name: `verify-${task.name}`, command: `cd ${env.projectRoot} && ${task.verify}` });
  if (v.exitCode === 0) return { name: task.name, verified: true };
  const fixed = await fixAndReverify(ctx, task, v.output, env);
  return { name: task.name, verified: fixed.verified, lastOutput: fixed.lastOutput };
}

async function fixAndReverify(ctx, task, failureOutput, env) {
  let last = failureOutput;
  for (let a = 1; a <= MAX_FIX_ATTEMPTS; a++) {
    await ctx.task(implementTask, { ...env, ...task, attempt: a,
      taskText: `${task.taskText} — previous attempt failed verification; failure tail: ${String(last).slice(-2000)}` });
    const v = await ctx.task(shellTask, { name: `verify-${task.name}-fix${a}`, command: `cd ${env.projectRoot} && ${task.verify}` });
    if (v.exitCode === 0) return { verified: true };
    last = v.output;
  }
  return { verified: false, lastOutput: last };
}

const implementTask = defineTask('implement-sss-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.id}: ${args.name}${args.attempt ? ` (retry ${args.attempt})` : ''}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: args.role, task: args.taskText,
      context: { projectRoot: args.projectRoot, branch: args.branch, planPath: args.planPath },
      instructions: [
        `Working directory: ${args.projectRoot}. Branch ${args.branch} is checked out — do NOT switch branches.`,
        ...COMMON, ...args.steps,
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
  shell: { command: args.command, timeout: 900000, outputPath: `tasks/${taskCtx.effectId}/output.json` },
  io: { inputJsonPath: `tasks/${taskCtx.effectId}/input.json`, outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
  labels: ['shell', args.name],
}));

const reportTask = defineTask('final-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Final batch report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Tech lead writing a completion report', task: 'Summarize semantic subject search Phase 1',
      context: { projectRoot: args.projectRoot, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        'Run: git log --oneline -16; PYTHONPATH=. poetry run pytest tests/scripts/chat/test_subject_concept_resolver.py -q 2>&1 | tail -3',
        'Report (markdown): the resolver + resolve_subject_concept action + held-set explore-gating + interpreter/narrator evidence + the subject_embeddings artifact + Dockerfile/onnxruntime, merge SHA, #63 status, and that deploy + the Venice prod re-validation are PENDING the user (model artifact must ship in the build context + DB).',
        'Return JSON: { report: "<markdown>", allTestsPassed: boolean, deployPending: boolean }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report', 'allTestsPassed'] },
  },
  io: { inputJsonPath: `tasks/${taskCtx.effectId}/input.json`, outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
  labels: ['report'],
}));
