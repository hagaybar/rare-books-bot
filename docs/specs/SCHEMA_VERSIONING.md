# M3 Schema Versioning Strategy

## Overview

This document defines the versioning strategy for the M3 database schema (`scripts/marc/m3_schema.sql`) and its contract (`scripts/marc/m3_contract.py`). The goal is to enable schema evolution while maintaining backward compatibility and preventing silent breakage.

## Core Principles

### 1. Explicit Contracts

- **M3 Schema** (`m3_schema.sql`): Defines the database structure (tables, columns, indexes, triggers)
- **M3 Contract** (`m3_contract.py`): Defines constants for table and column names used by query builder
- **Schema Validation Test** (`test_m3_contract_matches_schema()`): Ensures contract matches actual schema

### 2. Schema as Source of Truth

The schema file (`m3_schema.sql`) is the single source of truth for database structure. Changes flow:

```
m3_schema.sql → database → m3_contract.py → db_adapter.py
```

**Process:**
1. Modify `m3_schema.sql` to add/modify schema
2. Update `m3_contract.py` to reflect changes
3. Update `db_adapter.py` if query logic changes
4. Run `test_m3_contract_matches_schema()` to validate

### 3. Backward Compatibility

Schema changes should maintain backward compatibility with existing data and queries where possible.

## Change Classification

### Non-Breaking Changes (Safe)

These changes do NOT require database migration:

- **Add new column** (with nullable or default value)
  ```sql
  ALTER TABLE imprints ADD COLUMN new_field TEXT;
  ```
  - Update `m3_contract.py` to add constant
  - Update `test_m3_contract_matches_schema()` to validate
  - No query builder changes needed (optional field)

- **Add new table**
  ```sql
  CREATE TABLE new_table (...);
  ```
  - Update `m3_contract.py` to add table and column constants
  - Update test to validate new table
  - Query builder changes only if new queries needed

- **Add new index**
  ```sql
  CREATE INDEX idx_new ON table(column);
  ```
  - No contract changes needed (indexes are internal optimization)

### Breaking Changes (Requires Migration)

These changes REQUIRE database migration:

- **Remove column**: Data loss, queries will break
- **Rename column**: Queries will break
- **Rename table**: Queries will break
- **Change column type**: Potential data loss, queries may break
- **Add NOT NULL constraint**: Fails if existing rows have NULL

**Migration Required For:**
- Any change that affects existing data
- Any change that breaks existing queries
- Any change to table/column names

## Versioning Scheme

### Schema Version Field

Add version tracking to records table:

```sql
CREATE TABLE records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mms_id TEXT NOT NULL UNIQUE,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    jsonl_line_number INTEGER NOT NULL,
    schema_version TEXT DEFAULT '1.0'  -- Add version field
);
```

Version format: `MAJOR.MINOR`
- **MAJOR**: Incremented for breaking changes (requires migration)
- **MINOR**: Incremented for backward-compatible changes (no migration)

### Contract Version

Add version constant to `m3_contract.py`:

```python
class M3Schema:
    """M3 schema metadata."""
    VERSION = "1.0"
    LAST_UPDATED = "2025-01-12"
```

## Migration Strategy

### For Non-Breaking Changes

1. Update `m3_schema.sql` with new field
2. Increment MINOR version in schema
3. Update `m3_contract.py` constants
4. Run tests to validate
5. Deploy - existing databases will work

Example:
```sql
-- Add optional enrichment field
ALTER TABLE imprints ADD COLUMN place_geonames_id INTEGER;
-- Version 1.0 → 1.1
```

### For Breaking Changes

Breaking changes require full database rebuild. Follow this process:

1. **Assess Impact**: Identify all affected queries and data
2. **Create Migration Script**: Document transformation logic
3. **Increment MAJOR Version**: Version 1.x → 2.0
4. **Update Contract**: Modify `m3_contract.py` for new schema
5. **Update Query Builder**: Modify `db_adapter.py` as needed
6. **Update Tests**: Ensure all tests pass
7. **Rebuild Database**: Re-run M3 indexing pipeline

