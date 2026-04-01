# M2 Normalization Specification

**Status:** ✅ COMPLETED

**Implemented in:**
- `scripts/marc/normalize.py` - Core normalization functions
- `scripts/marc/m2_normalize.py` - M1→M2 enrichment CLI
- `scripts/marc/m2_models.py` - Data models

**Tests:** `tests/scripts/marc/test_m2_normalize.py`

**Related:** [Place Normalization Pipeline](../pipelines/place_normalization.md)

---

## Original Specification

### Objective

Create an M2 enrichment step that reads M1 JSONL records and outputs M1 + normalized fields, **without changing any existing M1 keys/values**.

Normalization must be:

- **Deterministic** (same input → same output)
- **Reversible** (raw preserved)
- **Confidence-scored**
- **Method-tagged**
- **No web calls. No LLM.**

### Input

JSONL records in the frozen M1 schema (e.g., MMS 990011964120204146).

Key M1 paths to use:

- `source.control_number.value`
- `imprints[].place.value`
- `imprints[].publisher.value`
- `imprints[].date.value`
- `languages[].value`
- `language_fixed.value`

### Output (Append-Only)

For each record, append an `m2` object:

```json
{
  "m2": {
    "imprints_norm": [
      {
        "place_norm": {...},
        "publisher_norm": {...},
        "date_norm": {...}
      }
    ]
  }
}
```

**Do not rename or remove any M1 fields.**

---

## M2.1 Date Normalization (Per Imprint)

### Field Structure

Inside each `m2.imprints_norm[i]`, create:

```json
{
  "date_norm": {
    "start": <int|null>,
    "end": <int|null>,
    "label": "<string>",
    "confidence": <0..1>,
    "method": "<rule_id>",
    "evidence_paths": ["imprints[i].date.value"],
    "warnings": [ ... ]
  }
}
```

### Deterministic Rules (Apply in This Exact Order)

Given `raw = imprints[i].date.value`:

#### 1. Exact Year

**Pattern:** `^\d{4}$`

**Example:** `"1680"`

**Output:**
- `start = end = year`
- `confidence = 0.99`
- `method = "year_exact"`
- `warnings = []`

#### 2. Bracketed Year

**Pattern:** `^\[(\d{4})\]$`

**Example:** `"[1680]"`

**Output:**
- `start = end = year`
- `confidence = 0.95`
- `method = "year_bracketed"`
- `warnings = []`

#### 3. Circa

**Pattern:** `^c\.?\s*(\d{4})$` OR `^c(\d{4})$`

**Examples:** `"c. 1680"`, `"c1680"`, `"c.1680"`

**Output:**
- `start = year - 5`
- `end = year + 5`
- `confidence = 0.80`
- `method = "year_circa_pm5"`
- `warnings = []`

#### 4. Range

**Pattern:** `^(\d{4})\s*[-/]\s*(\d{4})$`

**Examples:** `"1680-1685"`, `"1680/1685"`

**Output:**
- `start = start_year`
- `end = end_year`
- `confidence = 0.90`
- `method = "year_range"`
- `warnings = []`

#### 5. Year Embedded Anywhere

**Pattern:** Find first `(\d{4})` anywhere in string

**Example:** `"printed in 1680"`

**Output:**
- `start = end = year`
- `confidence = 0.85`
- `method = "year_embedded"`
- `warnings = ["embedded_year_in_complex_string"]`

#### 6. Unparsed

**Fallback:** If no pattern matches

**Output:**
- `start = end = null`
- `confidence = 0.0`
- `method = "unparsed"`
- `warnings = ["date_unparsed"]`

### Validation Example (MMS 990011964120204146)

**Input:** `"[1680]"`

**Expected Output:**
- `start = end = 1680`
- `method = "year_bracketed"`
- `confidence = 0.95`

---

## M2.2 Place Normalization (Per Imprint)

### Field Structure

```json
{
  "place_norm": {
    "value": "<norm_key|null>",
    "display": "<best_display>",
    "confidence": <0..1>,
    "method": "<rule_id>",
    "evidence_paths": ["imprints[i].place.value"],
    "warnings": []
  }
}
```

### Rules (Apply in Order)

Given `raw = imprints[i].place.value`:

#### Step 1: Basic Cleaning

