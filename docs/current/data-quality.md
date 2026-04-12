# Data Quality

> Last verified: 2026-04-12
> Source of truth for: Quality checks, fix scripts, sampling protocol, remediation processes

## 1. Overview

The data quality system uses a **two-tier quality model** to assess and remediate the 2,796 records in `bibliographic.db`:

- **Tier 1 (Zero-Error Target)**: Dimensions that directly affect answer correctness. Every error is a bug to fix. Five weighted dimensions: Date Accuracy (0.20), Place Accuracy (0.20), Agent Identity (0.25), Publisher Identity (0.15), Role Accuracy (0.20).
- **Tier 2 (Gap Analysis)**: Dimensions that measure coverage and completeness. Analyzed for awareness and prioritization: Subject Coverage, Record Completeness, Authority Enrichment.

**Overall Tier 1 score**: 0.868 (weighted combination of all five dimensions).

Design spec: `docs/superpowers/specs/2026-04-02-data-quality-scorecard-design.md`

## 2. Running the Quality Checks

### Command

```bash
python3 scripts/qa/data_quality_checks.py \
  --db-path data/index/bibliographic.db \
  --output-dir data/qa
```

### What It Produces

- `data/qa/data-quality-report.json` -- Full JSON report with every error keyed by `(dimension, check_name, mms_id)`, tier scores, tier 2 gap analysis, sampling verification results, and before/after comparisons.
- Formatted summary printed to stdout showing scores and error counts per dimension.

### How to Interpret

Each Tier 1 dimension has:
- `score`: 1 - (error_count / total_checked). Goal is 1.0.
- `weight`: Contribution to the overall weighted score.
- `errors`: Array of `{check, mms_id, detail}` tuples identifying every specific error.

Tier 2 dimensions report coverage percentages and counts (no error scoring).

### Current Automated Scores

| Dimension | Score | Weight | Checked | Errors |
|-----------|-------|--------|---------|--------|
| Date Accuracy | 0.886 | 0.20 | 2,758 | 314 |
| Place Accuracy | 0.996 | 0.20 | 2,754 | 11 |
| Agent Identity | 0.383 | 0.25 | 3,102 | 1,914 |
| Publisher Identity | 0.902 | 0.15 | 2,130 | 209 |
| Role Accuracy | 0.856 | 0.20 | 4,894 | 705 |
| **Overall (weighted)** | **0.868** | | | |

### Tier 2 Gap Analysis

| Dimension | Key Metric |
|-----------|-----------|
| Subject Coverage | 87.5% of records have subjects (349 without) |
| Record Completeness | 81.9% complete (all key fields populated) |
| Authority Enrichment | 79.9% agent URIs enriched; 11.0% publishers researched |

## 3. Fix Processes

All 19 fix scripts live in `scripts/qa/fixes/`. Each script:
- Takes `--db-path` (defaults to `data/index/bibliographic.db`) and `--dry-run` flags
- Is **idempotent**: safe to re-run after re-ingest; finds only unfixed records
- Preserves raw MARC values (only modifies normalized/derived fields)
- Appends results to `data/qa/fix-log.jsonl`

Quick wins (fixes 01-07) can be run together:
```bash
bash scripts/qa/fixes/run_quick_wins.sh
```

---

### Fix 01: Role Trailing Periods

- **Problem**: 81 agent-role rows have `role_method='unmapped'` because `role_raw` ends with a trailing period (e.g., `"printer."` instead of `"printer"`). The normalizer does not strip punctuation before mapping.
- **Detection**: `SELECT * FROM agents WHERE role_method = 'unmapped' AND role_raw LIKE '%.';`
- **Fix script**: `scripts/qa/fixes/fix_01_role_trailing_periods.py`
- **Usage**: `python3 scripts/qa/fixes/fix_01_role_trailing_periods.py --db-path data/index/bibliographic.db`
- **What it does**: Strips trailing period from `role_raw`, looks up the cleaned term in the MARC relator map, updates `role_norm`, `role_method='trailing_period_fix'`, and `role_confidence`.
- **Verification**: Re-run quality checks; `unmapped` count for trailing-period terms should be 0.
- **Dimension**: Role Accuracy

