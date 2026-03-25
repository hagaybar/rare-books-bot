# Definitive Implementation Plan — Process Diagram

## Process Flow

```
Phase 1: EXTRACT & RECONCILE
  └── Agent reads ALL 13 reports
       ├── Original analysis (reports 01-07)
       └── Empirical verification (reports 08-12)
       └── For each contradiction: empirical WINS
       └── Output: Reconciled fact base JSON
            │     (architecture, screenSpecs, dataReality,
            │      apiReality, backendWork, timeline,
            │      features, risks, contradictions)
            │
            ▼
Phase 2: WRITE THE PLAN
  └── Agent produces IMPLEMENTATION_PLAN.md
       ├── Section 1: Product Vision & Architecture
       ├── Section 2: Screen Specifications (9 screens × detailed spec)
       ├── Section 3: Backend Work Inventory (every endpoint to build)
       ├── Section 4: Phased Implementation Plan (8 weeks, 6 phases)
       ├── Section 5: Features — Keep vs Drop
       ├── Section 6: Risks & Mitigations
       ├── Section 7: Verification Stamp [placeholder]
       └── Section 8: Appendix — Contradiction Log
            │
            ▼
Phase 3: VERIFY CONSISTENCY
  └── QA Agent cross-checks plan against empirical data
       ├── Every screen spec → actual API shapes (report 10)
       ├── Every backend item → API gaps (reports 10-12)
       ├── Timeline → empirical corrections (report 12)
       ├── Features → no dropped feature appears in specs
       └── Output: issues[], pass/fail verdict
            │
            ▼
Phase 4: FINALIZE
  └── Editor Agent applies fixes + verification stamp
       ├── Fix any issues from Phase 3
       ├── Fill Section 7 with verification results
       └── Add "supersedes all reports" declaration
            │
            ▼
        IMPLEMENTATION_PLAN.md
        (single source of truth)
```

## Key Design Decisions

- **Extract before write**: Phase 1 builds a structured fact base so Phase 2 writes from reconciled data, not raw reports
- **Empirical override rule**: When original reports and empirical reports disagree, empirical ALWAYS wins
- **Self-verification**: Phase 3 catches any assumptions that survived reconciliation
- **Surgical fixes**: Phase 4 only changes what verification flagged, preserving the plan's structure
- **Single output file**: IMPLEMENTATION_PLAN.md at project root — one document to rule them all
