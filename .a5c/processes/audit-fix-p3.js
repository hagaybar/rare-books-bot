/**
 * @process audit-fix-p3
 * @description Fix P3 audit findings one at a time: frontend code splitting, N+1 queries, model consolidation, metadata.py refactor
 * @inputs { projectRoot: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // FIX 1: HEALTH-004 — Frontend code splitting for MapLibre
  // ============================================================================

  ctx.log('info', 'Fix 1: HEALTH-004 — Frontend code splitting');

  const codeSplit = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'HEALTH-004: Add frontend code splitting for MapLibre',
    description: `Add route-level code splitting to the React frontend so MapLibre GL (~1MB) is only loaded on the /network route.

CURRENT: Single JS bundle (~1.7MB). MapLibre loaded on every page even though only Network uses it.

CHANGES in frontend/src/pages/ and frontend/src/App.tsx:

1. In App.tsx (or wherever routes are defined), lazy-load the Network page:
   import { lazy, Suspense } from 'react';
   const Network = lazy(() => import('./pages/Network'));

   Then wrap the Network route in Suspense:
   <Route path="/network" element={
     <Suspense fallback={<div className="flex items-center justify-center h-full"><div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full" /></div>}>
       <Network />
     </Suspense>
   } />

2. Also lazy-load other heavy pages if they exist (Enrichment, Coverage, DB Explorer, etc).
   Keep Chat and Login as eager imports since they're the most used.

3. Do NOT change any component logic — only the import/route configuration.

Read App.tsx first to understand the current routing setup.

Verification: cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build`,
  });
  ctx.log('info', `Code split: ${JSON.stringify(codeSplit)}`);

  const verify1 = await ctx.task(shellTask, {
    projectRoot,
    phase: 'HEALTH-004 build verify',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | grep -E "dist/|chunks"`,
    timeout: 120000,
  });
  ctx.log('info', `Verify 1: ${JSON.stringify(verify1)}`);

  // ============================================================================
  // FIX 2: PERF-001 — Batch grounding queries (N+1 fix)
  // ============================================================================

  ctx.log('info', 'Fix 2: PERF-001 — Batch grounding queries');

  const batchQueries = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'PERF-001: Fix N+1 queries in grounding collection',
    description: `Fix the N+1 query pattern in scripts/chat/executor.py _collect_grounding().

CURRENT (lines ~1219-1277): For each mms_id, 5 separate queries run:
  for mms_id in all_mms:
      title_row = conn.execute("SELECT ... FROM titles WHERE mms_id=?")
      imp_row = conn.execute("SELECT ... FROM imprints WHERE mms_id=?")
      lang_row = conn.execute("SELECT ... FROM languages WHERE mms_id=?")
      agent_rows = conn.execute("SELECT ... FROM agents WHERE mms_id=?")
      subj_rows = conn.execute("SELECT ... FROM subjects WHERE mms_id=?")

With 30 records = 150 queries.

FIX: Replace with batch queries. Fetch all data for all mms_ids at once, then assemble RecordSummary objects in Python:

1. Build a single IN clause: placeholders = ",".join("?" for _ in all_mms)
2. Batch fetch titles: conn.execute(f"SELECT mms_id, value FROM titles WHERE mms_id IN ({placeholders})", all_mms)
3. Batch fetch imprints: similar pattern
4. Batch fetch languages: similar
5. Batch fetch agents: similar
6. Batch fetch subjects: similar
7. Build a dict keyed by mms_id for each, then loop once to assemble RecordSummary objects

This reduces 5N queries to 5 queries total.

IMPORTANT: Read the current _collect_grounding() function CAREFULLY before changing it. The RecordSummary construction must produce IDENTICAL output — same fields, same types. The only change is HOW the data is fetched, not WHAT is returned.

Also check if there's a Primo URL generation step per record — if so, keep it (it's a pure function, not a DB query).

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.chat.executor import execute_plan; print('OK')"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from scripts.chat.executor import execute_plan; print('OK')"`,
  });
  ctx.log('info', `Batch queries: ${JSON.stringify(batchQueries)}`);

  // ============================================================================
  // FIX 3: HEALTH-001 — Split metadata.py into focused modules
  // ============================================================================

  ctx.log('info', 'Fix 3: HEALTH-001 — Split metadata.py');

  const splitMetadata = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'HEALTH-001: Split metadata.py into focused modules',
    description: `Refactor app/api/metadata.py (2186 lines) into focused modules while preserving ALL existing behavior.

STRATEGY: Extract endpoint groups into separate router files, keep a thin metadata.py that imports and re-exports.

1. Create app/api/metadata_enrichment.py:
   - Move ALL /metadata/enrichment/* endpoints (get_enrichment_stats, get_enrichment_facets, get_enriched_agents, get_agent_enrichment, get_agent_records)
   - Move helper functions they depend on (_build_enrichment_where, etc)
   - Create a new APIRouter with prefix="/metadata/enrichment"

2. Create app/api/metadata_publishers.py:
   - Move ALL publisher authority endpoints (/metadata/publishers/*)
   - Move helper functions they depend on
   - Create a new APIRouter with prefix="/metadata/publishers"

3. Create app/api/metadata_corrections.py:
   - Move correction endpoints (post_correction, batch_corrections, correction_history)
   - Move _count_affected_records and related helpers
   - Create a new APIRouter with prefix="/metadata"

4. Keep in metadata.py:
   - Coverage endpoints (get_coverage, get_issues, get_unmapped, get_clusters, get_methods)
   - Agent chat endpoint
   - Primo URL endpoints
   - The shared _get_db_path() function
   - Import and mount the new sub-routers

5. In app/api/main.py:
   - Register the new routers alongside metadata router
   - Make sure the metadata_auth_middleware still applies to all /metadata/* paths

CRITICAL RULES:
- Every endpoint must produce IDENTICAL responses before and after
- Every URL path must remain the same
- Do NOT change any business logic
- Import shared utilities (like _get_db_path) from the original metadata.py
- The middleware in main.py matches on path prefix "/metadata/" — new routers with that prefix will be caught automatically

Read the FULL metadata.py first (in chunks) to understand all endpoints and their groupings.

Verification: source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; [print(r.path) for r in app.routes if hasattr(r,'path') and '/metadata' in r.path]"`,
    testCommand: `source ${projectRoot}/.venv/bin/activate && python3 -c "from app.api.main import app; print('All routers loaded OK')"`,
  });
  ctx.log('info', `Split metadata: ${JSON.stringify(splitMetadata)}`);

  // ============================================================================
  // BUILD VERIFICATION
  // ============================================================================

  ctx.log('info', 'Build verification');

  const buildCheck = await ctx.task(shellTask, {
    projectRoot,
    phase: 'full build + test verification',
    command: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build && echo "Frontend OK" && cd ${projectRoot} && source .venv/bin/activate && python3 -c "from app.api.main import app; print('Backend OK')" && python3 -m pytest tests/scripts/metadata/ tests/app/ -x -q 2>&1 | tail -5`,
    timeout: 180000,
  });
  ctx.log('info', `Build: ${JSON.stringify(buildCheck)}`);

  // ============================================================================
  // DEPLOY
  // ============================================================================

  const deployApproval = await ctx.task(breakpointTask, {
    question: 'P3 fixes implemented. Deploy?',
    options: ['Approve', 'Reject'],
  });

  if (!deployApproval?.approved) {
    return { success: true, deployed: false };
  }

  ctx.log('info', 'Deploying');

  const deploy = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Commit P3 fixes and deploy',
    description: `Commit all P3 fixes and deploy:

1. Stage all changed/new files
2. Commit with message:
   refactor: address P3 audit findings — code splitting, N+1 queries, metadata.py modularization

   HEALTH-004: Lazy-load Network page (MapLibre) for smaller initial bundle
   PERF-001: Batch grounding queries (5N → 5 queries)
   HEALTH-001: Split metadata.py into enrichment, publishers, corrections modules

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

3. Push to origin main
4. Run ./deploy.sh`,
    testCommand: `cd ${projectRoot} && git log --oneline -1`,
  });
  ctx.log('info', `Deploy: ${JSON.stringify(deploy)}`);

  // ============================================================================
  // UPDATE FIX REPORT
  // ============================================================================

  const report = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Update fix report with P3 results',
    description: `Update audits/2026-04-01-full-stack/FIX_REPORT.md:

1. Change the Summary section:
   - Fixed: 12 (was 9)
   - Deferred: 1 (HEALTH-002 model consolidation — too cross-cutting for safe refactor)

2. Update the P3 section to show which are now fixed:
   | HEALTH-001 | metadata.py SRP violation | Fixed | app/api/metadata*.py |
   | HEALTH-004 | Frontend bundle not code-split | Fixed | frontend/src/App.tsx |
   | PERF-001 | N+1 grounding queries | Fixed | scripts/chat/executor.py |
   | HEALTH-002 | 8 Pydantic model files | Deferred | Too cross-cutting |

3. Update the Deferred Items section to only list HEALTH-002.

4. Add a "P3 Fix Details" section with brief descriptions of what was done.`,
    testCommand: `ls ${projectRoot}/audits/2026-04-01-full-stack/FIX_REPORT.md`,
  });
  ctx.log('info', `Report: ${JSON.stringify(report)}`);

  return { success: true, deployed: true, feature: 'p3-audit-fixes' };
}

const agentTask = defineTask('agent-impl', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack engineer performing careful refactoring with zero behavior changes',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Read the relevant files thoroughly before making changes.',
        'Make careful, tested changes. Preserve all existing behavior.',
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status, filesChanged, details }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const shellTask = defineTask('shell-cmd', (args, taskCtx) => ({
  kind: 'shell',
  title: args.phase,
  shell: { command: args.command, cwd: args.projectRoot, timeout: args.timeout || 60000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
}));

const breakpointTask = defineTask('breakpoint-gate', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: { question: args.question, options: args.options },
}));
