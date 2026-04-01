# Authority URI Integration Plan

**Date**: 2026-01-12
**Status**: Planning
**Target**: Support MARC XML with authority URIs in subfield $0 (tags 1XX, 6XX, 7XX)

---

## Overview

New MARC XML format includes subfield $0 in authority-controlled fields (1XX, 6XX, 7XX), containing URIs to authority records:

```xml
<subfield code="0">https://open-eu.hosted.exlibrisgroup.com/alma/972NNL_INST/authorities/987007261327805171.jsonld</subfield>
```

Authority records may contain Wikidata identifiers, enabling optional downstream enrichment.

**Example file**: `data/marc_source/enriched_datafields.txt`

---

## Current State Analysis

**M1 (Canonical Parsing)**:
- `AgentData` model (models.py:27-52): Captures 1XX/7XX fields with name, dates, role
- `SubjectData` model (models.py:55-63): Captures 6XX fields with value, parts, scheme
- Parser currently **skips subfield $0** (parse.py:176) along with $6 and $8
- Both models use `SourcedValue` for provenance tracking

**M3 (SQLite Index)**:
- `agents` table (m3_schema.sql:106-131): Includes normalized agent names and roles
- `subjects` table (m3_schema.sql:84-99): Includes display values and structured parts
- No current support for authority URIs in schema

---

## Integration Plan

### Phase 1: M1 Data Model Extension (Core Ingestion)

**Goal**: Capture authority URIs deterministically during MARC parsing, no external calls.

#### 1.1 Extend Data Models

**File**: `scripts/marc/models.py`

Add authority URI field to both `SubjectData` and `AgentData`:

```python
class SubjectData(BaseModel):
    # ... existing fields ...
    authority_uri: Optional[SourcedValue] = Field(
        None,
        description="Authority URI from $0 (e.g., Alma authority JSONLD link)"
    )

class AgentData(BaseModel):
    # ... existing fields ...
    authority_uri: Optional[SourcedValue] = Field(
        None,
        description="Authority URI from $0 (e.g., Alma authority JSONLD link)"
    )
```

**Rationale**:
- Keeps URIs at M1 layer (raw data)
- Uses existing `SourcedValue` pattern for provenance
- No assumptions about URI content or resolvability

#### 1.2 Update MARC Parser

**File**: `scripts/marc/parse.py`

