# Rare Books Bot - MARC XML Bibliographic Discovery System

A deterministic, evidence-based bibliographic discovery system for rare books where MARC XML is the source of truth.

## Overview

This project processes MARC XML records through a multi-stage pipeline (M1 → M2 → M3 → M4) to enable fielded queries and analysis of rare book collections. All normalization is reversible, confidence-scored, and traceable back to source MARC fields.

**Primary Success Criterion:** Given an inventory query, deterministically produce the correct CandidateSet (record IDs) with evidence showing which MARC fields/values caused inclusion.

## Quick Start

```bash
# Install dependencies
poetry install

# Parse MARC XML to canonical format (M1)
python -m scripts.marc.parse_xml \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/canonical/records.jsonl

# Build place frequency table (for normalization)
python -m scripts.marc.build_place_freq \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/frequency/places_freq.csv \
  data/frequency/places_examples.json

# Generate place alias map (one-time, LLM-assisted)
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json

# Enrich with M2 normalization
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json

# Build M3 SQLite index
python -m scripts.marc.m3_index \
  data/m2/records_m1m2.jsonl \
  data/index/bibliographic.db \
  scripts/marc/m3_schema.sql

# Query the index (M4 - in development)
python -m app.cli query "Books printed in Paris in the 17th century"
```

## Project Structure

```
rare-books-bot/
├── CLAUDE.md                    # Claude Code guidance
├── README.md                    # This file
├── plan.mf                      # Milestone roadmap
│
├── docs/                        # Documentation
│   ├── specs/                   # Completed specifications
│   │   ├── place_frequency_spec.md
│   │   └── m2_normalization_spec.md
│   ├── pipelines/               # Pipeline documentation
│   │   └── place_normalization.md
│   └── utilities/               # Utility documentation
│       └── place_alias_mapping.md
│
├── scripts/                     # Source code
│   ├── marc/                    # MARC XML processing
│   │   ├── parse.py            # M1: MARC XML → canonical JSONL
│   │   ├── models.py           # M1 data models
│   │   ├── normalize.py        # M2: Normalization functions
│   │   ├── m2_normalize.py     # M2: Enrichment CLI
│   │   ├── m2_models.py        # M2 data models
│   │   ├── build_place_freq.py # Place frequency analysis
│   │   ├── m3_schema.sql       # M3: SQLite schema
│   │   ├── m3_index.py         # M3: Indexing script
│   │   └── m3_query.py         # M3: Query functions
│   ├── normalization/           # Normalization utilities
│   │   └── generate_place_alias_map.py  # Place alias generation
│   └── utils/                   # Shared utilities
│
├── tests/                       # Test suite
│   └── scripts/                 # Mirrors scripts/ structure
│       ├── marc/
│       │   ├── test_parse.py
│       │   ├── test_m2_normalize.py
│       │   ├── test_place_freq.py
│       │   └── test_m3_index.py
│       └── ...
│
├── data/                        # Data artifacts (gitignored)
│   ├── marc_source/             # Raw MARC XML files
│   ├── canonical/               # M1: Canonical JSONL records
│   │   ├── records.jsonl
│   │   └── extraction_report.json
│   ├── frequency/               # Frequency analysis outputs
│   │   ├── places_freq.csv
│   │   └── places_examples.json
│   ├── normalization/           # Normalization artifacts
│   │   ├── place_aliases/
│   │   │   ├── place_alias_map.json    # (tracked in git)
│   │   │   ├── place_alias_cache.jsonl # (gitignored)
│   │   │   └── place_alias_proposed.csv # (gitignored)
│   │   └── test_results/        # Archived experiments
│   ├── m2/                      # M2: Enriched records
│   │   └── records_m1m2.jsonl
│   ├── index/                   # M3: SQLite database
│   │   └── bibliographic.db
│   └── runs/                    # M4: Query artifacts (per run_id)
│
├── app/                         # CLI interface
│   └── cli.py
│
└── configs/                     # Configuration files
```

## Data Pipeline

### M1: MARC XML Parsing

**Purpose:** Extract bibliographic records from MARC XML into canonical JSON format

**Input:** Raw MARC XML files

**Output:** `data/canonical/records.jsonl` (one JSON record per line)

**Key features:**
- Preserves all raw MARC values
- Occurrence-indexed provenance (e.g., `500[0]$a`, `500[1]$a`)
- Extracts: title, imprints, agents, subjects, languages, notes
- Reference record: MMS 990011964120204146

```bash
python -m scripts.marc.parse_xml \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/canonical/records.jsonl
```

### M2: Normalization & Enrichment

**Purpose:** Add normalized fields for querying without modifying M1 data

**Input:** M1 canonical records

**Output:** `data/m2/records_m1m2.jsonl` (M1 + `m2` object appended)

