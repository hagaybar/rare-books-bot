/**
 * @process historian-enhancement-plan
 * @description Turn the Historian Evaluation Report's Top 5 Enhancements into a concrete,
 * verified implementation plan with TDD strategy, task breakdown, and validation criteria.
 * Composes brownfield analysis + planning + codebase verification patterns.
 * @inputs { projectRoot: string, reportPath: string, targetScore: number }
 * @outputs { success: boolean, planPath: string, verificationReport: object }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill project-audit .claude/skills/project-audit/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

/**
 * Historian Enhancement Plan Process
 *
 * Produces a concrete implementation plan for the 5 enhancements identified
 * in the historian evaluation report. The plan is verified against the actual
 * codebase to ensure all file references, function signatures, and schema
 * claims are accurate.
 *
 * Phases:
 * 1. Deep Research — parallel analysis of report + codebase components
 * 2. Enhancement Planning — detailed plan for each of the 5 enhancements
 * 3. Task Breakdown & Validation — dependency graph, task list, validation plan
 * 4. Codebase Verification — verify all claims against actual code
 * 5. Assembly — combine into final plan document
 */
export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    reportPath = 'reports/historian-evaluation.md',
    targetScore = 15.70,
    dbPath = 'data/index/bibliographic.db'
  } = inputs;

  const startTime = ctx.now();
  ctx.log('info', 'Starting Historian Enhancement Plan generation');

  // ==========================================================================
  // PHASE 1: DEEP RESEARCH (parallel)
  // ==========================================================================
  ctx.log('info', 'Phase 1: Deep codebase and report research');

  const [reportAnalysis, queryPipelineAnalysis, narrativePipelineAnalysis, dataModelAnalysis] =
    await ctx.parallel.all([
      () => ctx.task(analyzeReportTask, { projectRoot, reportPath }),
      () => ctx.task(analyzeQueryPipelineTask, { projectRoot, dbPath }),
      () => ctx.task(analyzeNarrativePipelineTask, { projectRoot }),
      () => ctx.task(analyzeDataModelTask, { projectRoot, dbPath })
    ]);

  // ==========================================================================
  // PHASE 2: ENHANCEMENT PLANNING (sequential — each depends on research + prior)
  // ==========================================================================
  ctx.log('info', 'Phase 2: Generating detailed plans for each enhancement');

  const researchContext = {
    reportAnalysis,
    queryPipelineAnalysis,
    narrativePipelineAnalysis,
    dataModelAnalysis
  };

  const e1Plan = await ctx.task(planEnhancement1Task, {
    projectRoot, ...researchContext
  });

  const e2Plan = await ctx.task(planEnhancement2Task, {
    projectRoot, ...researchContext, priorPlans: { e1: e1Plan }
  });

  const e3Plan = await ctx.task(planEnhancement3Task, {
    projectRoot, ...researchContext, priorPlans: { e1: e1Plan, e2: e2Plan }
  });

  const e4Plan = await ctx.task(planEnhancement4Task, {
    projectRoot, ...researchContext, priorPlans: { e1: e1Plan, e2: e2Plan, e3: e3Plan }
  });

  const e5Plan = await ctx.task(planEnhancement5Task, {
    projectRoot, ...researchContext,
    priorPlans: { e1: e1Plan, e2: e2Plan, e3: e3Plan, e4: e4Plan }
  });

  // ==========================================================================
  // PHASE 3: TASK BREAKDOWN & VALIDATION PLANNING
  // ==========================================================================
  ctx.log('info', 'Phase 3: Generating task breakdown and validation plan');

  const enhancementPlans = { e1: e1Plan, e2: e2Plan, e3: e3Plan, e4: e4Plan, e5: e5Plan };

  const [taskBreakdown, validationPlan] = await ctx.parallel.all([
    () => ctx.task(generateTaskBreakdownTask, {
      projectRoot, enhancementPlans, ...researchContext
    }),
    () => ctx.task(generateValidationPlanTask, {
      projectRoot, enhancementPlans, reportAnalysis, targetScore
    })
  ]);

  // ==========================================================================
  // PHASE 4: CODEBASE VERIFICATION
  // ==========================================================================
  ctx.log('info', 'Phase 4: Verifying plan against actual codebase');

  const verificationReport = await ctx.task(verifyPlanAgainstCodebaseTask, {
    projectRoot,
    enhancementPlans,
    taskBreakdown,
    dataModelAnalysis
  });

  // ==========================================================================
  // PHASE 5: ASSEMBLY
  // ==========================================================================
  ctx.log('info', 'Phase 5: Assembling final plan document');

  const assemblyResult = await ctx.task(assemblePlanDocumentTask, {
    projectRoot,
    reportPath,
    reportAnalysis,
    enhancementPlans,
    taskBreakdown,
    validationPlan,
    verificationReport,
    targetScore
  });

  // Single breakpoint: final review (user profile: minimal breakpoints)
  await ctx.breakpoint({
    question: 'Implementation plan generated. Review and approve?',
    title: 'Enhancement Plan Review',
    context: {
      runId: ctx.runId,
      files: [
        { path: assemblyResult.planPath, format: 'markdown', label: 'Implementation Plan' }
      ]
    }
  });

  return {
    success: true,
    planPath: assemblyResult.planPath,
    enhancementPlans,
    taskBreakdown,
    validationPlan,
    verificationReport,
    duration: ctx.now() - startTime,
    metadata: { processId: 'historian-enhancement-plan', timestamp: startTime }
  };
}

