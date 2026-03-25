/**
 * @process implement-historian-enhancements
 * @description Implement all 5 historian evaluation enhancements (E1-E5) with TDD,
 *   quality gates, and integration verification. Targets lifting score from 30.2% to 62.8%.
 *
 * E1: Agent Name Resolution Layer (CRITICAL, 3.5d)
 * E2: Auto-Aggregation for Analytical Questions (CRITICAL, 3.0d)
 * E3: Entity Cross-Reference and Set Comparison (HIGH, 4.5d, depends on E1)
 * E4: Contextual Narrative Depth Layer (HIGH, 4.0d, depends on E3)
 * E5: Intelligent Selection and Exhibit Curation (MEDIUM, 3.5d, depends on E2+E4)
 *
 * @inputs { projectRoot: string, planPath: string, dbPath: string }
 * @outputs { success: boolean, enhancementsCompleted: number, testsPassing: number }
 *
 * @skill python-dev-expert .claude/skills/python-dev-expert/SKILL.md
 * @skill git-expert .claude/skills/git-expert/SKILL.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    projectRoot = '/home/hagaybar/projects/rare-books-bot',
    planPath = 'reports/historian-enhancement-plan.md',
    dbPath = 'data/index/bibliographic.db'
  } = inputs;

  ctx.log('info', 'Starting historian enhancement implementation (E1-E5)');

  // ============================================================================
  // PHASE 1: E1 + E2 in parallel (both CRITICAL, no dependencies between them)
  // ============================================================================

  ctx.log('info', 'Phase 1: Implementing E1 (Agent Aliases) and E2 (Analytical Routing) in parallel');

  const [e1Result, e2Result] = await ctx.parallel.all([
    () => implementE1(inputs, ctx),
    () => implementE2(inputs, ctx),
  ]);

  // Phase 1 verification gate
  const phase1Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase1-e1-e2',
    description: 'Verify E1 and E2 implementations pass all tests',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40`,
  });

  // ============================================================================
  // PHASE 2: E3 (depends on E1)
  // ============================================================================

  ctx.log('info', 'Phase 2: Implementing E3 (Cross-Reference Engine)');

  const e3Result = await implementE3(inputs, ctx);

  const phase2Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase2-e3',
    description: 'Verify E3 implementation passes all tests including E1 integration',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40`,
  });

  // ============================================================================
  // PHASE 3: E4 (depends on E3)
  // ============================================================================

  ctx.log('info', 'Phase 3: Implementing E4 (Contextual Narrative Depth)');

  const e4Result = await implementE4(inputs, ctx);

  const phase3Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase3-e4',
    description: 'Verify E4 implementation passes all tests',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40`,
  });

  // ============================================================================
  // PHASE 4: E5 (depends on E2 + E4)
  // ============================================================================

  ctx.log('info', 'Phase 4: Implementing E5 (Curation Engine)');

  const e5Result = await implementE5(inputs, ctx);

  const phase4Verify = await ctx.task(verifyPhaseTask, {
    projectRoot,
    phase: 'phase4-e5',
    description: 'Verify E5 implementation passes all tests',
    command: `cd ${projectRoot} && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40`,
  });

  // ============================================================================
  // PHASE 5: FINAL REGRESSION + LINT
  // ============================================================================

  ctx.log('info', 'Phase 5: Final regression and lint verification');

  const finalVerify = await ctx.task(finalRegressionTask, {
    projectRoot,
    dbPath,
  });

  return {
    success: true,
    enhancementsCompleted: 5,
    e1: e1Result,
    e2: e2Result,
    e3: e3Result,
    e4: e4Result,
    e5: e5Result,
    finalVerification: finalVerify,
  };
}

// ============================================================================
// E1: Agent Name Resolution Layer
// ============================================================================

async function implementE1(inputs, ctx) {
  const { projectRoot, dbPath } = inputs;

  // E1-T1: Write tests first (TDD)
  const e1Tests = await ctx.task(e1WriteTestsTask, { projectRoot, dbPath });

  // E1-T2: Schema and M3 contract updates
  const e1Schema = await ctx.task(e1SchemaTask, { projectRoot });

  // E1-T3: Implement AgentAuthorityStore CRUD
  const e1Crud = await ctx.task(e1CrudTask, { projectRoot });

  // E1-T4: Write seeding and integration tests
  const e1IntTests = await ctx.task(e1IntegrationTestsTask, { projectRoot, dbPath });

  // E1-T5 and E1-T6 in parallel (both depend on E1-T3/T4 but not each other)
  const [e1Seed, e1QueryPath] = await ctx.parallel.all([
    () => ctx.task(e1SeedingTask, { projectRoot, dbPath }),
    () => ctx.task(e1QueryPathTask, { projectRoot }),
  ]);

  // E1-T7: Integration verification
  const e1Verify = await ctx.task(e1VerifyTask, {
    projectRoot, dbPath,
    description: 'Run E1 tests and verify agent alias resolution works',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/metadata/test_agent_authority.py tests/scripts/query/test_db_adapter_agent_alias.py tests/scripts/metadata/test_seed_agent_authorities.py -v --timeout=60 2>&1 | tail -30`,
  });

  return { e1Tests, e1Schema, e1Crud, e1IntTests, e1Seed, e1QueryPath, e1Verify };
}

// ============================================================================
// E2: Auto-Aggregation for Analytical Questions
// ============================================================================

async function implementE2(inputs, ctx) {
  const { projectRoot } = inputs;

  // E2-T1: Write analytical router tests (TDD)
  const e2Tests = await ctx.task(e2WriteTestsTask, { projectRoot });

  // E2-T2: Implement analytical router
  const e2Router = await ctx.task(e2RouterTask, { projectRoot });

  // E2-T3: Write curation engine tests
  const e2CurationTests = await ctx.task(e2CurationTestsTask, { projectRoot });

  // E2-T4: Implement curation engine and aggregation extensions
  const e2CurationImpl = await ctx.task(e2CurationImplTask, { projectRoot });

  // E2-T5: Wire into API and WebSocket
  const e2ApiWiring = await ctx.task(e2ApiWiringTask, { projectRoot });

  // E2-T6: Integration verification
  const e2Verify = await ctx.task(e2VerifyTask, {
    projectRoot,
    description: 'Run E2 tests and verify analytical routing works',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_analytical_router.py tests/scripts/chat/test_curation_engine.py tests/app/test_api_analytical.py -v --timeout=60 2>&1 | tail -30`,
  });

  return { e2Tests, e2Router, e2CurationTests, e2CurationImpl, e2ApiWiring, e2Verify };
}

// ============================================================================
// E3: Entity Cross-Reference and Set Comparison
// ============================================================================

async function implementE3(inputs, ctx) {
  const { projectRoot, dbPath } = inputs;

  // E3-T1: Write cross-reference tests
  const e3Tests = await ctx.task(e3WriteTestsTask, { projectRoot });

  // E3-T2: Implement cross-reference engine
  const e3Engine = await ctx.task(e3EngineTask, { projectRoot, dbPath });

  // E3-T3: Write comparison and narrative tests
  const e3CompTests = await ctx.task(e3ComparisonTestsTask, { projectRoot });

  // E3-T4: Integrate into narrative, comparison, formatter
  const e3Integration = await ctx.task(e3IntegrationTask, { projectRoot, dbPath });

  // E3-T5: Wire into API and exploration agent
  const e3ApiWiring = await ctx.task(e3ApiWiringTask, { projectRoot });

  // E3-T6: Integration verification
  const e3Verify = await ctx.task(e3VerifyTask, {
    projectRoot,
    description: 'Run E3 tests including cross-reference integration',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_cross_reference.py tests/scripts/chat/test_comparison_enhanced.py tests/scripts/chat/test_cross_reference_integration.py -v --timeout=60 2>&1 | tail -30`,
  });

  return { e3Tests, e3Engine, e3CompTests, e3Integration, e3ApiWiring, e3Verify };
}

// ============================================================================
// E4: Contextual Narrative Depth Layer
// ============================================================================

async function implementE4(inputs, ctx) {
  const { projectRoot } = inputs;

  // E4-T1: Write thematic context and scoring tests
  const e4Tests = await ctx.task(e4WriteTestsTask, { projectRoot });

  // E4-T2: Implement thematic context module with 8 entries
  const e4ThematicImpl = await ctx.task(e4ThematicImplTask, { projectRoot });

  // E4-T3: Write pedagogical formatting tests
  const e4PedTests = await ctx.task(e4PedagogicalTestsTask, { projectRoot });

  // E4-T4: Add pedagogical framing and wire into API
  const e4ApiWiring = await ctx.task(e4ApiWiringTask, { projectRoot });

  // E4-T5: Integration verification
  const e4Verify = await ctx.task(e4VerifyTask, {
    projectRoot,
    description: 'Run E4 tests including thematic integration',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_thematic_context.py tests/scripts/chat/test_formatter_pedagogical.py tests/integration/test_thematic_integration.py -v --timeout=60 2>&1 | tail -30`,
  });

  return { e4Tests, e4ThematicImpl, e4PedTests, e4ApiWiring, e4Verify };
}

// ============================================================================
// E5: Intelligent Selection and Exhibit Curation
// ============================================================================

async function implementE5(inputs, ctx) {
  const { projectRoot } = inputs;

  // E5-T1: Write curator tests
  const e5Tests = await ctx.task(e5WriteTestsTask, { projectRoot });

  // E5-T2: Implement curator module
  const e5CuratorImpl = await ctx.task(e5CuratorImplTask, { projectRoot });

  // E5-T3: Add exhibit formatting and schema updates
  const e5Formatting = await ctx.task(e5FormattingTask, { projectRoot });

  // E5-T4: Wire RECOMMENDATION handler in API
  const e5ApiWiring = await ctx.task(e5ApiWiringTask, { projectRoot });

  // E5-T5: Integration verification
  const e5Verify = await ctx.task(e5VerifyTask, {
    projectRoot,
    description: 'Run E5 tests and verify curation works',
    command: `cd ${projectRoot} && poetry run pytest tests/scripts/chat/test_curator.py -v --timeout=60 2>&1 | tail -30`,
  });

  return { e5Tests, e5CuratorImpl, e5Formatting, e5ApiWiring, e5Verify };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

// --- E1 Tasks ---

const e1WriteTestsTask = defineTask('e1-write-tests', (args) => ({
  kind: 'agent',
  title: 'E1: Write AgentAuthorityStore unit tests (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer specializing in SQLite and data authority systems',
      task: `Write unit tests for the AgentAuthorityStore module BEFORE the implementation exists.

The plan is in: reports/historian-enhancement-plan.md (section 2.1)

Create the test file: tests/scripts/metadata/test_agent_authority.py

Key tests to write (from the plan):
- test_create_authority_and_retrieve: Create authority with 2 aliases, verify all fields
- test_search_by_alias_case_insensitive: Search 'moshe ben maimon', match Maimonides
- test_search_by_alias_cross_script: Search Hebrew 'רמב"ם', match Maimonides
- test_search_by_alias_word_reorder: Search 'johann buxtorf', match authority
- test_unique_alias_constraint: Duplicate alias raises IntegrityError
- test_delete_cascades_aliases: FK cascade verified
- test_detect_script_hebrew_latin: Script detection (Hebrew vs Latin)
- test_list_all_with_type_filter: Filter by agent_type
- test_add_alias_to_existing_authority: Dynamic alias addition
- test_init_schema_creates_tables: Tables created with correct columns/indexes

Use in-memory SQLite for all tests. Tests should import from scripts.metadata.agent_authority (the module we'll implement next).

Follow the existing test patterns in the project (see tests/scripts/metadata/test_publisher_authority.py for reference).

Mirror the publisher_authorities/publisher_variants pattern in schema design. The schema for agent_authorities and agent_aliases is defined in the plan.

Also create the schema SQL additions needed by reading scripts/marc/m3_schema.sql first. DO NOT modify any files yet — just write the test file.

IMPORTANT: All tests should FAIL initially (import errors are expected). This is TDD — tests first.`,
      context: { projectRoot: args.projectRoot, dbPath: args.dbPath },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for exact schema and test specifications',
        'Read tests/scripts/metadata/test_publisher_authority.py for test patterns and conftest usage',
        'Read scripts/metadata/publisher_authority.py to understand the authority store pattern',
        'Create tests/scripts/metadata/test_agent_authority.py with 10+ unit tests',
        'Use in-memory SQLite (:memory:) for all tests',
        'Tests should import from scripts.metadata.agent_authority',
        'Include fixtures for Maimonides, Buxtorf, Mendelssohn, Karo test data',
        'Return summary of tests written'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e1SchemaTask = defineTask('e1-schema', (args) => ({
  kind: 'agent',
  title: 'E1: Schema and M3 contract updates',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in SQLite schema and data contracts',
      task: `Add agent_authorities and agent_aliases tables to the schema and M3 contract.

The exact SQL schema is in: reports/historian-enhancement-plan.md section 2.1 "Schema / Data-Model Changes"

Files to modify:
1. scripts/marc/m3_schema.sql — Add CREATE TABLE IF NOT EXISTS statements for agent_authorities and agent_aliases with all indexes
2. scripts/marc/m3_contract.py — Add AGENT_AUTHORITIES and AGENT_ALIASES to M3Tables, M3Columns, M3Aliases, and EXPECTED_SCHEMA

Follow the exact same pattern used for publisher_authorities/publisher_variants.

Read the plan for the exact schema, and read the existing m3_contract.py and m3_schema.sql to understand the patterns.

All DDL must use IF NOT EXISTS for safety. Do not modify any existing table definitions.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for exact schema SQL',
        'Read scripts/marc/m3_schema.sql to understand existing schema patterns',
        'Read scripts/marc/m3_contract.py to understand M3Tables, M3Columns, M3Aliases, EXPECTED_SCHEMA patterns',
        'Add agent_authorities CREATE TABLE to m3_schema.sql (with indexes)',
        'Add agent_aliases CREATE TABLE to m3_schema.sql (with indexes)',
        'Add entries to M3Tables, M3Columns, M3Aliases, EXPECTED_SCHEMA in m3_contract.py',
        'Do not modify any existing table definitions',
        'Return summary of changes made'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, tablesAdded: array, summary: string }'
    }
  }
}));

const e1CrudTask = defineTask('e1-crud', (args) => ({
  kind: 'agent',
  title: 'E1: Implement AgentAuthorityStore CRUD module',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in SQLite data access patterns',
      task: `Implement the AgentAuthorityStore module at scripts/metadata/agent_authority.py.

This mirrors the existing publisher_authority.py pattern. The plan is in reports/historian-enhancement-plan.md section 2.1.

The module must include:
- AgentAuthority and AgentAlias dataclasses (or Pydantic models matching the test expectations)
- AgentAuthorityStore class with:
  - __init__(self, db_path: Path) — opens connection, calls init_schema()
  - init_schema() — CREATE TABLE IF NOT EXISTS for both tables
  - create(authority) -> int — insert authority + aliases
  - search_by_alias(query: str) -> Optional[AgentAuthority] — case-insensitive alias lookup
  - resolve_agent_norm_to_authority_ids(agent_norm: str) -> List[int] — resolve via alias
  - list_all(agent_type: Optional[str] = None) -> List[AgentAuthority]
  - add_alias(authority_id: int, alias: AgentAlias) — add alias to existing authority
  - delete(authority_id: int) — CASCADE deletes aliases
  - detect_script(text: str) -> str — returns 'hebrew' or 'latin' based on Unicode ranges

Read scripts/metadata/publisher_authority.py for the exact code patterns to follow.
Read the tests at tests/scripts/metadata/test_agent_authority.py to ensure the implementation passes them.

Target: ~300 lines. Make sure all existing tests pass.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for specifications',
        'Read scripts/metadata/publisher_authority.py for the code pattern to follow',
        'Read tests/scripts/metadata/test_agent_authority.py to understand test expectations',
        'Create scripts/metadata/agent_authority.py with AgentAuthorityStore class',
        'Include init_schema, create, search_by_alias, resolve_agent_norm_to_authority_ids, list_all, add_alias, delete, detect_script',
        'Run the tests: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/metadata/test_agent_authority.py -v --timeout=60 2>&1 | tail -30',
        'Fix any failing tests until all pass',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { fileCreated: string, testsPassed: number, testsFailed: number, summary: string }'
    }
  }
}));

const e1IntegrationTestsTask = defineTask('e1-integration-tests', (args) => ({
  kind: 'agent',
  title: 'E1: Write seeding and alias-aware query integration tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer specializing in integration testing',
      task: `Write two test files for E1:

1. tests/scripts/metadata/test_seed_agent_authorities.py — Tests for the seeding script
2. tests/scripts/query/test_db_adapter_agent_alias.py — Integration tests for alias-aware queries

The plan is in reports/historian-enhancement-plan.md section 2.1.

For test_seed_agent_authorities.py:
- Test seeding from enrichment data (mocked enrichment rows)
- Test word-reorder alias generation ('Last, First' -> 'First Last')
- Test cross-script alias generation
- Test deduplication
- Test idempotency (run twice, same result)

For test_db_adapter_agent_alias.py (6 key integration tests):
- test_query_buxtorf_word_reorder: 'Johann Buxtorf' finds records with agent_norm 'buxtorf, johann'
- test_query_mendelssohn_cross_script: Latin query finds Hebrew records
- test_query_maimonides_all_forms: All forms unified via authority
- test_query_karo_latin_to_hebrew: Latin query finds Hebrew-only records
- test_query_aldus_manutius: Agent alias for printer
- test_query_fallback_no_alias_tables: Graceful degradation when tables don't exist

Use in-memory SQLite with mini-database fixtures. Tests should import from modules that will be created.

Read the existing test_db_adapter.py to understand the testing patterns for query execution.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for test specifications',
        'Read tests/scripts/query/test_db_adapter.py for query testing patterns',
        'Read scripts/query/db_adapter.py to understand the build_where_clause patterns',
        'Create tests/scripts/metadata/test_seed_agent_authorities.py',
        'Create tests/scripts/query/test_db_adapter_agent_alias.py with 6 integration tests',
        'Tests should use in-memory SQLite with fixtures',
        'Tests are expected to FAIL initially (implementations not yet created)',
        'Return summary of tests written'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFiles: array, summary: string }'
    }
  }
}));

const e1SeedingTask = defineTask('e1-seeding', (args) => ({
  kind: 'agent',
  title: 'E1: Implement seeding script and CLI command',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building data seeding pipelines for bibliographic databases',
      task: `Implement the agent authority seeding system:

1. Create scripts/metadata/seed_agent_authorities.py (~250 lines):
   - seed_from_enrichment(store, db_path): Group agents by authority_uri, gather agent_norm values as primary aliases, add enrichment labels and Hebrew labels as cross-script aliases
   - generate_word_reorder_aliases(store): For 'Last, First' patterns -> add 'First Last' alias
   - generate_cross_script_aliases(store, db_path): From authority_enrichment hebrew_label field
   - seed_all(store, db_path): Orchestrate all seeding steps. Idempotent (INSERT OR IGNORE).

2. Add CLI command to app/cli.py:
   - seed-agent-authorities with --db, --dry-run, --verbose flags
   - Init schema, run seed_all(), print statistics

The plan is in reports/historian-enhancement-plan.md section 2.1.

Read the existing publisher authority seeding pattern if one exists.
Read scripts/metadata/agent_authority.py for the AgentAuthorityStore API.
Read tests/scripts/metadata/test_seed_agent_authorities.py to ensure implementation passes tests.
Read the database schema to understand the agents and authority_enrichment tables.

After implementation, run the seeding tests:
cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/metadata/test_seed_agent_authorities.py -v --timeout=60

Fix any failures until all tests pass.`,
      context: { projectRoot: args.projectRoot, dbPath: args.dbPath },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for seeding specifications',
        'Read scripts/metadata/agent_authority.py for AgentAuthorityStore API',
        'Read tests/scripts/metadata/test_seed_agent_authorities.py for test expectations',
        'Read app/cli.py to understand CLI command patterns',
        'Examine the agents and authority_enrichment tables in the database schema',
        'Create scripts/metadata/seed_agent_authorities.py',
        'Add seed-agent-authorities CLI command to app/cli.py',
        'Run seeding tests and fix any failures',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { filesCreated: array, filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e1QueryPathTask = defineTask('e1-query-path', (args) => ({
  kind: 'agent',
  title: 'E1: Modify AGENT_NORM query path for alias resolution',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in SQL query generation and database adapters',
      task: `Modify the AGENT_NORM query path in scripts/query/db_adapter.py to support alias resolution.

The plan is in reports/historian-enhancement-plan.md section 2.1 "Retrieval / Orchestration Changes".

Changes needed:
1. In build_where_clause(), modify the AGENT_NORM branch (around lines 293-312) to add an OR EXISTS subquery that joins through agent_aliases -> agent_authorities -> agents via authority_uri
2. Add _agent_alias_tables_exist(conn) function that checks sqlite_master. Cache result per process.
3. If alias tables don't exist, fall back to the current behavior (backward compatibility)
4. The EXISTS subquery pattern: (existing direct match) OR EXISTS(SELECT 1 FROM agent_aliases al JOIN agent_authorities aa ON al.authority_id = aa.id WHERE al.alias_form_lower LIKE :param AND aa.authority_uri = a.authority_uri)

Read scripts/query/db_adapter.py to understand the current AGENT_NORM handler.
Read tests/scripts/query/test_db_adapter.py to understand existing test expectations.
Read tests/scripts/query/test_db_adapter_agent_alias.py for the new alias-aware test expectations.

After modification, run BOTH test suites to ensure backward compatibility:
cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/query/test_db_adapter.py tests/scripts/query/test_db_adapter_agent_alias.py -v --timeout=60

Fix any failures until all tests pass.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.1 for query path specifications',
        'Read scripts/query/db_adapter.py focusing on build_where_clause AGENT_NORM branch',
        'Read tests/scripts/query/test_db_adapter.py for existing test patterns',
        'Read tests/scripts/query/test_db_adapter_agent_alias.py for alias-aware test expectations',
        'Modify build_where_clause() AGENT_NORM handler to add alias resolution via EXISTS subquery',
        'Add _agent_alias_tables_exist(conn) with caching',
        'Ensure backward compatibility: fallback to direct match if alias tables absent',
        'Run both test suites and fix any failures',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, testsPassed: number, testsFailed: number, summary: string }'
    }
  }
}));

const e1VerifyTask = defineTask('e1-verify', (args) => ({
  kind: 'shell',
  title: 'E1: Run all E1 tests to verify completion',
  shell: {
    command: args.command,
    cwd: args.projectRoot,
  }
}));

// --- E2 Tasks ---

const e2WriteTestsTask = defineTask('e2-write-tests', (args) => ({
  kind: 'agent',
  title: 'E2: Write analytical router detection tests (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer specializing in NLP-based routing and classification',
      task: `Write unit tests for the analytical router BEFORE implementation.

The plan is in reports/historian-enhancement-plan.md section 2.2.

Create tests/scripts/chat/test_analytical_router.py with 25 unit tests:

Key tests:
- test_detect_q14_chronological_distribution: Returns TEMPORAL_DISTRIBUTION, field='date_decade'
- test_detect_q15_printing_centers: Returns GEOGRAPHIC_DISTRIBUTION, field='place', implied language filter
- test_detect_q20_curated_exhibit: Returns CURATION
- test_not_analytical_specific_search: 'books printed in Paris' returns NOT_ANALYTICAL
- test_not_analytical_comparison: 'compare Venice and Amsterdam' returns NOT_ANALYTICAL
- test_implied_filter_hebrew: Extracts language=heb from 'Hebrew'
- test_borderline_about_chronological_history: anti-signal detection
- test_case_insensitive: 'CHRONOLOGICAL DISTRIBUTION' still detected
- Plus 17 more covering edge cases, false positives, and negative patterns

Tests should import from scripts.chat.analytical_router.

Also reference the existing chat module patterns in scripts/chat/ and tests/scripts/chat/.

Tests are expected to FAIL initially (module not yet created).`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.2 for test specifications',
        'Read scripts/chat/models.py to understand existing model patterns',
        'Read scripts/chat/aggregation.py to understand aggregation patterns',
        'Create tests/scripts/chat/test_analytical_router.py with 25 unit tests',
        'Tests should cover: analytical detection, anti-signals, implied filters, edge cases',
        'Tests import from scripts.chat.analytical_router',
        'All tests should FAIL initially',
        'Return summary of tests written'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e2RouterTask = defineTask('e2-router', (args) => ({
  kind: 'agent',
  title: 'E2: Implement analytical router',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in NLP routing and query classification',
      task: `Implement the analytical router at scripts/chat/analytical_router.py (~150-200 lines).

The plan is in reports/historian-enhancement-plan.md section 2.2.

The module must include:
- AnalyticalIntent enum: TEMPORAL_DISTRIBUTION, GEOGRAPHIC_DISTRIBUTION, PUBLISHER_DISTRIBUTION, LANGUAGE_DISTRIBUTION, SUBJECT_DISTRIBUTION, GENERAL_DISTRIBUTION, CURATION, NOT_ANALYTICAL
- AnalyticalQueryResult Pydantic model: is_analytical, intent, aggregation_field, implied_filters, confidence
- detect_analytical_query(query_text: str) -> AnalyticalQueryResult
  - Two-layer: (1) signal detection with multi-word phrases by category, (2) anti-signals
  - Implied filter extraction (Hebrew -> language=heb, 16th century -> date range, etc.)
- classify_analytical_intent(query_text: str) -> AnalyticalIntent (helper)

The detection must be DETERMINISTIC (no LLM calls). Works without OPENAI_API_KEY.

Read tests/scripts/chat/test_analytical_router.py to ensure all tests pass.
After implementation, run:
cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_analytical_router.py -v --timeout=60

Fix any failures.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.2 for specifications',
        'Read tests/scripts/chat/test_analytical_router.py for test expectations',
        'Read scripts/chat/models.py for existing model patterns',
        'Create scripts/chat/analytical_router.py',
        'Implement AnalyticalIntent enum and AnalyticalQueryResult model',
        'Implement detect_analytical_query() with signal/anti-signal detection',
        'Implement implied filter extraction',
        'Run tests and fix failures',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { fileCreated: string, testsPassed: number, testsFailed: number, summary: string }'
    }
  }
}));

const e2CurationTestsTask = defineTask('e2-curation-tests', (args) => ({
  kind: 'agent',
  title: 'E2: Write curation engine tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer',
      task: `Write unit tests for the E2 curation engine (NOT the E5 curator).

Create tests/scripts/chat/test_curation_engine.py with 8-10 tests:
- Test curation scoring heuristic (temporal, enrichment, diversity, subject)
- Test diverse selection from scored candidates
- Test formatting of curation responses
- Test edge cases: empty input, single item, all identical scores

The plan is in reports/historian-enhancement-plan.md section 2.2.
Tests import from scripts.chat.curation_engine.
Tests should FAIL initially.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.2 for specifications',
        'Create tests/scripts/chat/test_curation_engine.py with 8-10 tests',
        'Return summary of tests written'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e2CurationImplTask = defineTask('e2-curation-impl', (args) => ({
  kind: 'agent',
  title: 'E2: Implement curation engine, aggregation extensions, and narrative analytical path',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in data aggregation and curation systems',
      task: `Implement three components for E2:

1. scripts/chat/curation_engine.py (~200-250 lines):
   - score_for_curation(candidate, db_path) with heuristic: temporal_score (0.3), enrichment_score (0.3), diversity_bonus (0.2), subject_richness (0.2)
   - select_curated_items(candidates, n=10, db_path) -> List of scored+selected items
   - format_curation_response(items) -> formatted response text
   - CurationScorer class orchestrating the scoring

2. Modify scripts/chat/aggregation.py:
   - Add execute_aggregation_full_collection(db_path, field, filters=None) — SQL GROUP BY without WHERE record_id IN clause
   - Add get_all_record_ids(db_path, filters=None) — utility for filtered-then-aggregate

3. Modify scripts/chat/narrative_agent.py:
   - Add generate_analytical_narrative(aggregation_data, query_text) for statistical summaries
   - Add optional analytical_mode parameter to existing functions

4. Add CURATION to ExplorationIntent enum in scripts/chat/models.py

Read the plan section 2.2 and the tests at tests/scripts/chat/test_curation_engine.py.
After implementation, run tests and fix failures.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.2',
        'Read tests/scripts/chat/test_curation_engine.py for test expectations',
        'Read scripts/chat/aggregation.py to understand existing aggregation patterns',
        'Read scripts/chat/narrative_agent.py to understand narrative generation',
        'Read scripts/chat/models.py for ExplorationIntent enum',
        'Create scripts/chat/curation_engine.py',
        'Modify aggregation.py with full-collection aggregation',
        'Modify narrative_agent.py with analytical narrative',
        'Add CURATION to ExplorationIntent',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_curation_engine.py tests/scripts/chat/test_analytical_router.py -v --timeout=60',
        'Fix any failures',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { filesCreated: array, filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e2ApiWiringTask = defineTask('e2-api-wiring', (args) => ({
  kind: 'agent',
  title: 'E2: Wire analytical routing into API and WebSocket',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in FastAPI and WebSocket integration',
      task: `Wire analytical routing into the API layer for E2.

The plan is in reports/historian-enhancement-plan.md section 2.2.

Changes to app/api/main.py:
1. Add handle_analytical_query() function — routes analytical results through aggregation or curation
2. Wire detect_analytical_query() into handle_query_definition_phase() — insert BEFORE interpret_query(), AFTER is_overview_query()
3. Wire into websocket_chat() — add 'Analyzing collection...' progress message
4. Create ChatResponse with phase=CORPUS_EXPLORATION, visualization_hint, structured data in metadata

Also modify scripts/chat/exploration_agent.py:
- Add CURATION examples to the system prompt
- Update ExplorationRequestLLM if needed

After implementation, create integration tests at tests/app/test_api_analytical.py (8 tests):
- E2E test for Q14 (chronological distribution)
- E2E test for Q15 (printing centers)
- E2E test for Q20 (curated exhibit)
- WebSocket routing test
- Follow-up after analytical response test
- Standard retrieval not misrouted test
- HTTP and WebSocket parity tests

Run all E2 tests after implementation.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.2',
        'Read app/api/main.py to understand current routing logic',
        'Read scripts/chat/exploration_agent.py to understand system prompt',
        'Modify app/api/main.py to add analytical routing',
        'Modify scripts/chat/exploration_agent.py for CURATION examples',
        'Create tests/app/test_api_analytical.py with 8 integration tests',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/app/test_api_analytical.py tests/scripts/chat/test_analytical_router.py tests/scripts/chat/test_curation_engine.py -v --timeout=60',
        'Fix any failures',
        'Return summary with test results'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, filesCreated: array, testsPassed: number, summary: string }'
    }
  }
}));

const e2VerifyTask = defineTask('e2-verify', (args) => ({
  kind: 'shell',
  title: 'E2: Run all E2 tests to verify completion',
  shell: {
    command: args.command,
    cwd: args.projectRoot,
  }
}));

// --- E3 Tasks ---

const e3WriteTestsTask = defineTask('e3-write-tests', (args) => ({
  kind: 'agent',
  title: 'E3: Write cross-reference engine tests (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer specializing in graph-based entity resolution',
      task: `Write unit tests for the cross-reference engine BEFORE implementation.

The plan is in reports/historian-enhancement-plan.md section 2.3.

Create tests/scripts/chat/test_cross_reference.py with 13 unit tests:
- test_build_agent_graph_from_enrichment: Graph has correct node count
- test_find_teacher_student_connection: Discovers teacher_of relationship
- test_find_co_publication: Shared records create co_publication connection
- test_find_same_place_period: Agents in same city + overlapping dates
- test_find_network_neighbors: 1-hop neighbors discovered
- test_no_connections_found: Empty list for unrelated agents
- test_self_loop_excluded: Agent not connected to self
- test_max_results_respected: Cap on returned connections
- test_connection_confidence_values: teacher_of=0.90, co_publication=0.85, etc.
- test_empty_enrichment: Graceful empty graph
- test_circular_teacher_student: No infinite loops
- test_visited_tracking: No duplicate connections
- test_agent_node_fields: All fields populated correctly

Use in-memory SQLite with fixture data mimicking authority_enrichment.person_info.
Tests import from scripts.chat.cross_reference.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.3',
        'Read scripts/chat/models.py for existing model patterns',
        'Create tests/scripts/chat/test_cross_reference.py with 13 tests',
        'Return summary of tests written'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e3EngineTask = defineTask('e3-engine', (args) => ({
  kind: 'agent',
  title: 'E3: Implement cross-reference engine',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building entity relationship graphs for bibliographic data',
      task: `Implement the cross-reference engine at scripts/chat/cross_reference.py (~280 lines).

The plan is in reports/historian-enhancement-plan.md section 2.3.

Also add new Pydantic models to scripts/chat/models.py:
- Connection, AgentNode, ComparisonFacets, ComparisonResult
- Add CROSS_REFERENCE to ExplorationIntent enum

The cross_reference.py module:
- build_agent_graph(db_path) — Load ~2,665 enriched records from authority_enrichment.person_info. Build in-memory graph of agent relationships.
- find_connections(record_ids, db_path) — Check pairwise relationships: teacher/student, co-publication, same_place_period
- find_network_neighbors(agent_norm, db_path, max_hops=1) — Discover agents 1 hop away
- Pure functions, no LLM. Graph cached as lazy singleton.

Performance guard: skip if >50 agents in result set.
Cap at 30 agents for pairwise comparison.

Read the tests and make them pass.`,
      context: { projectRoot: args.projectRoot, dbPath: args.dbPath },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.3',
        'Read tests/scripts/chat/test_cross_reference.py for test expectations',
        'Read scripts/chat/models.py to add new models',
        'Create scripts/chat/cross_reference.py',
        'Add Connection, AgentNode, ComparisonFacets, ComparisonResult to models.py',
        'Add CROSS_REFERENCE to ExplorationIntent',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_cross_reference.py -v --timeout=60',
        'Fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesCreated: array, filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e3ComparisonTestsTask = defineTask('e3-comparison-tests', (args) => ({
  kind: 'agent',
  title: 'E3: Write enhanced comparison and narrative tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer',
      task: `Write test files for E3 enhanced comparison and narrative integration:

1. tests/scripts/chat/test_comparison_enhanced.py (8 tests):
   - test_comparison_facets_populated: All facet types have data
   - test_shared_agents_discovered: Agents appearing in both compared sets
   - test_subject_overlap: Common subjects identified
   - test_backward_compatible: Old execute_comparison() still returns Dict[str, int]
   - test_empty_comparison: Graceful with empty values
   - test_single_value: Comparison with one value works
   - test_date_ranges_correct: Min/max dates per value
   - test_language_distribution: Language counts per compared value

2. tests/scripts/chat/test_narrative_agent_e3.py (6 tests):
   - test_narrative_with_connections: Connections section appended
   - test_narrative_no_connections: No section when empty
   - test_connections_section_format: '**Connections found:**' header present
   - test_performance_guard_large_set: >50 agents skips cross-ref
   - test_non_blocking: Exception in cross-ref doesn't break narrative
   - test_connection_evidence_format: Evidence strings are readable

The plan is in reports/historian-enhancement-plan.md section 2.3.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.3',
        'Create tests/scripts/chat/test_comparison_enhanced.py',
        'Create tests/scripts/chat/test_narrative_agent_e3.py',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFiles: array, summary: string }'
    }
  }
}));

const e3IntegrationTask = defineTask('e3-integration', (args) => ({
  kind: 'agent',
  title: 'E3: Integrate cross-reference into narrative, comparison, formatter',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer integrating cross-reference capabilities into existing chat pipeline',
      task: `Integrate the cross-reference engine into existing modules:

1. scripts/chat/narrative_agent.py — After bios section, call find_connections(). Append '**Connections found:**' section. Non-blocking (try/except). Performance guard: skip if >50 agents.

2. scripts/chat/aggregation.py — Replace execute_comparison() with execute_comparison_enhanced() returning ComparisonResult with multi-faceted data: counts, date_ranges, language_distribution, top_agents, shared_agents, subject_overlap. Keep old function as backward-compatible wrapper.

3. scripts/chat/formatter.py — Enhance follow-up suggestions: for multi-place results suggest 'Compare [A] vs [B]'. For multi-agent results suggest 'Show connections'. For single prominent agent: 'Show [agent] network'.

4. Also create tests/scripts/chat/test_formatter_e3.py (6 tests) for the new follow-up suggestion logic.

5. Create tests/scripts/chat/test_cross_reference_integration.py (6 integration tests against real DB patterns):
   - test_buxtorf_network
   - test_venice_printer_connections
   - test_teacher_student_chain
   - test_venice_amsterdam_comparison
   - test_graceful_no_enrichment
   - test_performance_under_500ms

Read existing code in each module before modifying. Run all tests after changes.`,
      context: { projectRoot: args.projectRoot, dbPath: args.dbPath },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.3',
        'Read scripts/chat/narrative_agent.py to understand bio generation flow',
        'Read scripts/chat/aggregation.py for comparison patterns',
        'Read scripts/chat/formatter.py for follow-up suggestion patterns',
        'Read tests/scripts/chat/test_comparison_enhanced.py and test_narrative_agent_e3.py',
        'Modify narrative_agent.py, aggregation.py, formatter.py',
        'Create tests/scripts/chat/test_formatter_e3.py',
        'Create tests/scripts/chat/test_cross_reference_integration.py',
        'Run all E3 tests and fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, filesCreated: array, testsPassed: number, summary: string }'
    }
  }
}));

const e3ApiWiringTask = defineTask('e3-api-wiring', (args) => ({
  kind: 'agent',
  title: 'E3: Wire cross-reference into API and exploration agent',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in FastAPI integration',
      task: `Wire cross-reference capabilities into the API layer:

1. app/api/main.py:
   - Phase 1: Include connection data in response_metadata when connections exist
   - Phase 2: Add CROSS_REFERENCE handler for exploration requests
   - Enhanced COMPARISON handler using execute_comparison_enhanced()

2. scripts/chat/exploration_agent.py:
   - Add cross_reference_entity, cross_reference_scope fields to ExplorationRequestLLM
   - Update system prompt with CROSS_REFERENCE examples
   - Add examples distinguishing COMPARISON from CROSS_REFERENCE

Read the plan section 2.3 and existing app/api/main.py exploration handling.
Run all tests after changes.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.3',
        'Read app/api/main.py focusing on exploration phase handling',
        'Read scripts/chat/exploration_agent.py for current schema and prompt',
        'Modify app/api/main.py for cross-reference support',
        'Modify exploration_agent.py for CROSS_REFERENCE intent',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40',
        'Fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e3VerifyTask = defineTask('e3-verify', (args) => ({
  kind: 'shell',
  title: 'E3: Run all E3 tests to verify completion',
  shell: {
    command: args.command,
    cwd: args.projectRoot,
  }
}));

// --- E4 Tasks ---

const e4WriteTestsTask = defineTask('e4-write-tests', (args) => ({
  kind: 'agent',
  title: 'E4: Write thematic context and scoring tests (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer specializing in scholarly content systems',
      task: `Write unit tests for the thematic context module BEFORE implementation.

The plan is in reports/historian-enhancement-plan.md section 2.4.

Create tests/scripts/chat/test_thematic_context.py with 13 tests:
- test_venetian_theme_matches_venice_16c_hebrew
- test_amsterdam_theme_matches_amsterdam_1620_1650
- test_talmud_theme_matches_subject_talmud
- test_napoleon_theme_matches_1795_1815
- test_no_theme_matches_unrelated_filters (place=london, year=1900-1950)
- test_highest_scoring_theme_wins
- test_thematic_block_has_citations: Every entry has >=1 Reference
- test_significance_score_pre1500_higher
- test_notable_items_returns_top3
- test_notable_items_respects_max_result_set (>150 candidates -> empty)
- test_significance_factors_have_reasons
- test_theme_id_unique_across_registry
- test_all_themes_have_teaching_notes

Tests import from scripts.chat.thematic_context.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.4',
        'Create tests/scripts/chat/test_thematic_context.py with 13 tests',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e4ThematicImplTask = defineTask('e4-thematic-impl', (args) => ({
  kind: 'agent',
  title: 'E4: Implement thematic context module with 8 scholarly entries',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer with deep knowledge of early modern Jewish printing history and Hebrew bibliography',
      task: `Implement the thematic context module at scripts/chat/thematic_context.py (~400-500 lines).

The plan is in reports/historian-enhancement-plan.md section 2.4.

The module must include:

1. Pydantic models: ThematicBlock, Reference, MatchRule, ThematicEntry, SignificanceResult, SignificanceFactor, NotableItem

2. THEMATIC_REGISTRY dict with 8 pre-authored scholarly paragraphs:
   - venetian_hebrew_printing: Council of Trent, censorship, Bragadin family. Citations: Heller 2004, Amram 1909.
   - amsterdam_dutch_jerusalem: Sephardic exile, Menasseh ben Israel, freedom of press. Citations: Fuks 1987, Offenberg 1990.
   - christian_hebraism: Buxtorf dynasty, Basel printing. Citations: Burnett 1996, Grafton 1983.
   - haskalah: Enlightenment, Berlin-Dessau, Mendelssohn Biur. Citations: Feiner 2004, Sorkin 1996.
   - incunabula_spread: Pre-1500 printing, Soncino family, Gutenberg. Citations: Offenberg 1990, Steinschneider 1893.
   - talmud_printing: Bomberg 1520-23, 1553 burning, Vilna Shas. Citations: Heller 1999, Habermann 1978.
   - napoleonic_emancipation: Sanhedrin, ghetto dissolution, transitional works. Citations: Feiner 2004, Schechter 2003.
   - ottoman_hebrew_printing: Constantinople, Sephardic diaspora, early presses. Citations: Tamari 1999, Yaari 1967.

   Each paragraph must be pre-authored string literals with citations — NOT LLM-generated.

3. get_thematic_context(filters, candidates, db_path) -> Optional[ThematicBlock]
   - Match rules against filter dimensions
   - Score by matching dimensions
   - Return highest-scoring theme or None

4. significance_score(candidate, db_path) -> SignificanceResult
   - Factors: date_rarity (pre-1500: +5), enrichment_richness (max +3.5), place_rarity, first_edition, subject_richness
   - Pure function, no LLM, no API calls

5. get_notable_items(candidates, db_path, top_n=3) -> List[NotableItem]
   - Score all, sort descending, return top-N with highlight_reasons
   - Respect _MAX_RESULT_SET=100

Run tests and fix failures:
cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_thematic_context.py -v --timeout=60`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.4 for full specifications',
        'Read tests/scripts/chat/test_thematic_context.py for test expectations',
        'Create scripts/chat/thematic_context.py with all models, registry, and functions',
        'Ensure all 8 thematic entries have scholarly citations',
        'Ensure significance_score is importable by E5',
        'Run tests and fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { fileCreated: string, testsPassed: number, testsFailed: number, summary: string }'
    }
  }
}));

const e4PedagogicalTestsTask = defineTask('e4-pedagogical-tests', (args) => ({
  kind: 'agent',
  title: 'E4: Write pedagogical formatting tests',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer',
      task: `Write tests for pedagogical formatting functions.

Create tests/scripts/chat/test_formatter_pedagogical.py with 3 tests:
- test_format_teaching_note_output: Teaching note formatted with header and markdown
- test_format_citations_output: Citations formatted as academic references
- test_followups_include_thematic_suggestions: Theme-specific follow-up suggestions included

Tests import from scripts.chat.formatter.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.4',
        'Read scripts/chat/formatter.py for existing patterns',
        'Create tests/scripts/chat/test_formatter_pedagogical.py',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e4ApiWiringTask = defineTask('e4-api-wiring', (args) => ({
  kind: 'agent',
  title: 'E4: Add pedagogical framing and wire thematic context into API',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer integrating scholarly context into FastAPI endpoints',
      task: `Wire thematic context into the API and formatter:

1. scripts/chat/formatter.py — Add:
   - format_teaching_note(note: str) -> str
   - Format citations as academic references
   - Add theme-specific follow-up suggestions to generate_followups()
   (~60 lines added)

2. scripts/chat/models.py — Add:
   - thematic_context: Optional[str] = None field on ChatResponse
   (~2 lines)

3. app/api/main.py — Integrate into handle_query_definition_phase():
   - After agent narrative block, call get_thematic_context()
   - If theme found: append '**Historical Context**' section with horizontal rule
   - Add notable items if applicable
   - Merge theme-specific followups
   - Non-blocking (try/except)
   (~30 lines added)

4. Create tests/integration/test_thematic_integration.py (2 integration tests):
   - test_venice_query_includes_historical_context
   - test_generic_query_no_context

Run all E4 tests and fix failures.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.4',
        'Read tests/scripts/chat/test_formatter_pedagogical.py for test expectations',
        'Read scripts/chat/formatter.py for existing patterns',
        'Read app/api/main.py for handle_query_definition_phase location',
        'Modify formatter.py, models.py, main.py',
        'Create tests/integration/test_thematic_integration.py',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_thematic_context.py tests/scripts/chat/test_formatter_pedagogical.py tests/integration/test_thematic_integration.py -v --timeout=60',
        'Fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, filesCreated: array, testsPassed: number, summary: string }'
    }
  }
}));

const e4VerifyTask = defineTask('e4-verify', (args) => ({
  kind: 'shell',
  title: 'E4: Run all E4 tests to verify completion',
  shell: {
    command: args.command,
    cwd: args.projectRoot,
  }
}));

// --- E5 Tasks ---

const e5WriteTestsTask = defineTask('e5-write-tests', (args) => ({
  kind: 'agent',
  title: 'E5: Write curator scoring and diversity tests (TDD)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python TDD developer',
      task: `Write unit tests for the E5 curator module BEFORE implementation.

The plan is in reports/historian-enhancement-plan.md section 2.5.

Create tests/scripts/chat/test_curator.py with 25 tests in these groups:
- ScoredCandidate validation (3): valid, score bounds, empty reasons
- fetch_record_metadata (4): all fields, missing record, NULL fields, batching
- score_candidates (4): sorted descending, reasons populated, empty input, fallback scoring
- select_diverse (7): basic, improves coverage, n exceeds total, empty, single item, dimension coverage, identical dimensions
- exhibit formatting (4): item complete, missing date, response header, coverage summary
- exploration agent schema (2): recommendation fields, defaults
- integration (3): handler returns exhibit, metadata populated, followups non-empty (these may mock the API)

Tests import from scripts.chat.curator.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.5',
        'Create tests/scripts/chat/test_curator.py with 25 tests',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { testsWritten: number, testFile: string, summary: string }'
    }
  }
}));

const e5CuratorImplTask = defineTask('e5-curator-impl', (args) => ({
  kind: 'agent',
  title: 'E5: Implement curator module',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer building intelligent curation for bibliographic collections',
      task: `Implement the curator module at scripts/chat/curator.py (~230 lines).

The plan is in reports/historian-enhancement-plan.md section 2.5.

The module must include:
1. ScoredCandidate model: record_id, significance_score (0.0-1.0), reasons, metadata
2. CurationRequest model: n (default 10, clamped [1,50]), criteria, dimensions
3. CurationResult model: selected, total_scored, selection_method, dimension_coverage

4. fetch_record_metadata(record_ids, db_path) -> Dict[str, dict]:
   - Single query joining records, imprints, languages, agents, subjects, authority_enrichment
   - Batches if >500 IDs

5. score_candidates(candidates, db_path) -> List[ScoredCandidate]:
   - Calls fetch_record_metadata then significance_score (from thematic_context.py, with fallback)
   - Returns sorted list (descending score) with human-readable reasons

6. select_diverse(scored, n=10, dimensions=['date_decade','place_norm','language','agent']) -> CurationResult:
   - Greedy diversity-aware selection
   - Diversity bonus: 0.15 * (new_dimension_values / total_dimensions)
   - Edge cases: n >= total, empty input, identical dimensions

Read tests/scripts/chat/test_curator.py and make all tests pass.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.5',
        'Read tests/scripts/chat/test_curator.py for test expectations',
        'Read scripts/chat/thematic_context.py for significance_score import',
        'Create scripts/chat/curator.py',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_curator.py -v --timeout=60',
        'Fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { fileCreated: string, testsPassed: number, testsFailed: number, summary: string }'
    }
  }
}));

const e5FormattingTask = defineTask('e5-formatting', (args) => ({
  kind: 'agent',
  title: 'E5: Add exhibit formatting and exploration agent schema updates',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer',
      task: `Add exhibit formatting and update exploration agent schema for E5:

1. scripts/chat/formatter.py:
   - format_exhibit_item(item, n) -> str: 'Item {n} ({date}, {place}): {title} -- {significance_note}'
   - format_exhibit_response(result) -> str: header, dimension coverage summary, items, footer
   (~45 lines added)

2. scripts/chat/exploration_agent.py:
   - Add recommendation_count: Optional[int] and recommendation_criteria: Optional[str] to ExplorationRequestLLM
   - Update system prompt with 5 RECOMMENDATION examples
   (~35 lines added)

Read existing patterns in both files. Run tests after changes.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.5',
        'Read scripts/chat/formatter.py for existing patterns',
        'Read scripts/chat/exploration_agent.py for ExplorationRequestLLM',
        'Modify both files',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/scripts/chat/test_curator.py -v --timeout=60',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e5ApiWiringTask = defineTask('e5-api-wiring', (args) => ({
  kind: 'agent',
  title: 'E5: Wire RECOMMENDATION handler in API',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python developer specializing in FastAPI endpoint implementation',
      task: `Replace the static RECOMMENDATION stub in app/api/main.py with a working handler for E5.

The plan is in reports/historian-enhancement-plan.md section 2.5.

Replace the static stub (around lines 1025-1038) with:
1. Extract count/criteria from ExplorationRequestLLM
2. Call score_candidates(candidates, db_path) from scripts.chat.curator
3. Call select_diverse(scored, n=count)
4. Call format_exhibit_response(result)
5. Build ChatResponse with metadata['curation'] containing total_scored, selected_count, dimension_coverage
6. Add context-aware follow-up suggestions

Also handle edge cases: empty candidates, n > total, etc.

Run all tests after changes to verify no regressions.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        'Read reports/historian-enhancement-plan.md section 2.5',
        'Read app/api/main.py to find the RECOMMENDATION stub',
        'Read scripts/chat/curator.py for the API',
        'Replace the stub with working handler',
        'Run: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/ -v --timeout=120 -x 2>&1 | tail -40',
        'Fix failures',
        'Return summary'
      ],
      outputFormat: 'JSON with fields: { filesModified: array, testsPassed: number, summary: string }'
    }
  }
}));

const e5VerifyTask = defineTask('e5-verify', (args) => ({
  kind: 'shell',
  title: 'E5: Run all E5 tests to verify completion',
  shell: {
    command: args.command,
    cwd: args.projectRoot,
  }
}));

// --- Shared Tasks ---

const verifyPhaseTask = defineTask('verify-phase', (args) => ({
  kind: 'agent',
  title: `Verify phase: ${args.phase}`,
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'QA engineer verifying test suite integrity',
      task: `Run the verification command and analyze results for phase: ${args.phase}

Description: ${args.description}

Run: ${args.command}

Analyze the output:
1. Count passing and failing tests
2. If there are failures, identify the root causes
3. If failures exist, attempt to fix them by reading the failing test and the implementation
4. Re-run until all tests pass or report what cannot be fixed

Return the final test results.`,
      context: { projectRoot: args.projectRoot },
      instructions: [
        `Run the command: ${args.command}`,
        'Analyze test output for pass/fail counts',
        'If failures exist, investigate and fix',
        'Re-run tests after fixes',
        'Return final results'
      ],
      outputFormat: 'JSON with fields: { phase: string, testsPassed: number, testsFailed: number, fixed: array, summary: string }'
    }
  }
}));

const finalRegressionTask = defineTask('final-regression', (args) => ({
  kind: 'agent',
  title: 'FINAL: Full regression, lint, and cross-enhancement verification',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Senior QA engineer performing final release verification',
      task: `Run comprehensive final verification for all 5 enhancements:

1. Full test suite: cd /home/hagaybar/projects/rare-books-bot && poetry run pytest tests/ -v --timeout=120 2>&1 | tail -60
2. Lint check: cd /home/hagaybar/projects/rare-books-bot && poetry run ruff check scripts/ app/ --select E,W,F 2>&1 | tail -20
3. Verify new modules exist and are importable:
   - scripts/metadata/agent_authority.py
   - scripts/metadata/seed_agent_authorities.py
   - scripts/chat/analytical_router.py
   - scripts/chat/curation_engine.py
   - scripts/chat/cross_reference.py
   - scripts/chat/thematic_context.py
   - scripts/chat/curator.py

4. Count total new test files and tests added

Fix any remaining issues. Return comprehensive report.`,
      context: { projectRoot: args.projectRoot, dbPath: args.dbPath },
      instructions: [
        'Run full test suite',
        'Run ruff lint check',
        'Verify all new modules are importable',
        'Count new tests',
        'Fix any remaining issues',
        'Run ruff format if needed: cd /home/hagaybar/projects/rare-books-bot && poetry run ruff format scripts/ app/',
        'Return comprehensive final report'
      ],
      outputFormat: 'JSON with fields: { allTestsPassed: boolean, totalTests: number, lintClean: boolean, newModules: array, summary: string }'
    }
  }
}));