### Fix 02: Hebrew Role Terms

- **Problem**: 54 agent-role rows have `role_method='unmapped'` because the role term is in Hebrew or Arabic (e.g., author, editor, printer, translator in Hebrew script). The normalizer only has English/Latin relator maps.
- **Detection**: `SELECT * FROM agents WHERE role_method = 'unmapped' AND role_raw GLOB '*[^A-Za-z0-9 .,-]*';` (non-ASCII characters)
- **Fix script**: `scripts/qa/fixes/fix_02_hebrew_role_terms.py`
- **Usage**: `python3 scripts/qa/fixes/fix_02_hebrew_role_terms.py --db-path data/index/bibliographic.db`
- **What it does**: Maps Hebrew/Arabic role terms to English equivalents using a built-in dictionary. Sets `role_method='hebrew_mapped'`.
- **Verification**: Re-run quality checks; Hebrew unmapped roles should be 0.
- **Dimension**: Role Accuracy

### Fix 03: Missing MARC Relator Terms

- **Problem**: 130 agent-role rows have `role_method='unmapped'` because their MARC relator terms (e.g., "writer of added commentary", "host institution", "autographer") are valid but absent from the normalizer's relator map.
- **Detection**: `SELECT * FROM agents WHERE role_method = 'unmapped' AND role_raw NOT LIKE '%.' AND role_raw GLOB '[A-Za-z]*';`
- **Fix script**: `scripts/qa/fixes/fix_03_missing_relator_terms.py`
- **Usage**: `python3 scripts/qa/fixes/fix_03_missing_relator_terms.py --db-path data/index/bibliographic.db`
- **What it does**: Extends the relator vocabulary with missing terms and remaps affected rows. Sets `role_method='relator_term_fix'`.
- **Verification**: Re-run quality checks; relator-term unmapped count should be 0.
- **Dimension**: Role Accuracy

### Fix 04: Subject Scheme Normalization

- **Problem**: 169 subject rows have scheme `"NLI"` (uppercase) while the rest use `"nli"` (lowercase), causing inconsistent filtering.
- **Detection**: `SELECT * FROM subjects WHERE scheme = 'NLI';`
- **Fix script**: `scripts/qa/fixes/fix_04_subject_scheme_normalize.py`
- **Usage**: `python3 scripts/qa/fixes/fix_04_subject_scheme_normalize.py --db-path data/index/bibliographic.db`
- **What it does**: `UPDATE subjects SET scheme = 'nli' WHERE scheme = 'NLI';`
- **Verification**: `SELECT COUNT(*) FROM subjects WHERE scheme = 'NLI';` should return 0.
- **Dimension**: Subject Coverage (Tier 2)

### Fix 05: Calendar Confusion Dates

- **Problem**: 2 records have incorrect `date_start` due to calendar confusion: one Hijri date (1244 Hijri = 1828 CE) and one gematria misparse (1349 should be 1834).
- **Detection**: Check `date_accuracy` errors with `check='calendar_confusion'` in the quality report.
- **Fix script**: `scripts/qa/fixes/fix_05_calendar_confusion_dates.py`
- **Usage**: `python3 scripts/qa/fixes/fix_05_calendar_confusion_dates.py --db-path data/index/bibliographic.db`
- **What it does**: Manually corrects `date_start`, `date_end`, `date_label`, `date_method`, and `date_confidence` for the two affected records (`990013146190204146`, `990013766990204146`).
- **Verification**: Re-run quality checks; `calendar_confusion` error count should be 0.
- **Dimension**: Date Accuracy

### Fix 06: Place-Country Code Mismatches

