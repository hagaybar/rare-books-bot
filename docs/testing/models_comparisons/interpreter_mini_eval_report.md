# GPT-4.1-Mini Interpreter Evaluation Report

**Date:** 2026-04-03
**Evaluation set:** `data/eval/interpreter_nano_queries.json` (13 queries)
**Model under test:** `gpt-4.1-mini` (interpreter stage only)
**Comparison models:** `gpt-4.1-nano`, `gpt-4.1` (Aldine baseline)
**Scoring:** 0-3 scale (0 = broken, 1 = partial, 2 = good with minor issues, 3 = perfect)

---

## 1. Executive Summary

**Verdict: gpt-4.1-mini is a strong candidate for the default interpreter model, contingent on fixing shared prompt-level issues (OOS detection, incunabula subject mapping).**

Mini scores 2.46/3.0 overall (82%) vs nano's 2.08/3.0 (69%) -- a meaningful +18% improvement. On in-scope queries specifically, mini achieves 2.62 vs nano's 2.00, a +31% quality gap. Mini eliminates nano's two worst structural failures (incomplete plans) while maintaining the same ambiguity handling quality. The trade-off is 45% higher latency (3.96s vs 2.73s) and 4x cost, but both remain well within acceptable bounds for a pipeline where the narrator stage dominates total cost and latency.

### Key Metrics

| Model | Avg Score | Success Rate (>=2) | Perfect (3) | Avg Latency | Est. Cost/Query |
|-------|-----------|-------------------|-------------|-------------|-----------------|
| **gpt-4.1-mini** | **2.46 / 3.0 (82%)** | **11/13 (85%)** | **8/13 (62%)** | **3.96s** | **~$0.0019** |
| gpt-4.1-nano | 2.08 / 3.0 (69%) | 9/13 (69%) | 5/13 (38%) | 2.73s | ~$0.0005 |
| gpt-4.1 (est.) | ~2.7-2.8 / 3.0 | ~12/13 (est.) | ~10/13 (est.) | ~4-6s (est.) | ~$0.0094 |

*gpt-4.1 estimates are based on the Aldine Press test and expected behavior on the shared failure patterns. A direct 13-query evaluation on gpt-4.1 has not yet been run.*

---

## 2. Results by Category

### 2.1 In-Scope Queries (8)

| ID | Query | Mini Score | Mini Latency | Key Issues |
|----|-------|-----------|-------------|------------|
| q_is01 | Books published by Insel Verlag | 3 | 3.02s | None -- perfect publisher retrieval with resolve step |
| q_is02 | What was printed in Basel? | 3 | 2.74s | None -- correct imprint_place filter |
| q_is03 | Latin books from the sixteenth century | 2 | 2.88s | Date start 1501 vs expected 1500 (minor boundary, same issue as nano) |
| q_is04 | Books illustrated by Ludwig Schwerin | 3 | 4.14s | None -- correct agent + role filter (**fixed vs nano**) |
| q_is05 | Josephus Flavius and his works | 3 | 5.04s | None -- resolve + retrieve + enrich (**fixed vs nano**) |
| q_is06 | Cities with the most books | 3 | 2.95s | None -- correct aggregate on imprint_place |
| q_is07 | Hebrew books in Amsterdam 1600-1800 | 3 | 4.49s | None -- all three filters correct (**improved vs nano**) |
| q_is08 | Interested in incunabula | 1 | 3.73s | Date filter (1450-1500) instead of subject filter -- 7 vs 34 records |

**In-scope average: 2.62 / 3.0 (87%)**

**What mini handles well:**
- All filter types: publisher, place, language, date range, agent + role, aggregation
- Multi-step plans with resolve + retrieve + enrich chains (q_is04, q_is05, q_is07)
- Language code mapping ("Latin" -> "lat", "Hebrew" -> "heb") -- correct in all cases
- Role-specific queries: correctly added `agent_role = 'illustrator'` filter for q_is04

