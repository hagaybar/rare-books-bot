/**
 * @process network-phase23
 * @description Network Map Phase 2+3: onboarding + arc hierarchy. 3 tasks.
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */
import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const plan = 'docs/superpowers/plans/2026-03-27-network-map-phase2-3.md';

  ctx.log('info', 'Network Map Phase 2+3 (3 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Backend — same_place_period + API fixes',
    description: `Read ${plan} — Task 1 completely. Implement ALL steps:
1. Add _build_same_place_period_edges() to build_network_tables.py — finds agents sharing the same place_norm with overlapping active periods (>=10 years). Call it in build_network_edges BEFORE indexes.
2. Rebuild: poetry run python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json
3. In app/api/network.py: add 'same_place_period' to VALID_CONNECTION_TYPES. Handle empty connection_types (when types=[] or types=['none'], return nodes with 0 edges — don't let empty IN() cause SQL error). Add category limit: when 'category' is in types, LIMIT 100 for category edges only.
4. In app/api/network_models.py: add category_limited: bool = False and category_total: int = 0 to MapMeta.
5. Test all 3 scenarios (empty types, same_place_period, category limited).
Commit.`,
    testCommand: `cd ${projectRoot} && curl -s 'http://localhost:8000/network/map?connection_types=same_place_period&limit=10' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Edges: {len(d[\"edges\"])}')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Frontend types + store + API client',
    description: `Read ${plan} — Task 2 completely. Implement ALL steps:
1. In frontend/src/types/network.ts: add 'same_place_period' to ConnectionType union. Replace CONNECTION_TYPE_CONFIG with the 6-type version including tier:'primary'|'secondary' field and new human-readable labels and colors (teacher_student blue, co_publication green, same_place_period cyan [6,182,212], wikilink orange, llm_extraction purple, category gray).
2. In frontend/src/stores/networkStore.ts: change default connectionTypes to [] (empty array). Remove the deselect guard (the line that prevents deselecting the last connection type).
3. In frontend/src/api/network.ts: when connectionTypes is empty, send 'none' instead of empty string.
Verify: cd frontend && npx tsc --noEmit
Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: Frontend components — tiered buttons, arc hierarchy, header',
    description: `Read ${plan} — Task 3 completely. Implement ALL steps:

1. ControlBar.tsx: Replace connection type buttons with tiered layout. Primary buttons (Teacher & Student, Published Together, Active in Same City, Mentioned Together) are normal-sized. After a | separator and "More:" label, show secondary buttons (AI-Discovered, Shared Topics) smaller and muted. Filter CONNECTION_TYPE_CONFIG entries by tier.

2. MapView.tsx: Update arc layer:
   - getSourcePosition/getTargetPosition: use jitteredPositions lookup (fall back to nodeMap)
   - getSourceColor/getTargetColor: confidence-based opacity (>=0.8→200, >=0.6→130, <0.6→60) when no selection; keep existing selection highlighting logic
   - getWidth: confidence-based (>=0.8→3px, >=0.6→2px, <0.6→1px), doubled when selected

3. Network.tsx:
   - Add page header before ControlBar: "Scholarly Network Map" (text-xl font-semibold) + subtitle with agent count
   - Update status bar: when connectionTypes is empty show "Select connection types to see relationships"; when category_limited show the limit note
   - Import connectionTypes from useNetworkStore

Verify: cd frontend && npx tsc --noEmit && npm run build
Commit and push.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  ctx.log('info', 'Phase 2+3 complete');
  return { success: true };
}

const agentTask = defineTask('phase23-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior developer implementing Network Map UX improvements',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        `Verification: ${args.testCommand}`,
        'Return JSON: { taskName, status, filesChanged }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