// =============================================================================
// PHASE 1 TASKS: Deep Research
// =============================================================================

export const analyzeReportTask = defineTask('analyze-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Analyze historian evaluation report — extract structured enhancement data',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a systems analyst reviewing a historian evaluation report for a bibliographic discovery system.',
      task: 'Parse the historian evaluation report and extract structured data about the 5 proposed enhancements, their root causes, affected queries, and projected score improvements.',
      context: {
        projectRoot: args.projectRoot,
        reportPath: args.reportPath
      },
      instructions: [
        `Read the evaluation report at ${args.projectRoot}/${args.reportPath}`,
        '',
        'Extract and return structured JSON with:',
        '',
        '1. evaluationSummary: { totalQuestions, passRate, overallScore, gradeDistribution }',
        '',
        '2. rootCauses: array of { code, questionsAffected, count, impact, description }',
        '  - NAME_FORM_MISMATCH, MISSING_CROSS_REF, NO_AGGREGATION, THIN_NARRATIVE, NO_COMPARISON, LARGE_SET_SILENT, NO_CURATION',
        '',
        '3. enhancements: array of 5 objects, each with:',
        '  - id (E1-E5)',
        '  - name',
        '  - priority (CRITICAL/HIGH/MEDIUM)',
        '  - questionsImproved (array of Q IDs)',
        '  - rootCausesAddressed (array of codes)',
        '  - scoreImpact (estimated points)',
        '  - effortDays',
        '  - dependencies (array of E IDs)',
        '  - implementationTasks (array of { title, description, effortDays })',
        '',
        '4. questionDetails: array of 20 objects with:',
        '  - id, category, query, filtersApplied, resultCount, scores, rootCauses',
        '',
        '5. projectedScores: { baseline, afterE1, afterE1E2, afterAll }',
        '',
        'Be precise — preserve exact numbers from the report.',
        'Do NOT write any files. Return JSON only.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['evaluationSummary', 'rootCauses', 'enhancements', 'questionDetails', 'projectedScores']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['research', 'report-analysis']
}));

export const analyzeQueryPipelineTask = defineTask('analyze-query-pipeline', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Analyze query pipeline — db_adapter, intent_agent, query execution',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a Python developer analyzing a query pipeline for a bibliographic database system.',
      task: 'Analyze the query pipeline components to understand how queries are compiled, normalized, and executed. Focus on the specific functions that need modification for Enhancements E1 and E2.',
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath
      },
      instructions: [
        'Read and analyze these files (use offset/limit for large files):',
        '',
        `1. ${args.projectRoot}/scripts/query/db_adapter.py`,
        '   - Focus on normalize_filter_value() — how agent names are normalized',
        '   - Focus on build_where_clause() — how AGENT_NORM filters become SQL',
        '   - Document the exact normalization steps and their limitations',
        '',
        `2. ${args.projectRoot}/scripts/chat/intent_agent.py`,
        '   - Focus on IntentInterpretationLLM schema — what fields exist',
        '   - Focus on INTENT_AGENT_SYSTEM_PROMPT — what intents are classified',
        '   - Document which intent types exist and how they route',
        '',
        `3. ${args.projectRoot}/scripts/query/execute.py`,
        '   - How QueryPlan is executed against the database',
        '',
        `4. ${args.projectRoot}/app/api/main.py`,
        '   - Focus on handle_query_definition_phase() — the Phase 1 routing logic',
        '   - How is_overview_query() is detected and handled',
        '   - How confidence threshold gates execution',
        '',
        'Return JSON with:',
        '- normalizeFilterValue: { location, lineRange, steps, limitations }',
        '- buildWhereClause: { location, lineRange, agentHandler, publisherHandler }',
        '- intentAgent: { intentTypes, schema, systemPromptAnalysis }',
        '- phase1Routing: { overviewDetection, confidenceThreshold, executionFlow }',
        '- modificationPoints: array of { file, function, line, changeNeeded, enhancement }',
        '',
        'Be precise with line numbers and function signatures.',
        'Do NOT write any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['normalizeFilterValue', 'buildWhereClause', 'intentAgent', 'phase1Routing', 'modificationPoints']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['research', 'query-pipeline']
}));