**Where mini still struggles:**
- **q_is08 (incunabula):** Same failure as nano -- used date range (1450-1500) instead of subject filter. This is a prompt-level issue: the model applies correct general knowledge about incunabula but does not know this collection uses "Incunabula" as a subject heading for books *about* incunabula. This would likely affect gpt-4.1 as well without prompt guidance.

### 2.2 Out-of-Scope Queries (2)

| ID | Query | Score | Detected OOS? | Confidence | Clarification? |
|----|-------|-------|---------------|------------|----------------|
| q_oos01 | Machine learning / computer science | 2 | No | 0.90 (too high) | None |
| q_oos02 | J.K. Rowling | 1 | No | 0.95 (far too high) | None |

**Did mini identify these as OOS?** No. Neither query was flagged as out-of-scope.

**Analysis:** Mini exhibits the same OOS-detection weakness as nano. Both models treat these queries as standard retrievals with high confidence. The specific patterns differ slightly:

- **q_oos01 (machine learning):** Mini used subject CONTAINS filters for both terms, similar to nano. Unlike nano, mini did not provide a clarification. The filters would correctly return 0 results, but the model showed no awareness that modern CS topics are inherently absent from a rare books collection.
- **q_oos02 (J.K. Rowling):** Mini confidently (0.95) built a resolve_agent + retrieve plan with no clarification, identical to nano's behavior. A modern author born in 1965 has no place in a rare books collection, yet the model processed it as routine.

**Root cause:** This is almost certainly a **prompt/schema issue**, not a model capacity issue. The interpreter prompt does not instruct the model to reason about whether a query falls within the collection's temporal and topical scope. Both nano and mini fail identically, suggesting the fix belongs in the prompt.

### 2.3 Ambiguous Queries (3)

| ID | Query | Score | Clarification Provided? | Default Interpretation | Confidence |
|----|-------|-------|------------------------|----------------------|------------|
| q_amb01 | Really old books | 3 | Yes ("specify century, region...") | 1401-1500 (15th century) | 0.80 |
| q_amb02 | What do you have by Moses? | 3 | Yes (mentions Maimonides, prophet) | resolve_agent for "Moses" | 0.75 |
| q_amb03 | Venice books | 2 | Yes ("specify subject, period...") | retrieve imprint_place=venice | 0.80 |

**Ambiguous average: 2.67 / 3.0 -- identical to nano.**

**Analysis:** Ambiguity handling is equally strong for both models. Mini:
- Lowered confidence appropriately for all three (0.75-0.85 vs 0.90-0.95 for clear queries)
- Provided useful clarification messages in all three cases
- Made reasonable default interpretations while inviting refinement

The one weakness (q_amb03 scoring 2) matches nano exactly: classifying "Tell me about" as retrieval rather than overview intent. Both models default to a flat retrieve of 164 Venice records instead of an analytical summary.

Mini's clarification style differs slightly from nano: mini's clarifications are more generic ("specify century, region, language, subject, or author") while nano was more query-specific (e.g., "I interpret 'really old books' as books printed in the 15th century. If you mean a different period..."). In practice, both approaches work.

---

## 3. Head-to-Head: Mini vs Nano vs GPT-4.1

### 3.1 Side-by-Side Score Comparison

| ID | Query (truncated) | Nano Score | Mini Score | Delta | Winner |
|----|-------------------|-----------|-----------|-------|--------|
| q_is01 | Insel Verlag | 3 | 3 | 0 | Tie |
| q_is02 | Printed in Basel | 3 | 3 | 0 | Tie |
| q_is03 | Latin 16th century | 2 | 2 | 0 | Tie |
| q_is04 | Illustrated by Schwerin | **1** | **3** | **+2** | **Mini** |
| q_is05 | Josephus Flavius | **1** | **3** | **+2** | **Mini** |
| q_is06 | Cities with most books | 3 | 3 | 0 | Tie |
| q_is07 | Hebrew Amsterdam 1600-1800 | **2** | **3** | **+1** | **Mini** |
| q_is08 | Incunabula | 1 | 1 | 0 | Tie (both fail) |
| q_oos01 | Machine learning | 2 | 2 | 0 | Tie |
| q_oos02 | J.K. Rowling | 1 | 1 | 0 | Tie (both fail) |
| q_amb01 | Really old books | 3 | 3 | 0 | Tie |
| q_amb02 | By Moses | 3 | 3 | 0 | Tie |
| q_amb03 | Venice books | 2 | 2 | 0 | Tie |
| | **Totals** | **27/39** | **32/39** | **+5** | **Mini** |