- **Problem**: 19 imprint rows have `country_code` that contradicts `place_norm` (e.g., Venice tagged as Germany, London tagged as Netherlands).
- **Detection**: Cross-validate `place_norm` against a known place-to-country-code map in the checks script.
- **Fix script**: `scripts/qa/fixes/fix_06_place_country_mismatches.py`
- **Usage**: `python3 scripts/qa/fixes/fix_06_place_country_mismatches.py --db-path data/index/bibliographic.db`
- **What it does**: Updates `country_code` to the correct MARC country code based on `place_norm`. Records details of each old/new mapping in the fix log.
- **Verification**: Re-run quality checks; `place_country_mismatch` errors should be 0.
- **Dimension**: Place Accuracy

### Fix 07: Germany-Level Place Normalization

- **Problem**: 7 records have `place_norm = 'germany'` (a country, not a city) because the MARC source only says "[Germany]", "Germanien", or "Deutschland" with no city specified.
- **Detection**: `SELECT * FROM imprints WHERE place_norm = 'germany';`
- **Fix script**: `scripts/qa/fixes/fix_07_germany_place_norm.py`
- **Usage**: `python3 scripts/qa/fixes/fix_07_germany_place_norm.py --db-path data/index/bibliographic.db`
- **What it does**: Flags these records with `place_method='country_only'` and adjusts `place_confidence` to indicate that no city-level data exists in the source MARC. Does NOT invent a city.
- **Verification**: Re-run quality checks; `place_norm_is_country` errors should be 0 (flagged, not fixed).
- **Dimension**: Place Accuracy

### Fix 08: Merge Multi-Script Agent Variants

- **Problem**: 43 agent groups have Latin and Hebrew name variants that refer to the same person but are stored as separate `agent_norm` values, even when sharing the same `authority_uri`. This fragments identity.
- **Detection**: `SELECT authority_uri, COUNT(DISTINCT agent_norm) FROM agents WHERE authority_uri IS NOT NULL GROUP BY authority_uri HAVING COUNT(DISTINCT agent_norm) > 1;`
- **Fix script**: `scripts/qa/fixes/fix_08_merge_multiscript_agents.py`
- **Usage**: `python3 scripts/qa/fixes/fix_08_merge_multiscript_agents.py --db-path data/index/bibliographic.db`
- **What it does**: Creates/updates `agent_authorities` and `agent_aliases` to bridge multi-script variants under a single authority. Processed 43 groups, created 39 authorities, added 56 aliases.
- **Verification**: Re-run the authority-URI duplication check; duplicate count should be 0.
- **Dimension**: Agent Identity

### Fix 09: Bare First-Name Agents

- **Problem**: 61 agent rows have bare first names as `agent_norm` (e.g., "rene" for Rene Descartes). This is a parsing artifact where the normalizer stripped the surname.
- **Detection**: Short `agent_norm` values (< 10 chars) with high record counts, or single-word names.
- **Fix script**: `scripts/qa/fixes/fix_09_bare_rene_investigation.py`
- **Usage**: `python3 scripts/qa/fixes/fix_09_bare_rene_investigation.py --db-path data/index/bibliographic.db`
- **What it does**: Investigates each bare name, classifying them as classical single-name authors (25), genuinely bare first names (33), or already handled (3). Creates authority stubs and aliases. Does NOT delete agents -- annotates them.
- **Verification**: Check `agent_authorities` for newly classified bare-name entries.
- **Dimension**: Agent Identity

### Fix 10: Populate Country Name

- **Problem**: 2,771 imprint rows have a `country_code` but empty `country_name`. The column exists in the schema but was never populated.
- **Detection**: `SELECT COUNT(*) FROM imprints WHERE country_code IS NOT NULL AND country_name IS NULL;`
- **Fix script**: `scripts/qa/fixes/fix_10_populate_country_name.py`
- **Usage**: `python3 scripts/qa/fixes/fix_10_populate_country_name.py --db-path data/index/bibliographic.db`
- **What it does**: Maps every `country_code` to a human-readable `country_name` using the MARC country code table. Updated 2,771 rows, 2 skipped (null code), 0 unmapped.
- **Verification**: `SELECT COUNT(*) FROM imprints WHERE country_code IS NOT NULL AND country_name IS NULL;` should return 0.
- **Dimension**: Place Accuracy

