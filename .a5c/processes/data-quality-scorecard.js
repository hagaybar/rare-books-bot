/**
 * @process data-quality-scorecard
 * @description Comprehensive data quality scorecard & remediation for bibliographic.db — Tier 1 zero-error fixes + Tier 2 gap analysis
 * @inputs { specPath: string, dbPath: string, archiveDir: string, qaDir: string }
 * @outputs { success: boolean, qualityReport: object, fixesApplied: number, artifacts: array }
 *
 * @skill data-quality-profiler specializations/data-engineering-analytics/skills/data-quality-profiler/SKILL.md
 * @agent data-quality-engineer specializations/data-engineering-analytics/agents/data-quality-engineer/AGENT.md
 */

import { defineTask } from '@a5c-ai/babysitter-sdk';

export async function process(inputs, ctx) {
  const {
    specPath = 'docs/superpowers/specs/2026-04-02-data-quality-scorecard-design.md',
    dbPath = 'data/index/bibliographic.db',
    archiveDir = 'data/archive/data-quality-2026-04-02',
    qaDir = 'data/qa',
    fixScriptsDir = 'scripts/qa/fixes',
    checksScript = 'scripts/qa/data_quality_checks.py'
  } = inputs;

  const startTime = ctx.now();
  const artifacts = [];

  ctx.log('info', 'Starting Data Quality Scorecard & Remediation process');

  // ============================================================================
  // PHASE 1: BUILD AUTOMATED CONSISTENCY CHECKS SCRIPT
  // ============================================================================

  ctx.log('info', 'Phase 1: Build automated consistency checks infrastructure');

  const checksInfra = await ctx.task(buildChecksScriptTask, {
    specPath,
    dbPath,
    checksScript,
    qaDir
  });

  artifacts.push({ path: checksScript, type: 'python_script' });

  // ============================================================================
  // PHASE 2: RUN BASELINE CHECKS & GENERATE INITIAL REPORT
  // ============================================================================

  ctx.log('info', 'Phase 2: Run baseline consistency checks');

  const baselineReport = await ctx.task(runBaselineChecksTask, {
    checksScript,
    dbPath,
    qaDir
  });

  artifacts.push({ path: `${qaDir}/data-quality-report.json`, type: 'report' });

  // ============================================================================
  // PHASE 3: BUILD FIX SCRIPTS (Quick Wins)
  // ============================================================================

  ctx.log('info', 'Phase 3: Build quick-win fix scripts');

  const quickWinScripts = await ctx.task(buildQuickWinFixesTask, {
    specPath,
    dbPath,
    fixScriptsDir,
    archiveDir,
    qaDir
  });

  // ============================================================================
  // PHASE 4: APPROVAL GATE — Review quick-win fixes before applying
  // ============================================================================

  await ctx.breakpoint({
    question: 'Quick-win fix scripts are built. Review the scripts in scripts/qa/fixes/ and the baseline report in data/qa/data-quality-report.json. Approve to apply fixes to the database? (Original data will be archived first.)',
    title: 'Approve Quick-Win Data Fixes',
    context: {
      fixes: [
        'Fix 1: Strip trailing periods from role_raw (~74 records)',
        'Fix 2: Add Hebrew role term mappings (~49 records)',
        'Fix 3: Add missing MARC relator terms (~116 records)',
        'Fix 4: Normalize subject scheme NLI→nli (169 records)',
        'Fix 5: Fix 2 calendar-confusion dates',
        'Fix 6: Fix ~12 place-country_code mismatches',
        'Fix 7: Normalize "germany" place_norm to actual cities (7 records)'
      ],
      archiveDir,
      dbPath
    }
  });

  // ============================================================================
  // PHASE 5: APPLY QUICK-WIN FIXES
  // ============================================================================

  ctx.log('info', 'Phase 5: Archive originals and apply quick-win fixes');

  const quickWinResults = await ctx.task(applyQuickWinFixesTask, {
    fixScriptsDir,
    dbPath,
    archiveDir,
    qaDir
  });

  artifacts.push({ path: `${qaDir}/fix-log.jsonl`, type: 'fix_log' });

  // ============================================================================
  // PHASE 6: BUILD & APPLY MEDIUM-EFFORT FIXES
  // ============================================================================

  ctx.log('info', 'Phase 6: Build and apply medium-effort fixes');

  const mediumFixScripts = await ctx.task(buildMediumFixesTask, {
    specPath,
    dbPath,
    fixScriptsDir,
    archiveDir,
    qaDir
  });

  // ============================================================================
  // PHASE 7: APPROVAL GATE — Medium fixes
  // ============================================================================

  await ctx.breakpoint({
    question: 'Medium-effort fix scripts are built. These address: multi-script agent merging (20+ pairs), bare "rené" investigation (657 records), country_name population (2,773 rows), and publisher authority research guidance. Approve to apply?',
    title: 'Approve Medium-Effort Data Fixes',
    context: {
      fixes: [
        'Fix 8: Merge multi-script agent_norm pairs sharing authority_uri',
        'Fix 9: Investigate & fix bare "rené" agent_norm',
        'Fix 10: Populate country_name from country_code lookup',
        'Fix 11: Document top unresearched publisher authorities'
      ],
      archiveDir,
      dbPath
    }
  });

  // ============================================================================
  // PHASE 8: APPLY MEDIUM FIXES
  // ============================================================================

  ctx.log('info', 'Phase 8: Apply medium-effort fixes');

  const mediumResults = await ctx.task(applyMediumFixesTask, {
    fixScriptsDir,
    dbPath,
    archiveDir,
    qaDir
  });

  // ============================================================================
  // PHASE 9: BUILD & APPLY LARGER INVESTMENT FIXES
  // ============================================================================

  ctx.log('info', 'Phase 9: Build larger investment fixes');

  const largerFixScripts = await ctx.task(buildLargerFixesTask, {
    specPath,
    dbPath,
    fixScriptsDir,
    archiveDir,
    qaDir
  });

  // ============================================================================
  // PHASE 10: APPROVAL GATE — Larger fixes
  // ============================================================================

  await ctx.breakpoint({
    question: 'Larger investment fix scripts are built. These address: missing publisher authorities (Aldine, Bomberg, Plantin, etc.), bridging 3,710 unmatched agents, collection scope boundary (pre/post 1950), and expanding Wikidata role inference. Approve to apply?',
    title: 'Approve Larger Investment Data Fixes',
    context: {
      fixes: [
        'Fix 12: Add missing publisher authorities for major historical publishers',
        'Fix 13: Bridge agents with no authority match via fuzzy/alias expansion',
        'Fix 14: Define scope boundary and flag out-of-scope records',
        'Fix 15: Expand Wikidata occupation→role inference',
        'Fix 16: Investigate 349 records with no subjects'
      ],
      archiveDir,
      dbPath
    }
  });

  // ============================================================================
  // PHASE 11: APPLY LARGER FIXES
  // ============================================================================

  ctx.log('info', 'Phase 11: Apply larger investment fixes');

  const largerResults = await ctx.task(applyLargerFixesTask, {
    fixScriptsDir,
    dbPath,
    archiveDir,
    qaDir
  });

  // ============================================================================
  // PHASE 12: SAMPLING & EXTERNAL VERIFICATION
  // ============================================================================

  ctx.log('info', 'Phase 12: Sampling & external verification (30 records, 5 fields each)');

  const samplingResults = await ctx.task(samplingVerificationTask, {
    dbPath,
    qaDir,
    specPath
  });

  artifacts.push({ path: `${qaDir}/sampling-verification.csv`, type: 'verification' });

  // ============================================================================
  // PHASE 13: FINAL QUALITY REPORT
  // ============================================================================

  ctx.log('info', 'Phase 13: Generate final quality report (post-fixes)');

  const finalReport = await ctx.task(generateFinalReportTask, {
    checksScript,
    dbPath,
    qaDir,
    samplingResults: `${qaDir}/sampling-verification.csv`
  });

  artifacts.push({ path: `${qaDir}/data-quality-report.json`, type: 'final_report' });

  // ============================================================================
  // PHASE 14: PROCESS DOCUMENTATION
  // ============================================================================

  ctx.log('info', 'Phase 14: Write process documentation and update Topic Registry');

  const docsResult = await ctx.task(writeDocumentationTask, {
    specPath,
    qaDir,
    fixScriptsDir,
    checksScript
  });

  artifacts.push({ path: 'docs/current/data-quality.md', type: 'documentation' });

  // ============================================================================
  // COMPLETION
  // ============================================================================

  ctx.log('info', 'Data Quality Scorecard & Remediation complete');

  return {
    success: true,
    artifacts,
    metadata: {
      processId: 'data-quality-scorecard',
      startTime,
      endTime: ctx.now()
    }
  };
}

