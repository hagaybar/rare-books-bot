/**
 * @process network-map-explorer
 * @description Build Network Map Explorer: geocoding, materialized tables, FastAPI endpoints,
 *   React page with MapLibre GL + deck.gl, filter controls, and agent detail panel.
 *   13 tasks following the plan at docs/superpowers/plans/2026-03-26-network-map-explorer.md
 *
 * @inputs { projectRoot: string, planPath: string, specPath: string, dbPath: string }
 * @outputs { success: boolean, tasksCompleted: number }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 * @agent backend-developer specializations/web-development/agents/backend-developer/AGENT.md
 * @agent fullstack-architect specializations/web-development/agents/fullstack-architect/AGENT.md
 * @agent react-developer specializations/web-development/agents/react-developer/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = 'docs/superpowers/plans/2026-03-26-network-map-explorer.md',
    specPath = 'docs/superpowers/specs/2026-03-26-network-map-explorer-design.md',
    dbPath = 'data/index/bibliographic.db',
    branch = 'feature/network-map-explorer',
  } = inputs;

  ctx.log('info', 'Starting Network Map Explorer build (13 tasks, 5 phases)');

  // ============================================================================
  // PHASE 1: Data Foundation (Tasks 1-3)
  // Geocoding file, build script, materialize tables
  // ============================================================================

  ctx.log('info', 'Phase 1: Data foundation — geocoding + materialized tables');

  const task1 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 1,
    taskName: 'Generate Place Geocodes File',
    description: `Follow Task 1 in the plan exactly. Create data/normalization/place_geocodes.json with lat/lon for the top places from the imprints table. Query "SELECT DISTINCT place_norm, count(*) as cnt FROM imprints WHERE place_norm IS NOT NULL GROUP BY place_norm ORDER BY cnt DESC" from ${dbPath}. Use Python to generate coordinates for well-known historical cities (Amsterdam, Venice, Paris, London, Jerusalem, Safed, Constantinople, etc). You can use OpenAI API if OPENAI_API_KEY is set, otherwise manually create the coordinates — these are famous cities with well-known coordinates. Target at least 80 places. Verify with: python3 -c "import json; d=json.load(open('data/normalization/place_geocodes.json')); print(f'{len(d)} places')". Then git add and commit.`,
    testCommand: `cd ${projectRoot} && python3 -c "import json; d=json.load(open('data/normalization/place_geocodes.json')); print(f'{len(d)} places geocoded'); assert len(d) >= 30, f'Only {len(d)} places'"`,
  });

  const task2 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 2,
    taskName: 'Build Script for Materialized Tables',
    description: `Follow Task 2 in the plan exactly. Create scripts/network/__init__.py, scripts/network/build_network_tables.py, tests/scripts/network/__init__.py, and tests/scripts/network/test_build_network_tables.py. The build script materializes network_edges (from wikipedia_connections + teacher/student + co-publication) and network_agents (with place assignment, display_name fallback chain, connection counts). Use the EXACT code from the plan. Run tests: poetry run pytest tests/scripts/network/test_build_network_tables.py -v. All tests must pass. Then git add and commit.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/network/test_build_network_tables.py -v 2>&1 | tail -15`,
  });

  const task3 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 3,
    taskName: 'Run Build Script to Populate Tables',
    description: `Follow Task 3 in the plan exactly. Run: poetry run python -m scripts.network.build_network_tables data/index/bibliographic.db data/normalization/place_geocodes.json. Verify tables were created and populated: check network_edges has 40000+ rows and network_agents has 2000+ rows. Check all 5 connection types exist. Fix any issues. Commit.`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); e=c.execute('SELECT count(*) FROM network_edges').fetchone()[0]; a=c.execute('SELECT count(*) FROM network_agents').fetchone()[0]; print(f'edges={e} agents={a}'); assert e > 1000, f'Only {e} edges'; assert a > 100, f'Only {a} agents'"`,
  });

  const phase1Verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase1-data-foundation',
    command: `cd ${projectRoot} && python3 -c "
import sqlite3, json
c = sqlite3.connect('${dbPath}')
e = c.execute('SELECT count(*) FROM network_edges').fetchone()[0]
a = c.execute('SELECT count(*) FROM network_agents').fetchone()[0]
types = c.execute('SELECT connection_type, count(*) FROM network_edges GROUP BY connection_type').fetchall()
placed = c.execute('SELECT count(*) FROM network_agents WHERE lat IS NOT NULL').fetchone()[0]
print(f'Edges: {e}, Agents: {a} (placed: {placed})')
for t, cnt in types: print(f'  {t}: {cnt}')
geocodes = json.load(open('data/normalization/place_geocodes.json'))
print(f'Geocodes: {len(geocodes)}')
"`,
  });

  // ============================================================================
  // PHASE 2: API Layer (Tasks 4-6)
  // Pydantic models, FastAPI router, mount + tests
  // ============================================================================

  ctx.log('info', 'Phase 2: API layer — models, router, tests');

  const task4 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 4,
    taskName: 'API Pydantic Models',
    description: `Follow Task 4 in the plan exactly. Create app/api/network_models.py with Pydantic models: MapNode, MapEdge, MapMeta, MapResponse, AgentConnection, AgentDetail. Use the EXACT code from the plan. Verify import: poetry run python -c "from app.api.network_models import MapResponse, AgentDetail; print('OK')". Commit.`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.network_models import MapResponse, AgentDetail; print('OK')"`,
  });

  const task5 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 5,
    taskName: 'API Router',
    description: `Follow Task 5 in the plan exactly. Create app/api/network.py with FastAPI router: GET /network/map (filtered nodes+edges) and GET /network/agent/{agent_norm:path} (agent detail with Wikipedia summary, connections, external links, primo_url). Use the EXACT code from the plan. Verify: poetry run python -c "from app.api.network import router; print(f'Routes: {len(router.routes)}')". Commit.`,
    testCommand: `cd ${projectRoot} && poetry run python -c "from app.api.network import router; print(f'Routes: {len(router.routes)}')"`,
  });

  const task6 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 6,
    taskName: 'Mount Router and Write API Tests',
    description: `Follow Task 6 in the plan exactly. (1) Mount the network router in app/api/main.py: add "from app.api.network import router as network_router" and "app.include_router(network_router)". (2) Create tests/app/test_network_api.py with tests: test_get_map_default, test_get_map_with_types, test_get_map_invalid_type, test_get_agent_detail, test_get_agent_not_found. Use tmp_path fixture for mock DB. Run: poetry run pytest tests/app/test_network_api.py -v. All tests must pass. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/app/test_network_api.py -v 2>&1 | tail -15`,
  });

  const phase2Verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase2-api-layer',
    command: `cd ${projectRoot} && poetry run pytest tests/app/test_network_api.py -v 2>&1 | tail -20`,
  });

  // ============================================================================
  // PHASE 3: Frontend Foundation (Tasks 7-8)
  // Dependencies, types, API client, store
  // ============================================================================

  ctx.log('info', 'Phase 3: Frontend foundation — deps, types, API client, store');

  const task7 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 7,
    taskName: 'Install Frontend Dependencies',
    description: `Follow Task 7 in the plan exactly. (1) Install packages: cd frontend && npm install maplibre-gl react-map-gl @deck.gl/core @deck.gl/layers @deck.gl/react. (2) Add Vite proxy for /network — edit frontend/vite.config.ts and add '/network': { target: 'http://localhost:8000', changeOrigin: true } alongside existing proxy entries. (3) Verify: cd frontend && node -e "require('maplibre-gl'); require('react-map-gl'); console.log('OK')". Commit package.json, package-lock.json, vite.config.ts.`,
    testCommand: `cd ${projectRoot}/frontend && node -e "require('maplibre-gl'); require('react-map-gl'); console.log('OK')"`,
  });

  const task8 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 8,
    taskName: 'Frontend Types, API Client, and Store',
    description: `Follow Task 8 in the plan exactly. Create 3 files: (1) frontend/src/types/network.ts — TypeScript interfaces for MapNode, MapEdge, MapMeta, MapResponse, AgentConnection, AgentDetail, ConnectionType, CONNECTION_TYPE_CONFIG. (2) frontend/src/api/network.ts — API client with fetchMapData(params) and fetchAgentDetail(agentNorm). (3) frontend/src/stores/networkStore.ts — Zustand store for filter state. Use the EXACT code from the plan. Verify: cd frontend && npx tsc --noEmit. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // ============================================================================
  // PHASE 4: Frontend Components (Tasks 9-12)
  // Page + routing + sidebar, MapView, ControlBar, AgentPanel
  // ============================================================================

  ctx.log('info', 'Phase 4: Frontend components — page, map, controls, panel');

  const task9 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 9,
    taskName: 'Network Page, Routing, and Sidebar',
    description: `Follow Task 9 in the plan exactly. (1) Create frontend/src/pages/Network.tsx — main page component with useQuery for map data and agent detail, placeholderData for smooth transitions, toast notifications for errors, empty results overlay. Uses MapView, ControlBar, AgentPanel components. Use the EXACT code from the plan. (2) Add route in frontend/src/App.tsx: import Network and add <Route path="/network" element={<Network />} />. (3) Add to Sidebar.tsx: add 'network' GlobeAlt icon to ICONS and nav item to Primary section. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  const task10 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 10,
    taskName: 'MapView Component',
    description: `Follow Task 10 in the plan exactly. Create frontend/src/components/network/MapView.tsx — MapLibre GL + deck.gl component. IMPORTANT: import as "MapGL" not "Map" to avoid shadowing JavaScript's built-in Map. Use globalThis.Map for the node lookup. Use pickedRef to handle background clicks (deck.gl onClick doesn't fire on empty space — attach onClick to MapGL instead). ArcLayer for connections, ScatterplotLayer for agents. OpenFreeMap Positron tiles. Selection highlighting, tooltips. Use the EXACT code from the plan. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  const task11 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 11,
    taskName: 'ControlBar Component',
    description: `Follow Task 11 in the plan exactly. Create frontend/src/components/network/ControlBar.tsx — filter controls with connection type toggle buttons (colored by type), century dropdown, role dropdown, and agent count slider. IMPORTANT: The slider must be debounced (300ms) using useDebouncedCallback hook with local state for smooth dragging. Use the EXACT code from the plan (includes AgentSlider sub-component). Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  const task12 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 12,
    taskName: 'AgentPanel Component',
    description: `Follow Task 12 in the plan exactly. Create frontend/src/components/network/AgentPanel.tsx — side panel with agent header (name, dates, place, occupations), expandable Wikipedia summary, connections grouped by type (clickable to navigate), catalog links (View in Chat, Primo, external links). Use the EXACT code from the plan. Verify: cd frontend && npx tsc --noEmit — should have NO errors. Commit.`,
    testCommand: `cd ${projectRoot}/frontend && npx tsc --noEmit 2>&1 | tail -10`,
  });

  // ============================================================================
  // PHASE 5: Integration Verification (Task 13)
  // ============================================================================

  ctx.log('info', 'Phase 5: Integration verification');

  const task13 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath, branch,
    taskNumber: 13,
    taskName: 'Integration Test and Verification',
    description: `Follow Task 13 in the plan. (1) Run all backend tests: poetry run pytest tests/app/test_network_api.py tests/scripts/network/ -v. All must pass. (2) Verify TypeScript compiles: cd frontend && npx tsc --noEmit. (3) Verify frontend builds: cd frontend && npm run build. (4) Test API manually: start uvicorn app.api.main:app --port 8765 in background, curl http://localhost:8765/network/map?connection_types=teacher_student&limit=5, verify JSON response has nodes and edges. Kill the server after. (5) Commit any fixes needed.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/app/test_network_api.py tests/scripts/network/ -v 2>&1 | tail -15 && cd frontend && npm run build 2>&1 | tail -5`,
  });

  const finalVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-verification',
    command: `cd ${projectRoot} && echo "=== Git Status ===" && git status --short && echo "=== Test Results ===" && poetry run pytest tests/app/test_network_api.py tests/scripts/network/ -v 2>&1 | tail -10 && echo "=== Frontend Build ===" && cd frontend && npm run build 2>&1 | tail -5 && echo "=== DONE ==="`,
  });

  ctx.log('info', `Network Map Explorer build complete. All ${13} tasks executed.`);

  return {
    success: true,
    tasksCompleted: 13,
    branch,
    phases: {
      dataFoundation: { geocodes: !!task1, buildScript: !!task2, populate: !!task3 },
      apiLayer: { models: !!task4, router: !!task5, tests: !!task6 },
      frontendFoundation: { deps: !!task7, types: !!task8 },
      frontendComponents: { page: !!task9, map: !!task10, controls: !!task11, panel: !!task12 },
      integration: { verified: !!task13 },
    },
  };
}

// ============================================================================
// Task Definitions
// ============================================================================

const implTask = defineTask('implementation-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.taskNumber}: ${args.taskName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior full-stack developer implementing a Network Map Explorer feature',
      task: `Implement Task ${args.taskNumber}: ${args.taskName}`,
      context: {
        projectRoot: args.projectRoot,
        branch: args.branch,
        planPath: args.planPath,
        specPath: args.specPath,
        dbPath: args.dbPath,
      },
      instructions: [
        `You are working in ${args.projectRoot} on branch ${args.branch}.`,
        `Read the implementation plan at ${args.planPath} — specifically Task ${args.taskNumber}: "${args.taskName}".`,
        `Also read the design spec at ${args.specPath} for context.`,
        `IMPORTANT: ${args.description}`,
        'Follow the plan code EXACTLY — do not improvise or deviate unless there is a clear bug.',
        'After implementation, run the verification command to ensure it works.',
        `Verification: ${args.testCommand}`,
        'If tests fail, debug and fix until they pass.',
        'Commit your changes with a descriptive message.',
        'Return a JSON summary with: { taskNumber, taskName, status, filesCreated, filesModified, testsPassed }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const shellTask = defineTask('shell-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: {
    command: args.command,
    cwd: args.projectRoot,
    timeout: 60000,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));