**Change 1**: Modify `extract_subjects()` (line ~140-208)
- Currently skips $0 at line 176: `elif code not in ['0', '6', '8']:`
- Change to: `elif code not in ['6', '8']:`  (allow $0 through)
- Capture $0 value separately (don't include in display string)
- Store in `SubjectData.authority_uri`

**Change 2**: Modify agent extraction functions:
- `_extract_personal_agent()` (line ~276)
- `_extract_corporate_agent()` (line ~308)
- `_extract_meeting_agent()` (line ~354)

Each should:
- Extract $0 subfield via `field.get_subfields('0')`
- Store first occurrence in `authority_uri` field with source tracking
- If multiple $0 values exist, take first (log warning for investigation)

**Expected behavior**:
- If $0 present: capture URI with source like `700[0]$0`
- If $0 absent: `authority_uri = None` (no error, expected partial coverage)
- No validation of URI format (accept as-is)

#### 1.3 Update Tests

**File**: `tests/scripts/marc/test_parse.py`

Add test cases for:
- Subject with $0 URI (verify captured)
- Agent with $0 URI (verify captured)
- Subject/agent without $0 (verify None, no error)
- Multiple $0 values in one field (verify first taken, warning logged)

---

### Phase 2: M3 Index Schema Extension

**Goal**: Store authority URIs in queryable format for evidence/provenance.

#### 2.1 Extend Database Schema

**File**: `scripts/marc/m3_schema.sql`

**Change 1**: Add column to `subjects` table:
```sql
ALTER TABLE subjects ADD COLUMN authority_uri TEXT;  -- Alma authority JSONLD link from $0
CREATE INDEX idx_subjects_authority_uri ON subjects(authority_uri);
```

**Change 2**: Add column to `agents` table:
```sql
ALTER TABLE agents ADD COLUMN authority_uri TEXT;  -- Alma authority JSONLD link from $0
CREATE INDEX idx_agents_authority_uri ON agents(authority_uri);
```

**Rationale**:
- Simple TEXT column (URIs are strings, no special handling needed)
- Indexed for fast lookup (e.g., "find all records with this authority")
- NULL-safe (many records won't have URIs)

#### 2.2 Update Indexing Code

**File**: `scripts/marc/m3_index.py`

Modify subject and agent insertion logic to include `authority_uri` field:

```python
# For subjects (estimate line ~100-120):
cursor.execute(
    "INSERT INTO subjects (record_id, value, source_tag, scheme, heading_lang, parts, source, authority_uri) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (record_id, subject['value'], subject['source_tag'], ..., authority_uri_value)
)

# For agents (estimate line ~130-150):
cursor.execute(
    "INSERT INTO agents (..., authority_uri) VALUES (..., ?)",
    (..., authority_uri_value)
)
```

Where `authority_uri_value = agent.get('authority_uri', {}).get('value')` (extract from SourcedValue).

#### 2.3 Schema Version Management

**File**: `scripts/marc/m3_index.py`

Current schema has no versioning. Recommend:
- Add `schema_version` to database metadata (e.g., in `records` table or separate `metadata` table)
- Current version: `1.0` (implicit)
- New version: `1.1` (adds authority_uri columns)
- Add migration logic or require rebuild with warning

**Migration strategy** (choose one):
- **Option A** (recommended for POC): Drop and rebuild database (existing pattern)
- **Option B**: Add ALTER TABLE migration for backwards compatibility

---

### Phase 3: Query Execution Support

**Goal**: Make authority URIs available in evidence output for transparency.

#### 3.1 Update Evidence Extraction

**File**: `scripts/query/db_adapter.py`

When evidence is returned for agents/subjects, include `authority_uri` field:

```python
# In evidence dictionaries:
{
    "agent_name": "...",
    "authority_uri": "https://...",  # Include if present
    ...
}
```

This allows users to see which entities are authority-linked.

#### 3.2 Query Planning (Optional)

**File**: `scripts/query/llm_compiler.py`

No immediate changes needed, but document capability:
- Queries like "books by authority 987007261327805171" could be supported
- LLM compiler would need to recognize authority ID patterns
- Low priority: Most users won't know authority IDs upfront

---

### Phase 4: Authority Enrichment Layer (Optional, External)

**Goal**: Enable optional Wikidata enrichment without blocking core pipeline.

#### 4.1 Design Principles

**Separation of concerns**:
- **Core pipeline** (M1→M2→M3): Deterministic, no network calls, always runs
- **Enrichment layer**: External process, cached, can fail gracefully

**Proposed architecture**:
```
M1+M2 JSONL records
    ↓
[Optional] Authority Resolver
    → Fetch authority records from Alma URIs
    → Extract Wikidata IDs if present
    → Cache results in `data/authority_cache/`
    ↓
M3 Index (with optional enrichment metadata)
```

#### 4.2 Authority Cache Design

**Storage**: `data/authority_cache/authority_cache.jsonl`

Format:
```json
{
  "authority_uri": "https://open-eu.hosted.exlibrisgroup.com/alma/.../987007261327805171.jsonld",
  "fetched_at": "2026-01-12T10:00:00Z",
  "status": "success",
  "wikidata_id": "Q12345",
  "label": "...",
  "error_message": null,
  "confidence": 0.95
}
```

**Key features**:
- Append-only JSONL (git-ignored)
- TTL-based refresh (e.g., 90 days)
- Graceful degradation: if fetch fails, continue without enrichment

#### 4.3 Integration Points

**Option A**: Extend M2 normalization
- Add optional `--enrich-authorities` flag to `m2_normalize.py`
- Reads authority_uri from M1, fetches if not cached, appends to M2
- Fits existing M2 pattern (append-only enrichment)

**Option B**: Separate M4 enrichment step
- New script: `scripts/enrichment/authority_resolver.py`
- Runs after M3 indexing
- Updates separate `authority_metadata` table in SQLite

**Recommendation**: Option A (M2 extension) for consistency with existing pipeline.

#### 4.4 Schema Extension for Enrichment

If pursuing enrichment, add to M3 schema:

```sql
CREATE TABLE authority_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    authority_uri TEXT NOT NULL UNIQUE,
    wikidata_id TEXT,
    label TEXT,
    fetched_at TEXT NOT NULL,
    confidence REAL,
    error_message TEXT
);

CREATE INDEX idx_authority_wikidata ON authority_metadata(wikidata_id);
```

Then join to `agents`/`subjects` via `authority_uri`.

---

## Uncertainty and Partial Coverage

### Expected Coverage Patterns

1. **Not all records will have authority URIs**
   - Older records may lack $0 subfields
   - Some cataloging workflows don't include authorities
   - **Handling**: NULL values in database, filter queries as needed

2. **Not all authority URIs resolve**
   - Broken links, server errors, access restrictions
   - **Handling**: Cache fetch errors, continue without enrichment

3. **Not all authority records have Wikidata IDs**
   - Wikidata linking is incomplete for many entities
   - **Handling**: Store NULL for wikidata_id, don't fail

4. **URI format may vary**
   - Current example: Alma JSONLD links
   - Could include LOC authorities, VIAF, etc.
   - **Handling**: Store as-is, pattern matching in queries if needed

### Risk Mitigation

- **Core pipeline** (M1→M3) must never fail due to missing/invalid authority URIs
- Use optional fields and NULL-safe queries
- Log warnings for investigation, not errors
- Enrichment layer can fail independently without blocking queries

---

## Implementation Order

**Priority 1** (Core functionality):
1. Extend data models (Phase 1.1)
2. Update parser (Phase 1.2)
3. Update tests (Phase 1.3)
4. Extend schema (Phase 2.1)
5. Update indexing (Phase 2.2)
6. Update evidence extraction (Phase 3.1)

**Priority 2** (Quality of life):
7. Schema versioning (Phase 2.3)
8. Query planning for authority IDs (Phase 3.2)

**Priority 3** (Optional enrichment):
9. Authority cache design (Phase 4.2)
10. M2 enrichment extension (Phase 4.3)
11. Schema for enrichment metadata (Phase 4.4)

**Estimated effort**:
- Priority 1: ~4-6 hours (core changes are straightforward)
- Priority 2: ~2-3 hours (infrastructure improvements)
- Priority 3: ~6-10 hours (external API integration, error handling)

---

## Open Questions for Clarification

1. **Schema migration strategy**: Rebuild database or add migration support?
2. **Authority enrichment timeline**: Implement now or defer until core ingestion is validated?
3. **Multiple $0 values**: Take first, take last, or store all? (Recommend: first, log others)
4. **URI validation**: Accept any string or validate URL format? (Recommend: accept as-is)

---

## Summary

This plan maintains strict separation between deterministic core ingestion and optional enrichment, ensuring the system remains reliable while enabling future enhancements.

**Core principle**: Authority URIs are captured as raw data in M1, indexed in M3 for evidence/provenance, and can optionally be enriched in a separate non-blocking process.
