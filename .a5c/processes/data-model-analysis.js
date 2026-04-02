/**
 * @process data-model-analysis
 * @description Analyze and document the full data model from MARC ingestion to chat user flows, evaluate strengths and weaknesses
 * @inputs { projectRoot: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
  } = inputs;

  // ============================================================================
  // PHASE 1: Deep analysis of the data model across all pipeline stages
  // ============================================================================

  ctx.log('info', 'Phase 1: Analyze data model across the full pipeline');

  const analysis = await ctx.task(analyzeDataModelTask, { projectRoot });
  ctx.log('info', `Data model analysis complete`);

  // ============================================================================
  // PHASE 2: Evaluate strengths and weaknesses
  // ============================================================================

  ctx.log('info', 'Phase 2: Evaluate strengths and weaknesses');

  const evaluation = await ctx.task(evaluateDataModelTask, {
    projectRoot,
    analysis,
  });
  ctx.log('info', `Evaluation complete`);

  // ============================================================================
  // PHASE 3: Write the document to docs/current/ and commit
  // ============================================================================

  ctx.log('info', 'Phase 3: Write document and commit');

  const document = await ctx.task(writeDocumentTask, {
    projectRoot,
    analysis,
    evaluation,
  });
  ctx.log('info', `Document written: ${JSON.stringify(document)}`);

  return { success: true, analysis, evaluation, document };
}

// ---------------------------------------------------------------------------
// TASK DEFINITIONS
// ---------------------------------------------------------------------------

export const analyzeDataModelTask = defineTask('analyze-data-model', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Deep analysis of data model across full pipeline',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior data architect and domain expert in bibliographic systems',
      task: 'Analyze the complete data model of this rare books bibliographic discovery system, from MARC XML ingestion through to the chat user interface.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Trace the data model through every stage of the pipeline. For each stage, document:',
        '  - Input data shape (what comes in)',
        '  - Transformations applied',
        '  - Output data shape (what goes out)',
        '  - Key data structures (Pydantic models, SQLite schemas, API models)',
        '  - Where raw vs normalized data lives',
        '',
        'The stages to cover (read the actual source code for each):',
        '',
        '1. M1 - MARC XML Parsing:',
        '   Read: scripts/marc/parse.py, scripts/marc/models.py',
        '   Document: CanonicalRecord structure, how MARC fields map to JSON, provenance tracking',
        '',
        '2. M2 - Normalization:',
        '   Read: scripts/marc/normalize.py, scripts/marc/m2_normalize.py',
        '   Document: How dates/places/publishers are normalized, confidence scoring, method tagging',
        '',
        '3. M3 - SQLite Indexing:',
        '   Read: scripts/marc/m3_schema.sql, scripts/marc/m3_index.py',
        '   Document: Table schema, relationships, FTS setup, what gets indexed vs stored',
        '',
        '4. Enrichment Layer:',
        '   Read: scripts/enrichment/ (wikidata_client.py, key files)',
        '   Read: scripts/metadata/agents/ (agent files)',
        '   Document: How Wikidata/Wikipedia/NLI data enriches records, where enrichment data is stored',
        '',
        '5. M4 - Query Planning & Execution:',
        '   Read: scripts/query/models.py, scripts/query/llm_compiler.py, scripts/query/execute.py',
        '   Document: QueryPlan structure, Filter model, how NL query becomes SQL, CandidateSet + Evidence',
        '',
        '6. Chat/Narration Layer:',
        '   Read: scripts/chat/models.py, scripts/chat/narrator.py, scripts/chat/session_store.py',
        '   Document: ChatSession, ChatMessage, ScholarResponse, how grounding data flows to the narrator',
        '',
        '7. API Layer:',
        '   Read: app/api/models.py, app/api/main.py (first 100 lines + key endpoints)',
        '   Document: ChatRequest, ChatResponse, WebSocket message protocol, how data flows from backend to frontend',
        '',
        '8. Frontend Data Model:',
        '   Read: frontend/src/types/chat.ts, frontend/src/pages/Chat.tsx (state declarations)',
        '   Document: TypeScript types, how streaming messages map to React state',
        '',
        '9. Auth & Session:',
        '   Read: app/api/auth_db.py, app/api/auth_service.py (schema parts)',
        '   Document: User model, token model, session model, how auth state flows',
        '',
        'IMPORTANT: Read the ACTUAL source files. Do not guess from names. Use Read tool with offset/limit for large files.',
        'IMPORTANT: For each data structure, note the actual field names and types from the code.',
        'IMPORTANT: Pay special attention to how data flows BETWEEN stages — the seams are where issues hide.',
        '',
        'Return a structured JSON with one key per stage, each containing: inputShape, outputShape, keyStructures (with actual field names), transformations, and dataFlowNotes.',
      ],
      outputFormat: 'JSON with one key per pipeline stage',
    },
    outputSchema: {
      type: 'object',
      required: ['stages'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['analysis', 'data-model'],
}));

export const evaluateDataModelTask = defineTask('evaluate-data-model', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Evaluate data model strengths and weaknesses',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior data architect specializing in bibliographic and library systems',
      task: 'Evaluate the strengths and weaknesses of this data model based on the analysis provided.',
      context: {
        projectRoot: args.projectRoot,
        analysis: args.analysis,
      },
      instructions: [
        'Based on the data model analysis provided in context, evaluate the system along these dimensions:',
        '',
        'STRENGTHS — identify what the data model does well:',
        '  - Data preservation and reversibility',
        '  - Confidence scoring and provenance',
        '  - Schema design and normalization approach',
        '  - Query pipeline design',
        '  - Evidence traceability',
        '  - Separation of concerns between stages',
        '',
        'WEAKNESSES — identify problems, gaps, or risks:',
        '  - Data loss or lossy transformations',
        '  - Missing relationships or undermodeled entities',
        '  - Schema limitations (e.g., can the schema handle edge cases in MARC data?)',
        '  - Performance concerns at scale',
        '  - Coupling between stages',
        '  - Gaps between what the data model captures and what the chat/UI needs',
        '  - Any mismatch between the "Answer Contract" (CandidateSet + Evidence) and the actual data flow',
        '',
        'Also verify by reading actual code where needed:',
        '  - Read scripts/marc/m3_schema.sql to check for missing indexes or constraints',
        '  - Read scripts/query/execute.py to check if evidence actually traces back to MARC fields',
        '  - Read scripts/chat/narrator.py to check if the narrator has access to all the grounding data it needs',
        '  - Read app/api/main.py to check if the API response includes all the data the frontend expects',
        '',
        'For each weakness, rate severity: HIGH (data correctness risk), MEDIUM (usability/completeness gap), LOW (cosmetic/optimization)',
        '',
        'IMPORTANT: Ground every finding in specific code evidence. No vague generalizations.',
        'IMPORTANT: Read actual source files to verify claims. Use Read tool.',
      ],
      outputFormat: 'JSON with fields: { strengths: [{title, description, evidence}], weaknesses: [{title, description, severity, evidence, suggestion}] }',
    },
    outputSchema: {
      type: 'object',
      required: ['strengths', 'weaknesses'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['evaluation', 'data-model'],
}));

export const writeDocumentTask = defineTask('write-document', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Write data model document to docs/current/ and commit',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical documentation writer',
      task: 'Write a comprehensive data model document based on the analysis and evaluation, save it to docs/current/data-model.md, update CLAUDE.md topic registry, and commit.',
      context: {
        projectRoot: args.projectRoot,
        analysis: args.analysis,
        evaluation: args.evaluation,
      },
      instructions: [
        '1. Write docs/current/data-model.md with this structure:',
        '   - Standard header: # Data Model / > Last verified: 2026-04-02 / > Source of truth for: ...',
        '   - Overview section: brief description of the end-to-end data flow',
        '   - One section per pipeline stage (M1 through Frontend), each with:',
        '     - Input/output shapes',
        '     - Key data structures with actual field names',
        '     - How data flows to the next stage',
        '   - A data flow diagram (ASCII or markdown table showing stage→stage)',
        '   - Strengths section',
        '   - Weaknesses section with severity ratings',
        '   - Recommendations section (derived from weaknesses)',
        '',
        '2. Update CLAUDE.md topic registry:',
        '   - Read CLAUDE.md',
        '   - Add a row to the Topic Registry table: Data Model | docs/current/data-model.md | End-to-end data flow, schemas, strengths/weaknesses',
        '   - Use Edit tool to add the row',
        '',
        '3. Commit and push:',
        '   git add docs/current/data-model.md CLAUDE.md',
        '   git commit with descriptive message',
        '   git push origin main',
        '',
        'IMPORTANT: The document should be comprehensive but readable. Use markdown formatting well.',
        'IMPORTANT: Include actual Pydantic model field names and SQLite column names — not abstractions.',
        'IMPORTANT: Follow the Documentation Maintenance Protocol from CLAUDE.md.',
      ],
      outputFormat: 'JSON with fields: { filePath: string, lineCount: number, committed: boolean, pushed: boolean }',
    },
    outputSchema: {
      type: 'object',
      required: ['filePath', 'committed'],
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['documentation', 'commit'],
}));
