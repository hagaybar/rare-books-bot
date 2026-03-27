/**
 * @process enrichment-record-panel
 * @description Implement clickable record count badge on Entity Enrichment cards.
 *   4 tasks: API endpoint, panel component, wire into page, verify.
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = 'docs/superpowers/plans/2026-03-27-enrichment-record-panel.md',
    specPath = 'docs/superpowers/specs/2026-03-27-enrichment-record-panel-design.md',
  } = inputs;

  ctx.log('info', 'Implementing Enrichment Record Panel (4 tasks)');

  const task1 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 1: API Endpoint for agent records',
    description: `Read the plan at ${planPath} — Task 1.

Add GET /metadata/enrichment/agent-records endpoint to app/api/metadata.py.
Follow the EXACT code from the plan. The endpoint:
- Accepts wikidata_id OR agent_norm query params (exactly one required)
- Finds all agent_norms sharing the wikidata_id (handles merged Hebrew/Latin entities)
- Joins agents → records → titles → imprints
- Returns mms_id, title, date_raw, date_start, place_norm, publisher_norm, role, primo_url
- Deduplicates by mms_id
- Uses generate_primo_url() from scripts/utils/primo.py

Test: curl -s 'http://localhost:8000/metadata/enrichment/agent-records?wikidata_id=Q319902' | python3 -m json.tool | head -30
Expected: display_name "Isaac Abrabanel", record_count 14, records array with primo_urls.

Commit: git add app/api/metadata.py && git commit -m "feat: add agent-records endpoint for enrichment record panel"`,
    testCommand: `cd ${projectRoot} && curl -s 'http://localhost:8000/metadata/enrichment/agent-records?wikidata_id=Q319902' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Records: {d[\"record_count\"]}')"`,
  });

  const task2 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 2: Frontend API client + Panel component',
    description: `Read the plan at ${planPath} — Task 2.

1. Add to frontend/src/api/metadata.ts:
   - AgentRecord and AgentRecordsResponse interfaces
   - fetchAgentRecords(wikidataId?, agentNorm?) function

2. Create frontend/src/components/enrichment/EnrichmentRecordPanel.tsx:
   - Slide-in panel (w-96, right side, full height)
   - Header: display name, lifespan, record count, close button
   - Scrollable record list: each shows title (linked to Primo), date/place/publisher/role
   - Footer: "Ask in Chat" button + "View in Primo" button

IMPORTANT: ALL external links (Primo, Wikipedia, Wikidata, VIAF) must use target="_blank" rel="noopener noreferrer" to open in new tabs. Check the whole component for this.

Use the EXACT code from the plan as a starting point, but ensure:
- All <a> tags with external URLs have target="_blank" rel="noopener noreferrer"
- Loading and error states are handled
- Record titles link to Primo in new tabs

Verify: cd frontend && npx tsc --noEmit

Commit: git add frontend/src/api/metadata.ts frontend/src/components/enrichment/EnrichmentRecordPanel.tsx && git commit -m "feat: add EnrichmentRecordPanel component and API client"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -5`,
  });

  const task3 = await ctx.task(agentTask, {
    projectRoot,
    taskName: 'Task 3: Wire panel into Enrichment page + audit external links',
    description: `Read the plan at ${planPath} — Task 3.

1. In frontend/src/pages/admin/Enrichment.tsx:
   - Import EnrichmentRecordPanel
   - Add state: selectedAgent
   - Change the record count badge from <span> to <button> with onClick
   - Render EnrichmentRecordPanel when selectedAgent is set
   - The panel should appear to the RIGHT of the card grid (use flex layout)

2. IMPORTANT AUDIT: Check ALL external links across the entire Enrichment.tsx file and the new panel component. Every <a> tag that links to an external URL (Wikipedia, Wikidata, VIAF, Primo, or any non-app URL) MUST have target="_blank" rel="noopener noreferrer". Check:
   - Wikipedia links on enrichment cards
   - Wikidata links on enrichment cards
   - VIAF links on enrichment cards
   - Primo links in the record panel
   - Any other external links

Fix any that are missing target="_blank".

3. Also check these other files for external links that might not open in new tabs:
   - frontend/src/components/network/AgentPanel.tsx (external links section)
   - frontend/src/components/chat/ (any Primo links in chat responses)

Verify: cd frontend && npx tsc --noEmit && npm run build

Commit: git add frontend/src/ && git commit -m "feat: wire record panel into Enrichment page, audit all external links for new-tab behavior"`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`,
  });

  const verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-verify',
    command: `cd ${projectRoot} && echo "=== TypeScript ===" && cd frontend && npx tsc --noEmit 2>&1 | tail -3 && echo "=== Build ===" && npm run build 2>&1 | tail -3 && echo "=== API Test ===" && cd ${projectRoot} && curl -s 'http://localhost:8000/metadata/enrichment/agent-records?wikidata_id=Q319902' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d[\"display_name\"]}: {d[\"record_count\"]} records')" && echo "=== Done ==="`,
  });

  ctx.log('info', 'Enrichment Record Panel complete');
  return { success: true };
}

const agentTask = defineTask('panel-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack developer implementing a record panel feature',
      task: args.taskName,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        args.description,
        'Follow the plan code closely. Fix any issues that arise.',
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

const shellTask = defineTask('panel-shell', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: { command: args.command, cwd: args.projectRoot, timeout: 60000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/output.json` },
}));
