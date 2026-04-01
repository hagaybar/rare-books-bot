# Ingestion Pipeline
> Last verified: 2026-04-01
> Source of truth for: Full MARC XML ingestion pipeline -- 7 phases from parsing through enrichment to final verification

## Overview

The full ingestion pipeline rebuilds `bibliographic.db` from MARC XML through all stages: parsing, normalization, QA audit, authorities, Wikidata/Wikipedia enrichment, and network tables.

**When to use**: After re-exporting MARC XML from Alma, after data corruption, or when alias maps have been updated.

---

## Source Data

**File**: `data/marc_source/rare_books_with_lod.xml`

- Tracked in git (public bibliographic data from the Sourasky Central Library, Tel Aviv University)
- LOD export with `$0` authority URIs for Wikidata enrichment

---

## Running the Pipeline

### Via Slash Command (recommended)

```
/marc-ingest                              # Interactive -- with QA review breakpoints
/marc-ingest --yolo                       # Non-interactive -- auto-approve everything
/marc-ingest --skip-enrichment            # Fast core-only rebuild (~2 min)
```

### Via Babysitter

```
/babysitter:call Execute .a5c/processes/full-ingestion-pipeline.js with inputs from .a5c/processes/full-ingestion-pipeline-inputs.json
```

---

## 7 Phases

### Phase 1: Backup + Core Rebuild (M1 -> M2 -> M3)

1. **Backup**: Create timestamped backup of existing `bibliographic.db`
2. **M1 Parse**: MARC XML -> CanonicalRecord JSONL (`data/canonical/records.jsonl`)
3. **M2 Normalize**: Enrich M1 records with normalized date, place, publisher fields
4. **M3 Index**: Build SQLite database from M2 records (`data/index/bibliographic.db`)

### Phase 2: QA Audit and Normalization Corrections

- Run coverage audit against the newly built database
- Apply normalization corrections if needed
- Review breakpoint (in interactive mode)

### Phase 3: Agent/Publisher Authorities

- Seed publisher authority records
- Build publisher variant mappings

### Phase 4: Wikidata Enrichment

- Fetch Wikidata identifiers using authority URIs from MARC `$0` subfields
- Cache results for subsequent runs

### Phase 5: Wikipedia Enrichment (3 passes)

- Fetch Wikipedia summaries for enriched entities
- Three passes for completeness

### Phase 6: Network Tables

- Build agent-to-record relationship tables
- Generate co-occurrence and network data

### Phase 7: Final Verification

- Run full QA suite
- Verify record counts, coverage statistics
- Confirm no data integrity issues

---

## Safety Measures

- **Auto-backup**: Creates timestamped backup before destructive operations
- **Production DB protection**: `seed_test_db.py` refuses to operate on production DB path
- **MARC XML in git**: Source data is version-controlled and recoverable
- **Incremental enrichment**: Wikidata/Wikipedia caches prevent redundant API calls

---

## Process Documentation

| File | Purpose |
|------|---------|
| `.a5c/processes/full-ingestion-pipeline.process.md` | Process definition |
| `.a5c/processes/full-ingestion-pipeline.diagram.md` | Flow diagram |
| `.a5c/processes/full-ingestion-pipeline.js` | Babysitter process script |
| `.a5c/processes/full-ingestion-pipeline-inputs.json` | Default inputs |

---

## CLI Commands (Individual Steps)

```bash
# M1: Parse MARC XML to JSONL
python -m app.cli parse data/marc_source/rare_books_with_lod.xml

# M2: Normalize (with alias maps)
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json

# M3: Build SQLite index
python -m app.cli index data/canonical/

# Full pipeline (interactive)
/marc-ingest
```

---

## Timing

- **Core-only rebuild** (phases 1-3, `--skip-enrichment`): ~2 minutes
- **Full pipeline** (all 7 phases): depends on Wikidata/Wikipedia API response times and cache status; typically 10-30 minutes for first run, faster with caches
