# Agent Integration Implementation Plan

**Created**: 2026-01-11
**Goal**: Add agents (people/corporate bodies) + roles (author, printer, publisher, editor, etc.) as first-class, queryable metadata across the entire M1→M4 pipeline + QA/UI

## Target Outcome

After this integration, queries like these will work deterministically:

- "books printed by Aldus Manutius in Venice between 1500–1520"
- "books translated by X"
- "books published by Oxford" (as agent role publisher)

Each query compiles into a QueryPlan and SQL that hits an `agents` table, returning CandidateSet with Evidence showing which MARC fields/values caused the match.

---

## Stage 1 — Data Contract: Agent Object Structure

### 1.1 M1 Canonical Agent Object

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/models.py`

**Current State**:
- `AgentData` class exists at lines 83-99
- Already extracts: `value` (string), `sources` (SourceMetadata array), `agent_index` (int)
- Does NOT yet extract: role information, multiple agent types

**Required Changes**:

Add new fields to `AgentData`:

```python
@dataclass
class AgentData:
    """Agent (person or corporate body) with role and provenance."""
    value: str  # Keep existing: raw string from MARC
    agent_index: int  # Keep existing: stable ordering
    sources: List[SourceMetadata]  # Keep existing: MARC provenance

    # NEW FIELDS:
    agent_type: str  # "personal" | "corporate" | "meeting"
    role_raw: Optional[str] = None  # Raw role from MARC (relator code/term)
    role_source: Optional[str] = None  # "relator_code" | "relator_term" | "inferred_from_tag"
```

**Rationale**: This keeps extraction deterministic + auditable while preserving existing structure.

---

### 1.2 M2 Normalized Agent Object

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/m2_models.py`

**Current State**:
- File exists (59 lines) with `DateNormalization`, `PlaceNormalization`, `PublisherNormalization`
- Pattern: raw value → normalized key + confidence + method tags

**Required Changes**:

Add new normalization classes:

```python
@dataclass
class AgentNormalization:
    """Normalized agent with confidence tracking."""
    agent_raw: str  # Original from M1
    agent_norm: str  # Canonical string for faceting (lowercase, no punctuation)
    agent_confidence: float  # 0.0-1.0
    agent_method: str  # "base_clean" | "alias_map" | "ambiguous"
    agent_notes: Optional[str] = None  # Warnings or ambiguity flags

@dataclass
class RoleNormalization:
    """Normalized role with confidence tracking."""
    role_raw: Optional[str]  # Original from M1
    role_norm: str  # Controlled vocabulary
    role_confidence: float  # 0.0-1.0
    role_method: str  # "relator_code" | "relator_term" | "inferred" | "manual_map"
```

Add to `M2Enrichment`:

```python
@dataclass
class M2Enrichment:
    imprints_norm: List[ImprintNormalization]
    agents_norm: List[Tuple[int, AgentNormalization, RoleNormalization]]  # (agent_index, agent, role)
```

**Rationale**: Mirrors place/publisher normalization pattern; raw values preserved.

---

## Stage 2 — M1 Extraction (Deterministic, No LLM)

### 2.1 Expand MARC Extraction Rules

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/parse.py`

**Current function**: `extract_agents(record: pymarc.Record) -> List[AgentData]` (lines 385-441)

**Current limitations**:
- Only extracts from 100 (main personal name) and 700 (added personal names)
- Does NOT extract corporate bodies (110/710) or meetings (111/711)
- Does NOT capture role information ($4 relator code, $e relator term)

**Required changes**:

1. **Expand tag coverage**:
```python
def extract_agents(record: pymarc.Record) -> List[AgentData]:
    """Extract all agents with roles from MARC record."""
    agents = []
    agent_index = 0

    # Personal names: 100, 700
    for tag in ['100', '700']:
        for field in record.get_fields(tag):
            agent = _extract_personal_agent(field, agent_index)
            if agent:
                agents.append(agent)
                agent_index += 1

    # Corporate bodies: 110, 710
    for tag in ['110', '710']:
        for field in record.get_fields(tag):
            agent = _extract_corporate_agent(field, agent_index)
            if agent:
                agents.append(agent)
                agent_index += 1

    # Meetings: 111, 711 (if present in collection)
    for tag in ['111', '711']:
        for field in record.get_fields(tag):
            agent = _extract_meeting_agent(field, agent_index)
            if agent:
                agents.append(agent)
                agent_index += 1

    return agents
```

2. **Add role extraction helper**:
```python
def _extract_role_from_field(field: pymarc.Field, tag: str) -> Tuple[Optional[str], str]:
    """Extract role with source priority: $4 > $e > inferred from tag.

    Returns:
        (role_raw, role_source)
    """
    # Priority 1: $4 relator code (best)
    if '4' in field:
        code = field['4'].strip()
        if code:
            return (code, "relator_code")

    # Priority 2: $e relator term
    if 'e' in field:
        term = field['e'].strip()
        if term:
            return (term, "relator_term")

    # Priority 3: Infer from tag type (lower confidence)
    inferred_roles = {
        '100': 'author',  # Main entry - personal name (usually author)
        '110': 'creator',  # Main entry - corporate body
        '111': 'creator',  # Main entry - meeting
        '700': None,  # Added entry - unknown role without explicit code/term
        '710': None,  # Added corporate - unknown
        '711': None,  # Added meeting - unknown
    }
    role = inferred_roles.get(tag)
    if role:
        return (role, "inferred_from_tag")

    return (None, "unknown")
```

3. **Add agent type extractors**:
```python
def _extract_personal_agent(field: pymarc.Field, agent_index: int) -> Optional[AgentData]:
    """Extract personal name agent (100/700)."""
    name_parts = []
    for code in ['a', 'b', 'c', 'd', 'q']:  # Name components
        if code in field:
            name_parts.append(field[code].strip())

    if not name_parts:
        return None

    value = ' '.join(name_parts)
    role_raw, role_source = _extract_role_from_field(field, field.tag)

    return AgentData(
        value=value,
        agent_index=agent_index,
        sources=[_build_source_metadata(field)],
        agent_type="personal",
        role_raw=role_raw,
        role_source=role_source
    )

