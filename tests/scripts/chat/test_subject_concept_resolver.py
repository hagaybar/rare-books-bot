import numpy as np

from scripts.chat.subject_concept_resolver import HeadingMatch, SubjectConceptResolver


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
        v = self._q[t]
        return v / np.linalg.norm(v)

    def encode_passages(self, ts):
        return np.array(
            [self._h[t] / np.linalg.norm(self._h[t]) for t in ts], np.float32
        )


def test_resolver_returns_headings_above_threshold_ranked():
    headings = ["Jewish philosophy", "Philosophy, Roman", "Jewish liturgy -- Texts"]
    vecs = FakeEmbedder().encode_passages(headings)
    r = SubjectConceptResolver(
        embedder=FakeEmbedder(),
        headings=headings,
        vectors=vecs,
        threshold=0.84,
        top_k=40,
        cache=None,
    )
    out = r.resolve("philosophy")
    vals = [m.heading_value for m in out]
    assert "Jewish philosophy" in vals and "Philosophy, Roman" in vals
    assert "Jewish liturgy -- Texts" not in vals  # below threshold
    assert out[0].score >= out[-1].score  # ranked
    assert all(isinstance(m, HeadingMatch) for m in out)


def test_resolver_empty_when_nothing_clears_threshold():
    headings = ["Jewish liturgy -- Texts"]
    r = SubjectConceptResolver(
        embedder=FakeEmbedder(),
        headings=headings,
        vectors=FakeEmbedder().encode_passages(headings),
        threshold=0.84,
        top_k=40,
        cache=None,
    )
    assert r.resolve("philosophy") == []


def _resolver(top_k=40, cache=None):
    headings = ["Jewish philosophy", "Philosophy, Roman", "Jewish liturgy -- Texts"]
    return SubjectConceptResolver(
        embedder=FakeEmbedder(),
        headings=headings,
        vectors=FakeEmbedder().encode_passages(headings),
        threshold=0.84,
        top_k=top_k,
        cache=cache,
    )


def test_scope_headings_restricts_ranking_to_in_scope_vocabulary():
    """With scope_headings, only in-scope headings are ranked — even when a
    higher-scoring heading exists out of scope (the held-set-vocab fix)."""
    # Global top_k=1 would pick the single highest ("Jewish philosophy", 0.98).
    r = _resolver(top_k=1)
    # But scoping to {"Philosophy, Roman"} must return THAT, not the global top.
    out = r.resolve("philosophy", scope_headings={"Philosophy, Roman"})
    assert [m.heading_value for m in out] == ["Philosophy, Roman"]


def test_scope_headings_empty_intersection_returns_empty():
    r = _resolver()
    assert r.resolve("philosophy", scope_headings={"Nonexistent heading"}) == []


def test_scope_headings_below_threshold_excluded():
    r = _resolver()
    # "Jewish liturgy" is in scope but below threshold -> excluded
    out = r.resolve("philosophy", scope_headings={"Jewish liturgy -- Texts"})
    assert out == []


def test_scoped_resolve_bypasses_cache():
    cache = {}
    r = _resolver(cache=cache)
    r.resolve("philosophy", scope_headings={"Philosophy, Roman"})
    assert cache == {}  # scoped resolves are per-set; never cached


def test_global_cache_key_includes_top_k():
    """Re-tuning top_k must not reuse a stale cached entry (cache-key fix)."""
    cache = {}
    _resolver(top_k=1, cache=cache).resolve("philosophy")
    _resolver(top_k=2, cache=cache).resolve("philosophy")
    assert len(cache) == 2  # distinct keys per top_k, not one shared stale entry