### Fix 11: Document Unresearched Publishers

- **Problem**: 202 of 227 publisher authorities (89%) have `type='unresearched'`. These are authority stubs with no verified information.
- **Detection**: `SELECT * FROM publisher_authorities WHERE type = 'unresearched';`
- **Fix script**: `scripts/qa/fixes/fix_11_document_unresearched_publishers.py`
- **Usage**: `python3 scripts/qa/fixes/fix_11_document_unresearched_publishers.py --db-path data/index/bibliographic.db`
- **What it does**: **Analysis only, no DB changes.** Generates a priority CSV (`data/qa/publisher-research-priorities.csv`) ranking 200 publishers by record count to guide future manual research.
- **Verification**: Check that `data/qa/publisher-research-priorities.csv` exists and contains the prioritized list.
- **Dimension**: Publisher Identity

### Fix 12: Add Missing Publisher Authorities

- **Problem**: Major publishers (Aldine, Bomberg, Plantin, Blaeu, Insel, etc.) have records in the collection but no `publisher_variants` linking `publisher_norm` values to existing authorities.
- **Detection**: High-record-count publishers missing from `publisher_variants` join.
- **Fix script**: `scripts/qa/fixes/fix_12_add_missing_publisher_authorities.py`
- **Usage**: `python3 scripts/qa/fixes/fix_12_add_missing_publisher_authorities.py --db-path data/index/bibliographic.db`
- **What it does**: Creates `publisher_variants` rows linking known `publisher_norm` values to their existing authorities. Initially 11 rows covering 88 records; subsequently expanded by 53 additional variants covering 11 more authorities (commit 746b39b).
- **Verification**: Re-run quality checks; named publishers should now resolve through the variants table.
- **Dimension**: Publisher Identity

### Fix 13: Bridge Unmatched Agents

- **Problem**: 1,946 agent rows have no match in `agent_authorities`, representing 75.8% of all agents.
- **Detection**: `SELECT * FROM agents WHERE agent_norm NOT IN (SELECT agent_norm FROM agent_authorities) AND authority_uri IS NULL;`
- **Fix script**: `scripts/qa/fixes/fix_13_bridge_unmatched_agents.py`
- **Usage**: `python3 scripts/qa/fixes/fix_13_bridge_unmatched_agents.py --db-path data/index/bibliographic.db`
- **What it does**: Uses three strategies: prefix matching (70 matched), URI-based matching from MARC data (1,550 matched), and stub creation for the remainder (326 stubs). Creates entries in `agent_authorities` and `agent_aliases`.
- **Verification**: Re-run the authority-gap check; unmatched count should drop significantly.
- **Dimension**: Agent Identity

### Fix 14: Collection Scope Boundary

- **Problem**: 247 records have `date_start > 1950`, placing them outside the expected rare-books scope. These inflate the date-accuracy error count without being actual data errors.
- **Detection**: `SELECT * FROM imprints WHERE date_start > 1950;`
- **Fix script**: `scripts/qa/fixes/fix_14_collection_scope_boundary.py`
- **Usage**: `python3 scripts/qa/fixes/fix_14_collection_scope_boundary.py --db-path data/index/bibliographic.db`
- **What it does**: Creates a `record_scope_flags` table and inserts 247 rows flagged as `modern_reprint_or_edition`. Records are NOT deleted -- only tagged.
- **Verification**: `SELECT COUNT(*) FROM record_scope_flags WHERE flag = 'modern_reprint_or_edition';` should return 247.
- **Dimension**: Date Accuracy

### Fix 15: Expand Wikidata Role Inference