export const analyzeNarrativePipelineTask = defineTask('analyze-narrative-pipeline', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Analyze narrative pipeline — narrative_agent, aggregation, exploration, formatter',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a Python developer analyzing a narrative generation pipeline for a bibliographic discovery system.',
      task: 'Analyze the narrative, aggregation, exploration, and formatting components. Focus on what exists, what is missing, and what needs modification for Enhancements E2-E5.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read and analyze these files (use offset/limit for large files):',
        '',
        `1. ${args.projectRoot}/scripts/chat/narrative_agent.py`,
        '   - _MAX_RESULT_SET constant and its impact',
        '   - How agent enrichment data is fetched and formatted',
        '   - What narrative types are generated',
        '',
        `2. ${args.projectRoot}/scripts/chat/aggregation.py`,
        '   - AGGREGATION_QUERIES — what fields can be aggregated',
        '   - execute_aggregation() — how it works, does it accept record_ids=None?',
        '   - is_overview_query() — how analytical queries are currently detected',
        '   - format_collection_overview() — what output format looks like',
        '',
        `3. ${args.projectRoot}/scripts/chat/exploration_agent.py`,
        '   - ExplorationRequestLLM schema — what intent types exist',
        '   - EXPLORATION_AGENT_SYSTEM_PROMPT — how exploration intents are classified',
        '   - Does COMPARISON intent exist? Is RECOMMENDATION stubbed?',
        '',
        `4. ${args.projectRoot}/scripts/chat/formatter.py`,
        '   - generate_followups() — current follow-up suggestion logic',
        '   - format_for_chat() — formatting structure',
        '',
        `5. Check if these files exist: ${args.projectRoot}/scripts/chat/cross_reference.py, ${args.projectRoot}/scripts/chat/curator.py, ${args.projectRoot}/scripts/chat/thematic_context.py`,
        '',
        'Return JSON with:',
        '- narrativeAgent: { maxResultSet, enrichmentFlow, narrativeTypes, limitations }',
        '- aggregation: { supportedFields, canHandleFullCollection, overviewDetection, formatCapabilities }',
        '- explorationAgent: { intentTypes, comparisonSupport, recommendationSupport }',
        '- formatter: { followupLogic, formatStructure }',
        '- missingModules: array of { name, path, enhancementNeeded }',
        '- modificationPoints: array of { file, function, line, changeNeeded, enhancement }',
        '',
        'Do NOT write any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['narrativeAgent', 'aggregation', 'explorationAgent', 'formatter', 'missingModules', 'modificationPoints']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['research', 'narrative-pipeline']
}));

export const analyzeDataModelTask = defineTask('analyze-data-model', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Analyze data model — SQLite schema, authority tables, alias patterns',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a data engineer analyzing a SQLite database schema for a bibliographic system.',
      task: 'Analyze the existing database schema, focusing on agent storage patterns, publisher authority/variant tables (as a pattern to replicate for agents), and authority enrichment data that can seed an agent alias table.',
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath
      },
      instructions: [
        'Run these SQL queries to analyze the schema (use sqlite3):',
        '',
        `sqlite3 ${args.projectRoot}/${args.dbPath} ".schema agents" | head -30`,
        `sqlite3 ${args.projectRoot}/${args.dbPath} ".schema publisher_authorities" | head -30`,
        `sqlite3 ${args.projectRoot}/${args.dbPath} ".schema publisher_variants" | head -30`,
        `sqlite3 ${args.projectRoot}/${args.dbPath} ".schema authority_enrichment" | head -30`,
        `sqlite3 ${args.projectRoot}/${args.dbPath} ".schema imprints" | head -30`,
        '',
        'Then run analysis queries:',
        '',
        '-- How agents are currently stored (word order pattern):',
        `sqlite3 ${args.projectRoot}/${args.dbPath} "SELECT agent_norm, count(*) FROM agents GROUP BY agent_norm ORDER BY count(*) DESC LIMIT 20;"`,
        '',
        '-- Agents that have enrichment with hebrew labels:',
        `sqlite3 ${args.projectRoot}/${args.dbPath} "SELECT ae.label, ae.person_info FROM authority_enrichment ae LIMIT 5;"`,
        '',
        '-- Publisher variant pattern (to replicate for agents):',
        `sqlite3 ${args.projectRoot}/${args.dbPath} "SELECT pv.variant_form, pa.canonical_name FROM publisher_variants pv JOIN publisher_authorities pa ON pv.authority_id = pa.id LIMIT 10;"`,
        '',
        '-- Specific problematic agents from the report:',
        `sqlite3 ${args.projectRoot}/${args.dbPath} "SELECT DISTINCT agent_norm FROM agents WHERE agent_norm LIKE '%buxtorf%' OR agent_norm LIKE '%mendelssohn%' OR agent_norm LIKE '%maimonides%' OR agent_norm LIKE '%karo%' OR agent_norm LIKE '%קארו%';"`,
        '',
        'Also read the publisher authority store pattern:',
        `Read ${args.projectRoot}/scripts/metadata/publisher_authority.py (first 100 lines)`,
        '',
        'Return JSON with:',
        '- agentsTable: { schema, sampleData, wordOrderPattern }',
        '- publisherAuthorities: { schema, variantPattern, totalAuthorities, totalVariants }',
        '- authorityEnrichment: { schema, hasHebrewLabels, totalRecords }',
        '- imprintsTable: { schema, relevantColumns }',
        '- problematicAgents: { buxtorf, mendelssohn, maimonides, karo — how each is stored }',
        '- proposedAgentAliasSchema: SQL CREATE TABLE statement following publisher_variants pattern',
        '- seedDataSources: array of { source, fieldPath, estimatedRecords }',
        '',
        'Do NOT write any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['agentsTable', 'publisherAuthorities', 'authorityEnrichment', 'problematicAgents', 'proposedAgentAliasSchema']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['research', 'data-model']
}));