def _extract_corporate_agent(field: pymarc.Field, agent_index: int) -> Optional[AgentData]:
    """Extract corporate body agent (110/710)."""
    name_parts = []
    for code in ['a', 'b']:  # Corporate name + subordinate unit
        if code in field:
            name_parts.append(field[code].strip())

    if not name_parts:
        return None

    value = ' '.join(name_parts)
    role_raw, role_source = _extract_role_from_field(field, field.tag)

    return AgentData(
        value=value,
        agent_index=agent_index,
        sources=[_build_source_metadata(field)],
        agent_type="corporate",
        role_raw=role_raw,
        role_source=role_source
    )

def _extract_meeting_agent(field: pymarc.Field, agent_index: int) -> Optional[AgentData]:
    """Extract meeting name agent (111/711)."""
    name_parts = []
    for code in ['a', 'c', 'd', 'n']:  # Meeting name, location, date, number
        if code in field:
            name_parts.append(field[code].strip())

    if not name_parts:
        return None

    value = ' '.join(name_parts)
    role_raw, role_source = _extract_role_from_field(field, field.tag)

    return AgentData(
        value=value,
        agent_index=agent_index,
        sources=[_build_source_metadata(field)],
        agent_type="meeting",
        role_raw=role_raw,
        role_source=role_source
    )
```

**Testing requirements**:
- Add test cases in `/home/hagaybar/projects/rare-books-bot/tests/scripts/marc/test_parse.py`
- Test each agent type (personal, corporate, meeting)
- Test role extraction priority ($4 > $e > inferred)
- Test provenance tracking for all field types

---

## Stage 3 — M2 Normalization (Deterministic Base + Optional LLM Assist)

### 3.1 Deterministic Base Normalization

**File to create**: `/home/hagaybar/projects/rare-books-bot/scripts/normalization/normalize_agent.py`

**Pattern**: Follow existing `normalize_place.py` / `normalize_publisher.py` pattern

**Required functions**:

```python
def normalize_agent_base(agent_raw: str) -> str:
    """Deterministic base normalization for agents.

    Rules:
    - Casefold (lowercase)
    - Trim leading/trailing whitespace
    - Collapse internal whitespace to single spaces
    - Strip trailing punctuation (commas, periods, colons, semicolons)
    - Remove bracket wrappers [...]
    - Keep diacritics (consistent with place normalization)
    - DO NOT expand abbreviations or invent data

    Examples:
        "Manutius, Aldus, 1450?-1515" → "manutius aldus 1450-1515"
        "[Oxford University Press]" → "oxford university press"
        "Elsevier, " → "elsevier"

    Returns:
        Normalized agent key (still may contain dates/qualifiers)
    """
    if not agent_raw:
        return ""

    # Remove brackets
    normalized = agent_raw.strip()
    if normalized.startswith('[') and normalized.endswith(']'):
        normalized = normalized[1:-1].strip()

    # Casefold
    normalized = normalized.lower()

    # Strip trailing punctuation
    normalized = normalized.rstrip('.,;:')

    # Collapse whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def normalize_role_base(role_raw: Optional[str]) -> Tuple[str, float, str]:
    """Map role string to controlled vocabulary.

    Uses explicit mapping table for common variants.
    Returns ("other", low_confidence) for unknown roles.

    Returns:
        (role_norm, confidence, method)
    """
    if not role_raw:
        return ("other", 0.5, "missing_role")

    role_clean = role_raw.strip().lower()

    # Relator code mappings (high confidence)
    RELATOR_CODE_MAP = {
        'aut': 'author',
        'prt': 'printer',
        'pbl': 'publisher',
        'trl': 'translator',
        'edt': 'editor',
        'ill': 'illustrator',
        'com': 'commentator',
        'scr': 'scribe',
        'fmo': 'former_owner',
        'dte': 'dedicatee',
        'bsl': 'bookseller',
        'ctg': 'cartographer',
        'eng': 'engraver',
        'bnd': 'binder',
        'ann': 'annotator',
    }

    if role_clean in RELATOR_CODE_MAP:
        return (RELATOR_CODE_MAP[role_clean], 0.99, "relator_code")

    # Relator term mappings (medium confidence)
    RELATOR_TERM_MAP = {
        'author': 'author',
        'printer': 'printer',
        'publisher': 'publisher',
        'translator': 'translator',
        'editor': 'editor',
        'illustrator': 'illustrator',
        'commentator': 'commentator',
        'scribe': 'scribe',
        'former owner': 'former_owner',
        'dedicatee': 'dedicatee',
        'bookseller': 'bookseller',
        'engraver': 'engraver',
        'binder': 'binder',
        'annotator': 'annotator',
        # Variants
        'impr.': 'printer',
        'pub.': 'publisher',
        'ed.': 'editor',
        'trans.': 'translator',
    }

    if role_clean in RELATOR_TERM_MAP:
        return (RELATOR_TERM_MAP[role_clean], 0.95, "relator_term")

    # Unknown role
    return ("other", 0.6, "unmapped")
```

**Testing requirements**:
- Unit tests for `normalize_agent_base()` with edge cases
- Unit tests for `normalize_role_base()` covering all mappings
- Test file: `/home/hagaybar/projects/rare-books-bot/tests/scripts/normalization/test_normalize_agent.py`

---

### 3.2 Authority/Alias Mapping Layer (LLM-Assisted)

**File to create**: `/home/hagaybar/projects/rare-books-bot/scripts/normalization/generate_agent_alias_map.py`

**Pattern**: Mirror existing `generate_place_alias_map.py` (458 lines)

**Data files**:
```
data/normalization/agent_aliases/
├── agent_alias_map.json         # Production mapping (version-controlled)
├── agent_alias_cache.jsonl      # LLM cache (gitignored)
└── agent_alias_proposed.csv     # Human review file (gitignored)
```

**Structure**:
```json
{
  "manutius aldus 1450-1515": {
    "decision": "MAP",
    "canonical": "aldus manutius",
    "confidence": 0.95,
    "notes": "Standard form, dates removed",
    "llm_model": "claude-sonnet-4.5",
    "prompt_hash": "abc123..."
  },
  "aldus manutius": {
    "decision": "KEEP",
    "canonical": "aldus manutius",
    "confidence": 1.0,
    "notes": "Already canonical"
  },
  "manuzio aldo": {
    "decision": "MAP",
    "canonical": "aldus manutius",
    "confidence": 0.90,
    "notes": "Italian variant of Aldus Manutius"
  }
}
```

---

### 3.3 LLM Integration Points (Guarded)

**AI Prompt 1 — Agent Canonicalization**

**Usage context**: Called in `generate_agent_alias_map.py` for each unique agent_norm_base

**Prompt Template**:

```
SYSTEM:
You normalize bibliographic agent strings into ONE canonical key for faceting.
Follow the JSON schema exactly. No prose. Never invent facts (e.g., dates, places, identities).
If uncertain whether two forms are the same person/body, output decision="AMBIGUOUS".

