# Narrator Gold-Standard Evaluation — Design Spec

**Date:** 2026-06-14
**Status:** Approved (brainstorming) — pending spec review → implementation plan
**Author:** Claude Code (Opus 4.8) + Hagay Bar
**Topic area:** `data/eval` / QA Framework (`docs/current/qa-framework.md`)

---

## 1. Motivation

A single chat turn costs ~1.6–3¢. Per `logs/llm_calls.jsonl`, the **narrator** stage
(`gpt-4.1`, ~800–1,900 output tokens) is the dominant cost line (~$0.011–0.024/turn),
several times the interpreter. Prior model evals (2026-04, `docs/testing/models_comparisons/`)
only ever varied the *interpreter* model and the narrator's *prompt mode* (lean vs full) —
**no eval has ever tested the narrator on a cheaper model.** That is the untested frontier
for cost reduction, and the one most likely to move the bill.

This spec defines a focused, repeatable evaluation that measures candidate narrator models
against a gold standard authored by Opus 4.8 (Claude Code, in-session), so we can choose a
cost/quality point with evidence rather than guesswork.

## 2. Goal & Success Criteria

**Goal:** Determine which narrator model gives the best quality-per-dollar, measured against
a fixed gold standard, on a representative set of grounded queries.

**Success criteria:**
- A ranked report: per-model composite quality score (per rubric dimension) alongside measured
  $/query, over a shared set of ~11 gold cases.
- The comparison isolates **only** the narration step — all models judged on identical, frozen
  grounding data and against the same gold.
- The whole paid run costs **≤ $1.00** (estimated ~$0.56), guarded by a hard ceiling.

## 3. Non-Goals

- Not re-evaluating the interpreter (separate, already-studied stage).
- Not testing premium models more expensive than current `gpt-4.1` (no cost-reduction value).
- Not testing the `full` (non-token-saving) narrator prompt mode — we evaluate the production
  default (`token_saving=True`, lean) only.
- Not changing production model config in this work; that is a follow-up decision informed by
  the report.

## 4. Approach Overview

```
Phase A (in-session, $0): author gold set
  for each query:
    interpret → execute → enrich  (REAL pipeline against bibliographic.db)
    freeze ExecutionResult → grounding.json
    Opus 4.8 writes gold narrative → gold.md   (applying narrator's 7 evidence rules)

  → USER REVIEWS & APPROVES the gold set (gate)

Phase B (paid, batch, ~$0.56): run + score candidates
  build narration batch (44 reqs: 11 cases × 4 models, frozen grounding, lean prompt)
    → submit → poll → download
  build judge batch (44 reqs: gpt-5.4, reference-anchored rubric, bounded grounding)
    → submit → poll → download
  parse → ranked report (quality × cost) → data/eval/runs/<date>-narrator-gold/
```

The fairness anchor: candidates receive the **frozen** `ExecutionResult` used to write the gold,
via `narrate()` directly — the interpret+execute steps are **not** re-run per candidate (which
is what the existing `run_eval.py` does, and why we add a new script instead of reusing it).

## 5. Components

### 5.1 Gold standard generation (in-session, $0)
Opus 4.8 (this Claude Code session) authors each gold narrative — no API key, no cost. For each
case it runs the real interpreter, executor, and enrichment steps against `bibliographic.db`,
captures the resulting `ExecutionResult`, and writes the gold prose from that exact grounding,
following the narrator's own 7 evidence rules (`scripts/chat/narrator.py:NARRATOR_SYSTEM_PROMPT`).

### 5.2 Query set & coverage (~11 DB-grounded cases)
Chosen to exercise the narrator's full range; each grounded in real DB content:

| # | Case type | Why it tests the narrator |
|---|-----------|---------------------------|
| 1 | Publisher retrieval (small set) | Clean record listing + counts |
| 2 | Place retrieval (medium set) | Place evidence, grouping |
| 3 | Agent + role | Role-specific framing |
| 4 | Multi-filter (Hebrew, place, date range) | Multiple constraints, Hebrew content |
| 5 | Semantic subject concept (#63) | Surfacing matched headings as evidence |
| 6 | Aggregation / analytical | Stats-style narration (not record listing) |
| 7 | Entity exploration (resolve+retrieve+enrich) | Weaving bio + Wikipedia/Wikidata links |
| 8 | Large result set (100+ records) | Summarizing at scale without fabrication |
| 9 | Empty / zero-result in-scope | Evidence rule 4: say so clearly, no fabrication |
| 10 | Hebrew-language query | Multilingual / BiDi narration |
| 11 | Ambiguous query | Clarification framing, hedged confidence |

Balance: mix of small (3–10) and large (100+) candidate sets; Hebrew + Latin/English content.

### 5.3 Frozen grounding fixtures
Stored under `data/eval/narrator_gold/`:
```
manifest.json                 # [{case_id, query, intent_type, language, set_size_bucket, notes}]
<case_id>/
  query.txt                   # the query string
  grounding.json              # serialized frozen ExecutionResult (narrate() input)
  gold.md                     # Opus-authored gold narrative
```
`grounding.json` is a faithful JSON round-trip of the `ExecutionResult` (and nested
`GroundingData`, `RecordSummary`, `AgentSummary`, `GroundingLink`, `StepResult`) so `narrate()`
receives an object identical to what Opus saw.

### 5.4 Candidate narration (batched)
Candidates (all judged against the gold): **`gpt-4.1` (baseline), `gpt-5.4-mini`, `gpt-5-mini`,
`gpt-4.1-mini`** — a cost-cutting ladder spanning 1.8×–5× cheaper output than the baseline.
Each candidate narration uses the **production lean prompt** (`token_saving=True`) built from the
frozen grounding. The harness reuses the narrator's own prompt-builder so batch requests are
byte-identical to production prompts (a small refactor to expose the builder may be required).

### 5.5 Reference-anchored rubric & judge
Judge scores each candidate narrative on weighted dimensions (0–3 each, per the project's
existing eval convention), with the gold as the "complete & excellent" yardstick:

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Grounding / no fabrication | 40% | Every specific claim (count, title, date, printer, place, link) appears in the frozen grounding; no invented records or figures |
| Coverage | 20% | Covers the holdings / key facts the gold covers (records, matched headings, agents, counts) |
| Evidence fidelity | 15% | Exact counts correct; links correct format; titles transcribed faithfully |
| Scholarly quality & coherence | 15% | Clarity, structure, scholarly framing; general knowledge clearly labeled as such |
| Scope handling | 10% | Empty-set honesty (rule 4); clarification when ambiguous; no overreach |

**Fabrication override:** if the judge detects any fabricated specific claim, the case is flagged
and the composite is hard-capped (fabrication is a project non-negotiable, regardless of prose).
Candidates are **not** penalized for valid-but-different prose — only for missing/wrong substance.

**Judge model: `gpt-5.4`.** Chosen because it is neither the gold author (Opus — author ≠ judge)
nor a candidate (`gpt-4.1` is in the slate — avoid self-preference), and is the strongest OpenAI
model available. Judge calls are short and run via batch.

### 5.6 Cost controls
- **Batch everything** (narration + judging) via OpenAI Batch API — 50% off, async (≤24h, usually
  minutes–hours). Two sequential batch jobs: narration must complete before judge prompts can be built.
- **Bounded grounding for the judge:** the judge receives a compact canonical summary (record rows
  capped at ~40 + exact counts + cited links), not the full `ExecutionResult` — keeps every judge
  prompt ~3–5K tokens, even for the 100-record case.
- **Reasoning-token containment (critical):** `gpt-5.4`, `gpt-5.4-mini`, and `gpt-5-mini` are
  reasoning models — hidden reasoning tokens bill as *output* tokens (at full output rate). Because
  reasoning happens server-side after submission, a pre-submit estimate cannot observe it, so we
  bound it deterministically:
  - **`max_completion_tokens` cap per request** (covers reasoning + visible output) — narration
    capped at ~2,000, judge at ~1,200. This makes each call's billable output a known upper bound.
  - **`reasoning_effort: low`** on the judge (rubric-against-gold needs no deep reasoning), and
    likewise minimal/low for reasoning-capable narration candidates unless quality testing shows
    they need more.
  - The cost-ceiling guard estimates output cost at the **capped `max_completion_tokens`** (worst
    case), not at optimistic visible-token counts — so its projection is a genuine upper bound.
- **Cost-ceiling guard:** before submitting each batch, the harness estimates spend using full input
  token counts and the **capped** output budget, and **aborts** if projected total exceeds
  **$2.00** (configurable; raised from $1.00 to absorb the reasoning-token unknown). A run can never
  silently overrun the budget.

### 5.7 Report / output
Written to `data/eval/runs/<date>-narrator-gold/`:
- `results.json` — per (case × model): candidate text, per-dimension scores, fabrication flags,
  measured input/output tokens, measured cost.
- `REPORT.md` — ranked table: composite quality + per-dimension means × model, alongside measured
  $/query and projected savings vs `gpt-4.1` baseline; plus per-case drill-down and flagged failures.

## 6. Harness Design

New script: **`scripts/eval/run_narrator_gold_eval.py`** (leaves `run_eval.py` untouched).

Reused / refactored seams:
- Narrator prompt builder (`scripts/chat/narrator.py`) — expose the lean prompt-building function so
  it can be called without making an LLM call (needed to emit batch requests).
- Judge logic (`scripts/eval/judge.py`) — extract the reference-anchored rubric prompt builder and
  result parser so judging can be batched; add a new `score_narrator_vs_gold` path.
- Cost helpers (`scripts/utils/llm_logger.py` pricing via `litellm`) — reuse for the ceiling guard.

New modules (likely):
- `scripts/eval/batch_client.py` — thin wrapper over the OpenAI Batch endpoint: build JSONL by
  `custom_id`, submit, poll, download, reconcile. Uses `scripts/api_clients/openai/`.
- `scripts/eval/narrator_gold.py` — fixture load/save, grounding (de)serialization, bounded summary.

CLI sketch:
```
python -m scripts.eval.run_narrator_gold_eval \
  --gold-dir data/eval/narrator_gold \
  --models gpt-4.1,gpt-5.4-mini,gpt-5-mini,gpt-4.1-mini \
  --judge-model gpt-5.4 --judge-reasoning-effort low \
  --batch --cost-ceiling 2.00 \
  --max-narration-tokens 2000 --max-judge-tokens 1200 \
  --output-dir data/eval/runs/2026-06-14-narrator-gold
```

## 7. Data Formats

- **Fixture:** see §5.3.
- **Batch request line:** `{"custom_id": "<case_id>::<model>", "method": "POST",
  "url": "/v1/chat/completions", "body": {"model": "...", "messages": [...], ...}}`.
  `custom_id` encodes case + model (+ `::judge` for judge requests) for reconciliation.
- **Judge output:** structured JSON — per-dimension 0–3 scores, fabrication flag + offending claims,
  one-line rationale per dimension.

## 8. Cost Estimate

11 cases × 4 candidates = 44 narrations + 44 judgments, all batched (−50%), judge = `gpt-5.4`.
Two scenarios, because reasoning models bill hidden reasoning as output:

- **Optimistic** (visible output only): narration ~1K out, judge ~0.6K out.
- **Worst case** (output at the `max_completion_tokens` caps): narration 2K out, judge 1.2K out.
  This is the bound the ceiling guard enforces.

| Item (batch, −50%) | Optimistic | Worst case (capped) |
|--------------------|-----------|---------------------|
| Narration (4 models, 11 cases) | ~$0.14 | ~$0.18 |
| Judge (`gpt-5.4`, 44 calls) | ~$0.42 | ~$0.62 |
| **Total** | **~$0.56** | **~$0.80** |

Gold authoring: **$0** (in-session). Ceiling guard aborts any run projected above **$2.00** — so
even if reasoning tokens run hot beyond the caps' assumptions, the run is hard-stopped well within
budget, leaving ~$3 of the $5.

## 9. Workflow & Gates

1. **Phase A** — Opus authors the gold set ($0).
2. **GATE: user reviews & approves the gold set** before any paid call (a bad gold poisons everything).
3. **GATE: explicit user go-ahead** before submitting paid batches (per user cost-approval policy).
4. **Phase B** — batch narration → batch judging → report.
5. Report informs a *separate* decision on whether to change production narrator config.

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Gold quality bias (Opus prose style) | Rubric scores substance, not style; user approves gold; grounding/no-fabrication weighted highest |
| Judge self-preference | Judge (`gpt-5.4`) is not a candidate and not the gold author |
| Grounding serialization drift | Faithful JSON round-trip of `ExecutionResult`; spot-check that re-loaded grounding renders identically |
| Large-set judge prompt bloat | Bounded canonical grounding summary (~40 rows + counts) |
| New model strings / batch eligibility unknown | Verify exact litellm/OpenAI model IDs + batch support via a free `models.list()` at implementation start; fall back (e.g. `gpt-5.2`/`gpt-5.1`) if a string is invalid |
| Hidden reasoning tokens (gpt-5.x) inflate output cost | `max_completion_tokens` caps + `reasoning_effort: low` on judge; ceiling guard estimates at the capped output (true upper bound), not optimistic visible counts |
| Budget overrun | Hard cost-ceiling guard ($2.00) aborts before submit |
| Batch job failure / partial completion | Reconcile by `custom_id`; surface missing results explicitly, never silently drop a case |

## 11. Open Implementation Questions

- Exact litellm model strings for `gpt-5.4`, `gpt-5.4-mini`, `gpt-5-mini` and their Batch API
  eligibility — confirm at implementation start (free `models.list()`).
- Whether the narrator lean prompt-builder is already separable from the LLM call or needs a small refactor.
- Streaming vs non-streaming for narration in batch (batch is non-streaming; the structured
  `narrate()` path, not `narrate_streaming()`, is the right seam).

## 12. Testing

- Unit: grounding (de)serialization round-trip; bounded-summary cap; cost-ceiling guard math;
  `custom_id` reconciliation; rubric parser.
- Dry-run: build both batch JSONLs and run the ceiling estimate **without submitting** — assert
  projected cost ≤ ceiling and request shapes valid.
- All deterministic / no-LLM where possible (project rule: parsing & scoring testable without the LLM).