- **Problem**: 706 agent rows have `role_method='missing_role'` (no role data in the MARC source at all). Wikidata occupation data could infer roles for some of these.
- **Detection**: `SELECT * FROM agents WHERE role_method = 'missing_role';`
- **Fix script**: `scripts/qa/fixes/fix_15_expand_wikidata_role_inference.py`
- **Usage**: `python3 scripts/qa/fixes/fix_15_expand_wikidata_role_inference.py --db-path data/index/bibliographic.db`
- **What it does**: Checks existing Wikidata enrichment for occupation data and maps occupations to roles. Found 1 semantic match (author); 705 had no Wikidata occupation data available. **No external API calls** -- uses only cached enrichment data.
- **Verification**: Re-run quality checks; `missing_role` count may decrease slightly.
- **Dimension**: Role Accuracy

### Fix 16: Investigate Subjectless Records

- **Problem**: 349 records (12.5%) have no subject headings at all.
- **Detection**: `SELECT r.mms_id FROM records r LEFT JOIN subjects s ON r.mms_id = s.mms_id WHERE s.mms_id IS NULL;`
- **Fix script**: `scripts/qa/fixes/fix_16_investigate_subjectless_records.py`
- **Usage**: `python3 scripts/qa/fixes/fix_16_investigate_subjectless_records.py --db-path data/index/bibliographic.db`
- **What it does**: **Analysis only, no DB changes.** Produces `data/qa/subjectless-records-analysis.csv` with breakdowns by language (118 Hebrew, 67 French, 60 German, ...) and period (141 from 1700-1900). Identifies 46 modern reprints and 11 Hebrew liturgical works.
- **Verification**: Check that `data/qa/subjectless-records-analysis.csv` exists.
- **Dimension**: Subject Coverage (Tier 2)

### Fix 17: Enrich Publisher Authorities

- **Problem**: Many publisher authority records remain 'unresearched' despite web research data being available.
- **Detection**: `SELECT COUNT(*) FROM publisher_authorities WHERE type = 'unresearched';`
- **Fix script**: `scripts/qa/fixes/fix_17_enrich_publishers.py`
- **Usage**: `python3 scripts/qa/fixes/fix_17_enrich_publishers.py --db-path data/index/bibliographic.db`
- **What it does**: Reads `data/qa/publisher-research-results.json` and updates `publisher_authorities` rows where research confidence >= 0.90. Updates type, dates, location, notes, and sources. **No external API calls** -- uses only cached research data.
- **Verification**: Re-check unresearched count; should decrease.
- **Dimension**: Publisher Identity

### Fix 18: Apply Subject Proposals

- **Problem**: 349 records have no subject headings (identified by Fix 16). Proposed subjects are available from prior analysis.
- **Detection**: Records in `data/qa/proposed-subjects.json` without subjects in the DB.
- **Fix script**: `scripts/qa/fixes/fix_18_apply_subject_proposals.py`
- **Usage**: `python3 scripts/qa/fixes/fix_18_apply_subject_proposals.py --db-path data/index/bibliographic.db`
- **What it does**: Inserts proposed subject headings from `data/qa/proposed-subjects.json` into the `subjects` table for records that currently have no subjects (gap-filling for Tier 2).
- **Verification**: `SELECT COUNT(DISTINCT r.mms_id) FROM records r LEFT JOIN subjects s ON r.mms_id = s.mms_id WHERE s.mms_id IS NULL;` should show fewer subjectless records.
- **Dimension**: Subject Coverage (Tier 2)

### Fix 19: Add Hebrew Subject Translations

- **Problem**: Subject headings exist only in English, preventing Hebrew-language search.
- **Detection**: `SELECT COUNT(*) FROM subjects WHERE value_he IS NULL;`
- **Fix script**: `scripts/qa/fixes/fix_19_add_hebrew_subjects.py`
- **Usage**: `python3 scripts/qa/fixes/fix_19_add_hebrew_subjects.py --db-path data/index/bibliographic.db`
- **What it does**: Adds a `value_he` column to the subjects table. Translates 3,094+ subject headings into Hebrew using a component-based approach (base terms + subdivisions translated independently, then composed). Rebuilds the `subjects_fts` FTS5 index to include Hebrew values for bilingual search. Coverage: 78.4% of unique headings, 83.6% of subject rows.
- **Verification**: `SELECT COUNT(*) FROM subjects WHERE value_he IS NOT NULL;` should return ~3,094+.
- **Dimension**: Subject Coverage (Tier 2)