Constraints:
- canonical must be lowercase ASCII (letters/digits/spaces only, no punctuation)
- do NOT include life dates, titles, honorifics, or qualifiers in canonical form
- if input already fits canonical constraints, decision="KEEP" and canonical must equal input
- for personal names, use natural order: "firstname lastname" (not "lastname, firstname")
- for corporate bodies, use shortest unambiguous form

USER:
Task: Map one agent key to ONE canonical key.

Input agent_norm_base: "{agent_norm_base}"
Count in collection: {count}
Raw examples (first 5): {raw_examples_json}
Agent type: {agent_type}

Return JSON:
{
  "decision": "KEEP" | "MAP" | "AMBIGUOUS",
  "canonical": "<lowercase ascii, no punctuation>",
  "confidence": 0.0-1.0,
  "reason": "<very short explanation, max 10 words>"
}
```

**Code guardrails** (must enforce):

```python
def validate_agent_canonical_response(response: dict, input_key: str) -> bool:
    """Validate LLM response for agent canonicalization."""
    # Schema check
    required_keys = {"decision", "canonical", "confidence", "reason"}
    if not required_keys.issubset(response.keys()):
        return False

    # Decision validation
    if response["decision"] not in ["KEEP", "MAP", "AMBIGUOUS"]:
        return False

    # Canonical format validation (ASCII, no punctuation)
    canonical = response["canonical"]
    if not re.match(r'^[a-z0-9 ]+$', canonical):
        return False

    # KEEP => canonical must equal input
    if response["decision"] == "KEEP" and canonical != input_key:
        return False

    # AMBIGUOUS => canonical must be "ambiguous"
    if response["decision"] == "AMBIGUOUS" and canonical != "ambiguous":
        return False

    # Confidence range
    if not (0.0 <= response["confidence"] <= 1.0):
        return False

    return True
```

**Retry logic**:
- On validation failure: retry once with repair prompt
- On second failure: mark as `{"decision": "AMBIGUOUS", "canonical": "ambiguous", "confidence": 0.0, "reason": "llm_validation_failed"}`
- Always log LLM model name + prompt hash for traceability

---

**AI Prompt 2 — Role Normalization** (RARELY NEEDED)

**Usage context**: Only if MARC role strings are very messy and not covered by deterministic mappings

**Prompt Template**:

```
SYSTEM:
Normalize MARC relator terms/codes to a controlled role list.
No prose. If unknown, output "other".

USER:
role_raw: "{role_raw}"
context: bibliographic agent role in rare books catalog

Return JSON:
{
  "role_norm": "author"|"printer"|"publisher"|"translator"|"editor"|"illustrator"|"commentator"|"scribe"|"former_owner"|"dedicatee"|"bookseller"|"other",
  "confidence": 0.0-1.0,
  "reason": "<very short>"
}
```

**Note**: This should be unnecessary if relator codes are clean. Only implement if needed after analyzing actual data.

---

### 3.4 Update M2 Normalization Pipeline

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/normalize.py`

**Add function**:

```python
def normalize_agents(
    agents: List[AgentData],
    agent_alias_map: Optional[Dict[str, dict]] = None
) -> List[Tuple[int, AgentNormalization, RoleNormalization]]:
    """Normalize all agents from M1 record.

    Args:
        agents: List of AgentData from M1
        agent_alias_map: Optional alias map for canonical forms

    Returns:
        List of (agent_index, agent_norm, role_norm) tuples
    """
    results = []

    for agent in agents:
        # Normalize agent name
        agent_norm_base = normalize_agent_base(agent.value)

        # Apply alias map if available
        if agent_alias_map and agent_norm_base in agent_alias_map:
            alias_entry = agent_alias_map[agent_norm_base]
            agent_norm = AgentNormalization(
                agent_raw=agent.value,
                agent_norm=alias_entry["canonical"],
                agent_confidence=alias_entry["confidence"],
                agent_method="alias_map",
                agent_notes=alias_entry.get("notes")
            )
        else:
            # Base normalization only
            agent_norm = AgentNormalization(
                agent_raw=agent.value,
                agent_norm=agent_norm_base,
                agent_confidence=0.80,  # Base confidence
                agent_method="base_clean",
                agent_notes=None
            )

        # Normalize role
        role_norm_str, role_conf, role_method = normalize_role_base(agent.role_raw)
        role_norm = RoleNormalization(
            role_raw=agent.role_raw,
            role_norm=role_norm_str,
            role_confidence=role_conf,
            role_method=role_method
        )

        results.append((agent.agent_index, agent_norm, role_norm))

    return results
```

**Integrate into main normalization**:

```python
def enrich_m2(
    record: CanonicalRecord,
    place_alias_map: Optional[Dict] = None,
    publisher_alias_map: Optional[Dict] = None,
    agent_alias_map: Optional[Dict] = None  # NEW
) -> M2Enrichment:
    """Add M2 normalized fields to M1 canonical record."""
    # Existing imprint normalization...
    imprints_norm = [normalize_imprint(imp, place_alias_map, publisher_alias_map)
                     for imp in record.imprints]

    # NEW: Agent normalization
    agents_norm = normalize_agents(record.agents, agent_alias_map)

    return M2Enrichment(
        imprints_norm=imprints_norm,
        agents_norm=agents_norm
    )
```

