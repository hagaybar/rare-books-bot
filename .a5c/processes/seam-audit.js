/**
 * @process seam-audit
 * @description Targeted cross-layer seam audit: silent-fallback inventory,
 *   cross-layer reference verification, derived-artifact invariants (run as
 *   SQL against the live DB), synthesized into a contract register at
 *   audits/2026-06-12-seam-audit/, with consolidated GitHub issues
 *   (label seam-audit-2026-06-12) and a final commit to dev.
 * @inputs { projectRoot: string }
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

const AUDIT_DIR = 'audits/2026-06-12-seam-audit';
const MAX_FIX_ATTEMPTS = 2;

const COMMON_RULES = [
  'Working directory: PROJECT_ROOT (passed in context). Stay on branch dev; do NOT create branches; do NOT commit (a later step commits).',
  'Read-only on databases: SELECT/PRAGMA only, always via `sqlite3` CLI with bounded output (| head -n 50).',
  'No paid LLM API calls. No network except GitHub via `gh` where the task says so.',
  'SECRETS: never read or echo .env files, shell rc files, or token values.',
  'Bounded reading: rg first, then small excerpts (sed -n). Never read large files in full.',
  'Cite every claim as file:line. If you cannot verify a claim, mark it UNVERIFIED — never guess.',
];

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  ctx.log('info', 'Seam audit: fallbacks, cross-layer refs, derived invariants');

  const mkdir = await ctx.task(shellTask, {
    name: 'mk-audit-dir',
    command: `cd ${projectRoot} && mkdir -p ${AUDIT_DIR} && git branch --show-current`,
  });
  if (mkdir.exitCode !== 0) {
    return { success: false, failedAt: 'mk-audit-dir', detail: mkdir.output };
  }

  const sweeps = [
    {
      id: 1,
      name: 'fallback-inventory',
      outFile: `${AUDIT_DIR}/fallback-inventory.md`,
      role: 'Defensive-code auditor hunting silent failure conversion',
      taskText: 'Inventory EVERY silent-fallback pattern in scripts/ and app/',
      steps: [
        `Sweep with rg for the fallback shapes: 'except' blocks that swallow into defaults ("except" followed by assignment/pass/continue/return-default), '.get(' with non-None defaults on cross-module data, 'or \\'\\'' / 'or []' coercions on loaded data, try/except around json.loads. Use: rg -n "except" scripts/ app/ -A 2 | head -n 200 (paginate as needed) plus targeted patterns.`,
        'For EACH hit decide: (a) what failure does it hide, (b) what does the user see instead (the "plausible output"), (c) is it logged/surfaced anywhere, (d) risk class HIGH (silently changes results/evidence), MEDIUM (degrades quality visibly), LOW (cosmetic/intentional).',
        `Write ${AUDIT_DIR}/fallback-inventory.md: a table (file:line | pattern | failure hidden | user-visible effect | logged? | risk) sorted by risk, then a "Top HIGH risks" section with 1-paragraph analysis each. Include total counts per risk class. Start the file with the header line '# Silent-Fallback Inventory' and include the marker line 'SWEEP-COMPLETE' at the end.`,
        'Known fixed examples for calibration (do not re-report as new): marc:unknown agent provenance (#43, fixed), agent_aliases comma-split (#53, fixed).',
      ],
      verify: `test -s ${AUDIT_DIR}/fallback-inventory.md && grep -q "SWEEP-COMPLETE" ${AUDIT_DIR}/fallback-inventory.md`,
    },
    {
      id: 2,
      name: 'cross-layer-seams',
      outFile: `${AUDIT_DIR}/cross-layer-seams.md`,
      role: 'Contract auditor verifying producer/consumer references across modules',
      taskText: 'Verify every cross-module reference against the actual producer (schema, shapes, enums)',
      steps: [
        'Seam class A — DB columns: every row["..."] / SELECT column referenced in scripts/query/execute.py, scripts/query/db_adapter.py, scripts/chat/executor.py, scripts/network/ must exist in the actual schema (PRAGMA table_info via sqlite3 on data/index/bibliographic.db and data/chat/sessions.db, and scripts/marc/m3_contract.py). Report any reference to a non-existent or differently-named column.',
        'Seam class B — op support matrix: enumerate FilterField x FilterOp combinations the interpreter prompt/conversion can emit (scripts/chat/interpreter.py incl. the year EQUALS coercion) versus what build_where_clause supports per field (scripts/query/db_adapter.py raise sites). Produce the full matrix with each cell: supported / coerced / RAISES / never-emitted. Note #44 fixed year EQUALS; check ALL other fields ops (e.g. RANGE on non-year fields, IN on year, negate on CONTAINS-FTS...).',
        'Seam class C — JSON shapes: fields stored as JSON in one module and parsed in another (provenance_json, query_plan, candidate_set, sources, person_info, context, metadata...). For each: producer file:line, consumer file:line, shape assumed vs shape stored (verify against a real row via sqlite3). Report drift.',
        `Write ${AUDIT_DIR}/cross-layer-seams.md with one section per seam class, a finding table (seam | producer | consumer | status OK/DRIFT/RAISES | evidence), and end with marker 'SWEEP-COMPLETE'.`,
      ],
      verify: `test -s ${AUDIT_DIR}/cross-layer-seams.md && grep -q "SWEEP-COMPLETE" ${AUDIT_DIR}/cross-layer-seams.md`,
    },
    {
      id: 3,
      name: 'derived-invariants',
      outFile: `${AUDIT_DIR}/derived-invariants.md`,
      role: 'Data-integrity auditor writing and executing derivation invariants',
      taskText: 'Enumerate every derived artifact, state its invariant, RUN it as SQL, report violations',
      steps: [
        'Enumerate derived artifacts: agent_aliases, agent_authorities, publisher_variants, publisher_authorities, network_* tables, titles_fts, subjects_fts, subjects.value_he, authority_enrichment-derived columns, and any others found in scripts/marc/m3_contract.py / scripts/network/ / scripts/qa/fixes/.',
        'For EACH: state the derivation invariant in one sentence (what must hold between it and its source), express it as a single SELECT returning a violation count, RUN it via sqlite3 against data/index/bibliographic.db (READ-ONLY), and record count + verdict OK (0) / VIOLATION (n>0) with up to 3 sample rows when violated.',
        'Include at minimum: every authority-linked agent_norm has an alias row; no alias is a comma-fragment of its authority\'s norms; every multi-record publisher_norm is variant-linked or is itself canonical; FTS rowcount parity with source tables; network node references resolve to existing authorities; value_he coverage matches the documented 78.4% +/- drift.',
        `Write ${AUDIT_DIR}/derived-invariants.md: table (artifact | invariant | SQL | count | verdict), violations detailed below, and a final "Proposed test encodings" list mapping each invariant to a pytest one-liner. End with marker 'SWEEP-COMPLETE'.`,
      ],
      verify: `test -s ${AUDIT_DIR}/derived-invariants.md && grep -q "SWEEP-COMPLETE" ${AUDIT_DIR}/derived-invariants.md && grep -Eq "OK|VIOLATION" ${AUDIT_DIR}/derived-invariants.md`,
    },
  ];

  const completed = [];
  for (const sweep of sweeps) {
    const result = await runTaskWithVerification(ctx, sweep, { projectRoot });
    completed.push(result);
    if (!result.verified) {
      return { success: false, failedAt: sweep.name, completed, detail: result.lastOutput };
    }
  }

  // Synthesis: contract register
  const synth = {
    id: 4,
    name: 'contract-register',
    outFile: `${AUDIT_DIR}/contract-register.md`,
    role: 'Tech lead synthesizing audit sweeps into an enforceable contract register',
    taskText: 'Synthesize the three sweep files into the contract register',
    steps: [
      `Read ${AUDIT_DIR}/fallback-inventory.md, ${AUDIT_DIR}/cross-layer-seams.md, ${AUDIT_DIR}/derived-invariants.md in full.`,
      `Write ${AUDIT_DIR}/contract-register.md: (1) executive summary (counts of seams audited, OK vs findings, top 5 risks); (2) the REGISTER — one line per contract: id (SEAM-NN) | seam | invariant | currently enforced by (test/gate/nothing) | status OK/FINDING | finding ref; (3) "Findings" section grouping confirmed defects (deduped against known issues #43-#54 — mark which are already covered by an existing open issue); (4) "Proposed enforcement" — prioritized list of test encodings (invariant battery, contract tests, metamorphic tests) with effort estimates S/M/L. End with marker 'REGISTER-COMPLETE'.`,
    ],
    verify: `test -s ${AUDIT_DIR}/contract-register.md && grep -q "REGISTER-COMPLETE" ${AUDIT_DIR}/contract-register.md`,
  };
  const synthResult = await runTaskWithVerification(ctx, synth, { projectRoot });
  completed.push(synthResult);
  if (!synthResult.verified) {
    return { success: false, failedAt: synth.name, completed, detail: synthResult.lastOutput };
  }

  // Issues: open new / update existing
  const issues = {
    id: 5,
    name: 'github-issues',
    outFile: `${AUDIT_DIR}/issues-opened.md`,
    role: 'Maintainer triaging audit findings into the issue tracker',
    taskText: 'Open consolidated GitHub issues for NEW confirmed findings; comment on existing issues where findings add evidence',
    steps: [
      `Read ${AUDIT_DIR}/contract-register.md Findings section. Check existing open issues first: gh issue list --state open --limit 40 --json number,title,labels.`,
      'For findings that overlap existing issues (#45 #47 #48 #49 #50 #51 #52 #54): add ONE consolidated comment per issue with the new evidence (file:line + invariant SQL where applicable) — do not open duplicates.',
      'For NEW confirmed defects: open AT MOST 6 consolidated issues (group by subsystem, not one-per-finding), each labeled "seam-audit-2026-06-12" plus "bug" (confirmed code/data defect) or "question" (design decision needed). Body: symptom, evidence (file:line / SQL count), impact, proposed enforcement. Title prefix not needed.',
      'UNVERIFIED items from the sweeps must NOT become issues — list them in the output file under "Not filed (unverified)".',
      `Write ${AUDIT_DIR}/issues-opened.md: list of created issue URLs with one-line summaries, list of updated issues with what was added, and the not-filed list. End with marker 'ISSUES-COMPLETE'.`,
    ],
    verify: `test -s ${AUDIT_DIR}/issues-opened.md && grep -q "ISSUES-COMPLETE" ${AUDIT_DIR}/issues-opened.md`,
  };
  const issuesResult = await runTaskWithVerification(ctx, issues, { projectRoot });
  completed.push(issuesResult);
  if (!issuesResult.verified) {
    return { success: false, failedAt: issues.name, completed, detail: issuesResult.lastOutput };
  }

  // Commit the audit directory on dev
  const commit = await ctx.task(shellTask, {
    name: 'commit-audit',
    command:
      `cd ${projectRoot} && git add ${AUDIT_DIR} && ` +
      `git commit -m "audit: cross-layer seam audit - contract register + findings (seam-audit-2026-06-12)" ` +
      `-m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>" && git push origin dev 2>&1 | tail -1`,
  });
  if (commit.exitCode !== 0) {
    return { success: false, failedAt: 'commit-audit', completed, detail: commit.output };
  }

  const report = await ctx.task(reportTask, { projectRoot, completed });
  return { success: true, tasksCompleted: completed.map((c) => c.name), report };
}

async function runTaskWithVerification(ctx, task, env) {
  await ctx.task(auditTask, { ...env, ...task });
  let verify = await ctx.task(shellTask, {
    name: `verify-${task.name}`,
    command: `cd ${env.projectRoot} && ${task.verify}`,
  });
  if (verify.exitCode === 0) {
    return { name: task.name, verified: true };
  }
  let lastOutput = verify.output;
  for (let attempt = 1; attempt <= MAX_FIX_ATTEMPTS; attempt++) {
    await ctx.task(auditTask, {
      ...env, ...task, attempt,
      taskText: `${task.taskText} — previous attempt failed verification (${task.verify}); complete the missing parts`,
    });
    verify = await ctx.task(shellTask, {
      name: `verify-${task.name}-fix${attempt}`,
      command: `cd ${env.projectRoot} && ${task.verify}`,
    });
    if (verify.exitCode === 0) {
      return { name: task.name, verified: true };
    }
    lastOutput = verify.output;
  }
  return { name: task.name, verified: false, lastOutput };
}

const auditTask = defineTask('audit-sweep', (args, taskCtx) => ({
  kind: 'agent',
  title: `Sweep ${args.id}: ${args.name}${args.attempt ? ` (retry ${args.attempt})` : ''}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: args.role,
      task: args.taskText,
      context: { projectRoot: args.projectRoot, outFile: args.outFile },
      instructions: [
        ...COMMON_RULES.map((r) => r.replace('PROJECT_ROOT', args.projectRoot)),
        ...args.steps,
        'Execute fully and return only the summary JSON, not a plan.',
        'Return JSON: { taskName, status: "done"|"blocked", outFile, findingsCount, notes }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['taskName', 'status'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['audit', args.name],
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
  title: 'Final audit report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Tech lead writing the audit completion report',
      task: 'Summarize the seam audit for the user',
      context: { projectRoot: args.projectRoot, auditDir: AUDIT_DIR, completed: args.completed },
      instructions: [
        `Working directory: ${args.projectRoot}. Read-only.`,
        `Read ${AUDIT_DIR}/contract-register.md (executive summary + findings) and ${AUDIT_DIR}/issues-opened.md.`,
        'Return JSON: { report: "<concise markdown: seams audited, findings by severity, issues opened/updated with URLs, top 3 recommended enforcement steps>", issuesOpened: [], issuesUpdated: [] }',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: { type: 'object', required: ['report'] },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
  labels: ['report'],
}));
