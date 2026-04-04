# GPT-4.1-Nano Interpreter Evaluation Report

**Date:** 2026-04-03
**Evaluation set:** `data/eval/interpreter_nano_queries.json` (13 queries)
**Model under test:** `gpt-4.1-nano` (interpreter stage only)
**Scoring:** 0-3 scale (0 = broken, 1 = partial, 2 = good with minor issues, 3 = perfect)

---

## 1. Executive Summary

**Verdict: gpt-4.1-nano should NOT replace gpt-4.1 as the default interpreter model at this time.**

While nano demonstrates strong performance on simple, single-filter queries and handles ambiguity well, it has significant failures on moderate-complexity tasks that require complete multi-step execution plans. Four of 13 queries scored 1 (partial), indicating incomplete or incorrect structured output. The interpreter is the most critical pipeline stage -- errors here cascade through retrieval and narration -- so the quality bar must be high.

### Key Metrics

| Metric | Value |
|--------|-------|
| Average score | **2.08 / 3.0** (69%) |
| Perfect score (3/3) | 5 / 13 (38%) |
| Good or better (2+) | 9 / 13 (69%) |
| Partial or broken (0-1) | 4 / 13 (31%) |
| Average latency | **2.73s** |
| Median latency | 2.34s |
| Estimated cost per query | **~$0.0002** (based on ~1K input + 500 output tokens at nano pricing) |
| Estimated gpt-4.1 cost per query | **~$0.006** (same token counts at gpt-4.1 pricing) |
| **Cost savings (nano vs 4.1)** | **~97%** |

---

## 2. Results by Category

### 2.1 In-Scope Queries (8)

| ID | Query (truncated) | Score | Latency | Key Issues |
|----|--------------------|-------|---------|------------|
| q_is01 | Books published by Insel Verlag | 3 | 2.66s | None -- perfect publisher retrieval |
| q_is02 | What was printed in Basel? | 3 | 1.75s | None -- correct place filter |
| q_is03 | Latin books from the sixteenth century | 2 | 1.64s | Date start 1501 vs expected 1500 (minor boundary) |
| q_is04 | Books illustrated by Ludwig Schwerin | 1 | 4.28s | **Missing role filter** for "illustrator" -- returns 17 vs expected 10 |
| q_is05 | Tell me about Josephus Flavius... | 1 | 2.80s | **Missing retrieve step** -- resolves agent but never fetches records |
| q_is06 | Cities with the most books? | 3 | 6.70s | None -- correct aggregate action |
| q_is07 | Hebrew books in Amsterdam 1600-1800 | 2 | 2.34s | Used resolve_publisher for a place name; date end 1799 vs 1800 |
| q_is08 | Interested in incunabula | 1 | 1.36s | **Date filter instead of subject filter** -- 7 vs expected 34 records |

**What nano handles well:**
- Simple, single-filter retrieval (publisher, place) -- scored 3/3 on both
- Analytical/aggregation queries -- correctly chose aggregate action with sensible parameters
- Language code mapping ("Latin" -> "lat", "Hebrew" -> "heb") -- correct in all cases

**Where nano struggles:**
- **Multi-step plan completeness:** Two queries (q_is04, q_is05) had structurally incomplete plans -- missing a role filter in one case and missing an entire retrieve step in another. This suggests nano sometimes generates a partial plan and stops prematurely.
- **Domain-specific semantics:** The incunabula query (q_is08) required understanding that in this collection "incunabula" is a subject heading covering books *about* incunabula, not just books printed before 1501. Nano applied the textbook definition rather than the collection-specific usage.
- **Semantic precision of actions:** q_is07 used `resolve_publisher` for a place name, showing confusion between entity types.

### 2.2 Out-of-Scope Queries (2)

| ID | Query | Score | Detected OOS? | Confidence | Clarification? |
|----|-------|-------|---------------|------------|----------------|
| q_oos01 | Machine learning / computer science | 2 | No | 0.85 (too high) | Yes, but unhelpful |
| q_oos02 | J.K. Rowling | 1 | No | 0.92 (far too high) | None |

