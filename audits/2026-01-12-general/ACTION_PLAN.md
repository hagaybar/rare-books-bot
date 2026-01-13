# Action Plan

**Date:** 2026-01-12
**Project:** rare-books-bot
**Based on:** AUDIT_REPORT.md and FINDINGS.yaml

---

## Execution Principles

1. **Fix P0 findings first** - None identified (excellent!)
2. **Each step references findings** - Trace actions back to FINDINGS.yaml
3. **Include rollback notes** - Document how to revert if needed
4. **Minimal changes** - Only what's necessary to address findings
5. **Delegate implementation** - Use python-dev-expert skill for code changes

---

## Phase 1: Critical Fixes (P0)

**No P0 findings identified.** The core MARC processing pipeline (M1-M3) is production-ready with no correctness, data loss, or contract breakage issues.

---

## Phase 2: High Priority (P1)

### Action 2.1: Document QA Tool Status and Boundaries
- **Addresses:** Finding F001
- **Description:** Clarify whether ui_qa is a development tool or production feature. Document scope boundaries and relationship to core pipeline in CLAUDE.md and README.md.
- **Scope:** CLAUDE.md, README.md (documentation only)
- **Delegated to:** Direct (no code changes)
- **Acceptance criteria:**
  - [ ] Add "## QA Tool Architecture" section to CLAUDE.md describing:
    - Purpose: Development tool for M4 quality assurance
    - Scope: Query labeling, issue tracking, gold set management, regression testing
    - Database: data/qa/qa.db (separate from production bibliographic.db)
    - Status: Maintained as part of core repository (decision documented)
  - [ ] Update README.md "Current Status" section to mention QA tool
  - [ ] Add note to app/ui_qa/README.md clarifying this is a development tool
- **Rollback:** Git revert documentation changes

### Action 2.2: Add LLM Failure Handling and Tests
- **Addresses:** Finding F002
- **Description:** Implement graceful error handling for OpenAI API failures in M4 query compilation. Add integration tests for failure scenarios.
- **Scope:** scripts/query/llm_compiler.py, scripts/query/compile.py, tests/scripts/query/, app/cli.py
- **Delegated to:** python-dev-expert
- **Acceptance criteria:**
  - [ ] Add try/except in compile_query_with_llm() for OpenAI API errors
  - [ ] Raise custom exception (e.g., QueryCompilationError) with clear message
  - [ ] Update app/cli.py to catch QueryCompilationError and display helpful message:
    - "Error: M4 query compilation requires OpenAI API"
    - "Please set OPENAI_API_KEY environment variable"
    - "See CLAUDE.md:198-199 for setup instructions"
  - [ ] Add integration test: test_llm_compiler_missing_api_key()
  - [ ] Add integration test: test_llm_compiler_api_timeout() (mock timeout)
  - [ ] Add integration test: test_llm_compiler_invalid_response() (mock malformed JSON)
  - [ ] Update README.md to prominently mention OpenAI API requirement for M4
- **Rollback:** Git revert; existing behavior (raise on API error) is restored

### Action 2.3: Validate Normalization Confidence Scores
- **Addresses:** Finding F003
- **Description:** Empirically validate that M2 normalization confidence scores (0.80, 0.95, 0.99) correlate with actual accuracy. Sample 100-200 records, manually validate, calculate precision/recall.
- **Scope:** Manual validation + documentation update (no code changes initially)
- **Delegated to:** Direct (requires human judgment)
- **Acceptance criteria:**
  - [ ] Sample 200 normalized records stratified by confidence level:
    - 50 date normalizations (0.95-0.99 high, 0.80-0.85 medium)
    - 50 place normalizations (0.95 with alias map, 0.80 base only)
    - 50 publisher normalizations (0.95 with alias map, 0.80 base only)
    - 50 agent normalizations (0.95 with alias map, 0.80 base only)
  - [ ] Manually validate each normalization as correct/incorrect
  - [ ] Calculate precision per confidence level
  - [ ] Create data/normalization/validation_report.json with results
  - [ ] Update CLAUDE.md confidence score documentation with one of:
    - If validated: "Empirically validated: 0.95 = 95%+ precision"
    - If not validated: "Heuristic confidence scores (not yet validated against ground truth)"
  - [ ] If scores don't correlate: Adjust formulas or add "Pending Validation" warnings