**Summary:** Mini matches nano on 10/13 queries and outperforms on 3. Nano never outperforms mini on any query. The three improvements are all in-scope queries requiring multi-step structured plans -- precisely the area where model capacity matters most.

### 3.2 Where Mini Improved Over Nano

1. **q_is04 (Ludwig Schwerin, +2):** Nano omitted the `agent_role = 'illustrator'` filter, returning 17 records instead of 10. Mini correctly included the role filter, producing a complete resolve_agent + retrieve plan with both agent_norm and agent_role constraints.

2. **q_is05 (Josephus Flavius, +2):** Nano resolved the agent but stopped there -- no retrieve step followed. Mini produced a complete 3-step plan: resolve_agent (with multilingual variants) + retrieve + enrich(bio, links). This is the expected plan for an entity_exploration query.

3. **q_is07 (Hebrew Amsterdam 1600-1800, +1):** Nano used `resolve_publisher` for the place name "Amsterdam" (semantic mismatch) and set end date to 1799 instead of 1800. Mini used `imprint_place` directly with the correct value and all three filters (language, place, year range) producing the expected 112 records. Minor note: mini's results file showed the right plan; nano's was semantically confused.

### 3.3 Shared Failures (Same Query Fails on Both Models)

| ID | Query | Both Score | Root Cause | Fix Location |
|----|-------|-----------|------------|-------------|
| q_is08 | Incunabula | 1 | Date filter instead of subject filter | **Prompt** -- add subject-mapping guidance |
| q_oos02 | J.K. Rowling | 1 | No OOS detection, high confidence | **Prompt** -- add collection scope instructions |

These shared failures strongly indicate **prompt-level issues**, not model-level issues. If gpt-4.1 also fails on these (likely without prompt fixes), it confirms the hypothesis.

### 3.4 Cost Comparison

| Model | Input ($/1M tok) | Output ($/1M tok) | Est. Cost/Query* | Relative | Annual (1K queries/day) |
|-------|-------------------|--------------------|--------------------|----------|------------------------|
| gpt-4.1-nano | $0.10 | $0.40 | ~$0.0005 | **1x** | ~$182 |
| **gpt-4.1-mini** | **$0.40** | **$1.60** | **~$0.0019** | **4x** | **~$694** |
| gpt-4.1 | $2.00 | $8.00 | ~$0.0094 | 20x | ~$3,431 |

*Estimated based on ~1,500 input tokens and ~800 output tokens per interpreter call.*

**Cost perspective:** Mini costs 4x nano but 5x less than gpt-4.1. At ~$0.002/query, the interpreter cost is negligible compared to the narrator stage. Even at 1,000 queries/day, mini adds only ~$1.90/day vs nano's ~$0.50/day -- a $1.40/day premium for a +18% quality improvement. The narrator stage (which uses gpt-4.1 at ~5,000+ output tokens) dominates total pipeline cost regardless.

### 3.5 Latency Comparison

| Model | Avg Latency | Median | Min | Max | Source |
|-------|-------------|--------|-----|-----|--------|
| gpt-4.1-nano | **2.73s** | 2.34s | 1.36s | 6.70s | 13-query eval |
| gpt-4.1-mini | 3.96s | 3.73s | 2.74s | 5.87s | 13-query eval |
| gpt-4.1 (est.) | ~4-6s | -- | -- | -- | Aldine baseline |

Mini is 45% slower than nano on average (3.96s vs 2.73s). However, mini's latency is more consistent: its range is 2.74-5.87s (3.13s spread) vs nano's 1.36-6.70s (5.34s spread). Nano has a lower floor but a higher ceiling, likely due to variance in how it handles complex queries.

