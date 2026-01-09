# Place Frequency Analysis Specification

**Status:** ✅ COMPLETED

**Implemented in:** `scripts/marc/build_place_freq.py`

**Tests:** `tests/scripts/marc/test_place_freq.py`

**Related:** [Place Normalization Pipeline](../pipelines/place_normalization.md)

---

## Original Specification

### Task

Build Place Frequency Table From MARC XML (for alias mapping)

### Goal

Given a MARC XML file (e.g. `BIBLIOGRAPHIC_39080891200004146_39080891180004146_1.xml`), produce:

1. **places_freq.csv**
   - Columns: `place_norm`, `count`

2. **places_examples.json** (Optional, recommended)
   - Dictionary: `place_norm -> {count, examples[]}` where examples are raw strings seen in the file

This output will be used as input for an AI-assisted proposal of a place alias map, then validated by a human expert.

### Hard Rules

- **Deterministic:** Same input file → identical output
- **No LLM, no web**
- **No aliasing / authority work:** Only basic normalization/cleaning
- **Keep raw values** for examples, but counting is done on the cleaned key (`place_norm`)

### What Counts as "Imprint Place"

Extract place from these MARC fields, in this priority:

1. **264 with indicator2 = 1** (publication) → subfield `$a`
2. **If no qualifying 264, use 260** → subfield `$a`
3. If multiple 264s qualify, include them all (rare but possible)
4. If multiple 260 fields exist, include them all
5. Ignore other place-like fields (e.g., 752) for this task

### Step-by-Step Instructions

#### Step 1: Parse MARC XML

- Use a MARC XML parser (Python: `pymarc` supports MARCXML)
- Iterate record-by-record
- Extract record ID for logging: control number from 001 (MMS) if available

#### Step 2: Extract Candidate Place Strings (Raw)

For each record:

1. Look for 264 fields:
   - Only include a 264 if `ind2 == '1'` (publication)
   - For each qualifying 264, collect all `$a` subfields as raw strings

2. If you collected zero raw places from qualifying 264 fields:
   - Collect raw strings from all `260$a`

3. Store each raw place string exactly as found (including punctuation) for the examples file

#### Step 3: Normalize Each Place into `place_norm` (Basic Cleaning Only)

Implement a deterministic function:

```python
place_norm = normalize_place(raw_place: str) -> str | None
```

**Rules (apply in order):**

1. If raw is null/empty after stripping → return `None`
2. `s = s.strip()`
3. Strip surrounding brackets if the entire string is bracketed:
   - `"[Paris :]"` → `"Paris :"`
4. Remove trailing punctuation characters repeatedly (while last char in set):
   - Punctuation set: `:`, `,`, `;`, `/`
   - Example: `"Paris :"` → `"Paris"`
   - Example: `"Paris :,"` → `"Paris"`
5. Unicode normalize: **NFKC**
6. Collapse internal whitespace to single spaces
7. Casefold/lowercase: `s = s.casefold()`
8. Return `s` (final norm key)

**Do NOT:**
- Remove diacritics
- Translate scripts
- Expand abbreviations

#### Step 4: Count Frequencies

For each raw place extracted:

1. Compute `place_norm`
2. If `place_norm is None`: increment `missing_place_count`
3. Else: increment `counter[place_norm] += 1`
4. Also keep a small set/list of up to N examples per `place_norm` (e.g., N=5), preserving first-seen order:
   - `examples[place_norm] = [raw1, raw2, ...]` (unique examples only)

#### Step 5: Output `places_freq.csv`

- Sort by count desc, then place_norm asc (stable deterministic ordering)
- Write CSV with header:

```csv
place_norm,count
paris,123
venetiis,98
...
```

#### Step 6: Output `places_examples.json` (Recommended)

Write JSON like:

```json
{
  "paris": { "count": 123, "examples": ["Paris :", "Paris"] },
  "venetiis": { "count": 98, "examples": ["Venetiis :", "Venetiis"] }
}
```

This file helps later review (humans can see what got grouped).

#### Step 7: Produce a Small Run Report (stdout or log file)

Include:

- Input filename
- Number of MARC records processed
- Number of raw place strings extracted
- Number of unique `place_norm`
- Count of records with no place found
- Top 20 places (norm + count)

### Validation Check Using MMS 990011964120204146

Given MARC:

```
260 $a Paris :
```

Expected:

- Raw example includes `"Paris :"`
- `place_norm == "paris"`
- Frequency count increments accordingly

### Definition of Done

Running the script on the MARC XML produces:

1. `places_freq.csv` (sorted deterministically)
2. `places_examples.json` (optional but recommended)
3. A run report with counts and top entries
4. No schema changes, no aliasing, no external calls

---

## Implementation Status

### Implementation

**File:** `scripts/marc/build_place_freq.py`

**Key Functions:**

1. `normalize_place_basic(raw: Optional[str]) -> Optional[str]`
   - Implements normalization rules exactly as specified
   - Returns `None` for empty/invalid inputs
   - Deterministic: same input always produces same output

2. `extract_places_from_record(record: pymarc.Record) -> List[str]`
   - Extracts places following priority rules:
     - 264 with ind2='1' first
     - Fallback to 260 if no qualifying 264
   - Returns list of raw place strings

3. `build_place_frequency(marc_xml_path: Path, max_examples: int = 5) -> Tuple`
   - Parses MARC XML using `pymarc.parse_xml_to_array()`
   - Builds frequency counter and examples dictionary
   - Returns `(frequency, examples, stats)`

4. `write_frequency_csv(frequency: Counter, output_path: Path)`
   - Sorts by count desc, place_norm asc (deterministic)
   - Writes CSV with header

5. `write_examples_json(frequency: Counter, examples: Dict, output_path: Path)`
   - Writes examples dictionary to JSON
   - Includes both count and examples array

6. `print_report(marc_xml_path: Path, frequency: Counter, stats: Dict, top_n: int = 20)`
   - Prints summary statistics
   - Shows top N places

### Tests

**File:** `tests/scripts/marc/test_place_freq.py`

**Test Coverage:**

1. `test_normalize_paris_with_colon()` - Validates reference record normalization
2. `test_normalize_paris_with_comma()` - Trailing comma removal
3. `test_normalize_bracketed_place()` - Bracket stripping
4. `test_normalize_with_multiple_trailing_punct()` - Multiple punctuation characters
5. `test_normalize_empty_string()` - Empty/None handling
6. `test_normalize_only_brackets()` - Empty brackets
7. `test_normalize_unicode()` - Hebrew and other scripts preserved
8. `test_normalize_with_whitespace()` - Whitespace collapsing
9. `test_normalize_latin_place()` - Latin place names
10. `test_deterministic()` - Validates determinism (same input → same output)
11. `test_casefold()` - Case normalization

**Test Result:** ✅ All 11 tests passing

### Example Usage

```bash
python -m scripts.marc.build_place_freq \
  data/marc_source/BIBLIOGRAPHIC_*.xml \
  data/frequency/places_freq.csv \
  data/frequency/places_examples.json
```

### Output (Reference Dataset)

**Statistics:**

```
Total records processed: 2,796
Records with places: 2,780
Records without places: 16
Total raw place strings: 2,780
Unique place_norm values: 838
Missing/empty after normalization: 0
```

**Top 20 Places:**

```
1. paris                                    :   273
2. london                                   :   187
3. berlin                                   :    91
4. אמשטרדם                                   :    85
5. venetiis                                 :    60
6. hamburg                                  :    50
7. leipzig                                  :    46
8. venetiæ                                  :    41
9. roma                                     :    40
10. oxford                                   :    38
11. frankfvrt am mayn                        :    37
12. [s.l.]                                   :    36
13. יאזפהוא                                  :    34
14. hafniæ                                   :    33
15. lipsiae                                  :    32
16. francofvrti ad moenvm                    :    31
17. new york                                 :    29
18. viennæ                                   :    28
19. ירושלים                                  :    27
20. פראג                                     :    27
```

**Key Observations:**

- Mix of modern English (paris, london), Latin (venetiis, lipsiae), and Hebrew (אמשטרדם, ירושלים)
- Punctuation and bracket variations normalized out
- Placeholder `[s.l.]` (sine loco) preserved
- No unexpected missing values (0 missing after normalization)

### Validation Result

**Reference Record MMS 990011964120204146:**

✅ **PASSED**

- Input: `260 $a Paris :`
- Raw example: `"Paris :"` preserved in examples
- Normalized: `place_norm = "paris"`
- Frequency count: Incremented correctly

---

## Next Steps

1. **Use output for alias mapping:** Feed `places_freq.csv` into `scripts/normalization/generate_place_alias_map.py`
2. **Review examples:** Use `places_examples.json` to validate normalization quality
3. **Iterate:** If normalization rules need adjustment, update `normalize_place_basic()` and regenerate

## See Also

- [Place Normalization Pipeline](../pipelines/place_normalization.md) - Full workflow documentation
- [M2 Normalization Specification](./m2_normalization_spec.md) - How place normalization integrates with M2