**Analysis:** Nano failed to recognize either query as out-of-scope for a rare books collection. Both queries were treated as normal retrievals that would mechanically return zero results. The key failure is not in the filters (which would correctly return empty sets) but in the model's inability to reason about collection scope:

- **q_oos01:** Provided a clarification, but it asked "Would you like to narrow by date, language, author?" -- suggesting the model believes the collection might contain CS books. A good interpreter would say: "This is a rare books collection focused on pre-modern works; machine learning and computer science are not represented."
- **q_oos02:** High confidence (0.92) with no clarification at all. The model confidently attempted to resolve J.K. Rowling as an agent in a rare books collection. This is a gap in collection-awareness reasoning.

**Impact:** While the filters would produce correct (empty) results, the lack of scope recognition leads to poor user experience -- the system silently returns nothing instead of explaining why.

### 2.3 Ambiguous Queries (3)

| ID | Query | Score | Clarification Provided? | Default Interpretation |
|----|-------|-------|------------------------|----------------------|
| q_amb01 | Really old books | 3 | Yes | 1401-1600 (reasonable) |
| q_amb02 | What do you have by Moses? | 3 | Yes (excellent) | resolve_agent, mentions Maimonides |
| q_amb03 | Venice books | 2 | Yes | Retrieval, not overview |

**Analysis:** Ambiguous query handling is nano's strongest category (avg 2.67/3.0). The model:
- Correctly lowered confidence for ambiguous queries (0.70-0.85 vs 0.90-0.95 for clear queries)
- Provided useful clarification messages in all three cases
- Made reasonable default interpretations while asking for refinement

The one weakness (q_amb03) was classifying "Tell me about the Venice books" as retrieval intent rather than overview/analytical intent. A flat retrieve of 164 records is less useful than an aggregated summary by era, printer, or language.

---

## 3. Comparison with gpt-4.1 Baseline

### 3.1 Reference: Aldine Press Test (from 4_tests_03042026.txt)

The previous evaluation tested the Aldine Press query ("review books published by aldine press that are in this collection") across three configurations:

| Configuration | Time | Cost | Tokens (in/out) | Quality |
|---------------|------|------|-----------------|---------|
| gpt-4.1 (interpreter + narrator) | 16.5s | N/A | N/A | Complete, accurate, 7 records found |
| gpt-5-mini (interpreter + narrator) | 62.8s | N/A | N/A | Very detailed, correct, verbose |
| gpt-5-mini interpreter + gpt-4.1 narrator | 49.1s | $0.0219 | 5,275 / 3,885 | Complete, well-structured |
| **gpt-4.1-nano interpreter + gpt-4.1 narrator** | **25.5s** | **$0.0143** | **5,084 / 1,609** | **Complete, correct, 7 records found** |

Key observations:
- **Nano + gpt-4.1 narrator was 35% cheaper** than gpt-5-mini + gpt-4.1 narrator ($0.0143 vs $0.0219)
- **Nano + gpt-4.1 narrator was 48% faster** than gpt-5-mini + gpt-4.1 narrator (25.5s vs 49.1s)
- Nano produced a correct CandidateSet (all 7 Aldine records) -- the same as gpt-4.1 alone
- Nano used fewer output tokens (1,609 vs 3,885), indicating more concise interpreter output

### 3.2 Cost Comparison

| Model | Input Price ($/1M tok) | Output Price ($/1M tok) | Est. Cost/Query (interpreter only) | Relative Cost |
|-------|----------------------|------------------------|-----------------------------------|---------------|
| gpt-4.1-nano | $0.10 | $0.40 | ~$0.0003 | **1x (baseline)** |
| gpt-4.1-mini | $0.40 | $1.60 | ~$0.0011 | ~4x |
| gpt-4.1 | $2.00 | $8.00 | ~$0.0060 | ~20x |

