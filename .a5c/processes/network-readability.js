/**
 * @process network-readability
 * @description Network Map readability: color-by, dot sizing, jitter, labels, legend. 5 tasks.
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const planPath = 'docs/superpowers/plans/2026-03-27-network-map-readability.md';

  ctx.log('info', 'Network Map readability (5 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Add primary_role to backend',
    description: `Read ${planPath} — Task 1. Add primary_role column to network_agents table in scripts/network/build_network_tables.py (compute most common role_norm per agent). Add to network_models.py MapNode. Rebuild tables. Verify API returns primary_role. Commit.`,
    testCommand: `cd ${projectRoot} && curl -s 'http://localhost:8000/network/map?connection_types=teacher_student&limit=3' | python3 -c "import sys,json; d=json.load(sys.stdin); n=d['nodes'][0]; print(f'{n[\"display_name\"]}: role={n.get(\"primary_role\",\"MISSING\")}')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Frontend types + color palettes + store',
    description: `Read ${planPath} — Task 2. In frontend/src/types/network.ts: add primary_role to MapNode, add ColorByMode type, add CENTURY_COLORS/ROLE_COLORS/OCCUPATION_COLORS palettes, add getCenturyLabel() and getAgentColor() helper functions. In frontend/src/stores/networkStore.ts: add colorBy state and setColorBy action, default 'century'. Verify: cd frontend && npx tsc --noEmit. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: MapView — color, size, jitter, labels',
    description: `Read ${planPath} — Task 3. This is the core visual change in frontend/src/components/network/MapView.tsx.

1. Add colorBy to Props and import getAgentColor, ColorByMode from types.
2. Add jitteredPositions useMemo that spreads agents at the same city in a circle pattern.
3. Update ScatterplotLayer: getPosition uses jitteredPositions, getRadius uses connection_count (4 + min(count/10, 10)), getFillColor uses getAgentColor(d, colorBy), add getLineColor/getLineWidth for white ring selection, add stroked+lineWidthUnits.
4. Add TextLayer for labels: top 15 agents by connection_count, getPosition from jitteredPositions, fontSize 12, fontWeight 600, white outline, pixelOffset [10,0].
5. Add labelLayer to the DeckGL layers array.
6. Update all updateTriggers to include colorBy.

IMPORTANT: Import TextLayer from '@deck.gl/layers'. Use globalThis.Map for JavaScript Maps (not the react-map-gl Map component).

Verify: cd frontend && npx tsc --noEmit. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task4 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 4: ControlBar — Color-by dropdown',
    description: `Read ${planPath} — Task 4. In frontend/src/components/network/ControlBar.tsx: import ColorByMode, destructure colorBy/setColorBy from store, add a "Color by:" dropdown with options Life Period (century), Role (role), Occupation (occupation). Place it before the Connections label. Verify: cd frontend && npx tsc --noEmit. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -3`,
  });

  const task5 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 5: Legend component + wire into Network page',
    description: `Read ${planPath} — Task 5.

1. Create frontend/src/components/network/Legend.tsx — compact overlay in bottom-left of map showing current color palette entries as colored dots with labels, plus "Size = connections" note. Use absolute positioning, bg-white/90 with backdrop-blur.

2. In frontend/src/pages/Network.tsx: import Legend and useNetworkStore, get colorBy from store, pass colorBy to MapView as prop, render Legend inside the map container div.

Verify: cd frontend && npx tsc --noEmit && npm run build. Commit and push.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  ctx.log('info', 'Network readability complete');
  return { success: true };
}

const agentTask = defineTask('readability-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior frontend developer improving Network Map visualization',
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
