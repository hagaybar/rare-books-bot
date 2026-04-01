# Place Normalization Pipeline

## Overview

The place normalization pipeline converts raw place names from MARC records into canonical English keys for consistent querying and analysis. This pipeline combines deterministic rule-based processing with LLM-assisted mapping to handle diverse place name variations including:

- Different languages and scripts (Hebrew, Latin, German, etc.)
- Historical place names (e.g., "Lipsiae" → "leipzig")
- Bracketed variants (e.g., "[Paris]" → "paris")
- Punctuation variations (e.g., "Paris :" → "paris")
- Colloquial names (e.g., "'s-Gravenhage" → "the hague")

## Prerequisites

- M1 canonical records generated (`data/canonical/records.jsonl`)
- Place frequency analysis completed (`data/frequency/places_freq.csv`)
- OpenAI API key configured in `.env` file

## Pipeline Stages

### Stage 1: Place Frequency Analysis

**Input:** M1 canonical records (`data/canonical/records.jsonl`)

**Script:** `scripts/marc/build_place_freq.py`

**Purpose:** Extract and normalize place names to identify unique variants and their frequencies

**Process:**
1. Extract places from MARC 264 (ind2='1') or 260 fields
2. Apply basic normalization:
   - Strip whitespace and surrounding brackets
   - Remove trailing punctuation (`:`, `,`, `;`, `/`)
   - Unicode normalize (NFKC)
   - Casefold to lowercase
3. Count frequency of each normalized variant
4. Collect raw examples for human review

**Output:**
- `data/frequency/places_freq.csv` - Place variants with frequencies
- `data/frequency/places_examples.json` - Sample raw strings for each variant

**Usage:**
```bash
python -m scripts.marc.build_place_freq \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/frequency/places_freq.csv \
  data/frequency/places_examples.json
```

**Statistics (reference dataset):**
- 2,780 raw place strings extracted
- 838 unique normalized variants
- Top places: paris (273), london (187), berlin (91), אמשטרדם (85)

### Stage 2: Place Alias Mapping Generation

**Input:** `data/frequency/places_freq.csv`

**Script:** `scripts/normalization/generate_place_alias_map.py`

**Purpose:** Generate canonical English keys for place variants using deterministic rules + LLM

**Process:**

#### 2.1 Auto-Rules (Deterministic, No LLM)

Applied first for efficiency and cost savings:

1. **Already canonical** (confidence: 0.95)
   - Pattern: lowercase ASCII, space-separated words
   - Examples: `london`, `new york`, `tel aviv`
   - Decision: `KEEP` as-is

2. **Bracket stripping** (confidence: 0.90)
   - Pattern: `[place]` where inner text is canonical
   - Examples: `[paris]` → `paris`, `[amsterdam]` → `amsterdam`
   - Decision: `MAP` to stripped form

3. **Placeholder preservation** (confidence: 0.95)
   - Pattern: `s.l.` (sine loco - "without place")
   - Decision: `KEEP` as placeholder

4. **Known ambiguous** (confidence: 0.0)
   - Examples: `frankfurt` (am Main vs. an der Oder), `alexandria` (Egypt vs. US cities)
   - Decision: `AMBIGUOUS` - no mapping applied

#### 2.2 LLM-Assisted Mapping

For variants not handled by auto-rules:

**Primary Model:** `gpt-4o` (or configured model)

**Prompt structure:**
```
Given a normalized place name from bibliographic records, map it to a canonical English key.

Input: אמשטרדם
Count: 85 occurrences

Output structured JSON with:
- canonical: lowercase English key (e.g., "amsterdam")
- decision: KEEP | MAP | AMBIGUOUS | UNKNOWN
- confidence: 0.0-1.0
- notes: brief explanation
```

**Response validation:**
- Pydantic schema enforcement
- Post-processing: casefold, punctuation removal, space collapsing
- Canonical format validation (lowercase ASCII)

**Fallback strategy:**
If primary model returns low confidence (<0.75) or AMBIGUOUS/UNKNOWN:
- Retry with `gpt-4o-mini` fallback model
- Use higher of two confidence scores
- If still uncertain, mark as `UNKNOWN`

