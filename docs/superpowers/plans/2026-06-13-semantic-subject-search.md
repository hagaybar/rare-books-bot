# Semantic Subject Search (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans or subagent-driven-development. TDD; checkbox steps. Some tasks are **infra/ML** (model export, heading embedding, deploy) and are run inline by the orchestrator on the GPU box — they are flagged **[INLINE]**; the rest are TDD code tasks suitable for agents.

**Goal:** Fix the held-set concept-count defect (philosophy/theology → 0) by resolving a user concept to the collection's real subject headings via a local multilingual ONNX embedding model, then counting records exactly on those headings with the matched headings as evidence — held set unchanged.

**Architecture:** Offline (GPU): export `multilingual-e5-small` to ONNX, embed the distinct headings → vectors stored in `bibliographic.db`. Runtime (prod ARM CPU): `onnxruntime` loads the model + vectors; a `subject_concept_resolver` maps concept→headings (cosine ≥ 0.84, top-K, cached); a new `resolve_subject_concept` executor action feeds a held-set-scoped `retrieve` whose matched headings are surfaced as evidence; `subgroup_policy` keeps the held set unchanged for explore intent; the narrator reports the count + headings and never fabricates a zero. Spec: `docs/superpowers/specs/2026-06-13-semantic-subject-search-design.md` (gate PASSED).

**Tech Stack:** Python 3.12, sentence-transformers/optimum (offline export only), onnxruntime (runtime), numpy, SQLite, FastAPI, pytest.

---

## Validated parameters (from the prototype gate)
- Model: `intfloat/multilingual-e5-small` (384-dim). Prefixes: headings `"passage: "`, queries `"query: "`. L2-normalize both sides.
- Threshold ≈ **0.84**, top-K cap (default 40 headings). Tunable; cached per concept.
- Evidence transparency is mandatory: every count shows the matched headings.

## File structure
| File | Responsibility | New/Mod |
|---|---|---|
| `scripts/index/export_embed_model.py` | **[INLINE]** export e5-small → `data/models/e5-small-onnx/` (model.onnx + tokenizer), pinned. | Create |
| `scripts/index/embed_subjects.py` | **[INLINE]** embed distinct headings → `subject_embeddings` table. | Create |
| `scripts/chat/subject_concept_resolver.py` | concept→headings via onnxruntime + cosine + cache. | Create |
| `scripts/chat/plan_models.py` | `ResolveSubjectConceptParams`; `StepAction.RESOLVE_SUBJECT_CONCEPT`; resolved-headings output type. | Modify |
| `scripts/chat/executor.py` | handle `resolve_subject_concept`; matched headings → evidence/grounding. | Modify |
| `scripts/chat/subgroup_policy.py` | gate held-set replacement on intent (explore never replaces). | Modify |
| `scripts/chat/interpreter.py` | route "how many in ‹concept›?" → resolve_subject_concept + scoped retrieve, explore intent. | Modify |
| `scripts/chat/narrator.py` | surface matched headings as evidence; honesty guard (no fabricated zero). | Modify |
| `Dockerfile` | install `onnxruntime`; COPY the ONNX model + tokenizer. | Modify |
| `pyproject.toml` | add `onnxruntime` (runtime dep); export deps optional/dev. | Modify |
| tests under `tests/scripts/chat/` | resolver, executor action, subgroup_policy, narrator. | Create/Mod |

---

## Task 1 [INLINE]: Export the model + embed headings (the artifact)

Run by the orchestrator on the GPU box (env already proven in the prototype). Produces the deterministic artifact both ends share.

- [ ] **Step 1: Export e5-small to ONNX** — `scripts/index/export_embed_model.py`:

```python
"""Export intfloat/multilingual-e5-small to ONNX + tokenizer (pinned).
Run offline (GPU or CPU). Writes data/models/e5-small-onnx/.
"""
from pathlib import Path
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

MODEL_ID = "intfloat/multilingual-e5-small"
OUT = Path("data/models/e5-small-onnx")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    m = ORTModelForFeatureExtraction.from_pretrained(MODEL_ID, export=True)
    m.save_pretrained(OUT)
    AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(OUT)
    (OUT / "MODEL_ID.txt").write_text(MODEL_ID + "\n")
    print("exported to", OUT)

if __name__ == "__main__":
    main()
```

Run: `data/models/` should hold `e5-small-onnx/model.onnx` + tokenizer files. (int8 quantization optional follow-up; v1 ships fp32 ONNX — verify size ≤ ~140 MB; quantize if larger.)

