/**
 * @process wikipedia-enrichment
 * @description Three-pass Wikipedia enrichment: connection discovery, summaries, LLM extraction.
 *   8 tasks following the plan at docs/superpowers/plans/2026-03-25-wikipedia-enrichment.md
 *
 * @inputs { projectRoot: string, planPath: string, specPath: string, dbPath: string }
 * @outputs { success: boolean, tasksCompleted: number }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = 'docs/superpowers/plans/2026-03-25-wikipedia-enrichment.md',
    specPath = 'docs/superpowers/specs/2026-03-25-wikipedia-enrichment-design.md',
    dbPath = 'data/index/bibliographic.db',
  } = inputs;

  ctx.log('info', 'Starting Wikipedia enrichment (8 tasks, 3 passes)');

  // ============================================================================
  // PHASE 1: Foundation (Tasks 1-2)
  // ============================================================================

  ctx.log('info', 'Phase 1: DB schema + Wikipedia client');

  const task1 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 1,
    taskName: 'Database Schema',
    description: `Create scripts/enrichment/wikipedia_schema.sql with wikipedia_cache and wikipedia_connections tables. Apply to bibliographic.db via: sqlite3 data/index/bibliographic.db < scripts/enrichment/wikipedia_schema.sql. Verify tables exist. Commit.`,
    testCommand: `sqlite3 ${projectRoot}/${dbPath} ".tables" | grep wikipedia`,
  });

  const task2 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 2,
    taskName: 'Wikipedia Client Module',
    description: `Create scripts/enrichment/wikipedia_client.py — async Wikipedia/MediaWiki API client using httpx. Follow the pattern from scripts/enrichment/wikidata_client.py. Functions: resolve_titles_batch(qids) using Wikidata wbgetentities API, fetch_links_batch(titles) using MediaWiki prop=links|categories (50 per request), fetch_summary(title) using REST API /page/summary. Filter broad categories with regex. Create tests/scripts/enrichment/test_wikipedia_client.py with mocked httpx. TDD. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/enrichment/test_wikipedia_client.py -v 2>&1 | tail -20`,
  });

  const phase1Verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase1-foundation',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/enrichment/test_wikipedia_client.py -v 2>&1 | tail -10`,
  });

  // ============================================================================
  // PHASE 2: Pass 1 — Links + Connection Discovery (Tasks 3-4)
  // ============================================================================

  ctx.log('info', 'Phase 2: Batch Pass 1 (links) + connection discovery');

  const task3 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 3,
    taskName: 'Batch Script Pass 1 (Links)',
    description: `Create scripts/enrichment/batch_wikipedia.py — CLI script with --pass and --limit flags. Implement run_pass_1(): query authority_enrichment for all wikidata_ids, resolve QIDs to Wikipedia titles via resolve_titles_batch, fetch links+categories via fetch_links_batch, cache all in wikipedia_cache table. Test with --limit 5 first, then run full Pass 1 (all agents). Report stats. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 1 --db ${dbPath} --limit 5 2>&1 | tail -10`,
  });

  const task4 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 4,
    taskName: 'Connection Discovery Engine',
    description: `Create scripts/enrichment/wikipedia_connections.py with: build_agent_lookup() builds title->QID->agent_norm maps from wikipedia_cache + authority_enrichment + agents tables. discover_connections() cross-references each agent's wikilinks against the lookup (match by QID not name). Score: see_also=0.85, body_link=0.75, shared_categories=0.65, bidirectional=0.90. Canonical rows: source < target alphabetically. Store to wikipedia_connections table. generate_candidate_linkage_report() fuzzy-matches unmatched wikilinks against un-enriched agents, outputs CSV. Create tests. Run on real data. Also install thefuzz if needed: poetry add thefuzz. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/enrichment/test_wikipedia_connections.py -v 2>&1 | tail -20`,
  });

  const phase2Verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase2-connections',
    command: `cd ${projectRoot} && sqlite3 ${dbPath} "SELECT COUNT(*) as connections FROM wikipedia_connections;" && sqlite3 ${dbPath} "SELECT source_type, COUNT(*) FROM wikipedia_connections GROUP BY source_type;"`,
  });

  // ============================================================================
  // PHASE 3: Pass 2 + Narrator Integration (Tasks 5-6, parallel)
  // ============================================================================

  ctx.log('info', 'Phase 3: Summaries + narrator integration');

  const [task5, task6] = await ctx.parallel.all([
    () => ctx.task(implTask, {
      projectRoot, planPath, specPath, dbPath,
      taskNumber: 5,
      taskName: 'Batch Script Pass 2 (Summaries)',
      description: `Add run_pass_2() to scripts/enrichment/batch_wikipedia.py. Fetch Wikipedia summaries for all agents in wikipedia_cache, ordered by connectivity (most connections first). Use fetch_summary() for each. Extract name variants from first paragraph using regex (parenthetical names, Hebrew text). Store summary_extract and name_variants in wikipedia_cache. Add _extract_name_variants() helper. Test with --limit 10 first, then run full pass. Commit.`,
      testCommand: `cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 2 --db ${dbPath} --limit 10 2>&1 | tail -10`,
    }),
    () => ctx.task(implTask, {
      projectRoot, planPath, specPath, dbPath,
      taskNumber: 6,
      taskName: 'Narrator Integration',
      description: `Three changes: (1) Add wikipedia_context: str | None = None to AgentSummary in scripts/chat/plan_models.py. (2) In scripts/chat/executor.py _handle_enrich(), after building AgentSummary from authority_enrichment, query wikipedia_cache for the agent's wikidata_id. If found, set description to Wikipedia summary (richer than Wikidata one-liner) and set wikipedia_context to the full extract. Handle gracefully if wikipedia_cache table doesn't exist. (3) In scripts/chat/narrator.py, add evidence rule 7 to NARRATOR_SYSTEM_PROMPT about Wikipedia context. In _build_narrator_prompt(), render wikipedia_context when available. Run existing tests. Commit.`,
      testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v 2>&1 | tail -20`,
    }),
  ]);

  const phase3Verify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'phase3-summaries-narrator',
    command: `cd ${projectRoot} && sqlite3 ${dbPath} "SELECT COUNT(*) as with_summary FROM wikipedia_cache WHERE summary_extract IS NOT NULL;" && poetry run pytest tests/scripts/chat/test_executor.py tests/scripts/chat/test_narrator.py -v 2>&1 | tail -5`,
  });

  // ============================================================================
  // PHASE 4: Pass 3 + Cross-Reference Integration (Tasks 7-8)
  // ============================================================================

  ctx.log('info', 'Phase 4: LLM extraction + cross-reference integration');

  const task7 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 7,
    taskName: 'Batch Script Pass 3 (LLM Extraction)',
    description: `Add extract_relationships_llm() to scripts/enrichment/wikipedia_connections.py — uses gpt-4.1-nano to extract structured relationships from Wikipedia text. Input: agent name + summary text + list of known linked agents with QIDs (from Pass 1). Output: list of {target_name, target_wikidata_id, relationship (free-text), tags (from vocab + open-ended), confidence}. Tag vocab in prompt: [teacher_of, student_of, collaborator, commentator, co_publication, patron, rival, translator, publisher_of, same_school, family, influenced_by] + "Add new tags if none fit." Match by QID (identifier-first). Add run_pass_3() to batch_wikipedia.py — runs LLM extraction on top N most-connected agents. Test with --limit 5. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 3 --db ${dbPath} --limit 5 2>&1 | tail -10`,
  });

  const task8 = await ctx.task(implTask, {
    projectRoot, planPath, specPath, dbPath,
    taskNumber: 8,
    taskName: 'Cross-Reference Integration',
    description: `In scripts/chat/cross_reference.py, add _find_wikipedia_connections(agent_norms, conn, visited_pairs) that queries wikipedia_connections table for pairs where both agents are in agent_norms. Returns Connection objects with relationship_type="wikipedia_mention". Handle gracefully if table doesn't exist (try/except). Wire into find_connections() as 4th connection type after same_place_period. Run tests. Commit.`,
    testCommand: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_cross_reference.py -v 2>&1 | tail -10`,
  });

  // Final verification
  const finalVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-all-tests',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --ignore=tests/app/test_scholar_evidence.py -x 2>&1 | tail -20`,
  });

  // Final commit
  const finalCommit = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-commit',
    command: `cd ${projectRoot} && git add -A && git status --short | head -20`,
  });

  ctx.log('info', 'Wikipedia enrichment complete');

  return {
    success: true,
    tasksCompleted: 8,
  };
}

// =============================================================================
// Task Definitions
// =============================================================================

const implTask = defineTask('implement-task', (args, taskCtx) => ({
  kind: 'agent',
  title: `Task ${args.taskNumber}: ${args.taskName}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer implementing Wikipedia enrichment for a rare books chatbot',
      task: `Implement Task ${args.taskNumber} (${args.taskName}) from the Wikipedia enrichment plan.`,
      context: {
        projectRoot: args.projectRoot,
        planPath: args.planPath,
        specPath: args.specPath,
        dbPath: args.dbPath,
      },
      instructions: [
        `Read the plan at ${args.planPath} — focus on Task ${args.taskNumber}.`,
        `Read the spec at ${args.specPath} for design details.`,
        args.description,
        'Follow TDD where applicable: write tests first, verify they fail, implement, verify they pass.',
        `After implementation, run: ${args.testCommand}`,
        'Commit changes with a descriptive message.',
        'Return JSON: {success: boolean, filesCreated: string[], filesModified: string[], testsPassing: boolean, commitHash: string}',
      ],
      outputFormat: 'JSON',
    },
    outputSchema: {
      type: 'object',
      required: ['success'],
      properties: {
        success: { type: 'boolean' },
        filesCreated: { type: 'array', items: { type: 'string' } },
        filesModified: { type: 'array', items: { type: 'string' } },
        testsPassing: { type: 'boolean' },
        commitHash: { type: 'string' },
      },
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/result.json`,
  },
}));

const shellTask = defineTask('verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify: ${args.phase}`,
  shell: { command: args.command, cwd: args.projectRoot, timeout: 300000 },
  io: { outputJsonPath: `tasks/${taskCtx.effectId}/result.json` },
}));
