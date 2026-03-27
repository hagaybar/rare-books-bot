/**
 * @process cascading-filters
 * @description Implement cascading enrichment filters — 2 tasks.
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;

  ctx.log('info', 'Implementing cascading enrichment filters (2 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: Backend — shared WHERE builder + scoped facets',
    description: `Read docs/superpowers/plans/2026-03-27-cascading-enrichment-filters.md — Task 1.

In app/api/metadata.py:

1. Add _build_enrichment_where() helper function BEFORE the get_enriched_agents endpoint (~line 1865). This function takes search, occupation, century, role, has_bio, has_image params and returns (where_sql, params). Copy the EXACT code from the plan.

2. Refactor get_enriched_agents() to use the new helper instead of inline filter building. Replace the inline where_clauses/params construction (lines ~1892-1949) with a call to _build_enrichment_where().

3. Replace the entire get_enrichment_facets() function (~lines 1809-1862) with the new version from the plan that:
   - Accepts the same filter params as get_enriched_agents
   - For each facet (role, occupation, century), calls _build_enrichment_where with all filters EXCEPT that facet's own
   - Uses COALESCE(ae.wikidata_id, a.agent_norm) for deduplication (consistent with agents endpoint)

Test:
  curl -s 'http://localhost:8000/metadata/enrichment/facets' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Global: occ={len(d[\"occupations\"])}, cent={len(d[\"centuries\"])}')"
  curl -s 'http://localhost:8000/metadata/enrichment/facets?occupation=rabbi' | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  {c[\"value\"]}: {c[\"count\"]}') for c in d['centuries']]"

The second call should show smaller counts than the first.

Commit: git add app/api/metadata.py && git commit -m "feat: cascading enrichment filters — shared WHERE builder + scoped facets"`,
    testCommand: `cd ${projectRoot} && curl -s 'http://localhost:8000/metadata/enrichment/facets?occupation=rabbi' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Scoped centuries: {len(d[\"centuries\"])} entries')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Frontend — pass filters to facets query',
    description: `Read docs/superpowers/plans/2026-03-27-cascading-enrichment-filters.md — Task 2.

In frontend/src/pages/admin/Enrichment.tsx:

1. Update the fetchFacets function (~line 80) to accept filter params and build query string. Use the EXACT code from the plan.

2. Update the facetsQuery (~line 395) to:
   - Include filters in the queryKey: ['enrichment-facets', filters]
   - Pass filters to fetchFacets: queryFn: () => fetchFacets(filters)
   - Add placeholderData: (prev) => prev to prevent dropdown flicker
   - Reduce staleTime to 10_000

Verify: cd frontend && npx tsc --noEmit && npm run build

Commit: git add frontend/src/pages/admin/Enrichment.tsx && git commit -m "feat: frontend cascading filters — pass filters to facets query"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  const verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final',
    command: `cd ${projectRoot} && echo "=== Build ===" && cd frontend && npm run build 2>&1 | tail -3 && echo "=== API ===" && cd ${projectRoot} && curl -s 'http://localhost:8000/metadata/enrichment/facets?occupation=rabbi' | python3 -c "import sys,json; d=json.load(sys.stdin); total=sum(c['count'] for c in d['centuries']); print(f'Rabbi centuries total: {total}')" && echo "=== Done ==="`,
  });

  ctx.log('info', 'Cascading filters complete');
  return { success: true };
}

const agentTask = defineTask('filter-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior developer implementing cascading filters',
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

const shellTask = defineTask('filter-shell', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: { command: args.command, cwd: args.projectRoot, timeout: 60000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
}));