// ============================================================================
// TASK DEFINITIONS
// ============================================================================

const buildChecksScriptTask = defineTask('build-checks-script', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build automated consistency checks script (scripts/qa/data_quality_checks.py)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in SQLite data quality',
      task: `Build a comprehensive data quality checks script at ${args.checksScript}. The script must:

1. Read the approved spec at ${args.specPath} for the full list of checks
2. Connect to ${args.dbPath} (read-only for checks)
3. Implement ALL Tier 1 checks from the spec:
   - Date Accuracy: impossible inversions, out-of-scope dates, wide ranges, gematria cross-validation, failed parses, agent lifespan vs publication date
   - Place Accuracy: place_norm vs country_code cross-validation, country-name-as-place detection, country_name population check
   - Agent Identity: multi-script fragmentation (same authority_uri → multiple agent_norm), bare first names, missing authority linkage, agent type conflicts
   - Publisher Identity: high-record publishers missing from authorities, unresearched authorities with records
   - Role Accuracy: unmapped roles with trailing periods, Hebrew role terms, missing MARC relators, missing roles
4. Implement ALL Tier 2 checks:
   - Subject Coverage: % with subjects, scheme consistency
   - Record Completeness: % missing key fields
   - Authority Enrichment: % with external links
5. Output a JSON report to ${args.qaDir}/data-quality-report.json with structure:
   { generated_at, record_count, tier1: { dimension: { score, errors: [{check, mms_id, detail}], total_checked, error_count } }, tier2: { dimension: { metric_name: value } } }
6. Also create ${args.qaDir}/ directory if it doesn't exist
7. Use argparse for CLI: --db-path, --output-dir flags
8. Include a summary table printed to stdout

Write clean, well-structured Python with type hints. Make it runnable with: python ${args.checksScript} --db-path ${args.dbPath} --output-dir ${args.qaDir}`,
      context: {
        specPath: args.specPath,
        dbPath: args.dbPath,
        qaDir: args.qaDir
      },
      instructions: [
        'Read the spec file first to understand all checks required',
        'Create the scripts/qa/ directory if needed',
        'Write the complete Python script',
        'Run it once to verify it works and produces valid JSON output',
        'Fix any errors until it runs cleanly',
        'Return a summary of the checks implemented and the baseline scores'
      ],
      outputFormat: 'JSON summary of checks implemented and baseline results'
    }
  }
}));

