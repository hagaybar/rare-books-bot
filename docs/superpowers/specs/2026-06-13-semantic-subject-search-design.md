# Semantic Subject Search via Local Multilingual Embeddings (Phase 1)

**Date**: 2026-06-13
**Status**: Approved (user, 2026-06-13; design decided collaboratively in-session — engine = local multilingual embeddings, Track 1 small ONNX on prod CPU)
**Issue**: follow-up to #62 (held-set concept-count returns 0). New issue to be opened.

## Origin

A live prod test exposed that counting a held set by a topical concept fails: over
368 "17th-century European" books, *"How many are in philosophy?"* returned **0**
though **11** records genuinely carry philosophy subjects (and ~4 theology). Root
cause (evidenced, see #62 analysis): the system has **no semantic subject
resolution** — it relies on exact/substring facet matching, so a concept like
"philosophy" (realized across many specific, multilingual headings: "Jewish
philosophy — 17th century", "Philosophy, Dutch", פילוסופיה…, none literally
"philosophy", first such facet ranked 41st of 579) is invisible. No lexical method
(substring, stemming, plurals) can bridge "religious thought" → "Jewish
philosophy" — zero shared tokens; only meaning connects them.

## Goal

Resolve a user **concept** to the **real subject headings present in the
collection** via local multilingual embeddings, then match/count records exactly
on those headings — so "how many are in philosophy?" over a held set answers
"11 — via *Jewish philosophy* (8), *Philosophy and religion* (2)…" with
deterministic MARC evidence. Phase 1 scope: the **held-set concept-count** path
(the reported defect) + the reusable resolver. Collection-wide subject search and
authority-graph augmentation are Phase 2.

## Deliberate, scoped exception to "no embedding retrieval"

CLAUDE.md says *"No embedding-based retrieval (use SQLite fielded queries first)."*
This spec makes a **narrow, documented exception**: embeddings are used **only** to
resolve *concept → the collection's real headings* (a controlled-vocabulary
expansion). **Records still match exactly on those headings**, so the Answer
Contract holds — evidence is the matched MARC subject headings, never a similarity
score. This is materially different from embedding-based *record* retrieval, which
remains excluded. CLAUDE.md will be updated to record this refined principle.

## Architecture

### Component: `subject_concept_resolver` (new, reusable, the core)
`resolve(concept: str, scope_headings: Optional[set[str]] = None) -> list[HeadingMatch]`
- Encodes `concept` with the pinned ONNX model → query vector (L2-normalized).
- Cosine vs the precomputed heading vectors (brute force over 3,944 — sub-ms, no
  vector DB); keep matches with `score >= THRESHOLD` (and a sane top-K cap).
- Returns `HeadingMatch{heading_value, score, record_count}` ranked by score —
  these are **real headings**, the evidence.
- **Cache**: memoize `concept → [headings]` into the existing
  `data/normalization/concept_maps/` (a new `semantic_subject_cache.json`) so
  repeat concepts are instant and hand-curatable; cache keyed by
  `(concept_casefold, model_id, threshold)`.
- Deterministic given fixed model + vectors + threshold.

### Offline: heading embedding (one-time / on ingest)
- New script `scripts/index/embed_subjects.py`: collect the distinct subject
  headings (`subjects.value` + non-empty `subjects.value_he`), embed each with the
  pinned ONNX model, store vectors + metadata in a new table
  `subject_embeddings(heading_value TEXT, lang TEXT, vector BLOB, model_id TEXT)`
  in `bibliographic.db` (or a sidecar `.npz` — decided in the plan; table preferred
  so it ships with the DB rsync). Records the `model_id`/version and dim.
- Runs on the dev GPU (fast) but uses the **same ONNX artifact** as runtime.
- Idempotent; re-run when the model or heading set changes.

### Runtime: query embedding on the prod CPU
- ONNX Runtime (`onnxruntime`, aarch64 wheel) loads the pinned `.onnx` + tokenizer
  at app startup; loads heading vectors from `subject_embeddings` into memory once.
- Per query: encode concept (~30–80 ms on the Oracle Ampere 4-core CPU), cosine,
  threshold. No GPU, no external API, no per-query cost.

