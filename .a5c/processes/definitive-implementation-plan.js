/**
 * @process definitive-implementation-plan
 * @description Synthesize 13 UI evaluation reports into a single definitive implementation plan
 * that serves as the sole source of truth for building the unified Rare Books Bot UI.
 * Resolves all contradictions between original analysis and empirical verification,
 * produces empirically-grounded screen specs, backend work inventory, and phased timeline.
 * @inputs { projectRoot: string }
 * @outputs { success: boolean, planPath: string }
 *
 * @agent technical-writer specializations/web-development/agents/technical-writer/AGENT.md
 * @agent frontend-architect specializations/web-development/agents/frontend-architect/AGENT.md
 * @agent architecture-documentation specializations/web-development/agents/architecture-documentation/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot'
  } = inputs;

  const startTime = ctx.now();

  ctx.log('info', 'Starting Definitive Implementation Plan synthesis');

  // ============================================================================
  // PHASE 1: EXTRACT & RECONCILE
  // Read all 13 reports, build a reconciled fact base that resolves
  // every contradiction between original analysis (reports 01-07)
  // and empirical corrections (reports 08-12).
  // Output: structured JSON of reconciled facts + contradiction log
  // ============================================================================

  ctx.log('info', 'Phase 1: Extracting facts from 13 reports and reconciling contradictions');

  const reconciledFacts = await ctx.task(extractAndReconcileTask, {
    projectRoot,
    reportsDir: `${projectRoot}/reports`,
    reports: {
      original: [
        '00-executive-report.md', '01-ui-inventory.md', '02-per-ui-evaluation.md',
        '03-project-goal.md', '04-alignment-assessment.md', '05-redundancy-analysis.md',
        '06-new-ui-definition.md', '07-migration-plan.md'
      ],
      empirical: [
        '08-empirical-db-probe.md', '09-empirical-pipeline-test.md',
        '10-empirical-api-verify.md', '11-empirical-cross-reference.md',
        '12-empirical-refinements.md'
      ]
    }
  });

  // ============================================================================
  // PHASE 2: WRITE THE DEFINITIVE PLAN
  // Using the reconciled facts, produce the single implementation plan
  // document with all 6 required sections. Every claim is grounded in
  // empirical evidence. No assumptions survive that were contradicted.
  // ============================================================================

  ctx.log('info', 'Phase 2: Writing the definitive implementation plan');

  const draftPlan = await ctx.task(writeDefinitivePlanTask, {
    projectRoot,
    reconciledFacts
  });

  // ============================================================================
  // PHASE 3: VERIFY INTERNAL CONSISTENCY
  // Cross-check every screen spec against empirical data.
  // Verify every timeline claim. Ensure backend work inventory
  // accounts for all identified API gaps. Flag any remaining
  // contradictions or unsupported assumptions.
  // ============================================================================

  ctx.log('info', 'Phase 3: Verifying plan against empirical evidence');

  const verificationResult = await ctx.task(verifyPlanConsistencyTask, {
    projectRoot,
    reconciledFacts,
    draftPlan
  });

  // ============================================================================
  // PHASE 4: FINALIZE
  // If verification found issues, apply fixes to the plan document.
  // Add a verification stamp section at the end.
  // The result is the final, verified, definitive plan.
  // ============================================================================

  ctx.log('info', 'Phase 4: Finalizing plan with verification results');

  const finalResult = await ctx.task(finalizePlanTask, {
    projectRoot,
    draftPlan,
    verificationResult
  });

  const endTime = ctx.now();

  return {
    success: true,
    planPath: finalResult.planPath,
    duration: endTime - startTime,
    metadata: {
      processId: 'definitive-implementation-plan',
      timestamp: startTime,
      contradictionsResolved: reconciledFacts.contradictionCount,
      verificationIssues: verificationResult.issueCount
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const extractAndReconcileTask = defineTask('extract-reconcile', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 1: Extract facts from 13 reports and reconcile contradictions',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Technical Analyst specializing in document reconciliation and fact extraction',
      task: `Read all 13 reports in ${args.reportsDir} and produce a single reconciled fact base. For every topic where the original reports (01-07) and empirical reports (08-12) disagree, the empirical finding WINS. Log every contradiction resolved.`,
      context: {
        reportsDir: args.reportsDir,
        originalReports: args.reports.original,
        empiricalReports: args.reports.empirical,
        reconciliationPriority: 'Empirical findings (08-12) override original analysis (01-07) in ALL cases of contradiction'
      },
      instructions: [
        '1. Read ALL 13 report files from the reports/ directory',
        '2. Extract key facts into these categories:',
        '   a. ARCHITECTURE: confirmed decisions (9 screens, 4 tiers, React stack)',
        '   b. SCREEN_SPECS: per-screen features, data sources, API endpoints — using EMPIRICAL data shapes',
        '   c. DATA_REALITY: actual database numbers, confidence distributions, coverage rates, anomalies',
        '   d. API_REALITY: actual endpoint shapes, gaps, surprises, missing endpoints',
        '   e. PIPELINE_REALITY: actual query behavior, evidence shapes, known issues',
        '   f. BACKEND_WORK: every API endpoint or change that must be built (from reports 10-12)',
        '   g. TIMELINE: phased plan with empirical corrections (8 weeks, sequential not parallel)',
        '   h. FEATURES_KEEP: features to keep with their source UI',
        '   i. FEATURES_DROP: features to drop with reason',
        '   j. RISKS: all identified risks with mitigations',
        '3. For each category, check for contradictions between original and empirical reports:',
        '   - Report 06 says X, but Report 11/12 says Y → use Y',
        '   - Report 07 says Z timeline, but Report 12 corrects to W → use W',
        '4. Log every contradiction in a contradictions array: {topic, original, empirical, resolution}',
        '5. Return a structured JSON fact base — this becomes the input for writing the plan',
        'CRITICAL: Do not write any files. Return ONLY the structured JSON fact base.'
      ],
      outputFormat: 'JSON with architecture, screenSpecs, dataReality, apiReality, pipelineReality, backendWork, timeline, featuresKeep, featuresDrop, risks, contradictions'
    },
    outputSchema: {
      type: 'object',
      required: ['architecture', 'screenSpecs', 'dataReality', 'backendWork', 'timeline', 'contradictions'],
      properties: {
        architecture: { type: 'object' },
        screenSpecs: { type: 'array' },
        dataReality: { type: 'object' },
        apiReality: { type: 'object' },
        pipelineReality: { type: 'object' },
        backendWork: { type: 'array' },
        timeline: { type: 'object' },
        featuresKeep: { type: 'array' },
        featuresDrop: { type: 'array' },
        risks: { type: 'array' },
        contradictions: { type: 'array' },
        contradictionCount: { type: 'number' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['synthesis', 'reconciliation', 'extraction']
}));

export const writeDefinitivePlanTask = defineTask('write-plan', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Write the definitive implementation plan',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Frontend Architect and Technical Writer producing a definitive implementation plan',
      task: `Using the reconciled fact base, write a single definitive implementation plan document. This document SUPERSEDES all 13 previous reports. Every fact must be grounded in empirical evidence. No unverified assumptions.`,
      context: {
        projectRoot: args.projectRoot,
        reconciledFacts: args.reconciledFacts
      },
      instructions: [
        'Write the definitive implementation plan to: /home/hagaybar/projects/rare-books-bot/IMPLEMENTATION_PLAN.md',
        '',
        'The document MUST have these sections in this exact order:',
        '',
        '## Section 1: Product Vision & Architecture',
        '- Product name, one-paragraph vision statement',
        '- Architecture decision: React, 9 screens, 4 tiers',
        '- Tech stack (with justification: React 19, TypeScript, Vite 8, Tailwind CSS 4, TanStack Query/Table, Zustand, Radix UI, React Router 7)',
        '- Design principles (6 principles from the reconciled facts)',
        '- Navigation structure with tier-based sidebar',
        '',
        '## Section 2: Screen Specifications (one subsection per screen)',
        'For EACH of the 9 screens, provide:',
        '- Screen name, route path, tier',
        '- Purpose (1-2 sentences)',
        '- Alignment rating from empirical verification (CONFIRMED / PARTIALLY_ALIGNED / MISALIGNED)',
        '- Data sources: which API endpoints feed this screen (name them explicitly)',
        '- Data shape: what fields are ACTUALLY available (from empirical API probe)',
        '- Features list (ONLY features supported by existing or planned API endpoints)',
        '- Known gaps: what the screen needs but API does not yet provide',
        '- Backend prerequisites: API endpoints that must be built BEFORE this screen',
        '- Key design notes: any empirical findings that affect visual design (e.g., binary confidence = use resolved/unresolved not four-band)',
        '',
        '## Section 3: Backend Work Inventory',
        'Complete list of every backend API endpoint or change required, organized by:',
        '- API changes to existing endpoints (additions to ChatResponse, etc.)',
        '- New endpoints to build (diagnostics, CRUD, etc.)',
        '- For each item: endpoint, method, purpose, effort estimate, which screen needs it, blocking/non-blocking',
        '- Total effort estimate in developer-days',
        '',
        '## Section 4: Phased Implementation Plan',
        'The corrected 8-week timeline with:',
        '- Phase 0: Foundation & Scaffolding (1 week)',
        '- Phase 1: Chat Screen + Backend Micro-Tasks (2 weeks) — HTTP-only, defer WebSocket',
        '- Phase 2: Query Debugger + Backend (2 weeks) — SEQUENTIAL after Phase 1, not parallel',
        '- Phase 3: Admin Screens (1 week) — read-only publisher view early, CRUD later',
        '- Phase 4: Polish, Integration & WebSocket (1-2 weeks)',
        '- Phase 5: Retirement & Cleanup (1 week)',
        '- For each phase: deliverables, exit criteria, dependencies, backend work included',
        '- Gantt-style dependency diagram (text-based)',
        '',
        '## Section 5: Features — Keep vs Drop',
        'Two definitive lists:',
        '- KEEP: feature, source UI, which new screen inherits it, any modifications needed',
        '- DROP: feature, source UI, reason for dropping',
        '',
        '## Section 6: Risks & Mitigations',
        'All identified risks (from original + empirical), each with:',
        '- Risk description',
        '- Likelihood (high/medium/low)',
        '- Impact (high/medium/low)',
        '- Mitigation strategy',
        '',
        '## Section 7: Verification Stamp',
        'Leave this section as a placeholder: "[To be filled after Phase 3 verification]"',
        '',
        '## Section 8: Appendix — Contradiction Log',
        'List every contradiction between original reports and empirical findings, showing:',
        '- Topic, what was originally assumed, what empirical data showed, resolution applied',
        '',
        'IMPORTANT RULES:',
        '- Every number must come from the reconciled facts (empirical data)',
        '- Every screen spec must reflect ACTUAL API shapes and data availability',
        '- Do NOT include features that depend on APIs that do not exist unless those APIs are listed in the backend work inventory',
        '- The document must be self-contained — a developer should be able to build the UI from this document alone without reading the 13 reports',
        '- Use tables for structured data (screen specs, backend inventory, features)',
        '- Be precise and decisive — no hedging, no "might" or "could consider"'
      ],
      outputFormat: 'JSON with planPath and sectionSummary'
    },
    outputSchema: {
      type: 'object',
      required: ['planPath', 'sectionSummary'],
      properties: {
        planPath: { type: 'string' },
        sectionSummary: { type: 'object' },
        wordCount: { type: 'number' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['writing', 'plan', 'synthesis']
}));

export const verifyPlanConsistencyTask = defineTask('verify-consistency', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 3: Verify plan against empirical evidence',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA Auditor verifying implementation plan consistency against empirical evidence',
      task: `Read the implementation plan at IMPLEMENTATION_PLAN.md and cross-check every claim against the reconciled facts and the empirical reports. Flag any remaining contradictions, unsupported assumptions, or missing items.`,
      context: {
        projectRoot: args.projectRoot,
        planPath: `${args.projectRoot}/IMPLEMENTATION_PLAN.md`,
        reconciledFacts: args.reconciledFacts,
        empiricalReports: [
          'reports/08-empirical-db-probe.md',
          'reports/09-empirical-pipeline-test.md',
          'reports/10-empirical-api-verify.md',
          'reports/11-empirical-cross-reference.md',
          'reports/12-empirical-refinements.md'
        ]
      },
      instructions: [
        '1. Read IMPLEMENTATION_PLAN.md',
        '2. For each screen specification, verify:',
        '   a. Every listed data source endpoint actually exists or is in the backend work inventory',
        '   b. Every listed feature is supported by the actual API response shape (from report 10)',
        '   c. The alignment rating matches report 11',
        '   d. Backend prerequisites are complete (no missing dependencies)',
        '3. For the backend work inventory, verify:',
        '   a. Every gap identified in reports 10-12 has a corresponding backend work item',
        '   b. Effort estimates are reasonable',
        '   c. Blocking dependencies are correctly identified',
        '4. For the timeline, verify:',
        '   a. Phase dependencies are correct (Phase 2 after Phase 1, not parallel)',
        '   b. Backend work is assigned to the correct phase',
        '   c. Exit criteria are testable and specific',
        '5. For features keep/drop, verify:',
        '   a. No dropped feature appears as a screen feature',
        '   b. No kept feature depends on a dropped API or data source',
        '6. Check for any empirical finding from reports 08-12 that is NOT reflected in the plan',
        '7. Do NOT write to IMPLEMENTATION_PLAN.md — only report findings',
        '8. Return JSON with issues array and overall pass/fail'
      ],
      outputFormat: 'JSON with issues array, passedChecks, failedChecks, overallStatus (pass/fail), issueCount'
    },
    outputSchema: {
      type: 'object',
      required: ['issues', 'overallStatus', 'issueCount'],
      properties: {
        issues: { type: 'array' },
        passedChecks: { type: 'array' },
        failedChecks: { type: 'array' },
        overallStatus: { type: 'string' },
        issueCount: { type: 'number' },
        missingEmpiricalFindings: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['verification', 'consistency', 'qa']
}));

export const finalizePlanTask = defineTask('finalize-plan', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 4: Finalize plan with verification corrections',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical Editor finalizing the implementation plan with verification results',
      task: `Apply any fixes from the verification phase to IMPLEMENTATION_PLAN.md, then fill in the Verification Stamp section with the verification results.`,
      context: {
        projectRoot: args.projectRoot,
        planPath: `${args.projectRoot}/IMPLEMENTATION_PLAN.md`,
        verificationResult: args.verificationResult,
        draftPlan: args.draftPlan
      },
      instructions: [
        '1. Read the current IMPLEMENTATION_PLAN.md',
        '2. If verification found issues (issueCount > 0):',
        '   a. Fix each issue directly in the document',
        '   b. Be surgical — only change what the verification flagged',
        '3. Fill in Section 7 (Verification Stamp) with:',
        '   a. Verification date',
        '   b. Number of checks passed vs failed',
        '   c. Issues found and how they were resolved',
        '   d. Statement: "This plan has been verified against empirical database probes, pipeline tests, and API response analysis."',
        '4. Add a final line: "This document supersedes all reports in reports/ and is the sole source of truth for UI implementation."',
        '5. Return the final plan path and summary'
      ],
      outputFormat: 'JSON with planPath, fixesApplied, verificationStamp'
    },
    outputSchema: {
      type: 'object',
      required: ['planPath'],
      properties: {
        planPath: { type: 'string' },
        fixesApplied: { type: 'number' },
        verificationStamp: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['finalization', 'editing', 'plan']
}));
