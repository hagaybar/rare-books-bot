# Data Quality Scorecard & Remediation Roadmap

> Design spec for comprehensive data quality assessment of bibliographic.db
> Created: 2026-04-02
> Status: Approved

## 1. Goal

Assess and fix weaknesses in the actual bibliographic data (2,796 records) across accuracy, completeness, and authority richness. Produce a reusable quality infrastructure that runs after every ingest.

**Primary success criterion**: Tier 1 dimensions (dates, places, agents, publishers, roles) aspire to zero errors. Every error found is a specific fix item with a record ID.

## 2. Two-Tier Quality Model

### Tier 1 — Zero-Error Target

These dimensions directly affect whether answers are correct. Every error is a bug to fix.

| # | Dimension | Weight | Error Metric |
|---|-----------|--------|-------------|
| 1 | **Date Accuracy** | 0.20 | Count of wrong dates (calendar confusion, misparses, range errors) |
| 2 | **Place Accuracy** | 0.20 | Count of place-country mismatches, wrong normalizations |
| 3 | **Agent Identity** | 0.25 | Count of mis-identified agents, unmerged duplicates, wrong authority links |
| 4 | **Publisher Identity** | 0.15 | Count of wrong normalizations, misattributions |
| 5 | **Role Accuracy** | 0.20 | Count of wrong/missing role mappings |

**Scoring**: Error rate = errors found / total checked. Score = 1 - error rate. Goal is 1.0. Every error logged with record ID. Weights sum to 1.0 within Tier 1 only.

### Tier 2 — Gap Analysis

These dimensions measure how much we know, not whether what we know is correct. Analyzed for awareness and prioritization.

| # | Dimension | What We Measure |
|---|-----------|----------------|
| 6 | **Subject Coverage** | % of records with subjects, distribution, scheme consistency |
| 7 | **Record Completeness** | % of records missing key fields (thin record census) |
| 8 | **Authority Enrichment** | % of agents/publishers with external links, quality of enrichment data |

**Scoring**: Coverage percentage. Summary statistics and opportunity-size estimates.

## 3. Automated Consistency Checks

A single Python script (`scripts/qa/data_quality_checks.py`) runs all checks, outputs a JSON report with every error keyed by `(dimension, check_name, mms_id)`.

### Date Accuracy Checks

| Check | What It Catches | Known Errors |
|-------|----------------|-------------|
| `date_end < date_start` | Impossible inversions | 0 |
| `date_start < 1400 OR date_start > 1950` | Out-of-scope / calendar confusion | 251 (2 calendar bugs + ~249 scope questions) |
| `date_end - date_start > 100` | Suspiciously wide ranges | 5 (1 Hijri confusion) |
| Gematria vs non-gematria on same record, disagreement > 5yr | Hebrew date misparses | 0 |
| `date_raw IS NOT NULL AND date_start IS NULL` | Failed parses | 5 |
| Agent lifespan vs publication date (enrichment birth/death vs imprint date) | Anachronistic links | 1 (van der Aa d.1733 linked to 1970 pub) |

### Place Accuracy Checks

| Check | What It Catches | Known Errors |
|-------|----------------|-------------|
| `place_norm` vs `country_code` cross-validation | Wrong place or wrong country code | ~12 mismatches |
| `place_norm` is a country name, not a city | Normalization too coarse | 7 ("germany") |
| `country_name` column populated? | Schema waste | 0 of 2,773 rows populated |

### Agent Identity Checks

| Check | What It Catches | Known Errors |
|-------|----------------|-------------|
| Same `authority_uri` maps to multiple `agent_norm` values | Multi-script fragmentation | 20+ pairs |
| Bare first names as `agent_norm` | Parsing bugs | "rene" (actually `rené`) with 657 records |
| `agent_norm` not in `agent_authorities` | Missing authority linkage | 3,710 agents (75.8%) |
| Agent type conflicts on same `agent_norm` | Misclassification | 0 |

### Publisher Identity Checks

| Check | What It Catches | Known Errors |
|-------|----------------|-------------|
| High-record-count publishers missing from `publisher_authorities` | Authority gap | Aldine, Bomberg, Plantin, Blaeu, Insel |
| `publisher_authorities.type = 'unresearched'` with records | Unvetted authorities | 202 of 227 (89%) |