1. Trim whitespace
2. Strip trailing punctuation (`:`, `,`, `;`, `/`)
3. Remove surrounding brackets `[]` if present
4. Unicode normalize (NFKC)

#### Step 2: Generate Normalized Key

```python
norm_key = casefold(raw_clean)
```

**Default Output:**
- `method = "place_casefold_strip"`
- `confidence = 0.80`
- `warnings = []`

#### Step 3: Optional Alias Map (External File)

If `norm_key` is in `place_alias_map.json`, replace with mapped key:

**Output:**
- `method = "place_alias_map"`
- `confidence = 0.95`
- `warnings = []`

### Validation Example (MMS 990011964120204146)

**Input:** `"Paris :"`

**Expected Output:**
- `value = "paris"`
- `display = "Paris"`
- `method = "place_casefold_strip"` (or `"place_alias_map"` if alias file is used)
- `confidence = 0.80` (or `0.95` with alias map)

---

## M2.3 Publisher Normalization (Per Imprint)

### Field Structure

```json
{
  "publisher_norm": {
    "value": "<norm_key|null>",
    "display": "<best_display>",
    "confidence": <0..1>,
    "method": "<rule_id>",
    "evidence_paths": ["imprints[i].publisher.value"],
    "warnings": []
  }
}
```

### Rules

**Same cleaning as place:**
1. Trim whitespace
2. Strip trailing punctuation (`:`, `,`, `;`, `/`)
3. Remove surrounding brackets
4. Unicode normalize (NFKC)

```python
norm_key = casefold(clean)
```

**Default Output:**
- `method = "publisher_casefold_strip"`
- `confidence = 0.80`

**Optional:** `publisher_alias_map.json` mapping
- `method = "publisher_alias_map"`
- `confidence = 0.95`

---

## Implementation Requirements

### Must-Have Behaviors

1. **Handle missing values safely:**
   - `value = null` → norm fields `null` with `method = "missing"` and `confidence = 0`

2. **Preserve imprint order:**
   - `m2.imprints_norm[i]` corresponds to `imprints[i]`

3. **Write unit tests using MMS 990011964120204146:**
   - Date `"[1680]"` → `1680` (bracketed)
   - Place `"Paris :"` → norm key `"paris"`
   - Publisher `"C. Fosset,"` → norm key `"c. fosset"`

### Definition of Done

1. Script `m2_normalize.py` (or equivalent) reads M1 JSONL and outputs JSONL with appended `m2`
2. Deterministic: running twice produces identical output
3. Tests pass for MMS 990011964120204146

---

## Implementation Status

### Core Normalization Functions

**File:** `scripts/marc/normalize.py`

#### `normalize_date(raw: Optional[str], evidence_path: str) -> DateNormalization`

Implements all 6 date normalization rules:

1. ✅ Exact year (`^\d{4}$`) - confidence 0.99
2. ✅ Bracketed year (`^\[(\d{4})\]$`) - confidence 0.95
3. ✅ Circa (`^c\.?\s*(\d{4})$`) - confidence 0.80, ±5 years
4. ✅ Range (`^(\d{4})\s*[-/]\s*(\d{4})$`) - confidence 0.90
5. ✅ Embedded year (first `\d{4}`) - confidence 0.85, warning added
6. ✅ Unparsed fallback - confidence 0.0, warning added

**Returns:** `DateNormalization` Pydantic model with all required fields

#### `normalize_place(raw: Optional[str], evidence_path: str, alias_map: Optional[Dict] = None) -> PlaceNormalization`

Implements place normalization:

1. ✅ Clean: trim, strip punctuation, remove brackets, Unicode NFKC
2. ✅ Casefold to normalized key
3. ✅ Optional alias map lookup
4. ✅ Confidence 0.80 (base) or 0.95 (with alias)
5. ✅ Method tagging: `place_casefold_strip` or `place_alias_map`

**Returns:** `PlaceNormalization` Pydantic model

#### `normalize_publisher(raw: Optional[str], evidence_path: str, alias_map: Optional[Dict] = None) -> PublisherNormalization`

Implements publisher normalization (same rules as place):