---

## Stage 4 — M3 SQLite Schema Updates

### 4.1 Modify Agents Table Schema

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/m3_schema.sql`

**Current agents table** (lines 103-112):
```sql
CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    agent_value TEXT,
    agent_index INTEGER,
    sources TEXT,
    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_agents_record_id ON agents(record_id);
CREATE INDEX IF NOT EXISTS idx_agents_value ON agents(agent_value);
```

**REPLACE with enhanced schema**:

```sql
-- Enhanced agents table with roles and normalization
DROP TABLE IF EXISTS agents;

CREATE TABLE agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL,
    agent_index INTEGER NOT NULL,

    -- M1 raw fields
    agent_raw TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('personal', 'corporate', 'meeting')),
    role_raw TEXT,
    role_source TEXT,  -- "relator_code" | "relator_term" | "inferred_from_tag" | "unknown"

    -- M2 normalized fields
    agent_norm TEXT NOT NULL,
    agent_confidence REAL NOT NULL CHECK(agent_confidence BETWEEN 0 AND 1),
    agent_method TEXT NOT NULL,
    agent_notes TEXT,

    role_norm TEXT NOT NULL,
    role_confidence REAL NOT NULL CHECK(role_confidence BETWEEN 0 AND 1),
    role_method TEXT NOT NULL,

    -- Provenance (JSON array of SourceMetadata)
    provenance_json TEXT NOT NULL,

    FOREIGN KEY (record_id) REFERENCES records(record_id) ON DELETE CASCADE
);

-- Indexes for efficient querying
CREATE INDEX idx_agents_record_id ON agents(record_id);
CREATE INDEX idx_agents_agent_norm ON agents(agent_norm);
CREATE INDEX idx_agents_role_norm ON agents(role_norm);
CREATE INDEX idx_agents_agent_role ON agents(agent_norm, role_norm);  -- Composite for "printer X" queries
CREATE INDEX idx_agents_type ON agents(agent_type);
```

**Rationale**:
- Stores both M1 raw and M2 normalized fields (non-destructive)
- Confidence tracking for both agent and role normalization
- Provenance as JSON for flexible querying
- Composite index for fast agent+role queries

---

### 4.2 Update Indexing Code

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/marc/m3_index.py`

**Current function**: `_insert_agents()` (lines 257-276)

**REPLACE with**:

```python
def _insert_agents(
    cursor: sqlite3.Cursor,
    record_id: str,
    agents: List[AgentData],
    agents_norm: List[Tuple[int, AgentNormalization, RoleNormalization]]
) -> None:
    """Insert agents with M1 raw + M2 normalized fields."""
    # Build lookup: agent_index → (agent_norm, role_norm)
    norm_lookup = {idx: (agent_n, role_n) for idx, agent_n, role_n in agents_norm}

    for agent in agents:
        # Get normalized fields
        agent_norm, role_norm = norm_lookup.get(agent.agent_index, (None, None))

        if not agent_norm:
            # Skip if normalization failed (shouldn't happen)
            continue

        cursor.execute(
            """
            INSERT INTO agents (
                record_id, agent_index,
                agent_raw, agent_type, role_raw, role_source,
                agent_norm, agent_confidence, agent_method, agent_notes,
                role_norm, role_confidence, role_method,
                provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                agent.agent_index,
                agent.value,
                agent.agent_type,
                agent.role_raw,
                agent.role_source,
                agent_norm.agent_norm,
                agent_norm.agent_confidence,
                agent_norm.agent_method,
                agent_norm.agent_notes,
                role_norm.role_norm,
                role_norm.role_confidence,
                role_norm.role_method,
                json.dumps([s.dict() for s in agent.sources]),
            ),
        )
```

**Update main indexing function** (lines 111-173):

```python
def index_record(
    cursor: sqlite3.Cursor,
    record: CanonicalRecord,
    enrichment: Optional[M2Enrichment] = None
) -> None:
    """Index a single M1+M2 record into SQLite."""
    # ... existing code for records, titles, imprints ...

    # Insert agents (M1 + M2)
    if enrichment and enrichment.agents_norm:
        _insert_agents(cursor, record_id, record.agents, enrichment.agents_norm)
    else:
        # Fallback: insert M1 only (but should always have M2)
        _insert_agents_m1_only(cursor, record_id, record.agents)

    # ... rest of indexing ...
```

---

## Stage 5 — M4 QueryPlan + SQL Compiler Support

### 5.1 Update QueryPlan Schema

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/schemas/query_plan.py`

**Current FilterField enum** (lines 13-21):
```python
class FilterField(str, Enum):
    """Supported filter fields."""
    PUBLISHER = "PUBLISHER"
    IMPRINT_PLACE = "IMPRINT_PLACE"
    YEAR = "YEAR"
    LANGUAGE = "LANGUAGE"
    TITLE = "TITLE"
    SUBJECT = "SUBJECT"
    AGENT = "AGENT"
```

**ADD new fields**:
```python
class FilterField(str, Enum):
    """Supported filter fields."""
    PUBLISHER = "PUBLISHER"
    IMPRINT_PLACE = "IMPRINT_PLACE"
    YEAR = "YEAR"
    LANGUAGE = "LANGUAGE"
    TITLE = "TITLE"
    SUBJECT = "SUBJECT"
    AGENT = "AGENT"  # Keep existing for backward compat
    AGENT_NORM = "AGENT_NORM"  # NEW: Query normalized agent names
    AGENT_ROLE = "AGENT_ROLE"  # NEW: Query by role (printer, translator, etc.)
    AGENT_TYPE = "AGENT_TYPE"  # NEW: Query by type (personal, corporate, meeting)
```

**Rationale**: Allows fine-grained agent queries while keeping backward compatibility.

---

### 5.2 Update Compiler Heuristics

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/query/compile.py`

**Add new parsing functions**:

```python
def parse_agent_with_role(query: str) -> List[Filter]:
    """Parse agent + role patterns from natural language query.

    Patterns:
    - "printed by <name>" → role=printer, agent=<name>
    - "published by <name>" → role=publisher, agent=<name>
    - "translated by <name>" → role=translator, agent=<name>
    - "books by <name>" → agent=<name> (role ambiguous, add debug note)
    - "author <name>" → role=author, agent=<name>
    """
    filters = []

    # Pattern: "printed by X"
    pattern_printer = re.compile(r'printed by ([A-Z][A-Za-z\s.]+?)(?:\s+in|\s+between|$)', re.IGNORECASE)
    for match in pattern_printer.finditer(query):
        agent_name = match.group(1).strip()
        filters.append(Filter(
            field=FilterField.AGENT_ROLE,
            op=FilterOp.EQUALS,
            value="printer",
            notes=f"role filter from 'printed by'"
        ))
        filters.append(Filter(
            field=FilterField.AGENT_NORM,
            op=FilterOp.CONTAINS,
            value=agent_name.lower(),
            notes=f"agent name from 'printed by {agent_name}'"
        ))

    # Pattern: "published by X"
    pattern_publisher = re.compile(r'published by ([A-Z][A-Za-z\s.]+?)(?:\s+in|\s+between|$)', re.IGNORECASE)
    for match in pattern_publisher.finditer(query):
        agent_name = match.group(1).strip()
        filters.append(Filter(
            field=FilterField.AGENT_ROLE,
            op=FilterOp.EQUALS,
            value="publisher",
            notes=f"role filter from 'published by'"
        ))
        filters.append(Filter(
            field=FilterField.AGENT_NORM,
            op=FilterOp.CONTAINS,
            value=agent_name.lower(),
            notes=f"agent name from 'published by {agent_name}'"
        ))

    # Pattern: "translated by X"
    pattern_translator = re.compile(r'translated by ([A-Z][A-Za-z\s.]+?)(?:\s+in|\s+between|$)', re.IGNORECASE)
    for match in pattern_translator.finditer(query):
        agent_name = match.group(1).strip()
        filters.append(Filter(
            field=FilterField.AGENT_ROLE,
            op=FilterOp.EQUALS,
            value="translator",
            notes=f"role filter from 'translated by'"
        ))
        filters.append(Filter(
            field=FilterField.AGENT_NORM,
            op=FilterOp.CONTAINS,
            value=agent_name.lower(),
            notes=f"agent name from 'translated by {agent_name}'"
        ))

    # Pattern: "books by X" (ambiguous role - could be author, printer, publisher)
    pattern_by = re.compile(r'books by ([A-Z][A-Za-z\s.]+?)(?:\s+in|\s+between|$)', re.IGNORECASE)
    for match in pattern_by.finditer(query):
        agent_name = match.group(1).strip()
        filters.append(Filter(
            field=FilterField.AGENT_NORM,
            op=FilterOp.CONTAINS,
            value=agent_name.lower(),
            notes=f"agent name from 'books by {agent_name}' (role ambiguous: could be author/printer/publisher)"
        ))

    return filters
```

**Update main compile function** (lines 210-249):

```python
def compile_query(query_text: str) -> QueryPlan:
    """Compile natural language query to QueryPlan."""
    filters = []

    # Existing parsers...
    filters.extend(parse_publisher(query_text))
    filters.extend(parse_year_range(query_text))
    filters.extend(parse_place(query_text))
    filters.extend(parse_language(query_text))

    # NEW: Agent+role parsing
    filters.extend(parse_agent_with_role(query_text))

    # Remove duplicates, validate
    filters = _deduplicate_filters(filters)

    plan = QueryPlan(
        query_text=query_text,
        filters=filters,
        soft_filters=[],
        limit=None,
        debug={"compiler_version": "1.1.0", "agent_support": True}
    )

    return plan
```

---

### 5.3 Update SQL Generator

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/query/execute.py`

**Current function**: `build_full_query()` (lines 48-154)

**Add agent join logic**:

```python
def build_full_query(plan: QueryPlan) -> str:
    """Generate SQL from QueryPlan with agent support."""
    base_select = "SELECT DISTINCT r.record_id"
    tables = {"r": "records r"}
    where_clauses = []
    params_placeholder = []

    # Track if we need to join agents table
    needs_agent_join = False

    for filter_obj in plan.filters:
        if filter_obj.field in [FilterField.AGENT_NORM, FilterField.AGENT_ROLE, FilterField.AGENT_TYPE]:
            needs_agent_join = True

        # ... existing filter logic for other fields ...

        # NEW: Agent filters
        if filter_obj.field == FilterField.AGENT_NORM:
            if filter_obj.op == FilterOp.EQUALS:
                where_clauses.append("LOWER(a.agent_norm) = LOWER(?)")
                params_placeholder.append(filter_obj.value)
            elif filter_obj.op == FilterOp.CONTAINS:
                where_clauses.append("LOWER(a.agent_norm) LIKE LOWER(?)")
                params_placeholder.append(f"%{filter_obj.value}%")

        elif filter_obj.field == FilterField.AGENT_ROLE:
            where_clauses.append("a.role_norm = ?")
            params_placeholder.append(filter_obj.value)

        elif filter_obj.field == FilterField.AGENT_TYPE:
            where_clauses.append("a.agent_type = ?")
            params_placeholder.append(filter_obj.value)

    # Build JOIN clauses
    joins = []
    if needs_agent_join:
        tables["a"] = "agents a"
        joins.append("JOIN agents a ON a.record_id = r.record_id")

    # ... existing join logic for imprints, titles, etc. ...

    # Assemble SQL
    sql_parts = [base_select]
    sql_parts.append(f"FROM {tables['r']}")
    sql_parts.extend(joins)

    if where_clauses:
        sql_parts.append(f"WHERE {' AND '.join(where_clauses)}")

    return '\n'.join(sql_parts)
