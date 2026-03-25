# Historian Enhancement Plan — Process Flow

```mermaid
graph TD
    START([Start]) --> P1[Phase 1: Deep Research]

    subgraph P1 [Phase 1: Deep Research - Parallel]
        R1[Analyze Report<br/>Extract 5 enhancements,<br/>root causes, scores]
        R2[Analyze Query Pipeline<br/>db_adapter, intent_agent,<br/>execute.py, main.py]
        R3[Analyze Narrative Pipeline<br/>narrative_agent, aggregation,<br/>exploration, formatter]
        R4[Analyze Data Model<br/>SQLite schema, authority tables,<br/>agent storage patterns]
    end

    P1 --> P2[Phase 2: Enhancement Planning]

    subgraph P2 [Phase 2: Enhancement Planning - Sequential]
        E1[E1: Agent Name Alias Table<br/>CRITICAL - fixes 4 failures<br/>+70 points]
        E2[E2: Analytical Query Routing<br/>CRITICAL - unlocks 3 query types<br/>+33 points]
        E3[E3: Cross-Reference Engine<br/>HIGH - scholarly connections<br/>+24 points]
        E4[E4: Scholarly Narrative<br/>HIGH - pedagogical depth<br/>+21 points]
        E5[E5: Curation Engine<br/>MEDIUM - exhibit planning<br/>+15 points]

        E1 --> E2 --> E3 --> E4 --> E5
    end

    P2 --> P3[Phase 3: Task Breakdown & Validation]

    subgraph P3 [Phase 3: Task Breakdown & Validation - Parallel]
        TB[Generate Task Breakdown<br/>Dependencies, ordering,<br/>critical path, milestones]
        VP[Generate Validation Plan<br/>20 queries, expected scores,<br/>regression tests, gates]
    end

    P3 --> P4[Phase 4: Codebase Verification]

    P4[Verify Plan Against Codebase<br/>File paths, function signatures,<br/>line numbers, schema claims] --> P5[Phase 5: Assembly]

    P5[Assemble Plan Document<br/>5 sections, tables, SQL,<br/>TDD plans, acceptance criteria] --> BP{Breakpoint:<br/>Review Plan}

    BP -->|Approved| DONE([Complete])
    BP -->|Rejected| P2

    style E1 fill:#ff6b6b,color:#fff
    style E2 fill:#ff6b6b,color:#fff
    style E3 fill:#ffa500,color:#fff
    style E4 fill:#ffa500,color:#fff
    style E5 fill:#4ecdc4,color:#fff
    style BP fill:#ffe66d,color:#333
```

## Legend

| Color | Meaning |
|-------|---------|
| Red | CRITICAL priority |
| Orange | HIGH priority |
| Teal | MEDIUM priority |
| Yellow | Breakpoint (human review) |

## Task Count by Phase

| Phase | Tasks | Parallel? | Dependencies |
|-------|-------|-----------|-------------|
| Phase 1 | 4 | Yes (all parallel) | None |
| Phase 2 | 5 | No (sequential) | Phase 1 research |
| Phase 3 | 2 | Yes (parallel) | Phase 2 plans |
| Phase 4 | 1 | N/A | Phase 3 outputs |
| Phase 5 | 1 | N/A | Phase 4 verification |
| **Total** | **13 agent tasks + 1 breakpoint** | | |

## Enhancement Dependency Graph

```mermaid
graph LR
    E1[E1: Agent Aliases<br/>3.5d CRITICAL] --> E3[E3: Cross-Reference<br/>4.5d HIGH]
    E2[E2: Analytical Routing<br/>3d CRITICAL] --> E5[E5: Curation<br/>3.5d MEDIUM]
    E3 --> E4[E4: Scholarly Narrative<br/>4d HIGH]
    E4 --> E5

    style E1 fill:#ff6b6b,color:#fff
    style E2 fill:#ff6b6b,color:#fff
    style E3 fill:#ffa500,color:#fff
    style E4 fill:#ffa500,color:#fff
    style E5 fill:#4ecdc4,color:#fff
```

## Score Projection

```
Baseline:       ████░░░░░░░░░░░░░░░░  7.55/25 (30%)  — 7 FAIL queries
After E1+E2:    ██████████░░░░░░░░░░  12.70/25 (51%) — highest ROI
After E1-E3:    ████████████░░░░░░░░  13.90/25 (56%)
After E1-E4:    █████████████░░░░░░░  14.95/25 (60%)
After All:      ██████████████░░░░░░  15.70/25 (63%) — 0 FAIL queries
```
