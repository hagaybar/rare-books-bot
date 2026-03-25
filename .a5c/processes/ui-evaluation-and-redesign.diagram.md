# UI Evaluation and Redesign — Process Diagram

## Process Flow

```
Phase 1: UI Inventory Discovery
  └── Agent: Scan entire project for all UI surfaces
       └── Output: reports/01-ui-inventory.md + JSON inventory
            │
            ▼
Phase 2: Deep UI Analysis
  └── Agent: Read ALL source files per UI, evaluate quality/features/coupling
       └── Output: reports/02-per-ui-evaluation.md + JSON evaluations
            │
            ▼
Phase 3: Project Goal Inference
  └── Agent: Analyze codebase, pipelines, data model → infer true purpose
       └── Output: reports/03-project-goal.md + JSON goal/users/useCases
            │
            ▼
Phase 4: Alignment Assessment
  └── Agent: Rate each UI against real project goal
       └── Output: reports/04-alignment-assessment.md + JSON alignments
            │
            ▼
Phase 5: Redundancy Analysis
  └── Agent: Feature matrix, overlap detection, historical noise
       └── Output: reports/05-redundancy-analysis.md + JSON matrix
            │
            ▼
Phase 6: New UI Definition + Tech Recommendation
  └── Agent: Design new UI, information architecture, React vs Angular
       └── Output: reports/06-new-ui-definition.md + JSON definition
            │
            ▼
Phase 7: Migration & Decommission Plan
  └── Agent: Phased plan, early retirements, deletion criteria
       └── Output: reports/07-migration-plan.md + JSON plan
            │
            ▼
Phase 8: Consolidated Executive Report
  └── Agent: Synthesize all sections into single 12-section report
       └── Output: reports/00-executive-report.md + JSON summary
```

## Key Design Decisions

- **Sequential execution**: Each phase depends on prior phases for context
- **No breakpoints**: YOLO mode — fully autonomous execution
- **Agent-only tasks**: All phases use LLM reasoning, no scripted logic
- **Dual output**: Each phase produces both a markdown report and structured JSON
- **Progressive context**: Later phases receive all prior phase results for informed analysis
