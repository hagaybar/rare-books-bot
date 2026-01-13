# Next Audit Checklist

**Purpose:** A reusable playbook for running future audits consistently and comparing results over time.

---

## Pre-Audit Preparation

### 1. Gather Project Intent Signals
- [ ] Read CLAUDE.md (primary project guidance)
- [ ] Read README.md (user-facing overview)
- [ ] Read docs/PROJECT_DESCRIPTION.md (if exists)
- [ ] Check plan.mf or ROADMAP.md for current milestone
- [ ] Review recent commits: `git log --oneline --since="[last audit date]" | head -20`
- [ ] Ask user for optional one-paragraph intent (current focus or concerns)

### 2. Understand Repository Structure
- [ ] Run: `tree -L 3 -I '__pycache__|*.pyc|.git|.venv|venv|node_modules|.pytest_cache' --dirsfirst`
- [ ] Identify main entrypoints:
  - CLI: `app/cli.py`
  - Library modules: `scripts/`
  - Tests: `tests/`
- [ ] Locate documentation: `docs/`
- [ ] Locate configuration: `configs/`, `pyproject.toml`, `pytest.ini`
- [ ] Locate data artifacts: `data/` (gitignored except critical files)

### 3. Review Recent Changes
- [ ] Run: `git log --oneline --since="[last audit date]" --stat | head -50`
- [ ] Identify areas of high churn: `git log --since="[last audit date]" --format=format: --name-only | sort | uniq -c | sort -rn | head -20`
- [ ] Check for new dependencies: `git diff [last audit commit] pyproject.toml`
- [ ] Check for new skills: `ls -la .claude/skills/`
- [ ] Check for major refactors or architectural changes

---

## Audit Execution (Follow SKILL.md Phases)

### Phase 0: Infer Project Intent
- [ ] Document core responsibilities (from CLAUDE.md, README, code structure)
- [ ] Document primary workflows/pipelines (e.g., M1→M2→M3→M4 for this project)
- [ ] Document key abstractions and artifacts (data models, schemas, output files)
- [ ] Document non-goals (what project explicitly avoids)
- [ ] Write down **Inferred Project Model** explicitly
- [ ] Validate model against user's one-paragraph intent (if provided)

### Phase 1: Architectural Mapping
- [ ] Map major components/modules:
  - `app/` - CLI interface
  - `scripts/` - Core library
  - `tests/` - Test suite
  - Other significant directories
- [ ] Map data flow (inputs → transformations → outputs)
- [ ] Map control flow (execution paths, entrypoints)
- [ ] Identify explicit boundaries:
  - Pydantic models (data contracts)
  - Database schemas (.sql files)
  - File formats (JSONL, JSON, XML)
  - API interfaces
- [ ] Identify implicit boundaries:
  - Naming conventions (e.g., `normalize_*_base()`)
  - Directory structure conventions
  - Module organization patterns

### Phase 2: Intent vs Implementation Alignment
- [ ] For each core responsibility:
  - [ ] Where is it implemented? (centralized or scattered)
  - [ ] Is ownership clear? (single module/function owns it)
  - [ ] Is it enforced by code or only by convention?
  - [ ] Classify alignment: ✅ aligned / ⚠ partially aligned / ❌ drifted / 🧨 contradictory
- [ ] Look for **directional drift**: Features that exist but aren't documented, or vice versa
- [ ] Specific areas to check:
  - Are all features in README actually implemented?
  - Are all major modules in `scripts/` documented in CLAUDE.md?
  - Are there large features (>500 lines) without clear documentation?

### Phase 3: Contract & Boundary Analysis
- [ ] For each major boundary identified in Phase 1:
  - [ ] What artifacts cross the boundary?
  - [ ] Are artifacts explicitly defined? (Pydantic models, schemas, documented formats)
  - [ ] Are artifacts validated? (runtime checks, schema enforcement)
  - [ ] Are artifacts versioned? (version field, migration strategy)
  - [ ] Are artifacts test-covered? (tests validate contract adherence)
  - [ ] Rate enforcement: Strong / Adequate / Weak / Missing
- [ ] Specific checks for this project:
  - [ ] Check all Pydantic models have corresponding tests
  - [ ] Check database schemas (.sql) have corresponding validation tests
  - [ ] Check critical JSON/JSONL artifacts have schema definitions
  - [ ] Check for version fields in serialized data models

### Phase 4: Determinism, Traceability, Explainability
- [ ] **Reproducibility**: Can outcomes be reproduced from inputs?
  - [ ] Run same MARC XML through M1-M3 pipeline twice, verify identical outputs
  - [ ] Check for randomness sources (LLM calls, timestamps, UUIDs)
  - [ ] Check if LLM usage has caching/fallback mechanisms
- [ ] **Traceability**: Can behavior be traced to inputs?
  - [ ] Check if data provenance is tracked (SourcedValue pattern in this project)
  - [ ] Check if normalizations preserve raw values
  - [ ] Check if query results link back to source data
