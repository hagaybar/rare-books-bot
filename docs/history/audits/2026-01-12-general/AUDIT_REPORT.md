# Project Audit Report

**Date:** 2026-01-12
**Project:** rare-books-bot (MARC XML Bibliographic Discovery System)
**Auditor:** Claude (project-audit skill)
**Scope:** Full codebase audit - M1-M4 pipeline, normalization, query execution, QA tools

---

## Executive Summary

The rare-books-bot project demonstrates strong architectural clarity and disciplined adherence to its core principle: MARC XML as the source of truth with deterministic, evidence-based processing. The codebase exhibits mature engineering practices with explicit contracts (Pydantic models), deterministic normalization, comprehensive test coverage, and excellent documentation.

**Key strengths**: Clean M1→M2→M3→M4 pipeline architecture, strong schema enforcement, reversible normalization with confidence scoring, and a sophisticated QA tool with gold set regression testing.

**Major risks**: (1) The ui_qa Streamlit tool represents significant scope expansion without clear project boundary documentation, (2) Recent transition from heuristic to LLM-based query parsing creates dependency risk without fallback strategy, (3) No validation that M2 normalization confidence scores correlate with actual accuracy.

**Recommendation**: Document the QA tool's status (production feature vs development tool), add fallback mechanism for LLM query compiler failures, and establish validation process for normalization quality.

---

## Inferred Project Model

### Core Responsibilities

1. **MARC XML Ingestion** (M1): Parse MARC XML files into canonical JSONL format, preserving all raw values with provenance tracking
2. **Deterministic Normalization** (M2): Enrich canonical records with normalized fields (dates, places, publishers, agents) using confidence-scored, reversible transformations
3. **Queryable Indexing** (M3): Build SQLite database with both raw and normalized fields, enabling fielded queries
4. **Query Execution** (M4): Convert natural language queries to QueryPlan → SQL → CandidateSet with evidence
5. **Quality Assurance**: Provide tooling for labeling query results and regression testing (ui_qa)

### Primary Workflows

1. **MARC Processing Pipeline**: MARC XML → M1 canonical → M2 enriched → M3 indexed → M4 queryable
2. **Place Alias Generation**: Frequency analysis → LLM-assisted mapping → human review → production alias map (one-time setup)
3. **Query Execution**: Natural language → LLM QueryPlan compilation → SQL generation → Evidence-backed results
4. **QA Workflow**: Run query → label candidates → identify issues → export gold set → regression testing

### Key Abstractions and Artifacts

- **CanonicalRecord** (M1): Pydantic model with SourcedValue tracking MARC provenance
- **M2EnrichedRecord** (M2): Canonical + m2 object with normalized fields + confidence + method
- **QueryPlan** (M4): Structured filter specification (validated against Pydantic schema)
- **CandidateSet** (M4): Query results with per-candidate evidence linking back to MARC fields
- **Place Alias Map**: Production artifact (JSON) mapping variants → canonical English keys
- **Gold Set**: Regression test specification (expected includes/excludes per query)

### Non-Goals

- **Not a general RAG platform**: Explicitly removing RAG-specific components from inherited template
- **No embedding-based retrieval**: Fielded SQLite queries only, no vector search
- **No destructive normalization**: Raw MARC values always preserved alongside normalized fields
- **No narrative-first answers**: CandidateSet + Evidence must exist before interpretation
- **No LLM in core pipeline**: M1-M3 are deterministic; LLM only in M4 query planning and utility scripts

---

## Architecture Map

### Major Components