## 4. Sampling Protocol

### Purpose

The automated checks catch consistency errors within the database. The sampling protocol catches errors where the database is internally consistent but factually wrong (e.g., a date that parses correctly but is the wrong year).

### Sampling Strategy

30 records, stratified to cover the riskiest areas:

| Stratum | Count | Rationale |
|---------|-------|-----------|
| Hebrew gematria dates | 8 | 555 records, highest parsing complexity |
| Pre-1600 records | 5 | Oldest records, unusual MARC conventions |
| Multi-script agents (Latin + Hebrew) | 5 | Where dedup fragmentation happens |
| Embedded/extracted dates | 5 | Dates from surrounding text, higher misparse risk |
| Random sample (remaining) | 7 | Unbiased baseline |

### Verification Procedure

For each of the 30 sampled records, verify 5 fields against external sources (NLI Primo public URLs, HebrewBooks, WorldCat, Wikipedia, auction records):

| Field | What to Check |
|-------|---------------|
| Date | Does `date_start` match the actual publication year? |
| Place | Does `place_norm` match the actual place of publication? |
| Agent | Is this the right person? Are multi-script variants the same person? |
| Publisher | Does `publisher_norm` map to the correct entity? |
| Role | Is the assigned role correct per the MARC 1XX/7XX relator codes? |

This produces 150 verification points (30 records x 5 fields). **No paid API calls** -- uses only web search and public catalog URLs.

### Output

`data/qa/sampling-verification.csv` -- columns: `mms_id | stratum | field | db_value | verified_value | correct | error_type | notes`

### Sampling Error Rates (2026-04-02)

| Field | Error Rate |
|-------|-----------|
| Date | 10.7% |
| Place | 3.8% |
| Agent | 0.0% |
| Publisher | 4.3% |
| Role | 3.7% |

## 5. Output Artifacts

| File | Purpose |
|------|---------|
| `data/qa/data-quality-report.json` | Full quality report: all errors, scores, tier 2 stats, before/after comparison |
| `data/qa/sampling-verification.csv` | 30-record manual verification results |
| `data/qa/fix-log.jsonl` | Append-only log of every fix applied (timestamp, fix_id, mms_ids, fields changed) |
| `data/qa/publisher-research-priorities.csv` | Publisher authorities ranked by record count for research prioritization |
| `data/qa/subjectless-records-analysis.csv` | Analysis of 349 records without subjects, by language and period |

## 6. Before/After Results

Comparison of Tier 1 scores before and after all 19 fix processes were applied:

| Dimension | Baseline Score | Current Score (Combined) | Improvement |
|-----------|---------------|-------------------------|-------------|
| Date Accuracy | 0.885 | 0.890 | +0.005 |
| Place Accuracy | 0.987 | 0.979 | -0.008 |
| Agent Identity | 0.259 | 0.691 | +0.433 |
| Publisher Identity | 0.897 | 0.929 | +0.032 |
| Role Accuracy | 0.802 | 0.909 | +0.108 |
| **Overall (weighted)** | **0.734** | **0.868** | **+0.134** |

Notes on the scores:
- **Agent Identity** saw the largest improvement (+0.433) from fixes 08, 09, and 13 bridging unmatched agents to authorities.
- **Role Accuracy** improved +0.108 from fixes 01-03 (trailing periods, Hebrew terms, missing relators) and fix 15 (Wikidata inference).
- **Place Accuracy** shows a slight decrease (-0.008) because the sampling verification found some errors that the automated checks do not yet catch. The automated score improved from 0.987 to 0.996; the combined (automated + sampling) score is 0.979.
- "Combined" scores blend automated consistency checks with sampling verification error rates for a more accurate picture.
- "Baseline" refers to the state before the M2 quality improvement work began.