// =============================================================================
// PHASE 2 TASKS: Enhancement Planning (one per enhancement)
// =============================================================================

const enhancementPlanPromptBase = {
  outputFormat: 'JSON',
  constraints: [
    'Preserve structured retrieval, explicit normalization, reversible transformations',
    'Preserve visible uncertainty (confidence scores)',
    'Maintain separation of catalog data vs normalized data vs enrichment',
    'Prefer incremental delivery — each enhancement independently testable',
    'Minimize regression risk — never modify existing normalization logic destructively',
    'All schema changes must be additive (new tables/columns), never drop existing ones',
    'Every implementation step must have a corresponding test'
  ]
};

export const planEnhancement1Task = defineTask('plan-e1-agent-aliases', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E1: Plan Agent Name Alias Table with Order-Insensitive Matching',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a senior Python developer planning a database enhancement for a bibliographic discovery system. You have deep expertise in text normalization, multilingual matching, and SQLite.',
      task: 'Create a detailed implementation plan for Enhancement 1: Agent Name Alias Table with Order-Insensitive Matching. This is the highest-priority enhancement (CRITICAL) that fixes 4 total query failures.',
      context: {
        projectRoot: args.projectRoot,
        reportAnalysis: args.reportAnalysis,
        queryPipelineAnalysis: args.queryPipelineAnalysis,
        dataModelAnalysis: args.dataModelAnalysis
      },
      instructions: [
        'Using the research data provided, create a detailed plan for E1.',
        '',
        'The plan must address these specific failures from the report:',
        '- Q3 (Aldine Press): EQUALS instead of CONTAINS for publisher, "aldine" vs "in aedibus aldi"',
        '- Q6 (Buxtorf): Word-order mismatch "johann buxtorf" vs "buxtorf, johann"',
        '- Q7 (Mendelssohn): Word-order + cross-script (Hebrew only records)',
        '- Q8 (Maimonides): Partial match, 7/20 found, 13 in Hebrew only',
        '- Q12 (Ethiopia): Subject variant mismatch (Faitlovitch records)',
        '- Q19 (Joseph Karo): Cross-script only, DB has "קארו, יוסף בן אפרים"',
        '',
        'Return JSON with these sections:',
        '',
        '1. goal: one-paragraph description',
        '2. reportFailuresAddressed: array of { questionId, currentBehavior, rootCause, expectedFix }',
        '3. affectedComponents: array of { file, functions, changeType }',
        '4. implementationSteps: ordered array of {',
        '     step, title, description, file, function, currentCode, proposedChange, testStrategy',
        '   }',
        '5. schemaChanges: array of { type, sql, description, seedDataSource }',
        '6. retrievalChanges: { queryCompilation, filterNormalization, sqlGeneration }',
        '7. risksAndEdgeCases: array of { risk, mitigation, severity }',
        '8. tddPlan: {',
        '     testFile, unitTests: array of { name, description, assertion },',
        '     integrationTests: array of { name, query, expectedMinResults }',
        '   }',
        '9. qualityGates: array of { gate, criterion, toolOrCommand }',
        '10. deliverables: array of { file, description }',
        '11. acceptanceCriteria: array of { criterion, verification }',
        '',
        ...enhancementPlanPromptBase.constraints.map(c => `Constraint: ${c}`),
        '',
        'Do NOT write any files.'
      ],
      outputFormat: enhancementPlanPromptBase.outputFormat
    },
    outputSchema: {
      type: 'object',
      required: ['goal', 'reportFailuresAddressed', 'affectedComponents', 'implementationSteps',
        'schemaChanges', 'retrievalChanges', 'risksAndEdgeCases', 'tddPlan',
        'qualityGates', 'deliverables', 'acceptanceCriteria']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'e1', 'agent-aliases']
}));

