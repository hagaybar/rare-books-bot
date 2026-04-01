# Normalization Pipeline
> Last verified: 2026-04-01
> Source of truth for: M2 normalization layer -- date, place, and publisher normalization rules, alias map generation, confidence scoring, and data models

## Overview

The M2 normalization layer enriches M1 canonical records (parsed MARC XML) with normalized fields for querying and analysis. Normalization is:

- **Deterministic** -- same input always produces same output
- **Reversible** -- raw MARC values are preserved alongside normalized values
- **Confidence-scored** -- every normalized value has a 0.0-1.0 confidence score
- **Method-tagged** -- every normalized value records which rule produced it
- **No web calls, no LLM** -- the M2 step itself is purely rule-based (LLM is used only for one-time alias map generation, not at normalization time)

### Key Principle

Raw MARC values are never destroyed. The M2 enrichment appends an `m2` object to each record; removing the `m2` key recovers the original M1 record exactly.

## Implementation Files

| File | Purpose |
|------|---------|
| `scripts/marc/normalize.py` | Core normalization functions (date, place, publisher) |
| `scripts/marc/m2_normalize.py` | M1-to-M2 enrichment CLI |
| `scripts/marc/m2_models.py` | Pydantic data models |
| `tests/scripts/marc/test_m2_normalize.py` | 20 unit/integration tests |

## M2 Output Structure

For each record, an `m2` object is appended:

```json
{
  "m2": {
    "imprints_norm": [
      {
        "place_norm": { "value": "paris", "display": "Paris", "confidence": 0.95, "method": "place_alias_map", "evidence_paths": ["imprints[0].place.value"], "warnings": [] },
        "publisher_norm": { "value": "c. fosset", "display": "C. Fosset", "confidence": 0.80, "method": "publisher_casefold_strip", "evidence_paths": ["imprints[0].publisher.value"], "warnings": [] },
        "date_norm": { "start": 1680, "end": 1680, "label": "1680", "confidence": 0.95, "method": "year_bracketed", "evidence_paths": ["imprints[0].date.value"], "warnings": [] }
      }
    ]
  }
}
```

Imprint order is preserved: `m2.imprints_norm[i]` corresponds to `imprints[i]`.

---

## Date Normalization

### Input

Raw date strings from M1 imprints (e.g., `"[1680]"`, `"c. 1650"`, `"1500-1599"`).

### Function

`normalize_date(raw: Optional[str], evidence_path: str) -> DateNormalization`

### Deterministic Rules (applied in this exact order)

| # | Name | Pattern | Example | start | end | Confidence | Method |
|---|------|---------|---------|-------|-----|------------|--------|
| 1 | Exact year | `^\d{4}$` | `"1680"` | 1680 | 1680 | 0.99 | `year_exact` |
| 2 | Bracketed year | `^\[(\d{4})\]$` | `"[1680]"` | 1680 | 1680 | 0.95 | `year_bracketed` |
| 3 | Circa | `^c\.?\s*(\d{4})$` | `"c. 1650"` | 1645 | 1655 | 0.80 | `year_circa_pm5` |
| 4 | Range | `^(\d{4})\s*[-/]\s*(\d{4})$` | `"1680-1685"` | 1680 | 1685 | 0.90 | `year_range` |
| 5 | Embedded year | First `\d{4}` anywhere | `"printed 1680"` | 1680 | 1680 | 0.85 | `year_embedded` |
| 6 | Unparsed | No pattern matches | `"uncertain"` | null | null | 0.0 | `unparsed` |

Rules 5 and 6 add warnings (`embedded_year_in_complex_string` and `date_unparsed` respectively).

Missing values (raw is `None`) produce `start=null, end=null, method="missing", confidence=0`.

### Reference Dataset Statistics

```
Total imprints: 2,773
  year_exact:     1,203 (confidence 0.99)
  year_bracketed:   742 (confidence 0.95)
  year_circa:        87 (confidence 0.80)
  year_range:        64 (confidence 0.90)
  year_embedded:     53 (confidence 0.85)
  unparsed:         624 (confidence 0.0)
```

---

## Place Normalization

### Input

Raw place strings from M1 imprints (e.g., `"Paris :"`, `"[Berlin]"`).