In the full pipeline context (interpreter + narrator typically totaling 15-30s), the 1.23s average latency increase from nano to mini is unlikely to be perceptible to users.

### 3.6 Quality by Query Type

| Query Type | Nano Avg | Mini Avg | Delta | Assessment |
|------------|----------|----------|-------|------------|
| In-scope (8) | 2.00 | **2.62** | **+0.62** | Mini substantially better -- fixes multi-step plan failures |
| Out-of-scope (2) | 1.50 | 1.50 | 0 | Identical -- both fail on OOS detection (prompt issue) |
| Ambiguous (3) | 2.67 | 2.67 | 0 | Identical -- both handle ambiguity well |
| **Overall (13)** | **2.08** | **2.46** | **+0.38** | Mini wins on the queries that matter most |

**Key insight:** Mini's advantage is concentrated in in-scope queries -- the bread-and-butter of the interpreter pipeline. It produces more complete and structurally correct plans for multi-step queries involving agent resolution, role filtering, and entity exploration. The areas where both models score identically (OOS, ambiguous) are either prompt-fixable or already well-handled.

---

## 4. Failure Analysis

### 4.1 Queries Scoring 0-1

| ID | Nano Score | Mini Score | Failure Type | Root Cause |
|----|-----------|-----------|-------------|------------|
| q_is04 | 1 | **3 (fixed)** | Missing role filter | Nano model capacity -- mini resolves this |
| q_is05 | 1 | **3 (fixed)** | Incomplete plan | Nano model capacity -- mini resolves this |
| q_is08 | 1 | 1 | Wrong filter strategy | **Prompt issue** -- both use date instead of subject |
| q_oos02 | 1 | 1 | Missing scope awareness | **Prompt issue** -- neither detects OOS |

### 4.2 Shared Failures (Prompt-Level Issues)

**q_is08 (incunabula) -- both score 1:**
Both models interpret "incunabula" as a date range (pre-1501 books) rather than searching the `subject` field where "Incunabula" is used as a heading for books *about* incunabula (bibliographies, facsimiles, catalogs). The collection has 34 subject-tagged records but only 7 actual pre-1501 imprints. This is a data-specific nuance that requires prompt-level guidance: the interpreter needs to know that terms like "incunabula" map to subject headings in this collection, not just date filters.

**q_oos02 (Rowling) -- both score 1:**
Both models confidently (mini: 0.95, nano: 0.92) process a query about a modern author (b. 1965) as a normal retrieval against a rare books collection. Neither provides a clarification or lowers confidence to reflect the scope mismatch. The fix is to add collection-scope instructions to the interpreter prompt: "This collection contains rare books primarily from the 15th-19th centuries. If a query references modern authors, technologies, or topics clearly outside this scope, set confidence below 0.5 and provide a clarification explaining the collection's boundaries."

### 4.3 Mini-Specific Remaining Weaknesses

Mini has only 2 queries scoring below 2, both shared with nano (q_is08, q_oos02). It has **no unique failures** -- every query where mini scores low, nano also scores low. This is a positive signal: mini does not introduce new failure modes.

The minor issues in mini's score-2 queries are:
- **q_is03:** Date boundary (1501 vs 1500) -- debatable convention, same as nano
- **q_oos01:** Confidence 0.90 for an OOS query -- should be lower, but filters are correct
- **q_amb03:** Retrieval intent instead of overview -- same as nano

### 4.4 Attribution Summary

| Failure Category | Queries Affected | Nano | Mini | Root Cause | Fix |
|-----------------|-----------------|------|------|------------|-----|
| Incomplete plans | q_is04, q_is05 | Fails (1) | **Passes (3)** | Nano model capacity | Use mini or gpt-4.1 |
| Domain semantics | q_is08 | Fails (1) | Fails (1) | Missing prompt context | Add subject-mapping guidance to prompt |
| Scope detection | q_oos01, q_oos02 | Partial (1-2) | Partial (1-2) | Missing prompt instructions | Add OOS detection rules to prompt |
| Semantic action confusion | q_is07 | Partial (2) | **Passes (3)** | Nano model capacity | Use mini or gpt-4.1 |