- **Rollback:** Documentation-only change; can revert if needed

---

## Phase 3: Medium Priority (P2)

### Action 3.1: Create M3/M4 Schema Contract
- **Addresses:** Finding F004
- **Description:** Explicit contract between M3 database schema and M4 query builder to prevent silent breakage on schema changes.
- **Scope:** scripts/marc/m3_contract.py (new), scripts/query/db_adapter.py, tests/scripts/marc/, tests/scripts/query/
- **Delegated to:** python-dev-expert
- **Acceptance criteria:**
  - [ ] Create scripts/marc/m3_contract.py with constants:
    ```python
    # M3 Database Schema Contract
    # Used by M4 query builder to reference tables and columns

    class M3Tables:
        RECORDS = "records"
        TITLES = "titles"
        IMPRINTS = "imprints"
        SUBJECTS = "subjects"
        AGENTS = "agents"
        LANGUAGES = "languages"
        NOTES = "notes"

    class M3Columns:
        # records table
        RECORD_ID = "record_id"

        # imprints table
        PLACE_NORM = "place_norm"
        PUBLISHER_NORM = "publisher_norm"
        DATE_START = "date_start"
        DATE_END = "date_end"
        # ... etc
    ```
  - [ ] Update scripts/query/db_adapter.py to import and use M3Tables, M3Columns constants
  - [ ] Add test: test_m3_schema_matches_contract() validating actual database schema
  - [ ] Document schema versioning strategy in docs/specs/SCHEMA_VERSIONING.md
- **Rollback:** Git revert; revert db_adapter.py to use hardcoded strings

### Action 3.2: Add Schema Versioning to Data Models
- **Addresses:** Finding F005
- **Description:** Add version field to CanonicalRecord, M2EnrichedRecord, CandidateSet for backward compatibility and migration support.
- **Scope:** scripts/marc/models.py, scripts/marc/m2_models.py, scripts/schemas/candidate_set.py, tests/
- **Delegated to:** python-dev-expert
- **Acceptance criteria:**
  - [ ] Add `version: str = "1.0"` field to CanonicalRecord (scripts/marc/models.py)
  - [ ] Add `version: str = "1.0"` field to M2EnrichedRecord (scripts/marc/m2_models.py)
  - [ ] Add `version: str = "1.0"` field to CandidateSet (scripts/schemas/candidate_set.py)
  - [ ] Update parsing logic to check version on load (raise error if mismatch)
  - [ ] Create docs/specs/SCHEMA_VERSIONING.md documenting:
    - Current versions
    - Migration strategy (backward compatibility policy)
    - How to increment versions
  - [ ] Add tests: test_version_mismatch_error() for each model
  - [ ] Update all existing test fixtures to include version field
- **Rollback:** Git revert; revert models to version-less state; may break existing JSONL files with version field (migration required)

### Action 3.3: Add Place Alias Map Schema Validation
- **Addresses:** Finding F006
- **Description:** Create Pydantic model for place_alias_map.json and validate on load to prevent silent failures from malformed alias maps.
- **Scope:** scripts/marc/m2_models.py (or new m2_schemas.py), scripts/marc/m2_normalize.py, tests/scripts/marc/
- **Delegated to:** python-dev-expert
- **Acceptance criteria:**
  - [ ] Create Pydantic model in scripts/marc/m2_models.py:
    ```python
    class PlaceAliasMap(BaseModel):
        version: str = "1.0"
        generated_at: Optional[str] = None
        mappings: Dict[str, str] = Field(..., description="Raw variant -> canonical key")

        @field_validator('mappings')
        @classmethod
        def validate_mappings(cls, v):
            # Ensure all keys and values are non-empty strings
            # Ensure all values are lowercase
            return v
    ```
  - [ ] Update scripts/marc/m2_normalize.py to load and validate alias map using PlaceAliasMap model
  - [ ] Add version field to production place_alias_map.json
  - [ ] Add test: test_place_alias_map_validation() ensuring production map passes
  - [ ] Add test: test_malformed_alias_map_error() ensuring bad maps are rejected