export const planEnhancement2Task = defineTask('plan-e2-analytical-routing', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E2: Plan Analytical Query Routing (Auto-Aggregation)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a senior Python developer planning query routing improvements for a bibliographic discovery system.',
      task: 'Create a detailed implementation plan for Enhancement 2: Analytical Query Routing. This CRITICAL enhancement unlocks 3 currently impossible query types by routing analytical questions to the existing aggregation engine.',
      context: {
        projectRoot: args.projectRoot,
        reportAnalysis: args.reportAnalysis,
        queryPipelineAnalysis: args.queryPipelineAnalysis,
        narrativePipelineAnalysis: args.narrativePipelineAnalysis,
        priorPlans: args.priorPlans
      },
      instructions: [
        'Using the research data provided, create a detailed plan for E2.',
        '',
        'The plan must address these specific failures:',
        '- Q14 (Chronological shape): All 2796 records returned, no temporal analysis. Professor wants decade-by-decade histogram.',
        '- Q15 (Printing centers): 806 records returned, no geographic aggregation. Professor wants place-by-count breakdown.',
        '- Q20 (Curated exhibit): 120 records, no selection capability.',
        '',
        'Key insight: The aggregation engine ALREADY EXISTS in scripts/chat/aggregation.py.',
        'The problem is routing: analytical questions arrive in Phase 1 (query definition) but',
        'aggregation only runs in Phase 2 (exploration). The fix is intent detection + routing.',
        '',
        'Also address: _MAX_RESULT_SET = 100 in narrative_agent.py blocks narrative for large sets.',
        '',
        'Return JSON with the same structure as E1 plan (all 11 sections).',
        '',
        ...enhancementPlanPromptBase.constraints.map(c => `Constraint: ${c}`),
        '',
        'Do NOT write any files.'
      ],
      outputFormat: enhancementPlanPromptBase.outputFormat
    },
    outputSchema: {
      type: 'object',
      required: ['goal', 'reportFailuresAddressed', 'affectedComponents', 'implementationSteps',
        'schemaChanges', 'retrievalChanges', 'risksAndEdgeCases', 'tddPlan',
        'qualityGates', 'deliverables', 'acceptanceCriteria']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'e2', 'analytical-routing']
}));

export const planEnhancement3Task = defineTask('plan-e3-cross-reference', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E3: Plan Cross-Reference and Comparison Engine',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a senior Python developer planning a cross-reference engine for a bibliographic discovery system with Wikidata enrichment data.',
      task: 'Create a detailed implementation plan for Enhancement 3: Entity Cross-Reference and Set Comparison. This HIGH-priority enhancement enables scholarly cross-referencing and comparative analysis.',
      context: {
        projectRoot: args.projectRoot,
        reportAnalysis: args.reportAnalysis,
        narrativePipelineAnalysis: args.narrativePipelineAnalysis,
        dataModelAnalysis: args.dataModelAnalysis,
        priorPlans: args.priorPlans
      },
      instructions: [
        'Using the research data provided, create a detailed plan for E3.',
        '',
        'Questions improved: Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17 (8 questions, +24 points)',
        '',
        'Key capabilities to add:',
        '- Surface connections between entities in a result set (teacher-student, shared publishers)',
        '- Compare two result sets side-by-side (e.g., Venice vs Amsterdam printing)',
        '- Use existing authority_enrichment data (person_info.teachers, person_info.students)',
        '',
        'New module: scripts/chat/cross_reference.py',
        'Modifications to: narrative_agent.py, exploration_agent.py, formatter.py',
        '',
        'Return JSON with the same structure as E1 plan (all 11 sections).',
        '',
        ...enhancementPlanPromptBase.constraints.map(c => `Constraint: ${c}`),
        '',
        'Do NOT write any files.'
      ],
      outputFormat: enhancementPlanPromptBase.outputFormat
    },
    outputSchema: {
      type: 'object',
      required: ['goal', 'reportFailuresAddressed', 'affectedComponents', 'implementationSteps',
        'schemaChanges', 'retrievalChanges', 'risksAndEdgeCases', 'tddPlan',
        'qualityGates', 'deliverables', 'acceptanceCriteria']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'e3', 'cross-reference']
}));