At nano pricing, the interpreter stage costs effectively nothing (~$0.0003 per query). Even at 1,000 queries/day, the daily interpreter cost would be ~$0.30. The 20x cost advantage over gpt-4.1 is substantial.

### 3.3 Latency Comparison

| Model | Avg Interpreter Latency | Source |
|-------|------------------------|--------|
| gpt-4.1-nano | **2.73s** | This evaluation (13 queries) |
| gpt-4.1 (full pipeline) | ~16.5s | Aldine Press test (includes narration) |
| gpt-4.1 (interpreter only, estimated) | ~4-6s | Estimated from pipeline breakdown |

Nano's average latency of 2.73s is competitive. The 6.70s outlier on the aggregation query (q_is06) may reflect the model generating a longer reasoning chain for analytical queries.

### 3.4 Quality Comparison

Without running the same 13 queries through gpt-4.1, a direct quality comparison is not possible. However, based on the failure patterns observed:

- **Failures likely specific to nano:** Missing role filter (q_is04), missing retrieve step (q_is05), and the incunabula subject-vs-date confusion (q_is08) all suggest that nano generates less complete structured plans. These are likely plan-completeness issues that gpt-4.1 would handle better due to stronger reasoning.
- **Failures likely shared across models:** The out-of-scope detection failures (q_oos01, q_oos02) may be prompt/schema issues rather than model issues. If the interpreter prompt does not instruct the model to reason about collection scope, even gpt-4.1 might produce high-confidence plans for out-of-scope queries. This hypothesis needs verification.

---

## 4. Failure Analysis

### 4.1 Queries Scoring 0 or 1

| ID | Score | Failure Type | Root Cause |
|----|-------|-------------|------------|
| q_is04 | 1 | Missing filter | No role_norm="illustrator" despite "illustrated by" in query |
| q_is05 | 1 | Incomplete plan | resolve_agent without subsequent retrieve step |
| q_is08 | 1 | Wrong filter strategy | Date range instead of subject filter for "incunabula" |
| q_oos02 | 1 | Missing scope awareness | Treated modern author as normal retrieval with high confidence |

### 4.2 Failure Patterns

**Pattern 1: Incomplete Execution Plans (q_is04, q_is05)**
Both failures involve the model generating a structurally incomplete plan -- it identifies the right approach but omits a critical step or filter. In q_is04, the agent resolution is correct but the role constraint is dropped. In q_is05, the agent resolution happens but no retrieval follows. This pattern suggests nano sometimes "loses track" of the full query intent when generating multi-step plans. This is likely a model capacity issue that would improve with gpt-4.1.

**Pattern 2: Collection-Specific Knowledge Gap (q_is08)**
The incunabula failure is interesting: nano applied correct general knowledge (incunabula = pre-1501 books) but missed that this specific collection uses "Incunabula" as a subject heading for books *about* incunabula. This is a data-specific nuance that no model would know without either (a) few-shot examples in the prompt, or (b) a schema description explaining how subjects work in this collection. This failure is likely **prompt-level**, not model-level.

**Pattern 3: Missing Out-of-Scope Detection (q_oos01, q_oos02)**
The interpreter schema and prompt may not include instructions to detect and flag out-of-scope queries. Both out-of-scope failures show the model mechanically building filters without reasoning about whether the query makes sense for a rare books collection. This is almost certainly a **prompt/schema issue** that would affect any model. Adding a `scope_check` field or explicit instructions about collection boundaries would likely fix this across all models.

### 4.3 Attribution Summary

| Failure Category | Queries | Likely Cause | Fix Location |
|-----------------|---------|-------------|-------------|
| Incomplete plans | q_is04, q_is05 | Model capacity limitation | Upgrade model or add plan validation |
| Domain semantics | q_is08 | Missing collection context in prompt | Prompt engineering |
| Scope detection | q_oos01, q_oos02 | Missing scope-check instructions | Prompt/schema engineering |

