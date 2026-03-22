# Publisher Authority Records — Process Plan

## Goal

Save all publisher research and create an internal publisher authority record system in the rare books database.

## Phases

### Phase 1: Save Research Data
- Save all 29 researched publishers to `data/normalization/publisher_research.json`
- Create `data/normalization/publisher_aliases/publisher_alias_map.json`
- Scan DB for additional high-frequency publishers not yet researched

### Phase 2a: Design Schema
- Design `publisher_authorities` table (+ `publisher_variants` table)
- Follow existing patterns from `authority_enrichment` table
- Create Python CRUD module at `scripts/metadata/publisher_authority.py`
- Write unit tests

### Phase 2b: Test Schema on 10-15 Publishers
- Select diverse test cases (Elzevir, Bomberg, Insel, Grolier Club, חמו"ל, etc.)
- Create records, add variants, link to imprints
- Document issues and edge cases

### Phase 2c: Review & Refine (BREAKPOINT — user reviews schema)
- Address test issues
- Refine schema, update module, re-run tests
- Add publisher authority tables to m3_schema.sql

### Phase 2d: Create All Authority Records
- Populate for all 29 researched publishers
- Add stub records for unresearched high-frequency publishers
- Link all to imprint records
- Log changes

### Phase 3: Verification
- Integration tests
- Update documentation (CLAUDE.md, architecture doc)
- Run full test suite