export const planEnhancement4Task = defineTask('plan-e4-scholarly-narrative', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E4: Plan Scholarly Narrative Enrichment',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a senior developer planning narrative enrichment for a system serving scholars of Jewish book history and early modern print culture.',
      task: 'Create a detailed implementation plan for Enhancement 4: Scholarly Narrative Enrichment. This HIGH-priority enhancement deepens the pedagogical and scholarly quality of system responses.',
      context: {
        projectRoot: args.projectRoot,
        reportAnalysis: args.reportAnalysis,
        narrativePipelineAnalysis: args.narrativePipelineAnalysis,
        priorPlans: args.priorPlans
      },
      instructions: [
        'Using the research data provided, create a detailed plan for E4.',
        '',
        'Questions improved: Q1, Q2, Q4, Q5, Q11, Q16, Q18 (7 questions, +21 points)',
        '',
        'Key capabilities to add:',
        '- Thematic context templates for major themes (Venetian printing, Amsterdam, Christian Hebraism, etc.)',
        '- Significance scoring for records (date rarity, enrichment richness, place rarity, first editions)',
        '- Pedagogical framing ("Teaching note: this set illustrates...")',
        '- Surface top-3 notable items per result set',
        '',
        'New module: scripts/chat/thematic_context.py',
        'Modifications to: narrative_agent.py, formatter.py, app/api/main.py',
        '',
        'IMPORTANT: Thematic templates must be clearly labeled as historical context, not catalog data.',
        'They must be authored paragraphs, not LLM-generated fabrications.',
        '',
        'Return JSON with the same structure as E1 plan (all 11 sections).',
        '',
        ...enhancementPlanPromptBase.constraints.map(c => `Constraint: ${c}`),
        '',
        'Do NOT write any files.'
      ],
      outputFormat: enhancementPlanPromptBase.outputFormat
    },
    outputSchema: {
      type: 'object',
      required: ['goal', 'reportFailuresAddressed', 'affectedComponents', 'implementationSteps',
        'schemaChanges', 'retrievalChanges', 'risksAndEdgeCases', 'tddPlan',
        'qualityGates', 'deliverables', 'acceptanceCriteria']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'e4', 'scholarly-narrative']
}));

export const planEnhancement5Task = defineTask('plan-e5-curation', (args, taskCtx) => ({
  kind: 'agent',
  title: 'E5: Plan Curation and Recommendation Engine',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a senior developer planning a curation engine for a rare books discovery system used by historians and librarians.',
      task: 'Create a detailed implementation plan for Enhancement 5: Intelligent Selection and Exhibit Curation. This MEDIUM-priority enhancement enables exhibit planning, teaching packet creation, and "best of" queries.',
      context: {
        projectRoot: args.projectRoot,
        reportAnalysis: args.reportAnalysis,
        narrativePipelineAnalysis: args.narrativePipelineAnalysis,
        priorPlans: args.priorPlans
      },
      instructions: [
        'Using the research data provided, create a detailed plan for E5.',
        '',
        'Questions improved: Q20 directly (score 1→12+), Q4/Q11/Q14/Q15 indirectly',
        '',
        'Key capabilities to add:',
        '- Significance scoring model (date rarity, enrichment richness, provenance, place rarity, first editions)',
        '- Diverse selection algorithm (maximize significance + diversity across dimensions)',
        '- Curation intent detection in exploration agent',
        '- Exhibit narrative formatting',
        '',
        'New module: scripts/chat/curator.py',
        'Modifications to: exploration_agent.py, formatter.py',
        '',
        'Note: significance scoring overlaps with E4. Plan for shared utility.',
        '',
        'Return JSON with the same structure as E1 plan (all 11 sections).',
        '',
        ...enhancementPlanPromptBase.constraints.map(c => `Constraint: ${c}`),
        '',
        'Do NOT write any files.'
      ],
      outputFormat: enhancementPlanPromptBase.outputFormat
    },
    outputSchema: {
      type: 'object',
      required: ['goal', 'reportFailuresAddressed', 'affectedComponents', 'implementationSteps',
        'schemaChanges', 'retrievalChanges', 'risksAndEdgeCases', 'tddPlan',
        'qualityGates', 'deliverables', 'acceptanceCriteria']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'e5', 'curation']
}));

// =============================================================================
// PHASE 3 TASKS: Task Breakdown & Validation Planning
// =============================================================================