**Normalization types:**
- **Dates:** 6 deterministic rules (exact, bracketed, circa, range, embedded, unparsed)
- **Places:** Cleaning + optional alias map lookup (0.80-0.95 confidence)
- **Publishers:** Same as places

**Key features:**
- Deterministic (same input → same output)
- Reversible (M1 preserved)
- Confidence-scored (0.0-1.0)
- Method-tagged (e.g., `year_bracketed`, `place_alias_map`)
- No LLM or web calls in core normalization

```bash
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  data/normalization/place_aliases/place_alias_map.json
```

### M3: SQLite Indexing

**Purpose:** Build queryable database with M1 raw + M2 normalized fields

**Input:** M2 enriched records

**Output:** `data/index/bibliographic.db` (SQLite database)

**Schema:**
- Tables: records, titles, imprints, subjects, agents, languages, notes
- FTS5 full-text search on titles and subjects
- Indexes on date ranges, places, publishers

**Statistics (reference dataset):**
- 2,796 records
- 4,791 titles
- 2,773 imprints with M2 normalization
- 5,415 subjects
- 4,708 agents

```bash
python -m scripts.marc.m3_index \
  data/m2/records_m1m2.jsonl \
  data/index/bibliographic.db \
  scripts/marc/m3_schema.sql
```

### M4: Query Planning & Execution (In Development)

**Purpose:** Convert natural language queries to SQL with CandidateSet + Evidence

**Input:** Natural language query

**Output:**
- QueryPlan (structured JSON)
- SQL query
- CandidateSet (matching record IDs)
- Evidence (MARC fields that caused inclusion)

**Example queries:**
- "All books published by X between 1500 and 1599"
- "All books printed in Paris in the 16th century"
- "Books on topic X" (subject headings)

```bash
python -m app.cli query "Books printed in Paris in the 17th century"
```

## Documentation

### Specifications (Completed Features)

- **[Place Frequency Analysis](docs/specs/place_frequency_spec.md)** - Extract and count place name variants
- **[M2 Normalization](docs/specs/m2_normalization_spec.md)** - Date, place, publisher normalization rules

### Pipeline Guides

- **[Place Normalization Pipeline](docs/pipelines/place_normalization.md)** - Complete workflow from frequency analysis to alias mapping

### Utilities

- **[Place Alias Mapping](docs/utilities/place_alias_mapping.md)** - Generate canonical place name mappings using LLM

## Testing

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/scripts/marc/test_m2_normalize.py

# Run with coverage
pytest --cov=scripts --cov-report=html

# Run M3 tests (requires test data)
pytest tests/scripts/marc/test_m3_index.py
```

**Test Coverage:**
- M1 parsing: 20+ tests
- M2 normalization: 20+ tests
- Place frequency: 11 tests
- M3 indexing: 15 tests

## Development Workflow

### Adding New Features

1. **Read specifications:** Check `docs/specs/` for existing specs
2. **Plan implementation:** Use `EnterPlanMode` for non-trivial features
3. **Write tests first:** Create tests in `tests/scripts/`
4. **Implement feature:** Add code in `scripts/`
5. **Update documentation:** Add/update relevant docs
6. **Commit with evidence:** Include test results in commit message

### Code Quality Standards

- **Single-purpose functions** (<50 lines)
- **Type hints** everywhere
- **Comprehensive docstrings**
- **Unit tests** for all normalization logic
- **No LLM/web calls** in core processing (except utility scripts)

### Skills Available

This project has specialized Claude Code skills:
- **python-dev-expert** - Best practices for Python development
- **git-expert** - Git workflow management

## Key Principles

### Answer Contract (Non-Negotiable)

Every query response must include:
1. **QueryPlan** (structured JSON)
2. **CandidateSet** (record IDs)
3. **Evidence** (MARC fields that matched)
4. **Normalized mapping** (raw → normalized with confidence)

**No narrative before CandidateSet exists.**

### Data Model Rules

- **Preserve raw MARC values always** (no destructive normalization)
- **Normalized fields are reversible** (store raw alongside normalized)
- **If uncertain:** store `null`/range + explicit reason (never invent data)

### Deterministic Processing

- Same input file → identical output
- All normalization rules are explicit and testable
- No randomness (LLM only used in utility scripts, not core pipeline)

## Current Status

**Completed:**
- ✅ M1: MARC XML parsing with occurrence indexing
- ✅ M2: Deterministic normalization (date, place, publisher)
- ✅ M3: SQLite indexing with FTS
- ✅ Place alias mapping utility (LLM-assisted)

**In Progress:**
- 🚧 M4: Query planning and execution
- 🚧 Additional normalization types (agents, subjects)

**Planned:**
- 📋 M5: Complex question answering over CandidateSet
- 📋 Web enrichment with caching
- 📋 Publisher alias mapping

## Contributing

See [CLAUDE.md](CLAUDE.md) for detailed guidance on working with this codebase.

## License

[Add license information]

## Contact

[Add contact information]