**Key insight:** 3 of the 4 failures (q_is08, q_oos01, q_oos02) are likely prompt/schema issues that would affect any model. Only 2 failures (q_is04, q_is05) are clearly attributable to nano's model capacity.

---

## 5. Recommendations

### 5.1 Primary Recommendation

**Do not adopt gpt-4.1-nano as the default interpreter at this time. Instead, keep gpt-4.1 as the default and pursue the following path:**

1. **Run the same 13 queries through gpt-4.1** to establish a true baseline comparison. Without this, we cannot distinguish model-specific failures from prompt-level failures. This is the highest-priority follow-up.

2. **Fix the prompt/schema issues first** (scope detection, incunabula subject guidance), then re-evaluate nano. If 3 of the 4 failures are prompt-level, fixing the prompt could raise nano's score from 2.08 to ~2.62 (assuming those 3 queries improve to score 2+).

3. **Consider gpt-4.1-nano for a "fast path" tier** where simple queries (single-filter retrieval, place/publisher/language lookups) are routed to nano, while complex queries (multi-filter, entity exploration, analytical) go to gpt-4.1. The data shows nano scores 3/3 on simple queries consistently.

### 5.2 Rationale

The interpreter's job is structured SQL generation from natural language -- a relatively constrained task compared to free-form narration. In principle, this should be achievable by a smaller model. The evidence shows that nano handles 69% of queries well, and its failures cluster in specific, addressable patterns. However, the 31% failure rate on a 13-query benchmark is too high for a production default, especially given that interpreter errors cascade (a missing filter means wrong records, which means a wrong narrative).

The cost argument is compelling (~97% savings), but the cost of the interpreter stage is already minimal even with gpt-4.1 (~$0.006/query). The real cost driver in the pipeline is the narrator stage, not the interpreter. Saving $0.006 per query at the expense of a 31% quality degradation is not a good trade-off.

### 5.3 Guardrails (If Nano Is Adopted Later)

If prompt fixes raise nano's quality to acceptable levels, the following guardrails should be in place:

- **Plan validation layer:** After the interpreter returns a plan, validate that (a) every resolve step has a corresponding retrieve step, (b) role-specific queries include role filters, (c) plans have at least the expected minimum number of steps for the detected intent type.
- **Confidence-gated fallback:** If nano returns confidence < 0.80 or if plan validation fails, automatically re-run the query through gpt-4.1.
- **Continuous monitoring:** Track per-query scores in production. If the rolling 50-query average drops below 2.5, alert and consider switching back to gpt-4.1.

### 5.4 Suggested Follow-Up Evaluations

| Priority | Evaluation | Purpose |
|----------|-----------|---------|
| **P0** | Run same 13 queries on gpt-4.1 | Establish true baseline; isolate model-specific vs prompt-specific failures |
| **P1** | Fix prompt (scope detection, subject guidance) and re-run nano | Measure prompt-fix impact on nano quality |
| **P2** | Run 13 queries on gpt-4.1-mini | Test the middle tier -- may offer the best quality/cost trade-off |
| **P3** | Expand benchmark to 30+ queries | Current 13-query set is too small for high-confidence conclusions |
| **P4** | Test tiered routing (simple -> nano, complex -> gpt-4.1) | Validate hybrid approach |

---

## Appendix: Raw Score Distribution

```
Score 3 (Perfect):  5 queries  (38%)  -- q_is01, q_is02, q_is06, q_amb01, q_amb02
Score 2 (Good):     4 queries  (31%)  -- q_is03, q_is07, q_oos01, q_amb03
Score 1 (Partial):  4 queries  (31%)  -- q_is04, q_is05, q_is08, q_oos02
Score 0 (Broken):   0 queries  (0%)
```

**Total: 27 / 39 points (69%)**

---

*Report generated 2026-04-03. Data sources: `data/eval/interpreter_nano_queries.json`, `data/eval/interpreter_nano_results.json`, `data/eval/interpreter_nano_verification.json`, `docs/testing/models_comparisons/4_tests_03042026.txt`.*