### Function

`normalize_place(raw: Optional[str], evidence_path: str, alias_map: Optional[Dict] = None) -> PlaceNormalization`

### Process

1. **Clean**: trim whitespace, strip trailing punctuation (`:` `,` `;` `/`), remove surrounding brackets `[]`, Unicode normalize (NFKC)
2. **Casefold** to lowercase normalized key
3. **Alias map lookup** (if provided): look up casefolded key in `place_alias_map.json`

### Confidence and Methods

| Condition | Confidence | Method |
|-----------|------------|--------|
| Alias map match | 0.95 | `place_alias_map` |
| No alias map or no match | 0.80 | `place_casefold_strip` |
| Unmatched with alias map present | tagged `missing` | `missing` |
| Raw value is `None` | 0.0 | `missing` |

### Production Methods

In the current production system, only two methods are used for places: `place_alias_map` (matched) and `missing` (unmatched). The `base_clean`/`place_casefold_strip` method is not used in production because all places go through alias map lookup.

### Mapping File

**Location**: `data/normalization/place_aliases/place_alias_map.json` (tracked in git)

**Format**:
```json
{
  "place_alias_map.json": "canonical english key",
  "lipsiae": "leipzig",
  "'s-gravenhage": "the hague",
  "münchen": "munich"
}
```

**Current statistics**: 383 mappings from 838 unique place variants (45.7% coverage, average confidence 0.92).

---

## Publisher Normalization

### Input

Raw publisher strings from M1 imprints (e.g., `"C. Fosset,"`, `"Elsevier:"`).

### Function

`normalize_publisher(raw: Optional[str], evidence_path: str, alias_map: Optional[Dict] = None) -> PublisherNormalization`

### Process

Same cleaning pipeline as place normalization:
1. Trim whitespace, strip trailing punctuation, remove brackets, Unicode NFKC
2. Casefold to normalized key
3. Optional alias map lookup

### Confidence and Methods

| Condition | Confidence | Method |
|-----------|------------|--------|
| Alias map match | 0.95 | `publisher_alias_map` |
| No alias map or no match | 0.80 | `publisher_casefold_strip` |
| Raw value is `None` | 0.0 | `missing` |

---

## Place Alias Map Generation

The place alias map is generated once (or incrementally) using LLM-assisted normalization, then used at M2 normalization time without any LLM calls.

### Pipeline Stages

#### Stage 1: Place Frequency Analysis

**Script**: `scripts/marc/build_place_freq.py`

Extracts places from MARC 264 (ind2='1') or 260 fields, applies basic normalization (strip, casefold, Unicode NFKC), and counts frequencies.

```bash
python -m scripts.marc.build_place_freq \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/frequency/places_freq.csv \
  data/frequency/places_examples.json
```

Reference: 2,780 raw strings yielding 838 unique normalized variants.

#### Stage 2: Alias Mapping Generation

**Script**: `scripts/normalization/generate_place_alias_map.py`

Combines deterministic auto-rules with LLM-assisted mapping:

**Auto-rules (no LLM needed)**:

| Rule | Pattern | Decision | Confidence |
|------|---------|----------|------------|
| Already canonical | Lowercase ASCII, space-separated | KEEP | 0.95 |
| Bracket stripping | `[canonical_key]` | MAP | 0.90 |
| Placeholder | `s.l.` (sine loco) | KEEP | 0.95 |
| Known ambiguous | `frankfurt`, `alexandria`, etc. | AMBIGUOUS | 0.0 |

**LLM-assisted mapping** (for remaining variants):
- Model: gpt-4o (default), with gpt-4o-mini fallback
- Uses OpenAI Structured Responses API with Pydantic schemas
- Decisions: KEEP, MAP, AMBIGUOUS, UNKNOWN
- Cached in `place_alias_cache.jsonl` (append-only JSONL)

**Fallback strategy**: If primary model returns confidence < 0.75 or AMBIGUOUS/UNKNOWN, retry with fallback model and use the higher confidence score.

**Post-processing**: All canonical keys are validated (lowercase ASCII, spaces only) and rejected if validation fails.

#### Stage 3: Production Map Filtering

Only MAP decisions with confidence >= 0.85 (configurable via `--min-conf`) are included in the production map.

