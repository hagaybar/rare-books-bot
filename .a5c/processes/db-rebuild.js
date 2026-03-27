/**
 * @process db-rebuild
 * @description Full rebuild of bibliographic.db from MARC XML source + enrichment + backup mechanism.
 *   Pipeline: M1 Parse → M2 Normalize → M3 Index → Agent/Publisher authorities →
 *   Wikidata enrichment → Wikipedia 3 passes → Network tables → Backup mechanism
 *
 * @inputs { projectRoot: string, marcXml: string, dbPath: string }
 * @outputs { success: boolean, recordCount: number, agentCount: number }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    marcXml = 'data/marc_source/rare_book_bibs.xml',
    dbPath = 'data/index/bibliographic.db',
    branch = 'feature/network-map-explorer',
  } = inputs;

  ctx.log('info', 'Starting full DB rebuild from MARC XML');

  // ============================================================================
  // PHASE 1: Backup mechanism + core rebuild (M1→M2→M3)
  // ============================================================================

  ctx.log('info', 'Phase 1: Backup mechanism + core rebuild');

  const backupTask = await ctx.task(agentTask, {
    projectRoot, branch,
    taskName: 'Create backup mechanism and fix seed script',
    description: `Two things to implement:

1. Create scripts/utils/db_backup.py — a utility that:
   - backup_db(db_path): copies db_path to db_path.bak (overwrites previous backup)
   - restore_db(db_path): restores from db_path.bak
   - Has a CLI: python -m scripts.utils.db_backup backup data/index/bibliographic.db
   - Has a CLI: python -m scripts.utils.db_backup restore data/index/bibliographic.db
   - Prints confirmation messages

2. Fix scripts/network/seed_test_db.py — add a safety check at the top of main():
   - If the target path is "data/index/bibliographic.db" (the production path), REFUSE to run
   - Print an error: "ERROR: Cannot seed the production database. Use a different path like data/index/test.db"
   - sys.exit(1)
   - This prevents accidental destruction of production data

3. Integrate backup into rebuild_pipeline.py — at the start of run_m3_index(), before creating the new DB:
   - If db_path exists, call backup_db(db_path) first
   - Print "Backed up existing database to {db_path}.bak"

4. Commit all changes.

Verification: python -c "from scripts.utils.db_backup import backup_db, restore_db; print('OK')"`,
    testCommand: `cd ${projectRoot} && python3 -c "from scripts.utils.db_backup import backup_db, restore_db; print('OK')"`,
  });

  const rebuildTask = await ctx.task(agentTask, {
    projectRoot, branch,
    taskName: 'Run core rebuild pipeline (M1→M2→M3)',
    description: `Run the full rebuild pipeline from MARC XML to SQLite database.

The XML file is at: ${marcXml} (8.2MB, ~2800 records)

Command:
  cd ${projectRoot} && poetry run python -m scripts.marc.rebuild_pipeline --full ${marcXml}

This runs:
  - M1: Parse MARC XML → data/canonical/records.jsonl
  - M2: Normalize (dates, places, publishers, agents) → data/m2/records_m1m2.jsonl
  - M3: Build SQLite index → ${dbPath}

The alias maps at data/normalization/place_aliases/place_alias_map.json and data/normalization/publisher_aliases/publisher_alias_map.json will be used automatically if they exist.

After the pipeline completes, verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); r=c.execute('SELECT count(*) FROM records').fetchone()[0]; a=c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]; i=c.execute('SELECT count(*) FROM imprints').fetchone()[0]; print(f'Records: {r}, Agents: {a}, Imprints: {i}')"

Expected: ~2800 records, ~2500+ distinct agents, ~2500+ imprints.

Do NOT commit the database (it's gitignored). But do commit any fixes if the pipeline needed patching.`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); r=c.execute('SELECT count(*) FROM records').fetchone()[0]; a=c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]; print(f'Records: {r}, Agents: {a}'); assert r > 1000, f'Only {r} records'"`,
  });

  const coreVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'core-rebuild',
    command: `cd ${projectRoot} && python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
tables = [t[0] for t in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print(f'Tables: {len(tables)}')
r = c.execute('SELECT count(*) FROM records').fetchone()[0]
a = c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
print(f'Records: {r}, Agents: {a}, Imprints: {i}')
"`,
  });

  // ============================================================================
  // PHASE 2: Seed authorities
  // ============================================================================

  ctx.log('info', 'Phase 2: Seed agent and publisher authorities');

  const authTask = await ctx.task(agentTask, {
    projectRoot, branch,
    taskName: 'Seed agent and publisher authorities',
    description: `Seed the agent_authorities + agent_aliases tables and publisher_authorities + publisher_variants tables.

1. Agent authorities:
   cd ${projectRoot} && poetry run python -m app.cli seed_agent_authorities

   This reads the agents table, creates canonical authority records, and generates aliases
   (primary, variant_spelling, cross_script, patronymic, acronym, word_reorder, historical).

2. Publisher authorities (if populate script exists):
   cd ${projectRoot} && poetry run python -m scripts.metadata.populate_publisher_authority

   This needs data/normalization/publisher_research.json. If it doesn't exist, skip this step.

3. Verify:
   python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); aa=c.execute('SELECT count(*) FROM agent_authorities').fetchone()[0]; al=c.execute('SELECT count(*) FROM agent_aliases').fetchone()[0]; print(f'Authorities: {aa}, Aliases: {al}')"

Do NOT commit the database.`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); aa=c.execute('SELECT count(*) FROM agent_authorities').fetchone()[0]; al=c.execute('SELECT count(*) FROM agent_aliases').fetchone()[0]; print(f'Authorities: {aa}, Aliases: {al}'); assert aa > 100"`,
  });

  // ============================================================================
  // PHASE 3: Wikidata + Wikipedia enrichment
  // ============================================================================

  ctx.log('info', 'Phase 3: Wikidata + Wikipedia enrichment (this takes ~3.5 hours)');

  const enrichBreakpoint = await ctx.task(breakpointTask, {
    question: 'About to start enrichment (Wikidata + Wikipedia 3 passes). This takes ~3.5 hours and costs ~$0.50 in API calls. The core DB is already rebuilt. Continue with enrichment?',
    options: ['Yes, proceed with enrichment', 'Skip enrichment for now'],
  });

  if (enrichBreakpoint?.approved) {
    const wikiEnrichTask = await ctx.task(agentTask, {
      projectRoot, branch,
      taskName: 'Run Wikidata enrichment',
      description: `Run the batch enrichment to populate the authority_enrichment table with Wikidata metadata.

1. First, apply the enrichment schema if needed:
   sqlite3 ${dbPath} < scripts/enrichment/schema.sql 2>/dev/null || true

2. Run batch enrichment:
   cd ${projectRoot} && poetry run python -m scripts.enrichment.run_batch_enrichment

   This fetches Wikidata metadata for agents with NLI authority URIs.

3. Populate authority_enrichment table:
   cd ${projectRoot} && poetry run python -m scripts.enrichment.populate_authority_enrichment

4. Re-enrich with relationships:
   cd ${projectRoot} && poetry run python -m scripts.enrichment.reenrich_with_relationships

5. Verify:
   python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); ae=c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]; print(f'Enriched agents: {ae}')"`,
      testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); ae=c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]; print(f'Enriched: {ae}'); assert ae > 100"`,
    });

    const wikiP1 = await ctx.task(agentTask, {
      projectRoot, branch,
      taskName: 'Wikipedia Pass 1: Links and categories',
      description: `Run Wikipedia enrichment Pass 1 — fetch wikilinks and categories for all agents with Wikipedia articles.

1. Apply Wikipedia schema:
   sqlite3 ${dbPath} < scripts/enrichment/wikipedia_schema.sql 2>/dev/null || true

2. Run Pass 1:
   cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 1 --db ${dbPath}

3. Verify:
   python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wc=c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]; print(f'Wikipedia cache: {wc}')"`,
      testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wc=c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]; print(f'Cache: {wc}')"`,
    });

    const wikiP2 = await ctx.task(agentTask, {
      projectRoot, branch,
      taskName: 'Wikipedia Pass 2: Summaries',
      description: `Run Wikipedia enrichment Pass 2 — fetch article summaries for all cached agents.

cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 2 --db ${dbPath}

This fetches 2-3 paragraph summaries and extracts name variants. Takes ~45 minutes.

Verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); s=c.execute('SELECT count(*) FROM wikipedia_cache WHERE summary_extract IS NOT NULL').fetchone()[0]; print(f'Summaries: {s}')"`,
      testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); s=c.execute('SELECT count(*) FROM wikipedia_cache WHERE summary_extract IS NOT NULL').fetchone()[0]; print(f'Summaries: {s}')"`,
    });

    const wikiP3 = await ctx.task(agentTask, {
      projectRoot, branch,
      taskName: 'Wikipedia Pass 3: LLM relationship extraction',
      description: `Run Wikipedia enrichment Pass 3 — use gpt-4.1-nano to extract structured relationships.

cd ${projectRoot} && poetry run python -m scripts.enrichment.batch_wikipedia --pass 3 --db ${dbPath} --limit 2000

This processes all agents with summaries. Costs ~$0.50 total.

Verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wconn=c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]; types=c.execute('SELECT source_type, count(*) FROM wikipedia_connections GROUP BY source_type').fetchall(); print(f'Connections: {wconn}'); [print(f'  {t}: {n}') for t,n in types]"`,
      testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wconn=c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]; print(f'Connections: {wconn}')"`,
    });
  }

  // ============================================================================
  // PHASE 4: Rebuild network tables
  // ============================================================================

  ctx.log('info', 'Phase 4: Rebuild network tables');

  const networkTask = await ctx.task(agentTask, {
    projectRoot, branch,
    taskName: 'Rebuild network tables',
    description: `Run the network tables build script to materialize network_edges and network_agents.

cd ${projectRoot} && poetry run python -m scripts.network.build_network_tables ${dbPath} data/normalization/place_geocodes.json

Verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); e=c.execute('SELECT count(*) FROM network_edges').fetchone()[0]; a=c.execute('SELECT count(*) FROM network_agents').fetchone()[0]; print(f'Edges: {e}, Agents: {a}')"`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); e=c.execute('SELECT count(*) FROM network_edges').fetchone()[0]; a=c.execute('SELECT count(*) FROM network_agents').fetchone()[0]; print(f'Edges: {e}, Agents: {a}')"`,
  });

  // ============================================================================
  // PHASE 5: Final verification
  // ============================================================================

  const finalVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-verification',
    command: `cd ${projectRoot} && python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
tables = [t[0] for t in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print(f'Tables: {len(tables)} — {sorted(tables)}')
r = c.execute('SELECT count(*) FROM records').fetchone()[0]
a = c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
print(f'Records: {r}, Agents: {a}, Imprints: {i}')
try:
    ae = c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]
    print(f'Authority enrichment: {ae}')
except: print('No authority_enrichment table')
try:
    wc = c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]
    wconn = c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]
    print(f'Wikipedia: cache={wc}, connections={wconn}')
except: print('No wikipedia tables')
try:
    ne = c.execute('SELECT count(*) FROM network_edges').fetchone()[0]
    na = c.execute('SELECT count(*) FROM network_agents').fetchone()[0]
    print(f'Network: edges={ne}, agents={na}')
except: print('No network tables')
import os
size_mb = os.path.getsize('${dbPath}') / 1024 / 1024
print(f'DB size: {size_mb:.1f} MB')
"`,
  });

  ctx.log('info', 'DB rebuild complete');

  return {
    success: true,
    branch,
  };
}

// ============================================================================
// Task Definitions
// ============================================================================

const agentTask = defineTask('agent-impl', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior Python developer rebuilding a bibliographic database',
      task: args.taskName,
      context: {
        projectRoot: args.projectRoot,
        branch: args.branch,
      },
      instructions: [
        `Working directory: ${args.projectRoot}, branch: ${args.branch}`,
        args.description,
        'If something fails, debug and fix it. Report what happened.',
        `Verification: ${args.testCommand}`,
        'Return a JSON summary with: { taskName, status, details }',
      ],
      outputFormat: 'JSON',
    },
  },
  io: {
    inputJsonPath: `tasks/${taskCtx.effectId}/input.json`,
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const shellTask = defineTask('shell-verify', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: {
    command: args.command,
    cwd: args.projectRoot,
    timeout: 60000,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const breakpointTask = defineTask('breakpoint-gate', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: {
    question: args.question,
    options: args.options,
  },
}));
