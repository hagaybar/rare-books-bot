# Next Audit Checklist

**Purpose:** A reusable playbook for running future audits consistently and comparing results over time.

---

## Pre-Audit Preparation

### 1. Gather Project Intent Signals
- [ ] Read README.md and any design docs
- [ ] Review CLAUDE.md or project instructions
- [ ] Check for ADRs (Architecture Decision Records)
- [ ] Identify any stated milestones or current focus
- [ ] Ask user for optional one-paragraph intent (if needed)

### 2. Understand Repository Structure
- [ ] Run: `tree -L 3 -I '__pycache__|*.pyc|.git'` (or equivalent)
- [ ] Identify main entrypoints (CLI, API, etc.)
- [ ] Locate test directories
- [ ] Find configuration files

### 3. Review Recent Changes
- [ ] Run: `git log --oneline --since="[last audit date]" --stat`
- [ ] Identify areas of high churn: `git log --since="[last audit date]" --format=format: --name-only | sort | uniq -c | sort -rn | head -20`
- [ ] Check for new dependencies or major refactors

---

## Audit Execution (Follow SKILL.md Phases)

### Phase 0: Infer Project Intent
- [ ] Document core responsibilities
- [ ] Document primary workflows/pipelines
- [ ] Document key abstractions and artifacts
- [ ] Document non-goals
- [ ] Write down **Inferred Project Model** explicitly

### Phase 1: Architectural Mapping
- [ ] Map major components/modules
- [ ] Map data/control flow
- [ ] Identify explicit boundaries (APIs, schemas, DB tables, files)
- [ ] Identify implicit boundaries (conventions, naming, folder structure)

### Phase 2: Intent vs Implementation Alignment
- [ ] For each responsibility, assess:
  - [ ] Implementation location
  - [ ] Centralization vs scatter
  - [ ] Ownership clarity
  - [ ] Enforcement mechanism
- [ ] Classify alignment status (✅ ⚠ ❌ 🧨)

### Phase 3: Contract & Boundary Analysis
- [ ] For each boundary, assess:
  - [ ] Explicit definition
  - [ ] Validation
  - [ ] Versioning
  - [ ] Test coverage
- [ ] Rate enforcement quality

### Phase 4: Determinism, Traceability, Explainability
- [ ] Assess reproducibility
- [ ] Assess traceability
- [ ] Assess inspectability
- [ ] Assess observability of side effects

### Phase 5: Code Health & Structural Risk
- [ ] Identify complexity hotspots
- [ ] Identify duplication patterns
- [ ] Identify cross-layer coupling
- [ ] Identify fragile modules (high churn + low coverage)
- [ ] Assess extension points

### Phase 6: Test & QA Effectiveness
- [ ] Compare what's tested vs what's critical
- [ ] Check if tests encode contracts
- [ ] Assess regression safety
- [ ] Assess failure observability

### Phase 7: Findings & Prioritization
- [ ] Classify findings by severity (P0, P1, P2, P3)
- [ ] Write findings to FINDINGS.yaml
- [ ] Create ACTION_PLAN.md

---

## Post-Audit

### 1. Generate Artifacts
- [ ] AUDIT_REPORT.md (use template from assets/)
- [ ] FINDINGS.yaml (use template from assets/)
- [ ] ACTION_PLAN.md (use template from assets/)
- [ ] NEXT_AUDIT_CHECKLIST.md (update this checklist if needed)

### 2. Archive Audit Results
```bash
# Create audit archive directory if needed
mkdir -p audits/

# Archive with timestamp
cp AUDIT_REPORT.md "audits/AUDIT_REPORT_$(date +%Y%m%d).md"
cp FINDINGS.yaml "audits/FINDINGS_$(date +%Y%m%d).yaml"
cp ACTION_PLAN.md "audits/ACTION_PLAN_$(date +%Y%m%d).md"
```

### 3. Compare with Previous Audit (if available)
- [ ] Compare number of findings by severity
- [ ] Check if previous P0/P1 findings were resolved
- [ ] Identify new areas of concern
- [ ] Note improvements or regressions

---

## Metrics to Track Over Time

Track these metrics across audits to measure progress:

| Metric | Current Audit | Previous Audit | Change |
|--------|--------------|----------------|--------|
| Total findings | | | |
| P0 findings | | | |
| P1 findings | | | |
| P2 findings | | | |
| P3 findings | | | |
| Weak/missing contracts | | | |
| Fragile modules | | | |
| Test coverage gaps | | | |
| Alignment drift areas | | | |

---

## Commands Reference

```bash
# Repository structure
tree -L 3 -I '__pycache__|*.pyc|.git'

# Recent changes
git log --oneline --since="YYYY-MM-DD" --stat

# High churn files
git log --since="YYYY-MM-DD" --format=format: --name-only | sort | uniq -c | sort -rn | head -20

# Test coverage (if pytest-cov installed)
pytest --cov=. --cov-report=term-missing

# Find TODO/FIXME comments
grep -r "TODO\|FIXME\|XXX\|HACK" --include="*.py" .

# Count lines of code (if cloc installed)
cloc . --exclude-dir=.git,__pycache__,venv,.venv

# Find duplicated code (if pylint installed)
pylint --disable=all --enable=duplicate-code .
```

---

## Notes for Next Audit

[Leave space for auditor to note anything specific to remember for next time]