export const generateTaskBreakdownTask = defineTask('generate-task-breakdown', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Generate comprehensive task breakdown with dependencies and ordering',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a project manager creating a detailed task breakdown for a multi-enhancement implementation project.',
      task: 'Generate a comprehensive task breakdown from the 5 enhancement plans, with dependencies, ordering, complexity estimates, and deliverables.',
      context: {
        enhancementPlans: args.enhancementPlans,
        queryPipelineAnalysis: args.queryPipelineAnalysis,
        narrativePipelineAnalysis: args.narrativePipelineAnalysis,
        dataModelAnalysis: args.dataModelAnalysis
      },
      instructions: [
        'Create a task breakdown covering ALL implementation work across the 5 enhancements.',
        '',
        'For each task include:',
        '- id: unique identifier (e.g., E1-T1, E1-T2, E2-T1)',
        '- title: concise task title',
        '- description: 2-3 sentence description of what to do',
        '- enhancement: which enhancement (E1-E5)',
        '- complexity: low/medium/high',
        '- dependencies: array of task IDs that must complete first',
        '- order: execution order number (tasks with same order can run in parallel)',
        '- deliverable: what artifact this task produces',
        '- estimatedHours: rough estimate',
        '',
        'Key dependency rules from the report:',
        '- E1 and E2 have NO dependencies (can start in parallel)',
        '- E3 depends on E1 (agent aliases improve cross-reference quality)',
        '- E4 depends on E3 (cross-references enrich narratives)',
        '- E5 depends on E4 (significance scoring is shared) and E2 (analytical routing)',
        '',
        'Include test-writing tasks BEFORE implementation tasks (TDD).',
        'Include integration verification tasks after each enhancement.',
        '',
        'Return JSON with:',
        '- tasks: array of task objects',
        '- milestones: array of { name, afterTasks, deliverable, regressionQueries }',
        '- criticalPath: array of task IDs on the critical path',
        '- parallelOpportunities: array of { tasks, reason }',
        '',
        'Do NOT write any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['tasks', 'milestones', 'criticalPath', 'parallelOpportunities']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'task-breakdown']
}));

export const generateValidationPlanTask = defineTask('generate-validation-plan', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Generate validation plan with evaluation queries, metrics, and quality gates',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a QA architect designing a validation plan for a multi-enhancement implementation of a bibliographic discovery system.',
      task: 'Generate a validation plan that maps each enhancement to specific evaluation queries, expected score improvements, regression tests, and release quality gates.',
      context: {
        enhancementPlans: args.enhancementPlans,
        reportAnalysis: args.reportAnalysis,
        targetScore: args.targetScore
      },
      instructions: [
        'Create a comprehensive validation plan. The system has an existing 20-question evaluation',
        'framework with 5 scoring dimensions (Accuracy, Richness, Cross-Ref, Narrative, Pedagogical).',
        '',
        'Include:',
        '',
        '1. affectedQueries: for each enhancement, list which queries should improve and by how much:',
        '   { enhancement, queries: [{ id, currentScore, expectedScore, dimensionsImproved }] }',
        '',
        '2. regressionTests: queries that MUST NOT regress:',
        '   { query, currentScore, minimumAcceptable, riskFactors }',
        '',
        '3. metrics: quantitative success criteria:',
        '   { metric, baseline, target, measurement }',
        '   Examples: overall average score, FAIL count, zero-result query count',
        '',
        '4. perEnhancementGates: what must pass before each enhancement is merged:',
        '   { enhancement, gates: [{ gate, criterion, command, passCondition }] }',
        '',
        '5. releaseQualityGates: what must pass before ALL enhancements are considered done:',
        '   { gates: [{ gate, criterion, command, passCondition }] }',
        '',
        '6. evaluationProcedure: step-by-step instructions for running the full 20-query evaluation:',
        '   Include exact curl commands or Python invocations for each query',
        '',
        'Key metrics from the report:',
        '- Baseline: 7.55/25 average (30.2%)',
        '- After E1+E2: 12.70/25 (50.8%) — highest ROI milestone',
        '- After all: 15.70/25 (62.8%)',
        '- FAIL count: 7 baseline → 0 target',
        '',
        'Do NOT write any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['affectedQueries', 'regressionTests', 'metrics', 'perEnhancementGates', 'releaseQualityGates', 'evaluationProcedure']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['planning', 'validation']
}));

// =============================================================================
// PHASE 4 TASK: Codebase Verification
// =============================================================================