```

---

### 5.4 Update Evidence Extraction

**File to modify**: `/home/hagaybar/projects/rare-books-bot/scripts/query/execute.py`

**Add new evidence extractor**:

```python
def extract_agent_evidence(
    cursor: sqlite3.Cursor,
    record_id: str,
    filter_obj: Filter
) -> List[Evidence]:
    """Extract evidence for agent-based filters."""
    evidence_list = []

    # Query agents table for this record
    cursor.execute(
        """
        SELECT
            agent_raw, agent_norm, agent_confidence,
            role_raw, role_norm, role_confidence,
            provenance_json
        FROM agents
        WHERE record_id = ?
        """,
        (record_id,)
    )

    for row in cursor.fetchall():
        agent_raw, agent_norm, agent_conf, role_raw, role_norm, role_conf, prov_json = row
        provenance = json.loads(prov_json)

        # Check if this agent matches the filter
        matches = False
        matched_value = None

        if filter_obj.field == FilterField.AGENT_NORM:
            if filter_obj.op == FilterOp.EQUALS and agent_norm.lower() == filter_obj.value.lower():
                matches = True
                matched_value = agent_norm
            elif filter_obj.op == FilterOp.CONTAINS and filter_obj.value.lower() in agent_norm.lower():
                matches = True
                matched_value = agent_norm

        elif filter_obj.field == FilterField.AGENT_ROLE:
            if role_norm == filter_obj.value:
                matches = True
                matched_value = role_norm

        if matches:
            # Build source string from provenance
            source_str = ", ".join([f"marc:{s['tag']}{s.get('path', '')}" for s in provenance])

            evidence_list.append(Evidence(
                field=f"agents.{filter_obj.field.value.lower()}",
                value=matched_value,
                operator=filter_obj.op.value,
                matched_against=filter_obj.value,
                source=source_str,
                confidence=agent_conf if filter_obj.field == FilterField.AGENT_NORM else role_conf,
                raw_value=agent_raw
            ))

    return evidence_list
```

**Update main evidence gathering** (lines 222-285):

```python
def extract_evidence_for_filter(
    cursor: sqlite3.Cursor,
    record_id: str,
    filter_obj: Filter
) -> List[Evidence]:
    """Extract evidence for a single filter."""
    # Existing logic for other fields...

    # NEW: Agent evidence
    if filter_obj.field in [FilterField.AGENT_NORM, FilterField.AGENT_ROLE, FilterField.AGENT_TYPE]:
        return extract_agent_evidence(cursor, record_id, filter_obj)

    # ... rest of existing code ...
```

---

## Stage 6 — QA/UI Integration

### 6.1 DB Explorer: Add Agents Table

**File to modify**: `/home/hagaybar/projects/rare-books-bot/app/ui_qa/pages/5_db_explorer.py`

**Current state**: Already has table browser with "agents" in table list (line 45)

**Required changes**:

1. **Update schema display** (around lines 60-120):

```python
table_schemas = {
    # ... existing schemas ...
    "agents": """
    Enhanced agents table (M1 raw + M2 normalized):
    - agent_raw: Original name string from MARC
    - agent_type: personal | corporate | meeting
    - role_raw: Raw role from MARC (may be code/term/inferred)
    - agent_norm: Normalized canonical name (lowercase, no punctuation)
    - role_norm: Controlled vocabulary role
    - agent_confidence: 0.0-1.0 (normalization confidence)
    - role_confidence: 0.0-1.0 (role mapping confidence)
    - provenance_json: Source MARC fields (JSON array)
    """,
}
```

2. **Update sample queries** (add agent query examples):

```python
sample_queries = {
    "agents": [
        "SELECT agent_norm, role_norm, COUNT(*) as count FROM agents GROUP BY agent_norm, role_norm ORDER BY count DESC LIMIT 50",
        "SELECT DISTINCT agent_norm FROM agents WHERE role_norm = 'printer' ORDER BY agent_norm",
        "SELECT * FROM agents WHERE agent_confidence < 0.9",  # Low confidence agents
        "SELECT a.*, r.title_main FROM agents a JOIN records r ON a.record_id = r.record_id WHERE a.agent_norm LIKE '%manutius%'",
    ],
}
```

---

### 6.2 Run+Review: Show Agent Evidence

**File to modify**: `/home/hagaybar/projects/rare-books-bot/app/ui_qa/pages/1_run_review.py`

**Location**: Candidate sidebar display (around lines 250-350)

**Add agent evidence display**:

```python
def display_candidate_details(candidate: Candidate, record_data: dict):
    """Show candidate match details including agent evidence."""
    st.subheader("Match Evidence")

    # Group evidence by field type
    agent_evidence = [e for e in candidate.evidence if e.field.startswith('agents.')]
    other_evidence = [e for e in candidate.evidence if not e.field.startswith('agents.')]

    # Display agent evidence separately
    if agent_evidence:
        st.markdown("**Agent Matches:**")
        for ev in agent_evidence:
            with st.expander(f"{ev.field}: {ev.value} (confidence: {ev.confidence:.2f})"):
                st.markdown(f"- **Raw value**: {ev.raw_value}")
                st.markdown(f"- **Matched against**: {ev.matched_against}")
                st.markdown(f"- **Operator**: {ev.operator}")
                st.markdown(f"- **Source**: {ev.source}")
                if ev.confidence < 0.9:
                    st.warning(f"Low confidence ({ev.confidence:.2f}) - review recommended")

    # Display other evidence
    if other_evidence:
        st.markdown("**Other Evidence:**")
        for ev in other_evidence:
            st.markdown(f"- {ev.field}: {ev.value}")

    # Display full record agents
    st.markdown("**All Agents in Record:**")
    # Query database for full agent list...
