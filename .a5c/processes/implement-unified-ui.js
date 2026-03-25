/**
 * @process implement-unified-ui
 * @description Implement the unified Rare Books Bot UI per IMPLEMENTATION_PLAN.md.
 * 6 phases: Foundation, Chat Screen, Query Debugger, Admin, Polish, Cleanup.
 * Each phase includes implementation + verification.
 * @inputs { projectRoot: string }
 * @outputs { success: boolean }
 *
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 * @agent react-developer specializations/web-development/agents/react-developer/AGENT.md
 * @agent frontend-architect specializations/web-development/agents/frontend-architect/AGENT.md
 * @agent fullstack-architect specializations/web-development/agents/fullstack-architect/AGENT.md
 * @agent e2e-testing specializations/web-development/agents/e2e-testing/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const { projectRoot = '/home/hagaybar/projects/rare-books-bot' } = inputs;
  const startTime = ctx.now();

  ctx.log('info', 'Starting Unified UI Implementation');

  // ============================================================================
  // PHASE 0: FOUNDATION & SCAFFOLDING (Week 1)
  // ============================================================================
  ctx.log('info', 'Phase 0: Foundation & Scaffolding');

  const phase0 = await ctx.task(phase0Task, { projectRoot });

  // Verify Phase 0
  const phase0verify = await ctx.task(phase0VerifyTask, { projectRoot, phase0 });

  // ============================================================================
  // PHASE 1: CHAT SCREEN + BACKEND MICRO-TASKS (Weeks 2-3)
  // ============================================================================
  ctx.log('info', 'Phase 1: Chat Screen + Backend Micro-Tasks');

  // Backend micro-tasks B1-B4
  const backendMicro = await ctx.task(backendMicroTasksTask, { projectRoot });

  // Chat screen implementation
  const chatScreen = await ctx.task(chatScreenTask, { projectRoot, backendMicro });

  // Phase 3a: Publisher Authorities read-only (parallel with Phase 1)
  const publisherReadOnly = await ctx.task(publisherReadOnlyTask, { projectRoot });

  // Verify Phase 1
  const phase1verify = await ctx.task(phase1VerifyTask, { projectRoot });

  // ============================================================================
  // PHASE 2: QUERY DEBUGGER + DIAGNOSTICS BACKEND (Weeks 4-5)
  // ============================================================================
  ctx.log('info', 'Phase 2: Query Debugger + Diagnostics Backend');

  // Diagnostic API endpoints B5-B12
  const diagnosticBackend = await ctx.task(diagnosticBackendTask, { projectRoot });

  // Query Debugger frontend
  const queryDebugger = await ctx.task(queryDebuggerTask, { projectRoot, diagnosticBackend });

  // Database Explorer frontend
  const dbExplorer = await ctx.task(dbExplorerTask, { projectRoot, diagnosticBackend });

  // CLI regression consolidation
  const cliConsolidate = await ctx.task(cliConsolidateTask, { projectRoot });

  // Verify Phase 2
  const phase2verify = await ctx.task(phase2VerifyTask, { projectRoot });

  // ============================================================================
  // PHASE 3b: ADMIN SCREENS (Week 5)
  // ============================================================================
  ctx.log('info', 'Phase 3b: Admin Screens');

  // Publisher CRUD + Health
  const adminScreens = await ctx.task(adminScreensTask, { projectRoot });

  // Verify Phase 3
  const phase3verify = await ctx.task(phase3VerifyTask, { projectRoot });

  // ============================================================================
  // PHASE 4: POLISH, INTEGRATION & TESTING (Weeks 6-7)
  // ============================================================================
  ctx.log('info', 'Phase 4: Polish, Integration & Testing');

  const polishPhase = await ctx.task(polishTask, { projectRoot });

  // Verify Phase 4
  const phase4verify = await ctx.task(phase4VerifyTask, { projectRoot });

  // ============================================================================
  // PHASE 5: RETIREMENT & CLEANUP (Week 8)
  // ============================================================================
  ctx.log('info', 'Phase 5: Retirement & Cleanup');

  const cleanup = await ctx.task(cleanupTask, { projectRoot });

  // Final verification
  const finalVerify = await ctx.task(finalVerifyTask, { projectRoot });

  return {
    success: true,
    duration: ctx.now() - startTime,
    metadata: { processId: 'implement-unified-ui' }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const phase0Task = defineTask('phase0-foundation', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 0: Foundation & Scaffolding',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior React Developer implementing UI restructuring',
      task: 'Restructure the existing React app at frontend/ for the 9-screen tiered layout per IMPLEMENTATION_PLAN.md Phase 0.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 1 (Architecture) and Phase 0 deliverables carefully.',
        'Read ALL existing frontend source files to understand current structure.',
        '',
        'Implement Phase 0 deliverables:',
        '1. Restructure frontend/src/pages/ to tiered layout:',
        '   - Move Dashboard.tsx to pages/operator/Coverage.tsx (rename)',
        '   - Move Workbench.tsx to pages/operator/Workbench.tsx',
        '   - Move AgentChat.tsx to pages/operator/AgentChat.tsx',
        '   - Move Review.tsx to pages/operator/Review.tsx',
        '   - Create pages/Chat.tsx (placeholder with "Chat coming in Phase 1")',
        '   - Create pages/diagnostics/QueryDebugger.tsx (placeholder)',
        '   - Create pages/diagnostics/DatabaseExplorer.tsx (placeholder)',
        '   - Create pages/admin/Publishers.tsx (placeholder)',
        '   - Create pages/admin/Health.tsx (placeholder)',
        '',
        '2. Update App.tsx routing:',
        '   - / -> Chat placeholder (with redirect from old / to /operator/coverage temporarily)',
        '   - /operator/coverage -> Coverage (was Dashboard at /)',
        '   - /operator/workbench -> Workbench (was at /workbench)',
        '   - /operator/agent -> AgentChat (was at /agent)',
        '   - /operator/review -> Review (was at /review)',
        '   - /diagnostics/query -> QueryDebugger placeholder',
        '   - /diagnostics/db -> DatabaseExplorer placeholder',
        '   - /admin/publishers -> Publishers placeholder',
        '   - /admin/health -> Health placeholder',
        '   - Add redirects: /workbench -> /operator/workbench, /agent -> /operator/agent, /review -> /operator/review',
        '',
        '3. Replace Sidebar.tsx with tiered navigation:',
        '   - Primary section: Chat',
        '   - Operator section: Coverage, Workbench, Agent Chat, Review',
        '   - Diagnostics section: Query Debugger, DB Explorer',
        '   - Admin section: Publishers, Health',
        '   - Collapsible sidebar state',
        '   - Health indicator dot placeholder',
        '',
        '4. Install new dependencies:',
        '   cd frontend && npm install zustand @radix-ui/react-dialog @radix-ui/react-popover @radix-ui/react-select @radix-ui/react-tabs sonner react-markdown',
        '',
        '5. Create Zustand store (stores/appStore.ts):',
        '   - sessionId: string | null',
        '   - sidebarCollapsed: boolean',
        '   - toggleSidebar()',
        '',
        '6. Update Layout.tsx:',
        '   - Chat route hides sidebar by default (add sidebarHidden prop or detect route)',
        '   - Other routes show sidebar',
        '',
        '7. Extend Vite proxy in vite.config.ts:',
        '   - Add /chat, /sessions, /diagnostics, /ws proxies to localhost:8000',
        '',
        '8. Ensure npm run build succeeds with zero TypeScript errors.',
        '',
        'IMPORTANT: Read existing components carefully before modifying. Preserve all existing functionality.',
        'IMPORTANT: Do NOT delete existing files — move/rename them.',
        'IMPORTANT: After all changes, verify with: cd frontend && npm run build'
      ],
      outputFormat: 'JSON with filesCreated, filesMoved, depsInstalled, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: {
        filesCreated: { type: 'array' },
        filesMoved: { type: 'array' },
        depsInstalled: { type: 'array' },
        buildStatus: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'scaffolding', 'phase0']
}));

export const phase0VerifyTask = defineTask('phase0-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Phase 0: Verify build succeeds',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
    timeout: 60000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'build', 'phase0']
}));

export const backendMicroTasksTask = defineTask('backend-micro-tasks', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 1: Backend Micro-Tasks B1-B4',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer extending FastAPI endpoints',
      task: 'Implement backend micro-tasks B1-B4 from IMPLEMENTATION_PLAN.md Section 3. These are small additions to existing API endpoints.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 3 (Backend Work Inventory) for B1-B4 specs.',
        'Read app/api/main.py and scripts/query/service.py to understand current flow.',
        '',
        'B1: Add execution_time_ms to ChatResponse metadata',
        '- QueryService already computes this internally',
        '- Add it to the metadata dict in ChatResponse before returning',
        '- Find where ChatResponse is constructed in app/api/main.py',
        '',
        'B2: Forward FacetCounts in ChatResponse metadata',
        '- QueryService computes facets (compute_facets=True) but they are discarded',
        '- Serialize FacetCounts into ChatResponse.metadata["facets"]',
        '',
        'B3: Forward QueryWarnings to ChatResponse metadata',
        '- QueryService produces warnings list',
        '- Add warnings to ChatResponse.metadata["warnings"] as list of dicts',
        '',
        'B4: Add primo_url field to Candidate model OR batch endpoint extension',
        '- Add a generate_primo_url utility that the chat endpoint can call',
        '- Add primo_url to each Candidate in the ChatResponse',
        '- Use configurable institution from environment variable PRIMO_INSTITUTION',
        '',
        'After changes, run: cd /home/hagaybar/projects/rare-books-bot && python -m pytest tests/app/test_api.py -x -q 2>&1 | tail -20',
        'If tests fail due to the changes, fix them.',
        '',
        'IMPORTANT: Read existing code before modifying. Small, surgical changes only.',
        'IMPORTANT: Do not break existing API behavior.'
      ],
      outputFormat: 'JSON with b1Status, b2Status, b3Status, b4Status, testsPass'
    },
    outputSchema: {
      type: 'object',
      required: ['testsPass'],
      properties: {
        b1Status: { type: 'string' },
        b2Status: { type: 'string' },
        b3Status: { type: 'string' },
        b4Status: { type: 'string' },
        testsPass: { type: 'boolean' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['backend', 'api', 'phase1']
}));

export const chatScreenTask = defineTask('chat-screen', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 1: Chat Screen Implementation',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior React developer building a conversational discovery interface',
      task: 'Build the Chat screen (/) for the Rare Books Bot per IMPLEMENTATION_PLAN.md Screen 1 specification. This is the primary product screen.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 2 Screen 1 (Chat) for complete specification.',
        'Read app/api/main.py POST /chat endpoint to understand response shape.',
        'Read scripts/chat/models.py for ChatResponse, Candidate, Evidence types.',
        '',
        'Build these files:',
        '',
        '1. frontend/src/pages/Chat.tsx — Main chat page:',
        '   - Message history display (user + bot messages)',
        '   - Query input with send button',
        '   - Loading indicator during query (1.5-7.5s typical)',
        '   - Phase indicator (query_definition / corpus_exploration)',
        '   - Overall confidence display from ChatResponse.confidence',
        '   - Clarification prompt rendering when clarification_needed is set',
        '   - Follow-up suggestion chips from suggested_followups',
        '   - Example query shortcuts on empty state (at least 5 examples from empirical data:',
        '     "books published in Amsterdam", "Hebrew books printed in Venice",',
        '     "books from the 16th century", "books about medicine",',
        '     "books by Maimonides")',
        '   - Session management: create on first query, store sessionId in Zustand',
        '   - Sidebar hidden by default on this route',
        '   - Markdown rendering for bot message text via react-markdown',
        '   - Execution time display in collapsible metadata section',
        '',
        '2. frontend/src/components/shared/CandidateCard.tsx:',
        '   - Title (with Primo link via PrimoLink component)',
        '   - Author',
        '   - Smart date display: single year if start==end, range if different',
        '   - Place: canonical + raw with smart dedup (hide raw if same as canonical)',
        '   - Publisher',
        '   - Subjects as tag chips (up to 3)',
        '   - Description (from MARC notes, collapsible if long)',
        '   - Expandable evidence panel with Evidence items',
        '   - Handle empty imprint gracefully: "No imprint data" for Faitlovitch manuscripts',
        '',
        '3. frontend/src/components/shared/ConfidenceBadge.tsx:',
        '   - Green (>=0.95), amber (0.80-0.95), red (<0.80)',
        '   - Shows percentage and label (High/Medium/Low)',
        '',
        '4. frontend/src/components/shared/PrimoLink.tsx:',
        '   - Renders a link to Primo catalog for a given mms_id',
        '   - Uses configurable base URL (env var or default)',
        '',
        '5. frontend/src/components/chat/MessageBubble.tsx:',
        '   - User messages (right-aligned, blue)',
        '   - Bot messages (left-aligned, gray) with CandidateCards for results',
        '',
        '6. frontend/src/components/chat/FollowUpChips.tsx:',
        '   - Row of clickable suggestion chips',
        '   - Clicking sends the suggestion as a new query',
        '',
        '7. frontend/src/components/chat/PhaseIndicator.tsx:',
        '   - Shows current conversation phase with icon',
        '',
        '8. frontend/src/api/chat.ts:',
        '   - sendChatMessage(message, sessionId?) -> ChatResponse',
        '   - getSession(sessionId) -> Session',
        '   - Uses fetch (not TanStack Query for mutations)',
        '',
        '9. frontend/src/types/chat.ts:',
        '   - TypeScript interfaces matching actual API response shapes:',
        '     ChatResponseAPI { success, response: ChatResponse, error? }',
        '     ChatResponse { message, candidate_set, suggested_followups, clarification_needed, session_id, phase, confidence, metadata }',
        '     CandidateSet { query_text, plan_hash, sql, candidates, total_count }',
        '     Candidate { record_id, match_rationale, evidence[], title, author, date_start, date_end, place_norm, place_raw, publisher, subjects, description, primo_url? }',
        '     Evidence { field, value, operator, matched_against, source, confidence, extraction_error }',
        '',
        'Style with Tailwind CSS. Use existing Tailwind config.',
        'After implementation: cd frontend && npm run build',
        'Fix any TypeScript errors.',
        '',
        'IMPORTANT: This is the most important screen. Make it polished and functional.',
        'IMPORTANT: Handle empty states, error states, loading states.',
        'IMPORTANT: The chat should feel modern, clean, and trustworthy.'
      ],
      outputFormat: 'JSON with filesCreated, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: {
        filesCreated: { type: 'array' },
        buildStatus: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'chat', 'phase1']
}));

export const publisherReadOnlyTask = defineTask('publisher-readonly', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 3a: Publisher Authorities Read-Only View',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React developer building an admin page',
      task: 'Build the Publisher Authorities read-only page at /admin/publishers per IMPLEMENTATION_PLAN.md Screen 8.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 2 Screen 8 (Publisher Authorities).',
        'The GET /metadata/publishers endpoint already exists. Read app/api/metadata.py to understand response shape.',
        '',
        'Build frontend/src/pages/admin/Publishers.tsx:',
        '- Fetch from GET /metadata/publishers using TanStack Query',
        '- Authority list table: canonical_name, type, confidence, variant_count, imprint_count',
        '- Type filter dropdown (printing_house, unresearched, bibliophile_society, etc.)',
        '- Expandable row showing variants (variant_form, script, language)',
        '- Research status indicator: "unresearched" (202 of 227) highlighted differently',
        '- Stats card: total authorities, researched vs unresearched, total variants',
        '',
        'Add API hook in frontend/src/api/publishers.ts or extend metadata.ts.',
        'Add TypeScript types in frontend/src/types/publishers.ts.',
        '',
        'After implementation: cd frontend && npm run build',
        'IMPORTANT: This is read-only for now. CRUD comes in Phase 3b.'
      ],
      outputFormat: 'JSON with filesCreated, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: { filesCreated: { type: 'array' }, buildStatus: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'admin', 'phase3a']
}));

export const phase1VerifyTask = defineTask('phase1-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Phase 1: Verify build succeeds',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
    timeout: 60000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'build', 'phase1']
}));

export const diagnosticBackendTask = defineTask('diagnostic-backend', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Diagnostic API Endpoints B5-B12',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer building diagnostic API endpoints',
      task: 'Build all diagnostic API endpoints (B5-B12) per IMPLEMENTATION_PLAN.md Section 3.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 3 for B5-B12 specifications.',
        'Read app/api/main.py and app/api/metadata.py to understand existing patterns.',
        'Read app/ui_qa/db.py to understand the QA database schema (qa_queries, qa_candidate_labels, qa_query_gold).',
        '',
        'Create app/api/diagnostics.py with these endpoints:',
        '',
        'B5: POST /diagnostics/query-run',
        '   - Accept query text, execute via QueryService, store result in QA DB',
        '   - Return: run_id, plan (JSON), sql, candidates with evidence, timing',
        '',
        'B6: GET /diagnostics/query-runs',
        '   - List recent query runs from QA DB (paginated)',
        '',
        'B7: POST /diagnostics/labels',
        '   - Submit TP/FP/FN/UNK labels and issue tags for candidates',
        '   - Store in qa_candidate_labels table',
        '',
        'B8: GET /diagnostics/labels/{run_id}',
        '   - Get all labels for a specific query run',
        '',
        'B9: GET /diagnostics/gold-set/export',
        '   - Export current gold set as JSON',
        '',
        'B10: POST /diagnostics/gold-set/regression',
        '   - Run regression test against gold set, return pass/fail per query',
        '',
        'B11: GET /diagnostics/tables',
        '   - List all tables in bibliographic.db with row counts and column names',
        '',
        'B12: GET /diagnostics/tables/{name}/rows',
        '   - Paginated row browsing with column search (query param: search, limit, offset)',
        '   - IMPORTANT: Validate table name against allowlist to prevent SQL injection',
        '',
        'Register all endpoints in app/api/main.py by importing the diagnostics router.',
        '',
        'Create Pydantic models in app/api/diagnostics_models.py for request/response types.',
        '',
        'Use existing patterns: use Path() for db path, use existing QA DB at data/qa/qa.db.',
        '',
        'After implementation, run: python -m pytest tests/ -x -q --ignore=tests/integration 2>&1 | tail -20',
        '',
        'IMPORTANT: Table name MUST be validated against an allowlist. No dynamic SQL injection.',
        'IMPORTANT: Use existing db patterns from app/ui_qa/db.py where possible.'
      ],
      outputFormat: 'JSON with endpointsCreated, testsPass'
    },
    outputSchema: {
      type: 'object',
      required: ['endpointsCreated'],
      properties: { endpointsCreated: { type: 'array' }, testsPass: { type: 'boolean' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['backend', 'diagnostics', 'phase2']
}));

export const queryDebuggerTask = defineTask('query-debugger', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Query Debugger Frontend',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior React developer building a query debugging tool',
      task: 'Build the Query Debugger screen at /diagnostics/query per IMPLEMENTATION_PLAN.md Screen 6.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 2 Screen 6 (Query Debugger).',
        '',
        'Build frontend/src/pages/diagnostics/QueryDebugger.tsx:',
        '- Three-panel layout: Query Input (top) | Results + Labels (left) | Plan + SQL (right)',
        '- Query input with "Run" button, limit control',
        '- Results table with candidate cards and TP/FP/FN/UNK labeling buttons per row',
        '- Issue tagging with predefined categories dropdown',
        '- Query plan display as formatted JSON tree',
        '- Generated SQL display with syntax highlighting (use <pre> with Tailwind)',
        '- Run history list in sidebar/drawer',
        '- Gold set export button',
        '- Regression runner with pass/fail display',
        '- Execution timing breakdown',
        '',
        'Create frontend/src/api/diagnostics.ts:',
        '- runQuery(queryText, limit) -> QueryRunResult',
        '- getQueryRuns() -> QueryRun[]',
        '- submitLabels(runId, labels) -> void',
        '- getLabels(runId) -> Label[]',
        '- exportGoldSet() -> GoldSet',
        '- runRegression() -> RegressionResult',
        '',
        'Create frontend/src/types/diagnostics.ts:',
        '- TypeScript interfaces for all diagnostic API types',
        '',
        'Use TanStack Query for data fetching. Use TanStack Table for results table.',
        'Style with Tailwind. After build: cd frontend && npm run build'
      ],
      outputFormat: 'JSON with filesCreated, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: { filesCreated: { type: 'array' }, buildStatus: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'diagnostics', 'phase2']
}));

export const dbExplorerTask = defineTask('db-explorer', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Database Explorer Frontend',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React developer building a database browsing tool',
      task: 'Build the Database Explorer screen at /diagnostics/db per IMPLEMENTATION_PLAN.md Screen 7.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 2 Screen 7 (Database Explorer).',
        '',
        'Build frontend/src/pages/diagnostics/DatabaseExplorer.tsx:',
        '- Table selector dropdown listing all 10 tables with row counts',
        '- Column names display for selected table',
        '- Paginated data browser using TanStack Table',
        '- Column search input (filters rows where any column contains search term)',
        '- Quick MMS ID lookup across tables',
        '',
        'The tables (from empirical data): records (2,796), imprints (2,773), titles (4,791),',
        'subjects (5,415), agents (4,366), languages (3,197), notes (8,037),',
        'publisher_authorities (227), publisher_variants (265), authority_enrichment (0)',
        '',
        'API calls: GET /diagnostics/tables, GET /diagnostics/tables/{name}/rows',
        '',
        'Style with Tailwind. After build: cd frontend && npm run build'
      ],
      outputFormat: 'JSON with filesCreated, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: { filesCreated: { type: 'array' }, buildStatus: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'diagnostics', 'phase2']
}));

export const cliConsolidateTask = defineTask('cli-consolidate', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: CLI Regression Consolidation',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer consolidating CLI commands',
      task: 'Merge app/qa.py regression runner (187 lines) into app/cli.py as a "regression" subcommand.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read app/qa.py to understand the regression runner logic.',
        'Read app/cli.py to understand the existing CLI structure.',
        '',
        'Add a "regression" command to app/cli.py that:',
        '- Takes --gold and --db arguments (same as app/qa.py regress command)',
        '- Takes --log-file and --verbose flags',
        '- Runs the same regression logic as app/qa.py',
        '- Returns exit code 0 (pass) or 1 (fail)',
        '',
        'Do NOT delete app/qa.py yet (that happens in Phase 5).',
        'The new CLI subcommand should work: python -m app.cli regression --gold data/qa/gold.json --db data/index/bibliographic.db',
        '',
        'IMPORTANT: Import the regression logic from app/qa.py rather than duplicating it.'
      ],
      outputFormat: 'JSON with status'
    },
    outputSchema: {
      type: 'object',
      required: ['status'],
      properties: { status: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['backend', 'cli', 'phase2']
}));

export const phase2VerifyTask = defineTask('phase2-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Phase 2: Verify build succeeds',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
    timeout: 60000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'build', 'phase2']
}));

export const adminScreensTask = defineTask('admin-screens', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 3b: Admin CRUD + Health Screen',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Full-stack developer building admin screens',
      task: 'Build Publisher CRUD backend (B13-B14), Health backend (B15), and Health frontend per IMPLEMENTATION_PLAN.md.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 2 Screens 8-9 and Section 3 B13-B15.',
        '',
        '### Backend (app/api/metadata.py):',
        '',
        'B13: Publisher Authority CRUD endpoints:',
        '- POST /metadata/publishers — create new authority',
        '- PUT /metadata/publishers/{id} — update authority (type, confidence, etc.)',
        '- DELETE /metadata/publishers/{id} — delete authority (with cascade to variants)',
        '- POST /metadata/publishers/{id}/variants — add variant',
        '- DELETE /metadata/publishers/{id}/variants/{variant_id} — remove variant',
        '',
        'B14: GET /metadata/publishers/{id}/match-preview — show how many imprints would match',
        '- Given a variant form, count imprints where publisher_norm LIKE variant',
        '',
        'B15: GET /health/extended — DB file size, last modified time',
        '',
        '### Frontend:',
        '',
        'Update frontend/src/pages/admin/Publishers.tsx:',
        '- Add "New Authority" button with form dialog (Radix Dialog)',
        '- Add edit button per row -> edit dialog',
        '- Add delete button with confirmation dialog',
        '- Add variant management within expanded row',
        '- Add match preview: "Adding this variant would match N imprints"',
        '',
        'Build frontend/src/pages/admin/Health.tsx:',
        '- Fetch from GET /health and GET /health/extended',
        '- Status card: healthy/degraded/unhealthy',
        '- Database info: file size, last modified',
        '- Session store status',
        '- Nav bar health indicator: update Sidebar to show green/red dot based on health polling',
        '',
        'After implementation: cd frontend && npm run build'
      ],
      outputFormat: 'JSON with backendEndpoints, frontendFiles, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: { backendEndpoints: { type: 'array' }, frontendFiles: { type: 'array' }, buildStatus: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['fullstack', 'admin', 'phase3']
}));

export const phase3VerifyTask = defineTask('phase3-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Phase 3: Verify build succeeds',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
    timeout: 60000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'build', 'phase3']
}));

export const polishTask = defineTask('polish-phase', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 4: Polish, Integration & Cross-Screen Links',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior frontend developer polishing and integrating',
      task: 'Polish the unified UI: add cross-screen navigation, shared component finalization, responsive layout, and backend fixes B17-B22.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Section 4 Phase 4 deliverables.',
        '',
        '### Cross-Screen Navigation Links:',
        '- Chat CandidateCard: "Flag issue" link -> /operator/workbench',
        '- Workbench ClusterCard: "Ask agent" link -> /operator/agent',
        '- Query Debugger: FN results link -> /operator/workbench',
        '- Coverage Dashboard: Gap card drill-through -> /operator/workbench',
        '',
        '### Shared Components:',
        '- Ensure CandidateCard, ConfidenceBadge, PrimoLink, FieldBadge work across all consuming screens',
        '- Create FieldBadge.tsx if not yet created (small badge showing field name with color)',
        '',
        '### Backend B17-B22 (pick the impactful ones):',
        'B17: Add date support to CorrectionRequest.field in app/api/metadata.py',
        'B20: Fix subject evidence.value null in scripts/query/execute.py (capture matched subject heading)',
        'B21: Fix agent evidence.source marc:unknown -> actual tag (100/700)',
        '',
        '### Responsive Layout:',
        '- Sidebar collapses to icon-only on narrow viewports (<768px)',
        '- Chat page is full-width on all viewports',
        '- Tables scroll horizontally on narrow viewports',
        '',
        '### Coverage Dashboard Updates:',
        '- Add binary confidence visualization for place/publisher (resolved vs unresolved)',
        '- Lead with agent normalization gap (4,366 base_clean, 0% alias-mapped)',
        '- Add Hebrew publisher indicator (553 Hebrew-script publishers at 0.95 confidence)',
        '',
        '### Issues Workbench Updates:',
        '- Reframe from "issues" to "improvement opportunities"',
        '- Add Hebrew Publishers tab',
        '- Add Agent Normalization tab',
        '- Add GET /metadata/unmapped endpoint consumption',
        '',
        'After all changes: cd frontend && npm run build',
        'Fix any TypeScript errors.'
      ],
      outputFormat: 'JSON with changesApplied, buildStatus'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: { changesApplied: { type: 'array' }, buildStatus: { type: 'string' } }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['frontend', 'polish', 'phase4']
}));

export const phase4VerifyTask = defineTask('phase4-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Phase 4: Verify build succeeds',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20',
    timeout: 60000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'build', 'phase4']
}));

export const cleanupTask = defineTask('cleanup', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 5: Retirement & Cleanup',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Developer performing codebase cleanup',
      task: 'Retire Streamlit UIs, clean up redundant code, update documentation per IMPLEMENTATION_PLAN.md Phase 5.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read IMPLEMENTATION_PLAN.md Phase 5 deliverables.',
        '',
        '### Archive (move, do not delete):',
        '- mkdir -p archive/retired_streamlit',
        '- Move app/ui_qa/pages/_wizard.py to archive/retired_streamlit/',
        '- Move app/ui_qa/wizard_components.py to archive/retired_streamlit/',
        '- Create archive/retired_streamlit/README.md explaining what was archived and why',
        '',
        '### Delete:',
        '- rm -rf app/ui_chat/ (449 lines, replaced by React Chat)',
        '- rm -rf app/ui_qa/ (3,531 lines, replaced by React Query Debugger + DB Explorer)',
        '- rm app/qa.py (187 lines, merged into CLI regression subcommand)',
        '- Remove run_chat_ui.sh if it exists',
        '',
        '### Preserve (do NOT delete):',
        '- data/qa/qa.db (historical data, read by diagnostic API)',
        '- data/qa/gold.json (active, used by CLI regression)',
        '',
        '### Remove streamlit dependency:',
        '- Edit pyproject.toml: remove streamlit from dependencies',
        '- Run: poetry lock --no-update (if poetry.lock exists)',
        '',
        '### Clean up RAG template remnants:',
        '- Remove configs/chunk_rules.yaml if it exists',
        '- Remove configs/outlook_helper.yaml if it exists',
        '- Remove scripts/api_clients/openai/completer.py if it exists',
        '',
        '### Update CLAUDE.md:',
        '- Remove all Streamlit UI references',
        '- Update QA Tool section to reference React Query Debugger',
        '- Correct stale numbers: publisher authorities 228->227, variants 266->265, unresearched 203->202',
        '- Remove stale place normalization method references (base_clean for places does not exist in production)',
        '- Add diagnostics API documentation',
        '',
        '### Route change:',
        '- In App.tsx, make / point to Chat (remove redirect to /operator/coverage)',
        '- Chat becomes the landing page',
        '',
        'After cleanup: cd frontend && npm run build',
        'Also run: cd /home/hagaybar/projects/rare-books-bot && python -m pytest tests/ -x -q --ignore=tests/integration 2>&1 | tail -20',
        '',
        'IMPORTANT: Verify nothing breaks after deletion. Run both frontend build and backend tests.'
      ],
      outputFormat: 'JSON with deleted, archived, updated, buildStatus, testsPass'
    },
    outputSchema: {
      type: 'object',
      required: ['buildStatus'],
      properties: {
        deleted: { type: 'array' },
        archived: { type: 'array' },
        updated: { type: 'array' },
        buildStatus: { type: 'string' },
        testsPass: { type: 'boolean' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['cleanup', 'retirement', 'phase5']
}));

export const finalVerifyTask = defineTask('final-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Final: Verify complete build',
  shell: {
    command: 'cd /home/hagaybar/projects/rare-books-bot/frontend && npm run build 2>&1 | tail -20 && echo "---PYTEST---" && cd /home/hagaybar/projects/rare-books-bot && python -m pytest tests/ -x -q --ignore=tests/integration 2>&1 | tail -20',
    timeout: 120000
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verify', 'final']
}));
