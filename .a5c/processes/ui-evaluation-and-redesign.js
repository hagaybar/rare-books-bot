/**
 * @process ui-evaluation-and-redesign
 * @description Deep product, UX, architecture, and implementation evaluation of all existing UIs,
 * followed by design and specification of a single new integrated UI for the Rare Books Bot.
 * Covers: UI inventory, per-UI analysis, project goal inference, alignment assessment,
 * future UI definition, technology recommendation, and migration planning.
 * @inputs { projectRoot: string, prompt: string }
 * @outputs { success: boolean, report: object, artifacts: array }
 *
 * @skill frontend-design specializations/web-development/skills/frontend-design/SKILL.md
 * @agent frontend-architect specializations/web-development/agents/frontend-architect/AGENT.md
 * @agent fullstack-architect specializations/web-development/agents/fullstack-architect/AGENT.md
 * @agent architecture-documentation specializations/web-development/agents/architecture-documentation/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    prompt = ''
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting UI Evaluation and Redesign Process');

  // ============================================================================
  // PHASE 1: DISCOVERY — Inventory all existing UIs
  // ============================================================================

  ctx.log('info', 'Phase 1: Discovering and inventorying all existing UIs');

  const inventoryResult = await ctx.task(uiInventoryTask, {
    projectRoot,
    prompt
  });

  artifacts.push({ path: 'reports/01-ui-inventory.md', format: 'markdown' });

  // ============================================================================
  // PHASE 2: DEEP ANALYSIS — Evaluate each UI
  // ============================================================================

  ctx.log('info', 'Phase 2: Deep analysis of each discovered UI');

  const analysisResult = await ctx.task(uiDeepAnalysisTask, {
    projectRoot,
    inventory: inventoryResult,
    prompt
  });

  artifacts.push({ path: 'reports/02-per-ui-evaluation.md', format: 'markdown' });

  // ============================================================================
  // PHASE 3: PROJECT GOAL INFERENCE
  // ============================================================================

  ctx.log('info', 'Phase 3: Inferring the real project goal from codebase');

  const goalInferenceResult = await ctx.task(projectGoalInferenceTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    prompt
  });

  artifacts.push({ path: 'reports/03-project-goal.md', format: 'markdown' });

  // ============================================================================
  // PHASE 4: ALIGNMENT ASSESSMENT
  // ============================================================================

  ctx.log('info', 'Phase 4: Evaluating alignment of each UI with real project goal');

  const alignmentResult = await ctx.task(alignmentAssessmentTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    projectGoal: goalInferenceResult,
    prompt
  });

  artifacts.push({ path: 'reports/04-alignment-assessment.md', format: 'markdown' });

  // ============================================================================
  // PHASE 5: FEATURE OVERLAP & REDUNDANCY ANALYSIS
  // ============================================================================

  ctx.log('info', 'Phase 5: Feature overlap and redundancy analysis');

  const redundancyResult = await ctx.task(redundancyAnalysisTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    alignment: alignmentResult,
    prompt
  });

  artifacts.push({ path: 'reports/05-redundancy-analysis.md', format: 'markdown' });

  // ============================================================================
  // PHASE 6: NEW UI DEFINITION & TECHNOLOGY RECOMMENDATION
  // ============================================================================

  ctx.log('info', 'Phase 6: Defining the future integrated UI and recommending technology');

  const newUiDefinitionResult = await ctx.task(newUiDefinitionTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    projectGoal: goalInferenceResult,
    alignment: alignmentResult,
    redundancy: redundancyResult,
    prompt
  });

  artifacts.push({ path: 'reports/06-new-ui-definition.md', format: 'markdown' });

  // ============================================================================
  // PHASE 7: MIGRATION & DECOMMISSION PLAN
  // ============================================================================

  ctx.log('info', 'Phase 7: Creating migration and decommissioning plan');

  const migrationResult = await ctx.task(migrationPlanTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    projectGoal: goalInferenceResult,
    newUiDefinition: newUiDefinitionResult,
    prompt
  });

  artifacts.push({ path: 'reports/07-migration-plan.md', format: 'markdown' });

  // ============================================================================
  // PHASE 8: CONSOLIDATED FINAL REPORT
  // ============================================================================

  ctx.log('info', 'Phase 8: Generating consolidated final report');

  const finalReportResult = await ctx.task(finalReportTask, {
    projectRoot,
    inventory: inventoryResult,
    analysis: analysisResult,
    projectGoal: goalInferenceResult,
    alignment: alignmentResult,
    redundancy: redundancyResult,
    newUiDefinition: newUiDefinitionResult,
    migration: migrationResult,
    prompt
  });

  artifacts.push({ path: 'reports/00-executive-report.md', format: 'markdown' });

  const endTime = ctx.now();

  return {
    success: true,
    report: finalReportResult,
    artifacts,
    duration: endTime - startTime,
    metadata: {
      processId: 'ui-evaluation-and-redesign',
      timestamp: startTime
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

export const uiInventoryTask = defineTask('ui-inventory', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 1: Discover and inventory all existing UIs',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Product and Frontend Architect conducting a UI inventory audit',
      task: `Discover and inventory ALL existing UIs/frontend interfaces in the project at ${args.projectRoot}. This includes: production UIs, experimental UIs, abandoned UIs, admin/debug panels, internal tools, notebooks/scripts acting as UI layers, and duplicate entry points.`,
      context: {
        projectRoot: args.projectRoot,
        userPrompt: args.prompt,
        knownUiLocations: [
          'frontend/ - React SPA (Metadata Co-pilot Workbench)',
          'app/ui_qa/ - Streamlit QA UI (5 pages)',
          'app/ui_chat/ - Streamlit Chat UI',
          'app/api/ - FastAPI backend with API docs at /docs',
          'app/cli.py - CLI interface'
        ]
      },
      instructions: [
        '1. Scan the entire project for ALL UI-related code: frontend/, app/ui_qa/, app/ui_chat/, app/api/, app/cli.py, and any other locations',
        '2. For each UI found, document: name, location, purpose, target users, technology stack, entry point',
        '3. Assess current status: active, partially used, legacy, deprecated, broken, unclear',
        '4. Read key files in each UI to understand their actual functionality (package.json, main entry files, page files)',
        '5. Check for any hidden or undiscovered UI layers (Jupyter notebooks, scripts with visual output, etc.)',
        '6. Document the API layer as it serves multiple UIs',
        '7. Write the complete inventory report to reports/01-ui-inventory.md in the project root',
        '8. Return a structured JSON summary of all discovered UIs'
      ],
      outputFormat: 'JSON with uis array, each containing: name, location, purpose, targetUsers, techStack, entryPoint, status, description'
    },
    outputSchema: {
      type: 'object',
      required: ['uis'],
      properties: {
        uis: {
          type: 'array',
          items: {
            type: 'object',
            required: ['name', 'location', 'purpose', 'status'],
            properties: {
              name: { type: 'string' },
              location: { type: 'string' },
              purpose: { type: 'string' },
              targetUsers: { type: 'string' },
              techStack: { type: 'string' },
              entryPoint: { type: 'string' },
              status: { type: 'string' },
              description: { type: 'string' }
            }
          }
        }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['audit', 'inventory', 'ui']
}));

export const uiDeepAnalysisTask = defineTask('ui-deep-analysis', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 2: Deep analysis of each existing UI',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior UX Engineer and Software Architect conducting deep UI evaluation',
      task: `Perform a deep analysis of each UI discovered in the inventory. For every UI, evaluate: workflows, features, overlap with other UIs, unique features, missing features, UX quality, maintainability, technical quality, architectural coherence, backend coupling, and evidence of drift from the real project goal.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        userPrompt: args.prompt
      },
      instructions: [
        '1. For each UI in the inventory, read ALL its source files to understand actual functionality',
        '2. Document main workflows it supports with specific user interactions',
        '3. List core features, overlapping features, and unique features',
        '4. Identify missing features that should exist given its purpose',
        '5. Evaluate UX quality: layout, navigation, responsiveness, accessibility',
        '6. Assess maintainability: code organization, component structure, dependencies',
        '7. Evaluate technical quality: type safety, error handling, performance patterns',
        '8. Check architectural coherence: does the codebase structure match its purpose?',
        '9. Analyze coupling to backend/data logic: tight vs loose coupling',
        '10. Identify dead features, partially implemented features, and experimental leftovers',
        '11. Flag features that should NOT survive into the new UI (historical noise)',
        '12. Write the complete analysis to reports/02-per-ui-evaluation.md in the project root',
        '13. Return structured JSON summary'
      ],
      outputFormat: 'JSON with evaluations array, each containing analysis details per UI'
    },
    outputSchema: {
      type: 'object',
      required: ['evaluations'],
      properties: {
        evaluations: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['audit', 'analysis', 'ui', 'ux']
}));

export const projectGoalInferenceTask = defineTask('project-goal-inference', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 3: Infer the real project goal',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Product Strategist and Domain Expert analyzing a bibliographic discovery system',
      task: `Based on the codebase, structure, naming, workflows, and actual implemented behavior, determine: what the project is fundamentally trying to achieve, who the primary users are, what the most important use cases are, what must sit at the center of the future product experience, what is secondary, and what is accidental/historical noise.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        userPrompt: args.prompt,
        projectContext: 'This is a bibliographic discovery system for rare books where MARC XML is the source of truth. The product is called "Rare Books Bot - beta version". It should be treated as the primary product experience.'
      },
      instructions: [
        '1. Read CLAUDE.md, plan.mf, and key documentation files to understand the stated project mission',
        '2. Read the core pipeline code (scripts/marc/, scripts/query/, scripts/metadata/) to understand actual implemented behavior',
        '3. Analyze the data model: CanonicalRecord, NormalizedRecord, QueryPlan, CandidateSet',
        '4. Study the API layer: what endpoints exist and how they serve the product',
        '5. Determine the primary user persona and their core workflow',
        '6. Identify what must sit at the CENTER of the product experience (the bot)',
        '7. Identify what is secondary (admin tools, debugging, QA)',
        '8. Identify what is historical noise (template code, abandoned experiments)',
        '9. Favor the deepest product logic and clearest end-to-end value over feature count',
        '10. Write findings to reports/03-project-goal.md in the project root',
        '11. Return structured JSON with goal, users, useCases, core, secondary, noise'
      ],
      outputFormat: 'JSON with projectGoal, primaryUsers, coreUseCases, centerpiece, secondary, noise'
    },
    outputSchema: {
      type: 'object',
      required: ['projectGoal', 'primaryUsers', 'coreUseCases'],
      properties: {
        projectGoal: { type: 'string' },
        primaryUsers: { type: 'array', items: { type: 'string' } },
        coreUseCases: { type: 'array', items: { type: 'string' } },
        centerpiece: { type: 'string' },
        secondary: { type: 'array', items: { type: 'string' } },
        noise: { type: 'array', items: { type: 'string' } }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['product', 'strategy', 'goal']
}));

export const alignmentAssessmentTask = defineTask('alignment-assessment', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 4: Assess alignment of each UI with the real goal',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Product-Design Evaluator assessing UI alignment with strategic goals',
      task: `Evaluate how well each current UI aligns with: the core purpose of the project, needs of primary users, the central role of the Rare Books Bot, the need for observability and debugging, and long-term maintainability.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        projectGoal: args.projectGoal,
        userPrompt: args.prompt
      },
      instructions: [
        '1. For each UI, assess alignment with the core project purpose (bot-centric bibliographic discovery)',
        '2. Evaluate whether each UI serves the primary users or is self-serving/engineering-focused',
        '3. Check if the bot experience is central or treated as a side feature',
        '4. Assess observability capabilities: can users/operators see what the bot is doing?',
        '5. Evaluate debugging capabilities: can issues be diagnosed?',
        '6. Be explicit about where UIs: support the goal, distract, fragment, duplicate, expose complexity, miss observability',
        '7. Rate each UI on a scale: essential / valuable / nice-to-have / redundant / harmful',
        '8. Write findings to reports/04-alignment-assessment.md in the project root',
        '9. Return structured JSON'
      ],
      outputFormat: 'JSON with alignments array per UI with rating and details'
    },
    outputSchema: {
      type: 'object',
      required: ['alignments'],
      properties: {
        alignments: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['product', 'alignment', 'assessment']
}));

export const redundancyAnalysisTask = defineTask('redundancy-analysis', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 5: Feature overlap and redundancy analysis',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'System Analyst identifying feature overlap and redundancy across UI surfaces',
      task: `Analyze feature overlap and redundancy across all discovered UIs. Identify duplicate capabilities, conflicting implementations, fragmented user experiences, and features that exist only because of historical decisions rather than current needs.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        alignment: args.alignment,
        userPrompt: args.prompt
      },
      instructions: [
        '1. Map features across all UIs in a comparison matrix',
        '2. Identify exact duplicates (same feature, different UI)',
        '3. Identify partial overlaps (similar but different implementations)',
        '4. Flag features that exist only due to historical decisions',
        '5. Identify features that fragment the user experience',
        '6. Distinguish: "useful because it exists" vs "important because it serves the goal"',
        '7. Write findings to reports/05-redundancy-analysis.md in the project root',
        '8. Return structured JSON'
      ],
      outputFormat: 'JSON with featureMatrix, duplicates, overlaps, historical, fragmented arrays'
    },
    outputSchema: {
      type: 'object',
      required: ['duplicates', 'overlaps'],
      properties: {
        featureMatrix: { type: 'object' },
        duplicates: { type: 'array' },
        overlaps: { type: 'array' },
        historical: { type: 'array' },
        fragmented: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['analysis', 'redundancy', 'features']
}));

export const newUiDefinitionTask = defineTask('new-ui-definition', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 6: Define future integrated UI and recommend technology',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Frontend Architect and Product Designer defining a new integrated UI',
      task: `Define the single replacement UI concept for "Rare Books Bot - beta version". The UI must place the bot at the center, support observability/debugging, and recommend React or Angular with full technology stack. Also define the information architecture, main screens, and observability capabilities.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        projectGoal: args.projectGoal,
        alignment: args.alignment,
        redundancy: args.redundancy,
        userPrompt: args.prompt,
        existingFrontend: 'React with Vite, TypeScript, TanStack Query. Existing React app at frontend/ has: Dashboard, Workbench, AgentChat, Review pages. FastAPI backend at app/api/ with REST endpoints.',
        designIntent: {
          center: 'Rare Books Bot - beta version as primary product experience',
          observability: 'Transparent insight into bot inputs, retrieved context, outputs, system behavior',
          debugging: 'Tooling for debugging content/data issues',
          quality: 'Visibility into source material quality and processing status',
          feel: 'robust, modern, clean, intentional, trustworthy, observable'
        }
      },
      instructions: [
        '1. Define core design principles for the new UI',
        '2. Propose the information architecture with main screens/modules',
        '3. Distinguish clearly between: primary user experience, operator observability, diagnostics, admin',
        '4. Define what features/components to KEEP from existing UIs',
        '5. Define what features/components to DROP',
        '6. Recommend React vs Angular with detailed justification',
        '7. Recommend: state management, routing, component architecture, testing strategy, UI framework/design system, charting/observability libraries, API integration patterns',
        '8. Define observability capabilities the new UI MUST include',
        '9. Write findings to reports/06-new-ui-definition.md in the project root',
        '10. Return structured JSON with complete UI definition'
      ],
      outputFormat: 'JSON with uiDefinition, screens, featuresToKeep, featuresToDrop, techRecommendation, observability'
    },
    outputSchema: {
      type: 'object',
      required: ['uiDefinition', 'screens', 'techRecommendation'],
      properties: {
        uiDefinition: { type: 'object' },
        screens: { type: 'array' },
        featuresToKeep: { type: 'array' },
        featuresToDrop: { type: 'array' },
        techRecommendation: { type: 'object' },
        observability: { type: 'object' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['design', 'architecture', 'frontend', 'product']
}));

export const migrationPlanTask = defineTask('migration-plan', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 7: Migration and decommissioning plan',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical Program Manager creating a migration and decommissioning plan',
      task: `Create a practical phased plan for building the new integrated UI, validating it, migrating workflows, removing old UIs, and reducing risk during transition.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        projectGoal: args.projectGoal,
        newUiDefinition: args.newUiDefinition,
        userPrompt: args.prompt
      },
      instructions: [
        '1. Define what to build first (highest impact, lowest risk)',
        '2. Identify what can be retired early (dead/deprecated UIs)',
        '3. Identify what needs temporary compatibility during migration',
        '4. Define what should be archived rather than migrated',
        '5. Set criteria for deleting old UIs',
        '6. Create a phased timeline with clear milestones',
        '7. Identify risks and mitigations for each phase',
        '8. Write findings to reports/07-migration-plan.md in the project root',
        '9. Return structured JSON'
      ],
      outputFormat: 'JSON with phases, earlyRetirements, temporaryCompatibility, archives, deletionCriteria, risks'
    },
    outputSchema: {
      type: 'object',
      required: ['phases'],
      properties: {
        phases: { type: 'array' },
        earlyRetirements: { type: 'array' },
        temporaryCompatibility: { type: 'array' },
        archives: { type: 'array' },
        deletionCriteria: { type: 'array' },
        risks: { type: 'array' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['migration', 'planning', 'decommission']
}));

export const finalReportTask = defineTask('final-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Phase 8: Generate consolidated final report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical Writer and Product Strategist creating an executive-level consolidated report',
      task: `Generate a single consolidated report with all 12 required sections. This is the definitive output of the UI evaluation. It must be decisive, concrete, and actionable.`,
      context: {
        projectRoot: args.projectRoot,
        inventory: args.inventory,
        analysis: args.analysis,
        projectGoal: args.projectGoal,
        alignment: args.alignment,
        redundancy: args.redundancy,
        newUiDefinition: args.newUiDefinition,
        migration: args.migration,
        userPrompt: args.prompt
      },
      instructions: [
        '1. Read ALL section reports from the reports/ directory (01 through 07)',
        '2. Synthesize into a single consolidated report with these 12 sections:',
        '   - Executive Summary',
        '   - Inventory of Existing UIs',
        '   - Per-UI Evaluation',
        '   - Feature Overlap / Redundancy Analysis',
        '   - Inferred Core Project Goal',
        '   - Assessment of Current UIs vs. Project Goal',
        '   - Principles for the New Integrated UI',
        '   - Recommended Information Architecture / Main Screens',
        '   - Observability and Debugging Capabilities the New UI Must Include',
        '   - Recommended Frontend Technology (React or Angular)',
        '   - Migration / Decommission Plan',
        '   - Risks, Unknowns, and Open Questions',
        '3. End with a FINAL RECOMMENDATIONS section containing:',
        '   - Clear recommendation for what the single new UI should be',
        '   - List of features/components to keep',
        '   - List of features/components to drop',
        '   - Proposed high-level screen/module structure',
        '   - Recommended implementation direction',
        '4. Be DECISIVE. Do not stay vague.',
        '5. Write the final report to reports/00-executive-report.md in the project root',
        '6. Return a JSON summary of key decisions'
      ],
      outputFormat: 'JSON with executive summary, key decisions, and report path'
    },
    outputSchema: {
      type: 'object',
      required: ['executiveSummary', 'keyDecisions', 'reportPath'],
      properties: {
        executiveSummary: { type: 'string' },
        keyDecisions: { type: 'array', items: { type: 'string' } },
        reportPath: { type: 'string' },
        featuresToKeep: { type: 'array' },
        featuresToDrop: { type: 'array' },
        proposedScreens: { type: 'array' },
        techStack: { type: 'string' }
      }
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`
  },
  labels: ['report', 'executive', 'synthesis']
}));