#### 2.3 Caching Strategy

All LLM calls are cached to `place_alias_cache.jsonl`:
- One JSON object per line (append-only)
- Includes: place_norm, canonical, decision, confidence, method, count, notes
- Cache checked before API calls (cost savings on re-runs)
- Can be deleted to force full regeneration

**Example cache entry:**
```json
{
  "place_norm": "אמשטרדם",
  "canonical": "amsterdam",
  "decision": "MAP",
  "confidence": 0.99,
  "notes": "Hebrew for Amsterdam",
  "method": "llm_primary",
  "count": 85
}
```

### Stage 3: Production Map Filtering

**Purpose:** Filter decisions into production-ready mapping file

**Criteria:**
- Include `MAP` decisions with confidence ≥ 0.85 (configurable via `--min-conf`)
- Exclude `KEEP`, `AMBIGUOUS`, and `UNKNOWN` decisions
- Post-process canonical keys for consistency

**Output:** `data/normalization/place_aliases/place_alias_map.json`

**Format:**
```json
{
  "אמשטרדם": "amsterdam",
  "[paris]": "paris",
  "lipsiae": "leipzig",
  "'s-gravenhage": "the hague",
  "münchen": "munich"
}
```

**Statistics (reference dataset):**
- 383 mappings in production file (from 838 total variants)
- 45.7% of variants mapped successfully
- Average confidence: 0.92

### Stage 4: Human Review (Optional)

**File:** `data/normalization/place_aliases/place_alias_proposed.csv`

**Purpose:** Complete audit trail for validation and quality control

**Format:**
```csv
place_norm,canonical,decision,confidence,method,count,notes
paris,paris,KEEP,0.9,auto_rule,273,already canonical
אמשטרדם,amsterdam,MAP,0.99,llm_primary,85,Hebrew for Amsterdam
frankfurt,frankfurt,AMBIGUOUS,0.0,auto_rule,23,multiple cities possible
```

**Review workflow:**
1. Sort by frequency (high-frequency errors have biggest impact)
2. Validate `MAP` decisions with confidence <0.90
3. Check `UNKNOWN` and `AMBIGUOUS` cases for patterns
4. Update auto-rules or LLM prompts as needed
5. Regenerate with improvements

## Integration with M2 Normalization

The place alias map is used during M2 enrichment:

**Script:** `scripts/marc/m2_normalize.py`

**Function:** `normalize_place(raw, evidence_path, alias_map)`

**Process:**
1. Clean raw place string (trim, remove brackets, strip punctuation)
2. Casefold to lowercase
3. Look up in alias map
4. Return normalized value with confidence and method

**Without alias map:**
- Confidence: 0.80
- Method: `place_casefold_strip`
- Value: Casefolded input (may not be canonical)

**With alias map:**
- Confidence: 0.95
- Method: `place_alias_map`
- Value: Canonical English key from map

**Example:**
```python
# Input: "Paris :"
# After cleaning: "Paris"
# After casefold: "paris"
# Alias lookup: "paris" (KEEP, no mapping needed)
# Result: PlaceNormalization(value="paris", confidence=0.95, method="place_alias_map")

# Input: "אמשטרדם"
# After cleaning: "אמשטרדם"
# After casefold: "אמשטרדם"
# Alias lookup: "amsterdam"
# Result: PlaceNormalization(value="amsterdam", confidence=0.95, method="place_alias_map")
```

## Usage Instructions

### Generating Place Alias Map

**Full generation (all variants):**
```bash
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json \
  --cache data/normalization/place_aliases/place_alias_cache.jsonl \
  --proposed data/normalization/place_aliases/place_alias_proposed.csv \
  --min-conf 0.85
```

**Incremental update (uses cache):**
```bash
# Add new places to places_freq.csv
# Run same command - only new places will be processed via LLM
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json \
  --cache data/normalization/place_aliases/place_alias_cache.jsonl \
  --proposed data/normalization/place_aliases/place_alias_proposed.csv
```