- [ ] **Inspectability**: Can decisions be inspected after the fact?
  - [ ] Check if intermediate artifacts are saved (QueryPlan, SQL, etc.)
  - [ ] Check if transformation methods are tagged (e.g., `method: "year_bracketed"`)
  - [ ] Check if confidence scores are recorded
- [ ] **Observability**: Are side effects observable?
  - [ ] Check for extraction/processing reports
  - [ ] Check for logging infrastructure usage
  - [ ] Check for error tracking and reporting

### Phase 5: Code Health & Structural Risk
- [ ] **Complexity hotspots**: Find large files (>400 lines) or complex functions
  - [ ] Run: `find scripts -name "*.py" -exec wc -l {} + | sort -rn | head -20`
  - [ ] Identify files approaching 500-line threshold (python-dev-expert limit)
  - [ ] Check for high cyclomatic complexity (many nested conditions)
- [ ] **Duplication**: Look for repeated code patterns
  - [ ] Run: `grep -r "def normalize_" scripts/ | wc -l` (check for pattern reuse)
  - [ ] Check for copy-paste between modules
  - [ ] Verify DRY principle adherence
- [ ] **Cross-layer coupling**: Check for inappropriate dependencies
  - [ ] Check if CLI imports internal implementation details (expected)
  - [ ] Check if core library modules depend on each other inappropriately
  - [ ] Check for hardcoded references (e.g., table names, file paths)
- [ ] **Fragile modules**: High churn + low test coverage
  - [ ] Cross-reference high-churn files with test coverage
  - [ ] Flag any high-churn files without tests
- [ ] **Extension points**: Are they clear and documented?
  - [ ] Check for extension guides in docs/
  - [ ] Check if patterns are consistent and reusable

### Phase 6: Test & QA Effectiveness
- [ ] **Coverage vs criticality**: Is critical code tested?
  - [ ] Count test files: `find tests -name "test_*.py" | wc -l`
  - [ ] Check if core pipeline (M1-M3 in this project) has tests
  - [ ] Check if contracts (Pydantic models) have validation tests
  - [ ] Check if high-churn modules have tests
- [ ] **Contract encoding**: Do tests validate contracts?
  - [ ] Check if Pydantic model tests verify field constraints
  - [ ] Check if schema tests validate database structure
  - [ ] Check if integration tests validate end-to-end contracts
- [ ] **Regression safety**: Can tests catch regressions?
  - [ ] Check for golden output tests (expected vs actual)
  - [ ] Check for property-based tests
  - [ ] Check for regression test suite (e.g., gold set in this project)
- [ ] **Failure observability**: Are test failures clear?
  - [ ] Run: `pytest --collect-only` to verify tests are discoverable
  - [ ] Check if test names describe what they test
  - [ ] Check if test fixtures are well-organized

### Phase 7: Findings & Prioritization
- [ ] Classify all findings by severity:
  - **P0**: Correctness, data loss, contract breakage
  - **P1**: Architectural drift, scaling blockers, missing critical features
  - **P2**: Maintainability risks, missing documentation
  - **P3**: Clarity, ergonomics, nice-to-haves
- [ ] For each finding, document:
  - [ ] ID (F001, F002, etc.)
  - [ ] Area (architecture, contracts, tests, determinism, code_health, clarity)
  - [ ] Evidence (file paths, line numbers, specific examples)
  - [ ] Recommended invariant (desired state)
  - [ ] Acceptance criteria (testable outcomes)
  - [ ] Delegation (which skill should fix it, if code changes needed)

---

## Post-Audit

### 1. Generate Artifacts
- [ ] AUDIT_REPORT.md (use template from .claude/skills/project-audit/assets/)
- [ ] FINDINGS.yaml (use template from .claude/skills/project-audit/assets/)
- [ ] ACTION_PLAN.md (use template from .claude/skills/project-audit/assets/)
- [ ] NEXT_AUDIT_CHECKLIST.md (update this checklist if process changed)

### 2. Archive Audit Results
```bash
# Create audit archive directory if needed
mkdir -p audits/

# Archive with timestamp
AUDIT_DATE=$(date +%Y%m%d)
cp AUDIT_REPORT.md "audits/AUDIT_REPORT_${AUDIT_DATE}.md"
cp FINDINGS.yaml "audits/FINDINGS_${AUDIT_DATE}.yaml"
cp ACTION_PLAN.md "audits/ACTION_PLAN_${AUDIT_DATE}.md"

# Optional: Create audit summary
echo "Audit Date: ${AUDIT_DATE}" > audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
echo "Total Findings: $(grep 'total_findings:' FINDINGS.yaml | awk '{print $2}')" >> audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
echo "P0: $(grep 'P0:' FINDINGS.yaml | awk '{print $2}')" >> audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
echo "P1: $(grep 'P1:' FINDINGS.yaml | awk '{print $2}')" >> audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
echo "P2: $(grep 'P2:' FINDINGS.yaml | awk '{print $2}')" >> audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
echo "P3: $(grep 'P3:' FINDINGS.yaml | awk '{print $2}')" >> audits/AUDIT_SUMMARY_${AUDIT_DATE}.txt
```

