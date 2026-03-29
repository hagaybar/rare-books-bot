/**
 * @process agent-role-enrichment
 * @description Enrich agent roles in the bibliographic database by resolving Wikidata occupations,
 * VIAF data, and web search to fill missing MARC relator terms. Three-tier approach:
 * Tier 1 (cached Wikidata occupations), Tier 2 (authority URI re-fetch), Tier 3 (web search for high-frequency agents).
 *
 * @inputs {
 *   projectRoot: string,
 *   dbPath: string,
 *   enrichmentCachePath: string,
 *   tier3MinFrequency: number
 * }
 * @outputs {
 *   success: boolean,
 *   totalAgentsProcessed: number,
 *   rolesAssigned: number,
 *   tier1Results: object,
 *   tier2Results: object,
 *   tier3Results: object,
 *   artifacts: array
 * }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @agent data-quality-engineer specializations/data-engineering-analytics/agents/data-quality-engineer/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    dbPath = 'data/index/bibliographic.db',
    enrichmentCachePath = 'data/enrichment/cache.db',
    tier3MinFrequency = 3,
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting Agent Role Enrichment process');

  // ============================================================================
  // PHASE 0: BACKUP & ANALYSIS
  // ============================================================================

  ctx.log('info', 'Phase 0: Backup database and analyze scope');

  const backup = await ctx.task(backupAndAnalyzeTask, {
    projectRoot,
    dbPath,
    enrichmentCachePath,
    tier3MinFrequency,
  });
  artifacts.push(...(backup.artifacts || []));

  // ============================================================================
  // PHASE 1: BUILD OCCUPATION → ROLE MAPPING
  // ============================================================================

  ctx.log('info', 'Phase 1: Build Wikidata occupation to role_norm mapping');

  const mappingTask = await ctx.task(buildOccupationMappingTask, {
    projectRoot,
    dbPath,
  });
  artifacts.push(...(mappingTask.artifacts || []));

  // Breakpoint: review the occupation mapping before applying
  await ctx.breakpoint({
    question: `Occupation → role_norm mapping created with ${mappingTask.mappingCount || '?'} entries. The mapping file is at data/normalization/occupation_role_map.json. Review the mapping before applying to the database?`,
    title: 'Review Occupation → Role Mapping',
    context: {
      mappingFile: 'data/normalization/occupation_role_map.json',
      sampleMappings: mappingTask.samples || [],
    },
  });

  // ============================================================================
  // PHASE 2: TIER 1 — APPLY CACHED WIKIDATA OCCUPATIONS (684 agents)
  // ============================================================================

  ctx.log('info', 'Phase 2: Tier 1 — Map cached Wikidata occupations to role_norm');

  const tier1 = await ctx.task(applyTier1Task, {
    projectRoot,
    dbPath,
    mappingFile: 'data/normalization/occupation_role_map.json',
  });
  artifacts.push(...(tier1.artifacts || []));

  // Verification for Tier 1
  const tier1Verify = await ctx.task(verifyTierTask, {
    projectRoot,
    dbPath,
    tier: 1,
    expectedCount: 684,
    resultsFile: tier1.resultsFile,
  });
  artifacts.push(...(tier1Verify.artifacts || []));

  // ============================================================================
  // PHASE 3: TIER 2 — FETCH MISSING WIKIDATA/VIAF (~298 agents)
  // ============================================================================

  ctx.log('info', 'Phase 3: Tier 2 — Re-fetch Wikidata/VIAF for agents with authority URIs but no occupations');

  const tier2 = await ctx.task(applyTier2Task, {
    projectRoot,
    dbPath,
    enrichmentCachePath,
    mappingFile: 'data/normalization/occupation_role_map.json',
  });
  artifacts.push(...(tier2.artifacts || []));

  // Verification for Tier 2
  const tier2Verify = await ctx.task(verifyTierTask, {
    projectRoot,
    dbPath,
    tier: 2,
    expectedCount: 298,
    resultsFile: tier2.resultsFile,
  });
  artifacts.push(...(tier2Verify.artifacts || []));

  // ============================================================================
  // PHASE 4: TIER 3 — WEB SEARCH FOR HIGH-FREQUENCY AGENTS (~40 agents)
  // ============================================================================

  ctx.log('info', 'Phase 4: Tier 3 — Web search for agents without authority URIs (frequency >= 3)');

  const tier3 = await ctx.task(applyTier3Task, {
    projectRoot,
    dbPath,
    tier3MinFrequency,
    mappingFile: 'data/normalization/occupation_role_map.json',
  });
  artifacts.push(...(tier3.artifacts || []));

  // Breakpoint: review web search results before applying
  await ctx.breakpoint({
    question: `Tier 3 web search completed for ${tier3.agentsSearched || '?'} high-frequency agents. ${tier3.rolesFound || '?'} roles found. Review results before applying?`,
    title: 'Review Tier 3 Web Search Results',
    context: {
      resultsFile: tier3.resultsFile,
      agentsSearched: tier3.agentsSearched,
      rolesFound: tier3.rolesFound,
    },
  });

  // Apply tier 3 results
  const tier3Apply = await ctx.task(applyTier3ResultsTask, {
    projectRoot,
    dbPath,
    resultsFile: tier3.resultsFile,
  });
  artifacts.push(...(tier3Apply.artifacts || []));

  // ============================================================================
  // PHASE 5: FINAL VERIFICATION & STATISTICS
  // ============================================================================

  ctx.log('info', 'Phase 5: Final verification and statistics');

  const finalVerify = await ctx.task(finalVerificationTask, {
    projectRoot,
    dbPath,
  });
  artifacts.push(...(finalVerify.artifacts || []));

  // Run existing tests to ensure no regressions
  const testRun = await ctx.task(runTestsTask, { projectRoot });

  return {
    success: true,
    totalAgentsProcessed: (tier1.processed || 0) + (tier2.processed || 0) + (tier3Apply.processed || 0),
    rolesAssigned: (tier1.rolesAssigned || 0) + (tier2.rolesAssigned || 0) + (tier3Apply.rolesAssigned || 0),
    tier1Results: {
      processed: tier1.processed,
      rolesAssigned: tier1.rolesAssigned,
      source: 'cached_wikidata_occupations',
    },
    tier2Results: {
      processed: tier2.processed,
      rolesAssigned: tier2.rolesAssigned,
      source: 'wikidata_viaf_refetch',
    },
    tier3Results: {
      processed: tier3Apply.processed,
      rolesAssigned: tier3Apply.rolesAssigned,
      source: 'web_search',
    },
    verification: finalVerify,
    artifacts,
    metadata: {
      processId: 'agent-role-enrichment',
      timestamp: startTime,
    },
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const backupAndAnalyzeTask = defineTask('backup-and-analyze', (args) => ({
  kind: 'agent',
  title: 'Backup database and analyze enrichment scope',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Database engineer specializing in bibliographic metadata',
      task: `Backup the bibliographic database and analyze the scope of agent role enrichment needed.

1. Create a timestamped backup:
   cp ${args.dbPath} ${args.dbPath}.backup.$(date +%Y%m%d_%H%M%S)

2. Run these analysis queries against ${args.dbPath} and report the results:

   a) Total agents with role_norm='other' AND role_source='unknown':
      SELECT COUNT(*), COUNT(DISTINCT agent_norm) FROM agents WHERE role_norm = 'other' AND role_source = 'unknown';

   b) Tier 1 — agents with cached Wikidata occupations:
      SELECT COUNT(DISTINCT a.agent_norm)
      FROM agents a JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
      WHERE a.role_norm = 'other' AND a.role_source = 'unknown'
      AND ae.person_info IS NOT NULL
      AND json_extract(ae.person_info, '$.occupations') <> '[]';

   c) Tier 2 — agents with authority URI but empty/no occupations:
      SELECT COUNT(DISTINCT a.agent_norm)
      FROM agents a
      LEFT JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
      WHERE a.role_norm = 'other' AND a.role_source = 'unknown'
      AND a.authority_uri IS NOT NULL AND a.authority_uri <> ''
      AND (ae.person_info IS NULL OR json_extract(ae.person_info, '$.occupations') = '[]' OR ae.authority_uri IS NULL);

   d) Tier 3 — agents without authority URIs by frequency:
      SELECT agent_norm, COUNT(*) as freq
      FROM agents
      WHERE role_norm = 'other' AND role_source = 'unknown'
      AND (authority_uri IS NULL OR authority_uri = '')
      GROUP BY agent_norm HAVING freq >= ${args.tier3MinFrequency}
      ORDER BY freq DESC;

   e) Current role_norm distribution:
      SELECT role_norm, COUNT(*) FROM agents GROUP BY role_norm ORDER BY COUNT(*) DESC;

   f) Extract all unique Wikidata occupation labels currently in the enrichment cache:
      SELECT DISTINCT value
      FROM authority_enrichment ae, json_each(json_extract(ae.person_info, '$.occupations'))
      WHERE ae.person_info IS NOT NULL
      ORDER BY value;
      Save this list to data/normalization/wikidata_occupations_raw.txt

3. Save the full analysis report to data/normalization/role_enrichment_analysis.json

Return: backup file path, scope counts for each tier, list of unique occupations found.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Create database backup first',
        'Run all analysis queries',
        'Save unique occupations list to data/normalization/wikidata_occupations_raw.txt',
        'Save analysis report as JSON',
        'Return summary with counts for each tier',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const buildOccupationMappingTask = defineTask('build-occupation-mapping', (args) => ({
  kind: 'agent',
  title: 'Build Wikidata occupation to role_norm mapping table',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Bibliographic metadata specialist with knowledge of MARC relator terms and Wikidata occupations',
      task: `Build a mapping from Wikidata occupation labels to the controlled role_norm vocabulary used in this project.

1. Read the unique Wikidata occupations list from data/normalization/wikidata_occupations_raw.txt

2. Read the controlled vocabulary from scripts/normalization/normalize_agent.py (lines 79-205) which defines the target role_norm values organized by category:
   - Authors: author, creator, compiler, contributor
   - Editors: editor, annotator, commentator, corrector, proofreader, redactor, reviewer
   - Writers: writer_of_preface, author_of_introduction, author_of_afterword
   - Translation: translator
   - Visual Arts: artist, illustrator, illuminator, engraver, etcher, lithographer, wood_engraver, draftsman, colorist, printmaker, photographer
   - Production: printer, publisher, binder, book_designer, book_producer, typographer, papermaker, marbler, manufacturer, distributor
   - Manuscripts: scribe, calligrapher, rubricator, inscriber
   - Cartography: cartographer, surveyor, delineator
   - Provenance: former_owner, owner, collector, donor, bookseller, curator
   - Patronage: dedicatee, patron, funder, sponsor, honoree
   - Conservation: conservator, restorationist
   - Other: facsimilist, signer, witness, censor, expert, researcher, other

3. Create a mapping file at data/normalization/occupation_role_map.json with this structure:
{
  "metadata": {
    "created": "ISO timestamp",
    "description": "Maps Wikidata occupation labels to MARC-based role_norm controlled vocabulary",
    "version": "1.0"
  },
  "direct_mappings": {
    "printer": { "role_norm": "printer", "confidence": 0.95, "note": "Direct match" },
    "publisher": { "role_norm": "publisher", "confidence": 0.95, "note": "Direct match" },
    "author": { "role_norm": "author", "confidence": 0.90, "note": "Direct match but person may have been author of other works, not necessarily the catalogued item" },
    "bookseller": { "role_norm": "bookseller", "confidence": 0.90, "note": "Direct match" },
    "translator": { "role_norm": "translator", "confidence": 0.90 },
    "editor": { "role_norm": "editor", "confidence": 0.90 },
    "engraver": { "role_norm": "engraver", "confidence": 0.90 },
    "illustrator": { "role_norm": "illustrator", "confidence": 0.90 },
    "calligrapher": { "role_norm": "calligrapher", "confidence": 0.90 },
    "cartographer": { "role_norm": "cartographer", "confidence": 0.90 },
    "lithographer": { "role_norm": "lithographer", "confidence": 0.90 },
    "typographer": { "role_norm": "typographer", "confidence": 0.90 },
    "scribe": { "role_norm": "scribe", "confidence": 0.90 },
    "photographer": { "role_norm": "photographer", "confidence": 0.90 },
    ...add all direct matches
  },
  "semantic_mappings": {
    "poet": { "role_norm": "author", "confidence": 0.80, "note": "Poets are authors in MARC context" },
    "writer": { "role_norm": "author", "confidence": 0.85, "note": "Generic writer maps to author" },
    "novelist": { "role_norm": "author", "confidence": 0.80 },
    "essayist": { "role_norm": "author", "confidence": 0.80 },
    "playwright": { "role_norm": "author", "confidence": 0.80 },
    "librettist": { "role_norm": "author", "confidence": 0.80 },
    "philosopher": { "role_norm": "author", "confidence": 0.70, "note": "Philosophers who wrote texts" },
    "theologian": { "role_norm": "author", "confidence": 0.70 },
    "historian": { "role_norm": "author", "confidence": 0.70 },
    "mathematician": { "role_norm": "author", "confidence": 0.65 },
    "jurist": { "role_norm": "author", "confidence": 0.65 },
    "printmaker": { "role_norm": "printmaker", "confidence": 0.90 },
    "etcher": { "role_norm": "etcher", "confidence": 0.90 },
    "wood engraver": { "role_norm": "wood_engraver", "confidence": 0.90 },
    "bookbinder": { "role_norm": "binder", "confidence": 0.90 },
    "book dealer": { "role_norm": "bookseller", "confidence": 0.85 },
    "bibliographer": { "role_norm": "researcher", "confidence": 0.75 },
    "university teacher": { "role_norm": "author", "confidence": 0.60, "note": "Academics who wrote texts" },
    "rabbi": { "role_norm": "author", "confidence": 0.65, "note": "Rabbis as authors of religious texts" },
    "physician": { "role_norm": "author", "confidence": 0.55, "note": "Physicians who wrote medical texts" },
    "patron of the arts": { "role_norm": "patron", "confidence": 0.85 },
    ...add all reasonable semantic mappings
  },
  "unmapped": [
    "sovereign", "politician", "banker", "diplomat", "military officer"
  ],
  "priority_order": [
    "printer", "publisher", "bookseller", "engraver", "illustrator", "etcher",
    "lithographer", "printmaker", "calligrapher", "scribe", "cartographer",
    "translator", "editor", "compiler", "annotator", "commentator",
    "author", "patron", "collector", "donor", "former_owner"
  ]
}

IMPORTANT rules for the mapping:
- Book-production roles (printer, publisher, bookseller, engraver, etc.) get HIGHEST priority since this is a rare books collection
- The "priority_order" array defines which occupation to prefer when an agent has multiple (e.g. if someone is both "printer" and "poet", assign "printer")
- Occupations not relevant to books at all (sovereign, politician, banker) go in "unmapped" and will remain as "other"
- Confidence reflects how certain the Wikidata occupation maps to the MARC role in the context of rare book cataloguing
- Every occupation found in wikidata_occupations_raw.txt must appear in either direct_mappings, semantic_mappings, or unmapped

4. Count how many mappings you created and return as mappingCount.
5. Return 5 sample mappings for the breakpoint review.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Read the occupations list from data/normalization/wikidata_occupations_raw.txt',
        'Read the controlled vocabulary from scripts/normalization/normalize_agent.py',
        'Create comprehensive mapping covering ALL occupations found',
        'Prioritize book-production roles for this rare books collection',
        'Save to data/normalization/occupation_role_map.json',
        'Return mappingCount and sample mappings',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const applyTier1Task = defineTask('apply-tier1', (args) => ({
  kind: 'agent',
  title: 'Tier 1: Apply cached Wikidata occupations to agents with unknown roles',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Database engineer with bibliographic metadata expertise',
      task: `Apply cached Wikidata occupations to agents that have role_norm='other' and role_source='unknown'.

This is Tier 1: these agents already have Wikidata occupations stored in authority_enrichment.person_info.

IMPORTANT: The user chose to STORE ALL MATCHING ROLES — meaning if an agent has multiple occupations that map to valid role_norm values, we create one row per role (not just pick one).

Steps:

1. Read the occupation mapping from ${args.mappingFile}

2. For each agent with role_norm='other' AND role_source='unknown' that has a matching authority_enrichment record with non-empty occupations:
   a. Extract occupations from json_extract(ae.person_info, '$.occupations')
   b. Look up each occupation in the mapping (direct_mappings first, then semantic_mappings)
   c. Skip occupations that are in the "unmapped" list
   d. For each mapped occupation, create a new agent row (or update existing) with:
      - role_norm = the mapped role
      - role_confidence = the mapping confidence
      - role_method = 'wikidata_occupation'
      - role_source = 'wikidata_p106'
      - role_raw = the original Wikidata occupation label

3. Strategy for multi-role agents:
   - Keep the original row but update it with the HIGHEST PRIORITY role (per priority_order in the mapping)
   - For each ADDITIONAL mapped role, INSERT a new row in the agents table duplicating all fields EXCEPT role_norm, role_confidence, role_method, role_source, role_raw
   - Use the priority_order from the mapping to determine which role gets the primary (updated) row

4. Write a Python script at scripts/normalization/apply_wikidata_roles.py that:
   - Reads the occupation_role_map.json
   - Queries the DB for Tier 1 agents
   - Applies the mapping with the multi-role strategy
   - Logs every change to data/normalization/tier1_role_changes.jsonl (one JSON line per change)
   - Reports summary statistics

5. Run the script and return results.

CRITICAL: Use a single transaction for all updates. Commit only after all changes are staged.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        mappingFile: args.mappingFile,
      },
      instructions: [
        'Read occupation_role_map.json',
        'Write scripts/normalization/apply_wikidata_roles.py',
        'The script must handle multi-role agents by creating additional rows',
        'Log all changes to tier1_role_changes.jsonl',
        'Run the script against the database',
        'Return processed count and roles assigned count',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const applyTier2Task = defineTask('apply-tier2', (args) => ({
  kind: 'agent',
  title: 'Tier 2: Re-fetch Wikidata/VIAF for agents with authority URIs but no occupations',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer with knowledge of Wikidata SPARQL and VIAF APIs',
      task: `Fetch occupations from Wikidata/VIAF for agents that have authority URIs but missing/empty occupations in the enrichment cache.

These are Tier 2 agents: they have an authority_uri but either:
- No corresponding authority_enrichment record
- An authority_enrichment record with empty occupations

Steps:

1. Identify Tier 2 agents:
   SELECT DISTINCT a.agent_norm, a.authority_uri
   FROM agents a
   LEFT JOIN authority_enrichment ae ON a.authority_uri = ae.authority_uri
   WHERE a.role_norm = 'other' AND a.role_source = 'unknown'
   AND a.authority_uri IS NOT NULL AND a.authority_uri <> ''
   AND (ae.person_info IS NULL
        OR json_extract(ae.person_info, '$.occupations') = '[]'
        OR json_extract(ae.person_info, '$.occupations') IS NULL
        OR ae.authority_uri IS NULL);

2. For each agent, use the existing enrichment infrastructure:
   - Use scripts/enrichment/nli_client.py: extract_nli_id_from_uri() to get NLI ID
   - Use scripts/enrichment/nli_client.py: get_wikidata_id_from_nli() to get Wikidata QID
   - Use scripts/enrichment/wikidata_client.py: enrich_agent_by_id() to fetch occupations
   - Fallback: if Wikidata has no occupations, try VIAF via the VIAF ID if available

3. Write a Python script at scripts/normalization/fetch_tier2_occupations.py that:
   - Imports the existing enrichment modules (nli_client, wikidata_client)
   - Processes each Tier 2 agent
   - Applies the occupation → role mapping from ${args.mappingFile}
   - Uses the same multi-role strategy as Tier 1
   - Logs changes to data/normalization/tier2_role_changes.jsonl
   - Includes rate limiting (1 request per second for Wikidata SPARQL)
   - Handles errors gracefully (skip agent on failure, log error)

4. Run the script and return results.

IMPORTANT: Reuse the project's existing Wikidata/NLI client code — do not re-implement SPARQL queries.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        enrichmentCachePath: args.enrichmentCachePath,
        mappingFile: args.mappingFile,
      },
      instructions: [
        'Query for Tier 2 agents (authority URI but no occupations)',
        'Write scripts/normalization/fetch_tier2_occupations.py using existing enrichment modules',
        'Include rate limiting and error handling',
        'Apply occupation mapping with multi-role strategy',
        'Log all changes to tier2_role_changes.jsonl',
        'Run the script',
        'Return processed count and roles assigned count',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const applyTier3Task = defineTask('apply-tier3-search', (args) => ({
  kind: 'agent',
  title: 'Tier 3: Web search for high-frequency agents without authority URIs',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Research librarian with expertise in rare books and historical figures',
      task: `Use web search to determine roles for agents that have no authority URI but appear frequently in the collection (${args.tier3MinFrequency}+ times).

1. Identify Tier 3 agents:
   SELECT agent_norm, COUNT(*) as freq
   FROM agents
   WHERE role_norm = 'other' AND role_source = 'unknown'
   AND (authority_uri IS NULL OR authority_uri = '')
   GROUP BY agent_norm HAVING freq >= ${args.tier3MinFrequency}
   ORDER BY freq DESC;

2. For each agent, perform a web search:
   - Search query: "{agent_name} role occupation printer publisher author bibliographer"
   - For names that appear to be Hebrew, also search with the transliterated form
   - Look for consistent role claims across multiple sources

3. Confidence scoring based on web search:
   - 0.85+ : Multiple authoritative sources (Wikipedia, VIAF, library catalogs) agree on role
   - 0.70-0.84: 2-3 sources agree, or one very authoritative source
   - 0.55-0.69: Only 1 source, or conflicting information
   - Below 0.55: Skip — leave as "other"

4. Map found roles to the controlled vocabulary using ${args.mappingFile}

5. Save results to data/normalization/tier3_web_search_results.json:
{
  "metadata": { "created": "ISO timestamp", "total_searched": N, "roles_found": N },
  "results": [
    {
      "agent_norm": "name",
      "frequency": N,
      "search_results_summary": "brief summary of what was found",
      "proposed_roles": [
        { "role_norm": "printer", "confidence": 0.85, "source": "url or description" }
      ],
      "skipped": false,
      "skip_reason": null
    }
  ]
}

6. Do NOT apply changes yet — just research and save results. The results will be reviewed at a breakpoint before applying.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        tier3MinFrequency: args.tier3MinFrequency,
        mappingFile: args.mappingFile,
      },
      instructions: [
        'Query for Tier 3 agents (no authority URI, frequency >= threshold)',
        'Web search each agent to determine their role',
        'Apply confidence scoring based on source quality and agreement',
        'Save structured results to tier3_web_search_results.json',
        'Do NOT apply to database yet',
        'Return agentsSearched and rolesFound counts',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const applyTier3ResultsTask = defineTask('apply-tier3-results', (args) => ({
  kind: 'agent',
  title: 'Apply approved Tier 3 web search results to database',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Database engineer',
      task: `Apply the reviewed Tier 3 web search results to the agents table.

1. Read results from ${args.resultsFile || 'data/normalization/tier3_web_search_results.json'}

2. For each agent with proposed_roles and confidence >= 0.55:
   - Update the primary row with the highest-priority role
   - Insert additional rows for secondary roles (same multi-role strategy as Tier 1)
   - Set role_method = 'web_search'
   - Set role_source = 'web_search'
   - Set role_raw = the source description

3. Log all changes to data/normalization/tier3_role_changes.jsonl

4. Return processed count and roles assigned count.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        resultsFile: args.resultsFile,
      },
      instructions: [
        'Read tier3_web_search_results.json',
        'Apply multi-role updates to the agents table',
        'Log changes to tier3_role_changes.jsonl',
        'Return processed and rolesAssigned counts',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const verifyTierTask = defineTask('verify-tier', (args) => ({
  kind: 'agent',
  title: `Verify Tier ${args.tier} enrichment results`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer for bibliographic data',
      task: `Verify the results of Tier ${args.tier} agent role enrichment.

1. Check the change log at ${args.resultsFile || `data/normalization/tier${args.tier}_role_changes.jsonl`}

2. Run verification queries:
   a) How many agents still have role_norm='other' AND role_source='unknown'?
   b) Distribution of new role_norm values assigned in this tier
   c) Sample 10 random agents that were updated — show old vs new values
   d) Check for any agents that got unexpected roles (e.g., a known author assigned 'printer')

3. Spot-check 5 specific cases:
   - Pick agents from the change log
   - Verify the Wikidata occupation matches the assigned role
   - Flag any suspicious mappings

4. Report: { verified: true/false, issues: [...], stats: {...} }`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        tier: args.tier,
      },
      instructions: [
        'Read the change log for this tier',
        'Run verification queries',
        'Spot-check 5 specific cases',
        'Report any issues found',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const finalVerificationTask = defineTask('final-verification', (args) => ({
  kind: 'agent',
  title: 'Final verification and statistics report',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data quality analyst for bibliographic metadata',
      task: `Generate a comprehensive final report on the agent role enrichment process.

Run these queries against ${args.dbPath}:

1. Before vs After comparison:
   - Count agents by role_norm (compare with the pre-enrichment baseline from data/normalization/role_enrichment_analysis.json)
   - Count agents still with role_norm='other'

2. Enrichment method distribution:
   SELECT role_method, role_source, COUNT(*) FROM agents
   WHERE role_method IN ('wikidata_occupation', 'web_search')
   GROUP BY role_method, role_source;

3. Confidence distribution for newly assigned roles:
   SELECT
     CASE
       WHEN role_confidence >= 0.90 THEN 'high (>=0.90)'
       WHEN role_confidence >= 0.70 THEN 'medium (0.70-0.89)'
       WHEN role_confidence >= 0.55 THEN 'low (0.55-0.69)'
       ELSE 'very_low (<0.55)'
     END as confidence_band,
     COUNT(*)
   FROM agents
   WHERE role_method IN ('wikidata_occupation', 'web_search')
   GROUP BY confidence_band;

4. Key test case: Verify Aldus Manutius now has role=printer:
   SELECT agent_norm, role_norm, role_confidence, role_method
   FROM agents WHERE agent_norm LIKE '%manuzio%' OR agent_norm LIKE '%manutius%';

5. Multi-role agents: How many agents now have more than one role?
   SELECT agent_norm, COUNT(DISTINCT role_norm) as role_count
   FROM agents GROUP BY agent_norm HAVING role_count > 1
   ORDER BY role_count DESC LIMIT 20;

6. Save final report to data/normalization/role_enrichment_final_report.json

7. Print a human-readable summary to stdout.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Run all verification queries',
        'Compare with pre-enrichment baseline',
        'Verify the Aldus Manutius test case specifically',
        'Save report as JSON',
        'Print readable summary',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const runTestsTask = defineTask('run-tests', (args) => ({
  kind: 'shell',
  title: 'Run existing test suite to check for regressions',
  shell: {
    command: `cd ${args.projectRoot} && poetry run python -m pytest tests/ -x -q --timeout=60 2>&1 | tail -30`,
  },
}));
