---
name: python-dev-expert
description: Python development expertise for rare-books-bot project. Use this skill when (1) Writing new Python code for MARC parsing, normalization, or query execution, (2) Refactoring existing code to improve maintainability or reduce duplication, (3) Making architectural decisions about file organization, class structure, or module design, (4) Reviewing code quality for PEP 8 compliance, type hints, or documentation, (5) Generating code from templates for parsers, normalizers, or query compilers, (6) Ensuring functions are single-purpose and under 50 lines with emphasis on logic density, deterministic outputs, and testability without LLM.
---

# Python Development Expert for rare-books-bot

Expert guidance for Python coding, refactoring, and architectural decisions in the rare-books-bot project.

**Mission Alignment**: All code must support deterministic, evidence-based bibliographic discovery from MARC XML.

## Project-Specific Principles

### Data Model Requirements

**Always preserve raw MARC values**:
- Never destructively normalize
- Store raw alongside normalized
- Track normalization method and confidence

**Testability without LLM**:
- All parsing/normalization must be deterministic
- Use pure functions where possible
- LLM is planner/explainer, not authority

**Answer Contract**:
- QueryPlan → CandidateSet → Evidence
- No narrative before CandidateSet exists

## Quick Decision Trees

### Should I Create a New File?

**New Parser/Loader** → Create in `scripts/ingestion/` when:
- Adding MARC XML parser or new bibliographic format support
- Building loader for canonical JSONL format
- Follow modular ingestion patterns

**New Normalizer** → Create in `scripts/normalization/` when:
- Adding date normalization (MARC dates → date_start/date_end)
- Building place/publisher/agent string normalization
- Implementing reversible normalization logic

**New Query Component** → Create in `scripts/query/` when:
- Building QueryPlan compiler (NL → JSON)
- Implementing SQL generator from QueryPlan
- Creating CandidateSet executor with evidence tracking

**New Utility Module** → Create in `scripts/utils/` when:
- Code is reused across 3+ components
- Provides general-purpose functionality (MARC field extraction, confidence scoring, etc.)

**DO NOT create new file** when:
- Function belongs in existing parser or normalizer
- Code is used in only 1-2 places (inline it or extract to method)

### Should I Refactor This Code?

**YES - Refactor immediately** when:
- Function exceeds 50 lines
- Same logic appears in 3+ places
- Function does multiple unrelated things
- Complex nested conditions (>3 levels)
- Non-deterministic behavior (random, time-dependent, LLM-dependent)

**MAYBE - Consider refactoring** when:
- Variable names are unclear (e.g., `x`, `data`, `temp`)
- Missing type hints or docstrings
- Magic numbers or hardcoded MARC field codes without constants
- Normalization without confidence tracking

**NO - Leave as-is** when:
- Code is clear and works correctly
- Refactoring would not improve readability
- One-time use code in scripts

## Core Workflows

### Workflow 1: Creating a MARC Parser Component

1. **Verify necessity**: Confirm new MARC field group needs dedicated parser
2. **Design interface**:
   ```python
   def parse_marc_field(field: Element) -> Dict[str, Any]:
       """Parse MARC field preserving raw values.

       Returns:
           Dict with 'raw' and 'parsed' keys, never destructive
       """
   ```
3. **Implement core logic**:
   - Extract field/subfield values from XML
   - Preserve all raw values in output
   - Return structured dict with raw + parsed
4. **Add type hints**: All parameters and return values (use Pydantic/dataclasses)
5. **Write docstrings**: Purpose, parameters, returns, MARC field references
6. **Ensure deterministic**: Same input always produces same output
7. **Add unit tests**: Test without requiring LLM or external services

### Workflow 2: Creating a Normalizer

1. **Design for reversibility**:
   ```python
   def normalize_date(raw_date: str) -> NormalizedDate:
       """Normalize MARC date to date range with confidence.

       Args:
           raw_date: Raw MARC date string (e.g., "1580-1599", "c1500")

       Returns:
           NormalizedDate with date_start, date_end, method, confidence, raw
       """
       return NormalizedDate(
           raw=raw_date,
           date_start=start,
           date_end=end,
           method="range_parse",
           confidence=0.95
       )
   ```
2. **Core requirements**:
   - Always include `raw` field in output
   - Track `method` used for normalization
   - Include `confidence` score (0.0-1.0)
   - If uncertain: return null/range + explicit reason
   - Never invent data
