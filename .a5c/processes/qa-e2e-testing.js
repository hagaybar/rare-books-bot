/**
 * @process qa-e2e-testing
 * @description End-to-end QA testing of the Rare Books Bot application using Playwright.
 *   Tests all screens, user flows, data integrity, and LLM interactions.
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    frontendUrl = 'http://localhost:5173',
    backendUrl = 'http://localhost:8000',
    dbPath = 'data/index/bibliographic.db',
  } = inputs;

  ctx.log('info', 'Starting E2E QA testing');

  // Phase 1: Test map and structure
  const testMap = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Build test map and verify app structure',
    description: `You are a QA engineer. First, understand the app by:

1. Use Playwright to navigate to ${frontendUrl} and take a screenshot
2. Map all sidebar navigation items and their URLs
3. Click through each screen and take screenshots
4. List all screens found, their purpose, and their data sources
5. Check the API health: curl ${backendUrl}/health
6. Check API docs: curl ${backendUrl}/docs

The app has these screens (from sidebar):
- Chat (/) - Main query interface with LLM
- Network (/network) - Geographic network map
- Coverage (/operator/coverage) - Metadata coverage stats
- Workbench (/operator/workbench) - Issue triage
- Agent Chat (/operator/agent) - Metadata co-pilot
- Review (/operator/review) - HITL review
- Query Debugger (/diagnostics/query) - Query testing
- DB Explorer (/diagnostics/db) - Table browser
- Publishers (/admin/publishers) - Publisher authorities
- Enrichment (/admin/enrichment) - Agent enrichment browser
- Health (/admin/health) - System health

Visit each screen, note what loads, any errors, empty states, or broken UI.
Take screenshots of each. Report findings as JSON.`,
  });

  // Phase 2: Test primary flows (Chat + Network)
  const chatTest = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Test Chat flow end-to-end',
    description: `Test the Chat screen (${frontendUrl}/chat) thoroughly using Playwright:

1. Navigate to chat, verify welcome screen renders
2. Type "books published in Amsterdam" and submit
3. Wait for response — verify:
   - Loading state shows
   - Response renders with results
   - Results have record IDs, titles, evidence
   - Follow-up suggestions appear
4. Test a follow-up query in same session
5. Test empty/vague query: "books" — should trigger clarification
6. Test edge cases: very long query, special characters, Hebrew text "ספרים בירושלים"
7. Check console for errors
8. Check network requests for failed API calls
9. Verify session persists across queries (same session_id)
10. Take screenshots of each state

Also verify DB effects:
- Check sessions.db for new session: sqlite3 data/chat/sessions.db "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1"

Report all findings.`,
  });

  const networkTest = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Test Network Map end-to-end',
    description: `Test the Network Map screen (${frontendUrl}/network) using Playwright:

1. Navigate to /network
2. Verify map renders (MapLibre + OpenFreeMap tiles)
3. Verify agent dots appear on the map
4. Verify connection arcs are visible
5. Test control bar:
   - Toggle connection types (click each button)
   - Change century dropdown
   - Change role dropdown
   - Move agent slider
6. Test agent interaction:
   - Click an agent dot on the map
   - Verify side panel opens with agent details
   - Check Wikipedia summary displays
   - Check connections list in panel
   - Click a connection to navigate to that agent
7. Test background click to close panel
8. Verify status bar shows correct counts
9. Check console for WebGL errors or API failures
10. Take screenshots of working states and any errors

Check API directly:
- curl ${backendUrl}/network/map?connection_types=teacher_student&limit=10
- curl ${backendUrl}/network/agent/maimonides%2C%20moses

Report all findings.`,
  });

  // Phase 3: Test operator screens
  const operatorTest = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Test Operator screens (Coverage, Workbench, Agent Chat)',
    description: `Test operator screens using Playwright:

**Coverage (${frontendUrl}/operator/coverage)**:
1. Navigate, verify charts render (recharts pie/bar)
2. Check coverage stats for date, place, publisher, agent
3. Verify confidence distribution displays
4. Take screenshot

**Workbench (${frontendUrl}/operator/workbench)**:
1. Navigate, verify table renders
2. Test filtering, sorting, pagination if available
3. Check for editable cells
4. Take screenshot

**Agent Chat (${frontendUrl}/operator/agent)**:
1. Navigate, verify UI loads
2. Check coverage sidebar
3. If possible, test a simple agent query
4. Take screenshot

**Review (${frontendUrl}/operator/review)**:
1. Navigate, verify loads
2. Take screenshot

Report all findings for each screen.`,
  });

  // Phase 4: Test diagnostics and admin screens
  const adminTest = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Test Diagnostics and Admin screens',
    description: `Test remaining screens using Playwright:

**DB Explorer (${frontendUrl}/diagnostics/db)**:
1. Navigate, verify table list loads
2. Click on different tables: records, agents, imprints, agent_aliases, wikipedia_cache, network_agents
3. Verify data rows display
4. Test pagination if available
5. Check for empty tables: publisher_variants, physical_descriptions
6. Take screenshots

**Query Debugger (${frontendUrl}/diagnostics/query)**:
1. Navigate, verify loads
2. If possible, run a test query
3. Take screenshot

**Publishers (${frontendUrl}/admin/publishers)**:
1. Navigate, verify table loads with 227 publisher authorities
2. Take screenshot

**Enrichment (${frontendUrl}/admin/enrichment)**:
1. Navigate, verify enriched agents display
2. Check Wikipedia links are clickable and correct (not broken Special:GoToLinkedPage URLs)
3. Check Wikidata links
4. Take screenshot

**Health (${frontendUrl}/admin/health)**:
1. Navigate, check health status
2. Take screenshot

Report all findings.`,
  });

  // Phase 5: Data integrity verification
  const dataTest = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'Verify data integrity and consistency',
    description: `Run data integrity checks directly against the database:

1. Record counts match across related tables:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
records = c.execute('SELECT count(*) FROM records').fetchone()[0]
imprints = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
agents = c.execute('SELECT count(*) FROM agents').fetchone()[0]
titles = c.execute('SELECT count(*) FROM titles').fetchone()[0]
print(f'Records: {records}, Imprints: {imprints}, Agents: {agents}, Titles: {titles}')
# Every imprint should have a valid record_id
orphan_imprints = c.execute('SELECT count(*) FROM imprints WHERE record_id NOT IN (SELECT id FROM records)').fetchone()[0]
print(f'Orphan imprints: {orphan_imprints}')
orphan_agents = c.execute('SELECT count(*) FROM agents WHERE record_id NOT IN (SELECT id FROM records)').fetchone()[0]
print(f'Orphan agents: {orphan_agents}')
"

2. Wikipedia URL integrity:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
broken = c.execute(\"SELECT count(*) FROM authority_enrichment WHERE wikipedia_url LIKE '%Special:GoToLinkedPage%'\").fetchone()[0]
null_urls = c.execute('SELECT count(*) FROM authority_enrichment WHERE wikipedia_url IS NULL AND wikidata_id IS NOT NULL').fetchone()[0]
print(f'Broken Wikipedia URLs: {broken}')
print(f'Missing Wikipedia URLs (with Wikidata): {null_urls}')
"

3. Network table consistency:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
# Every network_agent should have a valid agent_norm in agents table
orphan_net = c.execute('SELECT count(*) FROM network_agents WHERE agent_norm NOT IN (SELECT DISTINCT agent_norm FROM agents)').fetchone()[0]
print(f'Orphan network agents: {orphan_net}')
# Every network_edge source/target should be in network_agents
bad_edges = c.execute('SELECT count(*) FROM network_edges WHERE source_agent_norm NOT IN (SELECT agent_norm FROM network_agents) OR target_agent_norm NOT IN (SELECT agent_norm FROM network_agents)').fetchone()[0]
print(f'Edges with missing agents: {bad_edges}')
"

4. Authority enrichment completeness:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
agents_with_uri = c.execute('SELECT count(DISTINCT authority_uri) FROM agents WHERE authority_uri IS NOT NULL').fetchone()[0]
enriched = c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]
print(f'Agents with URI: {agents_with_uri}, Enriched: {enriched}')
"

Report all findings.`,
  });

  // Phase 6: Compile report
  const report = await ctx.task(agentTask, {
    projectRoot, frontendUrl, backendUrl, dbPath,
    taskName: 'Compile QA report',
    description: `Compile all findings from the previous test phases into a structured QA report.

Write the report to: reports/qa-e2e-report.md

The report should follow this structure:
1. Application areas tested
2. Test flows executed
3. Bugs found (with severity, repro steps, expected/actual, evidence, root cause)
4. DB/data consistency findings
5. LLM interaction findings
6. Flaky/suspicious behaviors
7. Coverage gaps / what still needs testing
8. Recommended fixes in priority order

Read the babysitter journal at .a5c/runs/ to find the results from previous tasks.
Also check screenshots in .playwright-mcp/ directory.

Commit the report: git add reports/qa-e2e-report.md && git commit -m "docs: add E2E QA test report"`,
  });

  ctx.log('info', 'QA testing complete');
  return { success: true };
}

const agentTask = defineTask('qa-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior QA engineer performing end-to-end testing with Playwright browser automation',
      task: args.taskName,
      context: {
        projectRoot: args.projectRoot,
        frontendUrl: args.frontendUrl,
        backendUrl: args.backendUrl,
        dbPath: args.dbPath,
      },
      instructions: [
        `Working directory: ${args.projectRoot}`,
        'Use Playwright MCP tools (mcp__playwright__*) for all browser interactions.',
        'Use mcp__playwright__browser_navigate to go to URLs.',
        'Use mcp__playwright__browser_snapshot to read page state.',
        'Use mcp__playwright__browser_take_screenshot to capture visual evidence.',
        'Use mcp__playwright__browser_click to interact with elements.',
        'Use mcp__playwright__browser_fill_form to fill inputs.',
        'Use mcp__playwright__browser_console_messages to check for errors.',
        'Use mcp__playwright__browser_network_requests to check API calls.',
        args.description,
        'Return a JSON summary of findings.',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
