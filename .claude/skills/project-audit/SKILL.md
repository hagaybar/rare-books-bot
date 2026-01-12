---
name: project-audit
description: |
  A project-neutral, repeatable audit skill for complex and evolving codebases.
  Produces a structured, evidence-based assessment of: project intent vs
  implementation, architectural coherence, contract enforcement, code health
  and maintainability, and test and QA effectiveness.

  The skill adapts to changing project direction by inferring the project model
  from code, docs, and user-provided intent — not from hardcoded assumptions.

  Use when: (1) The project has grown organically and needs structural audit,
  (2) Project direction or scope has evolved, (3) Before major refactors,
  releases, or onboarding, (4) Need an audit to rerun periodically and compare
  over time.

  When code changes are required, implementation is delegated to an existing
  language-specific expert skill (e.g. python-dev-expert).
---

# Project Audit – Skill Specification

## Inputs Expected

- Repository tree (or subset)
- Any available project intent signals (README, design docs, comments, ADRs)
- Optional: current focus or milestone (one paragraph max)

## Outputs Produced

- **AUDIT_REPORT.md** - Comprehensive audit findings and analysis
- **FINDINGS.yaml** - Machine-readable structured findings
- **ACTION_PLAN.md** - Prioritized remediation plan
- **NEXT_AUDIT_CHECKLIST.md** - Reusable playbook for future audits

## Core Principle

**The project model is inferred, not assumed.**

This skill first reconstructs:
- what the project *claims* to be doing
- what the project *actually* does
- where those two diverge

Only *after* that does it evaluate quality.

---

## Phase 0 — Infer Project Intent (Critical)

### Inputs used
- README / docs
- directory names
- module names
- CLI commands / entrypoints
- tests (what they assert is “important”)
- config files
- user-provided one-paragraph intent (if supplied)

### Outputs
Produce an explicit **Inferred Project Model**:
- Core responsibilities (tasks the system appears to serve)
- Primary workflows / pipelines
- Key abstractions and artifacts
- Non-goals (things explicitly or implicitly avoided)

> This model is written down and treated as *hypothesis*, not truth.

---

## Phase 1 — Architectural Mapping (Neutral)

Build a **descriptive architecture map**, not a prescriptive one:
- major components/modules
- data/control flow between them
- explicit boundaries (APIs, schemas, DB tables, files)
- implicit boundaries (conventions, naming, folder structure)

No judgment yet — just mapping.

---

## Phase 2 — Intent vs Implementation Alignment

For each inferred responsibility:
- Where is it implemented?
- Is it centralized or scattered?
- Is ownership clear?
- Is it enforced by code or only by convention?

Classify each as:
- ✅ aligned
- ⚠ partially aligned
- ❌ drifted / ambiguous
- 🧨 contradictory

This phase detects **directional drift**, not “bugs”.

---

## Phase 3 — Contract & Boundary Analysis (Abstract)

Instead of assuming specific contracts, the skill asks:
- What *artifacts* cross boundaries? (objects, schemas, files, DB rows)
- Are those artifacts:
  - explicitly defined?
  - validated?
  - versioned?
  - test-covered?

Contracts may be:
- schemas
- data classes
- implicit dict structures
- file formats
- conventions

The audit evaluates **how well boundaries are enforced**, not *what* they are.

---

## Phase 4 — Determinism, Traceability, and Explainability

Evaluate whether:
- outcomes are reproducible
- behavior is traceable to inputs
- decisions are inspectable after the fact
- side effects are observable

This applies equally to:
- data pipelines
- rule engines
- LLM calls
- heuristics
- config-driven behavior

---

## Phase 5 — Code Health & Structural Risk

Identify:
- complexity hotspots
- duplication
- cross-layer coupling
- fragile modules (high churn + low test coverage)
- unclear extension points

The goal is **risk discovery**, not style nitpicking.

---

## Phase 6 — Test & QA Effectiveness (Generic)

Assess:
- what is tested vs what appears critical
- whether tests encode contracts or only happy paths
- regression safety
- observability of failures

No assumptions about test frameworks or coverage targets.

---

## Phase 7 — Findings & Prioritization

Findings are classified by *impact*, not taste:
- P0 — correctness, data loss, contract breakage
- P1 — architectural drift, scaling blockers
- P2 — maintainability risk
- P3 — clarity, ergonomics

---

## Delegation Rule (Explicit)

This skill:
- **diagnoses, structures, prioritizes**
- **never performs large refactors**

Any finding that requires code changes must be expressed as:
- scope
- desired invariant
- acceptance criteria
- test expectations

Implementation is delegated to an existing expert skill
(e.g. python-dev-expert).

---

## Output Artifacts (Always)

**Templates are available in `assets/` directory. Use these as starting points for consistent output structure.**

### 1) AUDIT_REPORT.md
Template: `assets/AUDIT_REPORT_template.md`

Includes:
- Inferred Project Model
- Architecture Map
- Alignment Analysis
- Contract & Boundary Review
- Risk Hotspots
- Test Effectiveness
- Key Risks & Recommendations

### 2) FINDINGS.yaml
Template: `assets/FINDINGS_template.yaml`

Machine-readable findings with:
- id
- severity
- area
- description
- evidence (file paths, symbols)
- recommended invariant
- acceptance criteria

### 3) ACTION_PLAN.md
Template: `assets/ACTION_PLAN_template.md`

Ordered, minimal plan:
- fix P0 first
- each step references findings
- includes rollback notes where relevant

### 4) NEXT_AUDIT_CHECKLIST.md
Template: `assets/NEXT_AUDIT_CHECKLIST_template.md`

A reusable playbook:
- what inputs to gather
- what commands to run
- what metrics to compare
- how to diff against previous audits

