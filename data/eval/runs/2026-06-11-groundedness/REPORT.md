# Narrator Groundedness Probe (Committee Eval E3) — 2026-06-11

14 queries × 2 narrator models (gpt-4.1, gpt-4.1-mini) × 3 judge configurations
+ deterministic hallucination check. ~135 LLM calls, ≈$0.7.

## Findings

1. **Zero hallucinated record IDs in 30 narratives.** Every record ID cited in
   every narrative exists in that response's grounding. The evidence contract
   holds at the narrative level. (ID-based check; titles paraphrase too freely
   for exact matching.)

2. **The current narrator judge is broken-by-starvation — CONFIRMED.** With
   today's thin 10-line grounding summary the gpt-4.1 judge's mean accuracy
   score is **3.21**; given full grounding (counts, IDs, publishers, subjects,
   agents) the same judge scores the same narratives **4.43**. 22 of 28
   narrative-scores moved ≥1 point, almost always upward: the thin judge
   penalizes claims it simply cannot see the evidence for. Current narrator-stage
   eval scores measure *summary starvation*, not narrative quality.
   → Fix: pass full grounding to the judge in evaluate_narrator (committee A8-adjacent).

3. **No meaningful self/size-preference detected.** gpt-4.1 narratives score
   higher than mini's under BOTH judges (4.1 judge: 4.62 vs 4.27; mini judge:
   4.93 vs 4.71), and the deterministic check agrees (title coverage 0.28 vs
   0.21, hallucinations 0 vs 0) — the gap tracks real quality, not judge bias.
   Caveat: both judges are OpenAI models; a cross-provider judge was unavailable
   (no Anthropic key in this environment).

4. gpt-4.1-mini as narrator is only modestly weaker and 4× cheaper — worth a
   future cost-quality decision once the judge inputs are fixed.

## Action items fed back into the committee roadmap
- Sprint 2: evaluate_narrator must build the judge's grounding summary from
  full grounding (records+IDs+counts+agents), not 10 title lines.
- Keep the deterministic hallucination check as a permanent free eval stage.
