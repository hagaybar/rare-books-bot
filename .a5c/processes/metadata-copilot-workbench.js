/**
 * @process metadata-copilot-workbench
 * @description Metadata Co-pilot Workbench: Agent-driven HITL system for bibliographic data quality improvement.
 * Builds a React dashboard + FastAPI backend + specialist LLM agents (Date, Place, Publisher, Agent, Subject)
 * that analyze normalization gaps in a MARC-based rare books database, propose fixes grounded in evidence,
 * and allow a librarian to approve/reject corrections via an interactive workbench.
 *
 * @inputs {
 *   projectRoot: string,
 *   dbPath: string,
 *   aliasMapDir: string,
 *   frontendFramework: string,
 *   targetFields: array,
 *   primoBaseUrl: string
 * }
 * @outputs {
 *   success: boolean,
 *   phases: object,
 *   coverageReport: object,
 *   artifacts: array
 * }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill frontend-design .claude/skills/frontend-design/SKILL.md
 * @skill data-quality-profiler specializations/data-engineering-analytics/skills/data-quality-profiler/SKILL.md
 * @agent data-quality-engineer specializations/data-engineering-analytics/agents/data-quality-engineer/AGENT.md
 * @agent react-developer specializations/web-development/agents/react-developer/AGENT.md
 * @agent e2e-testing specializations/web-development/agents/e2e-testing/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    dbPath = 'data/index/bibliographic.db',
    aliasMapDir = 'data/normalization',
    frontendFramework = 'react',
    targetFields = ['date', 'place', 'publisher', 'agent', 'subject'],
    primoBaseUrl = '',
    outputDir = 'metadata-copilot-output'
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting Metadata Co-pilot Workbench build');
  ctx.log('info', `Target fields: ${targetFields.join(', ')}`);

  // ============================================================================
  // MILESTONE 1: AUDIT & COVERAGE ANALYSIS
  // Deterministic analysis of current normalization state
  // ============================================================================

  ctx.log('info', 'Milestone 1: Normalization Coverage Audit');

  // Task 1.1: Build the coverage audit module
  const auditModule = await ctx.task(buildAuditModuleTask, {
    projectRoot,
    dbPath,
    targetFields,
    outputDir
  });
  artifacts.push(...(auditModule.artifacts || []));

  // Task 1.2: Run initial audit to establish baseline
  const baselineAudit = await ctx.task(runBaselineAuditTask, {
    projectRoot,
    dbPath,
    targetFields,
    auditModule,
    outputDir
  });
  artifacts.push(...(baselineAudit.artifacts || []));

  // Task 1.3: Generate gap clustering analysis
  const gapClustering = await ctx.task(buildGapClusteringTask, {
    projectRoot,
    dbPath,
    targetFields,
    baselineAudit,
    outputDir
  });
  artifacts.push(...(gapClustering.artifacts || []));

  // Breakpoint: Review audit results before proceeding
  await ctx.breakpoint({
    question: `Milestone 1 Complete: Coverage audit shows normalization gaps across ${targetFields.length} fields. Review the baseline coverage report and gap clusters before building the API layer?`,
    title: 'Coverage Audit Review',
    context: {
      runId: ctx.runId,
      fields: targetFields,
      summary: 'Audit module built, baseline established, gaps clustered by frequency and type'
    }
  });

  // ============================================================================
  // MILESTONE 2: FASTAPI METADATA API
  // REST endpoints for coverage, issues, corrections, agent chat
  // ============================================================================

  ctx.log('info', 'Milestone 2: FastAPI Metadata API');

  // Task 2.1: Design and implement metadata API router
  const metadataApi = await ctx.task(buildMetadataApiTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    targetFields,
    outputDir
  });
  artifacts.push(...(metadataApi.artifacts || []));

  // Task 2.2: Implement corrections endpoint with alias map writes
  const correctionsApi = await ctx.task(buildCorrectionsApiTask, {
    projectRoot,
    aliasMapDir,
    metadataApi,
    outputDir
  });
  artifacts.push(...(correctionsApi.artifacts || []));

  // Task 2.3: Implement Primo URL batch generation endpoint
  const primoApi = await ctx.task(buildPrimoApiTask, {
    projectRoot,
    dbPath,
    primoBaseUrl,
    outputDir
  });
  artifacts.push(...(primoApi.artifacts || []));

  // Task 2.4: API tests
  const apiTests = await ctx.task(testMetadataApiTask, {
    projectRoot,
    metadataApi,
    correctionsApi,
    primoApi,
    outputDir
  });
  artifacts.push(...(apiTests.artifacts || []));

  // Verify API tests pass
  const apiTestRun = await ctx.task(runApiTestsShellTask, {
    projectRoot
  });

  // Breakpoint: Review API before building frontend
  await ctx.breakpoint({
    question: `Milestone 2 Complete: Metadata API built with ${apiTestRun.passed || 0} passing tests. Endpoints: /metadata/coverage, /metadata/issues, /metadata/corrections, /metadata/primo-urls. Proceed to React frontend?`,
    title: 'Metadata API Review',
    context: { runId: ctx.runId }
  });

  // ============================================================================
  // MILESTONE 3: SPECIALIST AGENTS (Grounding + LLM Reasoning)
  // Field-specific agents that analyze gaps and propose fixes
  // ============================================================================

  ctx.log('info', 'Milestone 3: Specialist Metadata Agents');

  // Task 3.1: Build the agent harness (shared grounding + LLM interface)
  const agentHarness = await ctx.task(buildAgentHarnessTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    outputDir
  });
  artifacts.push(...(agentHarness.artifacts || []));

  // Task 3.2: Build PlaceAgent (vertical slice - most infrastructure exists)
  const placeAgent = await ctx.task(buildPlaceAgentTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    agentHarness,
    outputDir
  });
  artifacts.push(...(placeAgent.artifacts || []));

  // Task 3.3: Build DateAgent
  const dateAgent = await ctx.task(buildDateAgentTask, {
    projectRoot,
    dbPath,
    agentHarness,
    outputDir
  });
  artifacts.push(...(dateAgent.artifacts || []));

  // Task 3.4: Build PublisherAgent
  const publisherAgent = await ctx.task(buildPublisherAgentTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    agentHarness,
    outputDir
  });
  artifacts.push(...(publisherAgent.artifacts || []));

  // Task 3.5: Build AgentAgent (name authority)
  const agentAgent = await ctx.task(buildAgentAgentTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    agentHarness,
    outputDir
  });
  artifacts.push(...(agentAgent.artifacts || []));

  // Task 3.6: Agent integration tests
  const agentTests = await ctx.task(testSpecialistAgentsTask, {
    projectRoot,
    agents: ['place', 'date', 'publisher', 'agent'],
    outputDir
  });
  artifacts.push(...(agentTests.artifacts || []));

  // Task 3.7: Add agent chat endpoint to API
  const agentChatApi = await ctx.task(buildAgentChatApiTask, {
    projectRoot,
    agentHarness,
    outputDir
  });
  artifacts.push(...(agentChatApi.artifacts || []));

  // Breakpoint: Review agents before frontend integration
  await ctx.breakpoint({
    question: `Milestone 3 Complete: 4 specialist agents built (Place, Date, Publisher, Agent) with shared harness. Each agent can analyze gaps, cluster issues, cross-reference evidence, and propose fixes via LLM. Proceed to React frontend?`,
    title: 'Specialist Agents Review',
    context: { runId: ctx.runId }
  });

  // ============================================================================
  // MILESTONE 4: REACT FRONTEND (Dashboard + Workbench + Agent Chat)
  // ============================================================================

  ctx.log('info', 'Milestone 4: React Frontend');

  // Task 4.1: Scaffold React project with Vite + TypeScript
  const reactScaffold = await ctx.task(scaffoldReactProjectTask, {
    projectRoot,
    frontendFramework,
    outputDir
  });
  artifacts.push(...(reactScaffold.artifacts || []));

  // Task 4.2: Build Coverage Dashboard page
  const dashboardPage = await ctx.task(buildDashboardPageTask, {
    projectRoot,
    targetFields,
    outputDir
  });
  artifacts.push(...(dashboardPage.artifacts || []));

  // Task 4.3: Build Issues Workbench page (data tables with inline editing)
  const workbenchPage = await ctx.task(buildWorkbenchPageTask, {
    projectRoot,
    targetFields,
    primoBaseUrl,
    outputDir
  });
  artifacts.push(...(workbenchPage.artifacts || []));

  // Task 4.4: Build Agent Chat page (per-field agent conversations)
  const agentChatPage = await ctx.task(buildAgentChatPageTask, {
    projectRoot,
    targetFields,
    outputDir
  });
  artifacts.push(...(agentChatPage.artifacts || []));

  // Task 4.5: Build Corrections Review page (batch approve/reject)
  const reviewPage = await ctx.task(buildReviewPageTask, {
    projectRoot,
    outputDir
  });
  artifacts.push(...(reviewPage.artifacts || []));

  // Breakpoint: Review frontend before integration testing
  await ctx.breakpoint({
    question: `Milestone 4 Complete: React frontend with 4 pages (Dashboard, Workbench, Agent Chat, Review). Proceed to integration testing?`,
    title: 'React Frontend Review',
    context: { runId: ctx.runId }
  });

  // ============================================================================
  // MILESTONE 5: INTEGRATION & FEEDBACK LOOP
  // End-to-end testing of the complete workflow
  // ============================================================================

  ctx.log('info', 'Milestone 5: Integration & Feedback Loop');

  // Task 5.1: Build the HITL feedback loop (approve → alias map → re-index → coverage update)
  const feedbackLoop = await ctx.task(buildFeedbackLoopTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    outputDir
  });
  artifacts.push(...(feedbackLoop.artifacts || []));

  // Task 5.2: Integration test - full workflow
  const integrationTest = await ctx.task(runIntegrationTestTask, {
    projectRoot,
    dbPath,
    aliasMapDir,
    outputDir
  });
  artifacts.push(...(integrationTest.artifacts || []));

  // Task 5.3: Review log persistence (track approved/rejected/skipped proposals)
  const reviewLog = await ctx.task(buildReviewLogTask, {
    projectRoot,
    outputDir
  });
  artifacts.push(...(reviewLog.artifacts || []));

  // Final breakpoint
  await ctx.breakpoint({
    question: `Milestone 5 Complete: Full integration tested - agent proposes fixes, librarian reviews, corrections applied to alias maps, pipeline re-indexes, coverage updates. Ready to finalize?`,
    title: 'Integration Review',
    context: { runId: ctx.runId }
  });

  // ============================================================================
  // MILESTONE 6: DOCUMENTATION & POLISH
  // ============================================================================

  ctx.log('info', 'Milestone 6: Documentation & Polish');

  const documentation = await ctx.task(writeDocumentationTask, {
    projectRoot,
    outputDir
  });
  artifacts.push(...(documentation.artifacts || []));

  return {
    success: true,
    phases: {
      audit: baselineAudit,
      api: metadataApi,
      agents: { place: placeAgent, date: dateAgent, publisher: publisherAgent, agent: agentAgent },
      frontend: { dashboard: dashboardPage, workbench: workbenchPage, chat: agentChatPage, review: reviewPage },
      integration: integrationTest
    },
    artifacts,
    metadata: {
      processId: 'metadata-copilot-workbench',
      timestamp: startTime,
      targetFields,
      frontendFramework
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

// --- MILESTONE 1: AUDIT ---

const buildAuditModuleTask = defineTask('build-audit-module', (args) => ({
  kind: 'agent',
  title: 'Build normalization coverage audit module',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in bibliographic metadata',
      task: `Build a Python module at scripts/metadata/audit.py that queries the M3 SQLite database and produces a comprehensive normalization coverage report.

The module must:
1. Query the imprints table for date, place, publisher confidence distributions (group by confidence band: 0.0, 0.5, 0.8, 0.95, 0.99)
2. Query the agents table for agent_confidence and role_confidence distributions
3. Count records by normalization method (date_method, place -> via confidence, etc.)
4. Export low-confidence values grouped by frequency (the place appearing 200 times unmapped is higher priority than one appearing once)
5. Flag "unparsed" dates (date_method='unparsed'), unmapped places (place_confidence <= 0.80), ambiguous agents
6. Return a structured CoverageReport dataclass with per-field breakdowns

Key database schema:
- imprints table: date_start, date_end, date_confidence, date_method, place_raw, place_norm, place_confidence, publisher_raw, publisher_norm, publisher_confidence, country_code
- agents table: agent_raw, agent_norm, agent_confidence, agent_method, role_raw, role_norm, role_confidence, role_method

Also create scripts/metadata/__init__.py.

The existing database is at: ${args.dbPath}
Use the python-dev-expert skill patterns: single-purpose functions, type hints, dataclasses, <50 lines per function.
Write tests at tests/scripts/metadata/test_audit.py.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        targetFields: args.targetFields
      },
      instructions: [
        'Read scripts/marc/m3_schema.sql to understand the exact table schemas',
        'Read scripts/marc/normalize.py to understand confidence levels and methods',
        'Create scripts/metadata/audit.py with CoverageReport dataclass',
        'Create scripts/metadata/__init__.py',
        'Write tests at tests/scripts/metadata/test_audit.py',
        'Run the tests to verify they pass'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const runBaselineAuditTask = defineTask('run-baseline-audit', (args) => ({
  kind: 'agent',
  title: 'Run baseline coverage audit and save results',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data analyst',
      task: `Run the coverage audit module against the real database at ${args.dbPath} and save the baseline report.

1. Import and call the audit module built in the previous step
2. Create a CLI entry point: python -m scripts.metadata.audit ${args.dbPath} --output data/metadata/baseline_audit.json
3. Run it against the real database
4. Save output as JSON for the dashboard to consume
5. Print a summary to stdout showing per-field coverage percentages`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath
      },
      instructions: [
        'Read the audit module that was just built',
        'Add a CLI __main__ block or argparse entry point',
        'Create data/metadata/ directory if needed',
        'Run the audit and save results',
        'Verify the JSON output is valid'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildGapClusteringTask = defineTask('build-gap-clustering', (args) => ({
  kind: 'agent',
  title: 'Build gap clustering analysis module',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in text normalization and clustering',
      task: `Build a module at scripts/metadata/clustering.py that takes the low-confidence/unmapped values from the audit and clusters them into actionable groups.

Clustering strategies per field:
- Places: Group by script (Latin, Hebrew, Arabic), by country code, by frequency
- Dates: Group by unparsed pattern type (Hebrew gematria, Latin conventions, ambiguous ranges)
- Publishers: Group by likely canonical form (fuzzy matching against existing alias map)
- Agents: Group by authority URI availability vs. missing

Each cluster should include:
- cluster_id, field, cluster_type (e.g. "latin_place_names", "hebrew_dates")
- raw_values with their frequencies
- proposed_canonical (if determinable without LLM)
- evidence (country codes, existing alias map matches, pattern analysis)
- priority_score (frequency * records_affected)

Write tests at tests/scripts/metadata/test_clustering.py.`,
      context: {
        projectRoot: args.projectRoot,
        targetFields: args.targetFields
      },
      instructions: [
        'Read the existing alias maps at data/normalization/ to understand the mapping patterns',
        'Read the audit module for the data structures',
        'Build clustering logic with deterministic heuristics',
        'Write comprehensive tests',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

// --- MILESTONE 2: FASTAPI METADATA API ---

const buildMetadataApiTask = defineTask('build-metadata-api', (args) => ({
  kind: 'agent',
  title: 'Build FastAPI metadata API router',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer with FastAPI expertise',
      task: `Build a new FastAPI router at app/api/metadata.py and integrate it into the existing app/api/main.py.

Endpoints to implement:
1. GET /metadata/coverage - Overall coverage stats per field (calls audit module)
2. GET /metadata/issues?field=date&max_confidence=0.7&limit=50&offset=0 - Records with low-confidence normalizations, paginated
3. GET /metadata/unmapped?field=place&sort=frequency - Raw values that don't map to any canonical form, sorted by frequency
4. GET /metadata/methods?field=place - Distribution of normalization methods used
5. GET /metadata/clusters?field=place - Gap clusters from the clustering module

The existing FastAPI app is at app/api/main.py. Follow the same patterns (Pydantic models, CORS, error handling).
Database is at ${args.dbPath}.
Use the audit and clustering modules from scripts/metadata/.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        targetFields: args.targetFields
      },
      instructions: [
        'Read app/api/main.py to understand existing patterns',
        'Read app/api/models.py for Pydantic model conventions',
        'Create app/api/metadata.py as a new APIRouter',
        'Add Pydantic response models',
        'Register the router in main.py',
        'Ensure CORS is properly configured for frontend access'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildCorrectionsApiTask = defineTask('build-corrections-api', (args) => ({
  kind: 'agent',
  title: 'Build corrections submission endpoint',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer',
      task: `Add corrections endpoints to the metadata API router at app/api/metadata.py:

1. POST /metadata/corrections - Submit a correction (raw_value -> canonical mapping for a field)
   - Input: { field: str, raw_value: str, canonical_value: str, evidence: str, source: "human"|"agent" }
   - Writes to the appropriate alias map JSON file in ${args.aliasMapDir}
   - Returns: { success: bool, alias_map_updated: str, records_affected: int }

2. GET /metadata/corrections/history - List of applied corrections with timestamps
   - Stored in a new review_log.jsonl file at data/metadata/review_log.jsonl

3. POST /metadata/corrections/batch - Batch approve multiple corrections at once

The corrections must:
- Write to the correct alias map (place_alias_map.json, publisher_alias_map.json, agent_alias_map.json)
- Log every correction to the review log
- Never overwrite existing mappings without explicit confirmation
- Count affected records by querying the database`,
      context: {
        projectRoot: args.projectRoot,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read the existing alias map files to understand their structure',
        'Implement atomic file writes (write to .tmp then rename)',
        'Add the review log append logic',
        'Write tests for the corrections endpoint',
        'Verify alias map read/write works correctly'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildPrimoApiTask = defineTask('build-primo-api', (args) => ({
  kind: 'agent',
  title: 'Build Primo URL batch generation endpoint',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer',
      task: `Add a Primo URL generation endpoint to the metadata API:

1. POST /metadata/primo-urls - Given a list of MMS IDs, return Primo discovery URLs
   - Input: { mms_ids: List[str], base_url?: str }
   - Output: { urls: List[{mms_id: str, primo_url: str}] }

2. GET /metadata/records/{mms_id}/primo - Single record Primo URL

Check how Primo links are generated in the existing Streamlit UI at app/ui_chat/ for the URL pattern.
The base URL should be configurable via environment variable PRIMO_BASE_URL.`,
      context: {
        projectRoot: args.projectRoot,
        primoBaseUrl: args.primoBaseUrl
      },
      instructions: [
        'Read app/ui_chat/ to find existing Primo URL generation logic',
        'Implement the endpoint in app/api/metadata.py',
        'Make the base URL configurable',
        'Write tests'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const testMetadataApiTask = defineTask('test-metadata-api', (args) => ({
  kind: 'agent',
  title: 'Write comprehensive API tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python test engineer',
      task: `Write comprehensive tests for the metadata API at tests/app/test_metadata_api.py.

Cover:
1. GET /metadata/coverage - returns valid coverage report
2. GET /metadata/issues - filters by field and confidence
3. GET /metadata/unmapped - returns frequency-sorted results
4. POST /metadata/corrections - writes to alias map correctly
5. POST /metadata/corrections/batch - batch corrections work
6. GET /metadata/primo-urls - generates valid URLs
7. Error cases (invalid field, missing parameters)

Use the same test patterns as tests/app/test_api.py (httpx AsyncClient with TestClient).
Tests should work without a real database (use fixtures/mocks where needed).`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read tests/app/test_api.py for existing test patterns',
        'Write tests using pytest and httpx',
        'Run the tests to verify they pass'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const runApiTestsShellTask = defineTask('run-api-tests', (args) => ({
  kind: 'shell',
  title: 'Run metadata API tests',
  command: `cd ${args.projectRoot} && python -m pytest tests/app/test_metadata_api.py -v --tb=short 2>&1 | head -50`,
  timeout: 60000
}));

// --- MILESTONE 3: SPECIALIST AGENTS ---

const buildAgentHarnessTask = defineTask('build-agent-harness', (args) => ({
  kind: 'agent',
  title: 'Build shared agent harness for specialist metadata agents',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python AI engineer building grounded LLM agent systems',
      task: `Build the shared agent harness at scripts/metadata/agent_harness.py.

This harness provides the foundation for all specialist agents. It has TWO layers:

1. GROUNDING LAYER (deterministic, no LLM):
   - query_gaps(field, max_confidence) -> List[GapRecord] - Query M3 DB for low-confidence records
   - query_alias_map(field) -> Dict - Load current alias mappings
   - query_country_codes(mms_ids) -> Dict[str, str] - Cross-reference MARC country codes
   - query_authority_uris(mms_ids) -> Dict[str, str] - Get authority URIs from agents table
   - cluster_values(raw_values, field) -> List[Cluster] - Use clustering module
   - count_affected_records(raw_value, field) -> int - How many records have this value

2. REASONING LAYER (LLM-assisted):
   - propose_mapping(raw_value, field, evidence) -> ProposedMapping - Ask LLM for canonical mapping with evidence
   - explain_cluster(cluster) -> str - LLM explains why values are related
   - suggest_investigation(cluster) -> str - LLM suggests next steps

The LLM calls must use STRICT system prompts:
- "You are a bibliographic metadata specialist. Given the following raw MARC value and evidence, propose the canonical English form."
- System prompt must include: the existing alias map entries as context, the country code if available, the raw value
- Response format must be structured JSON with: canonical_value, confidence, reasoning
- If uncertain: return confidence < 0.7 and reasoning explaining why

Use OpenAI API (same pattern as scripts/query/compile.py for the LLM calls).
Cache LLM responses at data/metadata/agent_llm_cache.jsonl.

Data models:
- GapRecord: mms_id, field, raw_value, current_norm, confidence, method, country_code
- ProposedMapping: raw_value, canonical_value, confidence, reasoning, evidence_sources
- Cluster: cluster_id, field, cluster_type, values, proposed_canonical, priority_score

Write tests at tests/scripts/metadata/test_agent_harness.py.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read scripts/query/compile.py to understand the LLM call pattern',
        'Read scripts/marc/normalize.py for field-specific normalization logic',
        'Read data/normalization/place_aliases/place_alias_map.json for alias map structure',
        'Build grounding layer with pure database queries',
        'Build reasoning layer with strict system prompts',
        'Implement LLM response caching',
        'Write comprehensive tests (mock LLM calls in tests)',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildPlaceAgentTask = defineTask('build-place-agent', (args) => ({
  kind: 'agent',
  title: 'Build PlaceAgent - specialist for place normalization',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python AI engineer with knowledge of historical geography and Latin toponyms',
      task: `Build the PlaceAgent at scripts/metadata/agents/place_agent.py.

The PlaceAgent knows:
- Latin toponyms (Lugduni Batavorum -> Leiden, Augustae Vindelicorum -> Augsburg)
- Hebrew place names (אמשטרדם -> Amsterdam, לובלין -> Lublin)
- Historical place name changes
- MARC country code cross-referencing (country code "ne" -> Netherlands, "gw" -> Germany)

PlaceAgent methods:
- analyze() -> PlaceAnalysis: Run full coverage analysis for places
- get_clusters() -> List[PlaceCluster]: Group unmapped places by type (Latin, Hebrew, unclear)
- propose_mappings(cluster_id) -> List[ProposedMapping]: LLM-assisted proposals for a cluster
- get_primo_links(raw_value) -> List[str]: Generate Primo links for records with this place value

The LLM system prompt for place analysis must include:
- Current alias map entries as vocabulary
- Available country codes as evidence
- Instruction to recognize Latin genitive/nominative/ablative forms
- Instruction to recognize Hebrew/Arabic script place names
- Instruction to check if the proposed place matches the country code

Uses the shared agent_harness for all data access and LLM calls.
Write tests at tests/scripts/metadata/agents/test_place_agent.py.`,
      context: {
        projectRoot: args.projectRoot,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read the agent harness module built in the previous step',
        'Read data/normalization/place_aliases/place_alias_map.json for existing mappings',
        'Read data/normalization/marc_country_codes.json for country code reference',
        'Build the PlaceAgent class using the harness',
        'Write tests with mocked LLM responses',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildDateAgentTask = defineTask('build-date-agent', (args) => ({
  kind: 'agent',
  title: 'Build DateAgent - specialist for date normalization',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python AI engineer with knowledge of historical dating conventions',
      task: `Build the DateAgent at scripts/metadata/agents/date_agent.py.

The DateAgent knows:
- Hebrew calendar dates and Gematria (תק"ע -> 5570 -> 1810 CE)
- Latin date conventions (ante, circa, post)
- Date ranges and approximate dates
- Publication date patterns by era

DateAgent methods:
- analyze() -> DateAnalysis: Run full coverage analysis for dates
- get_unparsed() -> List[UnparsedDate]: All dates with method="unparsed" or confidence < 0.8
- propose_dates(batch) -> List[ProposedDate]: LLM-assisted date proposals
- group_by_pattern() -> Dict[str, List]: Group unparsed dates by pattern type

The LLM system prompt for date analysis must include:
- The 6 deterministic patterns already handled (to avoid re-proposing known patterns)
- Hebrew calendar conversion rules
- Instruction to provide date_start, date_end, method, confidence

Uses the shared agent_harness.
Write tests at tests/scripts/metadata/agents/test_date_agent.py.`,
      context: {
        projectRoot: args.projectRoot
      },
      instructions: [
        'Read scripts/marc/normalize.py to understand the 6 existing date patterns',
        'Read the agent harness for data access patterns',
        'Build the DateAgent class',
        'Write tests with mocked LLM responses',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildPublisherAgentTask = defineTask('build-publisher-agent', (args) => ({
  kind: 'agent',
  title: 'Build PublisherAgent - specialist for publisher normalization',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python AI engineer with knowledge of early modern printing history',
      task: `Build the PublisherAgent at scripts/metadata/agents/publisher_agent.py.

The PublisherAgent knows:
- Publisher name patterns and printer dynasties (Plantin, Elzevir, Aldus)
- Latin/vernacular variants (ex officina Plantiniana -> Plantin press)
- Publisher abbreviation patterns
- Clustering related publisher names

PublisherAgent methods:
- analyze() -> PublisherAnalysis
- get_clusters() -> List[PublisherCluster]
- propose_mappings(cluster_id) -> List[ProposedMapping]
- find_related(canonical_name) -> List[str]: Find all variants of a known publisher

Uses the shared agent_harness.
Write tests at tests/scripts/metadata/agents/test_publisher_agent.py.`,
      context: {
        projectRoot: args.projectRoot,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read existing publisher alias map if it exists',
        'Read the agent harness',
        'Build the PublisherAgent class',
        'Write tests',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildAgentAgentTask = defineTask('build-agent-agent', (args) => ({
  kind: 'agent',
  title: 'Build AgentAgent - specialist for name authority normalization',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python AI engineer with knowledge of library authority files and name conventions',
      task: `Build the AgentAgent at scripts/metadata/agents/name_agent.py.

The AgentAgent (name authority agent) knows:
- Name authority conventions (VIAF, NLI, LCNAF)
- How to leverage authority URIs from MARC $0 subfields
- Name form standardization (Last, First vs First Last)
- Role code mapping

AgentAgent methods:
- analyze() -> AgentAnalysis
- get_without_authority() -> List[AgentRecord]: Agents missing authority URIs
- get_low_confidence() -> List[AgentRecord]: Agents with low confidence normalization
- propose_authority_match(agent_raw) -> ProposedAuthority: Suggest authority URI based on existing enrichment data
- validate_against_authority(mms_ids) -> List[ValidationResult]: Compare normalized names against authority canonical forms

Cross-references the authority_enrichment table for Wikidata/VIAF/NLI data.
Uses the shared agent_harness.
Write tests at tests/scripts/metadata/agents/test_name_agent.py.`,
      context: {
        projectRoot: args.projectRoot,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read the agent harness',
        'Read scripts/enrichment/enrichment_service.py for authority data patterns',
        'Read scripts/marc/m3_schema.sql for the authority_enrichment table',
        'Build the AgentAgent class',
        'Write tests',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const testSpecialistAgentsTask = defineTask('test-specialist-agents', (args) => ({
  kind: 'shell',
  title: 'Run all specialist agent tests',
  command: `cd ${args.projectRoot} && python -m pytest tests/scripts/metadata/agents/ -v --tb=short 2>&1 | head -60`,
  timeout: 60000
}));

const buildAgentChatApiTask = defineTask('build-agent-chat-api', (args) => ({
  kind: 'agent',
  title: 'Build agent chat endpoint for frontend integration',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer',
      task: `Add an agent chat endpoint to app/api/metadata.py:

POST /metadata/agent/chat
- Input: { field: str, message: str, session_id?: str }
- Routes to the appropriate specialist agent (PlaceAgent, DateAgent, etc.)
- Agent processes the message using grounding layer + LLM reasoning
- Returns: { response: str, proposals: List[ProposedMapping], clusters: List[Cluster] }

The agent should:
- If message is empty or "analyze": run full analysis and return clusters
- If message references a cluster: propose mappings for that cluster
- If message is a question: answer using grounding layer data + LLM reasoning
- Always include evidence and Primo links in responses

Also add WebSocket endpoint for streaming agent responses:
WS /ws/metadata/agent
- Same protocol as existing /ws/chat endpoint`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read app/api/main.py for the existing WebSocket pattern',
        'Read the specialist agent modules',
        'Implement the REST and WebSocket endpoints',
        'Write tests',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

// --- MILESTONE 4: REACT FRONTEND ---

const scaffoldReactProjectTask = defineTask('scaffold-react', (args) => ({
  kind: 'agent',
  title: 'Scaffold React project with Vite + TypeScript',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React frontend developer',
      task: `Create a React application at frontend/ in the project root using Vite + TypeScript.

Stack:
- React 18+ with TypeScript
- Vite for build tooling
- TanStack Table (or AG Grid Community) for data tables
- TanStack Query for API state management
- React Router for navigation
- Tailwind CSS for styling
- Recharts for dashboard charts

Project structure:
frontend/
  src/
    components/      # Shared UI components
    pages/           # Page components (Dashboard, Workbench, AgentChat, Review)
    api/             # API client functions
    types/           # TypeScript types matching backend Pydantic models
    hooks/           # Custom React hooks
    App.tsx
    main.tsx
  vite.config.ts     # With proxy to FastAPI backend
  package.json
  tsconfig.json

Set up the Vite proxy to forward /api/* and /metadata/* to localhost:8000.
Create a basic layout with sidebar navigation between the 4 pages.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Use npm create vite@latest with react-ts template',
        'Install all dependencies',
        'Set up the project structure',
        'Create the layout with sidebar navigation',
        'Verify the dev server starts successfully'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildDashboardPageTask = defineTask('build-dashboard-page', (args) => ({
  kind: 'agent',
  title: 'Build Coverage Dashboard page',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React frontend developer with data visualization experience',
      task: `Build the Coverage Dashboard page at frontend/src/pages/Dashboard.tsx.

The dashboard shows:
1. Summary cards: Total records, % normalized per field, overall data quality score
2. Per-field coverage bars: For each field (date, place, publisher, agent), show a stacked bar with confidence bands (high/medium/low/unmapped)
3. Gap summary: Cards showing "423 records have unparsed dates", "87 places unmapped", etc.
4. Method distribution charts: Pie/donut charts showing which normalization methods are used per field
5. Trend indicator: If a previous audit exists, show improvement/regression

Data source: GET /metadata/coverage API endpoint.
Use Recharts for charts, TanStack Query for data fetching.
Make each gap card clickable - navigates to the Workbench filtered by that field.`,
      context: {
        projectRoot: args.projectRoot,
        targetFields: args.targetFields
      },
      instructions: [
        'Create the API client function in frontend/src/api/metadata.ts',
        'Create TypeScript types matching the backend response models',
        'Build the Dashboard page with responsive layout',
        'Add loading states and error handling',
        'Verify it compiles without errors'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildWorkbenchPageTask = defineTask('build-workbench-page', (args) => ({
  kind: 'agent',
  title: 'Build Issues Workbench page with data tables',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React frontend developer with complex data table experience',
      task: `Build the Issues Workbench page at frontend/src/pages/Workbench.tsx.

The workbench is where the librarian reviews and fixes normalization issues:

1. Field selector tabs: Date | Place | Publisher | Agent | Subject
2. Data table (TanStack Table):
   - Columns: MMS ID, Raw Value, Current Normalized, Confidence, Method, Country Code, Primo Link
   - Sortable by any column
   - Filterable by confidence range, method, unmapped status
   - Paginated (50 records per page)
   - Row selection for batch operations
3. Inline editing: Click on "Current Normalized" to edit the canonical value
4. Batch operations toolbar:
   - "Apply correction to all selected" - opens modal for canonical value entry
   - "Export selected to CSV"
   - "Generate Primo links for selected"
5. Cluster view toggle: Switch between individual records and clustered view (groups related values)

Data source: GET /metadata/issues and GET /metadata/clusters API endpoints.
Corrections submitted via POST /metadata/corrections.`,
      context: {
        projectRoot: args.projectRoot,
        targetFields: args.targetFields,
        primoBaseUrl: args.primoBaseUrl
      },
      instructions: [
        'Build the TanStack Table with proper column definitions',
        'Implement filtering and sorting',
        'Add inline editing with confirmation',
        'Build batch operations toolbar',
        'Connect to the API endpoints',
        'Verify it compiles'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildAgentChatPageTask = defineTask('build-agent-chat-page', (args) => ({
  kind: 'agent',
  title: 'Build Agent Chat page for specialist agent conversations',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React frontend developer with chat UI experience',
      task: `Build the Agent Chat page at frontend/src/pages/AgentChat.tsx.

This is where the librarian has conversations with specialist agents:

1. Agent selector: Dropdown or tabs to select which agent (Place, Date, Publisher, Agent, Subject)
2. Chat interface:
   - Message history with user/agent messages
   - Agent messages can include:
     - Text explanations
     - Proposed mappings table (with Approve/Reject/Edit buttons per row)
     - Cluster summaries with expandable details
     - Primo links as clickable elements
   - User can type free-form messages or click suggested actions
3. Proposal actions:
   - [Approve] -> submits correction to API
   - [Approve All] -> batch correction
   - [Reject] -> logged to review log
   - [Edit] -> opens inline editor, then submit
4. Session state: Track what clusters have been reviewed, approved, skipped
5. Coverage sidebar: Show real-time coverage stats that update as corrections are applied

Data source: POST /metadata/agent/chat (or WebSocket /ws/metadata/agent).
Corrections via POST /metadata/corrections.`,
      context: {
        projectRoot: args.projectRoot,
        targetFields: args.targetFields
      },
      instructions: [
        'Build the chat UI with message rendering',
        'Handle structured agent responses (proposals, clusters)',
        'Implement approve/reject/edit actions',
        'Connect to the agent chat API endpoint',
        'Add real-time coverage update sidebar',
        'Verify it compiles'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildReviewPageTask = defineTask('build-review-page', (args) => ({
  kind: 'agent',
  title: 'Build Corrections Review page',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'React frontend developer',
      task: `Build the Corrections Review page at frontend/src/pages/Review.tsx.

This page shows the history of all corrections:

1. Timeline view: Chronological list of all corrections applied
2. Filters: By field, by source (human/agent), by date range
3. Impact metrics: For each correction, show records affected
4. Undo capability: Button to remove a mapping from the alias map
5. Export: Download the review log as CSV/JSON

Data source: GET /metadata/corrections/history API endpoint.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Build the review page with timeline view',
        'Add filtering and search',
        'Implement undo capability',
        'Add export functionality',
        'Verify it compiles'
      ],
      outputFormat: 'JSON'
    }
  }
}));

// --- MILESTONE 5: INTEGRATION ---

const buildFeedbackLoopTask = defineTask('build-feedback-loop', (args) => ({
  kind: 'agent',
  title: 'Build the HITL feedback loop (approve -> alias map -> re-index -> coverage update)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python backend developer',
      task: `Build the end-to-end feedback loop at scripts/metadata/feedback_loop.py.

When a correction is approved:
1. Write the new mapping to the alias map JSON file (atomic write)
2. Trigger re-normalization of affected records (using scripts/marc/normalize.py)
3. Update the M3 database with new normalized values
4. Recalculate coverage stats
5. Log the change to review_log.jsonl

This should be callable both from the API (immediate) and as a batch process.

Also create a CLI command: python -m scripts.metadata.feedback_loop --apply-pending
that processes any pending corrections from the review queue.

Key constraint: The pipeline (M2 normalize -> M3 index) must be re-runnable incrementally,
not requiring a full rebuild. Check if rebuild_pipeline.py supports incremental mode, otherwise
build an incremental re-normalization function.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Read scripts/marc/rebuild_pipeline.py for the full pipeline',
        'Read scripts/marc/normalize.py for normalization functions',
        'Build the feedback loop with atomic alias map writes',
        'Implement incremental re-normalization',
        'Write tests',
        'Run tests to verify'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const runIntegrationTestTask = defineTask('run-integration-test', (args) => ({
  kind: 'agent',
  title: 'Run full integration test of the complete workflow',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer',
      task: `Create and run an integration test at tests/integration/test_metadata_workbench.py that validates the complete workflow:

1. Run coverage audit -> verify report structure
2. Run gap clustering -> verify clusters are created
3. Call specialist agent (PlaceAgent) -> verify it returns proposals
4. Submit a correction via API -> verify alias map is updated
5. Trigger feedback loop -> verify database is updated
6. Re-run coverage audit -> verify coverage improved

This test should use a test database (copy of the real one or a fixture).
Mark it with @pytest.mark.integration so it can be run separately.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        aliasMapDir: args.aliasMapDir
      },
      instructions: [
        'Create the test file',
        'Use a temporary copy of the database for isolation',
        'Test the full workflow end-to-end',
        'Run the test',
        'Report results'
      ],
      outputFormat: 'JSON'
    }
  }
}));

const buildReviewLogTask = defineTask('build-review-log', (args) => ({
  kind: 'agent',
  title: 'Build review log persistence',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer',
      task: `Build the review log module at scripts/metadata/review_log.py.

The review log tracks every correction decision:
- Timestamp, field, raw_value, canonical_value, source (human/agent), action (approved/rejected/edited/skipped)
- Stored as append-only JSONL at data/metadata/review_log.jsonl
- Query functions: get_history(field?, date_range?), get_rejected() (so agents don't re-propose), count_by_action()

This log serves two purposes:
1. Audit trail for corrections
2. Negative signal - rejected proposals should not be re-proposed by agents`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Build the review log module with append-only JSONL',
        'Add query functions',
        'Integrate with the corrections API and agent harness',
        'Write tests'
      ],
      outputFormat: 'JSON'
    }
  }
}));

// --- MILESTONE 6: DOCUMENTATION ---

const writeDocumentationTask = defineTask('write-documentation', (args) => ({
  kind: 'agent',
  title: 'Write workbench documentation and update CLAUDE.md',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer',
      task: `Write documentation for the Metadata Co-pilot Workbench:

1. Update CLAUDE.md with a new "Metadata Co-pilot Workbench" section covering:
   - Architecture overview
   - API endpoints
   - Specialist agents
   - Frontend pages
   - Feedback loop workflow

2. Create docs/metadata_workbench.md with:
   - Getting started guide
   - Librarian workflow walkthrough
   - Agent interaction examples
   - Configuration (Primo URL, API keys)

Keep documentation concise and practical.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read the current CLAUDE.md',
        'Add the new section',
        'Create the detailed docs file',
        'Verify the documentation is accurate'
      ],
      outputFormat: 'JSON'
    }
  }
}));
