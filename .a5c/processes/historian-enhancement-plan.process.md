# Historian Enhancement Plan — Process Description

## Purpose

Transform the Historian Evaluation Report's 5 recommended enhancements into a concrete, codebase-verified implementation plan. The output is a single markdown document (`reports/historian-enhancement-plan.md`) containing executive summary, detailed plans per enhancement, task breakdown, validation plan, and open questions.

## Why This Process

The historian evaluation scored the system at 30.2% (7.55/25) with 7 FAIL-grade queries. The 5 enhancements could double this to 62.8% (15.70/25) with 0 failures. However, the evaluation report describes enhancements at a conceptual level. This process grounds each enhancement in the actual codebase — verifying every file path, function signature, and schema claim — to produce a plan that can be executed with confidence.

## Process Architecture

The process composes three patterns:

1. **Brownfield Analysis** (from `spec-kit-brownfield`): Deep codebase research before planning
2. **Sequential Enhancement Planning**: Each plan builds on prior plans to avoid conflicts
3. **Codebase Verification**: Every claim in the plan is verified against actual code

## Phase Details

### Phase 1: Deep Research (4 parallel agents)

Four research agents analyze the codebase simultaneously:

| Agent | Focus | Key Outputs |
|-------|-------|-------------|
| Report Analyzer | Parse evaluation report | Structured enhancement data, root causes, score projections |
| Query Pipeline Analyzer | db_adapter.py, intent_agent.py, main.py | Normalization steps, filter compilation, routing logic |
| Narrative Pipeline Analyzer | narrative_agent.py, aggregation.py, exploration_agent.py | Aggregation capabilities, narrative limits, missing modules |
| Data Model Analyzer | SQLite schema, authority tables | Agent storage patterns, publisher variant pattern for replication |

### Phase 2: Enhancement Planning (5 sequential agents)

Each enhancement is planned by a dedicated agent with access to all research data and prior plans:

| Enhancement | Agent Focus | Report Questions | Priority |
|-------------|------------|-----------------|----------|
| E1: Agent Name Alias Table | Schema design, order-insensitive matching, cross-script aliases | Q3, Q6, Q7, Q8, Q12, Q19 | CRITICAL |
| E2: Analytical Query Routing | Intent detection, aggregation routing, narrative threshold | Q14, Q15, Q20 | CRITICAL |
| E3: Cross-Reference Engine | Entity connections, set comparison, enrichment data usage | Q1, Q2, Q4, Q5, Q9, Q10, Q13, Q17 | HIGH |
| E4: Scholarly Narrative | Thematic templates, significance scoring, pedagogical framing | Q1, Q2, Q4, Q5, Q11, Q16, Q18 | HIGH |
| E5: Curation Engine | Selection algorithm, diversity optimization, exhibit formatting | Q20, Q4, Q11, Q14, Q15 | MEDIUM |

Each plan includes 11 sections: goal, report failures addressed, affected components, implementation steps, schema changes, retrieval changes, risks, TDD plan, quality gates, deliverables, acceptance criteria.

### Phase 3: Task Breakdown & Validation (2 parallel agents)

| Agent | Output |
|-------|--------|
| Task Breakdown | Ordered task list with dependencies, milestones, critical path, parallel opportunities |
| Validation Plan | Per-enhancement query expectations, regression tests, metrics, quality gates |

### Phase 4: Codebase Verification (1 agent)

Verifies every claim in the plans against the actual codebase:
- File existence checks
- Function signature validation
- Line number accuracy
- Schema compatibility
- Import path validity

### Phase 5: Assembly (1 agent)

Combines all outputs into a single markdown document at `reports/historian-enhancement-plan.md`.

## Breakpoints

Only 1 breakpoint (aligned with user profile: minimal breakpoint tolerance):
- **Plan Review**: After assembly, before completion. User reviews the final document.

## Key Constraints

All plans must:
- Preserve structured retrieval (SQLite fielded queries, not embeddings)
- Preserve explicit normalization (raw values always kept alongside normalized)
- Preserve reversible transformations (raw → normalized mapping with confidence)
- Preserve visible uncertainty (confidence scores on all normalized values)
- Maintain separation of catalog data, normalized data, and enrichment data
- Prefer incremental delivery (each enhancement independently testable)
- Minimize regression risk (additive schema changes only, no destructive modifications)

## Expected Output

A `reports/historian-enhancement-plan.md` document with:
1. Executive summary with score projections
2. Detailed plan for each of 5 enhancements (11 subsections each)
3. Task breakdown table (~30-40 tasks across all enhancements)
4. Validation plan with 20-query evaluation procedure
5. Open questions and verification accuracy report

## Effort Estimates

- Process execution: ~13 agent tasks across 5 phases
- Expected runtime: 15-25 minutes
- Plan covers: ~18.5 developer-days of implementation work