export const verifyPlanAgainstCodebaseTask = defineTask('verify-plan-against-codebase', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify all plan claims against actual codebase — file paths, functions, line numbers',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a QA engineer verifying that an implementation plan accurately references the actual codebase.',
      task: 'Verify every file path, function name, line number, and schema claim in the enhancement plans against the actual codebase. Flag any discrepancies.',
      context: {
        projectRoot: args.projectRoot,
        enhancementPlans: args.enhancementPlans,
        taskBreakdown: args.taskBreakdown,
        dataModelAnalysis: args.dataModelAnalysis
      },
      instructions: [
        'For each enhancement plan, verify:',
        '',
        '1. File paths: Does every referenced file actually exist?',
        '   Use: ls or glob to check each file path',
        '',
        '2. Function signatures: Does each referenced function exist with the expected signature?',
        '   Use: grep to find function definitions',
        '',
        '3. Line numbers: Are the referenced line numbers approximately correct?',
        '   Use: read with offset/limit to check specific lines',
        '',
        '4. Schema claims: Do the referenced database tables and columns exist?',
        `   Use: sqlite3 ${args.projectRoot}/data/index/bibliographic.db ".schema <table>"`,
        '',
        '5. Constants: Do referenced constants (like _MAX_RESULT_SET) have the expected values?',
        '',
        '6. Import paths: Are the proposed import paths valid given the project structure?',
        '',
        'Return JSON with:',
        '- verified: array of { claim, file, status: "confirmed", evidence }',
        '- discrepancies: array of { claim, file, expected, actual, severity, suggestion }',
        '- missingFiles: array of { path, enhancement, note }',
        '- schemaVerification: { tables, columns, allValid }',
        '- overallAccuracy: percentage of verified claims',
        '',
        'Do NOT write or modify any files.'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['verified', 'discrepancies', 'missingFiles', 'schemaVerification', 'overallAccuracy']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verification', 'qa']
}));

// =============================================================================
// PHASE 5 TASK: Assembly
// =============================================================================

export const assemblePlanDocumentTask = defineTask('assemble-plan-document', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Assemble final implementation plan document — markdown with all sections',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'You are a technical writer assembling a comprehensive implementation plan document for a bibliographic discovery system enhancement project.',
      task: 'Assemble all research, enhancement plans, task breakdown, validation plan, and verification results into a single, well-structured markdown document.',
      context: {
        projectRoot: args.projectRoot,
        reportPath: args.reportPath,
        reportAnalysis: args.reportAnalysis,
        enhancementPlans: args.enhancementPlans,
        taskBreakdown: args.taskBreakdown,
        validationPlan: args.validationPlan,
        verificationReport: args.verificationReport,
        targetScore: args.targetScore
      },
      instructions: [
        'Create a comprehensive markdown document following this exact structure:',
        '',
        '# Implementation Plan: Historian Evaluation Enhancements',
        '',
        '## 1. Executive Summary',
        '- Main problems identified by the evaluation',
        '- Why these 5 enhancements matter (with score projections)',
        '- Priority order with rationale',
        '- Total estimated effort',
        '',
        '## 2. Enhancement Plans',
        '',
        'For EACH of the 5 enhancements (E1-E5), include ALL of these subsections:',
        '### 2.N Enhancement N: [Name]',
        '- **Goal**',
        '- **Report Failures Addressed** (table with question ID, current behavior, root cause, expected fix)',
        '- **Affected Components** (table with file, functions, change type)',
        '- **Implementation Steps** (numbered, with file/function references)',
        '- **Schema/Data-Model Changes** (SQL statements)',
        '- **Retrieval/Orchestration Changes**',
        '- **Risks and Edge Cases** (table)',
        '- **TDD Plan** (test file, unit tests, integration tests)',
        '- **Quality Gates**',
        '- **Deliverables**',
        '- **Acceptance Criteria**',
        '',
        '## 3. Task Breakdown',
        '- Table with: ID, Title, Description, Complexity, Dependencies, Order, Deliverable',
        '- Milestones with regression queries',
        '- Critical path and parallel opportunities',
        '',
        '## 4. Validation Plan',
        '- Affected evaluation queries per enhancement',
        '- Expected score improvement (table)',
        '- Regression tests',
        '- Metrics and targets',
        '- Release quality gates',
        '',
        '## 5. Open Questions / Assumptions',
        '- Technical assumptions',
        '- Open questions requiring decision',
        '- Verification discrepancies found (from Phase 4)',
        '',
        'Include the verification report accuracy at the end.',
        '',
        `Write the document to: ${args.projectRoot}/reports/historian-enhancement-plan.md`,
        '',
        'Return JSON with: { planPath, wordCount, sectionsWritten, verificationAccuracy }'
      ],
      outputFormat: 'JSON'
    },
    outputSchema: {
      type: 'object',
      required: ['planPath']
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['assembly', 'documentation']
}));
