# Offline Re-score of 2026-06-10-postfix (issues #10/#11) — free, deterministic

58 stored plans replayed through the FIXED metrics and TODAY'S executor. No LLM calls.

## Judge-score impact: none on this run
avg 4.026 → 4.026, 0 queries changed ≥0.05. The RANGE and clarification fixes
are verified by unit tests and matter going forward (q34-class queries, q59),
but this particular stored run contained no entry whose stored plan hits them.

## The headline metric is finally trustworthy: 22 → 10 true zeros
- 6 were metric artifacts, now classified correctly (q17/q18/q36 aggregate
  overviews succeed with facets; q15/q16 follow-ups are skipped — no session
  context in single-turn eval; q58 'hi' empty-is-correct).
- 6 were fixed by the executor work since the run (issues #3/#4/#6 recoveries).
- 10 stored plans still produce zero, in two known groups:
  1. **q14/q27/q29/q30 — empty stored plans** (issue #5). Replay cannot fix
     emptiness, but the live interpreter no longer produces it (12/12
     verification in issue #5) — these clear on the next fresh benchmark run.
  2. **q24/q40/q44/q49/q53/q55 — genuine recall gaps**, each mapped to an open
     committee recommendation: Hebrew morphology/clitic ladder rungs
     (q24/q40/q55), query-time place aliases for קושטא (q53), manuscripts
     concept/field routing (q49), speculative year-range demotion (q44).

## New guardrail
Eval entries now carry a `judge_recall_disagreement` flag when the judge
scores ≥4.0 on empirically-zero recall (the q01-class smell).
