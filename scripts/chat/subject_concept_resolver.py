"""Concept -> real subject headings via cosine over precomputed embeddings.
Deterministic given (embedder, vectors, threshold). Cache is optional and keyed
by (concept_casefold, model_id, threshold)."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path("data/models/e5-small-onnx")
DEFAULT_CACHE_PATH = Path("data/normalization/concept_maps/semantic_subject_cache.json")
DEFAULT_THRESHOLD = 0.84
DEFAULT_TOP_K = 40


@dataclass(frozen=True)
class HeadingMatch:
    heading_value: str
    score: float


class _Embedder(Protocol):
    model_id: str

    def encode_query(self, text: str) -> np.ndarray: ...


class SubjectConceptResolver:
    def __init__(
        self,
        embedder,
        headings: list[str],
        vectors: np.ndarray,
        threshold: float = 0.84,
        top_k: int = 40,
        cache=None,
    ):
        self.embedder = embedder
        self.headings = headings
        self.vectors = vectors  # (N, dim), L2-normalized
        self.threshold = threshold
        self.top_k = top_k
        self.cache = cache  # optional dict-like {key: [headings]}

    def resolve(
        self, concept: str, scope_headings: Optional[set[str]] = None
    ) -> list[HeadingMatch]:
        """Resolve ``concept`` to ranked real headings (cosine >= threshold,
        capped at ``top_k``).

        When ``scope_headings`` is given, ranking is restricted to *those*
        headings only (the held-set's own vocabulary). This prevents the global
        top-K from being spent on headings that score high globally but are
        absent from the set the user is exploring — so a held-set count recovers
        the in-set matches instead of truncating them. Scoped resolves are
        per-set and bypass the cross-run cache.
        """
        if scope_headings is not None:
            idx = [i for i, h in enumerate(self.headings) if h in scope_headings]
            if not idx:
                return []
            q = self.embedder.encode_query(concept)
            sims = self.vectors[idx] @ q
            order = np.argsort(-sims)[: self.top_k]
            return [
                HeadingMatch(self.headings[idx[j]], float(sims[j]))
                for j in order
                if sims[j] >= self.threshold
            ]

        # Global resolve (cache key includes top_k so a re-tune invalidates).
        key = (
            f"{concept.casefold()}|{self.embedder.model_id}"
            f"|{self.threshold}|{self.top_k}"
        )
        if self.cache is not None and key in self.cache:
            cached = set(self.cache[key])
            return [HeadingMatch(h, 1.0) for h in self.headings if h in cached]
        q = self.embedder.encode_query(concept)  # (dim,), normalized
        sims = self.vectors @ q
        order = np.argsort(-sims)[: self.top_k]
        out = [
            HeadingMatch(self.headings[i], float(sims[i]))
            for i in order
            if sims[i] >= self.threshold
        ]
        if self.cache is not None:
            self.cache[key] = [m.heading_value for m in out]
        return out


# =============================================================================
# JSON-file-backed cache (persists resolved concept -> headings across runs)
# =============================================================================


class JsonFileCache(MutableMapping):
    """A dict-like cache persisted to a JSON file.

    Behaves as ``{key: list[str]}`` in memory and flushes to disk on every
    mutation so resolved concept->headings mappings survive process restarts.
    Corrupt/unreadable files start empty rather than crashing the resolver
    (the resolver simply recomputes and rewrites). The values are real
    catalogued headings, not embeddings, so the cache is human-readable and
    safe to inspect or hand-edit.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data = {str(k): list(v) for k, v in loaded.items()}
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(
                "JsonFileCache: could not load %s (%s); starting empty",
                self.path,
                exc,
            )
            self._data = {}

    def _flush(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError as exc:  # pragma: no cover - disk failure is non-fatal
            logger.warning("JsonFileCache: could not persist %s (%s)", self.path, exc)

    def __getitem__(self, key: str) -> list[str]:
        return self._data[key]

    def __setitem__(self, key: str, value: list[str]) -> None:
        self._data[key] = list(value)
        self._flush()

    def __delitem__(self, key: str) -> None:
        del self._data[key]
        self._flush()

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


# =============================================================================
# Runtime factory: build a model-backed resolver from subject_embeddings
# =============================================================================


def _load_embeddings(db_path: Path) -> tuple[list[str], Optional[np.ndarray]]:
    """Load (headings, vectors) from the ``subject_embeddings`` table.

    Decodes each BLOB via ``np.frombuffer(..., dtype=float32)`` and stacks them
    into an (N, dim) matrix aligned with the headings list. Returns an empty
    headings list and ``None`` matrix when the table is empty or absent.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            rows = conn.execute(
                "SELECT heading_value, vector FROM subject_embeddings "
                "WHERE vector IS NOT NULL"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.error(
                "load_subject_resolver: subject_embeddings table missing in %s "
                "(%s)",
                db_path,
                exc,
            )
            return [], None
    finally:
        conn.close()

    headings: list[str] = []
    vectors: list[np.ndarray] = []
    for heading_value, blob in rows:
        if not heading_value or blob is None:
            continue
        vec = np.frombuffer(blob, dtype=np.float32)
        if vec.size == 0:
            continue
        headings.append(heading_value)
        vectors.append(vec)

    if not headings:
        return [], None

    matrix = np.vstack(vectors).astype(np.float32)
    return headings, matrix


def load_subject_resolver(
    db_path: Path | str,
    model_dir: Path | str = DEFAULT_MODEL_DIR,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
    cache_path: Path | str = DEFAULT_CACHE_PATH,
) -> Optional[SubjectConceptResolver]:
    """Build a real, model-backed ``SubjectConceptResolver`` or fail loud.

    Loads every ``(heading_value, vector)`` from the ``subject_embeddings``
    table (decoding each BLOB as float32), constructs an :class:`OnnxEmbedder`
    over ``model_dir``, and wires a resolver with a JSON-file-backed cache at
    ``cache_path``.

    Fails LOUD (logs an error per the CLAUDE.md loud-failure rule) and returns
    ``None`` when the model directory is missing OR ``subject_embeddings`` is
    empty — so the ``resolve_subject_concept`` action honestly reports it cannot
    resolve rather than silently mis-counting. The ONNX model is loaded lazily
    here (NOT at import time) so importing the app stays cheap.
    """
    db_path = Path(db_path)
    model_dir = Path(model_dir)

    model_file = model_dir / "model.onnx"
    if not model_file.exists():
        logger.error(
            "load_subject_resolver: model directory %s missing model.onnx — "
            "cannot resolve concepts semantically; returning None",
            model_dir,
        )
        return None

    headings, vectors = _load_embeddings(db_path)
    if not headings or vectors is None:
        logger.error(
            "load_subject_resolver: subject_embeddings empty in %s — "
            "no precomputed heading vectors to resolve against; returning None. "
            "Run scripts/index/embed_subjects.py to populate it.",
            db_path,
        )
        return None

    # Import here (lazy) so onnxruntime/tokenizers are only required at first
    # real load, never at module import time.
    from scripts.chat.onnx_embedder import OnnxEmbedder

    embedder = OnnxEmbedder(model_dir)
    cache = JsonFileCache(Path(cache_path))
    logger.info(
        "load_subject_resolver: loaded %d heading vectors (dim=%d, model_id=%s) "
        "from %s; cache=%s",
        len(headings),
        vectors.shape[1],
        embedder.model_id,
        db_path,
        cache_path,
    )
    return SubjectConceptResolver(
        embedder=embedder,
        headings=headings,
        vectors=vectors,
        threshold=threshold,
        top_k=top_k,
        cache=cache,
    )