- [ ] **Step 2: Define the embedding helper (shared encode logic)** — a small module both the embed script and the resolver import so encode is identical. Create `scripts/chat/onnx_embedder.py`:

```python
"""Identical encode path for offline + runtime (the consistency anchor).
Uses onnxruntime; mean-pools + L2-normalizes; applies e5 prefixes."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DEFAULT_DIR = Path("data/models/e5-small-onnx")

class OnnxEmbedder:
    def __init__(self, model_dir: Path = DEFAULT_DIR):
        self.session = ort.InferenceSession(str(model_dir / "model.onnx"),
                                             providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.model_id = (model_dir / "MODEL_ID.txt").read_text().strip()

    def _encode(self, texts: list[str]) -> np.ndarray:
        encs = [self.tok.encode(t) for t in texts]
        maxlen = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), maxlen), dtype=np.int64)
        mask = np.zeros((len(encs), maxlen), dtype=np.int64)
        for i, e in enumerate(encs):
            ids[i, :len(e.ids)] = e.ids
            mask[i, :len(e.ids)] = e.attention_mask
        feeds = {"input_ids": ids, "attention_mask": mask}
        # token_type_ids if the graph needs it
        if any(i.name == "token_type_ids" for i in self.session.get_inputs()):
            feeds["token_type_ids"] = np.zeros_like(ids)
        out = self.session.run(None, feeds)[0]              # (n, seq, dim)
        m = mask[:, :, None].astype(np.float32)
        pooled = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean-pool
        norm = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.clip(norm, 1e-9, None)).astype(np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" for t in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([f"query: {text}"])[0]
```

(Verify the ONNX input names with `OnnxEmbedder(...).session.get_inputs()`; e5 typically takes input_ids/attention_mask/token_type_ids. Sanity-check that `encode_passages` here reproduces the prototype's sentence-transformers vectors to ~1e-2 cosine on a few headings — if pooling differs, adjust to match the exported graph's pooling.)

- [ ] **Step 3: Embed headings** — `scripts/index/embed_subjects.py`: create table `subject_embeddings(heading_value TEXT, lang TEXT, dim INT, model_id TEXT, vector BLOB)`, collect distinct non-empty `subjects.value` and `subjects.value_he`, `encode_passages` in batches, store `vector.astype(float32).tobytes()`. Idempotent (DELETE+INSERT by model_id). Run it against `data/index/bibliographic.db`.

- [ ] **Step 4: Verify** — `sqlite3 data/index/bibliographic.db "SELECT COUNT(*), model_id FROM subject_embeddings GROUP BY model_id"` → ~6,190 rows. Spot-check the resolver (Task 2) recovers the 11 philosophy records.