---

## 5. Recommendations

### 5.1 Primary Recommendation

**Adopt gpt-4.1-mini as the default interpreter model, replacing the current default, after addressing prompt-level issues.**

The decision matrix:

| Criterion | Weight | Nano | Mini | GPT-4.1 | Notes |
|-----------|--------|------|------|---------|-------|
| In-scope accuracy | High | 2.00 | **2.62** | ~2.7 (est.) | Mini closes 80% of the gap to gpt-4.1 |
| OOS handling | Medium | 1.50 | 1.50 | ~1.50 (est.) | All models likely fail equally -- prompt issue |
| Ambiguity handling | Medium | 2.67 | 2.67 | ~2.67 (est.) | All models handle well at current level |
| Cost | Low | $0.0005 | **$0.0019** | $0.0094 | Mini is 5x cheaper than gpt-4.1 |
| Latency | Low | 2.73s | 3.96s | ~4-6s (est.) | Mini comparable to gpt-4.1 |
| Plan completeness | High | 69% | **85%** | ~92% (est.) | Mini dramatically better than nano |

**Why mini over nano:** The +0.62 in-scope score improvement (2.00 -> 2.62) reflects real structural improvements in plan generation. Nano's incomplete plans (missing filters, missing retrieve steps) would produce wrong results in production -- the kind of silent errors that erode user trust. Mini eliminates these failures at a cost that is still negligible in the overall pipeline.

**Why mini over gpt-4.1:** The estimated ~0.1 point gap between mini and gpt-4.1 on in-scope queries does not justify the 5x cost premium. Mini's only remaining in-scope failure (incunabula, q_is08) is a prompt issue that would likely affect gpt-4.1 equally. The OOS failures are also prompt-level. After prompt fixes, mini's effective score is likely to approach gpt-4.1's.

### 5.2 Action Plan

| Priority | Action | Expected Impact |
|----------|--------|----------------|
| **P0** | Fix prompt: add OOS detection instructions | Fix q_oos01 (+1), q_oos02 (+2) for all models |
| **P0** | Fix prompt: add subject-mapping guidance for domain terms (incunabula, etc.) | Fix q_is08 (+2) for all models |
| **P1** | Re-run 13-query eval on mini with fixed prompt | Validate that mini reaches ~2.85+ avg score |
| **P1** | Run 13-query eval on gpt-4.1 (current prompt) | Establish true baseline; confirm shared failures |
| **P2** | Switch default interpreter from gpt-4.1 to gpt-4.1-mini | Deploy after P0+P1 validation |
| **P3** | Expand benchmark to 30+ queries | Increase statistical confidence |
| **P4** | Evaluate tiered routing (simple -> nano, complex -> mini) | Further cost optimization |

### 5.3 Projected Scores After Prompt Fixes

If the two prompt-level fixes (OOS detection + subject mapping) raise the affected queries by the expected amounts:

| Query | Current Mini | Projected Mini | Change |
|-------|-------------|---------------|--------|
| q_is08 | 1 | 3 | +2 (subject filter instead of date) |
| q_oos01 | 2 | 3 | +1 (explicit OOS recognition) |
| q_oos02 | 1 | 3 | +2 (explicit OOS recognition) |
| Others | 27 | 27 | 0 |
| **Total** | **32/39 (82%)** | **37/39 (95%)** | **+5** |
| **Average** | **2.46** | **2.85** | **+0.39** |

A projected 2.85/3.0 average with 95% success rate would be production-ready.

### 5.4 Guardrails for Production Deployment

Even with prompt fixes, the following guardrails should be in place:

1. **Plan validation layer:** After the interpreter returns a plan, validate structural completeness:
   - Every `resolve_agent`/`resolve_publisher` step must have a subsequent `retrieve` step referencing `$step_N`
   - Queries containing role indicators ("illustrated by", "printed by", "written by") must include `agent_role` filters
   - Plans must have at minimum the expected step count for the detected intent type