Example breaking change:
```sql
-- Rename column (BREAKING)
ALTER TABLE imprints RENAME COLUMN place_norm TO place_canonical;
-- Version 1.x → 2.0
-- Requires: db_adapter.py updates, full database rebuild
```

### Migration Documentation

Document each breaking change in `docs/migrations/`:

```
docs/migrations/
  v1.0_to_v2.0.md
  v2.0_to_v3.0.md
```

Include:
- **What Changed**: Schema modifications
- **Why**: Rationale for breaking change
- **Impact**: Affected queries and data
- **Rebuild Steps**: How to recreate database
- **Validation**: How to verify migration success

## Testing Requirements

### Schema Change Checklist

Before committing schema changes:

- [ ] Update `m3_schema.sql` with changes
- [ ] Update `m3_contract.py` with new/modified constants
- [ ] Update `test_m3_contract_matches_schema()` to validate new fields
- [ ] Run all M3 tests: `pytest tests/scripts/marc/test_m3_index.py`
- [ ] Run all query tests: `pytest tests/scripts/query/`
- [ ] Rebuild test database with new schema
- [ ] Verify existing queries work (or document breaking changes)

### Validation Tests

**Contract Validation**: `test_m3_contract_matches_schema()`
- Verifies all contract tables exist in database
- Verifies all contract columns exist in their tables
- Prevents silent breakage from schema drift

**Query Tests**: `tests/scripts/query/test_db_adapter.py`
- Ensures query builder generates valid SQL
- Validates JOIN logic and WHERE clauses
- Tests all filter types and operations

## Best Practices

### 1. Favor Additive Changes

When possible, add new columns/tables rather than modifying existing ones:

```sql
-- GOOD: Add new normalized field alongside raw
ALTER TABLE imprints ADD COLUMN place_geonames_id INTEGER;

-- AVOID: Replace existing field (breaking)
ALTER TABLE imprints DROP COLUMN place_norm;
ALTER TABLE imprints ADD COLUMN place_canonical TEXT;
```

### 2. Use Nullable Columns

New columns should be nullable or have defaults to avoid breaking existing data:

```sql
-- GOOD: Nullable new field
ALTER TABLE imprints ADD COLUMN place_confidence_v2 REAL;

-- AVOID: NOT NULL requires migration
ALTER TABLE imprints ADD COLUMN required_field TEXT NOT NULL;
```

### 3. Preserve M1 Raw Data

Never remove or modify M1 raw fields:
- `date_raw`, `place_raw`, `publisher_raw`, `agent_raw`, etc.

These fields are the source of truth and must be preserved for:
- Reproducibility: Re-run normalization with updated logic
- Auditing: Trace normalized values back to source
- Debugging: Investigate edge cases in raw data

### 4. Document Intent

Add comments to schema changes explaining the purpose:

```sql
-- Add GeoNames enrichment (2025-01-15)
-- Enables geographic querying and clustering by standardized place IDs
ALTER TABLE imprints ADD COLUMN place_geonames_id INTEGER;
ALTER TABLE imprints ADD COLUMN place_geonames_name TEXT;
```

## Rollback Strategy

### Non-Breaking Changes

Can be reverted without data loss:

```sql
-- Revert: Remove added column
ALTER TABLE imprints DROP COLUMN new_field;
```

### Breaking Changes

Require database rebuild from M1/M2 records:

1. Restore previous schema version
2. Re-run M3 indexing with previous schema
3. Validate queries work with old schema

**Prevention**: Always test breaking changes in a separate branch and database copy before production deployment.

## Version History

| Version | Date       | Type        | Changes |
|---------|------------|-------------|---------|
| 1.0     | 2025-01-12 | Initial     | Base M3 schema with M1 raw + M2 normalized fields |

## Related Documentation

- **M3 Schema**: `scripts/marc/m3_schema.sql`
- **M3 Contract**: `scripts/marc/m3_contract.py`
- **M3 Indexing**: `scripts/marc/m3_index.py`
- **Query Builder**: `scripts/query/db_adapter.py`
- **Schema Tests**: `tests/scripts/marc/test_m3_index.py::TestSchemaCreation`
- **Query Tests**: `tests/scripts/query/test_db_adapter.py`