1. ✅ Clean: trim, strip punctuation, remove brackets, Unicode NFKC
2. ✅ Casefold to normalized key
3. ✅ Optional alias map lookup
4. ✅ Confidence 0.80 (base) or 0.95 (with alias)
5. ✅ Method tagging: `publisher_casefold_strip` or `publisher_alias_map`

**Returns:** `PublisherNormalization` Pydantic model

#### `enrich_m2(m1_record: dict, place_alias_map: Optional[Dict] = None, publisher_alias_map: Optional[Dict] = None) -> M2Enrichment`

Main enrichment function:

1. ✅ Iterates through M1 `imprints[]`
2. ✅ Normalizes date, place, publisher for each imprint
3. ✅ Preserves imprint order
4. ✅ Returns `M2Enrichment` with `imprints_norm[]`

**Returns:** `M2Enrichment` Pydantic model

### Data Models

**File:** `scripts/marc/m2_models.py`

#### `DateNormalization(BaseModel)`

Fields:
- `start: Optional[int]` - Start year (inclusive)
- `end: Optional[int]` - End year (inclusive)
- `label: str` - Human-readable date label
- `confidence: float` (0.0-1.0)
- `method: str` - Rule ID (e.g., "year_bracketed")
- `evidence_paths: List[str]` - M1 JSON paths
- `warnings: List[str]` - Warnings (e.g., "date_unparsed")

#### `PlaceNormalization(BaseModel)`

Fields:
- `value: Optional[str]` - Normalized key
- `display: str` - Display form
- `confidence: float` (0.0-1.0)
- `method: str` - Rule ID (e.g., "place_alias_map")
- `evidence_paths: List[str]`
- `warnings: List[str]`

#### `PublisherNormalization(BaseModel)`

Fields:
- `value: Optional[str]` - Normalized key
- `display: str` - Display form
- `confidence: float` (0.0-1.0)
- `method: str` - Rule ID
- `evidence_paths: List[str]`
- `warnings: List[str]`

#### `ImprintNormalization(BaseModel)`

Fields:
- `date_norm: DateNormalization`
- `place_norm: PlaceNormalization`
- `publisher_norm: PublisherNormalization`

#### `M2Enrichment(BaseModel)`

Fields:
- `imprints_norm: List[ImprintNormalization]`

### CLI Script

**File:** `scripts/marc/m2_normalize.py`

#### `load_alias_map(alias_path: Optional[Path]) -> Dict[str, str]`

Loads alias map from JSON file (if provided).

#### `process_m1_to_m2(input_path: Path, output_path: Path, place_alias_path: Optional[Path], publisher_alias_path: Optional[Path]) -> dict`

Main processing function:

1. ✅ Reads M1 JSONL line-by-line
2. ✅ Loads alias maps (if provided)
3. ✅ Calls `enrich_m2()` for each record
4. ✅ Appends `m2` object to record (non-destructive)
5. ✅ Writes enriched JSONL
6. ✅ Reports statistics

**Returns:** Statistics dictionary

#### `main()`

CLI entry point with argument parsing:
- `<input_jsonl>` - M1 JSONL input
- `<output_jsonl>` - M1+M2 output
- `--place-alias` (optional) - Place alias map path
- `--publisher-alias` (optional) - Publisher alias map path

### Tests

**File:** `tests/scripts/marc/test_m2_normalize.py`

**Test Coverage:** 20 tests, all passing ✅

#### Date Normalization Tests (11 tests)

1. ✅ `test_exact_year()` - "1680" → 1680-1680, confidence 0.99
2. ✅ `test_bracketed_year()` - "[1680]" → 1680-1680, confidence 0.95
3. ✅ `test_circa_with_dot()` - "c. 1680" → 1675-1685, confidence 0.80
4. ✅ `test_circa_without_dot()` - "c1680" → 1675-1685, confidence 0.80
5. ✅ `test_year_range()` - "1680-1685" → 1680-1685, confidence 0.90
6. ✅ `test_year_embedded()` - "printed 1680" → 1680-1680, confidence 0.85, warning
7. ✅ `test_unparsed()` - "uncertain" → null-null, confidence 0.0, warning
8. ✅ `test_missing_date()` - None → null-null, method "missing"
9. ✅ `test_bracketed_range()` - "[1680-1685]" (falls through to embedded)
10. ✅ `test_slash_range()` - "1680/1685" → 1680-1685, confidence 0.90
11. ✅ `test_deterministic()` - Same input produces same output