### Model
- **`intfloat/multilingual-e5-small`** (384-dim, ~118 M) exported to **ONNX**
  (optionally int8-quantized, ~110 MB), pinned `(model_id, revision)`. Good
  English+Hebrew. Honor e5's prefix convention ("query: …" / "passage: …")
  consistently on both ends. Fallback candidate: `paraphrase-multilingual-MiniLM-L12-v2`.
- **Matching-consistency rules (the only way to get burned):** one ONNX artifact +
  tokenizer used on both ends; L2-normalize both sides; pin `(model, revision,
  prefix-scheme)`; re-embed headings on any change. Cross-arch FP differences
  (x86/CUDA vs ARM/CPU) are ~1e-6 — irrelevant to cosine ranking.

### Integration (reuses existing machinery)
- **Executor**: when a subject filter is a *concept* (flagged by the interpreter),
  resolve via the component → heading set → existing `retrieve` matches those
  headings exactly, `scope=$previous_results`, recording the matched headings as
  relaxation/evidence notes. Count = result size.
- **`subgroup_policy.build_subgroup_update`**: gate held-set *replacement* on intent
  — refine / new-search replace; **explore-in-set does not** (a concept-count
  leaves the held set unchanged even though it ran a retrieve to count).
- **Interpreter**: route "how many are in ‹concept›?" over a held set to the
  concept-filtered-count path (explore intent, scope `$previous_results`); reserve
  `aggregate` for distribution questions ("what subjects?") and `retrieve`-replace
  for refine ("only the philosophy ones").
- **Narrator**: report the count **and the matched headings** as evidence; never
  assert a fabricated zero — if the resolver returns nothing above threshold, say
  so honestly ("no headings matched 'philosophy' above the confidence threshold"),
  not "there are none."

## Validation gate (de-risk the core assumption FIRST)
Before any production wiring, a prototype eval (plan Task 1) MUST pass:
- Embed the 3,944 headings; run the resolver for **philosophy, theology, religious
  thought, jews/Jewish** against the ground truth we have (11 philosophy / ~4
  theology records in the #62 held set) and a small hand-labeled set.
- Report precision/recall@threshold; confirm Hebrew headings (פילוסופיה…) surface
  for English concepts (cross-lingual works). Pick the THRESHOLD from this curve.
- **Gate**: proceed only if precision is acceptable (target ≥ ~0.8 at a recall that
  recovers the known philosophy/theology records). If `e5-small` underperforms on
  Hebrew, switch to the fallback model or escalate before building.

## Deployment
- Docker image gains `onnxruntime` (aarch64) + the `.onnx` model + tokenizer; the
  heading vectors ship inside `bibliographic.db` (already rsync'd). +~110–150 MB
  image, ~300–500 MB RAM — comfortably within the Oracle 24 GB box. Health check
  must confirm the model loads. Portable to future AWS (same ONNX on Graviton/x86).

## Testing (deterministic — no live model in unit tests)
- **Resolver unit**: inject a tiny fake embedder + fixed heading vectors; assert
  threshold/top-K, cache read/write, ranking, evidence shape. (No model download in
  CI.)
- **Executor count path**: constructed plan with a concept filter resolving (via the
  fake resolver) to known headings over a tmp DB; assert count + matched-heading
  evidence + held set unchanged.
- **subgroup_policy**: explore-intent retrieve does NOT replace; refine does.
- **Narrator**: honesty test — empty resolver result → discloses limitation, never
  "none".
- **Quality eval**: the validation-gate harness (not a unit test; run manually /
  on demand with the real model).

## Out of scope (Phase 2 / YAGNI)
- Collection-wide semantic subject search outside the held-set count.
- NLI/LCSH authority-graph expansion (complementary, later).
- Embedding-based *record* retrieval (stays excluded).
- Title/agent semantic search (subjects only here).

## Cost
One-time: model export + the eval + embedding 3,944 headings (local GPU, free).
Per-query: **zero external cost** (CPU embed + cosine). Prod: +image/RAM only.

## Docs to update
- `docs/current/chatbot-api.md`, `docs/current/architecture.md` — the resolver,
  the concept-count path, the offline embed step.
- `CLAUDE.md` — record the scoped embeddings exception (concept→heading expansion
  only; record matching stays exact/evidential).
- `docs/current/ingestion-pipeline.md` — the new `embed_subjects` step.