**Force full regeneration (ignore cache):**
```bash
# Delete cache file
rm data/normalization/place_aliases/place_alias_cache.jsonl

# Run generation
python scripts/normalization/generate_place_alias_map.py \
  --input data/frequency/places_freq.csv \
  --output data/normalization/place_aliases/place_alias_map.json \
  --cache data/normalization/place_aliases/place_alias_cache.jsonl \
  --proposed data/normalization/place_aliases/place_alias_proposed.csv
```

### Configuration Options

**`--min-conf` (default: 0.85)**
- Minimum confidence threshold for production map
- Lower values include more mappings (higher recall, lower precision)
- Higher values are more conservative (lower recall, higher precision)

**`--primary-model` (default: gpt-4o)**
- OpenAI model for primary mapping
- Options: gpt-4o, gpt-4-turbo, gpt-4

**`--fallback-model` (default: gpt-4o-mini)**
- Cheaper model for uncertain cases
- Only used if primary model confidence <0.75 or returns AMBIGUOUS/UNKNOWN

**`--max-places` (default: unlimited)**
- Limit number of places to process (for testing)
- Useful for cost estimation: `--max-places 100`

### Cost Estimation

**Reference dataset (838 unique places):**
- Auto-rules handled: ~150 places (18%)
- LLM calls needed: ~688 places (82%)
- Primary model calls: ~688 @ $0.005/call = ~$3.44
- Fallback model calls: ~50 @ $0.0003/call = ~$0.015
- **Total estimated cost: ~$3.50**

**Incremental updates:**
- Only new places require LLM calls
- Cache prevents redundant API requests
- Typical cost per new place: $0.005-0.008

## Quality Metrics

**Reference Dataset Results:**

| Metric | Value |
|--------|-------|
| Total unique variants | 838 |
| Auto-rule coverage | 18% (150 places) |
| LLM processing needed | 82% (688 places) |
| MAP decisions (production) | 383 (45.7%) |
| KEEP decisions | 142 (16.9%) |
| AMBIGUOUS | 23 (2.7%) |
| UNKNOWN | 290 (34.6%) |
| Average MAP confidence | 0.92 |
| High confidence (≥0.90) | 72% of MAP decisions |

## Troubleshooting

### Issue: LLM returns non-canonical keys

**Symptom:** Canonical keys contain uppercase, punctuation, or non-ASCII

**Solution:** Post-processing normalizes keys automatically, but check LLM prompt

### Issue: Too many UNKNOWN decisions

**Symptom:** High percentage of places not mapped

**Possible causes:**
- Input data quality (malformed place names)
- LLM prompt needs refinement
- Model temperature too low (overly conservative)

**Solution:** Review `place_alias_proposed.csv` for patterns, adjust prompt or model

### Issue: Ambiguous places mapped incorrectly

**Symptom:** Frankfurt am Main conflated with Frankfurt an der Oder

**Solution:** Add to `ALWAYS_AMBIGUOUS` set in script, regenerate

### Issue: High API costs

**Symptom:** Unexpected charges for place mapping

**Solution:**
- Use `--max-places` flag for testing
- Ensure cache file is being used (check for LLM calls on re-runs)
- Consider using cheaper fallback model as primary: `--primary-model gpt-4o-mini`

## File Locations

```
data/
├── frequency/
│   ├── places_freq.csv              # Input: Place frequencies from M1
│   └── places_examples.json         # Raw examples for each variant
└── normalization/
    └── place_aliases/
        ├── place_alias_map.json     # Production mapping (tracked in git)
        ├── place_alias_cache.jsonl  # LLM cache (gitignored)
        └── place_alias_proposed.csv # Human review file (gitignored)
```

## See Also

- [M2 Normalization Specification](../specs/m2_normalization_spec.md) - Overall M2 enrichment process
- [Place Frequency Specification](../specs/place_frequency_spec.md) - Stage 1 frequency analysis
- [Place Alias Mapping Utility](../utilities/place_alias_mapping.md) - Detailed script documentation
