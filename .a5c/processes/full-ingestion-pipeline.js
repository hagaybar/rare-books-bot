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
  // PHASE 2: NORMALIZATION QA AUDIT & CORRECTION LOOP
  // Methodical review of normalization gaps — dates, places, publishers
  // Each field: audit → categorize → propose fixes → user approves → apply → re-verify
  // ============================================================================

  ctx.log('info', 'Phase 2: Normalization QA — audit, propose fixes, apply corrections');

  // --- 2a: Audit all normalization gaps ---
  const qaAudit = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'QA Audit: scan all normalization gaps',
    description: `Run a comprehensive audit of normalization quality across all three fields.

Query the database and produce a structured JSON report at data/qa/norm_audit.json:

mkdir -p data/qa

python3 << 'PYEOF'
import sqlite3, json
c = sqlite3.connect('${dbPath}')
audit = {"date": {}, "place": {}, "publisher": {}}
total = c.execute('SELECT count(*) FROM imprints').fetchone()[0]

# === DATE AUDIT ===
# Group by method and confidence
date_methods = c.execute(
    "SELECT date_method, date_confidence, count(*) as cnt FROM imprints WHERE date_raw IS NOT NULL GROUP BY date_method, date_confidence ORDER BY cnt DESC"
).fetchall()
audit["date"]["by_method"] = [{"method": m, "confidence": conf, "count": cnt} for m, conf, cnt in date_methods]

# Low confidence / unparsed dates with raw values
low_dates = c.execute(
    "SELECT date_raw, date_start, date_end, date_method, date_confidence, count(*) as cnt FROM imprints WHERE (date_confidence < 0.9 OR date_confidence IS NULL) AND date_raw IS NOT NULL GROUP BY date_raw ORDER BY cnt DESC LIMIT 50"
).fetchall()
audit["date"]["low_confidence"] = [{"raw": r[0], "start": r[1], "end": r[2], "method": r[3], "confidence": r[4], "count": r[5]} for r in low_dates]
audit["date"]["low_count"] = c.execute("SELECT count(*) FROM imprints WHERE (date_confidence < 0.9 OR date_confidence IS NULL) AND date_raw IS NOT NULL").fetchone()[0]
audit["date"]["high_count"] = c.execute("SELECT count(*) FROM imprints WHERE date_confidence >= 0.9").fetchone()[0]

# === PLACE AUDIT ===
low_places = c.execute(
    "SELECT place_raw, place_norm, place_method, place_confidence, count(*) as cnt FROM imprints WHERE (place_confidence < 0.9 OR place_confidence IS NULL) AND place_raw IS NOT NULL GROUP BY place_raw ORDER BY cnt DESC LIMIT 50"
).fetchall()
audit["place"]["low_confidence"] = [{"raw": r[0], "norm": r[1], "method": r[2], "confidence": r[3], "count": r[4]} for r in low_places]
audit["place"]["low_count"] = c.execute("SELECT count(*) FROM imprints WHERE (place_confidence < 0.9 OR place_confidence IS NULL) AND place_raw IS NOT NULL").fetchone()[0]
audit["place"]["high_count"] = c.execute("SELECT count(*) FROM imprints WHERE place_confidence >= 0.9").fetchone()[0]

# Missing / unmapped places (have raw but no norm)
unmapped_places = c.execute(
    "SELECT place_raw, count(*) as cnt FROM imprints WHERE place_norm IS NULL AND place_raw IS NOT NULL AND place_raw != '' GROUP BY place_raw ORDER BY cnt DESC LIMIT 30"
).fetchall()
audit["place"]["unmapped"] = [{"raw": r[0], "count": r[1]} for r in unmapped_places]

# === PUBLISHER AUDIT ===
low_pubs = c.execute(
    "SELECT publisher_raw, publisher_norm, publisher_method, publisher_confidence, count(*) as cnt FROM imprints WHERE (publisher_confidence < 0.8 OR publisher_confidence IS NULL) AND publisher_raw IS NOT NULL GROUP BY publisher_raw ORDER BY cnt DESC LIMIT 50"
).fetchall()
audit["publisher"]["low_confidence"] = [{"raw": r[0], "norm": r[1], "method": r[2], "confidence": r[3], "count": r[4]} for r in low_pubs]
audit["publisher"]["low_count"] = c.execute("SELECT count(*) FROM imprints WHERE (publisher_confidence < 0.8 OR publisher_confidence IS NULL) AND publisher_raw IS NOT NULL").fetchone()[0]
audit["publisher"]["high_count"] = c.execute("SELECT count(*) FROM imprints WHERE publisher_confidence >= 0.8").fetchone()[0]

audit["total_imprints"] = total
audit["summary"] = {
    "date_coverage_pct": round(100 * audit["date"]["high_count"] / total, 1),
    "place_coverage_pct": round(100 * audit["place"]["high_count"] / total, 1),
    "publisher_coverage_pct": round(100 * audit["publisher"]["high_count"] / total, 1),
}

with open('data/qa/norm_audit.json', 'w') as f:
    json.dump(audit, f, indent=2, ensure_ascii=False)

print(json.dumps(audit["summary"], indent=2))
print(f"Date gaps: {audit['date']['low_count']}")
print(f"Place gaps: {audit['place']['low_count']}")
print(f"Publisher gaps: {audit['publisher']['low_count']}")
print("Full audit written to data/qa/norm_audit.json")
PYEOF`,
    testCommand: `cd ${projectRoot} && python3 -c "import json; a=json.load(open('data/qa/norm_audit.json')); print(a['summary'])"`,
  });

  // --- 2b: Date fixes ---
  const dateFixTask = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'QA Fix: Date normalization gaps',
    description: `Review and fix date normalization gaps.

Read the audit report: data/qa/norm_audit.json — look at the "date" section.

For each low-confidence or unparsed date in audit["date"]["low_confidence"]:

1. CATEGORIZE the issue:
   - "hebrew_unparsed": Hebrew calendar date not recognized (e.g., תק"ג, שנת ה'שע"ח)
   - "complex_range": Multiple dates or ranges not captured (e.g., "1758-1765")
   - "circa_variant": Circa notation variant not recognized (e.g., "ca.", "um", "environ")
   - "embedded_noise": Date buried in other text
   - "no_date": Genuinely has no date (e.g., "n.d.", "[s.a.]")
   - "already_correct": The normalization is actually correct but confidence is low

2. For fixable issues, determine if the fix should be:
   a) A NEW PATTERN in scripts/marc/normalize.py (for recurring patterns)
   b) A DIRECT DB UPDATE for one-off values (using the feedback_loop.py pattern)

3. For new patterns: add them to normalize_date() in scripts/marc/normalize.py. Run tests.
4. For direct fixes: prepare SQL UPDATE statements but DO NOT execute them yet.

Write proposed fixes to data/qa/date_fixes_proposed.json:
{
  "new_patterns": [{"pattern": "...", "example_raw": "...", "expected_start": N, "expected_end": N, "confidence": 0.X}],
  "direct_fixes": [{"raw": "...", "current_start": N, "proposed_start": N, "proposed_end": N, "proposed_confidence": 0.X, "reason": "..."}],
  "already_correct": [{"raw": "...", "count": N, "reason": "confidence is actually appropriate"}],
  "unfixable": [{"raw": "...", "count": N, "reason": "genuinely no date"}],
  "summary": {"total_gaps": N, "fixable": N, "new_patterns": N, "direct_fixes": N, "already_correct": N, "unfixable": N}
}

If new patterns were added to normalize.py, run: poetry run pytest tests/ -k "date" -v
Commit code changes (new patterns) but NOT the proposed fixes JSON (that's for review).`,
    testCommand: `cd ${projectRoot} && python3 -c "import json; f=json.load(open('data/qa/date_fixes_proposed.json')); print(f['summary'])"`,
  });

  // --- 2c: Place fixes ---
  const placeFixTask = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'QA Fix: Place normalization gaps',
    description: `Review and fix place normalization gaps.

Read the audit report: data/qa/norm_audit.json — look at the "place" section.

For each low-confidence or unmapped place:

1. CATEGORIZE:
   - "latin_toponym": Latin place name (e.g., "Lugduni Batavorum" → "leiden")
   - "hebrew_place": Hebrew script place name not in alias map
   - "historical_rename": Historical name no longer used (e.g., "Pressburg" → "bratislava")
   - "bracket_variant": Bracketed form not stripped (e.g., "[Paris]")
   - "sine_loco_variant": An "unknown place" marker in another language
   - "already_mapped": Actually in the alias map but not matching (debug why)

2. For each fixable place, propose an alias map entry:
   {"raw_variant": "Lugduni Batavorum", "canonical": "leiden", "confidence": 0.95}

3. Write proposed fixes to data/qa/place_fixes_proposed.json:
{
  "new_aliases": [{"raw": "...", "canonical": "...", "category": "latin_toponym|hebrew_place|...", "affected_records": N}],
  "unfixable": [{"raw": "...", "count": N, "reason": "..."}],
  "summary": {"total_gaps": N, "fixable": N, "new_aliases": N, "unfixable": N}
}

Do NOT modify the alias map yet — just propose.`,
    testCommand: `cd ${projectRoot} && python3 -c "import json; f=json.load(open('data/qa/place_fixes_proposed.json')); print(f['summary'])"`,
  });

  // --- 2d: Publisher fixes ---
  const pubFixTask = await ctx.task(agentTask, {
    projectRoot, dbPath,
    taskName: 'QA Fix: Publisher normalization gaps',
    description: `Review and fix publisher normalization gaps.

Read the audit report: data/qa/norm_audit.json — look at the "publisher" section.

For each low-confidence or unmapped publisher:

1. CATEGORIZE:
   - "sine_nomine_variant": A "publisher unknown" marker (e.g., "s.n.", "[publisher not identified]")
   - "latin_form": Latin publisher name (e.g., "apud Elzevirios")
   - "punctuation_issue": Trailing punctuation/brackets causing mismatch
   - "already_mapped": Should be in alias map but not matching (debug why)

2. Propose alias map entries for fixable publishers.

3. Write proposed fixes to data/qa/publisher_fixes_proposed.json (same structure as place fixes).

Do NOT modify the alias map yet — just propose.`,
    testCommand: `cd ${projectRoot} && python3 -c "import json; f=json.load(open('data/qa/publisher_fixes_proposed.json')); print(f['summary'])"`,
  });

  // --- 2e: User reviews and approves fixes ---
  const reviewBreakpoint = await ctx.task(breakpointTask, {
    question: 'Normalization QA complete. Proposed fixes are in data/qa/*_fixes_proposed.json. Review them and approve applying the fixes.',
    options: [
      'Approve all fixes — apply to alias maps and re-normalize',
      'Skip fixes — proceed with current normalization as-is',
    ],
  });

  if (reviewBreakpoint?.approved) {
    // --- 2f: Apply approved fixes ---
    const applyFixes = await ctx.task(agentTask, {
      projectRoot, dbPath,
      taskName: 'Apply approved normalization fixes',
      description: `Apply the proposed normalization fixes.

1. PLACE FIXES: Read data/qa/place_fixes_proposed.json.
   For each entry in "new_aliases", add to data/normalization/place_aliases/place_alias_map.json.
   Use the feedback loop pattern:
     python3 -c "
import json
# Load existing map
with open('data/normalization/place_aliases/place_alias_map.json') as f:
    alias_map = json.load(f)
# Load proposed fixes
with open('data/qa/place_fixes_proposed.json') as f:
    fixes = json.load(f)
# Add new aliases
added = 0
for fix in fixes['new_aliases']:
    key = fix['raw'].lower().strip()
    if key not in alias_map:
        alias_map[key] = fix['canonical']
        added += 1
# Save
with open('data/normalization/place_aliases/place_alias_map.json', 'w') as f:
    json.dump(alias_map, f, indent=2, ensure_ascii=False, sort_keys=True)
print(f'Added {added} place aliases')
"

2. PUBLISHER FIXES: Same pattern for data/normalization/publisher_aliases/publisher_alias_map.json.

3. RE-RUN M2+M3 to apply the new alias maps:
   cd ${projectRoot} && poetry run python -m scripts.marc.rebuild_pipeline

   This re-normalizes with the updated maps and rebuilds the SQLite index.

4. VERIFY improvement:
   python3 -c "
import sqlite3
c = sqlite3.connect('${dbPath}')
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
hd = c.execute('SELECT count(*) FROM imprints WHERE date_confidence >= 0.9').fetchone()[0]
hp = c.execute('SELECT count(*) FROM imprints WHERE place_confidence >= 0.9').fetchone()[0]
hpub = c.execute('SELECT count(*) FROM imprints WHERE publisher_confidence >= 0.8').fetchone()[0]
print(f'AFTER FIXES:')
print(f'  Date coverage:      {hd}/{i} ({100*hd/i:.1f}%)')
print(f'  Place coverage:     {hp}/{i} ({100*hp/i:.1f}%)')
print(f'  Publisher coverage: {hpub}/{i} ({100*hpub/i:.1f}%)')
"

5. Commit alias map changes:
   git add data/normalization/place_aliases/place_alias_map.json data/normalization/publisher_aliases/publisher_alias_map.json scripts/marc/normalize.py
   git commit -m "fix: apply normalization corrections from QA audit"`,
      testCommand: `cd ${projectRoot} && python3 -c "import sqlite3; c=sqlite3.connect('${dbPath}'); i=c.execute('SELECT count(*) FROM imprints').fetchone()[0]; hp=c.execute('SELECT count(*) FROM imprints WHERE place_confidence >= 0.9').fetchone()[0]; print(f'Place coverage: {100*hp/i:.1f}%')"`,
    });

    // --- 2g: Post-fix verification ---
    const postFixVerify = await ctx.task(shellTask, {
      projectRoot,
      phase: 'post-fix-verify',
      command: `cd ${projectRoot} && python3 -c "
import sqlite3, json
c = sqlite3.connect('${dbPath}')
i = c.execute('SELECT count(*) FROM imprints').fetchone()[0]
hd = c.execute('SELECT count(*) FROM imprints WHERE date_confidence >= 0.9').fetchone()[0]
hp = c.execute('SELECT count(*) FROM imprints WHERE place_confidence >= 0.9').fetchone()[0]
hpub = c.execute('SELECT count(*) FROM imprints WHERE publisher_confidence >= 0.8').fetchone()[0]
remaining_date = c.execute('SELECT count(*) FROM imprints WHERE (date_confidence < 0.9 OR date_confidence IS NULL) AND date_raw IS NOT NULL').fetchone()[0]
remaining_place = c.execute('SELECT count(*) FROM imprints WHERE (place_confidence < 0.9 OR place_confidence IS NULL) AND place_raw IS NOT NULL').fetchone()[0]
remaining_pub = c.execute('SELECT count(*) FROM imprints WHERE (publisher_confidence < 0.8 OR publisher_confidence IS NULL) AND publisher_raw IS NOT NULL').fetchone()[0]
print('POST-FIX NORMALIZATION COVERAGE:')
print(f'  Date:      {hd}/{i} ({100*hd/i:.1f}%) — {remaining_date} gaps remaining')
print(f'  Place:     {hp}/{i} ({100*hp/i:.1f}%) — {remaining_place} gaps remaining')
print(f'  Publisher: {hpub}/{i} ({100*hpub/i:.1f}%) — {remaining_pub} gaps remaining')
"`,
    });
  }

  // ============================================================================
  // PHASE 3: AUTHORITY SYSTEMS
  // Seed agent authorities + aliases, populate publisher authorities
  // ============================================================================

  ctx.log('info', 'Phase 3: Seed agent & publisher authorities');

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
  // PHASE 4: WIKIDATA ENRICHMENT
  // Enrich agents via authority URIs (preferred) or name-based search (fallback)
  // ============================================================================

  if (!skipEnrichment) {
    ctx.log('info', 'Phase 4: Wikidata enrichment');

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

      ctx.log('info', 'Phase 5: Wikipedia enrichment (3 passes)');

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
  // PHASE 6: NETWORK TABLES
  // Materialize network_edges and network_agents for the Network Map Explorer
  // ============================================================================

  ctx.log('info', 'Phase 6: Build network tables');

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
  // PHASE 7: FINAL VERIFICATION
  // Comprehensive check of all tables and coverage metrics
  // ============================================================================

  ctx.log('info', 'Phase 7: Final verification');

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