### 3. Compare with Previous Audit (if available)
- [ ] Compare number of findings by severity
  ```bash
  # Compare total findings
  diff <(grep 'total_findings:' audits/FINDINGS_20260112.yaml) \
       <(grep 'total_findings:' audits/FINDINGS_[previous_date].yaml)
  ```
- [ ] Check if previous P0/P1 findings were resolved
  ```bash
  # List P0/P1 findings from previous audit
  grep -A 20 "severity: \"P0\"\|severity: \"P1\"" audits/FINDINGS_[previous_date].yaml
  ```
- [ ] Identify new areas of concern
- [ ] Note improvements or regressions in specific areas

### 4. Generate Comparison Report (Optional)
- [ ] Create audits/COMPARISON_[date1]_[date2].md
- [ ] Document:
  - Findings resolved since last audit
  - New findings introduced
  - Areas of improvement
  - Areas of regression
  - Overall trend (improving/stable/declining)

---

## Metrics to Track Over Time

Track these metrics across audits to measure progress:

| Metric | Current Audit (2026-01-12) | Previous Audit | Change |
|--------|----------------------------|----------------|--------|
| Total findings | 8 | - | - |
| P0 findings | 0 | - | - |
| P1 findings | 3 | - | - |
| P2 findings | 3 | - | - |
| P3 findings | 2 | - | - |
| Weak/missing contracts | 3 | - | - |
| Fragile modules | 0 | - | - |
| Test coverage gaps | 2 | - | - |
| Alignment drift areas | 2 | - | - |
| Files >400 lines | 2 | - | - |
| Test files | 15 | - | - |
| Total LOC (scripts/) | ~6000 | - | - |

### Additional Metrics (Optional)
```bash
# Count lines of code
cloc scripts/ --include-lang=Python

# Count test files
find tests -name "test_*.py" | wc -l

# Find large files
find scripts -name "*.py" -exec wc -l {} + | sort -rn | head -10

# Count TODO/FIXME
grep -r "TODO\|FIXME\|XXX\|HACK" --include="*.py" scripts/ | wc -l

# Count Pydantic models
grep -r "class.*BaseModel" scripts/ | wc -l
```

---

## Commands Reference

```bash
# Repository structure
tree -L 3 -I '__pycache__|*.pyc|.git|.venv|venv|node_modules|.pytest_cache' --dirsfirst

# Recent changes
git log --oneline --since="2026-01-01" --stat

# High churn files
git log --since="2026-01-01" --format=format: --name-only | sort | uniq -c | sort -rn | head -20

# Test collection
pytest --collect-only

# Find large files
find scripts -name "*.py" -exec wc -l {} + | sort -rn | head -20

# Find TODO/FIXME comments
grep -r "TODO\|FIXME\|XXX\|HACK" --include="*.py" scripts/

# Count lines of code (if cloc installed)
cloc . --exclude-dir=.git,__pycache__,venv,.venv,node_modules,.pytest_cache

# Find duplicated code (if pylint installed)
pylint --disable=all --enable=duplicate-code scripts/

# Count test files
find tests -name "test_*.py" | wc -l

# Check for cached Python files
find . -name "*.pyc" -o -name "__pycache__" | wc -l
```

---

## Project-Specific Notes

### Rare Books Bot Specifics

**Key contracts to verify:**
1. CanonicalRecord (M1 output)
2. M2EnrichedRecord (M2 output)
3. M3 database schema (m3_schema.sql)
4. QueryPlan (M4 input)
5. CandidateSet (M4 output)
6. place_alias_map.json (production artifact)

**Determinism checks:**
- M1-M3 must be fully deterministic
- M4 query compilation uses LLM (cached in query_plan_cache.jsonl)
- Check cache hit rate: `wc -l data/query_plan_cache.jsonl`

**Critical paths to test:**
- MARC XML → M1 canonical
- M1 → M2 enrichment (with place_alias_map.json)
- M2 → M3 indexing
- M4 query compilation → SQL generation → CandidateSet

**Common extension points:**
- Adding MARC fields: scripts/marc/parse.py + models.py
- Adding normalizations: scripts/marc/normalize.py + m2_models.py
- Adding filter types: scripts/schemas/query_plan.py + scripts/query/db_adapter.py

**Regression testing:**
- Run gold set: `poetry run python -m app.qa regress --gold data/qa/gold.json --db data/index/bibliographic.db`
- Check QA tool: `poetry run streamlit run app/ui_qa/main.py`

---

## Notes for Next Audit

**2026-01-12 Audit Notes:**
- First comprehensive audit using project-audit skill
- No P0 findings (excellent baseline)
- Main concerns: QA tool scope, LLM dependency, confidence score validation
- Strong test coverage for M1-M3, weaker for M4 and QA tool
- Excellent documentation (CLAUDE.md, README.md, docs/)

**For next audit:**
- Check if P1 findings (F001, F002, F003) were addressed
- Verify schema versioning was implemented (F005)
- Check if QA tool boundaries are now documented
- Compare test coverage (aim for >80% on critical paths)
- Check if new features maintain determinism and contract enforcement
