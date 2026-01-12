# Action Plan

**Date:** [YYYY-MM-DD]
**Project:** [Project Name]
**Based on:** AUDIT_REPORT.md and FINDINGS.yaml

---

## Execution Principles

1. **Fix P0 findings first** - Address critical correctness and data integrity issues
2. **Each step references findings** - Trace actions back to FINDINGS.yaml
3. **Include rollback notes** - Document how to revert if needed
4. **Minimal changes** - Only what's necessary to address findings
5. **Delegate implementation** - Use appropriate expert skills (e.g., python-dev-expert)

---

## Phase 1: Critical Fixes (P0)

### Action 1.1: [Brief title]
- **Addresses:** Finding F001, F003
- **Description:** [What needs to be done]
- **Scope:** [Files/modules affected]
- **Delegated to:** [skill-name or "direct"]
- **Acceptance criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Rollback:** [How to revert if needed]

### Action 1.2: [Brief title]
- **Addresses:** Finding F002
- **Description:** [What needs to be done]
- **Scope:** [Files/modules affected]
- **Delegated to:** [skill-name or "direct"]
- **Acceptance criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Rollback:** [How to revert if needed]

---

## Phase 2: High Priority (P1)

### Action 2.1: [Brief title]
- **Addresses:** Finding F004
- **Description:** [What needs to be done]
- **Scope:** [Files/modules affected]
- **Delegated to:** [skill-name or "direct"]
- **Acceptance criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Rollback:** [How to revert if needed]

---

## Phase 3: Medium Priority (P2)

### Action 3.1: [Brief title]
- **Addresses:** Finding F005, F006
- **Description:** [What needs to be done]
- **Scope:** [Files/modules affected]
- **Delegated to:** [skill-name or "direct"]
- **Acceptance criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Rollback:** [How to revert if needed]

---

## Phase 4: Low Priority (P3)

### Action 4.1: [Brief title]
- **Addresses:** Finding F007
- **Description:** [What needs to be done]
- **Scope:** [Files/modules affected]
- **Delegated to:** [skill-name or "direct"]
- **Acceptance criteria:**
  - [ ] [Criterion 1]
  - [ ] [Criterion 2]
- **Rollback:** [How to revert if needed]

---

## Validation & Testing

After each phase:
- [ ] Run existing test suite
- [ ] Verify acceptance criteria from FINDINGS.yaml
- [ ] Check for regression in unmodified areas
- [ ] Update documentation if needed

---

## Dependencies & Blockers

[Document any dependencies between actions or blockers that need resolution]

---

## Estimated Scope

- **P0 fixes:** [X actions]
- **P1 fixes:** [Y actions]
- **P2 fixes:** [Z actions]
- **P3 fixes:** [W actions]

**Total:** [X+Y+Z+W actions]

---

## Notes

[Any additional context, constraints, or considerations for implementation]
