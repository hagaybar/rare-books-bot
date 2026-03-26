/**
 * @process full-ingestion-pipeline
 * @description Complete MARC XML → fully enriched bibliographic.db pipeline.
 *   24 steps across 9 phases: parse, normalize, index, authorities, Wikidata,
 *   Wikipedia (3 passes), connection discovery, network tables, verification.
 *   Designed for re-use whenever new MARC XML is exported from the catalog.
 *
 * @inputs {
 *   projectRoot: string,
 *   marcXml: string,       // path to MARC XML file
 *   dbPath: string,        // output DB path (default: data/index/bibliographic.db)
 *   skipEnrichment: boolean // skip Wikidata/Wikipedia (fast rebuild)
 * }
 * @outputs { success: boolean, stats: object }
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
    skipEnrichment = false,
  } = inputs;

  const stats = {};
  ctx.log('info', `Full ingestion pipeline: ${marcXml} → ${dbPath}`);

  // ============================================================================
  // PHASE 1: BACKUP & PARSE (M1)
  // Back up existing DB, parse MARC XML to canonical JSONL
  // ============================================================================

  ctx.log('info', 'Phase 1: Backup existing DB + Parse MARC XML (M1)');

  const backup = await ctx.task(shellTask, {
    projectRoot,
    phase: 'backup',
    command: `cd ${projectRoot} && python3 -c "
from scripts.utils.db_backup import backup_db
from pathlib import Path
db = Path('${dbPath}')
if db.exists():
    backup_db(db)
    print('Backup created')
else:
    print('No existing DB to back up')
"`,
  });

  const m1Parse = await ctx.task(agentTask, {
    projectRoot, marcXml, dbPath,
    taskName: 'M1: Parse MARC XML to canonical JSONL',
    description: `Parse the MARC XML file to canonical JSONL records.

Run:
  cd ${projectRoot} && poetry run python -m scripts.marc.rebuild_pipeline --full ${marcXml} --m2-only-skip

Actually, the rebuild_pipeline doesn't have a parse-only flag. Instead run the full pipeline
which does M1→M2→M3 in one shot:

  cd ${projectRoot} && poetry run python -m scripts.marc.rebuild_pipeline --full ${marcXml}

This runs:
  - M1: Parse MARC XML → data/canonical/records.jsonl (extracts all fields including $0 authority URIs)
  - M2: Normalize dates/places/publishers/agents using alias maps at:
    - data/normalization/place_aliases/place_alias_map.json
    - data/normalization/publisher_aliases/publisher_alias_map.json
  - M3: Build SQLite index → ${dbPath}

The pipeline handles everything: date normalization (12 patterns including Hebrew calendar),
place normalization (196+ alias mappings, 99.3% coverage), publisher normalization (2,152 aliases, 98.8%).

Verify:
  python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
r = c.execute('SELECT count(*) FROM records').fetchone()[0]
a = c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
uri = c.execute('SELECT count(DISTINCT authority_uri) FROM agents WHERE authority_uri IS NOT NULL').fetchone()[0]
print(f'Records: {r}, Agents: {a}, Imprints: {i}, With authority_uri: {uri}')
assert r > 1000, f'Only {r} records'
"

If it fails, debug. The pipeline is well-tested and should work on any valid MARC XML.`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); r=c.execute('SELECT count(*) FROM records').fetchone()[0]; print(f'Records: {r}'); assert r > 1000"`,
  });

  const coreVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'core-verify',
    command: `cd ${projectRoot} && python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
r = c.execute('SELECT count(*) FROM records').fetchone()[0]
a = c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
uri = c.execute('SELECT count(DISTINCT authority_uri) FROM agents WHERE authority_uri IS NOT NULL').fetchone()[0]
print(f'Records: {r}')
print(f'Distinct agents: {a}')
print(f'Imprints: {i}')
print(f'Agents with authority_uri: {uri}')
# Check normalization coverage
high_date = c.execute('SELECT count(*) FROM imprints WHERE date_confidence >= 0.9').fetchone()[0]
high_place = c.execute('SELECT count(*) FROM imprints WHERE place_confidence >= 0.9').fetchone()[0]
high_pub = c.execute('SELECT count(*) FROM imprints WHERE publisher_confidence >= 0.8').fetchone()[0]
print(f'Date coverage (>=0.9): {high_date}/{i} ({100*high_date/i:.1f}%)')
print(f'Place coverage (>=0.9): {high_place}/{i} ({100*high_place/i:.1f}%)')
print(f'Publisher coverage (>=0.8): {high_pub}/{i} ({100*high_pub/i:.1f}%)')
"`,
  });

  // ============================================================================
  // PHASE 2: AUTHORITY SYSTEMS
  // Seed agent authorities + aliases, populate publisher authorities
  // ============================================================================

  ctx.log('info', 'Phase 2: Seed agent & publisher authorities');

  const seedAuthorities = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'Seed agent authorities and publisher authorities',
    description: `Seed the agent_authorities + agent_aliases tables and publisher_authorities.

1. Agent authorities:
   cd ${projectRoot} && poetry run python -m app.cli seed_agent_authorities

   If this fails because agents don't have authority_uri values, the seed script
   should still create authorities from agent_norm grouping. Check the output.

2. Publisher authorities (if publisher_research.json exists):
   cd ${projectRoot}
   if [ -f data/normalization/publisher_research.json ]; then
     poetry run python -m scripts.metadata.populate_publisher_authority
   fi

3. Verify:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
aa = c.execute('SELECT count(*) FROM agent_authorities').fetchone()[0]
al = c.execute('SELECT count(*) FROM agent_aliases').fetchone()[0]
al_types = c.execute('SELECT alias_type, count(*) FROM agent_aliases GROUP BY alias_type').fetchall()
print(f'Agent authorities: {aa}')
print(f'Agent aliases: {al}')
for t, n in al_types: print(f'  {t}: {n}')
try:
    pa = c.execute('SELECT count(*) FROM publisher_authorities').fetchone()[0]
    pv = c.execute('SELECT count(*) FROM publisher_variants').fetchone()[0]
    print(f'Publisher authorities: {pa}, variants: {pv}')
except: print('No publisher authority tables')
"`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); aa=c.execute('SELECT count(*) FROM agent_authorities').fetchone()[0]; print(f'Authorities: {aa}'); assert aa > 100"`,
  });

  // ============================================================================
  // PHASE 3: WIKIDATA ENRICHMENT
  // Enrich agents via authority URIs (preferred) or name-based search (fallback)
  // ============================================================================

  if (!skipEnrichment) {
    ctx.log('info', 'Phase 3: Wikidata enrichment');

    const enrichBreakpoint = await ctx.task(breakpointTask, {
      question: 'Core DB is ready. About to start Wikidata + Wikipedia enrichment. This takes ~1-4 hours depending on data. Continue?',
      options: ['Yes, continue with enrichment', 'Skip enrichment — done for now'],
    });

    if (enrichBreakpoint?.approved) {

      const wikidata = await ctx.task(agentTask, {
        projectRoot, dbPath,
        taskName: 'Wikidata enrichment (authority URI + name-based)',
        description: `Enrich agents with Wikidata metadata. Two strategies:

STRATEGY 1 (preferred): Authority URI based
  If agents have authority_uri values (from MARC $0 subfield), use the standard pipeline:
  cd ${projectRoot}
  sqlite3 ${dbPath} < scripts/enrichment/schema.sql 2>/dev/null || true
  poetry run python -m scripts.enrichment.run_batch_enrichment
  poetry run python -m scripts.enrichment.populate_authority_enrichment
  poetry run python -m scripts.enrichment.reenrich_with_relationships

  Check first: python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); u=c.execute('SELECT count(DISTINCT authority_uri) FROM agents WHERE authority_uri IS NOT NULL').fetchone()[0]; print(f'Agents with authority_uri: {u}')"

STRATEGY 2 (fallback): Name-based search
  If agents have NO authority_uri values (authority_uri is NULL), use name-based enrichment:
  cd ${projectRoot}
  sqlite3 ${dbPath} < scripts/enrichment/schema.sql 2>/dev/null || true
  poetry run python -m scripts.enrichment.run_name_enrichment --latin-only --limit 1000 --delay 1.5

  Then populate:
  poetry run python -m scripts.enrichment.populate_from_name_cache
  poetry run python -m scripts.enrichment.reenrich_with_relationships

Verify:
  python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
ae = c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]
wd = c.execute('SELECT count(*) FROM authority_enrichment WHERE wikidata_id IS NOT NULL').fetchone()[0]
print(f'Authority enrichment: {ae} total ({wd} with Wikidata)')
"`,
        testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); ae=c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]; print(f'Enriched: {ae}')"`,
      });

      // ============================================================================
      // PHASE 4: WIKIPEDIA ENRICHMENT (3 PASSES)
      // ============================================================================

      ctx.log('info', 'Phase 4: Wikipedia enrichment (3 passes)');

      const wikiP1 = await ctx.task(agentTask, {
        projectRoot, dbPath,
        taskName: 'Wikipedia Pass 1: Links and categories',
        description: `Fetch wikilinks and categories for all agents with Wikipedia articles.

cd ${projectRoot}
sqlite3 ${dbPath} < scripts/enrichment/wikipedia_schema.sql 2>/dev/null || true
poetry run python -m scripts.enrichment.batch_wikipedia --pass 1 --db ${dbPath}

Verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wc=c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]; print(f'Wikipedia cache: {wc}')"`,
        testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wc=c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]; print(f'Cache: {wc}')"`,
      });

      const wikiP2 = await ctx.task(agentTask, {
        projectRoot, dbPath,
        taskName: 'Wikipedia Pass 2: Summaries and name variants',
        description: `Fetch article summaries for all cached agents.

cd ${projectRoot}
poetry run python -m scripts.enrichment.batch_wikipedia --pass 2 --db ${dbPath}

Verify:
  python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); s=c.execute('SELECT count(*) FROM wikipedia_cache WHERE summary_extract IS NOT NULL').fetchone()[0]; print(f'Summaries: {s}')"`,
        testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); s=c.execute('SELECT count(*) FROM wikipedia_cache WHERE summary_extract IS NOT NULL').fetchone()[0]; print(f'Summaries: {s}')"`,
      });

      const wikiP3 = await ctx.task(agentTask, {
        projectRoot, dbPath,
        taskName: 'Wikipedia Pass 3: LLM relationship extraction',
        description: `Extract structured relationships using gpt-4.1-nano.

cd ${projectRoot}
poetry run python -m scripts.enrichment.batch_wikipedia --pass 3 --db ${dbPath} --limit 2000

Verify:
  python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
wconn = c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]
types = c.execute('SELECT source_type, count(*) FROM wikipedia_connections GROUP BY source_type').fetchall()
print(f'Connections: {wconn}')
for t, n in types: print(f'  {t}: {n}')
"`,
        testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); wconn=c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]; print(f'Connections: {wconn}')"`,
      });

    } // end enrichment approval
  } // end !skipEnrichment

  // ============================================================================
  // PHASE 5: NETWORK TABLES
  // Materialize network_edges and network_agents for the Network Map Explorer
  // ============================================================================

  ctx.log('info', 'Phase 5: Build network tables');

  const networkBuild = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'Build network tables (edges + agents)',
    description: `Materialize network_edges and network_agents tables.

cd ${projectRoot}
poetry run python -m scripts.network.build_network_tables ${dbPath} data/normalization/place_geocodes.json

Verify:
  python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
ne = c.execute('SELECT count(*) FROM network_edges').fetchone()[0]
na = c.execute('SELECT count(*) FROM network_agents').fetchone()[0]
placed = c.execute('SELECT count(*) FROM network_agents WHERE lat IS NOT NULL').fetchone()[0]
types = c.execute('SELECT connection_type, count(*) FROM network_edges GROUP BY connection_type').fetchall()
print(f'Network edges: {ne}')
print(f'Network agents: {na} (placed: {placed})')
for t, n in types: print(f'  {t}: {n}')
"`,
    testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); ne=c.execute('SELECT count(*) FROM network_edges').fetchone()[0]; na=c.execute('SELECT count(*) FROM network_agents').fetchone()[0]; print(f'Edges: {ne}, Agents: {na}')"`,
  });

  // ============================================================================
  // PHASE 6: FINAL VERIFICATION
  // Comprehensive check of all tables and coverage metrics
  // ============================================================================

  ctx.log('info', 'Phase 6: Final verification');

  const finalVerify = await ctx.task(shellTask, {
    projectRoot,
    phase: 'final-verification',
    command: `cd ${projectRoot} && python3 -c "
import sqlite3, os, json

c = sqlite3.connect('${dbPath}')
print('=' * 60)
print('FULL INGESTION PIPELINE — FINAL REPORT')
print('=' * 60)

# Core tables
r = c.execute('SELECT count(*) FROM records').fetchone()[0]
a = c.execute('SELECT count(DISTINCT agent_norm) FROM agents').fetchone()[0]
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
t = c.execute('SELECT count(*) FROM titles').fetchone()[0]
s = c.execute('SELECT count(*) FROM subjects').fetchone()[0]
print(f'Records:  {r}')
print(f'Agents:   {a} (distinct)')
print(f'Imprints: {i}')
print(f'Titles:   {t}')
print(f'Subjects: {s}')

# Authority URIs
uri = c.execute('SELECT count(DISTINCT authority_uri) FROM agents WHERE authority_uri IS NOT NULL').fetchone()[0]
print(f'Agents with authority_uri: {uri}')

# Normalization coverage
high_date = c.execute('SELECT count(*) FROM imprints WHERE date_confidence >= 0.9').fetchone()[0]
high_place = c.execute('SELECT count(*) FROM imprints WHERE place_confidence >= 0.9').fetchone()[0]
high_pub = c.execute('SELECT count(*) FROM imprints WHERE publisher_confidence >= 0.8').fetchone()[0]
print(f'\\nNormalization Coverage:')
print(f'  Date (>=0.9):      {high_date}/{i} ({100*high_date/i:.1f}%)')
print(f'  Place (>=0.9):     {high_place}/{i} ({100*high_place/i:.1f}%)')
print(f'  Publisher (>=0.8): {high_pub}/{i} ({100*high_pub/i:.1f}%)')

# Authorities
aa = c.execute('SELECT count(*) FROM agent_authorities').fetchone()[0]
al = c.execute('SELECT count(*) FROM agent_aliases').fetchone()[0]
print(f'\\nAuthorities:')
print(f'  Agent authorities: {aa}')
print(f'  Agent aliases:     {al}')
try:
    pa = c.execute('SELECT count(*) FROM publisher_authorities').fetchone()[0]
    pv = c.execute('SELECT count(*) FROM publisher_variants').fetchone()[0]
    print(f'  Publisher auth:    {pa}')
    print(f'  Publisher variants:{pv}')
except: pass

# Enrichment
try:
    ae = c.execute('SELECT count(*) FROM authority_enrichment').fetchone()[0]
    wd = c.execute('SELECT count(*) FROM authority_enrichment WHERE wikidata_id IS NOT NULL').fetchone()[0]
    print(f'\\nEnrichment:')
    print(f'  Authority enrichment: {ae} ({wd} with Wikidata)')
except: print('\\nNo authority_enrichment table')

try:
    wc = c.execute('SELECT count(*) FROM wikipedia_cache').fetchone()[0]
    ws = c.execute('SELECT count(*) FROM wikipedia_cache WHERE summary_extract IS NOT NULL').fetchone()[0]
    wconn = c.execute('SELECT count(*) FROM wikipedia_connections').fetchone()[0]
    print(f'  Wikipedia cache:      {wc} ({ws} with summaries)')
    print(f'  Wikipedia connections: {wconn}')
except: print('  No wikipedia tables')

# Network
try:
    ne = c.execute('SELECT count(*) FROM network_edges').fetchone()[0]
    na = c.execute('SELECT count(*) FROM network_agents').fetchone()[0]
    placed = c.execute('SELECT count(*) FROM network_agents WHERE lat IS NOT NULL').fetchone()[0]
    print(f'\\nNetwork:')
    print(f'  Edges:  {ne}')
    print(f'  Agents: {na} (placed: {placed})')
except: print('\\nNo network tables')

size_mb = os.path.getsize('${dbPath}') / 1024 / 1024
tables = len(c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall())
print(f'\\nDB: {size_mb:.1f} MB, {tables} tables')
print('=' * 60)
"`,
  });

  ctx.log('info', 'Full ingestion pipeline complete');

  return {
    success: true,
    marcXml,
    dbPath,
    stats,
  };
}

// ============================================================================
// Task Definitions
// ============================================================================

const agentTask = defineTask('pipeline-agent', (args, taskCtx) => ({
  kind: 'agent',
  title: args.taskName,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior data engineer running the bibliographic ingestion pipeline',
      task: args.taskName,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        marcXml: args.marcXml,
      },
      instructions: [
        `Working directory: ${args.projectRoot}`,
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

const shellTask = defineTask('pipeline-shell', (args, taskCtx) => ({
  kind: 'shell',
  title: `Verify ${args.phase}`,
  shell: {
    command: args.command,
    cwd: args.projectRoot,
    timeout: 120000,
  },
  io: {
    outputJsonPath: `tasks/${taskCtx.effectId}/output.json`,
  },
}));

const breakpointTask = defineTask('pipeline-breakpoint', (args, taskCtx) => ({
  kind: 'breakpoint',
  title: args.question,
  breakpoint: {
    question: args.question,
    options: args.options,
  },
}));
