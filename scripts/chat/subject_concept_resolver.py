"""Concept -> real subject headings via cosine over precomputed embeddings.
Deterministic given (embedder, vectors, threshold). Cache is optional and keyed
by (concept_casefold, model_id, threshold)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


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

    def resolve(self, concept: str) -> list[HeadingMatch]:
        key = f"{concept.casefold()}|{self.embedder.model_id}|{self.threshold}"
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