### Role Accuracy Checks

| Check | What It Catches | Known Errors |
|-------|----------------|-------------|
| `role_method = 'unmapped'` with trailing period in `role_raw` | Normalizer doesn't strip dots | ~74 |
| `role_method = 'unmapped'` with Hebrew role terms | Missing Hebrew-to-English map | ~49 |
| `role_method = 'unmapped'` with valid MARC relators not in map | Incomplete relator vocabulary | ~116 |
| `role_method = 'missing_role'` | No role data at all | 706 |

### Tier 2 Checks (Gap Analysis)

| Check | Dimension | Current Value |
|-------|-----------|--------------|
| % records with subjects | Subject Coverage | 87.5% (349 without) |
| Subject scheme consistency (NLI vs nli) | Subject Coverage | 169 inconsistent |
| % records with all key fields (imprint + agent + subject + language) | Record Completeness | TBD |
| % agents with enrichment | Authority Enrichment | 1,943 of 2,431 unique URIs |
| % publishers with enrichment | Authority Enrichment | 25 of 227 researched |

## 4. Sampling & External Verification Protocol

### Sampling Strategy

30 records, stratified to cover riskiest areas:

| Stratum | Count | Why |
|---------|-------|-----|
| Hebrew gematria dates | 8 | 555 records, highest parsing complexity |
| Pre-1600 records | 5 | Oldest, unusual MARC conventions |
| Multi-script agents (Latin + Hebrew) | 5 | Where dedup fragmentation happens |
| Embedded/extracted dates (`year_embedded`, `year_embedded_range`) | 5 | Dates from surrounding text, higher misparse risk |
| Random sample (remaining) | 7 | Unbiased baseline |

### Verification Per Record

For each sampled record, verify against NLI Primo (public URL from mms_id) and web search:

| Field | Source | What We Check |
|-------|--------|---------------|
| Date | Primo record + title page | Does `date_start` match actual publication year? |
| Place | Primo record | Does `place_norm` match actual place? |
| Agent names | Primo + VIAF/Wikidata | Is this the right person? Are multi-script variants same person? |
| Publisher | Primo record | Does `publisher_norm` map to correct entity? |
| Role | Primo 1XX/7XX relator codes | Is assigned role correct? |

### Output

CSV with columns: `mms_id | stratum | field | db_value | verified_value | correct | error_type | notes`

30 records x 5 fields = 150 verification points.

**No paid API calls** — uses web search and public Primo URLs only.

## 5. Remediation Roadmap

All fixes applied. Everything fixable gets fixed. Original values archived before any DB modification.

### Quick Wins (mechanical fixes, high impact)

| # | Fix | Records | Effort | Dimension |
|---|-----|---------|--------|-----------|
| 1 | Strip trailing periods from `role_raw` before mapping | 74 | 1 line in normalizer | Role Accuracy |
| 2 | Add Hebrew role term map (author, editor, printer, translator, etc.) | ~49 | Small dict | Role Accuracy |
| 3 | Add missing MARC relator terms (writer of added commentary, host institution, autographer, etc.) | ~116 | Extend relator map | Role Accuracy |
| 4 | Normalize subject scheme "NLI" to "nli" | 169 | 1 SQL update | Subject Coverage |
| 5 | Fix 2 calendar-confusion dates (Hijri 1244, gematria misparse 1349) | 2 | Manual correction | Date Accuracy |
| 6 | Fix ~12 place-country_code mismatches | ~12 | Manual per-record | Place Accuracy |
| 7 | Normalize "germany" to actual city in place_norm | 7 | Research + manual | Place Accuracy |

### Medium Effort (structural improvements)

| # | Fix | Records | Effort | Dimension |
|---|-----|---------|--------|-----------|
| 8 | Merge multi-script agent_norm pairs sharing same authority_uri | 20+ pairs | Unification script | Agent Identity |
| 9 | Investigate bare "rene" (`rené`) agent_norm (likely parsing bug) | 657 records | Debug parser, reprocess | Agent Identity |
| 10 | Populate `country_name` from `country_code` (MARC country code table) | 2,773 | Lookup table + script | Place Accuracy |
| 11 | Research top publisher authorities currently "unresearched" (prioritize by record count) | 202 authorities | Manual research | Publisher Identity |

### Larger Investments (high value, more work)