3. **Add comprehensive tests**: Edge cases, malformed input, uncertain dates
4. **Document assumptions**: Which MARC conventions are supported

### Workflow 3: Creating a Query Component

1. **Design QueryPlan schema**:
   ```python
   class QueryPlan(BaseModel):
       """Structured query plan validated by JSON schema."""
       query_type: str  # "date_range", "place", "subject", etc.
       filters: Dict[str, Any]
       evidence_fields: List[str]  # MARC fields to include in evidence
   ```
2. **Implement SQL generation**:
   - QueryPlan → SQL query
   - Include EXPLAIN in debug mode
   - Return SQL string + parameters separately (prevent SQL injection)
3. **Execute with evidence**:
   ```python
   def execute_plan(plan: QueryPlan, db: Path) -> ExecutionResult:
       """Execute query plan and return candidate set with evidence.

       Returns:
           ExecutionResult with:
           - candidate_set: List[str] (record IDs)
           - evidence: Dict[str, List[Dict]] (field values per record)
           - sql: str (executed SQL for transparency)
       """
   ```
4. **Validation**: JSON schema validation with retry logic (1 repair attempt)

### Workflow 4: Code Quality Review

Use this checklist before committing code:

1. **Data Model Compliance**:
   - [ ] Raw values always preserved
   - [ ] Normalization is reversible
   - [ ] Confidence scores included where applicable
   - [ ] No invented data (null/range + reason instead)

2. **Testability**:
   - [ ] Functions are deterministic (same input → same output)
   - [ ] No LLM dependencies in core logic
   - [ ] Unit tests cover edge cases
   - [ ] Tests run without external services

3. **Code Quality**:
   - [ ] All functions <50 lines and single-purpose
   - [ ] Type hints on all functions (Pydantic/dataclasses preferred)
   - [ ] Docstrings on all public methods
   - [ ] Imports organized (stdlib → third-party → local)
   - [ ] No commented-out code
   - [ ] No hardcoded API keys or secrets

4. **Logging**:
   - [ ] Logging for all parsing/normalization operations
   - [ ] Per-run artifacts written to `data/runs/<run_id>/`
   - [ ] Use LoggerManager from `scripts/utils/logger.py`

## Logic Density Principles

**Keep functions focused and concise:**

- **Maximum 50 lines** per function
- **Single purpose** - One function = One clear responsibility
- **Composition over inheritance** - Prefer composing objects over deep inheritance
- **Extract early** - If you think "this could be extracted," do it now
- **Deterministic** - No randomness, no time-dependent behavior in core logic

**Example of good logic density:**

```python
# GOOD - Single purpose, under 50 lines, deterministic
def extract_publication_date(record: Dict[str, Any]) -> Optional[str]:
    """Extract raw publication date from MARC 260$c or 264$c."""
    for field in record.get('fields', []):
        if '260' in field:
            for subfield in field['260'].get('subfields', []):
                if 'c' in subfield:
                    return subfield['c'].strip()
        if '264' in field:
            for subfield in field['264'].get('subfields', []):
                if 'c' in subfield:
                    return subfield['c'].strip()
    return None

def normalize_century_date(raw_date: str) -> NormalizedDate:
    """Normalize '16th century' or 'XVI century' to date range."""
    # 15 lines of parsing logic
    return NormalizedDate(
        raw=raw_date,
        date_start=start_year,
        date_end=end_year,
        method="century_parse",
        confidence=0.9
    )

# BAD - Multiple purposes, >50 lines, non-deterministic
def extract_and_normalize_date(record: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """Extract date and normalize."""  # Doing two things!
    # 20 lines of MARC field extraction
    # 25 lines of date normalization
    # 10 lines of logging and error handling
    # Total: 55+ lines doing multiple things
    return (start, end)  # Lost raw value, method, confidence!
```

## MARC-Specific Patterns

### Working with MARC Fields

```python
# Define constants for MARC fields
TITLE_FIELDS = ['245']
DATE_FIELDS = ['260', '264']
PLACE_FIELDS = ['260', '264']
SUBJECT_FIELDS = ['600', '610', '630', '650', '651']

def extract_field_value(record: Dict, field: str, subfield: str) -> List[str]:
    """Extract all occurrences of field$subfield from MARC record."""
    values = []
    for field_data in record.get('fields', []):
        if field in field_data:
            for sub in field_data[field].get('subfields', []):
                if subfield in sub:
                    values.append(sub[subfield])
    return values
```