**app/** - CLI interface layer
- `cli.py`: Typer-based CLI with `parse_marc` and `query` commands
- `qa.py`: CLI regression runner for gold set validation
- `ui_qa/`: Streamlit QA tool (12 files, 5 pages)

**scripts/** - Core library organized by function
- `marc/`: M1 parsing, M2 normalization, M3 indexing (9 files)
- `query/`: M4 query compilation and execution (5 files)
- `normalization/`: Agent/place normalization utilities (2 files)
- `schemas/`: Pydantic models for QueryPlan and CandidateSet (2 files)
- `utils/`: Logging, config, task paths (5 files)
- `api_clients/`: OpenAI client wrapper (1 file)

**tests/** - Pytest suite mirroring scripts/ structure (15 test files)

**data/** - Artifacts and run outputs (gitignored except place_alias_map.json)

**docs/** - Specifications, pipeline docs, dev instructions

### Data Flow

```
MARC XML file
    ↓ [M1: scripts/marc/parse.py]
Canonical JSONL (data/canonical/records.jsonl)
    ↓ [M2: scripts/marc/m2_normalize.py + place_alias_map.json]
M2 Enriched JSONL (data/m2/records_m1m2.jsonl)
    ↓ [M3: scripts/marc/m3_index.py + m3_schema.sql]
SQLite Database (data/index/bibliographic.db)
    ↓ [M4: scripts/query/compile.py + execute.py]
QueryPlan → SQL → CandidateSet (data/runs/query_YYYYMMDD_HHMMSS/)
```

### Control Flow

**CLI execution path**:
```
app/cli.py::query()
    ↓
scripts/query/compile.py::compile_query()  [uses LLM via llm_compiler.py]
    ↓
scripts/query/execute.py::execute_plan_from_file()
    ↓
scripts/query/db_adapter.py  [generates SQL, extracts evidence]
    ↓
CandidateSet output (JSON)
```

**QA tool execution path**:
```
app/ui_qa/main.py (Streamlit)
    ↓
app/ui_qa/pages/1_run_review.py
    ↓
scripts/query/compile.py + execute.py  [same as CLI]
    ↓
app/ui_qa/db.py  [stores labels in qa.db]
```

### Explicit Boundaries

1. **M1/M2 boundary**: CanonicalRecord → M2EnrichedRecord (JSONL files)
   - Contract: Pydantic `CanonicalRecord` model (scripts/marc/models.py)
   - Validation: Explicit parsing + Pydantic validation
   - Versioned: No explicit versioning yet

2. **M2/M3 boundary**: M2EnrichedRecord → SQLite rows
   - Contract: m3_schema.sql defines database schema
   - Validation: SQLite schema enforcement
   - Versioned: No migration system

3. **M3/M4 boundary**: Natural language → QueryPlan
   - Contract: Pydantic `QueryPlan` model (scripts/schemas/query_plan.py)
   - Validation: OpenAI Responses API enforces schema
   - Versioned: `version: "1.0"` field in QueryPlan

4. **M4 output**: QueryPlan + SQL → CandidateSet
   - Contract: Pydantic `CandidateSet` model (scripts/schemas/candidate_set.py)
   - Validation: Pydantic validation
   - Versioned: No explicit version field

5. **Place Alias Map**: place_alias_map.json (production artifact)
   - Contract: JSON dict {raw_variant: canonical_key}
   - Validation: JSON schema only (no Pydantic model)
   - Versioned: Git-tracked, no explicit version

### Implicit Boundaries

1. **Naming conventions**:
   - M1 models: `CanonicalRecord`, `ImprintData`, `AgentData`, etc.
   - M2 models: `M2EnrichedRecord`, `NormalizedPlace`, `NormalizedDate`, etc.
   - Normalization functions: `normalize_*_base()` pattern
   - Test files: `test_*.py` mirroring source structure

2. **Directory structure**:
   - `scripts/marc/` = MARC-specific processing
   - `scripts/query/` = M4 query layer
   - `scripts/normalization/` = Utility functions for M2
   - `data/canonical/` = M1 outputs
   - `data/m2/` = M2 outputs
   - `data/index/` = M3 outputs
   - `data/runs/` = M4 per-query outputs

3. **Module organization**:
   - `models.py` = Pydantic models only
   - `normalize.py` = Pure normalization functions
   - `parse.py` = Parsing logic
   - CLI commands = thin wrappers around scripts/ functions

---

## Alignment Analysis

### Responsibility 1: MARC XML Ingestion (M1)
- **Implementation location:** `scripts/marc/parse.py` (single module, ~400 lines)
- **Centralization:** ✅ Centralized - single parse function with helper functions
- **Ownership clarity:** ✅ Clear - `parse_marc_xml_file()` is entrypoint
- **Enforcement:** Code + Pydantic validation
- **Status:** ✅ **aligned** - Implementation matches intent perfectly

### Responsibility 2: Deterministic Normalization (M2)
- **Implementation location:** `scripts/marc/normalize.py` + `m2_normalize.py` + `scripts/normalization/normalize_agent.py`
- **Centralization:** ✅ Centralized - normalization logic in dedicated modules
- **Ownership clarity:** ✅ Clear - Each normalization type has dedicated function (normalize_date_base, normalize_place_base, etc.)
- **Enforcement:** Code + type hints + tests (no Pydantic validation on normalization output structure)
- **Status:** ✅ **aligned** - Strong adherence to reversibility and confidence scoring principles

### Responsibility 3: SQLite Indexing (M3)
- **Implementation location:** `scripts/marc/m3_index.py` + `m3_schema.sql`
- **Centralization:** ✅ Centralized - single script
- **Ownership clarity:** ✅ Clear - `build_index()` entrypoint
- **Enforcement:** Code + SQL schema constraints
- **Status:** ✅ **aligned** - Clean separation of schema definition and indexing logic

### Responsibility 4: Query Execution (M4)
- **Implementation location:** `scripts/query/` (5 files: compile.py, llm_compiler.py, execute.py, db_adapter.py, __init__.py)
- **Centralization:** ⚠ **Partially scattered** - Query compilation logic split between heuristic remnants and LLM path
- **Ownership clarity:** ✅ Clear - `compile_query()` is entrypoint, delegates to `llm_compiler.py`
- **Enforcement:** Code + Pydantic QueryPlan validation + OpenAI Responses API schema enforcement
- **Status:** ⚠ **partially aligned** - Recent transition from heuristic to LLM compiler complete, but code structure suggests incomplete cleanup

### Responsibility 5: Quality Assurance (QA Tool)
- **Implementation location:** `app/ui_qa/` (12 files, Streamlit app)
- **Centralization:** ⚠ **Self-contained but scope unclear** - Large feature with its own database (qa.db)
- **Ownership clarity:** ⚠ **Ambiguous** - Is this a development tool or production feature?
- **Enforcement:** Convention only (no explicit boundary between QA tool and core pipeline)
- **Status:** ❌ **drifted** - Significant feature (~12 files) not clearly documented in project intent (CLAUDE.md mentions acceptance tests but not QA tool architecture)

---

## Contract & Boundary Review

### Boundary 1: M1 Output (Canonical Records)
- **Artifacts crossing boundary:** CanonicalRecord objects serialized to JSONL
- **Explicitly defined?** ✅ Yes - Pydantic `CanonicalRecord` model in scripts/marc/models.py
- **Validated?** ✅ Yes - Pydantic validation during parsing
- **Versioned?** ❌ No - No version field in CanonicalRecord
- **Test-covered?** ✅ Yes - test_m1_upgrade.py, test_agent_extraction.py, 20+ tests
- **Assessment:** **Strong** - Well-defined contract with validation and tests; missing versioning

### Boundary 2: M2 Enrichment (Normalized Fields)
- **Artifacts crossing boundary:** M2EnrichedRecord (Canonical + m2 object)
- **Explicitly defined?** ✅ Yes - Pydantic `M2EnrichedRecord` model in scripts/marc/m2_models.py
- **Validated?** ⚠ Partial - Pydantic validates structure, but confidence scores not validated against ground truth
- **Versioned?** ❌ No - No version field in M2EnrichedRecord
- **Test-covered?** ✅ Yes - test_m2_normalize.py with 20+ tests
- **Assessment:** **Adequate** - Strong structural definition; confidence scores lack empirical validation

### Boundary 3: M3 Database Schema
- **Artifacts crossing boundary:** SQLite rows in 7 tables (records, titles, imprints, subjects, agents, languages, notes)
- **Explicitly defined?** ✅ Yes - scripts/marc/m3_schema.sql
- **Validated?** ✅ Yes - SQLite schema enforcement + foreign keys
- **Versioned?** ❌ No - No migration system or schema version tracking
- **Test-covered?** ✅ Yes - test_m3_index.py with 15 tests
- **Assessment:** **Adequate** - Clean schema definition; no migration strategy for schema evolution

### Boundary 4: QueryPlan Schema (M4 Input)
- **Artifacts crossing boundary:** QueryPlan JSON objects
- **Explicitly defined?** ✅ Yes - Pydantic model in scripts/schemas/query_plan.py + OpenAI Responses API schema
- **Validated?** ✅ Yes - Double validation: Pydantic + OpenAI Responses API
- **Versioned?** ✅ Yes - `version: "1.0"` field in QueryPlan
- **Test-covered?** ✅ Yes - test_query_plan.py, test_compile.py, test_llm_compiler.py
- **Assessment:** **Strong** - Excellent contract with dual validation and versioning

### Boundary 5: CandidateSet Output (M4 Output)
- **Artifacts crossing boundary:** CandidateSet JSON objects with Evidence arrays
- **Explicitly defined?** ✅ Yes - Pydantic model in scripts/schemas/candidate_set.py
- **Validated?** ✅ Yes - Pydantic validation
- **Versioned?** ❌ No - No version field in CandidateSet
- **Test-covered?** ✅ Yes - test_candidate_set.py, test_execute.py
- **Assessment:** **Strong** - Well-defined contract; missing versioning for schema evolution

### Boundary 6: Place Alias Map (Production Artifact)
- **Artifacts crossing boundary:** place_alias_map.json (dict mapping variants → canonical keys)
- **Explicitly defined?** ⚠ Partial - JSON structure documented in docs/utilities/place_alias_mapping.md, but no Pydantic model
- **Validated?** ❌ No - JSON parsing only, no schema validation
- **Versioned?** ❌ No - Git-tracked but no explicit version field or update strategy
- **Test-covered?** ⚠ Partial - Used in tests but map generation itself not fully tested
- **Assessment:** **Weak** - Critical production artifact lacks formal schema and validation

---

## Determinism, Traceability, and Explainability

### Reproducibility
✅ **Strong** - M1-M3 pipeline is fully deterministic
- Same MARC XML input → identical M1 canonical output (proven by tests)
- Same canonical input + place_alias_map → identical M2 enriched output (proven by tests)
- Same M2 input → identical M3 database (schema-enforced)
- ⚠ M4 query compilation: LLM-based, non-deterministic (mitigated by caching in query_plan_cache.jsonl)

**Evidence:**
- Test suite validates deterministic outputs across M1-M3
- CLAUDE.md:88-91 explicitly requires deterministic processing
- Caching strategy in scripts/query/llm_compiler.py ensures repeat queries use cached plans

### Traceability
✅ **Excellent** - Every value traces back to MARC source
- M1: SourcedValue tracks field$subfield provenance (e.g., "260$a", "264$b")
- M2: Normalization preserves raw value + adds normalized + method + confidence
- M4: Evidence objects link CandidateSet back to database fields and MARC sources

**Evidence:**
- scripts/marc/models.py:7-11 - SourcedValue design
- scripts/schemas/candidate_set.py:12-22 - Evidence tracking
- M4 output includes exact SQL executed for audit trail

### Inspectability
✅ **Strong** - Decisions are inspectable after the fact
- QueryPlan JSON saved to disk per run (data/runs/query_YYYYMMDD_HHMMSS/plan.json)
- SQL query saved alongside plan (sql.txt)
- CandidateSet includes per-candidate evidence showing match rationale
- M2 normalization includes method tags (e.g., "year_bracketed", "place_base_clean")

**Evidence:**
- app/cli.py:136-138 - Plan persistence
- scripts/marc/m2_models.py - Method tracking in normalized fields
- docs/ - Comprehensive documentation of pipelines and specifications

### Observability
✅ **Adequate** - Side effects are observable
- Extraction reports track parsing success/failure (data/canonical/extraction_report.json)
- Per-run output directories preserve full query execution context
- Logging infrastructure exists (scripts/utils/logger.py) but usage not verified in audit
- ⚠ No monitoring of normalization quality drift over time

**Evidence:**
- app/cli.py:63-78 - Extraction report displayed
- data/runs/ - Per-query artifacts preserved
- QA tool (app/ui_qa/) provides manual observability of M4 quality

---

## Code Health & Structural Risk

### Complexity Hotspots

1. **scripts/marc/parse.py** (~400 lines, single file)
   - High cyclomatic complexity in MARC field extraction logic
   - Risk: Moderate - Well-tested but difficult to extend for new MARC fields
   - Recommendation: Consider splitting into field-specific extractors if >500 lines

2. **scripts/query/db_adapter.py** (SQL generation + evidence extraction)
   - Multiple responsibilities: SQL generation, query execution, evidence extraction
   - Risk: Moderate - Changes to SQL generation can break evidence tracking
   - Recommendation: Split into query_builder.py and evidence_extractor.py

3. **app/ui_qa/** (12 files, Streamlit app)
   - Large feature with its own database and state management
   - Risk: High - Scope unclear (dev tool vs production feature?)
   - Recommendation: Document status and boundaries; consider extraction to separate package

### Duplication

✅ **Minimal duplication observed**
- Normalization pattern (`normalize_*_base()`) is abstracted and reused
- Test fixtures appear centralized in tests/fixtures/
- No obvious copy-paste patterns found in scripts/

**Evidence:**
- scripts/marc/normalize.py + scripts/normalization/normalize_agent.py use same base cleaning pattern
- CLAUDE.md:104 - "Extract logic after 3rd duplication (DRY principle)"

### Cross-Layer Coupling

⚠ **Moderate coupling issues**

1. **CLI depends on internal implementation details**
   - app/cli.py imports directly from scripts/ (acceptable for CLI)
   - ui_qa imports from scripts/query/ (acceptable for tooling)

2. **Query module depends on M3 schema implicitly**
   - scripts/query/db_adapter.py hardcodes table/column names
   - No explicit contract between M3 schema and M4 query builder
   - Risk: M3 schema changes could silently break M4 queries

3. **M2 normalization depends on external artifact (place_alias_map.json)**
   - Coupling is intentional and documented
   - Risk: Low - Map is version-controlled and stable

### Fragile Modules (High Churn + Low Test Coverage)

**Analysis based on git log since 2025-01-01:**

High churn files:
- CLAUDE.md (6 changes) - Documentation only, not fragile
- app/cli.py (5 changes) - CLI interface, covered by integration tests
- scripts/marc/parse.py (4 changes) - Well-tested (20+ tests)
- scripts/marc/models.py (4 changes) - Pydantic models, validated
- pyproject.toml (4 changes) - Dependency management, not fragile

✅ **No fragile modules identified** - High churn files have adequate test coverage

### Extension Points

✅ **Clear extension points**

1. **New MARC fields**: Add extraction logic to scripts/marc/parse.py + update CanonicalRecord model
2. **New normalization types**: Add `normalize_*_base()` function + update M2EnrichedRecord
3. **New filter types**: Add to FilterField enum in scripts/schemas/query_plan.py
4. **New query patterns**: Extend scripts/query/llm_compiler.py LLM instructions

⚠ **Documentation could be clearer**
- No explicit "extension guide" in docs/
- Developers must infer patterns from existing code
- Recommendation: Create docs/dev_instructions/EXTENSION_GUIDE.md

---

## Test & QA Effectiveness

### Coverage vs Criticality

✅ **Good alignment** - Critical paths are well-tested

**Well-tested areas:**
- M1 parsing: 20+ tests (test_m1_upgrade.py, test_agent_extraction.py)
- M2 normalization: 20+ tests (test_m2_normalize.py)
- M3 indexing: 15 tests (test_m3_index.py)
- M4 query planning: 5 test files (test_query_plan.py, test_compile.py, test_llm_compiler.py, test_candidate_set.py, test_execute.py)
- Agent normalization: test_normalize_agent.py

**Under-tested areas:**
- ⚠ Place alias map generation (scripts/normalization/generate_place_alias_map.py) - No dedicated test file found
- ⚠ QA tool (app/ui_qa/) - No test files found for Streamlit pages
- ⚠ CLI integration (app/cli.py) - No end-to-end integration tests found

### Contract Encoding

✅ **Tests encode contracts well**

**Evidence:**
- test_query_plan.py validates QueryPlan schema constraints (RANGE requires start/end, etc.)
- test_m2_normalize.py validates normalization contract (confidence scores, method tags, reversibility)
- test_m3_index.py validates database schema enforcement

⚠ **Missing contract tests:**
- No tests validating M3 schema matches M4 query expectations (implicit coupling risk)
- No tests validating place_alias_map.json structure
- No tests validating CandidateSet evidence integrity (does evidence actually trace to MARC fields?)

### Regression Safety

✅ **Strong regression safety for M1-M3**
- Comprehensive unit tests prevent regressions in parsing and normalization
- Deterministic outputs make regression detection straightforward

✅ **QA tool provides M4 regression framework**
- Gold set with expected_includes/expected_excludes
- CLI regression runner (app/qa.py)
- Streamlit UI for labeling and analysis

⚠ **Regression testing not automated in CI**
- No evidence of GitHub Actions or CI configuration
- Gold set regression could silently break without CI enforcement
- Recommendation: Add pytest integration test that runs gold set validation

### Failure Observability

✅ **Good failure observability**

**Test output:**
- Pytest provides clear failure messages
- Pydantic validation errors include field names and constraints
- Extraction reports track parsing failures (app/cli.py:63-78)

⚠ **LLM failures not well-observable**
- If OpenAI API fails, error handling unclear
- No tests for LLM failure scenarios (API timeout, invalid response, etc.)
- Recommendation: Add integration tests for LLM error handling

---

## Key Risks & Recommendations

### P0 — Critical

**No P0 findings** - No correctness, data loss, or contract breakage issues identified.

### P1 — High

#### F001: QA Tool Scope Drift
**Area:** Architecture
**Description:** The ui_qa Streamlit application (12 files, ~1000 lines) represents significant scope expansion not clearly documented in project intent. CLAUDE.md mentions "acceptance tests" but doesn't describe the QA tool architecture or its relationship to the core pipeline. The tool has its own database (qa.db), session management, and 5-page UI.

**Evidence:**
- app/ui_qa/ contains 12 Python files
- Separate database (data/qa/qa.db) not mentioned in CLAUDE.md
- README.md mentions "M4 in development" but ui_qa exists and is feature-complete
- No explicit statement of whether this is a development tool or production feature

**Risk:** Unclear boundaries make it difficult to:
1. Decide what should be tested/maintained
2. Determine if features belong in core or QA tool
3. Assess whether the tool should be extracted to a separate package

**Recommended Invariant:**
"The QA tool's status (development tool vs production feature), scope boundaries, and relationship to core pipeline must be explicitly documented in CLAUDE.md and README.md."

**Acceptance Criteria:**
1. CLAUDE.md includes section on QA tool architecture and scope
2. Clear decision documented: keep integrated vs extract to separate package
3. If kept: Define which features belong in ui_qa vs core pipeline
4. If extracted: Create separate repository and document integration points

#### F002: LLM Query Compiler Dependency Without Fallback
**Area:** Determinism / Architecture
**Description:** M4 query compilation transitioned from heuristic parser to LLM-based compilation (scripts/query/llm_compiler.py). The system now depends on OpenAI API availability for all queries. No fallback mechanism exists if:
1. API is unavailable
2. API key is missing/invalid
3. LLM returns invalid JSON (despite schema enforcement)
4. Query exceeds context limits

Caching (query_plan_cache.jsonl) mitigates repeat queries but not new queries.

**Evidence:**
- CLAUDE.md:143-167 documents LLM-based query planning
- scripts/query/compile.py:36-46 - compile_query() delegates to llm_compiler without fallback
- Recent commits show transition: "Replace heuristic query parser with LLM-based Query Planner" (90c91f6)
- No error handling tests for LLM failures found in test_llm_compiler.py

**Risk:** System cannot process new queries if OpenAI API is unavailable. This violates the "deterministic processing" principle for M4.

**Recommended Invariant:**
"M4 query compilation must either (a) provide fallback mechanism for LLM failures, or (b) explicitly document that M4 requires OpenAI API and fail gracefully with clear error messages."

**Acceptance Criteria:**
1. Add integration tests for LLM failure scenarios (API timeout, invalid key, rate limit)
2. Implement graceful failure: clear error message pointing to OPENAI_API_KEY requirement
3. Consider: Simple heuristic fallback for basic query patterns
4. Document LLM dependency prominently in README.md and CLI error messages

#### F003: No Validation of Normalization Confidence Scores
**Area:** Contracts / Quality
**Description:** M2 normalization assigns confidence scores (0.80, 0.95, 0.99) to normalized fields, but there's no validation that these scores correlate with actual accuracy. Scores are assigned by rule (base cleaning = 0.80, alias map = 0.95) without empirical validation.

**Evidence:**
- CLAUDE.md:49 - "Confidence: 0.80 (base cleaning) or 0.95 (with alias map)"
- CLAUDE.md:62 - "Confidence: 0.95-0.99 (high certainty), 0.80-0.85 (medium), 0.0 (unparsed)"
- scripts/marc/normalize.py assigns confidence scores
- No tests validating confidence scores against ground truth found

**Risk:** Confidence scores may mislead downstream consumers if they don't reflect actual accuracy. M4 query execution may trust low-quality normalizations.

**Recommended Invariant:**
"Normalization confidence scores must be validated against ground truth samples, or clearly documented as 'heuristic estimates pending validation'."

**Acceptance Criteria:**
1. Sample 100-200 normalized records across confidence levels
2. Manually validate normalization quality
3. Calculate actual precision/recall per confidence level
4. Either: Update confidence formulas based on empirical data, OR: Document scores as heuristic in CLAUDE.md
5. Add regression test suite for normalization quality

### P2 — Medium

#### F004: M3 Schema and M4 Query Builder Implicit Coupling
**Area:** Contracts
**Description:** scripts/query/db_adapter.py hardcodes M3 database table and column names without explicit contract. If M3 schema changes, M4 queries could silently break.

**Evidence:**
- scripts/query/db_adapter.py references "imprints.place_norm", "records.record_id", etc.
- No explicit contract between scripts/marc/m3_schema.sql and scripts/query/db_adapter.py
- No tests validating schema expectations

**Risk:** Schema evolution could break queries without detection.

**Recommended Invariant:**
"M3 schema must be explicitly referenced by M4 query builder, with tests validating schema expectations."

**Acceptance Criteria:**
1. Create scripts/marc/m3_contract.py defining expected tables/columns as constants
2. Update db_adapter.py to reference contract constants instead of hardcoded strings
3. Add test validating actual database schema matches contract
4. Document schema versioning strategy in docs/

#### F005: Missing Schema Versioning
**Area:** Contracts
**Description:** CanonicalRecord, M2EnrichedRecord, and CandidateSet lack version fields. Schema evolution would break backward compatibility without migration strategy.

**Evidence:**
- QueryPlan has `version: "1.0"` field (scripts/schemas/query_plan.py:87)
- CanonicalRecord, M2EnrichedRecord, CandidateSet have no version field
- No migration strategy documented

**Risk:** Adding fields or changing schemas would break existing JSONL files and databases.

**Recommended Invariant:**
"All serialized schemas (CanonicalRecord, M2EnrichedRecord, CandidateSet) must include version field and documented migration strategy."

**Acceptance Criteria:**
1. Add `version: str` field to CanonicalRecord, M2EnrichedRecord, CandidateSet
2. Create docs/specs/SCHEMA_VERSIONING.md documenting migration strategy
3. Implement version checking in parsing logic
4. Add tests for version mismatch handling

#### F006: Place Alias Map Lacks Formal Schema
**Area:** Contracts
**Description:** place_alias_map.json is a critical production artifact but lacks formal schema validation. It's a simple dict but no Pydantic model or JSON schema validates structure.

**Evidence:**
- data/normalization/place_aliases/place_alias_map.json is git-tracked
- docs/utilities/place_alias_mapping.md documents generation process
- No schema validation in scripts/marc/m2_normalize.py
- No Pydantic model for alias map structure

**Risk:** Malformed alias map could cause silent normalization failures.

**Recommended Invariant:**
"place_alias_map.json must be validated against formal schema (Pydantic model or JSON schema) during load."

**Acceptance Criteria:**
1. Create Pydantic model for alias map: `PlaceAliasMap(BaseModel)`
2. Update m2_normalize.py to validate alias map on load
3. Add test validating production alias map passes validation
4. Add version field to alias map JSON

### P3 — Low

#### F007: No Extension Guide for Developers
**Area:** Clarity / Ergonomics
**Description:** Clear extension points exist (add MARC fields, add normalizations, add filter types) but no explicit documentation guides developers through extension process.

**Recommended Invariant:**
"Developers should have clear documentation for common extension scenarios."

**Acceptance Criteria:**
1. Create docs/dev_instructions/EXTENSION_GUIDE.md
2. Document: Adding new MARC fields, adding normalization types, adding filter types
3. Include code examples and test templates

#### F008: Test Files for QA Tool Missing
**Area:** Test effectiveness
**Description:** app/ui_qa/ has 12 Python files but no corresponding test files found in tests/ directory.

**Recommended Invariant:**
"All non-trivial application code should have corresponding test coverage."

**Acceptance Criteria:**
1. Add tests/app/ui_qa/ directory
2. Test critical paths: database operations (app/ui_qa/db.py), regression runner (app/qa.py)
3. Achieve >80% coverage on non-UI code

---

## Conclusion

The rare-books-bot project demonstrates strong engineering discipline with clear architectural boundaries, comprehensive testing (M1-M3), and excellent documentation. The core MARC processing pipeline (M1→M2→M3) is production-ready with deterministic outputs and strong contracts.

**Primary recommendation**: Address the three P1 findings before expanding scope:
1. Document QA tool status and boundaries (F001)
2. Add LLM failure handling for M4 (F002)
3. Validate normalization confidence scores (F003)

**Secondary recommendation**: Implement schema versioning (F005) and M3/M4 contract enforcement (F004) to support future evolution.

The project is well-positioned to move from POC to production with these improvements.