const runBaselineChecksTask = defineTask('run-baseline-checks', (args, taskCtx) => ({
  kind: 'shell',
  title: 'Run baseline consistency checks',
  shell: {
    command: `cd /home/hagaybar/projects/rare-books-bot && python ${args.checksScript} --db-path ${args.dbPath} --output-dir ${args.qaDir}`,
    timeout: 120000
  }
}));

const buildQuickWinFixesTask = defineTask('build-quick-win-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build quick-win fix scripts (fixes 1-7)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in bibliographic data remediation',
      task: `Build fix scripts in ${args.fixScriptsDir}/ for the 7 quick-win fixes from the spec at ${args.specPath}. Each fix is a separate Python script that:

1. **fix_01_role_trailing_periods.py**: Strip trailing periods from role_raw in agents table, then re-map to correct role_norm. Affects ~74 records.
2. **fix_02_hebrew_role_terms.py**: Map Hebrew role terms to English equivalents (מחבר→author, עורך→editor, מדפיס→printer, מתרגם→translator, מוסד מארח→host institution, בעל האוטוגרף→autographer). Affects ~49 records.
3. **fix_03_missing_relator_terms.py**: Add mappings for valid MARC relator terms not yet in the map (writer of added commentary, host institution, autographer, writer of introduction, issuing body, writer of supplementary textual content, writer of added text). Affects ~116 records.
4. **fix_04_subject_scheme_normalize.py**: Normalize "NLI" to "nli" in subjects.scheme. Affects 169 records.
5. **fix_05_calendar_confusion_dates.py**: Fix 2 specific calendar-confusion dates (Hijri 1244 stored as Gregorian, gematria misparse 1349). Query the DB to find the exact records and determine correct dates.
6. **fix_06_place_country_mismatches.py**: Fix ~12 place-country_code mismatches found in analysis (Venice/gw, London/ne, Geneva/it, etc.). Determine which is wrong (place or country_code) and fix accordingly.
7. **fix_07_germany_place_norm.py**: Fix 7 records where place_norm="germany" — research the actual city from the raw place data and other record context.

CRITICAL REQUIREMENTS for ALL scripts:
- Each script MUST archive original values to ${args.archiveDir}/ BEFORE modifying anything (create a JSON file with {mms_id, field, old_value, new_value} for each change)
- Each script MUST append to ${args.qaDir}/fix-log.jsonl after applying fixes
- Each script MUST be idempotent (safe to re-run)
- Each script MUST use argparse with --db-path and --dry-run flags
- Each script prints a summary of changes made
- Database path: ${args.dbPath}
- Connect to the actual DB to verify the affected records exist and understand the data shape before writing fix logic

Also create a runner script ${args.fixScriptsDir}/run_quick_wins.sh that runs all 7 in order.`,
      context: {
        specPath: args.specPath,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Read the spec file for full fix details',
        'Create the scripts/qa/fixes/ directory if needed',
        'Create the archive directory if needed',
        'Query the DB to understand exact records affected before writing each fix',
        'Write all 7 fix scripts + the runner script',
        'Test each script with --dry-run flag to verify it identifies the right records',
        'Return summary of scripts created and dry-run results'
      ],
      outputFormat: 'JSON summary of scripts created and dry-run results'
    }
  }
}));