### Confidence Scoring

```python
def calculate_confidence(raw_value: str, method: str) -> float:
    """Calculate confidence score for normalization.

    Args:
        raw_value: Original MARC value
        method: Normalization method used

    Returns:
        Confidence score 0.0-1.0
    """
    if method == "exact_match":
        return 1.0
    elif method == "regex_parse":
        return 0.95
    elif method == "century_parse":
        return 0.9
    elif method == "circa_estimate":
        return 0.7
    elif method == "fallback_guess":
        return 0.5
    else:
        return 0.0
```

### Evidence Tracking

```python
class Evidence(BaseModel):
    """Evidence for why a record was included in CandidateSet."""
    record_id: str
    matched_fields: Dict[str, Any]  # field → value that matched
    normalization_applied: Dict[str, Dict]  # field → normalization details

def build_evidence(record: Dict, query_plan: QueryPlan) -> Evidence:
    """Build evidence dict showing which MARC fields caused inclusion."""
    matched = {}
    for field in query_plan.evidence_fields:
        value = extract_field_value(record, field, 'a')
        if value:
            matched[field] = value

    return Evidence(
        record_id=record['001'],
        matched_fields=matched,
        normalization_applied={}
    )
```

## Directory Structure Patterns

Your project uses this structure:

```
scripts/
  ingestion/         # MARC XML loaders, parsers
  normalization/     # Date, place, agent normalizers (to be created)
  query/             # QueryPlan compiler, SQL generator (to be created)
  core/              # ProjectManager, shared classes
  utils/             # Reusable utilities, logging
  chunking/          # (inherited from template, may not need)
  embeddings/        # (inherited from template, may not need)
  retrieval/         # (inherited from template, may not need)
```

**For MARC XML project:**
- Focus on `ingestion/`, `normalization/`, `query/`
- Leverage existing `core/` and `utils/`
- May deprecate RAG-specific components (embeddings, retrieval)

## Templates

Templates are available in `assets/` (to be adapted for MARC XML):

- **marc_parser_template.py** - MARC field parser structure
- **normalizer_template.py** - Normalizer with confidence tracking
- **query_component_template.py** - Query plan compiler structure
- **test_template.py** - Test structure for MARC components

**Note**: These templates need to be created. Current templates are AlmaAPITK-specific.

## Common Anti-Patterns to Avoid

### ❌ Destructive Normalization

```python
# BAD - Loses raw value
def normalize_date(date_str: str) -> int:
    return int(date_str[:4])  # Lost "c1580", "1580-1599", etc.

# GOOD - Preserves raw value
def normalize_date(date_str: str) -> NormalizedDate:
    return NormalizedDate(
        raw=date_str,
        date_start=1580,
        date_end=1580,
        method="year_extract",
        confidence=0.8
    )
```

### ❌ Non-Deterministic Logic

```python
# BAD - Time-dependent
def parse_date(date_str: str) -> int:
    if "modern" in date_str:
        return datetime.now().year  # Changes every execution!

# GOOD - Deterministic
def parse_date(date_str: str) -> Optional[NormalizedDate]:
    if "modern" in date_str:
        return None  # Or return range with explicit reasoning
```

### ❌ LLM in Core Logic

```python
# BAD - LLM in parser
def extract_place(record: Dict) -> str:
    raw = extract_field_value(record, '260', 'a')
    return llm.normalize(raw)  # Non-deterministic!

# GOOD - LLM only for planning
def compile_query(nl_query: str) -> QueryPlan:
    # LLM can help here (planning phase)
    plan_dict = llm.generate_plan(nl_query)
    # But validate with schema
    return QueryPlan.parse_obj(plan_dict)
```

## When NOT to Use This Skill

This skill focuses on Python code quality and MARC-specific architecture. Do NOT use for:

- Git operations (commits, branches, merges) → Use `git-expert` skill
- General questions about MARC standards → Consult MARC documentation
- Test execution → Run tests directly with pytest
- Package management → Use poetry commands directly

## Summary

This skill ensures Python code in rare-books-bot:
- Preserves raw MARC values (reversible normalization)
- Is deterministic and testable without LLM
- Follows logic density principles (<50 lines, single-purpose)
- Tracks confidence and evidence
- Aligns with the Answer Contract (QueryPlan → CandidateSet → Evidence)