#### Stage 4: Human Review (Optional)

All decisions are written to `place_alias_proposed.csv` for audit. Review workflow: sort by frequency, validate uncertain mappings (confidence < 0.90), check UNKNOWN patterns.

### Full Generation Command

```bash
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json \
  --cache data/normalization/place_aliases/place_alias_cache.jsonl \
  --proposed data/normalization/place_aliases/place_alias_proposed.csv \
  --min-conf 0.85
```

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--input` | (required) | Place frequency CSV path |
| `--output` | (required) | Production mapping JSON path |
| `--cache` | (required) | LLM cache JSONL path |
| `--proposed` | (required) | Human review CSV path |
| `--min-conf` | 0.85 | Minimum confidence for production map |
| `--primary-model` | gpt-4o | OpenAI model for primary mapping |
| `--fallback-model` | gpt-4o-mini | Cheaper model for uncertain cases |
| `--max-places` | unlimited | Limit places to process (for testing) |

### Cost Estimation

Reference dataset (838 places): ~$3.50 total. Auto-rules handle ~18% for free, LLM processes the remaining ~82%. Incremental updates use cache (95%+ hit rate), costing ~$0.005-0.008 per new place.

---

## Key Files

```
data/normalization/place_aliases/
  place_alias_map.json         # Production mapping (tracked in git)
  place_alias_cache.jsonl      # LLM cache (gitignored)
  place_alias_proposed.csv     # Human review file (gitignored)

data/frequency/
  places_freq.csv              # Place frequencies from M1
  places_examples.json         # Raw examples for each variant
```

---

## Data Models

All models are Pydantic BaseModels in `scripts/marc/m2_models.py`:

| Model | Key Fields |
|-------|------------|
| `DateNormalization` | start, end, label, confidence, method, evidence_paths, warnings |
| `PlaceNormalization` | value, display, confidence, method, evidence_paths, warnings |
| `PublisherNormalization` | value, display, confidence, method, evidence_paths, warnings |
| `ImprintNormalization` | date_norm, place_norm, publisher_norm |
| `M2Enrichment` | imprints_norm (list of ImprintNormalization) |

---

## CLI Usage

```bash
# Basic enrichment (no alias maps)
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl

# With place alias map (recommended)
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  --place-alias data/normalization/place_aliases/place_alias_map.json

# Full enrichment (place + publisher aliases)
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  --place-alias data/normalization/place_aliases/place_alias_map.json \
  --publisher-alias data/normalization/publisher_aliases/publisher_alias_map.json
```

---

## Testing

```bash
# Run all M2 normalization tests (20 tests)
poetry run python -m pytest tests/scripts/marc/test_m2_normalize.py -v
```

Test coverage:
- 11 date normalization tests (all 6 rules + edge cases + determinism)
- 3 place normalization tests (basic, alias map, missing)
- 2 publisher normalization tests (basic, missing)
- 4 integration tests (full enrichment, reference record, M1 preservation, imprint order)

### Reference Record Validation

MMS 990011964120204146:
- Date `"[1680]"` -> `start=1680, end=1680, method="year_bracketed", confidence=0.95`
- Place `"Paris :"` -> `value="paris", method="place_casefold_strip", confidence=0.80` (or `"place_alias_map"`, confidence=0.95 with alias)
- Publisher `"C. Fosset,"` -> `value="c. fosset", method="publisher_casefold_strip", confidence=0.80`

---

## Troubleshooting

### Too many UNKNOWN place decisions
Review `place_alias_proposed.csv` for patterns. Add patterns to auto-rules or adjust LLM prompt. Use `--primary-model gpt-4o` for better quality.

### Ambiguous places mapped incorrectly
Add to the `ALWAYS_AMBIGUOUS` set in the generation script. Delete affected cache entries and regenerate.

### High API costs for alias generation
Use `--max-places 100` for testing. Ensure cache file exists (prevents redundant API calls). Consider `--primary-model gpt-4o-mini` (10x cheaper, slightly lower quality).

### LLM returns non-canonical keys
Post-processing normalizes automatically, but check Pydantic validation is enabled. Verify canonical format: lowercase ASCII, space-separated words.