const applyQuickWinFixesTask = defineTask('apply-quick-win-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Archive originals and apply quick-win fixes',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer executing approved data fixes',
      task: `Apply the quick-win fix scripts in ${args.fixScriptsDir}/ to the database at ${args.dbPath}.

Steps:
1. Create the archive directory at ${args.archiveDir}/ if not exists
2. Run each fix script in order (fix_01 through fix_07) WITHOUT --dry-run to apply changes
3. After each script, verify changes were applied correctly
4. Check that the fix-log.jsonl is being appended to
5. Run a quick verification query for each fix to confirm the data looks correct

CRITICAL: This modifies the database. The scripts MUST archive original values first. Verify the archive files exist after each script runs.`,
      context: {
        fixScriptsDir: args.fixScriptsDir,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Run each fix script in order',
        'Verify archive files were created',
        'Verify database changes are correct',
        'Report total changes made per fix'
      ],
      outputFormat: 'JSON summary of fixes applied and verification results'
    }
  }
}));

const buildMediumFixesTask = defineTask('build-medium-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build medium-effort fix scripts (fixes 8-11)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in bibliographic authority data',
      task: `Build fix scripts in ${args.fixScriptsDir}/ for the 4 medium-effort fixes from the spec at ${args.specPath}:

1. **fix_08_merge_multiscript_agents.py**: Find agents sharing the same authority_uri but with different agent_norm values (Latin vs Hebrew script). Merge them under a single canonical agent_norm in agent_authorities, keeping both as aliases. Query the DB first to find all 20+ pairs.

2. **fix_09_bare_rene_investigation.py**: Investigate the bare "rené" agent_norm (657 records). Query the DB to understand what records these are, whether they share a common authority_uri, and what the correct full name should be. Fix accordingly.

3. **fix_10_populate_country_name.py**: Populate the country_name column from country_code using the MARC Code List for Countries (https://www.loc.gov/marc/countries/). Build an inline lookup dict of MARC country codes → country names. Apply to all 2,773 rows with country_code.

4. **fix_11_document_unresearched_publishers.py**: Generate a prioritized research list of the 202 "unresearched" publisher authorities, ordered by record count. Output to ${args.qaDir}/publisher-research-priorities.csv with columns: canonical_name, record_count, sample_titles, type. This is a documentation/analysis script, not a DB modification.

Same CRITICAL REQUIREMENTS as quick wins:
- Archive before modify
- Append to fix-log.jsonl
- Idempotent
- argparse with --db-path and --dry-run
- Database path: ${args.dbPath}`,
      context: {
        specPath: args.specPath,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Read the spec for full details',
        'Query the DB to understand each issue before writing fix logic',
        'Write all 4 scripts',
        'Test with --dry-run',
        'Return summary of scripts and dry-run findings'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const applyMediumFixesTask = defineTask('apply-medium-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Apply medium-effort fixes (fixes 8-11)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer executing approved data fixes',
      task: `Apply the medium-effort fix scripts (fix_08 through fix_11) in ${args.fixScriptsDir}/ to the database at ${args.dbPath}.

Steps:
1. Run each fix script in order WITHOUT --dry-run
2. Verify archive files created
3. Verify database changes correct
4. Check fix-log.jsonl updated
5. For fix_11 (publisher research), verify the CSV was generated

Report total changes per fix.`,
      context: {
        fixScriptsDir: args.fixScriptsDir,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Run each fix script',
        'Verify results',
        'Report changes'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const buildLargerFixesTask = defineTask('build-larger-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Build larger investment fix scripts (fixes 12-16)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Python data engineer specializing in bibliographic authority research and data enrichment',
      task: `Build fix scripts in ${args.fixScriptsDir}/ for the 5 larger investment fixes from the spec at ${args.specPath}:

1. **fix_12_add_missing_publisher_authorities.py**: Add publisher_authorities entries for major historical publishers found in imprints but missing from authorities: Aldine Press (Venice), Daniel Bomberg (Venice), Christophe Plantin (Antwerp), Blaeu (Amsterdam), Insel Verlag, House of Elzevir, Bragadin Press, etc. Use web search to research each publisher's dates_active, location, type. Create authority + variants entries. DO NOT make external API calls — use only web search and existing DB data.

2. **fix_13_bridge_unmatched_agents.py**: Bridge the 3,710 agents with no authority match. Strategy:
   a) Check if agent_norm exists as an alias in agent_aliases but just isn't linked
   b) Try fuzzy matching (Levenshtein distance ≤ 2) against agent_authorities.canonical_name_lower
   c) For remaining unmatched, create stub authority entries so future enrichment can fill them in
   Report how many were matched by each strategy.

3. **fix_14_collection_scope_boundary.py**: Add a 'scope_flag' to records or create a scope_flags table. Flag records with date_start > 1950 as 'modern_reprint_or_edition'. Flag records with date_start < 1400 as 'needs_date_review'. This is metadata tagging, not data deletion.

4. **fix_15_expand_wikidata_role_inference.py**: For the 706 agents with missing_role, check if they have Wikidata enrichment with occupations. Map occupations to bibliographic roles using the existing wikidata_occupation_direct and wikidata_occupation_semantic patterns already in the codebase. Query the DB to understand the existing pattern first.

5. **fix_16_investigate_subjectless_records.py**: Analyze the 349 records with no subjects. Categorize them: what languages, what time periods, what types of works. Generate a report at ${args.qaDir}/subjectless-records-analysis.csv. For records that have notes containing subject-like information, flag them as candidates for subject derivation.

Same CRITICAL REQUIREMENTS as before. NO external API calls (per user constraint). Web search OK for publisher research.`,
      context: {
        specPath: args.specPath,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Read spec for full details',
        'Query DB to understand each issue',
        'For fix_12 (publishers), use web search to research historical publishers',
        'Write all 5 scripts',
        'Test with --dry-run',
        'Return summary'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const applyLargerFixesTask = defineTask('apply-larger-fixes', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Apply larger investment fixes (fixes 12-16)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data engineer executing approved data fixes',
      task: `Apply the larger fix scripts (fix_12 through fix_16) in ${args.fixScriptsDir}/ to the database at ${args.dbPath}.

Run each in order, verify archives, verify changes, check fix-log.jsonl. Report total changes per fix.`,
      context: {
        fixScriptsDir: args.fixScriptsDir,
        dbPath: args.dbPath,
        archiveDir: args.archiveDir,
        qaDir: args.qaDir
      },
      instructions: [
        'Run each fix script',
        'Verify results',
        'Report changes'
      ],
      outputFormat: 'JSON summary'
    }
  }
}));

const samplingVerificationTask = defineTask('sampling-verification', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Sampling & external verification (30 records × 5 fields)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Bibliographic data quality analyst performing external verification',
      task: `Perform the sampling & external verification protocol from the spec at ${args.specPath}.

1. Select 30 records from ${args.dbPath} using stratified sampling:
   - 8 Hebrew gematria dates (date_method LIKE 'hebrew_gematria%')
   - 5 pre-1600 records (date_start < 1600)
   - 5 multi-script agent records (agents with authority_uri appearing under multiple scripts)
   - 5 embedded dates (date_method LIKE 'year_embedded%')
   - 7 random from remaining

2. For each record, verify 5 fields against the NLI Primo catalog. The Primo URL pattern is: https://primo.nli.org.il/discovery/fulldisplay?vid=972NNL_INST:NNL&docid=alma[mms_id]
   - Date: Does date_start match the actual publication year?
   - Place: Does place_norm match the actual place of publication?
   - Agent names: Is this the right person?
   - Publisher: Does publisher_norm map to correct entity?
   - Role: Is assigned role correct?

3. Use web search to verify when Primo is insufficient.

4. Write results to ${args.qaDir}/sampling-verification.csv with columns:
   mms_id,stratum,field,db_value,verified_value,correct,error_type,notes

5. Calculate error rates per dimension from the 150 verification points.

IMPORTANT: Do NOT make paid API calls. Use web search and public URLs only.`,
      context: {
        specPath: args.specPath,
        dbPath: args.dbPath,
        qaDir: args.qaDir
      },
      instructions: [
        'Select the 30 records using SQL queries',
        'For each record, look up the Primo URL via web search',
        'Verify each field',
        'Write the CSV',
        'Calculate and report error rates per dimension'
      ],
      outputFormat: 'JSON with error rates per dimension and total verification points'
    }
  }
}));

