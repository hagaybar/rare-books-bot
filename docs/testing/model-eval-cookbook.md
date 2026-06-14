# Model Evaluation Cookbook

> How to run a model-vs-cost evaluation for a pipeline stage and decide whether to switch.
> Distilled from the 2026-06-14 narrator gold-standard eval (narrator: gpt-4.1 → gpt-5-mini).
> Companion to `docs/current/qa-framework.md` (§ Narrator Gold-Standard Evaluation).

## When to use this
- Deciding whether to switch a stage's model for cost/quality (narrator done; **interpreter is the next obvious candidate**).
- Validating a prompt change against a fixed quality bar.

## The harness (what's where)
| File | Role |
|------|------|
| `scripts/eval/run_narrator_gold_eval.py` | Orchestrator: narrate → judge → ranked `REPORT.md` + `results.json` |
| `scripts/eval/narrator_gold.py` | Pricing table, cost-ceiling guard, gold fixtures, batch request builders |
| `scripts/eval/batch_client.py` | OpenAI Batch API wrapper (submit/poll/download/reconcile) |
| `scripts/eval/author_gold_grounding.py` | $0 grounding generator (runs the pure-DB executor) |
| `data/eval/narrator_gold/<case>/` | Gold set: `query.txt` + frozen `grounding.json` + Opus-authored `gold.md` |

## Recipe
1. **Pick candidates + a judge.** Candidates = realistic deployment targets (cheaper-or-comparable). Judge = a strong model **not in the candidate slate** (and ideally not the same family — see gotcha 6).
2. **Dry-run for the cost projection (free, no submit):**
   ```bash
   poetry run python -m scripts.eval.run_narrator_gold_eval \
     --models gpt-5-mini,gpt-4.1-mini --judge-model gpt-5.4 \
     --cost-ceiling 2.00 --output-dir data/eval/runs/<date>-label --dry-run
   ```
3. **Smoke-test ONE item end-to-end first** (gotcha 3) before the full paid run.
4. **Full run (batched):** drop `--dry-run`; set `--max-narration-tokens` high for reasoning models (gotcha 2).
5. **Read `REPORT.md` + `results.json`.** Spot-check that fabrication flags are *real* (read `fabricated_claims`) before trusting the ranking.
6. **Validate the winner LIVE** (gotcha 8) — the eval scores substance, not voice/format/latency.

## Hard-won gotchas (read before you run)
1. **One model per batch.** The OpenAI Batch API rejects mixed-model files (`mismatched_model`). The harness now submits one narration batch per candidate model.
2. **Reasoning models (gpt-5.x) truncate at the token cap.** They spend the budget on hidden reasoning and emit *empty* JSON (`finish_reason=length`) — which **still bills at full output rate**. Set `--max-narration-tokens` ≥ 6–8K and pass `reasoning_effort="low"`. A truncated call is the worst value: full cost, zero output.
3. **Smoke-test one batch before the full paid run.** Three batch issues surfaced only against the real API; a ~$0.01 one-item test catches them. (See `feedback_validate_before_batch` memory.)
4. **Judge parity + rubric.** The judge must see the **same grounding the model saw** (the harness feeds it the lean narrator prompt) or it false-flags grounded facts as fabrication. The rubric must **allow general scholarly/historical knowledge** — only unsupported *collection* claims count as fabrication.
5. **The hard fabrication cap dominates.** Any fabrication caps a case at composite ≤ 1.0, so the ranking is heavily driven by "who invents links/holdings." Read composite *alongside* the fabrication count.
6. **Judge family bias.** A `gpt-5.4` judge shares a family with gpt-5 candidates. The main signal (link fabrication) is fact-checkable so bias was limited, but for a clean ranking use a neutral judge or a panel.
7. **Cost the run from `logs/llm_calls.jsonl` per stage**, not the UI counter (the in-app token/cost display is unreliable — it showed ~$0.26 when the real turn was ~$0.008).
8. **Always validate live.** The eval rewards grounding/coverage; it missed gpt-5-mini's flat formatting and jargon-leaking voice ("tranche", "held set"). Both were fixable in the narrator prompt — but only a real query on the deployed app surfaced them.

## Authoring a gold case ($0, no API key)
1. Write an `InterpretationPlan` JSON that *simulates the interpreter* — schema in `scripts/chat/plan_models.py`; copy the shape from `data/eval/narrator_gold/*/*.plan.json`.
2. Freeze grounding (pure DB, no LLM, no network):
   ```bash
   poetry run python -m scripts.eval.author_gold_grounding \
     --plan <case>.plan.json --query "<query>" --case-id <case_id>
   ```
3. Write `gold.md` from the frozen `grounding.json`, applying the narrator's evidence rules. **Hebrew query → Hebrew gold** (the narrator answers in the query's language). For semantic-subject cases, cite the matched headings with per-heading counts.
4. Cover the range: publisher · place · agent+role · multi-filter · semantic-subject · aggregation · entity+enrich · large set · empty/in-scope · Hebrew · ambiguous.
5. **Have a human review the gold set before any paid judging run** — a bad gold poisons everything.

## Deploying a model switch (and rolling back)
- The active model lives in the **server volume**: `~/rare-books-data/eval/model-config.json` (deploy **excludes** `data/`). The prompt lives in code and ships via the image.
- **Switch:** `./deploy.sh` (ships code), then write the volume config (`narrator: <model>`, keep the cheap interpreter) + `docker restart rare-books`.
- **Rollback:**
  - Model only → `rm`/edit the volume config + `docker restart` → falls back to the `config.py` default (~10s, no rebuild).
  - Code too → `./deploy.sh --rollback` (previous image tag).
- **Fragility note:** because the config is volume-only, a volume reset silently reverts the model to the `config.py` default. Re-apply the volume config after any volume migration.

## Reference result (2026-06-14)
| Model | Quality /3 | Fabrications | $/turn (narrator) |
|-------|-----------|--------------|-------------------|
| **gpt-5-mini** (chosen) | 2.56 | 0 | ~$0.003–0.005 |
| gpt-4.1-mini | 1.98 | 3 | ~$0.002 |
| gpt-4.1 (previous) | 1.58 | 7 | ~$0.015–0.021 |

Net: narrator switched to `gpt-5-mini` — higher grounded quality, zero fabrications, ~⅓ the cost. Interpreter stage not yet evaluated (the next cost lever).
