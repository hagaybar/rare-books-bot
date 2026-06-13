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
