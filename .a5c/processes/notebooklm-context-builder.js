/**
 * @process notebooklm-context-builder
 * @description Build curated, structured context documents for a NotebookLM notebook
 *   that helps understand and navigate the rare-books-bot repository. Generates 7
 *   thematic source documents, uploads them via the notebooklm-connector, verifies
 *   coverage, and creates an update utility for ongoing refresh.
 *
 * @inputs {
 *   notebookUrl: string,
 *   notebookName: string,
 *   repoRoot: string,
 *   outputDir: string
 * }
 * @outputs {
 *   success: boolean,
 *   documentsGenerated: number,
 *   documentsUploaded: number,
 *   verificationScore: number,
 *   updateScriptPath: string
 * }
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

// =============================================================================
// TASK DEFINITIONS
// =============================================================================

/**
 * Phase 1: Deep repository analysis.
 * Reads code, schemas, git history, data samples — produces a structured
 * analysis JSON that downstream document-generation tasks consume.
 */
const deepRepoAnalysis = defineTask('deep-repo-analysis', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Deep repository analysis',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior software architect performing a codebase audit',
      task: `Analyze the rare-books-bot repository at ${args.repoRoot} and produce a structured analysis.`,
      context: {
        repoRoot: args.repoRoot,
        exclusions: [
          'data/marc_source/', 'data/canonical/', 'data/m2/',
          'data/index/', 'data/chat/', 'data/qa/', 'data/runs/',
          'archive/', '.venv/', 'node_modules/', '__pycache__/',
          'poetry.lock', 'frontend/node_modules/'
        ]
      },
      instructions: [
        'Read CLAUDE.md, plan.mf, and docs/PROJECT_DESCRIPTION.md for project context',
        'Map ALL Python modules under scripts/ and app/ — for each, extract: purpose, key functions/classes (with signatures), imports, and which other modules it depends on',
        'Read the SQLite schema from scripts/marc/m3_contract.py and scripts/marc/m3_index.py',
        'Read Pydantic models from scripts/marc/models.py, scripts/marc/m2_models.py, scripts/query/models.py, scripts/schemas/query_plan.py, scripts/schemas/candidate_set.py',
        'Extract the normalization rules from docs/specs/m2_normalization_spec.md and scripts/marc/m2_normalize.py',
        'Summarize git history: run "git log --oneline -50" and group commits by milestone/theme',
        'Read the latest audit report from audits/2026-03-22-status-review/AUDIT_REPORT.md',
        'Extract 1-2 sample records: read first 20 lines of data/canonical/records.jsonl (if accessible) or describe the schema from models',
        'Map the test structure: what test files exist, what they cover',
        'Identify the frontend structure under frontend/',
        'Map the API endpoints from app/api/main.py and app/api/metadata.py',
        'Document the data flow: MARC XML → M1 → M2 → M3 → M4 → M6 → User',
        'Write ALL findings to a single JSON file at .a5c/runs/CURRENT_RUN/artifacts/repo_analysis.json with sections: {project_overview, modules, data_pipeline, query_system, chat_system, metadata_workbench, data_model, normalization, tests, git_history, frontend, api_endpoints, current_status}',
        'IMPORTANT: Do NOT read large data files (JSONL, XML, SQLite). Only read code, docs, and config files.',
        'IMPORTANT: Bounded reads only — use offset/limit for files > 200 lines.'
      ],
      outputFormat: 'JSON file path'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 2: Generate 7 curated markdown source documents.
 * Each document is a standalone NotebookLM source focused on one theme.
 */
const generateDocuments = defineTask('generate-documents', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Generate 7 curated context documents for NotebookLM',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer creating structured knowledge base documents for an AI notebook assistant',
      task: `Using the repository analysis, generate 7 curated markdown documents that together give NotebookLM a complete understanding of the rare-books-bot repository.`,
      context: {
        repoRoot: args.repoRoot,
        outputDir: args.outputDir,
        analysisPath: args.analysisPath
      },
      instructions: [
        'Read the repo analysis JSON from the previous phase',
        'Also directly read key source files to get accurate details (CLAUDE.md, plan.mf, docs/PROJECT_DESCRIPTION.md, the latest audit report)',
        '',
        'Generate these 7 documents in the output directory:',
        '',
        '--- DOCUMENT 1: 01_project_overview.md ---',
        'Title: "Rare Books Bot — Project Overview & Architecture"',
        'Content: Mission statement, core philosophy (evidence-based, deterministic), key differentiators (MARC-first, reversible normalization, confidence scoring), architecture diagram (ASCII), technology stack, milestone status table, project structure tree, how all the pieces fit together.',
        'Target audience context: Someone who needs to answer "what is this project and how is it organized?"',
        '',
        '--- DOCUMENT 2: 02_code_map.md ---',
        'Title: "Code Map — Modules, Relationships & Entry Points"',
        'Content: For EVERY module under scripts/ and app/, describe: what it does, its key functions/classes with signatures, which modules it imports/depends on, which modules depend on it. Group by subsystem (marc/, query/, chat/, metadata/, etc.). Include entry points (CLI commands, API routes). Show the import dependency graph.',
        'Target audience context: Someone who needs to answer "where is the code for X?" or "what calls what?"',
        '',
        '--- DOCUMENT 3: 03_data_pipeline.md ---',
        'Title: "Data Pipeline — MARC XML to SQLite Index (M1→M2→M3)"',
        'Content: Step-by-step pipeline walkthrough. M1 parsing (pymarc, CanonicalRecord fields, extraction report). M2 normalization (place/date/publisher/agent normalization rules, confidence tiers, alias maps). M3 indexing (SQLite schema with all tables and columns, FTS5 setup, provenance tracking). Include 1-2 concrete examples showing a raw MARC record transforming through each stage. Show the Pydantic model fields at each stage.',
        'Target audience context: Someone who needs to answer "how does data get from XML to the database?" or "what normalization rules apply?"',
        '',
        '--- DOCUMENT 4: 04_query_and_chat.md ---',
        'Title: "Query Pipeline & Chatbot System (M4→M6)"',
        'Content: Query compilation (natural language → LLM → QueryPlan JSON → SQL). QueryPlan schema fields. SQL generation and execution. Evidence extraction (how MARC field citations are built). CandidateSet structure. Chat API (HTTP /chat endpoint, WebSocket /ws/chat). Session management (SQLite sessions.db). Response formatting. Clarification flow (ambiguity detection criteria). Follow-up suggestions. Streaming protocol (message types: progress, batch, complete).',
        'Target audience context: Someone who needs to answer "how does a user query become results?" or "how does the chat API work?"',
        '',
        '--- DOCUMENT 5: 05_metadata_workbench.md ---',
        'Title: "Metadata Quality Workbench & Publisher Authorities (M7)"',
        'Content: HITL architecture (React frontend → FastAPI → agents → feedback loop). All 12 API endpoints with purpose. 4 specialist agents (Place, Date, Publisher, Name) — what each knows, when each is invoked. Publisher authority system (authorities table, variants table, matching logic). Feedback loop (approve → alias map update → re-normalize → coverage update). Coverage audit system. React frontend pages and what they show.',
        'Target audience context: Someone who needs to answer "how is metadata quality improved?" or "what do the specialist agents do?"',
        '',
        '--- DOCUMENT 6: 06_data_model.md ---',
        'Title: "Data Model — Schemas, Normalization Rules & Confidence Scoring"',
        'Content: All Pydantic model definitions with field descriptions (CanonicalRecord, Imprint, NormalizedRecord, QueryPlan, QueryFilter, CandidateSet, Candidate, Evidence). SQLite table schemas (imprints, subjects, notes, etc.) with column types. Normalization rules for each field type (6 date patterns, place alias lookup, publisher cleaning). Confidence score tiers and what they mean. Place alias map structure. Publisher authority/variant structure. Data volume stats (2,796 records, coverage percentages).',
        'Target audience context: Someone who needs to answer "what fields does a record have?" or "what does confidence 0.85 mean?"',
        '',
        '--- DOCUMENT 7: 07_project_status.md ---',
        'Title: "Project Status, History & Development Guide"',
        'Content: Current milestone status (what is complete, what is in progress). Git history grouped by milestone (not raw commits — summarize themes like "M1 parsing complete", "normalization improvements", "chatbot API built"). Latest audit findings and action items. Known gaps and technical debt. QA system (gold sets, regression testing). Development commands (poetry install, pytest, ruff, uvicorn). How to run the full pipeline. How to test. Environment variables needed.',
        'Target audience context: Someone who needs to answer "what is the current status?" or "how do I run this?" or "what are the known issues?"',
        '',
        '--- FORMATTING RULES (apply to ALL documents) ---',
        'Use markdown headers (##, ###) to create scannable structure',
        'Use bullet lists for properties and enumerations',
        'Use tables for comparisons and field listings',
        'Use code blocks for function signatures, schemas, and commands',
        'Use ASCII diagrams for architecture and data flow',
        'Cross-reference other documents by name (e.g., "See 03_data_pipeline.md for details")',
        'Start each document with a 2-3 sentence summary of what it covers',
        'Keep each document focused — no duplication between documents',
        'Do NOT include raw data dumps or full file contents',
        'DO include concrete examples (1-2 per concept) to ground abstract descriptions',
        'Each document should be 2,000-5,000 words — comprehensive but not overwhelming',
        '',
        'Write all 7 files to the output directory. Return the list of generated file paths.'
      ],
      outputFormat: 'JSON with { files: string[], totalWords: number }'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 3: Quality review of generated documents.
 */
const qualityReview = defineTask('quality-review', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Review document quality and completeness',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical documentation reviewer and quality analyst',
      task: 'Review 7 NotebookLM context documents for completeness, clarity, accuracy, and noise level.',
      context: {
        repoRoot: args.repoRoot,
        outputDir: args.outputDir,
        documentFiles: args.documentFiles
      },
      instructions: [
        'Read ALL 7 generated documents',
        'Also read key source files (CLAUDE.md, plan.mf, latest audit) to verify accuracy',
        '',
        'For each document, evaluate:',
        '1. COMPLETENESS (0-25): Does it cover all important aspects of its topic?',
        '2. CLARITY (0-25): Would someone unfamiliar with the project understand it?',
        '3. ACCURACY (0-25): Are function signatures, schemas, and descriptions correct?',
        '4. SIGNAL-TO-NOISE (0-25): Is it free of irrelevant details while including what matters?',
        '',
        'Check specifically for:',
        '- Missing modules or components not mentioned anywhere',
        '- Incorrect function signatures or model fields',
        '- Stale information contradicted by current code',
        '- Excessive detail on unimportant aspects',
        '- Missing cross-references between documents',
        '- Any raw data or noise that slipped through',
        '',
        'If ANY document scores below 70 total, fix the issues directly by editing the file.',
        'If ALL documents score 70+, output the scores without modification.',
        '',
        'Output a JSON with { reviews: [{file, scores: {completeness, clarity, accuracy, signalToNoise}, total, issues: string[], fixed: boolean}], overallScore: number, allPassing: boolean }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 5: Upload documents to NotebookLM via the connector.
 * Uses the notebooklm-connector skill which handles Chrome automation.
 */
const uploadToNotebookLM = defineTask('upload-to-notebooklm', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Upload documents to NotebookLM',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Automation engineer uploading content to NotebookLM via browser',
      task: `Upload 7 curated context documents to the NotebookLM notebook at ${args.notebookUrl}`,
      context: {
        notebookUrl: args.notebookUrl,
        notebookName: args.notebookName,
        outputDir: args.outputDir,
        documentFiles: args.documentFiles
      },
      instructions: [
        `STEP 1: Navigate to the notebook at ${args.notebookUrl}`,
        `STEP 2: Rename the notebook from "Untitled notebook" to "${args.notebookName}"`,
        'STEP 3: For each of the 7 document files:',
        '  a. Read the file content from disk',
        '  b. In NotebookLM, click "Add source" → select "Copied text" (or "Paste text")',
        '  c. Paste the document content into the text area',
        '  d. Set the source title to the document filename (without extension)',
        '  e. Save/confirm the source',
        '  f. Wait for it to be processed before adding the next one',
        '',
        'IMPORTANT: Use the notebooklm-connector chrome-mcp-query agent (via Agent tool with subagent_type "notebooklm-connector:chrome-mcp-query") for ALL browser interactions.',
        'IMPORTANT: Process documents one at a time to avoid overwhelming NotebookLM.',
        'IMPORTANT: After all uploads, verify the source count matches 7.',
        '',
        'If a document is too large for a single paste (>40,000 chars), split it into Part 1 and Part 2.',
        '',
        'Return { uploaded: number, sources: [{name, charCount, status}] }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 6: Verify NotebookLM can answer questions about the repo.
 */
const verifyNotebook = defineTask('verify-notebook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify NotebookLM coverage with test questions',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer verifying knowledge base coverage',
      task: `Query the NotebookLM notebook to verify it can accurately answer questions about the rare-books-bot repository.`,
      context: {
        notebookUrl: args.notebookUrl,
        notebookName: args.notebookName
      },
      instructions: [
        'Use the notebooklm-connector (invoke skill "notebooklm-connector:notebooklm-manager") to query the notebook with these test questions:',
        '',
        'Q1: "What is the M1 to M2 to M3 data pipeline and what does each stage do?"',
        'Q2: "How does the query compilation work - from natural language to SQL results?"',
        'Q3: "What normalization rules are applied to place names and what confidence scores do they get?"',
        'Q4: "What are the specialist agents in the metadata workbench and what does each one handle?"',
        'Q5: "What is the current project status and what are the known gaps?"',
        '',
        'For each question, evaluate the answer:',
        '- ACCURATE: Does it match what the code actually does? (0-20)',
        '- COMPLETE: Does it cover the key aspects? (0-20)',
        '- SPECIFIC: Does it cite concrete details (function names, field names, etc.)? (0-20)',
        '',
        'Return { questions: [{question, answer_summary, scores: {accurate, complete, specific}, total}], overallScore: number, gaps: string[] }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 7: Create the update utility script.
 */
const createUpdatePipe = defineTask('create-update-pipe', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Create update utility for refreshing NotebookLM context',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building a utility script',
      task: 'Create a Python utility that regenerates the NotebookLM context documents from current repo state.',
      context: {
        repoRoot: args.repoRoot,
        outputDir: args.outputDir,
        documentTemplates: args.documentFiles,
        notebookUrl: args.notebookUrl,
        notebookName: args.notebookName
      },
      instructions: [
        'Create scripts/notebooklm/update_context.py with these capabilities:',
        '',
        '1. COLLECTOR FUNCTIONS — each collects data from the current repo state:',
        '   - collect_project_overview(): reads CLAUDE.md, plan.mf, PROJECT_DESCRIPTION.md',
        '   - collect_code_map(): walks scripts/ and app/, extracts module info via AST parsing',
        '   - collect_pipeline_info(): reads m2_normalize.py, m3_contract.py, models',
        '   - collect_query_chat_info(): reads query/, chat/, api/ modules',
        '   - collect_metadata_info(): reads metadata/ modules',
        '   - collect_data_model(): reads Pydantic models and schema definitions',
        '   - collect_status(): runs git log, reads latest audit, collects test counts',
        '',
        '2. RENDERER FUNCTIONS — each takes collected data and renders markdown:',
        '   - render_project_overview(data) -> str',
        '   - render_code_map(data) -> str',
        '   - render_data_pipeline(data) -> str',
        '   - render_query_chat(data) -> str',
        '   - render_metadata_workbench(data) -> str',
        '   - render_data_model(data) -> str',
        '   - render_project_status(data) -> str',
        '',
        '3. MAIN FUNCTION — orchestrates collection + rendering:',
        '   - Calls all collectors',
        '   - Calls all renderers',
        '   - Writes 7 markdown files to the output directory',
        '   - Prints summary (files written, word counts, timestamp)',
        '',
        '4. CLI INTERFACE — using argparse:',
        '   - python scripts/notebooklm/update_context.py --output data/notebooklm/sources/',
        '   - Optional --only flag to regenerate specific documents (e.g., --only status,code_map)',
        '   - Optional --diff flag to show what changed since last generation',
        '',
        'Also create scripts/notebooklm/__init__.py (empty)',
        '',
        'The script should use AST parsing (not imports) to analyze Python modules safely.',
        'Use pathlib.Path throughout. Include type hints.',
        'The script must work standalone without any external dependencies beyond stdlib + pathlib.',
        'Include a __main__ guard.',
        '',
        'IMPORTANT: The renderers should produce the SAME document structure as the Phase 2 documents,',
        'but with dynamically collected data instead of hardcoded content.',
        '',
        'Return { scriptPath: string, supportFiles: string[] }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 8: Verify the update utility works correctly.
 */
const verifyUpdatePipe = defineTask('verify-update-pipe', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Run update utility and verify output',
  shell: {
    command: `cd ${args.repoRoot} && python scripts/notebooklm/update_context.py --output ${args.outputDir}_verify/ 2>&1 | head -50`,
    timeout: 60000
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 8b: Validate update pipe outputs match expected structure.
 */
const validateUpdateOutputs = defineTask('validate-update-outputs', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Validate update pipe outputs',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer validating script output',
      task: 'Compare the update utility output with the original documents to verify structural consistency.',
      context: {
        originalDir: args.outputDir,
        verifyDir: `${args.outputDir}_verify`
      },
      instructions: [
        'Read all files in both directories',
        'For each document pair, verify:',
        '  1. Same filename exists in both directories',
        '  2. Same markdown header structure (## and ### headers match)',
        '  3. Similar word count (within 50% of original)',
        '  4. Key sections present in both versions',
        '',
        'If the update script failed to run, report the error and suggest fixes.',
        'Return { valid: boolean, fileComparisons: [{file, headersMatch, wordCountRatio, issues}] }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

/**
 * Phase 9: Register notebook in notebooklm-connector library.
 */
const registerNotebook = defineTask('register-notebook', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Register notebook in notebooklm-connector library',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Configuration manager',
      task: 'Register the NotebookLM notebook in the notebooklm-connector library for easy future access.',
      context: {
        notebookUrl: args.notebookUrl,
        notebookName: args.notebookName,
        notebookId: 'rare-books-bot'
      },
      instructions: [
        'Use the notebooklm-connector:notebooklm-manager skill with the "add" command to register the notebook.',
        `Invoke: Skill("notebooklm-connector:notebooklm-manager", "add ${args.notebookUrl}")`,
        'Set the notebook ID to "rare-books-bot" and name to the notebook name.',
        'Verify registration by running the "list" command.',
        'Return { registered: boolean, id: string, name: string }'
      ],
      outputFormat: 'JSON'
    }
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`
  }
}));

// =============================================================================
// PROCESS DEFINITION
// =============================================================================

export async function process(inputs, ctx) {
  const {
    notebookUrl,
    notebookName = 'Rare Books Bot',
    repoRoot = '/home/hagaybar/projects/rare-books-bot',
    outputDir = '/home/hagaybar/projects/rare-books-bot/data/notebooklm/sources'
  } = inputs;

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 1: Deep Repository Analysis
  // ──────────────────────────────────────────────────────────────────────────

  const analysisResult = await ctx.task(deepRepoAnalysis, {
    repoRoot
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 2: Generate 7 Curated Context Documents
  // ──────────────────────────────────────────────────────────────────────────

  const docsResult = await ctx.task(generateDocuments, {
    repoRoot,
    outputDir,
    analysisPath: analysisResult.analysisPath
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 3: Quality Review & Fix
  // ──────────────────────────────────────────────────────────────────────────

  const reviewResult = await ctx.task(qualityReview, {
    repoRoot,
    outputDir,
    documentFiles: docsResult.files
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 4: User Review Breakpoint
  // ──────────────────────────────────────────────────────────────────────────

  await ctx.breakpoint({
    question: [
      `Quality review complete. Overall score: ${reviewResult.overallScore || 'N/A'}/100.`,
      `Documents generated in: ${outputDir}`,
      '',
      'Please review the 7 documents in the output directory.',
      'Approve to proceed with uploading to NotebookLM, or reject to request changes.'
    ].join('\n'),
    title: 'Review Generated Documents Before Upload',
    context: {
      runId: ctx.runId,
      files: (docsResult.files || []).map(f => ({ path: f, format: 'markdown' }))
    }
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 5: Upload to NotebookLM
  // ──────────────────────────────────────────────────────────────────────────

  const uploadResult = await ctx.task(uploadToNotebookLM, {
    notebookUrl,
    notebookName,
    outputDir,
    documentFiles: docsResult.files
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 6: Verification — Query NotebookLM with Test Questions
  // ──────────────────────────────────────────────────────────────────────────

  const verifyResult = await ctx.task(verifyNotebook, {
    notebookUrl,
    notebookName
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 7: Create Update Utility
  // ──────────────────────────────────────────────────────────────────────────

  const updatePipeResult = await ctx.task(createUpdatePipe, {
    repoRoot,
    outputDir,
    documentFiles: docsResult.files,
    notebookUrl,
    notebookName
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 8: Verify Update Utility
  // ──────────────────────────────────────────────────────────────────────────

  await ctx.task(verifyUpdatePipe, { repoRoot, outputDir });

  const validationResult = await ctx.task(validateUpdateOutputs, {
    outputDir
  });

  // ──────────────────────────────────────────────────────────────────────────
  // PHASE 9: Register Notebook in Connector Library
  // ──────────────────────────────────────────────────────────────────────────

  const registerResult = await ctx.task(registerNotebook, {
    notebookUrl,
    notebookName
  });

  // ──────────────────────────────────────────────────────────────────────────
  // FINAL: Return Summary
  // ──────────────────────────────────────────────────────────────────────────

  return {
    success: true,
    documentsGenerated: (docsResult.files || []).length,
    documentsUploaded: uploadResult.uploaded || 0,
    qualityScore: reviewResult.overallScore || 0,
    verificationScore: verifyResult.overallScore || 0,
    updateScriptPath: updatePipeResult.scriptPath || 'scripts/notebooklm/update_context.py',
    notebookRegistered: registerResult.registered || false,
    notebookId: registerResult.id || 'rare-books-bot'
  };
}