| # | Fix | Records | Effort | Dimension |
|---|-----|---------|--------|-----------|
| 12 | Add missing publisher authorities (Aldine, Bomberg, Plantin, Blaeu, Insel, etc.) | ~60+ records | Research + create authority + variants | Publisher Identity |
| 13 | Bridge the 3,710 agents with no authority match | 3,710 rows | Alias expansion or fuzzy matching | Agent Identity |
| 14 | Define collection scope boundary (pre/post 1950) and flag out-of-scope records | ~249 records | Policy decision + tagging | Date Accuracy |
| 15 | Expand Wikidata occupation-to-role inference for 706 missing-role agents | 706 rows | Extend existing inference pipeline | Role Accuracy |
| 16 | Investigate 349 records with no subjects — derive from titles/notes where possible | 349 records | NLP or manual | Subject Coverage |

### Requires Investigation

| Issue | Records | Investigation Path |
|-------|---------|-------------------|
| 38 records with no imprints | 38 | Faitlovitch manuscripts — document as "archival material, imprint N/A" |
| Remaining truly-unknown agent roles after all fixes | TBD | Document as "role unavailable in source MARC" |
| Records with no subjects after investigation | TBD | Document as "unclassifiable from available metadata" |

## 6. Output Artifacts

### Quality Report (`data/qa/data-quality-report.json`)

```json
{
  "generated_at": "ISO 8601",
  "record_count": 2796,
  "tier1": {
    "date_accuracy": {
      "score": 0.997,
      "errors": [
        {"check": "calendar_confusion", "mms_id": "...", "detail": "..."}
      ],
      "total_checked": 2765,
      "error_count": 3
    }
  },
  "tier2": {
    "subject_coverage": {"records_with_subjects_pct": 0.875}
  }
}
```

### Verification Spreadsheet (`data/qa/sampling-verification.csv`)

30-record x 5-field manual verification results.

### Fix Log (`data/qa/fix-log.jsonl`)

Append-only log of every fix applied:
```json
{"timestamp": "...", "fix_id": "role-strip-periods", "mms_ids": ["..."], "field": "role_norm", "old_value": "other", "new_value": "printer", "method": "strip trailing period", "doc": "docs/current/data-quality.md#role-strip-periods"}
```

**Archive-first**: Original values archived to `data/archive/` before any DB modification.

## 7. Integration & Process Documentation

### Reusable Infrastructure

| Component | Location | When It Runs |
|-----------|----------|-------------|
| Automated checks script | `scripts/qa/data_quality_checks.py` | After every ingest, or on-demand |
| Fix scripts (one per fix type) | `scripts/qa/fixes/` | On-demand, each idempotent and re-runnable |
| Process documentation | `docs/current/data-quality.md` | New topic file, added to Topic Registry |

### Process Documentation Structure

Each fix process documented in `docs/current/data-quality.md` with:

1. **Problem**: What's wrong, how many records, how detected
2. **Detection query**: Exact SQL to find affected records
3. **Fix method**: What the script does, step by step
4. **Verification**: How to confirm the fix worked
5. **Re-run**: How to apply after a fresh ingest

### Workflow

```
Ingest (marc-ingest)
  -> Automated checks run
  -> Quality report generated
  -> Errors flagged
  -> User reviews error list
  -> Fix scripts run (with approval for DB changes)
  -> Fix log appended
  -> Re-run checks to verify
```

## 8. Baseline Data Snapshot (2026-04-02)

Summary of current state before any fixes:

| Metric | Value |
|--------|-------|
| Total records | 2,796 |
| Date parse success | 99.8% (5 unparseable) |
| Calendar confusion errors | 2 |
| Place-country mismatches | ~12 |
| Agent authority coverage | 24.2% (3,710 of 4,894 unmatched) |
| Publisher authorities researched | 11% (25 of 227) |
| Unmapped roles | 239 (trailing periods + Hebrew + missing relators) |
| Missing roles | 706 |
| Records without subjects | 349 (12.5%) |
| Records without agents | 145 (5.2%) |
| Records without imprints | 38 (1.4%) |
| Subject scheme inconsistency | 169 ("NLI" vs "nli") |
| Enrichment coverage | 1,943 authorities enriched |
| Wikipedia cache | 1,336 articles |
| Network connections | 32,115 |
