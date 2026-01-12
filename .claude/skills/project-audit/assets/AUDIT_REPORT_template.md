# Project Audit Report

**Date:** [YYYY-MM-DD]
**Project:** [Project Name]
**Auditor:** Claude (project-audit skill)
**Scope:** [Brief description of audit scope]

---

## Executive Summary

[2-3 paragraph summary of key findings, major risks, and recommended actions]

---

## Inferred Project Model

### Core Responsibilities
[What the project claims to do and appears designed to do]

### Primary Workflows
[Key pipelines, processes, or user journeys]

### Key Abstractions and Artifacts
[Central data structures, schemas, file formats, or domain concepts]

### Non-Goals
[Things explicitly or implicitly avoided by the project]

---

## Architecture Map

### Major Components
[List and briefly describe main modules, packages, or subsystems]

### Data Flow
[How data moves through the system]

### Control Flow
[How execution flows between components]

### Explicit Boundaries
[APIs, schemas, database tables, file interfaces]

### Implicit Boundaries
[Conventions, naming patterns, folder structure]

---

## Alignment Analysis

### [Responsibility 1]
- **Implementation location:** [Where it lives]
- **Centralization:** [Centralized / Scattered]
- **Ownership clarity:** [Clear / Ambiguous]
- **Enforcement:** [Code / Convention]
- **Status:** [✅ aligned / ⚠ partially aligned / ❌ drifted / 🧨 contradictory]

[Repeat for each key responsibility]

---

## Contract & Boundary Review

### [Boundary 1: e.g., "Input Data Schema"]
- **Artifacts crossing boundary:** [objects, schemas, files, DB rows]
- **Explicitly defined?** [Yes/No + evidence]
- **Validated?** [Yes/No + evidence]
- **Versioned?** [Yes/No + evidence]
- **Test-covered?** [Yes/No + evidence]
- **Assessment:** [Strong / Adequate / Weak / Missing]

[Repeat for each major boundary]

---

## Determinism, Traceability, and Explainability

### Reproducibility
[Can outcomes be reproduced from inputs?]

### Traceability
[Can behavior be traced to inputs?]

### Inspectability
[Can decisions be inspected after the fact?]

### Observability
[Are side effects observable?]

---

## Code Health & Structural Risk

### Complexity Hotspots
[Files/modules with high complexity]

### Duplication
[Significant duplication patterns]

### Cross-Layer Coupling
[Inappropriate dependencies between layers]

### Fragile Modules
[High churn + low test coverage]

### Extension Points
[How clear/documented are extension mechanisms?]

---

## Test & QA Effectiveness

### Coverage vs Criticality
[What's tested vs what appears critical]

### Contract Encoding
[Do tests encode contracts or only happy paths?]

### Regression Safety
[How safe is the project from regressions?]

### Failure Observability
[How observable are test failures?]

---

## Key Risks & Recommendations

### P0 — Critical
[Correctness, data loss, contract breakage issues]

### P1 — High
[Architectural drift, scaling blockers]

### P2 — Medium
[Maintainability risks]

### P3 — Low
[Clarity, ergonomics improvements]

---

## Conclusion

[Final assessment and next steps]