- [ ] **Step 5: Commit the artifact + scripts** (the model files: decide LFS vs ship-in-image; v1 — keep model out of git, COPY in Dockerfile from a build context path, and document the export step; vectors live in the DB which is rsync'd, not git). Commit the two scripts + onnx_embedder.py.

---

## Task 2: `subject_concept_resolver` (TDD, deterministic with a fake embedder)

**Files:** Create `scripts/chat/subject_concept_resolver.py`; Test `tests/scripts/chat/test_subject_concept_resolver.py`.

- [ ] **Step 1: Failing test** (inject a fake embedder + fixed vectors so no model is needed in CI):

```python
import numpy as np
from scripts.chat.subject_concept_resolver import SubjectConceptResolver, HeadingMatch

class FakeEmbedder:
    # 2-d toy space: "philosophy"~[1,0]; headings placed by hand
    def __init__(self):
        self.model_id = "fake"
        self._q = {"philosophy": np.array([1.0, 0.0], np.float32)}
        self._h = {
            "Jewish philosophy": np.array([0.98, 0.20], np.float32),
            "Philosophy, Roman": np.array([0.95, 0.31], np.float32),
            "Jewish liturgy -- Texts": np.array([0.0, 1.0], np.float32),
        }
    def encode_query(self, t): 
        v=self._q[t]; return v/np.linalg.norm(v)
    def encode_passages(self, ts):
        return np.array([self._h[t]/np.linalg.norm(self._h[t]) for t in ts], np.float32)

def test_resolver_returns_headings_above_threshold_ranked():
    headings = ["Jewish philosophy", "Philosophy, Roman", "Jewish liturgy -- Texts"]
    vecs = FakeEmbedder().encode_passages(headings)
    r = SubjectConceptResolver(embedder=FakeEmbedder(), headings=headings,
                               vectors=vecs, threshold=0.84, top_k=40, cache=None)
    out = r.resolve("philosophy")
    vals = [m.heading_value for m in out]
    assert "Jewish philosophy" in vals and "Philosophy, Roman" in vals
    assert "Jewish liturgy -- Texts" not in vals          # below threshold
    assert out[0].score >= out[-1].score                  # ranked
    assert all(isinstance(m, HeadingMatch) for m in out)

def test_resolver_empty_when_nothing_clears_threshold():
    headings = ["Jewish liturgy -- Texts"]
    r = SubjectConceptResolver(embedder=FakeEmbedder(),
        headings=headings, vectors=FakeEmbedder().encode_passages(headings),
        threshold=0.84, top_k=40, cache=None)
    assert r.resolve("philosophy") == []
```

- [ ] **Step 2: Run → fail** (`ModuleNotFoundError`). 
- [ ] **Step 3: Implement** `scripts/chat/subject_concept_resolver.py`:

```python
"""Concept -> real subject headings via cosine over precomputed embeddings.
Deterministic given (embedder, vectors, threshold). Cache is optional and keyed
by (concept_casefold, model_id, threshold)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol
import numpy as np

@dataclass(frozen=True)
class HeadingMatch:
    heading_value: str
    score: float

class _Embedder(Protocol):
    model_id: str
    def encode_query(self, text: str) -> np.ndarray: ...

class SubjectConceptResolver:
    def __init__(self, embedder, headings: list[str], vectors: np.ndarray,
                 threshold: float = 0.84, top_k: int = 40, cache=None):
        self.embedder = embedder
        self.headings = headings
        self.vectors = vectors            # (N, dim), L2-normalized
        self.threshold = threshold
        self.top_k = top_k
        self.cache = cache                # optional dict-like {key: [headings]}

    def resolve(self, concept: str) -> list[HeadingMatch]:
        key = f"{concept.casefold()}|{self.embedder.model_id}|{self.threshold}"
        if self.cache is not None and key in self.cache:
            cached = set(self.cache[key])
            return [HeadingMatch(h, 1.0) for h in self.headings if h in cached]
        q = self.embedder.encode_query(concept)            # (dim,), normalized
        sims = self.vectors @ q
        order = np.argsort(-sims)[: self.top_k]
        out = [HeadingMatch(self.headings[i], float(sims[i]))
               for i in order if sims[i] >= self.threshold]
        if self.cache is not None:
            self.cache[key] = [m.heading_value for m in out]
        return out
```

- [ ] **Step 4: Run → pass.** Commit. (A separate `load_resolver(db_path, model_dir)` factory that builds the real resolver from `subject_embeddings` + `OnnxEmbedder` is added in Task 4 wiring; unit tests use the fake.)

---

## Task 3: Plan model + executor action `resolve_subject_concept`

**Files:** `scripts/chat/plan_models.py`, `scripts/chat/executor.py`; tests in `tests/scripts/chat/test_executor.py`.

- [ ] **Step 1: Failing executor test** — over a tmp DB with subjects, a plan `[resolve_subject_concept("philosophy") -> $step_0, retrieve(subject IN $step_0) scope=$previous_results]` (resolver injected/faked to return known headings) returns the right record count AND records the matched headings as evidence, AND leaves the held set unchanged. (Follow the existing tmp-DB fixture style in test_executor.py.)
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — add to `plan_models.py`: `StepAction.RESOLVE_SUBJECT_CONCEPT = "resolve_subject_concept"`, `ResolveSubjectConceptParams(concept: str, top_k: int = 40)`, and a `ResolvedHeadings` step-output type (`headings: list[str]`, `matches: list[dict]` of {heading, score, record_count}). In `executor.py`, add `_handle_resolve_subject_concept` that calls the loaded resolver, attaches `record_count` per heading (COUNT over scope if given), returns `ResolvedHeadings`; make `_resolve_step_ref`/scope resolution accept a `ResolvedHeadings` for the subject-IN retrieve (the retrieve matches `subjects.value IN headings`). Thread the matched headings into grounding so the narrator can cite them.
- [ ] **Step 4: Run → pass.** Commit.

---

## Task 4: Held-set lifecycle — explore never replaces

**Files:** `scripts/chat/subgroup_policy.py`; test `tests/scripts/chat/test_subgroup_policy.py`.

- [ ] **Step 1: Failing test** — a turn with intent `explore-in-set` that ran a (concept-count) retrieve returns `None` from `build_subgroup_update` (held set unchanged); a `refine-in-set` retrieve still replaces. (Pass `plan.intents` through; current logic keys on `has_retrieve` only.)
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** — gate replacement: replace only when intents indicate new-search (scope full_collection) OR `refine-in-set`; for `explore-in-set` return `None` even with a retrieve. Keep the full-set `held_record_ids` source from #62 for the replace cases.
- [ ] **Step 4: Run → pass.** Commit.

---

## Task 5: Interpreter routing (prompt) + Task 6: Narrator evidence & honesty

- [ ] **Task 5** — `interpreter.py`: teach the prompt that "how many are in ‹specific topical concept›?" over a held set emits `[resolve_subject_concept(concept) -> retrieve(subject IN $step) scope=$previous_results]` with intent `explore-in-set`; "what subjects are represented?" stays `aggregate`; "only the ‹concept› ones" is `refine-in-set` (replaces). Few-shot with philosophy. Prompt-discipline test asserts the rule + `resolve_subject_concept` keyword. TDD.
- [ ] **Task 6** — `narrator.py`: when the turn used `resolve_subject_concept`, the prompt MUST cite the matched headings ("counted via: *Jewish philosophy* (8), *Philosophy and religion* (2)…") and MUST NOT assert a fabricated zero — if no headings cleared the threshold, disclose that ("no subject headings matched 'philosophy' above the confidence threshold") rather than "there are none". TDD prompt-discipline test.

---

## Task 7: Runtime wiring + Dockerfile + deps

**Files:** `scripts/chat/onnx_embedder.py` (Task 1), executor resolver factory, `Dockerfile`, `pyproject.toml`.

- [ ] **Step 1:** add `onnxruntime` + `tokenizers` to `pyproject.toml` runtime deps; keep `optimum`/`sentence-transformers` as an optional/dev group (export only).
- [ ] **Step 2:** resolver factory `load_subject_resolver(db_path, model_dir)` — load headings+vectors from `subject_embeddings`, build `OnnxEmbedder`, construct `SubjectConceptResolver` with a JSON-file cache at `data/normalization/concept_maps/semantic_subject_cache.json`; load once at app startup (lazy singleton in `executor.py` or the app lifespan).
- [ ] **Step 3:** `Dockerfile` — `COPY data/models/e5-small-onnx /app/data/models/e5-small-onnx`; ensure `onnxruntime` installs (aarch64 wheel confirmed). Keep model out of git; it's in the build context (document the export step as a pre-deploy requirement, or add to `marc-ingest`).
- [ ] **Step 4:** startup health: log model load + vector count; fail loud if `subject_embeddings` empty (per CLAUDE.md loud-failure rule).
- [ ] **Step 5: Verify** `PYTHONPATH=. poetry run python -c "import app.api.main"` and a local end-to-end: held set + "how many in philosophy?" → ~11 with cited headings, held set unchanged. Commit.

---

## Task 8: Full gate, docs, deploy, validate

- [ ] **Gate:** `poetry run pytest -m "not integration"` + integration green; `ruff` clean on new/changed files; `tsc` (no FE change) as guard.
- [ ] **Docs:** `chatbot-api.md`, `architecture.md`, `ingestion-pipeline.md` (embed step), and **`CLAUDE.md`** (record the scoped embeddings exception). `Last verified: 2026-06-13`.
- [ ] **Merge to dev**, then **[INLINE] deploy** (after confirming disk; the model is in the build context, image +~150–200 MB) and re-run the two-turn Venice → "how many in philosophy?" scenario on prod to confirm 0→11 with cited headings.
- [ ] **Issue:** open + close the tracking issue with the before/after evidence and the merge SHA. Note e5-base as the documented upgrade path.

---

## Self-review notes (author, 2026-06-13)
- **Consistency anchor:** offline embed (Task 1/3) and runtime (Task 7) both import `OnnxEmbedder` → identical encode/pooling/normalization. The one risk (pooling mismatch vs the exported graph) is caught by Task 1 Step 2's sanity-check against the prototype vectors.
- **Determinism of tests:** all unit tests inject a `FakeEmbedder`/fixed vectors — no model download in CI. The real model is exercised only in the [INLINE] tasks + the manual prod validation.
- **Evidence contract preserved:** records match exactly on resolved headings; the narrator cites them. Embeddings only expand concept→headings (the documented exception).
- **Scope:** Phase 1 = held-set concept-count only. Collection-wide subject search + authority-graph + int8 quantization + e5-base are explicit follow-ups.
- **Placeholder honesty:** Tasks 5/6 give edit specs + test assertions rather than full prompt text because they extend the #60/#62 prompt blocks already in the files; the executor wiring in Task 3 references existing patterns (`resolve_agent`) the implementer must read first.