2. **Confidence-gated fallback:** If mini returns confidence < 0.70, automatically escalate to gpt-4.1.

3. **Continuous monitoring:** Track per-query scores against the benchmark set. If the rolling average drops below 2.5, alert for investigation.

---

## Appendix A: Raw Score Distribution

### Mini
```
Score 3 (Perfect):  8 queries  (62%)  -- q_is01, q_is02, q_is04, q_is05, q_is06, q_is07, q_amb01, q_amb02
Score 2 (Good):     3 queries  (23%)  -- q_is03, q_oos01, q_amb03
Score 1 (Partial):  2 queries  (15%)  -- q_is08, q_oos02
Score 0 (Broken):   0 queries  (0%)

Total: 32 / 39 points (82%)
```

### Nano (for comparison)
```
Score 3 (Perfect):  5 queries  (38%)  -- q_is01, q_is02, q_is06, q_amb01, q_amb02
Score 2 (Good):     4 queries  (31%)  -- q_is03, q_is07, q_oos01, q_amb03
Score 1 (Partial):  4 queries  (31%)  -- q_is04, q_is05, q_is08, q_oos02
Score 0 (Broken):   0 queries  (0%)

Total: 27 / 39 points (69%)
```

## Appendix B: Latency Distribution

| ID | Query | Mini Latency | Nano Latency | Delta |
|----|-------|-------------|-------------|-------|
| q_is01 | Insel Verlag | 3.02s | 2.66s | +0.36s |
| q_is02 | Basel | 2.74s | 1.75s | +0.99s |
| q_is03 | Latin 16th century | 2.88s | 1.64s | +1.24s |
| q_is04 | Schwerin illustrator | 4.14s | 4.28s | -0.14s |
| q_is05 | Josephus Flavius | 5.04s | 2.80s | +2.24s |
| q_is06 | Cities aggregation | 2.95s | 6.70s | -3.75s |
| q_is07 | Hebrew Amsterdam | 4.49s | 2.34s | +2.15s |
| q_is08 | Incunabula | 3.73s | 1.36s | +2.37s |
| q_oos01 | Machine learning | 4.32s | 2.48s | +1.84s |
| q_oos02 | J.K. Rowling | 3.71s | 2.22s | +1.49s |
| q_amb01 | Really old books | 5.03s | 2.84s | +2.19s |
| q_amb02 | Moses | 5.87s | 2.31s | +3.56s |
| q_amb03 | Venice books | 3.50s | 2.13s | +1.37s |
| | **Average** | **3.96s** | **2.73s** | **+1.23s** |

## Appendix C: GPT-4.1 Aldine Press Baseline Reference

From `docs/testing/models_comparisons/4_tests_03042026.txt`, the Aldine Press query was tested across multiple configurations:

| Configuration | Time | Cost | Quality |
|---------------|------|------|---------|
| gpt-4.1 (interpreter + narrator) | 16.5s | N/A | Complete, accurate, 7 records |
| gpt-4.1-nano interpreter + gpt-4.1 narrator | 25.5s | $0.0143 | Complete, correct, 7 records |
| gpt-5-mini interpreter + gpt-4.1 narrator | 49.1s | $0.0219 | Very detailed, correct |
| gpt-5-mini (interpreter + narrator) | 62.8s | N/A | Very detailed, correct |

All configurations correctly identified the same 7 Aldine Press records, confirming that even the lowest-tier model (nano) produces correct CandidateSets for straightforward publisher queries.

---

*Report generated 2026-04-03. Data sources: `data/eval/interpreter_nano_queries.json`, `data/eval/interpreter_mini_results.json`, `data/eval/interpreter_mini_verification.json`, `data/eval/interpreter_nano_results.json`, `data/eval/interpreter_nano_verification.json`, `docs/testing/models_comparisons/4_tests_03042026.txt`, `docs/testing/models_comparisons/interpreter_nano_eval_report.md`.*
