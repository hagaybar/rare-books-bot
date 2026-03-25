/**
 * @process empirical-verification
 * @description Empirical verification of UI redesign alignment with actual data structures,
 * query pipeline behavior, API responses, and chatbot conversation flow.
 * Probes the real database, runs real queries, tests real API endpoints,
 * and cross-references findings against proposed UI screens.
 * If misalignments are found, refines the existing reports.
 * @inputs { projectRoot: string, prompt: string }
 * @outputs { success: boolean, findings: object, reportUpdates: array }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    prompt = ''
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting Empirical Verification Process');

  // ============================================================================
  // PHASE 1: DATABASE SHAPE & DATA QUALITY PROBE
  // ============================================================================

  ctx.log('info', 'Phase 1: Probing actual database structure, field populations, confidence distributions');

  const dbProbeResult = await ctx.task(databaseProbeTask, {
    projectRoot,
    dbPath: `${projectRoot}/data/index/bibliographic.db`
  });

  artifacts.push({ path: 'reports/08-empirical-db-probe.md', format: 'markdown' });

  // ============================================================================
  // PHASE 2: QUERY PIPELINE END-TO-END TEST
  // ============================================================================

  ctx.log('info', 'Phase 2: Running real queries through the pipeline, capturing QueryPlan/CandidateSet/Evidence');

  const pipelineTestResult = await ctx.task(queryPipelineTestTask, {
    projectRoot,
    dbPath: `${projectRoot}/data/index/bibliographic.db`,
    dbProbe: dbProbeResult
  });

  artifacts.push({ path: 'reports/09-empirical-pipeline-test.md', format: 'markdown' });

  // ============================================================================
  // PHASE 3: API RESPONSE STRUCTURE VERIFICATION
  // ============================================================================

  ctx.log('info', 'Phase 3: Verifying actual API response structures from FastAPI endpoints');

  const apiVerifyResult = await ctx.task(apiResponseVerifyTask, {
    projectRoot,
    dbProbe: dbProbeResult,
    pipelineTest: pipelineTestResult
  });

  artifacts.push({ path: 'reports/10-empirical-api-verify.md', format: 'markdown' });

  // ============================================================================
  // PHASE 4: CROSS-REFERENCE & MISALIGNMENT DETECTION
  // ============================================================================

  ctx.log('info', 'Phase 4: Cross-referencing empirical findings with proposed UI screens');

  const crossRefResult = await ctx.task(crossReferenceTask, {
    projectRoot,
    dbProbe: dbProbeResult,
    pipelineTest: pipelineTestResult,
    apiVerify: apiVerifyResult
  });

  artifacts.push({ path: 'reports/11-empirical-cross-reference.md', format: 'markdown' });

  // ============================================================================
  // PHASE 5: REPORT REFINEMENT (if needed)
  // ============================================================================

  ctx.log('info', 'Phase 5: Refining existing reports based on empirical findings');

  const refinementResult = await ctx.task(reportRefinementTask, {
    projectRoot,
    dbProbe: dbProbeResult,
    pipelineTest: pipelineTestResult,
    apiVerify: apiVerifyResult,
    crossRef: crossRefResult
  });

  artifacts.push({ path: 'reports/12-empirical-refinements.md', format: 'markdown' });

  const endTime = ctx.now();

  return {
    success: true,
    findings: {
      dbProbe: dbProbeResult,
      pipelineTest: pipelineTestResult,
      apiVerify: apiVerifyResult,
      crossRef: crossRefResult,
      refinements: refinementResult
    },
    reportUpdates: refinementResult.updatedReports || [],
    artifacts,
    duration: endTime - startTime,
    metadata: {
      processId: 'empirical-verification',
      timestamp: startTime
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const databaseProbeTask = defineTask('database-probe', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 1: Probe actual database structure and data quality',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data Engineer conducting empirical database analysis',
      task: `Query the SQLite database at ${args.dbPath} to understand the ACTUAL data shape, field population rates, confidence distributions, and sparsity patterns. This is not code reading — this is running real SQL queries against real data.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        tables: ['records', 'imprints', 'titles', 'subjects', 'agents', 'languages', 'notes', 'publisher_authorities', 'publisher_variants', 'authority_enrichment']
      },
      instructions: [
        '1. Run SQL queries against the actual bibliographic.db database using sqlite3 CLI',
        '2. For each table: count rows, count distinct values, identify null rates for every column',
        '3. For the imprints table specifically:',
        '   a. Count records with non-null date_start vs total (date coverage %)',
        '   b. Count records with non-null place_norm vs total (place coverage %)',
        '   c. Count records with non-null publisher_norm vs total (publisher coverage %)',
        '   d. Distribution of date_confidence values (histogram buckets: 0-0.5, 0.5-0.8, 0.8-0.95, 0.95-1.0)',
        '   e. Distribution of place_confidence values (same buckets)',
        '   f. Distribution of publisher_confidence values (same buckets)',
        '   g. Distribution of date_method values (count per method)',
        '   h. Distribution of place_method values',
        '   i. Top 20 most common place_norm values with counts',
        '   j. Top 20 most common publisher_norm values with counts',
        '   k. Date range: min(date_start) to max(date_end)',
        '4. For titles: count distinct titles, average titles per record',
        '5. For subjects: count distinct subjects, average subjects per record, top 20 subjects',
        '6. For agents: count distinct agent names, average agents per record, agent role distribution',
        '7. For publisher_authorities and publisher_variants: count authorities, count variants, how many imprints match',
        '8. Check for data anomalies: records with 0 imprints, records with 0 titles, null MMS IDs',
        '9. Sample 5 complete records (all joins) to show what a "full record" actually looks like',
        '10. Write ALL findings with actual SQL queries and results to reports/08-empirical-db-probe.md',
        '11. Return structured JSON with key metrics'
      ],
      outputFormat: 'JSON with tableCounts, coverageRates, confidenceDistributions, topValues, anomalies, sampleRecords'
    },
    outputSchema: {
      type: 'object',
      required: ['tableCounts', 'coverageRates', 'confidenceDistributions'],
      properties: {
        tableCounts: { type: 'object' },
        coverageRates: { type: 'object' },
        confidenceDistributions: { type: 'object' },
        topValues: { type: 'object' },
        anomalies: { type: 'array' },
        sampleRecords: { type: 'array' },
        dateRange: { type: 'object' },
        summary: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['empirical', 'database', 'data-quality']
}));

export const queryPipelineTestTask = defineTask('query-pipeline-test', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Run real queries through the pipeline',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA Engineer testing the query pipeline end-to-end with real data',
      task: `Run real queries through the Rare Books Bot query pipeline using the CLI and Python scripts directly. Capture actual QueryPlan, SQL, CandidateSet, and Evidence structures. Do NOT read code — EXECUTE real queries.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        dbProbe: args.dbProbe
      },
      instructions: [
        '1. Use the CLI to run at least 5 different real queries against the actual database:',
        '   a. "books published in Amsterdam" (place filter)',
        '   b. "books from the 16th century" (date range filter)',
        '   c. "books by Elsevier" (publisher filter)',
        '   d. "books about medicine" (subject filter)',
        '   e. "Hebrew books printed in Venice before 1600" (multi-filter)',
        '2. For each query, capture and document:',
        '   a. The full QueryPlan JSON (what filters were extracted)',
        '   b. The generated SQL query',
        '   c. The CandidateSet (how many results, what MMS IDs)',
        '   d. The Evidence structure for the first 3 results (what fields matched, confidence)',
        '3. Run queries using: cd /home/hagaybar/projects/rare-books-bot && python -m app.cli query "<query>" 2>&1',
        '4. Also run a query directly via Python to inspect internal structures:',
        '   python3 -c "import sys; sys.path.insert(0,\\".\\"); from scripts.query.service import QueryService; from pathlib import Path; qs = QueryService(Path(\\"data/index/bibliographic.db\\")); result = qs.execute(\\"books published in Amsterdam\\"); print(type(result)); print(dir(result))"',
        '5. Examine the output files in data/runs/ to understand artifact structure',
        '6. Test edge cases: empty results query, very broad query, single-word query',
        '7. Check if evidence contains MARC field references as documented',
        '8. Check what confidence scores actually look like in results',
        '9. Write ALL findings with actual command outputs to reports/09-empirical-pipeline-test.md',
        '10. Return structured JSON with queryResults array'
      ],
      outputFormat: 'JSON with queryResults array, each containing query, planShape, sqlShape, resultCount, evidenceShape, issues'
    },
    outputSchema: {
      type: 'object',
      required: ['queryResults'],
      properties: {
        queryResults: { type: 'array' },
        edgeCases: { type: 'array' },
        structureFindings: { type: 'object' },
        issues: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['empirical', 'pipeline', 'query']
}));

export const apiResponseVerifyTask = defineTask('api-response-verify', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 3: Verify actual API response structures',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'API Integration Engineer verifying actual response structures',
      task: `Verify the actual shapes of API responses from the FastAPI backend by reading the API code and the Pydantic models that define them. Since we cannot start the server in this context, we must trace the code path from endpoint to response model to understand what the frontend actually receives.`,
      context: {
        projectRoot: args.projectRoot,
        dbProbe: args.dbProbe,
        pipelineTest: args.pipelineTest
      },
      instructions: [
        '1. Read the FastAPI endpoint code in app/api/main.py and app/api/metadata.py',
        '2. Read the Pydantic response models in app/api/models.py and app/api/metadata_models.py',
        '3. Read the chat models in scripts/chat/models.py',
        '4. For each key endpoint, document the ACTUAL response shape:',
        '   a. POST /chat — what does ChatResponse actually contain? What is the candidate structure?',
        '   b. GET /metadata/coverage — what fields and structure?',
        '   c. GET /metadata/issues — what does an issue record look like?',
        '   d. POST /metadata/corrections — request and response shapes',
        '   e. POST /metadata/agent/chat — what does the agent response look like?',
        '   f. GET /metadata/publishers — publisher authority response shape',
        '   g. WS /ws/chat — what message types and shapes are streamed?',
        '   h. GET /health — what exactly is returned?',
        '5. For the chat endpoint specifically:',
        '   a. Trace the two-phase conversation flow: what does Phase 1 return vs Phase 2?',
        '   b. What does the intent agent return? What confidence structure?',
        '   c. What evidence structure is in each candidate?',
        '   d. What does clarification_needed look like?',
        '6. Compare what the API ACTUALLY returns vs what the proposed UI screens expect',
        '7. Identify gaps: fields the UI expects but the API does not provide',
        '8. Identify surprises: fields the API provides that were not considered in UI design',
        '9. Write ALL findings to reports/10-empirical-api-verify.md',
        '10. Return structured JSON'
      ],
      outputFormat: 'JSON with endpointShapes, gaps, surprises, recommendations'
    },
    outputSchema: {
      type: 'object',
      required: ['endpointShapes'],
      properties: {
        endpointShapes: { type: 'object' },
        gaps: { type: 'array' },
        surprises: { type: 'array' },
        recommendations: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['empirical', 'api', 'verification']
}));

export const crossReferenceTask = defineTask('cross-reference', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 4: Cross-reference empirical findings with proposed UI',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Product-Data Alignment Analyst identifying misalignments between actual data and proposed UI',
      task: `Cross-reference the empirical findings (database probe, pipeline test, API verification) against the proposed 9-screen UI design from reports/06-new-ui-definition.md. Identify every misalignment, wrong assumption, or missing data dependency.`,
      context: {
        projectRoot: args.projectRoot,
        dbProbe: args.dbProbe,
        pipelineTest: args.pipelineTest,
        apiVerify: args.apiVerify,
        proposedScreens: [
          '/ Chat — conversational discovery with two-phase flow, evidence, streaming',
          '/operator/coverage — coverage bars, confidence distributions, gap cards',
          '/operator/workbench — issue table with inline editing, batch corrections',
          '/operator/agent — specialist agent chat with proposals',
          '/operator/review — correction audit trail',
          '/diagnostics/query — query plan, SQL, results, labeling, gold sets',
          '/diagnostics/db — database table browser',
          '/admin/publishers — publisher authorities',
          '/admin/health — system health'
        ]
      },
      instructions: [
        '1. Read the proposed UI definition from reports/06-new-ui-definition.md',
        '2. For each of the 9 proposed screens, check:',
        '   a. Does the data actually exist to populate this screen?',
        '   b. Does the API actually provide the needed endpoints and response shapes?',
        '   c. Are the confidence distributions what we assumed? (e.g., do coverage bars make sense if 90% of data is at one confidence level?)',
        '   d. Does the evidence structure support the proposed evidence chain display?',
        '   e. Are there fields the UI assumes but the data/API does not provide?',
        '3. Specifically verify:',
        '   a. Chat screen: Does the two-phase conversation actually return what we expect? Is evidence rich enough for the proposed display?',
        '   b. Coverage Dashboard: Are coverage percentages meaningful given actual distributions?',
        '   c. Issues Workbench: Are there actually enough low-confidence records to warrant a dedicated screen?',
        '   d. Query Debugger: Does the QueryPlan structure support the proposed three-panel view?',
        '   e. Agent Chat: Do the agent responses have the structure the UI expects?',
        '4. Rate each screen alignment: CONFIRMED / PARTIALLY_ALIGNED / MISALIGNED',
        '5. For each misalignment, specify: what was assumed, what is actual, impact, recommendation',
        '6. Write comprehensive findings to reports/11-empirical-cross-reference.md',
        '7. Return structured JSON'
      ],
      outputFormat: 'JSON with screenAlignments array (name, rating, assumptions, actuals, gaps, recommendations)'
    },
    outputSchema: {
      type: 'object',
      required: ['screenAlignments'],
      properties: {
        screenAlignments: { type: 'array' },
        criticalMisalignments: { type: 'array' },
        confirmedAssumptions: { type: 'array' },
        overallVerdict: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['empirical', 'cross-reference', 'alignment']
}));

export const reportRefinementTask = defineTask('report-refinement', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 5: Refine reports based on empirical findings',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical Writer and Product Architect refining UI recommendations based on empirical evidence',
      task: `Based on the empirical verification findings, refine the existing reports. Update the executive report (00), the new UI definition (06), and the migration plan (07) with corrections, additions, or caveats discovered through empirical testing.`,
      context: {
        projectRoot: args.projectRoot,
        dbProbe: args.dbProbe,
        pipelineTest: args.pipelineTest,
        apiVerify: args.apiVerify,
        crossRef: args.crossRef,
        reportsToRefine: [
          'reports/00-executive-report.md',
          'reports/06-new-ui-definition.md',
          'reports/07-migration-plan.md'
        ]
      },
      instructions: [
        '1. Read the cross-reference findings (Phase 4 results and reports/11-empirical-cross-reference.md)',
        '2. For each misalignment or new finding:',
        '   a. Determine if it requires changing the proposed screen design',
        '   b. Determine if it requires adding new API endpoints or data transformations',
        '   c. Determine if it changes the migration timeline or priorities',
        '3. Write a refinement report to reports/12-empirical-refinements.md containing:',
        '   a. Summary of what the empirical verification confirmed',
        '   b. Summary of what it contradicted or revealed as missing',
        '   c. Specific changes recommended for each affected report',
        '   d. Updated screen specifications where needed',
        '   e. Updated migration plan steps where needed',
        '4. If there are critical changes, update the actual report files (06, 07) with an "EMPIRICAL VERIFICATION UPDATE" section appended',
        '5. Update the executive report (00) with an addendum section',
        '6. Return structured JSON with what was updated and why'
      ],
      outputFormat: 'JSON with confirmed, contradicted, updatedReports, screenChanges, migrationChanges'
    },
    outputSchema: {
      type: 'object',
      required: ['confirmed', 'contradicted'],
      properties: {
        confirmed: { type: 'array' },
        contradicted: { type: 'array' },
        updatedReports: { type: 'array' },
        screenChanges: { type: 'array' },
        migrationChanges: { type: 'array' },
        overallVerdict: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['refinement', 'report', 'verification']
}));
