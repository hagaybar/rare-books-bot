/**
 * @process publisher-authority-records
 * @description Save publisher research data and create an internal publisher authority record system
 * with schema design, testing on 10-15 publishers, refinement, and database implementation.
 *
 * @inputs {
 *   projectRoot: string,
 *   dbPath: string,
 *   schemaPath: string
 * }
 * @outputs {
 *   success: boolean,
 *   researchFile: string,
 *   authorityRecordsCreated: number,
 *   schemaVersion: string,
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
    schemaPath = 'scripts/marc/m3_schema.sql',
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting Publisher Authority Records process');

  // ============================================================================
  // PHASE 1: SAVE PUBLISHER RESEARCH DATA
  // ============================================================================

  ctx.log('info', 'Phase 1: Save all publisher research to structured file');

  const saveResearch = await ctx.task(saveResearchDataTask, {
    projectRoot,
    dbPath,
  });
  artifacts.push(...(saveResearch.artifacts || []));

  // ============================================================================
  // PHASE 2a: DESIGN AUTHORITY RECORD SCHEMA
  // ============================================================================

  ctx.log('info', 'Phase 2a: Design publisher authority record schema');

  const schemaDesign = await ctx.task(designSchemaTask, {
    projectRoot,
    dbPath,
    schemaPath,
    researchFile: saveResearch.researchFile,
  });
  artifacts.push(...(schemaDesign.artifacts || []));

  // ============================================================================
  // PHASE 2b: TEST SCHEMA ON 10-15 PUBLISHERS
  // ============================================================================

  ctx.log('info', 'Phase 2b: Test schema on 10-15 publishers');

  const schemaTest = await ctx.task(testSchemaTask, {
    projectRoot,
    dbPath,
    schemaDesign,
    researchFile: saveResearch.researchFile,
  });
  artifacts.push(...(schemaTest.artifacts || []));

  // ============================================================================
  // PHASE 2c: REVIEW AND REFINE SCHEMA (breakpoint for user approval)
  // ============================================================================

  ctx.log('info', 'Phase 2c: Review schema test results and refine');

  await ctx.breakpoint({
    question: `Schema tested on ${schemaTest.publishersTested || '10-15'} publishers. Review the schema design and test results before creating the final authority table. The schema, test data, and any issues found will be presented for your review. Proceed with refinement and final implementation?`,
    title: 'Publisher Authority Schema Review',
    context: {
      runId: ctx.runId,
      summary: 'Schema designed and tested on sample publishers',
    },
  });

  const schemaRefine = await ctx.task(refineSchemaTask, {
    projectRoot,
    dbPath,
    schemaDesign,
    schemaTest,
  });
  artifacts.push(...(schemaRefine.artifacts || []));

  // ============================================================================
  // PHASE 2d: CREATE AUTHORITY RECORDS IN DATABASE
  // ============================================================================

  ctx.log('info', 'Phase 2d: Create publisher authority records in database');

  const createRecords = await ctx.task(createAuthorityRecordsTask, {
    projectRoot,
    dbPath,
    schemaPath,
    schemaRefine,
    researchFile: saveResearch.researchFile,
  });
  artifacts.push(...(createRecords.artifacts || []));

  // ============================================================================
  // PHASE 3: VERIFICATION
  // ============================================================================

  ctx.log('info', 'Phase 3: Verify authority records and run tests');

  const verify = await ctx.task(verifyAuthorityRecordsTask, {
    projectRoot,
    dbPath,
  });
  artifacts.push(...(verify.artifacts || []));

  // Run tests
  const testRun = await ctx.task(runTestsShellTask, { projectRoot });

  return {
    success: true,
    researchFile: saveResearch.researchFile,
    authorityRecordsCreated: createRecords.recordsCreated,
    schemaVersion: schemaRefine.schemaVersion || 'v1',
    artifacts,
    metadata: {
      processId: 'publisher-authority-records',
      timestamp: startTime,
    },
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const saveResearchDataTask = defineTask('save-research-data', (args) => ({
  kind: 'agent',
  title: 'Save all publisher research data to structured file',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer specializing in bibliographic metadata',
      task: `Save ALL publisher research data to a structured JSON file at data/normalization/publisher_research.json.

This file must contain the complete research results for all 29 researched publishers from the current conversation context. The data includes canonical names, confidence scores, historical notes, sources, and identification details.

The file structure should be:
{
  "metadata": {
    "created": "ISO timestamp",
    "version": "1.0",
    "total_publishers": N,
    "description": "Publisher research for rare books bibliographic database"
  },
  "publishers": [
    {
      "normalized_form": "the form as it appears in the database",
      "canonical_name": "canonical English name",
      "confidence": 0.0-1.0,
      "type": "commercial_publisher|private_press|printing_house|bibliophile_society|unknown_marker",
      "dates_active": "e.g. 1583-1712 or null",
      "location": "city, country",
      "notes": "detailed identification notes",
      "sources": ["list of reference URLs or citations"],
      "variants": ["list of known name variants in the database"],
      "is_missing_marker": false
    }
  ]
}

Include ALL 29 publishers from the research:
1. חמו"ל - [publisher unknown] (Hebrew abbreviation)
2. ex officina elzeviriana - House of Elzevir
3. nella stamparia bragadina - Bragadin Press, Venice
4. nella stamparia vendramina - Vendramin Press, Venice
5. a. a. m. stols - A.A.M. Stols
6. f. dummler - Ferdinand Dummler, Berlin
7. verdiere - Verdiere, Paris
8. insel - Insel Verlag
9. aldus - Aldine Press, Venice
10. ex officina finceliana - Officina Finceliana, Wittenberg
11. apud s. gryphium - Sebastian Gryphius, Lyon
12. ex officina c. plantini - Christophe Plantin, Antwerp
13. apud janssonio-waesbergios - Janssonius van Waesberge, Amsterdam
14. apud i. & c. blaeu - Joan & Cornelis Blaeu, Amsterdam
15. apud g. & i. blaeu - Willem & Joan Blaeu, Amsterdam
16. ex officina elseviriorum - House of Elzevir, Leiden
17. impensis orphanotrophei - Francke Orphanage Press, Halle
18. typis et impensis orphanotrophei - Francke Orphanage Press, Halle
19. in aedibus aldi et andreae - Aldine Press (with Torresani)
20. דניאל זאניטי - Daniel Zanetti, Venice
21. דפוס דניאל בומבירגי / בבית דניאל בומבירגי - Daniel Bomberg, Venice
22. רוברטוס סטפניוס - Robert Estienne, Paris
23. קורנילייו אדיל קינד - Cornelio Adelkind, Venice
24. במצות אמברוסיאו פרוביניאו ובביתו - Ambrosius Froben, Basel
25. מארקו אנטוניאו יושטיניאן - Marco Antonio Giustiniani, Venice
26. soncino-gesellschaft - Soncino Society, Berlin
27. berliner bibliophilen abend - Berliner Bibliophilen Abend
28. grolier club - Grolier Club, New York
29. privatdruck - [privately printed] (not a publisher)

Also scan the database for additional publishers with frequency >= 3 that are NOT in the research list. For each, query the imprints table:
SELECT publisher_norm, COUNT(*) as freq FROM imprints WHERE publisher_norm IS NOT NULL GROUP BY publisher_norm HAVING freq >= 3 ORDER BY freq DESC

Add these to the file with type="unresearched" and confidence=0.5.

Additionally, create a publisher alias map at data/normalization/publisher_aliases/publisher_alias_map.json mapping normalized forms to canonical names (same pattern as the place alias map).`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Create data/normalization/publisher_research.json with all 29 researched publishers',
        'Query the database for additional high-frequency publishers',
        'Create data/normalization/publisher_aliases/ directory',
        'Create publisher_alias_map.json',
        'Verify both files are valid JSON',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const designSchemaTask = defineTask('design-schema', (args) => ({
  kind: 'agent',
  title: 'Design publisher authority record schema',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Database architect with knowledge of library authority systems (VIAF, ISNI, LCNAF)',
      task: `Design a schema for an internal publisher authority records table in the existing SQLite database.

Read the existing schema at scripts/marc/m3_schema.sql to understand the current table structure (especially the authority_enrichment table for agents — use that as a reference pattern).

Read the publisher research file at data/normalization/publisher_research.json to understand the data we need to store.

The schema should support:
1. Canonical publisher identity (name, location, dates active)
2. Multiple name variants (Hebrew, Latin, vernacular forms)
3. Cross-references to external authorities (VIAF, Wikidata, CERL)
4. Publisher type classification (printing house, private press, bibliophile society, etc.)
5. Relationship to imprints table (link publisher authority to actual records)
6. Historical notes and source citations
7. Confidence scoring

Design considerations:
- Should this be one table or normalized into multiple tables?
- How to handle publisher variants (separate table with FK, or JSON array in main table)?
- How to link to imprints (via publisher_norm column match, or explicit FK)?
- Consider the existing pattern: authority_enrichment table uses JSON columns for flexible data

Create the schema SQL file at scripts/marc/publisher_authority_schema.sql.
Also create a Python module at scripts/metadata/publisher_authority.py with:
- Pydantic/dataclass models matching the schema
- CRUD functions (create, read, update, search)
- A function to link authority records to imprint rows

Write tests at tests/scripts/metadata/test_publisher_authority.py.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
        schemaPath: args.schemaPath,
      },
      instructions: [
        'Read scripts/marc/m3_schema.sql for the existing pattern',
        'Read data/normalization/publisher_research.json for the data model',
        'Design the schema SQL',
        'Create the Python module with models and CRUD',
        'Write tests',
        'Run tests to verify',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const testSchemaTask = defineTask('test-schema', (args) => ({
  kind: 'agent',
  title: 'Test schema on 10-15 publishers from research',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer testing a database schema',
      task: `Test the publisher authority schema by populating it with 10-15 publishers from the research data.

Read the publisher authority module at scripts/metadata/publisher_authority.py.
Read the research data at data/normalization/publisher_research.json.

Select 10-15 publishers that represent diverse cases:
- A major printing dynasty (Elzevir, Plantin, Aldine Press)
- A Hebrew printer (Bomberg, Bragadin)
- A modern publisher (Insel Verlag)
- A bibliophile society (Grolier Club, Soncino Society)
- A missing marker (חמו"ל, privatdruck)
- A publisher with multiple name variants
- A publisher with known dates and location

For each:
1. Create the authority record using the CRUD functions
2. Add name variants
3. Link to actual imprint records in the database
4. Query back and verify all data is correct

Report:
- Which publishers were tested
- Any schema issues found (missing fields, wrong types, relationship problems)
- Any edge cases that the schema doesn't handle well
- Suggested refinements

Create a test report at data/metadata/publisher_authority_test_report.json.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Read the authority module and research data',
        'Select 10-15 diverse test publishers',
        'Create authority records for each',
        'Link to imprint records',
        'Query back and verify',
        'Document issues and suggestions',
        'Save test report',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const refineSchemaTask = defineTask('refine-schema', (args) => ({
  kind: 'agent',
  title: 'Refine schema based on test results',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Database architect refining a schema based on test feedback',
      task: `Read the test report at data/metadata/publisher_authority_test_report.json and refine the publisher authority schema.

Address any issues found during testing:
- Missing fields or wrong types
- Relationship problems
- Edge cases not handled
- Performance concerns (missing indexes)

Update:
1. scripts/marc/publisher_authority_schema.sql - refined schema
2. scripts/metadata/publisher_authority.py - updated models and CRUD
3. tests/scripts/metadata/test_publisher_authority.py - updated tests

If the schema changed significantly, drop and recreate the test tables.
Run all tests to verify the refinements work.

Also update the m3_schema.sql file to include the publisher authority tables so they're created as part of the standard pipeline.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Read the test report for issues',
        'Refine the schema SQL',
        'Update the Python module',
        'Update tests',
        'Run tests to verify',
        'Update m3_schema.sql to include publisher authority tables',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const createAuthorityRecordsTask = defineTask('create-authority-records', (args) => ({
  kind: 'agent',
  title: 'Create publisher authority records in database for all researched publishers',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer populating a publisher authority database',
      task: `Create publisher authority records for ALL publishers in the research file.

Read data/normalization/publisher_research.json for the full list.
Read scripts/metadata/publisher_authority.py for the CRUD functions.

For each publisher in the research:
1. Create the authority record with all available data
2. Add all known name variants (Hebrew, Latin, vernacular)
3. Link to imprint records in the database by matching publisher_norm
4. Set confidence scores

Also scan the imprints table for any high-frequency publishers NOT in the research file.
For these, create stub authority records with type="unresearched" so they can be enriched later.

After populating:
- Report total authority records created
- Report total variant mappings
- Report total imprint linkages
- Log all changes to logs/publisher_authority_creation.jsonl

Present the results for user approval before the final commit (per project convention: always show data fixes for approval).`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Read the research file and authority module',
        'Create authority records for all 29 researched publishers',
        'Add name variants for each',
        'Link to imprint records',
        'Create stub records for unresearched high-frequency publishers',
        'Log all changes',
        'Report summary statistics',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const verifyAuthorityRecordsTask = defineTask('verify-authority-records', (args) => ({
  kind: 'agent',
  title: 'Verify authority records and write integration tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer verifying data integrity',
      task: `Verify the publisher authority records in the database.

Check:
1. All 29 researched publishers have authority records
2. Name variants are correctly linked
3. Imprint linkages are correct (query imprints joined with authority)
4. No orphaned records
5. Confidence scores are set
6. The metadata API can serve authority data (add a GET /metadata/publishers endpoint if needed)

Write integration tests at tests/integration/test_publisher_authority.py.
Update CLAUDE.md with the publisher authority section.
Update docs/metadata_workbench_architecture.md with the new table.`,
      context: {
        projectRoot: args.projectRoot,
        dbPath: args.dbPath,
      },
      instructions: [
        'Query and verify all authority records',
        'Write integration tests',
        'Update documentation',
        'Run all tests',
      ],
      outputFormat: 'JSON',
    },
  },
}));

const runTestsShellTask = defineTask('run-tests', (args) => ({
  kind: 'shell',
  title: 'Run all publisher authority tests',
  command: `cd ${args.projectRoot} && poetry run python -m pytest tests/scripts/metadata/test_publisher_authority.py tests/integration/test_publisher_authority.py -v --tb=short 2>&1 | tail -30`,
  timeout: 60000,
}));