- **Rollback:** Git revert; revert to unvalidated JSON dict loading

---

## Phase 4: Low Priority (P3)

### Action 4.1: Create Developer Extension Guide
- **Addresses:** Finding F007
- **Description:** Comprehensive guide for common extension scenarios (adding MARC fields, normalizations, filter types).
- **Scope:** docs/dev_instructions/EXTENSION_GUIDE.md (new)
- **Delegated to:** Direct (documentation)
- **Acceptance criteria:**
  - [ ] Create docs/dev_instructions/EXTENSION_GUIDE.md with sections:
    - Adding a new MARC field to M1 (extract from XML, add to CanonicalRecord)
    - Adding a new normalization type to M2 (normalize_X_base pattern, M2 model field)
    - Adding a new filter type to M4 (FilterField enum, db_adapter SQL generation)
    - Adding a new QA issue tag (config.py, database schema)
  - [ ] Include code examples for each scenario
  - [ ] Include test template examples
  - [ ] Reference existing implementations as examples
  - [ ] Link from CLAUDE.md "Common Commands" section
- **Rollback:** Delete file; no dependencies

### Action 4.2: Add Test Coverage for QA Tool
- **Addresses:** Finding F008
- **Description:** Test critical non-UI code paths in app/ui_qa/db.py and app/qa.py to ensure regression runner and database operations work correctly.
- **Scope:** tests/app/ui_qa/ (new directory), tests/app/
- **Delegated to:** python-dev-expert
- **Acceptance criteria:**
  - [ ] Create tests/app/ui_qa/ directory
  - [ ] Add tests/app/ui_qa/test_db.py testing:
    - insert_query()
    - insert_label()
    - get_queries()
    - get_labels()
    - export_gold_set()
  - [ ] Add tests/app/test_qa.py testing:
    - CLI regression runner end-to-end
    - Gold set validation logic
    - Pass/fail detection
  - [ ] Achieve >80% coverage on app/ui_qa/db.py and app/qa.py
  - [ ] Skip Streamlit page files (UI testing out of scope)
- **Rollback:** Delete test files; no impact on production

---

## Validation & Testing

After each phase:
- [ ] Run existing test suite: `pytest`
- [ ] Verify acceptance criteria from FINDINGS.yaml
- [ ] Check for regression in unmodified areas
- [ ] Update documentation if needed
- [ ] Run gold set regression (if applicable): `poetry run python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db`

---

## Dependencies & Blockers

**Phase 2 dependencies:**
- Action 2.3 (confidence validation) requires human labeling time (~4-6 hours)
- Action 2.2 (LLM error handling) requires OpenAI API key for integration testing (can use pytest markers to skip if unavailable)

**Phase 3 dependencies:**
- Action 3.2 (schema versioning) should complete before Action 3.3 (alias map versioning) to maintain consistency

**No blockers identified.** All actions can proceed independently within phases.

---

## Estimated Scope

- **P0 fixes:** 0 actions
- **P1 fixes:** 3 actions (2 documentation, 1 code + tests)
- **P2 fixes:** 3 actions (all code + tests)
- **P3 fixes:** 2 actions (1 documentation, 1 tests only)

**Total:** 8 actions

**Time estimate:**
- Phase 2: 2-3 days (including confidence validation manual work)
- Phase 3: 3-4 days (schema changes require careful testing)
- Phase 4: 1-2 days (documentation + test coverage)

**Total:** ~1-2 weeks for complete remediation

---

## Notes

**Strengths to preserve:**
- M1-M3 pipeline is production-ready and deterministic
- Comprehensive test coverage (15 test files, 60+ tests)
- Excellent documentation (CLAUDE.md, README.md, docs/)
- Clean architecture with explicit Pydantic contracts

**Risk mitigation:**
- All actions include rollback notes
- Schema versioning (3.2) enables future evolution without breakage
- LLM error handling (2.2) prevents silent failures in M4

**Optional enhancements not in findings:**
- Consider CI/CD integration (GitHub Actions) for automated testing
- Consider adding pytest-cov report to track coverage over time
- Consider pre-commit hooks for ruff and black
