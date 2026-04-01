/**
 * @process docs-reorganization
 * @description Reorganize project documentation: slim CLAUDE.md, create docs/current/ topic files, move historical docs to docs/history/
 * @inputs { projectRoot: string, specPath: string }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import pkg from '@a5c-ai/babysitter-sdk';
const { defineTask } = pkg;

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    specPath = 'docs/superpowers/specs/2026-04-01-docs-reorganization-design.md',
  } = inputs;

  // ============================================================================
  // PHASE 1: Create directory structure and move historical docs
  // ============================================================================

  ctx.log('info', 'Phase 1: Create docs/history/ and move historical docs');

  const moveHistory = await ctx.task(moveHistoryTask, { projectRoot, specPath });
  ctx.log('info', `History move: ${JSON.stringify(moveHistory)}`);

  // ============================================================================
  // PHASE 2: Create docs/current/ topic files from CLAUDE.md + existing docs
  // ============================================================================

  ctx.log('info', 'Phase 2: Create docs/current/ topic files');

  const createTopics = await ctx.task(createTopicFilesTask, { projectRoot, specPath });
  ctx.log('info', `Topic files: ${JSON.stringify(createTopics)}`);

  // ============================================================================
  // PHASE 3: Rewrite CLAUDE.md to ~150 lines
  // ============================================================================

  ctx.log('info', 'Phase 3: Rewrite CLAUDE.md');

  const rewriteClaude = await ctx.task(rewriteClaudeMdTask, { projectRoot, specPath });
  ctx.log('info', `CLAUDE.md rewrite: ${JSON.stringify(rewriteClaude)}`);

  // ============================================================================
  // PHASE 4: Verify and commit
  // ============================================================================

  ctx.log('info', 'Phase 4: Verify accuracy and commit');

  const verify = await ctx.task(verifyAndCommitTask, { projectRoot });
  ctx.log('info', `Verification: ${JSON.stringify(verify)}`);

  return { success: true, moveHistory, createTopics, rewriteClaude, verify };
}

// ---------------------------------------------------------------------------
// TASK DEFINITIONS
// ---------------------------------------------------------------------------

export const moveHistoryTask = defineTask('move-history', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Create docs/history/ and move all historical docs',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'File organization specialist',
      task: 'Create the docs/history/ directory structure and move all historical documentation there.',
      context: { projectRoot: args.projectRoot, specPath: args.specPath },
      instructions: [
        `1. Read the spec at ${args.projectRoot}/${args.specPath} for the full file disposition plan`,
        '2. Create directory structure:',
        '   mkdir -p docs/history/{audits,reports,plans,specs,dev-instructions,misc}',
        '3. Move historical docs (use git mv to preserve history):',
        '   - git mv audits/2026-* docs/history/audits/',
        '   - git mv audits/README.md docs/history/audits/',
        '   - git mv reports/* docs/history/reports/ (preserve scholar-pipeline/ subdir)',
        '   - git mv docs/superpowers/plans/2026-* docs/history/plans/ (existing implemented plans only)',
        '   - git mv docs/superpowers/specs/2026-03-* docs/history/specs/ (implemented specs — NOT the new 2026-04-01 reorg spec)',
        '   - git mv docs/dev_instructions/* docs/history/dev-instructions/',
        '4. Move loose files per spec:',
        '   - git mv IMPLEMENTATION_PLAN.md docs/history/plans/',
        '   - git mv TODO_CONVERSATIONAL_AGENT.md docs/history/misc/',
        '   - git mv docs/PROJECT_DESCRIPTION.md docs/history/misc/',
        '   - git mv docs/qa_wizard_implementation.md docs/history/misc/',
        '   - git mv docs/session_management_implementation_plan.md docs/history/plans/',
        '   - git mv docs/specs/SCHEMA_VERSIONING.md docs/history/specs/',
        '   - git mv docs/specs/place_frequency_spec.md docs/history/specs/',
        '   - git mv docs/salvaged_discussion.txt docs/history/misc/',
        '   - git mv docs/chat_tests/ docs/history/misc/',
        '   - git mv docs/network_tests/ docs/history/misc/',
        '   - git mv docs/tests/token-saving-evaluation-2026-04-01.md docs/history/reports/',
        '5. Delete: rm docs/testing/other_needed_enhancements_190126.txt',
        '6. Create docs/history/INDEX.md with reverse-chronological entries for all moved items',
        '7. Clean up any empty directories left behind (rmdir if empty)',
        'IMPORTANT: Use git mv (not plain mv) to preserve git history.',
        'IMPORTANT: Do NOT move docs/superpowers/specs/2026-04-01-docs-reorganization-design.md — that is the active spec.',
        'IMPORTANT: Do NOT touch .a5c/ at all.',
        'IMPORTANT: Keep docs/testing/MANUAL_TESTING_GUIDE.md in place.',
        'IMPORTANT: Keep docs/superpowers/specs/ and docs/superpowers/plans/ directories (they are skill output targets).',
      ],
      outputFormat: 'JSON with fields: { movedFiles: number, createdDirs: string[], indexEntries: number, errors: string[] }',
    },
    outputSchema: {
      type: 'object',
      required: ['movedFiles'],
      properties: {
        movedFiles: { type: 'number' },
        createdDirs: { type: 'array', items: { type: 'string' } },
        indexEntries: { type: 'number' },
        errors: { type: 'array', items: { type: 'string' } },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['docs', 'history', 'migration'],
}));

export const createTopicFilesTask = defineTask('create-topic-files', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Create 9 docs/current/ topic files',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical documentation writer',
      task: 'Create the 9 topic files in docs/current/ by extracting content from CLAUDE.md and absorbing existing docs.',
      context: { projectRoot: args.projectRoot, specPath: args.specPath },
      instructions: [
        `1. Read the spec at ${args.projectRoot}/${args.specPath} for the topic file mapping`,
        `2. Read the current CLAUDE.md at ${args.projectRoot}/CLAUDE.md to extract content`,
        '3. Create docs/current/ directory',
        '4. Create each topic file with standard header:',
        '   ```',
        '   # Topic Name',
        '   > Last verified: 2026-04-01',
        '   > Source of truth for: [scope]',
        '   ```',
        '5. The 9 files to create:',
        '   a) normalization-pipeline.md — from CLAUDE.md "Data Normalization Pipeline" section + docs/pipelines/place_normalization.md + docs/utilities/place_alias_mapping.md + docs/specs/m2_normalization_spec.md',
        '   b) query-engine.md — from CLAUDE.md "LLM Usage Rules" + "Stable Interfaces" + "Acceptance Tests" sections',
        '   c) chatbot-api.md — from CLAUDE.md "API Layer" + "Session Management" + "Response Formatting" + "Clarification Flow" sections + docs/session_management_usage.md',
        '   d) streaming.md — from CLAUDE.md "Streaming Responses" + "Testing the Chatbot" sections',
        '   e) qa-framework.md — from CLAUDE.md "QA Tool Architecture" section',
        '   f) metadata-workbench.md — from CLAUDE.md "Metadata Co-pilot Workbench" + "Publisher Authority Records" sections + docs/metadata_workbench.md + docs/metadata_workbench_architecture.md',
        '   g) deployment.md — from CLAUDE.md "Production Deployment" section + docs/deployment.md',
        '   h) ingestion-pipeline.md — from CLAUDE.md "Full Ingestion Pipeline" section',
        '   i) architecture.md — from CLAUDE.md "Key Architecture Notes" + "Project Structure" sections + docs/model_index.md',
        '6. For each file, MERGE content from CLAUDE.md sections AND the absorbed existing docs — do not just copy one or the other. The topic file should be comprehensive and self-contained.',
        '7. After creating topic files, move the now-absorbed standalone docs to docs/history/misc/:',
        '   - git mv docs/pipelines/ docs/history/misc/pipelines/',
        '   - git mv docs/utilities/ docs/history/misc/utilities/',
        '   - git mv docs/deployment.md docs/history/misc/',
        '   - git mv docs/metadata_workbench.md docs/history/misc/',
        '   - git mv docs/metadata_workbench_architecture.md docs/history/misc/',
        '   - git mv docs/session_management_usage.md docs/history/misc/',
        '   - git mv docs/model_index.md docs/history/misc/',
        '   - git mv docs/specs/m2_normalization_spec.md docs/history/misc/',
        'IMPORTANT: Read each source file before creating the topic file — content must be accurate and current.',
        'IMPORTANT: Each topic file must be self-contained — a reader should not need to look elsewhere for that topic.',
        'IMPORTANT: Use git mv for moves to preserve history.',
      ],
      outputFormat: 'JSON with fields: { createdFiles: string[], absorbedFiles: string[], totalLines: number }',
    },
    outputSchema: {
      type: 'object',
      required: ['createdFiles'],
      properties: {
        createdFiles: { type: 'array', items: { type: 'string' } },
        absorbedFiles: { type: 'array', items: { type: 'string' } },
        totalLines: { type: 'number' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['docs', 'current', 'topic-files'],
}));

export const rewriteClaudeMdTask = defineTask('rewrite-claude-md', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Rewrite CLAUDE.md to ~150 lines with topic registry',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical documentation architect',
      task: 'Rewrite CLAUDE.md to ~150 lines by removing sections now in docs/current/ and adding the topic registry + maintenance protocol.',
      context: { projectRoot: args.projectRoot, specPath: args.specPath },
      instructions: [
        `1. Read the spec at ${args.projectRoot}/${args.specPath} for the CLAUDE.md structure`,
        `2. Read the current CLAUDE.md at ${args.projectRoot}/CLAUDE.md`,
        '3. Write the new CLAUDE.md with ONLY these sections (in order):',
        '   a) # CLAUDE.md (title)',
        '   b) ## Project Mission — keep the existing mission text unchanged',
        '   c) ## Answer Contract (Non-Negotiable) — keep existing text unchanged',
        '   d) ## Data Model Rules — keep existing text unchanged',
        '   e) ## Code Style — keep existing text unchanged',
        '   f) ## Available Skills — keep existing text but trim to just the list (no detailed descriptions)',
        '   g) ## Directory Conventions — UPDATE to reflect new docs/current/ and docs/history/ structure',
        '   h) ## Common Commands — trim to essential commands only (install, test, run server, deploy, query)',
        '   i) ## Topic Registry — NEW section with the table mapping topics to docs/current/*.md files',
        '   j) ## Documentation Maintenance Protocol — NEW section with the full protocol from the spec',
        '   k) ## What\'s Different from the Template — keep existing text unchanged',
        '4. REMOVE all other sections (they now live in docs/current/):',
        '   - Data Normalization Pipeline',
        '   - LLM Usage Rules / Query Planning',
        '   - Acceptance Tests',
        '   - QA Tool Architecture',
        '   - Session Management',
        '   - Response Formatting',
        '   - Clarification Flow',
        '   - Streaming Responses',
        '   - Testing the Chatbot',
        '   - Metadata Co-pilot Workbench',
        '   - Publisher Authority Records',
        '   - API Layer',
        '   - Full Ingestion Pipeline',
        '   - Production Deployment',
        '   - Key Architecture Notes',
        '   - Project Structure',
        '   - Stable Interfaces',
        '5. The Topic Registry table should look like:',
        '   | Topic | File | Covers |',
        '   |-------|------|--------|',
        '   | Normalization | docs/current/normalization-pipeline.md | M2 dates/places/publishers |',
        '   | Query Engine | docs/current/query-engine.md | M4 LLM compiler, SQL execution |',
        '   | ... (all 9 topics) |',
        '6. Target: ~150 lines total. If significantly over, trim further.',
        'IMPORTANT: Write the complete new file using the Write tool — this is a full rewrite, not an edit.',
        'IMPORTANT: Preserve the EXACT text of kept sections (mission, contract, data model, code style, template differences).',
        'IMPORTANT: The maintenance protocol text must match the spec exactly.',
      ],
      outputFormat: 'JSON with fields: { lineCount: number, sectionsKept: string[], sectionsRemoved: string[], newSections: string[] }',
    },
    outputSchema: {
      type: 'object',
      required: ['lineCount'],
      properties: {
        lineCount: { type: 'number' },
        sectionsKept: { type: 'array', items: { type: 'string' } },
        sectionsRemoved: { type: 'array', items: { type: 'string' } },
        newSections: { type: 'array', items: { type: 'string' } },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['docs', 'claude-md', 'rewrite'],
}));

export const verifyAndCommitTask = defineTask('verify-and-commit', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Verify docs accuracy and commit all changes',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer and git specialist',
      task: 'Verify the documentation reorganization is complete and accurate, then commit and push.',
      context: { projectRoot: args.projectRoot },
      instructions: [
        '1. Verify docs/current/ has exactly 9 topic files:',
        '   ls docs/current/*.md | wc -l  (should be 9)',
        '2. Verify each topic file has the standard header with Last verified date',
        '3. Verify CLAUDE.md is ~150 lines: wc -l CLAUDE.md',
        '4. Verify CLAUDE.md has the Topic Registry table with 9 entries',
        '5. Verify CLAUDE.md has the Documentation Maintenance Protocol section',
        '6. Verify docs/history/INDEX.md exists and has entries',
        '7. Verify skill output paths still exist:',
        '   - docs/superpowers/specs/ (should contain the reorg design spec)',
        '   - docs/superpowers/plans/ (should exist, may be empty)',
        '   - audits/ (should exist, may be empty after move)',
        '8. Verify .a5c/ was NOT touched: ls .a5c/processes/ | head -5',
        '9. Verify no broken references in CLAUDE.md — every docs/current/ file referenced exists',
        '10. Stage all changes: git add -A',
        '11. Commit with a descriptive message',
        '12. Push to origin main',
        '13. Report: file counts, CLAUDE.md line count, any issues found',
        'IMPORTANT: If any verification fails, report it but do NOT skip the commit of what is correct.',
        'IMPORTANT: Use git add -A to catch all moves/deletes/creates.',
      ],
      outputFormat: 'JSON with fields: { claudeMdLines: number, topicFiles: number, historyEntries: number, issues: string[], committed: boolean, pushed: boolean }',
    },
    outputSchema: {
      type: 'object',
      required: ['claudeMdLines', 'topicFiles', 'committed'],
      properties: {
        claudeMdLines: { type: 'number' },
        topicFiles: { type: 'number' },
        historyEntries: { type: 'number' },
        issues: { type: 'array', items: { type: 'string' } },
        committed: { type: 'boolean' },
        pushed: { type: 'boolean' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
  labels: ['verify', 'commit', 'push'],
}));