const generateFinalReportTask = defineTask('generate-final-report', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Generate final quality report (post-fixes)',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Data quality analyst generating final scorecard',
      task: `Generate the final data quality report after all fixes have been applied.

1. Run the checks script: python ${args.checksScript} --db-path ${args.dbPath} --output-dir ${args.qaDir}
2. Read the sampling verification CSV at ${args.samplingResults}
3. Combine automated check results with sampling results
4. Produce the final report at ${args.qaDir}/data-quality-report.json with:
   - Tier 1 dimension scores (incorporating both automated and sampling error rates)
   - Tier 2 gap analysis metrics
   - Comparison: before vs after fixes
   - Weighted overall Tier 1 score
5. Print a formatted summary table to stdout showing before/after comparison`,
      context: {
        checksScript: args.checksScript,
        dbPath: args.dbPath,
        qaDir: args.qaDir,
        samplingResults: args.samplingResults
      },
      instructions: [
        'Run the automated checks script',
        'Parse the sampling CSV',
        'Calculate final scores',
        'Write the report JSON',
        'Print before/after summary'
      ],
      outputFormat: 'JSON final quality scores'
    }
  }
}));

const writeDocumentationTask = defineTask('write-documentation', (args, taskCtx) => ({
  kind: 'agent',
  title: 'Write process documentation and update Topic Registry',
  agent: {
    name: 'general-purpose',
    prompt: {
      role: 'Technical writer documenting data quality processes',
      task: `Write the process documentation and update the project's documentation system.

1. Create docs/current/data-quality.md with:
   - Overview of the data quality framework
   - For each fix process (1-16):
     a. Problem: What's wrong, how many records, how detected
     b. Detection query: Exact SQL
     c. Fix method: What the script does
     d. Verification: How to confirm the fix worked
     e. Re-run: How to apply after a fresh ingest
   - How to run the automated checks script
   - How to interpret the quality report
   - Sampling protocol for future assessments

2. Update CLAUDE.md Topic Registry table to add the new data-quality entry:
   | Data Quality | docs/current/data-quality.md | Quality checks, fix scripts, sampling protocol, remediation |

3. Set "Last verified: 2026-04-02" in the new doc header.

Read the existing fix scripts in ${args.fixScriptsDir}/ and the checks script at ${args.checksScript} to document them accurately. Also read ${args.qaDir}/fix-log.jsonl for the actual changes made.`,
      context: {
        specPath: args.specPath,
        fixScriptsDir: args.fixScriptsDir,
        checksScript: args.checksScript,
        qaDir: args.qaDir
      },
      instructions: [
        'Read existing fix scripts to understand what they do',
        'Read the fix log for actual changes',
        'Write docs/current/data-quality.md',
        'Update CLAUDE.md Topic Registry',
        'Return summary of docs written'
      ],
      outputFormat: 'JSON summary of documentation created'
    }
  }
}));