```

---

### 6.3 QA Issue Tags: Add Agent-Specific Tags

**File to modify**: `/home/hagaybar/projects/rare-books-bot/app/ui_qa/db.py`

**Update issue tag enum** (around line 30):

```python
ISSUE_TAGS = [
    # Existing tags
    "NORM_PLACE_BAD",
    "NORM_PUBLISHER_BAD",
    "NORM_DATE_BAD",
    "PARSER_IMPRINT_BAD",
    "PARSER_TITLE_BAD",
    "QUERY_PLAN_BAD",

    # NEW: Agent-specific tags
    "NORM_AGENT_BAD",        # Agent name normalization incorrect
    "ROLE_MAP_BAD",          # Role mapping incorrect (wrong role assigned)
    "PARSER_AGENT_MISSED",   # Parser failed to extract an agent
    "PARSER_AGENT_WRONG",    # Parser extracted wrong agent or corrupt data
    "AGENT_AMBIGUOUS",       # Agent identity ambiguous (needs manual review)
]
```

**Update issue tracking UI** (in labeling page):

```python
# In candidate labeling form
issue_tags_agent = st.multiselect(
    "Agent-related issues (if any):",
    options=[
        "NORM_AGENT_BAD",
        "ROLE_MAP_BAD",
        "PARSER_AGENT_MISSED",
        "PARSER_AGENT_WRONG",
        "AGENT_AMBIGUOUS"
    ],
    help="Tag specific agent extraction/normalization problems"
)
```

---

## Stage 7 — Minimal Vertical Slice (Execution Order)

### Phase 1: Core Infrastructure (No UI changes yet)

**Tasks**:
1. **M1: Update models and extraction**
   - [ ] Modify `scripts/marc/models.py`: Add fields to `AgentData`
   - [ ] Modify `scripts/marc/parse.py`: Expand `extract_agents()` to include 110/710/111/711, extract roles
   - [ ] Write tests: `tests/scripts/marc/test_parse.py` (agent extraction)
   - [ ] Run tests: `pytest tests/scripts/marc/test_parse.py -k agent`

2. **M2: Add normalization logic**
   - [ ] Create `scripts/marc/m2_models.py`: Add `AgentNormalization`, `RoleNormalization`
   - [ ] Create `scripts/normalization/normalize_agent.py`: Implement `normalize_agent_base()`, `normalize_role_base()`
   - [ ] Modify `scripts/marc/normalize.py`: Add `normalize_agents()`, integrate into `enrich_m2()`
   - [ ] Write tests: `tests/scripts/normalization/test_normalize_agent.py`
   - [ ] Run tests: `pytest tests/scripts/normalization/test_normalize_agent.py`

3. **M3: Update database schema and indexing**
   - [ ] Modify `scripts/marc/m3_schema.sql`: Replace agents table with enhanced schema
   - [ ] Modify `scripts/marc/m3_index.py`: Update `_insert_agents()`, integrate M2 agent data
   - [ ] Test: Re-index a small dataset and verify agents table structure
   - [ ] Run: `sqlite3 data/index/records.db ".schema agents"` (verify schema)

4. **M4: Update QueryPlan and compiler**
   - [ ] Modify `scripts/schemas/query_plan.py`: Add `AGENT_NORM`, `AGENT_ROLE`, `AGENT_TYPE` to `FilterField`
   - [ ] Modify `scripts/query/compile.py`: Add `parse_agent_with_role()`
   - [ ] Modify `scripts/query/execute.py`: Update `build_full_query()`, add `extract_agent_evidence()`
   - [ ] Write tests: `tests/scripts/query/test_compile.py`, `test_execute.py` (agent queries)
   - [ ] Run tests: `pytest tests/scripts/query/ -k agent`

5. **Integration test**
   - [ ] Run full pipeline: MARC XML → M1 → M2 → M3 → M4
   - [ ] Test query: "printed by Aldus Manutius" → verify QueryPlan, SQL, CandidateSet
   - [ ] Verify Evidence includes agent provenance (MARC field pointers)

### Phase 2: UI Integration

**Tasks**:
6. **DB Explorer**
   - [ ] Modify `app/ui_qa/pages/5_db_explorer.py`: Update agents table schema display, add sample queries
   - [ ] Test: Browse agents table, run sample queries

7. **Run+Review**
   - [ ] Modify `app/ui_qa/pages/1_run_review.py`: Display agent evidence in candidate sidebar
   - [ ] Test: Run query with agent filter, verify evidence display

8. **QA Issue Tags**
   - [ ] Modify `app/ui_qa/db.py`: Add agent-specific issue tags
   - [ ] Test: Label candidates with agent issues, verify tags persist

### Phase 3: LLM Utility (Optional, for refinement)

**Tasks**:
9. **Agent alias map generator**
   - [ ] Create `scripts/normalization/generate_agent_alias_map.py` (mirror place alias pattern)
   - [ ] Implement LLM canonicalization prompt (AI Prompt 1)
   - [ ] Add validation guardrails
   - [ ] Create data directory: `data/normalization/agent_aliases/`
   - [ ] Generate alias map from real data
   - [ ] Review proposed mappings (manual QA)
   - [ ] Commit `agent_alias_map.json` to git

10. **Re-index with alias map**
    - [ ] Re-run M2 normalization with agent alias map
    - [ ] Re-run M3 indexing
    - [ ] Re-run test queries, verify improved canonicalization

---

## Testing Strategy

### Unit Tests

1. **M1 Extraction** (`tests/scripts/marc/test_parse.py`)
   - Test personal name extraction (100, 700)
   - Test corporate body extraction (110, 710)
   - Test meeting extraction (111, 711)
   - Test role extraction priority: $4 > $e > inferred
   - Test provenance tracking

2. **M2 Normalization** (`tests/scripts/normalization/test_normalize_agent.py`)
   - Test `normalize_agent_base()` edge cases (brackets, punctuation, whitespace)
   - Test `normalize_role_base()` all relator codes/terms
   - Test confidence scoring

3. **M3 Indexing** (`tests/scripts/marc/test_m3_index.py`)
   - Test agent insertion with M1+M2 data
   - Test provenance JSON serialization
   - Verify indexes exist

4. **M4 Query** (`tests/scripts/query/test_compile.py`, `test_execute.py`)
   - Test `parse_agent_with_role()` patterns
   - Test SQL generation with agent JOINs
   - Test evidence extraction for agent filters

### Integration Tests

1. **End-to-end pipeline test**
   - Input: Small MARC XML file with known agents (5-10 records)
   - Expected: Correct agents extracted, normalized, indexed, queryable
   - Verification: Run query "printed by X", verify CandidateSet matches expectations

2. **Golden set regression**
   - Add agent queries to golden set: `tests/data/golden_set.yaml`
   - Run: `pytest tests/scripts/query/test_golden.py`
   - Verify: All agent queries return expected candidate counts

### Manual QA Tests

1. **QA Wizard SMOKE test**
   - Query: "books printed by Aldus Manutius in Venice between 1500-1520"
   - Verify: QueryPlan shows agent filters, SQL includes agents JOIN, evidence shows role_norm=printer

2. **DB Explorer**
   - Browse agents table, verify schema
   - Run sample queries, verify results

3. **Run+Review**
   - Label candidates, verify agent evidence display
   - Tag issues with new agent-specific tags

---

## Success Criteria

### Functional Requirements

- [ ] Query "printed by X" compiles to QueryPlan with AGENT_ROLE=printer + AGENT_NORM=x
- [ ] SQL includes `JOIN agents` and filters on `role_norm` and `agent_norm`
- [ ] CandidateSet includes Evidence with:
  - `field`: "agents.agent_norm" or "agents.role_norm"
  - `value`: matched normalized agent/role
  - `source`: MARC provenance (e.g., "marc:700[1]$a")
  - `confidence`: normalization confidence score
- [ ] DB Explorer shows enhanced agents table with M1+M2 fields
- [ ] Run+Review displays agent evidence in candidate sidebar

### Data Quality Requirements

- [ ] Agent extraction: 100% recall on 100/700 personal names, 110/710 corporate bodies
- [ ] Role extraction: >95% accuracy on relator codes ($4), >90% on relator terms ($e)
- [ ] Agent normalization: >85% base confidence, >95% with alias map
- [ ] Role normalization: >95% accuracy with deterministic mapping

### Non-Functional Requirements

- [ ] All changes follow deterministic-first philosophy (no LLM in M1-M4 core)
- [ ] Raw values always preserved (non-destructive normalization)
- [ ] Confidence scores tracked at every step
- [ ] Provenance maintained (MARC field pointers in Evidence)
- [ ] Backward compatible: existing queries still work

---

## Risk Mitigation

### Risk 1: Dirty relator codes/terms in MARC data

**Mitigation**:
- Start with deterministic mapping (Stage 3.1)
- Analyze unmapped roles: `SELECT role_raw, COUNT(*) FROM agents WHERE role_norm='other' GROUP BY role_raw`
- Incrementally expand mapping table based on real data
- Only add LLM role normalization (AI Prompt 2) if >10% unmapped

### Risk 2: Agent name variants not unified

**Mitigation**:
- Phase 1: Ship with base normalization only (confidence 0.80)
- Phase 3: Add agent alias map generation with LLM (confidence 0.95)
- Manual QA review: sample 50-100 high-frequency agents, verify canonical forms
- Iterate on alias map based on QA feedback

### Risk 3: Performance degradation (agents JOIN)

**Mitigation**:
- Composite index: `(agent_norm, role_norm)` for fast "printer X" queries
- Benchmark before/after: measure query latency for agent filters
- If slow: consider materialized view or denormalized agent fields in records table

### Risk 4: Ambiguous agent identities (same name, different people)

**Mitigation**:
- LLM prompt includes AMBIGUOUS decision option
- Mark ambiguous agents with decision="AMBIGUOUS", canonical="ambiguous"
- QA issue tag: "AGENT_AMBIGUOUS" for manual review
- Future enhancement: authority control (link to VIAF, LCNAF)

---

## Future Enhancements (Post-MVP)

1. **Authority control**: Link agents to external authorities (VIAF, LCNAF, Wikidata)
2. **Agent faceting**: Add agent facets to UI (browse by printer, translator, etc.)
3. **Agent relationships**: Model relationships (e.g., "X translated Y's work")
4. **Agent timeline**: Visualize agent activity over time (publication years)
5. **Agent disambiguation**: Use additional context (dates, places) to resolve ambiguity

---

## File Manifest (All Changes)

### New Files
- `scripts/normalization/normalize_agent.py` (agent/role normalization logic)
- `scripts/normalization/generate_agent_alias_map.py` (LLM-assisted alias generation)
- `tests/scripts/normalization/test_normalize_agent.py` (normalization tests)
- `data/normalization/agent_aliases/agent_alias_map.json` (production alias map)
- `data/normalization/agent_aliases/agent_alias_cache.jsonl` (LLM cache, gitignored)
- `data/normalization/agent_aliases/agent_alias_proposed.csv` (review file, gitignored)

### Modified Files
- `scripts/marc/models.py` (add fields to AgentData)
- `scripts/marc/parse.py` (expand extract_agents)
- `scripts/marc/m2_models.py` (add AgentNormalization, RoleNormalization)
- `scripts/marc/normalize.py` (add normalize_agents)
- `scripts/marc/m3_schema.sql` (enhance agents table)
- `scripts/marc/m3_index.py` (update _insert_agents)
- `scripts/schemas/query_plan.py` (add AGENT_NORM, AGENT_ROLE, AGENT_TYPE)
- `scripts/query/compile.py` (add parse_agent_with_role)
- `scripts/query/execute.py` (update SQL generation, add extract_agent_evidence)
- `app/ui_qa/pages/5_db_explorer.py` (update agents table display)
- `app/ui_qa/pages/1_run_review.py` (display agent evidence)
- `app/ui_qa/db.py` (add agent issue tags)
- `tests/scripts/marc/test_parse.py` (agent extraction tests)
- `tests/scripts/query/test_compile.py` (agent query compilation tests)
- `tests/scripts/query/test_execute.py` (agent evidence tests)

---

## Estimated Scope

- **Phase 1 (Core Infrastructure)**: 3-5 days (deterministic, testable)
- **Phase 2 (UI Integration)**: 1-2 days (straightforward UI updates)
- **Phase 3 (LLM Utility)**: 2-3 days (includes alias map generation + QA review)

**Total**: 6-10 days for full integration (with testing and QA)

---

## Next Steps

1. Review this plan with stakeholders
2. Prioritize phases (can ship Phase 1+2 without Phase 3)
3. Set up test data (small MARC XML file with diverse agent examples)
4. Begin implementation with M1 extraction changes
5. Iterate with testing and QA feedback

---

**Document Status**: Ready for review
**Last Updated**: 2026-01-11