#### Place Normalization Tests (3 tests)

1. ✅ `test_place_basic()` - "Paris :" → "paris", confidence 0.80
2. ✅ `test_place_with_alias()` - Uses alias map, confidence 0.95
3. ✅ `test_place_missing()` - None → null, method "missing"

#### Publisher Normalization Tests (2 tests)

1. ✅ `test_publisher_basic()` - "C. Fosset," → "c. fosset", confidence 0.80
2. ✅ `test_publisher_missing()` - None → null, method "missing"

#### Integration Tests (4 tests)

1. ✅ `test_enrich_m2()` - Full M2 enrichment workflow
2. ✅ `test_reference_record_990011964120204146()` - Validates reference record
3. ✅ `test_m1_not_modified()` - Ensures M1 data preserved
4. ✅ `test_imprint_order_preserved()` - Validates parallel arrays

### Example Usage

**Basic enrichment (no alias maps):**
```bash
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl
```

**With place alias map:**
```bash
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  --place-alias data/normalization/place_aliases/place_alias_map.json
```

**Full enrichment (place + publisher aliases):**
```bash
python -m scripts.marc.m2_normalize \
  data/canonical/records.jsonl \
  data/m2/records_m1m2.jsonl \
  --place-alias data/normalization/place_aliases/place_alias_map.json \
  --publisher-alias data/normalization/publisher_aliases/publisher_alias_map.json
```

### Output (Reference Dataset)

**Statistics:**

```
Total records: 2,796
Total imprints: 2,773
Date normalizations: 2,149 (77% of imprints)
  - year_exact: 1,203 (confidence 0.99)
  - year_bracketed: 742 (confidence 0.95)
  - year_circa: 87 (confidence 0.80)
  - year_range: 64 (confidence 0.90)
  - year_embedded: 53 (confidence 0.85)
  - unparsed: 624 (confidence 0.0)

Place normalizations: 2,754 (99% of imprints)
  - place_casefold_strip: 2,371 (confidence 0.80)
  - place_alias_map: 383 (confidence 0.95, when alias file used)

Publisher normalizations: 2,697 (97% of imprints)
  - publisher_casefold_strip: 2,697 (confidence 0.80)
```

### Validation Result

**Reference Record MMS 990011964120204146:**

✅ **ALL TESTS PASSED**

**Date:**
- Input: `"[1680]"`
- Output: `start=1680, end=1680, method="year_bracketed", confidence=0.95`

**Place:**
- Input: `"Paris :"`
- Output: `value="paris", display="Paris", method="place_casefold_strip", confidence=0.80`
- With alias: `value="paris", method="place_alias_map", confidence=0.95`

**Publisher:**
- Input: `"C. Fosset,"`
- Output: `value="c. fosset", display="C. Fosset", method="publisher_casefold_strip", confidence=0.80`

**M1 Preservation:**
- ✅ No M1 fields modified
- ✅ M2 appended as separate object
- ✅ Reversible: M1 can be recovered by deleting `m2` key

---

## Quality Metrics

### Determinism

✅ **VERIFIED**: Running same input produces identical output (validated in tests)

### Reversibility

✅ **VERIFIED**: M1 fields unchanged, M2 appended separately

### Confidence Scoring

✅ **IMPLEMENTED**: All normalizations include confidence scores (0.0-1.0)

### Method Tagging

✅ **IMPLEMENTED**: All normalizations tagged with method ID for traceability

### No External Calls

✅ **VERIFIED**: No LLM or web calls (except optional local alias map files)

---

## Next Steps

1. **Use M2 for querying:** Feed `records_m1m2.jsonl` into M3 SQLite indexing
2. **Improve alias maps:** Generate and integrate publisher alias mappings
3. **Refine date rules:** Add more patterns based on dataset analysis
4. **Monitor confidence:** Track low-confidence normalizations for quality improvement

## See Also

- [Place Normalization Pipeline](../pipelines/place_normalization.md) - Detailed workflow for place alias generation
- [Place Frequency Specification](./place_frequency_spec.md) - Input for alias mapping
- [M3 SQLite Index](../../scripts/marc/m3_schema.sql) - How M2 is indexed for queries
